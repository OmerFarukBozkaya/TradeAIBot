"""Binance kripto verisi (sayfalama ve yerel istemci yönetimi)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.market_data.catalog import SymbolInfo

NATIVE_PERIODS = [
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
    "1w": 604_800_000, "1M": 2_592_000_000,
}

_client_lock = threading.Lock()
_client_singleton = None


def client():
    """Binance istemcisini süreç içinde bir kez oluşturur."""
    global _client_singleton
    with _client_lock:
        if _client_singleton is None:
            from core import Binance

            _client_singleton = Binance()
        return _client_singleton


def _rows_to_data(rows: List[list]) -> Dict[str, Any]:
    return {
        "opendate": [float(r[0]) for r in rows],
        "open": [float(r[1]) for r in rows],
        "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows],
        "close": [float(r[4]) for r in rows],
        "volume_coin": [float(r[5]) for r in rows],
        "closedate": [float(r[6]) for r in rows],
        "volume_usdt": [float(r[7]) for r in rows],
        "trade_number": [float(r[8]) for r in rows],
        "buy_coin_volume": [float(r[9]) for r in rows],
        "buy_usdt_volume": [float(r[10]) for r in rows],
    }


def _time_ms(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    import datetime as dt

    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def _fetch_pages(
    symbol: str,
    interval: str,
    limit: int,
    start: Any = None,
    end: Any = None,
) -> Tuple[List[list], Dict[str, Any]]:
    import requests

    base = getattr(client(), "base_url", "https://api.binance.com")
    step = INTERVAL_MS.get(interval, 3_600_000)
    start_ms = _time_ms(start)
    end_ms = _time_ms(end)
    rows: List[list] = []
    pages = 0
    raw = 0

    if start_ms is not None:
        cursor = start_ms
        while len(rows) < limit:
            want = min(1000, limit - len(rows))
            params: Dict[str, Any] = {
                "symbol": symbol, "interval": interval, "limit": want, "startTime": cursor,
            }
            if end_ms is not None:
                params["endTime"] = end_ms
            resp = requests.get(base + "/api/v3/klines", params=params, timeout=20)
            resp.raise_for_status()
            batch = resp.json()
            pages += 1
            raw += len(batch)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < want:
                break
            next_cursor = int(batch[-1][0]) + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
    else:
        end_time = end_ms
        while len(rows) < limit:
            want = min(1000, limit - len(rows))
            params = {"symbol": symbol, "interval": interval, "limit": want}
            if end_time is not None:
                params["endTime"] = end_time
            resp = requests.get(base + "/api/v3/klines", params=params, timeout=20)
            resp.raise_for_status()
            batch = resp.json()
            pages += 1
            raw += len(batch)
            if not batch:
                break
            rows = batch + rows
            end_time = int(batch[0][0]) - 1
            if len(batch) < want:
                break

    seen = set()
    uniq: List[list] = []
    for row in sorted(rows, key=lambda r: r[0]):
        if row[0] in seen:
            continue
        seen.add(row[0])
        uniq.append(row)
    return uniq, {"pages": pages, "raw_rows": raw, "duplicates_removed": len(rows) - len(uniq)}


def fetch(
    info: SymbolInfo,
    interval: str,
    limit: int,
    *,
    start: Any = None,
    end: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    limit = max(1, int(limit))
    if limit <= 1000 and start in (None, "") and end in (None, ""):
        # Eski yol: tek istek, testlerde sahte istemciyle de çalışır.
        data = client().get_coin_data(info.native, interval, limit)
        return data, {"requested": limit, "raw_rows": len(data.get("close") or []),
                      "duplicates_removed": 0, "pages": 1}

    rows, meta = _fetch_pages(info.native, interval, limit, start, end)
    if len(rows) > limit:
        rows = rows[-limit:]
    return _rows_to_data(rows), {"requested": limit, **meta}
