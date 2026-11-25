"""Türetilmiş altın/gümüş serileri (ons USD -> gram TL).

Yahoo Finance ücretsiz olarak ons altın/gümüş vadeli kontratını (GC=F,
SI=F) ve USDTRY kurunu (USDTRY=X) verir. Gram/TL fiyatı ayrı bir ücretli
sağlayıcı gerektirmeden şu şekilde hesaplanır::

    gram TL = ons USD × USDTRY / 31.1034768

Böylece hem ons (USD) hem gram (TL) serisi aynı geçmiş veriden üretilir.
"""

from __future__ import annotations

import bisect
from typing import Any, Dict, List, Optional, Tuple

from app.market_data.catalog import SymbolInfo, TROY_OUNCE_GRAMS, resolve_symbol
from app.market_data.providers import yahoo

NATIVE_PERIODS = ["1m", "5m", "15m", "30m", "1h", "1d"]

SELECTABLE_PERIODS = [
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h",
    "1d", "3d", "1w", "1M", "1y",
]

SPECS: Dict[str, Dict[str, str]] = {
    "GAUTRY": {
        "base": "GC=F",
        "fx": "USDTRY=X",
        "label": "Gram Altın (TL)",
    },
    "GUMUSTRY": {
        "base": "SI=F",
        "fx": "USDTRY=X",
        "label": "Gram Gümüş (TL)",
    },
}

_MAX_GAP_MS = {
    "1m": 3 * 86_400_000,
    "5m": 5 * 86_400_000,
    "15m": 7 * 86_400_000,
    "30m": 7 * 86_400_000,
    "1h": 7 * 86_400_000,
    "1d": 10 * 86_400_000,
}


def _fetch_series(
    native: str,
    interval: str,
    limit: int,
    *,
    start: Any = None,
    end: Any = None,
) -> Dict[str, Any]:
    info = SymbolInfo(
        symbol=native,
        provider="yahoo",
        native=native,
        asset_class="metal",
        live_supported=False,
        label=native,
    )
    data, _meta = yahoo.fetch(info, interval, limit, start=start, end=end)
    return data


def _nearest_index(stamps: List[float], stamp: float) -> Optional[int]:
    index = bisect.bisect_right(stamps, stamp) - 1
    return index if index >= 0 else None


def merge_with_fx(
    metal: Dict[str, Any],
    fx: Dict[str, Any],
    *,
    interval: str = "1d",
    divisor: float = TROY_OUNCE_GRAMS,
) -> Dict[str, Any]:
    """Ons USD serisini USDTRY ile çarpıp gram TL serisi üretir."""
    fx_stamps = [float(x) for x in (fx.get("opendate") or [])]
    fx_close = fx.get("close") or []
    max_gap = _MAX_GAP_MS.get(interval, 10 * 86_400_000)
    if not fx_stamps or not (metal.get("close") or []):
        raise RuntimeError("Türetilmiş seri için kaynak veri boş")

    out: Dict[str, Any] = {
        "opendate": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume_coin": [],
        "volume_usdt": [],
        "trade_number": [],
        "buy_coin_volume": [],
        "buy_usdt_volume": [],
        "closedate": [],
    }
    for i, raw_stamp in enumerate(metal.get("opendate") or []):
        stamp = float(raw_stamp)
        index = _nearest_index(fx_stamps, stamp)
        if index is None:
            continue
        if stamp - fx_stamps[index] > max_gap:
            continue
        try:
            rate = float(fx_close[index])
        except (IndexError, TypeError, ValueError):
            continue
        if not rate or rate <= 0:
            continue
        factor = rate / float(divisor)
        close = float(metal["close"][i]) * factor
        if close <= 0:
            continue
        open_ = float(metal["open"][i]) * factor
        high = float(metal["high"][i]) * factor
        low = float(metal["low"][i]) * factor
        high = max(high, open_, close)
        low = min(low, open_, close)
        out["opendate"].append(stamp)
        out["open"].append(open_)
        out["high"].append(high)
        out["low"].append(low)
        out["close"].append(close)
        out["volume_coin"].append(0.0)
        out["volume_usdt"].append(0.0)
        out["trade_number"].append(0.0)
        out["buy_coin_volume"].append(0.0)
        out["buy_usdt_volume"].append(0.0)
        closed = metal.get("closedate") or []
        out["closedate"].append(float(closed[i]) if i < len(closed) else stamp)
    if not out["close"]:
        raise RuntimeError("Türetilmiş seri oluşturulamadı (kur ve metal zamanları uyuşmadı)")
    return out


def fetch(
    info: SymbolInfo,
    interval: str,
    limit: int,
    *,
    start: Any = None,
    end: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    spec = SPECS.get(str(info.native or "").upper())
    if not spec:
        raise ValueError(f"Türetilmiş sembol tanınmadı: {info.native}")
    if interval not in NATIVE_PERIODS:
        raise ValueError(f"Türetilmiş seri için desteklenmeyen kaynak periyodu: {interval}")

    fetch_limit = max(int(limit) + 20, 50)
    metal = _fetch_series(spec["base"], interval, fetch_limit, start=start, end=end)
    fx = _fetch_series(spec["fx"], interval, fetch_limit, start=start, end=end)
    data = merge_with_fx(metal, fx, interval=interval)
    if len(data["close"]) > int(limit):
        for key in list(data.keys()):
            data[key] = data[key][-int(limit):]
    return data, {
        "requested": int(limit),
        "raw_rows": len(data["close"]),
        "pages": 2,
        "derived": True,
        "derived_from": [spec["base"], spec["fx"]],
        "has_ohlc": True,
    }


def resolve_components(symbol: str) -> Optional[Tuple[str, str]]:
    """Canlı fiyat için (temel sembol, kur sembolü) döndürür."""
    try:
        info = resolve_symbol(symbol)
    except ValueError:
        return None
    spec = SPECS.get(str(info.native or "").upper())
    if not spec:
        return None
    return spec["base"], spec["fx"]
