from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import db, bot_state
from app import coin_lists
from app import live_prices
from app.config import LOG_DIR, settings
from app.security import verify_user_password
from app.strategies.service import build_evaluator, get_custom, normalize_specs

router = APIRouter()


class BotBody(BaseModel):
    name: str
    period: str
    strategies: List[Any]
    coins: List[str] = []
    coin_list_id: Optional[str] = None
    cash: float = settings.DEFAULT_CASH
    mode: str = "paper"
    risk: Dict[str, Any] = {}
    filters: Dict[str, Any] = {}
    auto_restart: bool = True
    max_position_pct: float = 100
    password: Optional[str] = None
    confirm: Optional[str] = None


class PromoteBody(BaseModel):
    password: Optional[str] = None
    confirm: Optional[str] = None


class ModeBody(BaseModel):
    mode: str


class ActionBody(BaseModel):
    password: Optional[str] = None


class DuplicateBody(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None


def _builtin_label(name: str) -> str:
    from app.strategies.service import list_builtin

    for item in list_builtin(include_archived=True):
        if item["name"] == name:
            return item.get("label") or name
    return name


def _bot_config(body: BotBody) -> Dict[str, Any]:
    specs = normalize_specs(body.strategies)
    if not specs:
        raise HTTPException(400, "En az bir strateji seçilmeli")
    pinned = []
    for spec in specs:
        if spec.get("type") == "custom" or spec.get("kind") == "custom":
            item = get_custom(spec["id"])
            if not item:
                raise HTTPException(400, f"Strateji bulunamadı: {spec['id']}")
            pinned.append(
                {"type": "custom", "id": item["id"], "version": item["version"], "name": item["name"]}
            )
        elif (spec.get("type") or spec.get("kind")) == "ai":
            model_id = spec.get("model_id") or spec.get("id")
            from app.ai.artifacts import load_manifest

            manifest = load_manifest(str(model_id)) if model_id else None
            if not manifest:
                raise HTTPException(400, f"AI modeli bulunamadı: {model_id}")
            if str(manifest.get("status")) == "archived":
                raise HTTPException(400, "Arşivlenmiş AI modeli botlara eklenemez")
            pinned.append(
                {
                    "type": "ai",
                    "model_id": manifest["id"],
                    "name": manifest.get("name") or manifest["id"],
                    "status": manifest.get("status"),
                }
            )
        else:
            name = spec.get("name")
            pinned.append({"type": "builtin", "name": name, "label": _builtin_label(name)})
    # Doğrulama: motor kurabiliyor mu?
    for spec in pinned:
        try:
            build_evaluator(spec)
        except Exception as exc:
            raise HTTPException(400, f"Strateji hatası: {exc}")
    if body.period not in settings.SUPPORTED_PERIODS:
        raise HTTPException(400, f"Desteklenmeyen periyot: {body.period}")
    if body.cash <= 0:
        raise HTTPException(400, "Nakit pozitif olmalı")

    # Bot riski: stratejinin tanımındaki `risk` bloğu ile istemcinin verdiği değerler
    # birleştirilir; istemci aynı anahtarı verdiyse o kazanır. Böylece canlı motor,
    # backtest ile aynı stop/takipli stop/kâr koruma kurallarını uygular.
    explicit = {k: v for k, v in (body.risk or {}).items() if v is not None and v != ""}
    inherited: Dict[str, Any] = {}
    for spec in pinned:
        if spec.get("type") != "custom":
            continue
        item = get_custom(spec["id"])
        definition = (item or {}).get("definition") or {}
        candidate = definition.get("risk") if isinstance(definition, dict) else None
        if isinstance(candidate, dict) and candidate:
            inherited = dict(candidate)
            break
    risk = {**inherited, **explicit}

    # Coin evreni: elle seçilenler + varsa coin listesi (kayıt anında çözülür).
    try:
        coins = coin_lists.normalize_coins(body.coins)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    coin_list_meta: Optional[Dict[str, Any]] = None
    if body.coin_list_id:
        listed = coin_lists.get_list(body.coin_list_id)
        if not listed:
            raise HTTPException(400, "Coin listesi bulunamadı")
        # Arayüz listeyi coinlere çözer; coinler boş bırakılırsa liste kullanılır.
        if not coins:
            coins = coin_lists.normalize_coins(listed["coins"])
        coin_list_meta = {"id": listed["id"], "name": listed["name"], "count": listed["count"]}

    config = {
        "period": body.period,
        "strategies": pinned,
        "coins": coins,
        "cash": body.cash,
        "risk": risk,
        "filters": body.filters,
        "max_position_pct": body.max_position_pct,
    }
    if coin_list_meta:
        config["coin_list"] = coin_list_meta
    return config


def _live_gate() -> None:
    if not settings.LIVE_ENABLED:
        raise HTTPException(403, "Canlı işlem sunucu izni kapalı. Ayarlar > İşlem bölümünden açabilirsin.")
    if not db.get_setting("live_trading_unlocked", False):
        raise HTTPException(403, "Canlı işlem anahtarı kapalı. Üst çubuktan açın.")


def _require_password(password: Optional[str]) -> None:
    # Tehlikeli manuel işlemler için kullanılır.
    user = db.row("SELECT id FROM users ORDER BY id LIMIT 1")
    if not password or not user or not verify_user_password(int(user["id"]), password):
        raise HTTPException(403, "Geçersiz şifre")


def _enrich_risk(config: Dict[str, Any]) -> None:
    """Botun etkin risk kurallarını strateji tanımıyla senkronlar (eski botlar dahil).

    Eski botlarda `risk` yalnızca 4 boolean içeriyordu; stratejinin ATR stop /
    kâr koruma ayarları kaydedilmemişti. Burada eksik anahtarlar tamamlanır ki
    canlı motor backtest ile aynı kuralları uygulasın.
    """
    risk = config.get("risk")
    if not isinstance(risk, dict):
        risk = {}
    for spec in config.get("strategies") or []:
        if (spec.get("type") or spec.get("kind")) != "custom":
            continue
        item = get_custom(spec.get("id") or "")
        definition = (item or {}).get("definition") or {}
        inherited = definition.get("risk") if isinstance(definition, dict) else None
        if isinstance(inherited, dict) and inherited:
            config["risk"] = {**inherited, **{k: v for k, v in risk.items() if v is not None and v != ""}}
            return
    config["risk"] = risk


def _serialize(bot: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(bot)
    item["config"] = json.loads(item.pop("config_json"))
    _enrich_strategy_names(item["config"])
    _enrich_coin_list(item["config"])
    _enrich_risk(item["config"])
    state = bot_state.load_state(item["id"]) or {}
    position = _live_position(state.get("position"), item["config"].get("risk"))
    cash = float(state.get("cash") or 0)
    pos_value = float((position or {}).get("value") or 0)
    initial = float(state.get("initial_cash") or 0)
    equity = cash + pos_value
    item["state"] = {
        "cash": state.get("cash"),
        "position": position,
        "total_realized_pnl": state.get("total_realized_pnl"),
        "unrealized_pnl": (position or {}).get("unrealized_pnl"),
        "equity": round(equity, 4),
        "total_pnl": round(equity - initial, 4) if initial > 0 else None,
        "total_pnl_pct": round((equity / initial - 1) * 100, 2) if initial > 0 else None,
        "trade_count": state.get("trade_count"),
        "last_update": state.get("last_update"),
        "last_error": state.get("last_error"),
        "reconciliation_required": state.get("reconciliation_required", False),
    }
    item["auto_restart"] = bool(item.get("auto_restart"))
    return item


def _stop_price(pos: Dict[str, Any], risk: Dict[str, Any]) -> Optional[float]:
    """Pozisyonun etkin stop seviyesi (ATR stop + takipli stop + % tavan)."""
    entry = float(pos.get("entry_price") or 0)
    if not entry:
        return None
    atr = float(pos.get("atr") or 0)
    stop: Optional[float] = None
    if atr > 0:
        stop_atr = float(risk.get("stop_atr") or 0)
        trail_atr = float(risk.get("trail_atr") or 0)
        trail_after = float(risk.get("trail_after_pct") or 0)
        highest = float(pos.get("highest_price") or entry)
        stop = entry - stop_atr * atr if stop_atr > 0 else None
        armed = True
        if trail_atr > 0 and trail_after > 0:
            armed = highest >= entry * (1 + trail_after / 100)
        if trail_atr > 0 and armed:
            trail = highest - trail_atr * atr
            stop = trail if stop is None else max(stop, trail)
    if stop is None:
        existing = pos.get("stop_price")
        # Eski kayıtta stop varsa onu da tavana tabi tut.
        stop = float(existing) if existing else None
    max_stop_pct = float(risk.get("max_stop_pct") or 0)
    if stop is not None and max_stop_pct > 0:
        stop = max(stop, entry * (1 - max_stop_pct / 100))
    return stop


def _live_position(
    position: Optional[Dict[str, Any]], risk: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Pozisyonu anlık fiyatla zenginleştirir (gerçekleşmemiş K/Z dahil).

    Canlı fiyat alınamazsa motorun son mum kapanış fiyatı kullanılır.
    """
    if not position:
        return None
    pos = dict(position)
    coin = str(pos.get("coin") or "").upper()
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("quantity") or 0)
    live = live_prices.prices([coin]).get(coin) if coin else None
    if live:
        price = float(live)
        pos["price_source"] = "live"
    else:
        price = float(pos.get("last_price") or entry or 0)
        pos["price_source"] = "candle"
    stop = _stop_price(pos, risk or {})
    if stop:
        pos["stop_price"] = round(float(stop), 8)
    if price and entry and qty:
        pos["last_price"] = round(price, 8)
        pos["unrealized_pnl"] = round((price - entry) * qty, 4)
        pos["unrealized_pnl_pct"] = round((price / entry - 1) * 100, 2)
        pos["value"] = round(price * qty, 4)
        if stop:
            pos["stop_distance_pct"] = round((price / float(stop) - 1) * 100, 2)
    return pos


def _enrich_strategy_names(config: Dict[str, Any]) -> None:
    """Bot yapılandırmasındaki stratejilere görünen ad ekler (eski kayıtlar dahil)."""
    specs = config.get("strategies") or []
    for spec in specs:
        kind = spec.get("type") or spec.get("kind")
        if kind == "custom":
            item = get_custom(spec.get("id") or "")
            spec["name"] = (item["name"] if item else spec.get("name")) or spec.get("id")
        elif kind == "builtin":
            motor = spec.get("name") or ""
            spec["label"] = spec.get("label") or _builtin_label(motor)
        elif kind == "ai":
            spec["name"] = spec.get("name") or spec.get("model_id") or spec.get("id")


def _enrich_coin_list(config: Dict[str, Any]) -> None:
    """Coin listesi adını güncel tutar (liste yeniden adlandırılmış olabilir)."""
    meta = config.get("coin_list")
    if not isinstance(meta, dict) or not meta.get("id"):
        return
    item = coin_lists.get_list(meta["id"])
    if item:
        meta["name"] = item["name"]
        meta["current_count"] = item["count"]


@router.get("")
async def list_bots():
    return [_serialize(b) for b in db.rows("SELECT * FROM bots ORDER BY created_at DESC")]


@router.post("")
async def create_bot(body: BotBody):
    config = _bot_config(body)
    mode = (body.mode or "paper").lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(400, "Mod paper veya live olmalı")
    if mode == "live":
        _live_gate()
    bot_id = f"bot_{uuid.uuid4().hex[:10]}"
    now = db.utcnow()
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            bot_id,
            body.name,
            "trade",
            mode,
            body.period,
            json.dumps(config, ensure_ascii=False),
            "stopped",
            1 if body.auto_restart else 0,
            now,
            now,
        ),
    )
    db.log_event(bot_id, f"Bot oluşturuldu ({mode}, {body.period})", "info")
    return _serialize(db.row("SELECT * FROM bots WHERE id=?", (bot_id,)))


@router.get("/{bot_id}")
async def get_bot(bot_id: str):
    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    return _serialize(bot)


@router.post("/{bot_id}/duplicate")
async def duplicate_bot(bot_id: str, body: Optional[DuplicateBody] = None):
    """Botu kopyalar: ad, periyot ve kurallar (strateji/risk/coinler) taşınır.

    İşlem geçmişi, pozisyonlar, sinyaller, olaylar ve loglar **kopyalanmaz**;
    yeni bot sıfırdan başlar (durum dosyası yok → başlangıç nakdi ve sıfır K/Z).
    """
    source = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not source:
        raise HTTPException(404, "Bot bulunamadı")

    try:
        config = json.loads(source["config_json"] or "{}")
    except (TypeError, ValueError):
        config = {}
    if not isinstance(config, dict):
        config = {}

    # Kuralların hâlâ çalıştırılabilir olduğunu doğrula (silinmiş strateji kopyalanmasın).
    for spec in normalize_specs(config.get("strategies")):
        try:
            build_evaluator(spec)
        except Exception as exc:
            raise HTTPException(400, f"Strateji hatası: {exc}")

    mode = ((body.mode if body and body.mode else source["mode"]) or "paper").lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(400, "Mod paper veya live olmalı")
    if mode == "live":
        _live_gate()

    name = ((body.name if body and body.name else "") or f"{source['name']} (kopya)").strip()
    if not name:
        raise HTTPException(400, "Bot adı gerekli")

    new_id = f"bot_{uuid.uuid4().hex[:10]}"
    now = db.utcnow()
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            new_id,
            name,
            source["type"] or "trade",
            mode,
            source["period"],
            json.dumps(config, ensure_ascii=False),
            "stopped",
            1 if source.get("auto_restart") else 0,
            now,
            now,
        ),
    )
    db.log_event(
        new_id,
        f"Bot kopyalandı: {source['name']} → {name} ({mode}, {source['period']})",
        "info",
    )
    return _serialize(db.row("SELECT * FROM bots WHERE id=?", (new_id,)))


@router.patch("/{bot_id}")
async def update_bot(bot_id: str, body: BotBody):
    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    if bot["status"] in {"running", "stopping"}:
        raise HTTPException(400, "Çalışan botu düzenlemek için önce durdurun")
    config = _bot_config(body)
    mode = (body.mode or "paper").lower()
    if mode == "live":
        _live_gate()
    db.execute(
        "UPDATE bots SET name=?, mode=?, period=?, config_json=?, auto_restart=?, updated_at=? WHERE id=?",
        (
            body.name,
            mode,
            body.period,
            json.dumps(config, ensure_ascii=False),
            1 if body.auto_restart else 0,
            db.utcnow(),
            bot_id,
        ),
    )
    return _serialize(db.row("SELECT * FROM bots WHERE id=?", (bot_id,)))


@router.delete("/{bot_id}")
async def delete_bot(bot_id: str):
    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    if bot["status"] in {"running", "stopping"}:
        raise HTTPException(400, "Önce botu durdurun")
    db.execute("DELETE FROM bots WHERE id=?", (bot_id,))
    try:
        bot_state.state_path(bot_id).unlink(missing_ok=True)
        bot_state.stop_path(bot_id).unlink(missing_ok=True)
    except OSError:
        pass
    db.log_event(bot_id, "Bot silindi", "warning")
    return {"ok": True}


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str):
    from app.supervisor import supervisor

    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    if bot["mode"] == "live":
        _live_gate()
    try:
        return supervisor.start(bot_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: str):
    from app.supervisor import supervisor

    try:
        return supervisor.stop(bot_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/{bot_id}/restart")
async def restart_bot(bot_id: str):
    from app.supervisor import supervisor

    try:
        return supervisor.restart(bot_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/{bot_id}/promote-live")
async def promote_live(bot_id: str, body: Optional[PromoteBody] = None):
    return await switch_mode(bot_id, ModeBody(mode="live"))


@router.post("/{bot_id}/mode")
async def switch_mode(bot_id: str, body: ModeBody):
    """Tek tıkla paper ↔ live geçişi. Çalışan bot önce güvenli durdurulur."""
    from app.supervisor import supervisor

    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    mode = (body.mode or "paper").lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(400, "Mod paper veya live olmalı")
    if mode == "live":
        _live_gate()
        state = bot_state.load_state(bot_id) or {}
        if state.get("position"):
            raise HTTPException(400, "Açık pozisyon varken canlıya geçilemez. Önce pozisyonu kapatın.")
    was_running = bot["status"] in {"running", "stopping"}
    if was_running:
        supervisor.stop(bot_id)
    db.execute(
        "UPDATE bots SET mode=?, status='stopped', pid=NULL, updated_at=? WHERE id=?",
        (mode, db.utcnow(), bot_id),
    )
    db.log_event(
        bot_id,
        "Mod değiştirildi: " + ("canlı" if mode == "live" else "test"),
        "warning" if mode == "live" else "info",
    )
    result = _serialize(db.row("SELECT * FROM bots WHERE id=?", (bot_id,)))
    if was_running:
        try:
            supervisor.start(bot_id)
            result = _serialize(db.row("SELECT * FROM bots WHERE id=?", (bot_id,)))
            result["restarted"] = True
        except Exception as exc:
            result["restarted"] = False
            result["error"] = str(exc)
    return result


@router.get("/{bot_id}/logs")
async def bot_logs(bot_id: str, lines: int = Query(default=200, le=2000)):
    path = LOG_DIR / "bots" / f"{bot_id}.log"
    file_lines: List[str] = []
    if path.exists():
        file_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
    events = db.rows(
        "SELECT level, message, created_at FROM events WHERE bot_id=? ORDER BY id DESC LIMIT ?",
        (bot_id, min(lines, 200)),
    )
    return {"lines": file_lines, "events": list(reversed(events))}


@router.get("/{bot_id}/logs/stream")
async def bot_log_stream(bot_id: str):
    path = LOG_DIR / "bots" / f"{bot_id}.log"

    async def generator():
        position = 0
        while True:
            if path.exists():
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(position)
                    chunk = f.read()
                    position = f.tell()
                if chunk:
                    for line in chunk.splitlines():
                        yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/{bot_id}/trades")
async def bot_trades(bot_id: str, limit: int = 200):
    return db.rows(
        "SELECT * FROM trades WHERE bot_id=? ORDER BY created_at DESC LIMIT ?", (bot_id, limit)
    )


@router.get("/{bot_id}/signals")
async def bot_signals(bot_id: str, limit: int = 200):
    return db.rows(
        "SELECT * FROM signal_events WHERE bot_id=? ORDER BY created_at DESC LIMIT ?",
        (bot_id, limit),
    )
