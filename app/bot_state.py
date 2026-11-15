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
