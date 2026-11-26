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
    asset_class: str = ""
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


class SellBody(BaseModel):
    password: Optional[str] = None
    price: Optional[float] = None
    note: Optional[str] = None


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
        from app.market_data.periods import parse_period

        # Büyük harf / Türkçe yazım kabul edilsin (2H, 1Gun, 1W ...).
        try:
            period = parse_period(body.period).text
        except ValueError:
            raise HTTPException(
                400,
                f"Desteklenmeyen periyot: {body.period}. "
                f"Kullanılabilir: {', '.join(settings.SUPPORTED_PERIODS)}",
            )
        if period not in settings.SUPPORTED_PERIODS:
            raise HTTPException(
                400,
                f"Canlı/test botlar için desteklenmeyen periyot: {period}. "
                f"Kullanılabilir: {', '.join(settings.SUPPORTED_PERIODS)}",
            )
        body = body.model_copy(update={"period": period})
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
    # Stop güvenliği: 20–35×ATR gibi işe yaramaz ayarlar kaydedilmeden önce
    # periyot tavanına çekilir ve sert stop garantilenir. Böylece hem canlı
    # motor hem backtest aynı (mantıklı) seviyeleri kullanır.
    from app import risk as risk_rules

    risk, risk_warnings = risk_rules.normalize_risk(risk, body.period)

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

    # Canlı emirler Binance altyapısını kullanır. Hisse, altın/gümüş, döviz ve
    # TEFAS sembolleri **paper** botlarda desteklenir; gerçek emir göndermek
    # broker entegrasyonu gerektirdiği için canlı modda reddedilir.
    from app.market_data import available_periods, is_live_symbol

    unsupported = [coin for coin in coins if not is_live_symbol(coin)]
    if unsupported and body.mode == "live":
        preview = ", ".join(unsupported[:5])
        raise HTTPException(
            400,
            f"Canlı botlar yalnızca Binance kripto sembolleriyle çalışabilir. "
            f"Hisse/altın/döviz/fon için test (paper) modunu seçin: {preview}",
        )
    if unsupported:
        # Seçilen periyot her sağlayıcıda üretilebilir olmalı (TEFAS günlük vb.).
        for coin in unsupported:
            allowed = {item["id"] for item in available_periods(coin, asset_class=body.asset_class)}
            if body.period not in allowed:
                raise HTTPException(
                    400,
                    f"{coin} için {body.period} periyodu kullanılamıyor. "
                    f"Seçilebilir: {', '.join(sorted(allowed))}",
                )

    config = {
        "period": body.period,
        "strategies": pinned,
        "coins": coins,
        "cash": body.cash,
        "asset_class": str(body.asset_class or "").strip().lower(),
        "risk": risk,
        "filters": body.filters,
        "max_position_pct": body.max_position_pct,
    }
    if risk_warnings:
        config["risk_warnings"] = risk_warnings
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

    Ayrıca **her zaman** güvenli aralığa normalize edilir: eski kayıtlardaki
    20–35×ATR stoplar kartta ve motorda periyot tavanına çekilir; stop
    tanımlı değilse 2×ATR eklenir. Böylece veritabanına dokunmadan mevcut
    botlar da mantıklı stoplarla çalışır.
    """
    risk = config.get("risk")
    if not isinstance(risk, dict):
        risk = {}
    merged = risk
    found = False
    for spec in config.get("strategies") or []:
        if (spec.get("type") or spec.get("kind")) != "custom":
            continue
        item = get_custom(spec.get("id") or "")
        definition = (item or {}).get("definition") or {}
        inherited = definition.get("risk") if isinstance(definition, dict) else None
        if isinstance(inherited, dict) and inherited:
            merged = {**inherited, **{k: v for k, v in risk.items() if v is not None and v != ""}}
            found = True
            break
    from app import risk as risk_rules

    clean, warnings = risk_rules.normalize_risk(merged, config.get("period"))
    config["risk"] = clean
    if warnings:
        config["risk_warnings"] = warnings
    elif found:
        config.pop("risk_warnings", None)


def _money_pnl(bot_id: str, fee: float) -> Optional[Dict[str, float]]:
    """Botun **komisyon dahil** nakit akışından gerçek K/Z'sini hesaplar.

    Kart ile logların aynı sayıyı göstermesi için tek doğru kaynak işlem
    tablosudur (durum dosyası yeniden başlatmalarda/canlı bakiyede bozulabilir):

        nakit_akışı = Σ satış(tutar − komisyon) − Σ alış(tutar + komisyon)

    Açık pozisyon varsa çıkış komisyonu düşülerek bugünkü değeri eklenir.
    Hiç işlem yoksa ``None`` döner (eski kayıtlar durum dosyasından okunur).
    """
    rows = db.rows(
        "SELECT side, quantity, price, fee FROM trades WHERE bot_id=? ORDER BY created_at",
        (bot_id,),
    )
    if not rows:
        return None
    flow = 0.0
    bought = 0.0
    for row in rows:
        qty = float(row.get("quantity") or 0)
        price = float(row.get("price") or 0)
        fee_amount = row.get("fee")
        fee_amount = qty * price * fee if fee_amount is None else float(fee_amount)
        amount = qty * price
        if str(row.get("side")).upper() == "SELL":
            flow += amount - fee_amount
        else:
            flow -= amount + fee_amount
            bought += amount + fee_amount
    return {"flow": round(flow, 6), "bought": round(bought, 6), "trades": len(rows)}


def _serialize(bot: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(bot)
    item["config"] = json.loads(item.pop("config_json"))
    _enrich_strategy_names(item["config"])
    _enrich_coin_list(item["config"])
    _enrich_risk(item["config"])
    state = bot_state.load_state(item["id"]) or {}
    cash = float(state.get("cash") or 0)
    initial = float(state.get("initial_cash") or 0)

    fee = float(settings.PAPER_FEE or 0.001)
    if item.get("mode") == "live":
        fee = float(item["config"].get("fee") or fee)
    position = _live_position(
        state.get("position"),
        item["config"].get("risk"),
        fee=fee,
        period=str(item["config"].get("period") or item.get("period") or ""),
    )
    money = _money_pnl(item["id"], fee)
    realized_state = float(state.get("total_realized_pnl") or 0)

    # Açık pozisyon: alış maliyeti (komisyon dahil) ve satarsan eline geçecek
    # net değer. K/Z **net** hesaplanır ki "anlık" ile "toplam" birbirini tutsun.
    pos_qty = 0.0
    pos_price = 0.0
    pos_entry = 0.0
    pos_market = 0.0
    open_cost = 0.0
    open_net = 0.0
    if position:
        pos_qty = float(position.get("quantity") or 0)
        pos_price = float(position.get("last_price") or position.get("entry_price") or 0)
        pos_entry = float(position.get("entry_price") or 0)
        pos_market = pos_qty * pos_price
        open_cost = pos_qty * pos_entry * (1 + fee)
        open_net = pos_qty * pos_price * (1 - fee)
    unrealized = (open_net - open_cost) if position else 0.0
    # Fiyat farkından doğan (komisyon öncesi) kâr/zarar: kullanıcı güncel
    # fiyatla alış fiyatını kıyasladığında gördüğü sayı budur.
    unrealized_gross = (pos_price - pos_entry) * pos_qty if position else 0.0
    unrealized_gross_pct = (
        (pos_price / pos_entry - 1) * 100 if (position and pos_entry > 0) else 0.0
    )
    # Pozisyon için ödenen/ödenecek komisyon (giriş + tahmini çıkış).
    position_fees = (
        (pos_qty * pos_entry * fee) + (pos_qty * pos_price * fee) if position else 0.0
    )

    if money is not None and (initial > 0 or money["bought"] > 0):
        # Tek doğru kaynak işlem geçmişi. Açık pozisyonun alışı nakit akışında
        # negatif durduğu için geri eklenir; kalan kısım gerçekten kapanmış
        # işlemlerin net K/Z'sidir.
        capital = initial if initial > 0 else float(money["bought"])
        realized = float(money["flow"]) + open_cost
        total_pnl = realized + unrealized
        equity = capital + total_pnl
    else:
        # İşlem kaydı olmayan eski bot: durum dosyası tek kaynak.
        capital = initial
        realized = realized_state
        total_pnl = realized + unrealized
        equity = capital + total_pnl if capital > 0 else cash + pos_market

    # Botun ne kadar süredir çalıştığı: ilk başlatma zamanı → şimdi.
    started_at = state.get("started_at") or item.get("created_at") or item.get("updated_at")
    uptime = None
    if started_at:
        try:
            from datetime import datetime, timezone

            text = str(started_at).replace("Z", "+00:00")
            started = datetime.fromisoformat(text)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            uptime = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
        except (TypeError, ValueError):
            uptime = None

    item["state"] = {
        # Kuruş yuvarlamasından kalan eksi artıklar gösterilmesin. Durum
        # dosyası hiç yoksa (yeni/kopya bot) nakit "bilinmiyor" kalır.
        "cash": round(max(cash, 0.0), 4) if state.get("cash") is not None else None,
        "position": position,
        "total_realized_pnl": round(realized, 4),
        "unrealized_pnl": round(unrealized, 4) if position else None,
        "equity": round(equity, 4),
        "initial_cash": round(capital, 4) if capital else None,
        "total_pnl": round(total_pnl, 4),
        "total_pnl_pct": round(total_pnl / capital * 100, 2) if capital > 0 else None,
        "realized_pnl_pct": round(realized / capital * 100, 2) if capital > 0 else None,
        # Açık pozisyonun kendi K/Z'si. Kartta **brüt** (fiyat farkı) ana sayı,
        # komisyon dahil net ise alt bilgi olarak gösterilir; böylece güncel
        # fiyat − alış fiyatı kıyaslaması birebir tutar.
        "position_pnl": round(unrealized, 4) if position else None,
        "position_pnl_pct": (
            round(unrealized / open_cost * 100, 2) if (position and open_cost > 0) else None
        ),
        "position_pnl_gross": round(unrealized_gross, 4) if position else None,
        "position_pnl_gross_pct": round(unrealized_gross_pct, 2) if position else None,
        "position_fees": round(position_fees, 4) if position else None,
        "total_pnl_gross": round(realized + unrealized_gross, 4),
        "commission_total": round(realized + unrealized_gross - total_pnl, 4),
        "position_cost": round(open_cost, 4) if position else None,
        "position_value": round(pos_market, 4) if position else None,
        "position_net_value": round(open_net, 4) if position else None,
        "fee_pct": round(fee * 100, 3),
        "pnl_source": "trades" if money is not None else "state",
        "trade_count": state.get("trade_count"),
        "exit_reasons": state.get("exit_reasons") or {},
        "pending_exit": state.get("pending_exit"),
        "started_at": started_at,
        "uptime_seconds": uptime,
        "last_update": state.get("last_update"),
        "last_error": state.get("last_error"),
        "reconciliation_required": state.get("reconciliation_required", False),
    }
    item["auto_restart"] = bool(item.get("auto_restart"))
    return item


def _stop_price(
    pos: Dict[str, Any], risk: Dict[str, Any], period: str = ""
) -> Optional[float]:
    """Pozisyonun etkin stop seviyesi (canlı motorla aynı kurallar)."""
    from app import risk as risk_rules

    entry = float(pos.get("entry_price") or 0)
    if not entry:
        return None
    atr = float(pos.get("atr") or 0)
    highest = float(pos.get("highest_price") or entry)
    stop, _kind = risk_rules.effective_stop(
        entry, atr, highest, risk, floor=pos.get("stop_floor"), period=period
    )
    if stop is None:
        existing = pos.get("stop_price")
        stop = float(existing) if existing else None
    # effective_stop artık periyot tavanını uyguluyor; yine de eski kayıtlardan
    # gelen çok uzak stop değerleri tavanla sınırlanır.
    cap_pct = risk_rules.stop_cap_pct(period, risk)
    if stop is not None:
        stop = max(float(stop), entry * (1 - cap_pct / 100))
    return stop


def _live_position(
    position: Optional[Dict[str, Any]],
    risk: Optional[Dict[str, Any]] = None,
    fee: float = 0.0,
    period: str = "",
) -> Optional[Dict[str, Any]]:
    """Pozisyonu anlık fiyatla zenginleştirir.

    ``unrealized_pnl`` **komisyon dahil nettir**: giriş komisyonu maliyete
    eklenir, çıkış komisyonu satış gelirinden düşülür. Böylece pozisyonun
    "şimdi satsam elime ne geçer" değeri ile karttaki toplam K/Z tutarlı olur.
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
        age = live_prices.ages([coin]).get(coin)
        if age is not None:
            pos["price_age_seconds"] = age
    else:
        price = float(pos.get("last_price") or entry or 0)
        pos["price_source"] = "candle"
        if pos.get("last_price_at"):
            pos["price_at"] = pos.get("last_price_at")
    stop = _stop_price(pos, risk or {}, period)
    if stop:
        pos["stop_price"] = round(float(stop), 8)
    from app import risk as risk_rules

    entry_atr = float(pos.get("atr") or 0)
    target = risk_rules.target_price(entry, entry_atr, risk or {})
    if target is not None:
        pos["take_profit_price"] = round(float(target), 8)
        if price:
            pos["take_profit_distance_pct"] = round((float(target) / price - 1) * 100, 2)
    partial_target = risk_rules.partial_target_price(entry, entry_atr, risk or {})
    if partial_target is not None and not pos.get("partial_taken"):
        pos["partial_target_price"] = round(float(partial_target), 8)
    pos["breakeven_armed"] = bool(pos.get("stop_floor"))
    rate = max(0.0, float(fee or 0.0))
    if price and entry and qty:
        cost = qty * entry * (1 + rate)
        net_value = qty * price * (1 - rate)
        pos["last_price"] = round(price, 8)
        pos["cost"] = round(cost, 4)
        pos["value"] = round(price * qty, 4)
        pos["net_value"] = round(net_value, 4)
        # "Pozisyon ne kadar karda?" sorusunun en doğrudan cevabı: fiyat farkı.
        # Kullanıcı güncel fiyatla alışı kıyasladığında bu sayıyı görmeli;
        # komisyon etkisi ayrı alanda (net) verilir.
        pos["pnl_gross"] = round((price - entry) * qty, 4)
        pos["pnl_gross_pct"] = round((price / entry - 1) * 100, 2) if entry > 0 else 0.0
        pos["unrealized_pnl"] = round(net_value - cost, 4)
        pos["unrealized_pnl_pct"] = round((net_value - cost) / cost * 100, 2) if cost > 0 else 0.0
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
def list_bots():
    bots = db.rows("SELECT * FROM bots ORDER BY created_at DESC")
    # Tüm açık pozisyonların fiyatı tek toplu istekte çekilir. Bot sayısı
    # arttığında her bot için ayrı ağ çağrısı yapılması paneli yavaşlatıp
    # anlık K/Z'nin takılmasına yol açıyordu.
    coins = []
    for bot in bots:
        state = bot_state.load_state(bot["id"]) or {}
        position = state.get("position") or {}
        coin = str(position.get("coin") or "").strip().upper()
        if coin and coin not in coins:
            coins.append(coin)
    if coins:
        try:
            live_prices.prices(coins)
        except Exception:  # noqa: BLE001 - fiyat servisi paneli düşürmesin
            pass
    return [_serialize(b) for b in bots]


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
        from app.market_data import is_live_symbol

        if any(not is_live_symbol(coin) for coin in (config.get("coins") or [])):
            raise HTTPException(
                400,
                "Kripto dışı sembol içeren bot canlı modda kopyalanamaz; test modunu seçin.",
            )

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


