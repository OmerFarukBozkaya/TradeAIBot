"""Yahoo Finance verisi: altın/gümüş, ABD ve BIST hisseleri, ETF'ler.

Yahoo'nun genel ``chart`` uç noktası kullanılır; ek kütüphane gerekmez.
Intraday geçmiş Yahoo tarafından sınırlıdır (1m ~7 gün, 5-30m ~60 gün,
1h ~730 gün). Günlük ve üstü periyotlarda tüm geçmiş çekilebilir.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.market_data.catalog import SymbolInfo

NATIVE_PERIODS = ["1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"]

# Arayüzde gösterilecek periyotlar. Daha büyükleri kaynak veriden türetilir.
SELECTABLE_PERIODS = [
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h",
    "1d", "3d", "1w", "1M", "1y",
]

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

_INTRADAY_RANGE = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
}

_INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "1d": 86_400_000, "1w": 604_800_000, "1M": 2_592_000_000,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def _ms(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def _clean(values: List[Any]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(number if number == number else None)
    return out


def _anchor_ms(stamp_ms: float, interval: str) -> float:
    """Günlük ve üstü barları takvim başlangıcına hizalar.

    Yahoo, devam eden haftalık/aylık barı "şu an" damgasıyla döndürür. Bu,
    mum zamanlarını ve boşluk hesabını bozar. Haftalık barlar pazartesi 00:00,
    aylık barlar ayın 1'i 00:00 UTC'ye çekilir. Günlük barlar gün başına alınır.
    """
    native = _INTERVAL_MAP.get(interval, interval)
    if native not in {"1d", "1wk", "1mo"}:
        return stamp_ms
    parsed = dt.datetime.fromtimestamp(stamp_ms / 1000.0, dt.timezone.utc)
    day = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    if native == "1wk":
        day -= dt.timedelta(days=day.weekday())
    elif native == "1mo":
        day = day.replace(day=1)
    return day.timestamp() * 1000.0


def parse_chart(payload: Dict[str, Any], interval: str) -> Dict[str, Any]:
    """Yahoo chart JSON'ını ortak OHLCV biçimine çevirir."""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo hatası: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError("Yahoo veri döndürmedi")
    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")

    opens = _clean(quote.get("open") or [])
    highs = _clean(quote.get("high") or [])
    lows = _clean(quote.get("low") or [])
    closes = _clean(quote.get("close") or [])
    volumes = _clean(quote.get("volume") or [])
    adjusted = _clean(adj or [])

    out: Dict[str, Any] = {
        "opendate": [], "open": [], "high": [], "low": [], "close": [],
        "volume_coin": [], "volume_usdt": [], "trade_number": [],
        "buy_coin_volume": [], "buy_usdt_volume": [],
    }
    for i, stamp in enumerate(stamps):
        if i >= len(closes):
            break
        close = closes[i] if i < len(closes) else None
        if close is None or close <= 0:
            continue
        open_ = opens[i] if i < len(opens) and opens[i] is not None else close
        high = highs[i] if i < len(highs) and highs[i] is not None else max(open_, close)
        low = lows[i] if i < len(lows) and lows[i] is not None else min(open_, close)
        volume = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0

        # Temettü/bölünme düzeltmesi: adjusted close oranını OHLC'ye uygula.
        factor = 1.0
        if i < len(adjusted) and adjusted[i] not in (None, 0) and close:
            factor = float(adjusted[i]) / float(close)
        if factor and factor != 1.0:
            open_, high, low, close = open_ * factor, high * factor, low * factor, close * factor

        # Yahoo'da özellikle vadeli kontratlarda kapanış, bildirilen high/low
        # aralığının biraz dışında kalabiliyor. OHLC tutarlılığını burada
        # sağla; aksi halde her backtest "bozuk OHLC" uyarısı üretiyordu.
        high = max(high, open_, close)
        low = min(low, open_, close)

        out["opendate"].append(_anchor_ms(float(stamp) * 1000.0, interval))
        out["open"].append(float(open_))
        out["high"].append(float(high))
        out["low"].append(float(low))
        out["close"].append(float(close))
        out["volume_coin"].append(float(volume))
        out["volume_usdt"].append(float(volume) * float(close))
        out["trade_number"].append(0.0)
        out["buy_coin_volume"].append(0.0)
        out["buy_usdt_volume"].append(0.0)

    step = _INTERVAL_MS.get(interval, 86_400_000)
    stamps_ms = out["opendate"]
    out["closedate"] = [
        float((stamps_ms[i + 1] - 1) if i + 1 < len(stamps_ms) else (stamps_ms[i] + step - 1))
        for i in range(len(stamps_ms))
    ]

    # Tekrarları temizle ve kronolojik sırala.
    order = sorted(range(len(out["opendate"])), key=lambda i: out["opendate"][i])
    for key in list(out.keys()):
        out[key] = [out[key][i] for i in order]
    seen = set()
    keep = []
    for i, stamp in enumerate(out["opendate"]):
        if stamp in seen:
            continue
        seen.add(stamp)
        keep.append(i)
    if len(keep) != len(out["opendate"]):
        for key in list(out.keys()):
            out[key] = [out[key][i] for i in keep]
    return out


def fetch(
    info: SymbolInfo,
    interval: str,
    limit: int,
    *,
    start: Any = None,
    end: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    yahoo_interval = _INTERVAL_MAP.get(interval)
    if not yahoo_interval:
        raise ValueError(f"Yahoo için desteklenmeyen periyot: {interval}")

    params: Dict[str, Any] = {
        "interval": yahoo_interval,
        "includePrePost": "false",
        "events": "div,splits",
    }
    if interval in _INTRADAY_RANGE:
        params["range"] = _INTRADAY_RANGE[interval]
        limited = True
    else:
        params["period1"] = 0
        params["period2"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + 86_400
        limited = False

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{info.native}"
    response = requests.get(url, params=params, headers=_HEADERS, timeout=30)
    if response.status_code == 404:
        raise RuntimeError(f"Yahoo sembolü bulunamadı: {info.native}")
    response.raise_for_status()
    data = parse_chart(response.json(), interval)

    start_ms = _ms(start)
    end_ms = _ms(end)
    if start_ms is not None or end_ms is not None:
        keep = [
            i for i, stamp in enumerate(data["opendate"])
            if (start_ms is None or stamp >= start_ms) and (end_ms is None or stamp <= end_ms)
        ]
        for key in list(data.keys()):
            data[key] = [data[key][i] for i in keep]

    raw_rows = len(data["close"])
    if len(data["close"]) > limit:
        for key in list(data.keys()):
            data[key] = data[key][-limit:]
    meta = {
        "requested": int(limit),
        "raw_rows": raw_rows,
        "duplicates_removed": 0,
        "pages": 1,
        "intraday_limited": interval in _INTRADAY_RANGE and raw_rows < int(limit),
    }
    return data, meta
