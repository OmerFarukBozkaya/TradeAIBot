"""Yerel piyasa verisi önbelleği.

Veriler ``Data/market/<provider>/<sembol>/<periyot>.csv`` altında tutulur.
Amaç: aynı geçmişi her backtest'te tekrar indirmemek ve ağ kesintisinde son
bilinen veriyle çalışabilmek.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.paths import paths

_FIELDS = (
    "opendate", "open", "high", "low", "close", "closedate",
    "volume_coin", "volume_usdt", "trade_number",
    "buy_coin_volume", "buy_usdt_volume",
)
_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")


def _slug(value: str) -> str:
    text = _SAFE.sub("_", str(value or "").strip())
    return text.strip("._")[:80] or "symbol"


def cache_root() -> Path:
    return paths.data / "market"


def path_for(provider: str, symbol: str, interval: str) -> Path:
    return cache_root() / _slug(provider) / _slug(symbol) / f"{_slug(interval)}.csv"


def read(provider: str, symbol: str, interval: str) -> Optional[Dict[str, Any]]:
    path = path_for(provider, symbol, interval)
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None
    if frame.empty or "opendate" not in frame.columns or "close" not in frame.columns:
        return None
    out: Dict[str, Any] = {}
    for key in _FIELDS:
        if key in frame.columns:
            out[key] = pd.to_numeric(frame[key], errors="coerce").fillna(0.0).to_numpy(dtype=float).tolist()
    if not out.get("close"):
        return None
    return out


def write(provider: str, symbol: str, interval: str, data: Dict[str, Any]) -> None:
    if not data.get("close"):
        return
    path = path_for(provider, symbol, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(data["close"])
    payload: Dict[str, Any] = {}
    for key in _FIELDS:
        values = data.get(key)
        if values is None:
            values = [0.0] * n
        payload[key] = list(values)[:n]
    frame = pd.DataFrame(payload)
    tmp = path.with_suffix(".tmp.csv")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def merge(old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """İki veri kümesini zaman damgasına göre birleştirir (yeni kazanır)."""
    if not old or not old.get("close"):
        return new
    if not new or not new.get("close"):
        return old
    combined: Dict[str, Dict[float, Any]] = {}
    for source in (old, new):
        n = len(source.get("close") or [])
        for i in range(n):
            try:
                stamp = float(source["opendate"][i])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            row = {}
            for key in _FIELDS:
                values = source.get(key)
                try:
                    row[key] = float(values[i]) if values is not None else 0.0
                except (IndexError, TypeError, ValueError):
                    row[key] = 0.0
            combined[stamp] = row

    stamps = sorted(combined)
    out: Dict[str, Any] = {"opendate": stamps}
    for key in _FIELDS:
        if key == "opendate":
            continue
        out[key] = [combined[stamp].get(key, 0.0) for stamp in stamps]
    # closedate boşsa bir sonraki mumdan türet.
    if not any(out.get("closedate") or []):
        ends = np.asarray(stamps, dtype=float)
        if len(ends) > 1:
            step = float(np.median(np.diff(ends)))
            out["closedate"] = [float(v + step - 1) for v in ends]
    return out
