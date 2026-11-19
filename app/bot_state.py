from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app import db
from app.config import STATE_DIR


def state_path(bot_id: str) -> Path:
    return STATE_DIR / f"{bot_id}.json"


def stop_path(bot_id: str) -> Path:
    return STATE_DIR / f"{bot_id}.stop"


def load_state(bot_id: str) -> Optional[Dict[str, Any]]:
    return db.read_json(state_path(bot_id))


def save_state(bot_id: str, payload: Dict[str, Any]) -> None:
    db.atomic_write_json(state_path(bot_id), payload)


def request_stop(bot_id: str) -> None:
    stop_path(bot_id).write_text("stop", encoding="utf-8")


def clear_stop(bot_id: str) -> None:
    try:
        stop_path(bot_id).unlink()
    except OSError:
        pass


def stop_requested(bot_id: str) -> bool:
    return stop_path(bot_id).exists()


# ---------------------------------------------------------------------------
# Manuel satış komutu
#
# Bot ayrı bir süreçte çalıştığı için panelden gelen "sat" isteği bir komut
# dosyasıyla iletilir. Motor her döngüde ve mum beklerken (birkaç saniyede bir)
# bu dosyayı kontrol eder, pozisyonu kapatır ve dosyayı siler.
# ---------------------------------------------------------------------------
def sell_path(bot_id: str) -> Path:
    return STATE_DIR / f"{bot_id}.sell"


def request_sell(bot_id: str, price: Optional[float] = None, note: str = "") -> None:
    payload: Dict[str, Any] = {"requested_at": db.utcnow(), "note": note}
    if price:
        payload["price"] = float(price)
    db.atomic_write_json(sell_path(bot_id), payload)


def sell_requested(bot_id: str) -> Optional[Dict[str, Any]]:
    """Bekleyen manuel satış isteğini döndürür (yoksa None)."""
    path = sell_path(bot_id)
    if not path.exists():
        return None
    payload = db.read_json(path, {}) or {}
    return payload if isinstance(payload, dict) else {}


def clear_sell(bot_id: str) -> None:
    try:
        sell_path(bot_id).unlink()
    except OSError:
        pass