@router.post("/{bot_id}/sell")
async def sell_position(bot_id: str, body: Optional[SellBody] = None):
    """Manuel satış: açık pozisyonu kapatır.

    Çalışan botta istek komut dosyasıyla motora iletilir; motor birkaç saniye
    içinde piyasa fiyatından (veya verilen fiyattan) satar. Bot durmuşsa ve
    açık pozisyon varsa satışı uygulayabilmesi için bot yeniden başlatılır.
    """
    from app.supervisor import supervisor

    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    state = bot_state.load_state(bot_id) or {}
    position = state.get("position")
    if not position:
        raise HTTPException(400, "Açık pozisyon yok")
    if body and body.password:
        _require_password(body.password)

    running = bot["status"] in {"running", "stopping"}
    bot_state.request_sell(bot_id, price=(body.price if body else None), note=(body.note if body else "") or "panel")
    db.log_event(bot_id, "Panelden manuel satış istendi", "info")
    if not running:
        try:
            supervisor.start(bot_id)
        except Exception as exc:  # noqa: BLE001
            bot_state.clear_sell(bot_id)
            raise HTTPException(400, f"Satış için bot başlatılamadı: {exc}")
    return {
        "ok": True,
        "queued": True,
        "started": not running,
        "coin": position.get("coin"),
        "quantity": position.get("quantity"),
        "note": "Satış birkaç saniye içinde uygulanır; sonuç kartta ve loglarda görünür.",
    }


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
        from app.market_data import is_live_symbol

        config = db.json.loads(bot.get("config_json") or "{}")
        non_crypto = [
            coin for coin in (config.get("coins") or [])
            if not is_live_symbol(coin)
        ]
        if non_crypto:
            raise HTTPException(
                400,
                "Bu bot hisse/altın/döviz/fon sembolleri içeriyor; canlı mod yalnızca "
                "Binance kripto sembolleriyle çalışır. Test modunu kullanın.",
            )
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


