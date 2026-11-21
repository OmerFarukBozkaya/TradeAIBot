"""OHLCV verisini istenen periyoda yeniden örnekler."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.market_data.periods import Period, parse_period

_FIELDS = (
    "opendate", "open", "high", "low", "close", "closedate",
    "volume_coin", "volume_usdt", "trade_number",
    "buy_coin_volume", "buy_usdt_volume",
)
_AGG_FIRST = {"open"}
_AGG_MAX = {"high"}
_AGG_MIN = {"low"}
_AGG_LAST = {"close"}


def _as_float(values: Any) -> List[float]:
    return [float(v) for v in (values or [])]


def _empty() -> Dict[str, Any]:
    return {key: [] for key in _FIELDS}


def _build_frame(data: Dict[str, Any], length: int) -> pd.DataFrame:
    frame = pd.DataFrame(index=pd.to_datetime(
        np.asarray(_as_float(data.get("opendate"))[:length], dtype=float),
        unit="ms", utc=True,
    ))
    for key in _FIELDS:
        if key in {"opendate", "closedate"}:
            continue
        values = data.get(key)
        if values is None:
            continue
        arr = _as_float(values)[:length]
        if len(arr) < length:
            arr = arr + [0.0] * (length - len(arr))
        frame[key] = np.asarray(arr, dtype=float)
    if "open" not in frame.columns:
        frame["open"] = frame["close"]
    return frame


def _week_start(ts: float) -> dt.date:
    day = dt.datetime.fromtimestamp(ts / 1000.0, dt.timezone.utc).date()
    return day - dt.timedelta(days=day.weekday())


def _session_keys(stamps: List[float], period: Period) -> List[int]:
    """İşlem günü verisi için bar anahtarları.

    Hafta sonu/tatil mumu olmadığı için takvim temelli gruplama boş kovalar
    üretir. Burada işlem günleri sırayla ``count``'lu gruplara ayrılır;
    haftalık/aylık/yıllık periyotlarda ise takvim bileşeni kullanılır.
    """
    unit = period.unit
    count = period.count
    if unit == "d":
        return [i // count for i in range(len(stamps))]
    if unit == "w":
        weeks: Dict[dt.date, int] = {}
        keys = []
        for stamp in stamps:
            start = _week_start(stamp)
            if start not in weeks:
                weeks[start] = len(weeks)
            keys.append(weeks[start] // count)
        return keys
    if unit == "M":
        months: Dict[tuple, int] = {}
        keys = []
        for stamp in stamps:
            day = dt.datetime.fromtimestamp(stamp / 1000.0, dt.timezone.utc)
            key = (day.year, day.month)
            if key not in months:
                months[key] = len(months)
            keys.append(months[key] // count)
        return keys
    # y
    years: Dict[int, int] = {}
    keys = []
    for stamp in stamps:
        year = dt.datetime.fromtimestamp(stamp / 1000.0, dt.timezone.utc).year
        if year not in years:
            years[year] = len(years)
        keys.append(years[year] // count)
    return keys


def _resample_sessions(data: Dict[str, Any], period: Period, length: int) -> Dict[str, Any]:
    """İşlem günü takvimine uyan varlıklar için sıralı gruplama."""
    stamps = _as_float(data.get("opendate"))[:length]
    keys = _session_keys(stamps, period)
    arrays: Dict[str, List[float]] = {}
    for key in _FIELDS:
        if key in {"opendate", "closedate"}:
            continue
        values = data.get(key)
        if values is None:
            values = [0.0] * length
        arr = _as_float(values)[:length]
        if len(arr) < length:
            arr = arr + [0.0] * (length - len(arr))
        arrays[key] = arr

    order: List[int] = []
    seen = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            order.append(key)
    grouped: Dict[int, List[int]] = {key: [] for key in order}
    for index, key in enumerate(keys):
        grouped[key].append(index)

    out: Dict[str, Any] = {"opendate": [], "open": [], "high": [], "low": [],
                           "close": [], "volume_coin": [], "volume_usdt": [],
                           "trade_number": [], "buy_coin_volume": [], "buy_usdt_volume": []}
    for key in order:
        rows = grouped[key]
        first, last = rows[0], rows[-1]
        out["opendate"].append(float(stamps[first]))
        out["open"].append(float(arrays["open"][first] if "open" in arrays else arrays["close"][first]))
        out["high"].append(float(max(arrays["high"][i] for i in rows) if "high" in arrays
                                  else max(arrays["close"][i] for i in rows)))
        out["low"].append(float(min(arrays["low"][i] for i in rows) if "low" in arrays
                                 else min(arrays["close"][i] for i in rows)))
        out["close"].append(float(arrays["close"][last]))
        for field in ("volume_coin", "volume_usdt", "trade_number",
                      "buy_coin_volume", "buy_usdt_volume"):
            out[field].append(float(sum(arrays[field][i] for i in rows)))

    # closedate: bir sonraki barın açılışından 1 ms önce.
    starts = out["opendate"]
    out["closedate"] = [
        float(starts[i + 1] - 1) if i + 1 < len(starts) else float(starts[i] + period.ms - 1)
        for i in range(len(starts))
    ]
    return out


def resample_data(
    data: Dict[str, Any],
    target: str | Period,
    *,
    session_based: bool = False,
) -> Dict[str, Any]:
    """Veriyi hedef periyoda indirger.

    - open: dönemin ilk değeri
    - high/low: dönemin en yüksek/en düşük değeri
    - close: dönemin son değeri
    - hacim alanları: toplam
    - Boş dönemler (tatil, hafta sonu) atlanır; mum uydurulmaz.

    ``session_based`` hisse/altın/TEFAS gibi yalnızca işlem günlerinde veri
    üreten seriler içindir. Bu serilerde gün/hafta/ay grupları takvim yerine
    sıralı işlem günlerine göre kurulur.
    """
    period = target if isinstance(target, Period) else parse_period(target)
    source = _as_float(data.get("opendate"))
    closes = _as_float(data.get("close"))
    if not source or not closes:
        return _empty()

    length = min(len(source), len(closes))
    if session_based and period.unit in {"d", "w", "M", "y"}:
        return _resample_sessions(data, period, length)

    frame = _build_frame(data, length)
    present = [key for key in frame.columns]

    agg: Dict[str, str] = {}
    for key in present:
        if key in _AGG_FIRST:
            agg[key] = "first"
        elif key in _AGG_MAX:
            agg[key] = "max"
        elif key in _AGG_MIN:
            agg[key] = "min"
        elif key in _AGG_LAST:
            agg[key] = "last"
        else:
            agg[key] = "sum"

    kwargs: Dict[str, Any] = {"label": "left", "closed": "left"}
    if period.unit in {"m", "h"}:
        kwargs["origin"] = "epoch"
    grouped = frame.resample(period.pandas_rule, **kwargs).agg(agg)
    grouped = grouped.dropna(subset=[key for key in ("open", "close") if key in grouped.columns])
    if grouped.empty:
        return _empty()

    starts = (grouped.index.as_unit("ns").asi8 // 1_000_000).astype("int64")
    ends = np.empty(len(starts), dtype="int64")
    if len(starts) > 1:
        ends[:-1] = starts[1:] - 1
    ends[-1] = int(starts[-1] + period.ms - 1)

    out: Dict[str, Any] = {"opendate": [float(v) for v in starts]}
    for key in _FIELDS:
        if key in {"opendate", "closedate"}:
            continue
        if key in grouped.columns:
            out[key] = [float(v) for v in grouped[key].to_numpy(dtype=float)]
        else:
            out[key] = [0.0] * len(starts)
    out["closedate"] = [float(v) for v in ends]
    return out
