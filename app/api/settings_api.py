from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.config import settings
from app.security import verify_user_password

router = APIRouter()


class LiveToggleBody(BaseModel):
    enabled: bool


class CoinListBody(BaseModel):
    coins: List[str]


class DangerBody(BaseModel):
    password: str
    confirm: str
    coin: Optional[str] = None


def _require_password(password: str) -> None:
    user = db.row("SELECT id FROM users ORDER BY id LIMIT 1")
    if not user or not verify_user_password(int(user["id"]), password):
        raise HTTPException(403, "Geçersiz şifre")


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


class SettingsUpdateBody(BaseModel):
    values: Dict[str, Any] = {}


def _current_value(spec):
    from app import runtime_settings

    raw = runtime_settings.value(spec.key, getattr(settings, spec.key, None))
    if spec.secret:
        return "", bool(raw), runtime_settings.secret_preview(spec.key)
    return raw, False, ""


def _public_groups() -> List[Dict[str, Any]]:
    from app import runtime_settings
    from app.settings_schema import GROUPS, SETTINGS

    groups = []
    for group_id, label, description in GROUPS:
        items = []
        for spec in SETTINGS:
            if spec.group != group_id:
                continue
            value, configured, preview = _current_value(spec)
            items.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "kind": spec.kind,
                    "help": spec.help,
                    "min": spec.min,
                    "max": spec.max,
                    "options": [{"value": v, "label": l} for v, l in spec.options],
                    "placeholder": spec.placeholder,
                    "secret": spec.secret,
                    "value": value,
                    "configured": configured,
                    "preview": preview,
                }
            )
        groups.append({"id": group_id, "label": label, "description": description, "items": items})
    return groups


def _coerce(spec, raw):
    if spec.secret:
        return None if raw in (None, "") else str(raw).strip()[:500]

    if spec.kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "evet"}

    if spec.kind in {"int", "float"}:
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{spec.label}: sayı olmalı")
        if spec.kind == "int":
            number = int(number)
        if spec.min is not None and number < spec.min:
            raise HTTPException(400, f"{spec.label}: en az {spec.min:g}")
        if spec.max is not None and number > spec.max:
            raise HTTPException(400, f"{spec.label}: en fazla {spec.max:g}")
        return number

    if spec.kind == "select":
        text = str(raw).strip()
        allowed = {v for v, _ in spec.options}
        if text not in allowed:
            raise HTTPException(400, f"{spec.label}: geçersiz seçim")
        return text

    return str(raw).strip()[:500] if raw is not None else ""


@router.get("")
async def get_settings():
    from app.settings_schema import SETTINGS

    values = {}
    for spec in SETTINGS:
        if spec.secret:
            continue
        values[spec.key] = getattr(settings, spec.key, None)

    return {
        "app": {
            "name": settings.APP_NAME,
            "port": settings.PORT,
            "live_enabled": settings.LIVE_ENABLED,
            "live_unlocked": bool(db.get_setting("live_trading_unlocked", False)),
            "default_mode": settings.DEFAULT_MODE,
            "paper_fee": settings.PAPER_FEE,
            "paper_slippage": settings.PAPER_SLIPPAGE,
            "default_cash": settings.DEFAULT_CASH,
            "auto_restart": settings.AUTO_RESTART,
            "ai_enabled": settings.AI_ENABLED,
        },
        "notifications": {
            "mail_enabled": settings.MAIL_ENABLED,
            "telegram_enabled": settings.TELEGRAM_ENABLED,
        },
        "secrets": {
            "binance_key": _mask(settings.BINANCE_API_KEY),
            "binance_secret_configured": bool(settings.BINANCE_API_SECRET),
            "telegram_configured": bool(settings.TELEGRAM_TOKEN and settings.TELEGRAM_CHAT),
            "mail_configured": bool(settings.MAIL_FROM and settings.MAIL_PASSWORD and settings.MAIL_TO),
        },
        "strategy_limits": settings.STRATEGY_LIMITS,
        "risk_defaults": settings.DEFAULT_RISK,
        "supported_periods": settings.SUPPORTED_PERIODS,
        "groups": _public_groups(),
        "values": values,
    }


@router.put("")
async def update_settings(body: SettingsUpdateBody):
    """Panelden gelen ayarları doğrular, SQLite'a yazar ve anında uygular."""
    from app import runtime_settings
    from app.settings_schema import BY_KEY

    if not body.values:
        raise HTTPException(400, "Güncellenecek ayar yok")

    cleaned: Dict[str, Any] = {}
    for key, raw in body.values.items():
        spec = BY_KEY.get(key)
        if not spec:
            continue
        if spec.secret and raw in (None, ""):
            continue  # boş = mevcut gizli değeri koru
        cleaned[key] = _coerce(spec, raw)

    if not cleaned:
        return {"ok": True, "saved": [], "groups": _public_groups()}

    runtime_settings.set_many(cleaned)

    # Canlı işlem sunucu izni kapatıldıysa web anahtarını da kapat.
    if cleaned.get("LIVE_ENABLED") is False:
        db.set_setting("live_trading_unlocked", False)
        from app.supervisor import supervisor

        for bot in db.rows("SELECT id,status FROM bots WHERE mode='live'"):
            if bot["status"] in {"running", "stopping"}:
                try:
                    supervisor.stop(bot["id"])
                except Exception:
                    pass
            db.execute("UPDATE bots SET status='stopped', pid=NULL WHERE id=?", (bot["id"],))

    names = ", ".join(sorted(cleaned))
    db.log_event(None, f"Ayarlar güncellendi: {names}", "info")
    return {
        "ok": True,
        "saved": sorted(cleaned),
        "groups": _public_groups(),
        "live_enabled": settings.LIVE_ENABLED,
    }


