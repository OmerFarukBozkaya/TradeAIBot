"""İndikatör kataloğu ve normalize edici adaptör katmanı.

Tüm indikatör çıktıları giriş uzunluğunda ve başları `None` olacak şekilde hizalanır.
Bu, kural motorunun doğru mumla eşleşmesi için zorunludur.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core import Indikator


def _pad(values: List[Any], length: int) -> List[Any]:
    values = list(values or [])
    if len(values) < length:
        return [None] * (length - len(values)) + values
    if len(values) > length:
        return values[-length:]
    return values


def _series(data: Dict[str, List[float]], name: str) -> List[float]:
    return list(data.get(name) or [])


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b in (None, 0):
        return None
    return a / b


def _bb(data, params):
    length = int(params.get("length", 20))
    mult = float(params.get("std", 2.0))
    lower, mid, upper = Indikator.BB(_series(data, "close"), length)
    n = len(data["close"])
    lower, mid, upper = _pad(lower, n), _pad(mid, n), _pad(upper, n)
    width, percent_b = [], []
    for i in range(n):
        if None in (lower[i], mid[i], upper[i]):
            width.append(None)
            percent_b.append(None)
        else:
            width.append(_safe_div(upper[i] - lower[i], mid[i]))
            percent_b.append(_safe_div(data["close"][i] - lower[i], upper[i] - lower[i]))
    # std çarpanı 2'den farklıysa ölçekle
    if mult != 2.0:
        width = [None if v is None else v * (mult / 2.0) for v in width]
    return {"upper": upper, "middle": mid, "lower": lower, "width": width, "percent_b": percent_b}


def _macd(data, params):
    macd, signal = Indikator.MACD(
        _series(data, "close"),
        int(params.get("fast", 12)),
        int(params.get("slow", 26)),
        int(params.get("signal", 9)),
    )
    n = len(data["close"])
    macd, signal = _pad(macd, n), _pad(signal, n)
    hist = [
        None if (macd[i] is None or signal[i] is None) else macd[i] - signal[i]
        for i in range(n)
    ]
    return {"macd": macd, "signal": signal, "histogram": hist}


def _atr(data, params):
    atr = _pad(
        Indikator.ATR(
            _series(data, "high"), _series(data, "low"), _series(data, "close"),
            int(params.get("length", 14)),
        ),
        len(data["close"]),
    )
    pct = [
        None if (atr[i] is None or data["close"][i] == 0) else atr[i] / data["close"][i]
        for i in range(len(atr))
    ]
    return {"value": atr, "atr_pct": pct}


def _adx(data, params):
    adx = _pad(
        Indikator.ADX(
            _series(data, "high"), _series(data, "low"), _series(data, "close"),
            int(params.get("length", 14)),
        ),
        len(data["close"]),
    )
    return {"adx": adx}


def _supertrend(data, params):
    values, direction = Indikator.Super_Trend(
        _series(data, "high"), _series(data, "low"), _series(data, "close"),
        int(params.get("atr_length", 10)), float(params.get("factor", 3.0)),
    )
    n = len(data["close"])
    return {"value": _pad(values, n), "direction": _pad(direction, n)}


def _stochrsi(data, params):
    k, d = Indikator.StochasticRSI(
        _series(data, "close"),
        int(params.get("rsi_length", 14)),
        int(params.get("stoch_length", 14)),
        int(params.get("smooth_k", 3)),
        int(params.get("smooth_d", 3)),
    )
    n = len(data["close"])
    return {"k": _pad(k, n), "d": _pad(d, n)}


def _ichimoku(data, params):
    t, k, a, b = Indikator.Ichimoku_Bulutu(_series(data, "high"), _series(data, "low"))
    n = len(data["close"])
    return {
        "tenkan": _pad(t, n),
        "kijun": _pad(k, n),
        "senkou_a": _pad(a, n),
        "senkou_b": _pad(b, n),
    }


def _donchian(data, params):
    upper, lower = Indikator.Donchian_Kanali(
        _series(data, "high"), _series(data, "low"), int(params.get("length", 20))
    )
    n = len(data["close"])
    upper, lower = _pad(upper, n), _pad(lower, n)
    middle = [
        None if (upper[i] is None or lower[i] is None) else (upper[i] + lower[i]) / 2
        for i in range(n)
    ]
    return {"upper": upper, "lower": lower, "middle": middle}


def _mfi(data, params):
    value = Indikator.MFI(
        _series(data, "high"), _series(data, "low"), _series(data, "close"),
        _series(data, "volume_coin"), int(params.get("length", 14)),
    )
    return {"value": _pad(value, len(data["close"]))}


def _sma_of(data, source, length):
    values = _series(data, source)
    return _pad(Indikator.SMA(values, length), len(values))


def _volume_sma(data, params):
    length = int(params.get("length", 20))
    value = _sma_of(data, "volume_coin", length)
    ratio = [
        None if (value[i] in (None, 0)) else data["volume_coin"][i] / value[i]
        for i in range(len(data["close"]))
    ]
    return {"value": value, "ratio": ratio}


def _ema(data, params):
    value = Indikator.EMA(_series(data, "close"), int(params.get("length", 20)))
    return {"value": _pad(value, len(data["close"]))}


def _sma(data, params):
    return {"value": _sma_of(data, "close", int(params.get("length", 20)))}


def _rsi(data, params):
    value = Indikator.RSI(_series(data, "close"), int(params.get("length", 14)))
    return {"value": _pad(value, len(data["close"]))}


def _cci(data, params):
    value = Indikator.CCI(
        _series(data, "high"), _series(data, "low"), _series(data, "close"),
        int(params.get("period", 20)), int(params.get("length", 5)),
    )
    return {"value": _pad(value, len(data["close"]))}


def _momentum(data, params):
    value = Indikator.Momentum(_series(data, "close"), int(params.get("length", 10)))
    return {"value": _pad(value, len(data["close"]))}


def _psar(data, params):
    value = Indikator.ParabolicSAR(
        _series(data, "high"), _series(data, "low"),
        float(params.get("step", 0.02)), float(params.get("max", 0.2)),
    )
    return {"value": _pad(value, len(data["close"]))}


def _bb_rsi(data, params):
    rsi = Indikator.RSI(_series(data, "close"), int(params.get("rsi_length", 14)))
    lower, mid, upper = Indikator.BB(rsi, int(params.get("bb_length", 20)))
    n = len(data["close"])
    return {
        "rsi": _pad(rsi, n),
        "lower": _pad(lower, n),
        "middle": _pad(mid, n),
        "upper": _pad(upper, n),
    }


# ---------------------------------------------------------------------------
# Tillson T3
# ---------------------------------------------------------------------------
def _ema_none(values: List[Any], length: int) -> List[Optional[float]]:
    """None toleranslı EMA (Pine ile aynı özyineleme; ilk değerle tohumlanır)."""
    length = max(1, int(length))
    alpha = 2.0 / (length + 1.0)
    out: List[Optional[float]] = [None] * len(values)
    prev: Optional[float] = None
    for i, value in enumerate(values):
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def _rolling_mean_std(values: List[Any], length: int) -> tuple[List[Optional[float]], List[Optional[float]]]:
    """Kayan ortalama ve popülasyon standart sapması (Pine ta.stdev ile aynı)."""
    length = max(1, int(length))
    n = len(values)
    mean: List[Optional[float]] = [None] * n
    std: List[Optional[float]] = [None] * n
    for i in range(length - 1, n):
        window = values[i - length + 1:i + 1]
        if any(v is None for v in window):
            continue
        vals = [float(v) for v in window]
        m = sum(vals) / length
        var = sum((v - m) ** 2 for v in vals) / length
        mean[i] = m
        std[i] = var ** 0.5
    return mean, std


def _t3(data, params):
    """Tillson T3: 6 katmanlı EMA + hacim faktörü katsayıları."""
    length = max(1, int(params.get("length", 8)))
    a = float(params.get("factor", 0.7))
    n = len(data["close"])
    high, low, close = _series(data, "high"), _series(data, "low"), _series(data, "close")

    src = [(high[i] + low[i] + 2.0 * close[i]) / 4.0 for i in range(n)]
    e1 = _ema_none(src, length)
    e2 = _ema_none(e1, length)
    e3 = _ema_none(e2, length)
    e4 = _ema_none(e3, length)
    e5 = _ema_none(e4, length)
    e6 = _ema_none(e5, length)

    c1 = -a * a * a
    c2 = 3 * a * a + 3 * a * a * a
    c3 = -6 * a * a - 3 * a - 3 * a * a * a
    c4 = 1 + 3 * a + a * a * a + 3 * a * a

    value: List[Optional[float]] = [None] * n
    for i in range(n):
        if None in (e3[i], e4[i], e5[i], e6[i]):
            continue
        value[i] = c1 * e6[i] + c2 * e5[i] + c3 * e4[i] + c4 * e3[i]

    direction: List[Optional[int]] = [None] * n
    slope: List[Optional[float]] = [None] * n
    for i in range(n):
        if value[i] is None:
            continue
        if i == 0 or value[i - 1] is None:
            direction[i] = 0
            continue
        diff = value[i] - value[i - 1]
        slope[i] = diff
        direction[i] = 1 if diff > 0 else (-1 if diff < 0 else 0)
    return {"value": value, "direction": direction, "slope": slope}


# ---------------------------------------------------------------------------
# QQE MOD
# ---------------------------------------------------------------------------
def _qqe_core(close: List[float], rsi_length: int, smoothing: int, factor: float) -> Dict[str, List[Any]]:
    n = len(close)
    rsi = _pad(Indikator.RSI(close, int(rsi_length)), n)
    smoothed = _ema_none(rsi, int(smoothing))

    wilders = max(1, int(rsi_length) * 2 - 1)
    atr_rsi: List[Optional[float]] = [None] * n
    for i in range(1, n):
        if smoothed[i] is not None and smoothed[i - 1] is not None:
            atr_rsi[i] = abs(smoothed[i - 1] - smoothed[i])
    smoothed_atr = _ema_none(atr_rsi, wilders)
    dynamic_atr = [None if smoothed_atr[i] is None else smoothed_atr[i] * float(factor) for i in range(n)]

    long_band: List[Optional[float]] = [None] * n
    short_band: List[Optional[float]] = [None] * n
    trend_line: List[Optional[float]] = [None] * n
    direction: List[Optional[int]] = [None] * n

    prev_long = 0.0
    prev_short = 0.0
    prev_trend = 0

    def _cross(a, b, a_prev, b_prev) -> bool:
        if None in (a, b, a_prev, b_prev):
            return False
        return (a > b and a_prev <= b_prev) or (a < b and a_prev >= b_prev)

    for i in range(n):
        r = smoothed[i]
        d = dynamic_atr[i]
        if r is None or d is None:
            long_band[i] = prev_long
            short_band[i] = prev_short
            direction[i] = prev_trend
            continue

        r_prev = smoothed[i - 1] if i > 0 else None
        new_short = r + d
        new_long = r - d

        if r_prev is not None and r_prev > prev_long and r > prev_long:
            band_long = max(prev_long, new_long)
        else:
            band_long = new_long

        if r_prev is not None and r_prev < prev_short and r < prev_short:
            band_short = min(prev_short, new_short)
        else:
            band_short = new_short

        long_band[i] = band_long
        short_band[i] = band_short

        if i >= 2:
            # cross(smoothedRsi, shortBand[1])
            if _cross(r, short_band[i - 1], smoothed[i - 1], short_band[i - 2]):
                prev_trend = 1
            # cross(longBand[1], smoothedRsi)
            elif _cross(long_band[i - 1], r, long_band[i - 2], smoothed[i - 1]):
                prev_trend = -1

        trend_line[i] = band_long if prev_trend == 1 else band_short
        direction[i] = prev_trend
        prev_long, prev_short = band_long, band_short

    return {
        "rsi": smoothed,
        "trend": trend_line,
        "direction": direction,
        "long_band": long_band,
        "short_band": short_band,
    }


def _qqe_mod(data, params):
    """QQE MOD: iki QQE + trend çizgisi Bollinger bantlarıyla sinyal üretir."""
    close = _series(data, "close")
    n = len(close)

    primary = _qqe_core(
        close,
        int(params.get("rsi_length", 6)),
        int(params.get("rsi_smoothing", 5)),
        float(params.get("qqe_factor", 3.0)),
    )
    secondary = _qqe_core(
        close,
        int(params.get("secondary_rsi_length", 6)),
        int(params.get("secondary_smoothing", 5)),
        float(params.get("secondary_factor", 1.61)),
    )

    # Bollinger bantları trend çizgisinin 50 merkezine göre hesaplanır.
    centered = [None if primary["trend"][i] is None else primary["trend"][i] - 50.0 for i in range(n)]
    basis, std = _rolling_mean_std(centered, int(params.get("bb_length", 50)))
    mult = float(params.get("bb_mult", 0.35))
    upper = [None if (basis[i] is None or std[i] is None) else basis[i] + mult * std[i] for i in range(n)]
    lower = [None if (basis[i] is None or std[i] is None) else basis[i] - mult * std[i] for i in range(n)]

    threshold = float(params.get("threshold", 3.0))
    primary_centered = [None if primary["rsi"][i] is None else primary["rsi"][i] - 50.0 for i in range(n)]
    secondary_centered = [None if secondary["rsi"][i] is None else secondary["rsi"][i] - 50.0 for i in range(n)]

    signal: List[int] = [0] * n
    histogram: List[Optional[float]] = [None] * n
    hist_state: List[str] = ["none"] * n
    for i in range(n):
        sc, pc, up, low = secondary_centered[i], primary_centered[i], upper[i], lower[i]
        if sc is None:
            continue
        histogram[i] = sc
        if None in (pc, up, low):
            hist_state[i] = "gray" if abs(sc) > threshold else "none"
            continue
        if sc > threshold and pc > up:
            signal[i] = 1
            hist_state[i] = "blue"
        elif sc < -threshold and pc < low:
            signal[i] = -1
            hist_state[i] = "red"
        elif abs(sc) > threshold:
            hist_state[i] = "gray"
        else:
            hist_state[i] = "none"

    return {
        "signal": signal,
        "histogram": histogram,
        "hist_state": hist_state,
        "direction": primary["direction"],
        "trend": primary["trend"],
        "rsi": primary["rsi"],
        "centered": primary_centered,
        "upper": upper,
        "lower": lower,
        "secondary_rsi": secondary["rsi"],
        "secondary_trend": secondary["trend"],
        "secondary_centered": secondary_centered,
    }


def _make_params(*items):
    result = []
    for name, label, default, minimum, maximum, step in items:
        result.append(
            {
                "name": name,
                "label": label,
                "type": "int" if isinstance(default, int) else "float",
                "default": default,
                "min": minimum,
                "max": maximum,
                "step": step,
            }
        )
    return result


INDICATORS: Dict[str, Dict[str, Any]] = {
    "EMA": {
        "label": "EMA",
        "category": "trend",
        "params": _make_params(("length", "Periyot", 20, 1, 500, 1)),
        "outputs": ["value"],
        "fn": _ema,
    },
    "SMA": {
        "label": "SMA",
        "category": "trend",
        "params": _make_params(("length", "Periyot", 20, 1, 500, 1)),
        "outputs": ["value"],
        "fn": _sma,
    },
    "BB": {
        "label": "Bollinger Bantları",
        "category": "volatility",
        "params": _make_params(
            ("length", "Periyot", 20, 2, 200, 1), ("std", "Std Sapma", 2.0, 0.5, 4.0, 0.1)
        ),
        "outputs": ["upper", "middle", "lower", "width", "percent_b"],
        "fn": _bb,
    },
    "RSI": {
        "label": "RSI",
        "category": "momentum",
        "params": _make_params(("length", "Periyot", 14, 2, 200, 1)),
        "outputs": ["value"],
        "fn": _rsi,
    },
    "MACD": {
        "label": "MACD",
        "category": "momentum",
        "params": _make_params(
            ("fast", "Hızlı", 12, 1, 100, 1),
            ("slow", "Yavaş", 26, 2, 200, 1),
            ("signal", "Sinyal", 9, 1, 100, 1),
        ),
        "outputs": ["macd", "signal", "histogram"],
        "fn": _macd,
    },
    "ATR": {
        "label": "ATR",
        "category": "volatility",
        "params": _make_params(("length", "Periyot", 14, 1, 200, 1)),
        "outputs": ["value", "atr_pct"],
        "fn": _atr,
    },
    "ADX": {
        "label": "ADX",
        "category": "trend",
        "params": _make_params(("length", "Periyot", 14, 2, 200, 1)),
        "outputs": ["adx"],
        "fn": _adx,
    },
    "SUPERTREND": {
        "label": "SuperTrend",
        "category": "trend",
        "params": _make_params(
            ("atr_length", "ATR Periyodu", 10, 1, 100, 1),
            ("factor", "Çarpan", 3.0, 0.5, 10.0, 0.1),
        ),
        "outputs": ["value", "direction"],
        "fn": _supertrend,
    },
    "STOCHRSI": {
        "label": "Stochastic RSI",
        "category": "momentum",
        "params": _make_params(
            ("rsi_length", "RSI Periyodu", 14, 2, 100, 1),
            ("stoch_length", "Stoch Periyodu", 14, 2, 100, 1),
            ("smooth_k", "K Yumuşatma", 3, 1, 20, 1),
            ("smooth_d", "D Yumuşatma", 3, 1, 20, 1),
        ),
        "outputs": ["k", "d"],
        "fn": _stochrsi,
    },
    "ICHIMOKU": {
        "label": "Ichimoku",
        "category": "trend",
        "params": [],
        "outputs": ["tenkan", "kijun", "senkou_a", "senkou_b"],
        "fn": _ichimoku,
    },
    "DONCHIAN": {
        "label": "Donchian Kanalı",
        "category": "volatility",
        "params": _make_params(("length", "Periyot", 20, 2, 200, 1)),
        "outputs": ["upper", "lower", "middle"],
        "fn": _donchian,
    },
    "CCI": {
        "label": "CCI",
        "category": "momentum",
        "params": _make_params(
            ("period", "Periyot", 20, 2, 200, 1), ("length", "Yumuşatma", 5, 1, 50, 1)
        ),
        "outputs": ["value"],
        "fn": _cci,
    },
    "MFI": {
        "label": "MFI",
        "category": "volume",
        "params": _make_params(("length", "Periyot", 14, 2, 200, 1)),
        "outputs": ["value"],
        "fn": _mfi,
    },
    "MOMENTUM": {
        "label": "Momentum",
        "category": "momentum",
        "params": _make_params(("length", "Periyot", 10, 1, 200, 1)),
        "outputs": ["value"],
        "fn": _momentum,
    },
    "PSAR": {
        "label": "Parabolic SAR",
        "category": "trend",
        "params": _make_params(
            ("step", "Adım", 0.02, 0.001, 0.2, 0.001),
            ("max", "Maksimum", 0.2, 0.01, 1.0, 0.01),
        ),
        "outputs": ["value"],
        "fn": _psar,
    },
    "VOLUME_SMA": {
        "label": "Hacim SMA",
        "category": "volume",
        "params": _make_params(("length", "Periyot", 20, 1, 200, 1)),
        "outputs": ["value", "ratio"],
        "fn": _volume_sma,
    },
    "BB_RSI": {
        "label": "RSI Bollinger",
        "category": "momentum",
        "params": _make_params(
            ("rsi_length", "RSI Periyodu", 14, 2, 100, 1),
            ("bb_length", "BB Periyodu", 20, 2, 100, 1),
        ),
        "outputs": ["rsi", "lower", "middle", "upper"],
        "fn": _bb_rsi,
    },
    "T3": {
        "label": "Tillson T3",
        "category": "trend",
        "params": _make_params(
            ("length", "T3 Periyodu", 8, 1, 200, 1),
            ("factor", "Hacim Faktörü", 0.7, 0.1, 1.0, 0.01),
        ),
        "outputs": ["value", "direction", "slope"],
        "fn": _t3,
    },
    "QQE_MOD": {
        "label": "QQE MOD",
        "category": "momentum",
        "params": _make_params(
            ("rsi_length", "RSI Periyodu", 6, 2, 100, 1),
            ("rsi_smoothing", "RSI Yumuşatma", 5, 1, 50, 1),
            ("qqe_factor", "QQE Faktörü", 3.0, 0.5, 10.0, 0.01),
            ("threshold", "Eşik", 3.0, 0.5, 50.0, 0.5),
            ("secondary_rsi_length", "2. RSI Periyodu", 6, 2, 100, 1),
            ("secondary_smoothing", "2. RSI Yumuşatma", 5, 1, 50, 1),
            ("secondary_factor", "2. QQE Faktörü", 1.61, 0.5, 10.0, 0.01),
            ("bb_length", "BB Periyodu", 50, 2, 200, 1),
            ("bb_mult", "BB Çarpanı", 0.35, 0.05, 5.0, 0.05),
        ),
        "outputs": [
            "signal", "histogram", "hist_state", "direction", "trend", "rsi", "centered",
            "upper", "lower", "secondary_rsi", "secondary_trend", "secondary_centered",
        ],
        "fn": _qqe_mod,
    },
}


def catalog() -> List[Dict[str, Any]]:
    return [
        {
            "id": key,
            "label": spec["label"],
            "category": spec["category"],
            "params": spec["params"],
            "outputs": spec["outputs"],
        }
        for key, spec in INDICATORS.items()
    ]


class IndicatorCache:
    """Aynı indikatör + parametre kombinasyonunu tek kez hesaplar."""

    def __init__(self, data: Dict[str, List[float]]):
        self.data = data
        self._cache: Dict[str, Dict[str, List[Any]]] = {}
        # Derleyici operand serilerini (fiyat, sabit, offset, math) burada
        # önbelleğe alır. Aksi halde her mum için seri yeniden kurulur (O(n²)).
        self._operand_memo: Dict[Any, List[Any]] = {}
        # Veri uzunluğu sabittir; her operand çözümünde yeniden hesaplanmasın.
        self._n = len(data.get("close") or [])

    def compute(self, name: str, params: Optional[Dict[str, Any]], output: str) -> List[Any]:
        key = f"{name}:{sorted((params or {}).items())}"
        if key not in self._cache:
            spec = INDICATORS.get(name)
            if not spec:
                raise ValueError(f"Bilinmeyen indikatör: {name}")
            self._cache[key] = spec["fn"](self.data, params or {})
        outputs = self._cache[key]
        if output not in outputs:
            raise ValueError(f"{name} için geçersiz çıktı: {output}")
        return outputs[output]


def warmup_of(definition: Dict[str, Any]) -> int:
    """Tanımdaki en uzun parametreyi baz alarak gereken mum sayısını tahmin eder.

    Operand parametreleri eksik bırakılmışsa indikatörün varsayılanları da
    hesaba katılır; aksi halde QQE gibi uzun periyotlu indikatörler yetersiz
    ısınma ile sessizce sinyal üretmez.
    """
    longest = 20
    # Çarpan/eşik türü parametreler mum sayısı gerektirmez.
    NON_LENGTH = {
        "std", "factor", "step", "max", "min",
        "bb_mult", "qqe_factor", "secondary_factor", "threshold",
    }

    def visit(node: Any) -> None:
        nonlocal longest
        if isinstance(node, dict):
            if node.get("type") == "indicator":
                spec = INDICATORS.get(node.get("id") or "")
                defaults = {p["name"]: p["default"] for p in (spec["params"] if spec else [])}
                params = {**defaults, **(node.get("params") or {})}
                for key, value in params.items():
                    if key in NON_LENGTH:
                        continue
                    if isinstance(value, (int, float)):
                        longest = max(longest, int(value))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(definition.get("buy", {}))
    visit(definition.get("sell", {}))
    return max(60, longest * 3)