@router.get("/{bot_id}/live-chart")
def bot_live_chart(bot_id: str, candles: int = Query(default=150, ge=20, le=400)):
    """Açık pozisyon için canlı izleme grafiği.

    Mum geçmişini (botun periyodunda) ve pozisyonun alış/stop/kâr al
    seviyelerini tek yanıtta döndürür. Panel bunu 10 saniyede bir çağırır.

    Önbellek **yazılmaz** (``use_cache=False``): canlı izleme sık çalışır ve
    kısa bir pencere istediği için uzun geçmiş önbelleğini küçültmemelidir.
    Ağ hatasında panel son grafiği korur.
    """
    bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
    if not bot:
        raise HTTPException(404, "Bot bulunamadı")
    payload = _serialize(bot)
    position = (payload.get("state") or {}).get("position")
    if not position:
        raise HTTPException(409, "Bu botta açık pozisyon yok")

    coin = str(position.get("coin") or "").upper()
    period = str(bot.get("period") or "1h")
    config = payload.get("config") or {}
    asset_class = str(config.get("asset_class") or "")

    from app.market_data import load_history

    try:
        data, meta = load_history(
            coin, period, int(candles), asset_class=asset_class, use_cache=False
        )
    except Exception as exc:  # noqa: BLE001 - ağ/sağlayıcı hatası panele taşınır
        raise HTTPException(400, f"{coin} mum verisi alınamadı: {exc}")

    times = data.get("opendate") or []
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    volumes = data.get("volume_usdt") or data.get("volume_coin") or []
    closedates = data.get("closedate") or []

    rows = []
    for i, stamp in enumerate(times):
        try:
            rows.append(
                {
                    "time": float(stamp),
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                    "close_time": float(closedates[i]) if i < len(closedates) else None,
                }
            )
        except (IndexError, TypeError, ValueError):
            continue

    price = position.get("last_price") or position.get("entry_price")
    return {
        "bot_id": bot_id,
        "name": payload.get("name"),
        "mode": payload.get("mode"),
        "coin": coin,
        "period": period,
        "asset_class": asset_class,
        "provider": meta.get("provider") or meta.get("source"),
        "candles": rows,
        "live_price": price,
        "price_source": position.get("price_source"),
        "price_age_seconds": position.get("price_age_seconds"),
        "position": {
            "quantity": position.get("quantity"),
            "entry_price": position.get("entry_price"),
            "opened_at": position.get("opened_at"),
            "stop_price": position.get("stop_price"),
            "stop_distance_pct": position.get("stop_distance_pct"),
            "take_profit_price": position.get("take_profit_price"),
            "partial_target_price": position.get("partial_target_price"),
            "breakeven_armed": position.get("breakeven_armed", False),
            "pnl_gross": position.get("pnl_gross"),
            "pnl_gross_pct": position.get("pnl_gross_pct"),
            "unrealized_pnl": position.get("unrealized_pnl"),
            "unrealized_pnl_pct": position.get("unrealized_pnl_pct"),
            "candles_held": position.get("candles"),
        },
    }