@router.delete("/secret/{key}")
async def delete_secret(key: str):
    from app import runtime_settings
    from app.settings_schema import BY_KEY

    spec = BY_KEY.get(key)
    if not spec or not spec.secret:
        raise HTTPException(400, "Geçersiz gizli ayar")
    runtime_settings.clear_secret(key)
    db.log_event(None, f"Gizli ayar kaldırıldı: {key}", "warning")
    return {"ok": True}


@router.post("/test/mail")
async def test_mail():
    from app.notifications import notifier

    try:
        target = notifier.test_mail()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "message": f"Test e-postası gönderildi: {target}"}


@router.post("/test/telegram")
async def test_telegram():
    from app.notifications import notifier

    try:
        target = notifier.test_telegram()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "message": f"Test mesajı gönderildi: {target}"}


@router.post("/test/binance")
async def test_binance():
    if not (settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET):
        raise HTTPException(400, "Önce Binance API anahtarı ve gizli anahtarını kaydedin.")
    try:
        from binance.client import Client

        client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)
        account = client.get_account()
        balances = [
            b for b in account.get("balances", [])
            if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0
        ]
        return {"ok": True, "message": f"Bağlantı başarılı · {len(balances)} bakiyeli varlık"}
    except Exception as exc:
        raise HTTPException(400, f"Binance bağlantı hatası: {exc}")


@router.post("/live-toggle")
async def set_live_toggle(body: LiveToggleBody):
    """Tek anahtar: canlı işlem aç/kapat. Kapatınca çalışan canlı botlar durdurulur."""
    if body.enabled and not settings.LIVE_ENABLED:
        raise HTTPException(
            400,
            "Canlı işlem sunucu izni kapalı. Ayarlar > İşlem bölümünden açabilirsin.",
        )
    db.set_setting("live_trading_unlocked", bool(body.enabled))
    stopped = 0
    if not body.enabled:
        from app.supervisor import supervisor

        for bot in db.rows("SELECT id,status FROM bots WHERE mode='live'"):
            if bot["status"] in {"running", "stopping"}:
                try:
                    supervisor.stop(bot["id"])
                    stopped += 1
                except Exception:
                    pass
            db.execute("UPDATE bots SET status='stopped', pid=NULL WHERE id=?", (bot["id"],))
    db.log_event(
        None,
        "Canlı işlem " + ("açıldı" if body.enabled else f"kapatıldı ({stopped} bot durduruldu)"),
        "warning" if not body.enabled else "info",
    )
    return {"ok": True, "enabled": bool(body.enabled), "stopped": stopped}


@router.get("/coinlist")
async def coinlist():
    try:
        with open("Data/coin_list.txt", "r", encoding="utf-8") as f:
            coins = [c for c in f.readline().split(",") if c]
        return {"coins": coins}
    except OSError:
        return {"coins": []}


@router.put("/coinlist")
async def save_coinlist(body: CoinListBody):
    coins = [c.strip().upper() for c in body.coins if c.strip()]
    with open("Data/coin_list.txt", "w", encoding="utf-8") as f:
        f.write(",".join(coins))
    db.log_event(None, f"Coin listesi güncellendi ({len(coins)} coin)", "info")
    return {"ok": True, "count": len(coins)}


# ---------------------------------------------------------------------------
# Tehlikeli işlemler
# ---------------------------------------------------------------------------
def _sell_all(only_coin: Optional[str] = None) -> List[Dict[str, Any]]:
    from core import Binance

    client = Binance()
    balances = client.sahip_olduklarim()
    results = []
    for coin, amount in balances.items():
        if coin in {"USDTUSDT", "TRYUSDT"}:
            continue
        if only_coin and coin != only_coin:
            continue
        try:
            if coin.endswith("USDT"):
                base = coin[:-4]
                free = client.mevcut_adedim(coin) or amount
                if free <= 0:
                    continue
                min_qty = client.get_coin_minQTY(coin) or 0
                qty = client.miktar_duzelt(free, min_qty) if min_qty else free
                if qty <= 0:
                    continue
                order = client.market_sell(coin, qty)
                executed = float(order.get("executedQty") or qty)
                quote = float(order.get("cummulativeQuoteQty") or 0)
                db.execute(
                    "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,order_id,mode,reason,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        None,
                        coin,
                        "SELL",
                        executed,
                        quote / executed if executed else 0,
                        quote * settings.PAPER_FEE,
                        str(order.get("orderId")),
                        "live",
                        "manuel-kapat",
                        db.utcnow(),
                    ),
                )
                results.append({"coin": coin, "quantity": executed})
        except Exception as exc:
            results.append({"coin": coin, "error": str(exc)})
    db.log_event(None, f"Manuel kapatma: {len(results)} işlem", "warning")
    return results


@router.post("/danger/close-all")
async def close_all(body: DangerBody):
    _require_password(body.password)
    if body.confirm.strip() != "KAPAT":
        raise HTTPException(400, "Onay metni 'KAPAT' olmalı")
    return {"results": _sell_all()}


@router.post("/danger/full-cash")
async def full_cash(body: DangerBody):
    _require_password(body.password)
    if body.confirm.strip() != "NAKIT":
        raise HTTPException(400, "Onay metni 'NAKIT' olmalı")
    return {"results": _sell_all()}


@router.post("/danger/close-position")
async def close_position(body: DangerBody):
    _require_password(body.password)
    if not body.coin:
        raise HTTPException(400, "Coin gerekli")
    if body.confirm.strip() != "KAPAT":
        raise HTTPException(400, "Onay metni 'KAPAT' olmalı")
    return {"results": _sell_all(body.coin.upper())}
