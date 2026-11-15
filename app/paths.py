from __future__ import annotations

from app.config import BASE_DIR

__all__ = ["BASE_DIR", "paths"]


class _Paths:
    base = BASE_DIR
    data = BASE_DIR / "Data"
    logs = BASE_DIR / "Log"
    state = BASE_DIR / "state"
    db = BASE_DIR / "Data" / "tradeai.db"
    coin_list = BASE_DIR / "Data" / "coin_list.txt"
    strategies = BASE_DIR / "Data" / "Strategy" / "strategys.json"


paths = _Paths()
