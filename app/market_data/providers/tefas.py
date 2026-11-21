"""TEFAS yatırım fonu fiyatları.

Yeni TEFAS JSON API'si günlük NAV (fon fiyatı) verir; OHLC ve hacim yoktur.
Bu nedenle ``open=high=low=close`` ve hacim alanları 0 olarak doldurulur.
API en fazla 60 aylık (5 yıl) geriye dönük veri verir.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.market_data.catalog import SymbolInfo

NATIVE_PERIODS = ["1d"]

_ENDPOINT = "https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tefas.gov.tr/",
}
_VALID_MONTHS = (1, 3, 6, 12, 36, 60)


def _date(value: Any) -> Optional[dt.date]:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip().replace("Z", "")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Geçersiz tarih: {value!r}")


def _months_back(start: Optional[dt.date]) -> int:
    if start is None:
        return 60
    needed = math.ceil(max(0, (dt.date.today() - start).days) / 30) + 1
    for months in _VALID_MONTHS:
        if months >= needed:
            return months
    return 60


def parse_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """TEFAS ``resultList`` satırlarını ortak OHLCV biçimine çevirir."""
    prices: Dict[float, float] = {}
    for row in rows or []:
        raw_date = row.get("tarih")
        raw_price = row.get("fiyat")
        try:
            date = _date(raw_date)
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if date is None or price <= 0:
            continue
        stamp = float(dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
        prices[stamp] = price

    stamps = sorted(prices)
    out: Dict[str, Any] = {
        "opendate": stamps,
        "open": [prices[s] for s in stamps],
        "high": [prices[s] for s in stamps],
        "low": [prices[s] for s in stamps],
        "close": [prices[s] for s in stamps],
        "volume_coin": [0.0] * len(stamps),
        "volume_usdt": [0.0] * len(stamps),
        "trade_number": [0.0] * len(stamps),
        "buy_coin_volume": [0.0] * len(stamps),
        "buy_usdt_volume": [0.0] * len(stamps),
        "closedate": [float(s + 86_400_000 - 1) for s in stamps],
    }
    return out


def fetch(
    info: SymbolInfo,
    interval: str,
    limit: int,
    *,
    start: Any = None,
    end: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if interval != "1d":
        raise ValueError("TEFAS fonları yalnızca günlük (1d ve üstü) veri sağlar")

    start_date = _date(start)
    end_date = _date(end)
    months = _months_back(start_date)
    payload = {"fonKodu": info.native, "dil": "TR", "periyod": months}
    response = requests.post(_ENDPOINT, json=payload, headers=_HEADERS, timeout=30)
    if response.status_code == 404:
        raise RuntimeError(f"TEFAS fonu bulunamadı: {info.native}")
    response.raise_for_status()
    body = response.json()
    if body.get("errorMessage"):
        raise RuntimeError(f"TEFAS hatası: {body['errorMessage']}")
    rows = body.get("resultList") or []
    data = parse_rows(rows)

    if not data["close"]:
        raise RuntimeError(f"TEFAS fonu için veri bulunamadı: {info.native}")

    if start_date is not None or end_date is not None:
        start_ms = (
            dt.datetime(start_date.year, start_date.month, start_date.day, tzinfo=dt.timezone.utc).timestamp() * 1000
            if start_date else None
        )
        end_ms = (
            dt.datetime(end_date.year, end_date.month, end_date.day, tzinfo=dt.timezone.utc).timestamp() * 1000
            + 86_400_000 - 1
            if end_date else None
        )
        keep = [
            i for i, stamp in enumerate(data["opendate"])
            if (start_ms is None or stamp >= start_ms) and (end_ms is None or stamp <= end_ms)
        ]
        for key in list(data.keys()):
            data[key] = [data[key][i] for i in keep]
        if not data["close"]:
            raise RuntimeError("Seçilen tarih aralığında TEFAS verisi yok")

    raw_rows = len(data["close"])
    if len(data["close"]) > limit:
        for key in list(data.keys()):
            data[key] = data[key][-limit:]
    return data, {
        "requested": int(limit),
        "raw_rows": raw_rows,
        "duplicates_removed": 0,
        "pages": 1,
        "lookback_months": months,
        "has_ohlc": False,
    }
