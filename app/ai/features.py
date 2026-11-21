"""Nedensel (causal) özellik üretimi ve seçilebilir özellik grupları.

Buradaki her özellik ``i`` anındaki kapanmış mum ve öncesinden hesaplanır.
Hiçbir yerde ``shift(-n)``, merkezlenmiş pencere veya gelecekteki satır
kullanılmaz. Etiketler ayrı modüldedir (``labels.py``).

Panelden hangi grupların kullanılacağı seçilebilir. Bir grubu kapatmak
modelin o bilgiyi hiç görmemesi demektir; bu, hangi bilginin gerçekten
işe yaradığını ölçmeyi sağlar (ablation).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

DEFAULT_GROUPS = (
    "returns",
    "range_position",
    "ema",
    "rsi_macd",
    "bollinger",
    "volatility",
    "volume",
    "candle",
    "time",
    "local_extremes",
    "trend",
    "atr_position",
    "regime",
    "htf_trend",
)


def _safe_div(a, b):
    return a / b.replace(0, np.nan)


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = _safe_div(avg_gain, avg_loss)
    return 100 - (100 / (1 + rs))


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def _atr(high, low, close, length=14):
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def _adx(high, low, close, length=14):
    atr = _atr(high, low, close, length)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    plus_di = 100 * _safe_div(plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean(), atr)
    minus_di = 100 * _safe_div(minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean(), atr)
    dx = 100 * _safe_div((plus_di - minus_di).abs(), plus_di + minus_di)
    return dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


class _Ctx:
    def __init__(self, data: Dict[str, Sequence[float]]):
        self.close = pd.Series(np.asarray(data["close"], dtype=float))
        self.high = pd.Series(np.asarray(data["high"], dtype=float))
        self.low = pd.Series(np.asarray(data["low"], dtype=float))
        self.open = pd.Series(np.asarray(data["open"], dtype=float))
        values = data.get("volume_usdt")
        if values is None:
            values = data.get("volume_coin")
        if values is None:
            values = [0.0] * len(self.close)
        self.volume = pd.Series(np.asarray(values, dtype=float))
        self.ts = None
        raw = data.get("opendate")
        if raw is not None and len(raw) == len(self.close):
            self.ts = pd.to_datetime(pd.Series(raw), unit="ms", utc=True, errors="coerce")


def _g_returns(c: _Ctx) -> Dict[str, pd.Series]:
    out = {f"ret_{lag}": c.close.pct_change(lag) for lag in (1, 2, 3, 5, 10, 20, 50)}
    out["log_ret_1"] = np.log(c.close.replace(0, np.nan)).diff()
    out["ret_accel_5"] = c.close.pct_change(5) - c.close.pct_change(5).shift(5)
    return out


def _g_range_position(c: _Ctx) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for w in (10, 20, 50, 100, 200):
        roll_low = c.low.rolling(w, min_periods=max(5, w // 2)).min()
        roll_high = c.high.rolling(w, min_periods=max(5, w // 2)).max()
        width = (roll_high - roll_low).replace(0, np.nan)
        out[f"range_pos_{w}"] = _safe_div(c.close - roll_low, width)
        out[f"dist_low_{w}"] = _safe_div(c.close - roll_low, c.close)
        out[f"dist_high_{w}"] = _safe_div(roll_high - c.close, c.close)
    return out


def _g_ema(c: _Ctx) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for length in (7, 21, 50, 200):
        ema = c.close.ewm(span=length, adjust=False, min_periods=length).mean()
        out[f"ema_dist_{length}"] = _safe_div(c.close - ema, ema)
    ema50 = c.close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema200 = c.close.ewm(span=200, adjust=False, min_periods=200).mean()
    out["ema50_slope_20"] = _safe_div(ema50 - ema50.shift(20), ema50)
    out["ema_cross_50_200"] = _safe_div(ema50 - ema200, c.close)
    return out


def _g_rsi_macd(c: _Ctx) -> Dict[str, pd.Series]:
    out = {
        "rsi_7": _rsi(c.close, 7) / 100.0,
        "rsi_14": _rsi(c.close, 14) / 100.0,
        "rsi_28": _rsi(c.close, 28) / 100.0,
    }
    ema12 = c.close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = c.close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    out["macd_hist"] = _safe_div(macd - signal, c.close)
    out["macd_line"] = _safe_div(macd, c.close)
    return out


def _g_bollinger(c: _Ctx) -> Dict[str, pd.Series]:
    mid = c.close.rolling(20, min_periods=10).mean()
    std = c.close.rolling(20, min_periods=10).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return {
        "bb_percent_b": _safe_div(c.close - lower, (upper - lower).replace(0, np.nan)),
        "bb_width": _safe_div(upper - lower, mid),
        "bb_dist_mid": _safe_div(c.close - mid, mid),
    }


def _g_volatility(c: _Ctx) -> Dict[str, pd.Series]:
    atr = _atr(c.high, c.low, c.close, 14)
    returns = c.close.pct_change()
    return {
        "atr_pct": _safe_div(atr, c.close),
        "adx_14": _adx(c.high, c.low, c.close, 14) / 100.0,
        "volatility_20": returns.rolling(20, min_periods=10).std(),
        "volatility_ratio": _safe_div(
            returns.rolling(5, min_periods=3).std(), returns.rolling(20, min_periods=10).std()
        ),
    }


def _g_volume(c: _Ctx) -> Dict[str, pd.Series]:
    log_vol = np.log1p(c.volume.clip(lower=0))
    vol_mean = log_vol.rolling(20, min_periods=10).mean()
    vol_std = log_vol.rolling(20, min_periods=10).std()
    return {
        "volume_z_20": _safe_div(log_vol - vol_mean, vol_std),
        "volume_change_5": c.volume.pct_change(5).replace([np.inf, -np.inf], np.nan),
        "volume_ratio_20": _safe_div(c.volume, c.volume.rolling(20, min_periods=10).mean()),
    }


def _g_candle(c: _Ctx) -> Dict[str, pd.Series]:
    rng = (c.high - c.low).replace(0, np.nan)
    return {
        "body_ratio": _safe_div(c.close - c.open, rng),
        "upper_wick_ratio": _safe_div(c.high - pd.concat([c.open, c.close], axis=1).max(axis=1), rng),
        "lower_wick_ratio": _safe_div(pd.concat([c.open, c.close], axis=1).min(axis=1) - c.low, rng),
        "close_position": _safe_div(c.close - c.low, rng),
    }


def _g_time(c: _Ctx) -> Dict[str, pd.Series]:
    if c.ts is None:
        return {}
    hour = c.ts.dt.hour.astype(float)
    dow = c.ts.dt.dayofweek.astype(float)
    return {
        "hour_sin": np.sin(2 * np.pi * hour / 24.0),
        "hour_cos": np.cos(2 * np.pi * hour / 24.0),
        "dow_sin": np.sin(2 * np.pi * dow / 7.0),
        "dow_cos": np.cos(2 * np.pi * dow / 7.0),
    }


def _g_donchian(c: _Ctx) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for w in (10, 20, 55):
        upper = c.high.rolling(w, min_periods=max(5, w // 2)).max()
        lower = c.low.rolling(w, min_periods=max(5, w // 2)).min()
        out[f"donchian_pos_{w}"] = _safe_div(c.close - lower, (upper - lower).replace(0, np.nan))
        out[f"donchian_break_{w}"] = _safe_div(c.close - upper, upper)
    return out


def _g_stochastic(c: _Ctx) -> Dict[str, pd.Series]:
    low14 = c.low.rolling(14, min_periods=7).min()
    high14 = c.high.rolling(14, min_periods=7).max()
    k = 100 * _safe_div(c.close - low14, (high14 - low14).replace(0, np.nan))
    d = k.rolling(3, min_periods=2).mean()
    return {"stoch_k": k / 100.0, "stoch_d": d / 100.0, "stoch_diff": (k - d) / 100.0}


def _g_local_extremes(c: _Ctx) -> Dict[str, pd.Series]:
    """Yerel dip/zirveye uzaklık (Local_Min_Max mantığının nedensel hali)."""
    out: Dict[str, pd.Series] = {}
    for w in (5, 13, 21):
        prev_low = c.low.rolling(w, min_periods=2).min().shift(1)
        prev_high = c.high.rolling(w, min_periods=2).max().shift(1)
        out[f"local_low_dist_{w}"] = _safe_div(c.close - prev_low, c.close)
        out[f"local_high_dist_{w}"] = _safe_div(prev_high - c.close, c.close)
        out[f"local_span_{w}"] = _safe_div(c.close - prev_low, (prev_high - prev_low).replace(0, np.nan))
    return out


def _g_trend(c: _Ctx) -> Dict[str, pd.Series]:
    """Trend yönü ve gücü: EMA yığını, eğim, ATR'ye göre normalleştirilmiş mesafe."""
    atr = _atr(c.high, c.low, c.close, 14).replace(0, np.nan)
    ema20 = c.close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema50 = c.close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema200 = c.close.ewm(span=200, adjust=False, min_periods=200).mean()
    return {
        # EMA'lar arası mesafe ATR cinsinden: trendin gücü, fiyat ölçeğinden bağımsız.
        "ema20_50_atr": _safe_div(ema20 - ema50, atr),
        "ema50_200_atr": _safe_div(ema50 - ema200, atr),
        "close_ema20_atr": _safe_div(c.close - ema20, atr),
        "close_ema200_atr": _safe_div(c.close - ema200, atr),
        "ema50_slope_10": _safe_div(ema50 - ema50.shift(10), atr),
        "ema200_slope_20": _safe_div(ema200 - ema200.shift(20), atr),
        # Yığın durumu: tam yükseliş +1, tam düşüş -1.
        "ema_stack": (
            np.sign(ema20 - ema50) + np.sign(ema50 - ema200) + np.sign(c.close - ema200)
        ) / 3.0,
    }


def _g_atr_position(c: _Ctx) -> Dict[str, pd.Series]:
    """Fiyatın son salınım dibine/zirvesine ATR cinsinden uzaklığı.

    "Dibe yakın al, tepeye yakın sat" için doğrudan ölçüt: 0'a yakın değer
    dibe çok yakın, büyük değer zirveye çok yakın demektir.
    """
    atr = _atr(c.high, c.low, c.close, 14).replace(0, np.nan)
    out: Dict[str, pd.Series] = {}
    for w in (20, 55, 100):
        lo = c.low.rolling(w, min_periods=max(5, w // 2)).min()
        hi = c.high.rolling(w, min_periods=max(5, w // 2)).max()
        out[f"dist_swing_low_atr_{w}"] = _safe_div(c.close - lo, atr)
        out[f"dist_swing_high_atr_{w}"] = _safe_div(hi - c.close, atr)
        # ATR cinsinden aralık genişliği: rejim bilgisi taşır.
        out[f"range_atr_{w}"] = _safe_div(hi - lo, atr)
    return out


def _g_regime(c: _Ctx) -> Dict[str, pd.Series]:
    """Oynaklık rejimi ve trend verimliliği."""
    atr = _atr(c.high, c.low, c.close, 14)
    atr_pct = _safe_div(atr, c.close)
    atr_mean = atr_pct.rolling(100, min_periods=30).mean()
    atr_std = atr_pct.rolling(100, min_periods=30).std()
    move = c.close.diff().abs()
    path = move.rolling(20, min_periods=10).sum()
    net = (c.close - c.close.shift(20)).abs()
    return {
        "atr_z_100": _safe_div(atr_pct - atr_mean, atr_std),
        "atr_ratio_50": _safe_div(atr, atr.rolling(50, min_periods=20).mean()),
        # Kaufman verimlilik oranı: 1 = düzgün trend, 0 = testere.
        "efficiency_20": _safe_div(net, path),
        "efficiency_50": _safe_div((c.close - c.close.shift(50)).abs(), move.rolling(50, min_periods=20).sum()),
    }


def _g_htf_trend(c: _Ctx) -> Dict[str, pd.Series]:
    """Üst zaman dilimi bağlamı: son 4/12/48 mumun risk ayarlı getirisi."""
    atr = _atr(c.high, c.low, c.close, 14).replace(0, np.nan)
    out: Dict[str, pd.Series] = {}
    for k in (4, 12, 48):
        delta = c.close - c.close.shift(k)
        out[f"htf_move_{k}_atr"] = _safe_div(delta, atr * np.sqrt(k))
        out[f"htf_mean_slope_{k}"] = _safe_div(
            c.close.rolling(k, min_periods=max(2, k // 2)).mean()
            - c.close.rolling(k, min_periods=max(2, k // 2)).mean().shift(k),
            atr,
        )
    return out



GROUPS: Dict[str, Dict[str, Any]] = {
    "returns": {
        "label": "Getiri ve momentum",
        "desc": "1..50 mumluk getiriler, log getiri, ivme",
        "warmup": 60,
        "build": _g_returns,
    },
    "range_position": {
        "label": "Aralık konumu",
        "desc": "Fiyatın son 10..200 mumun dibine/zirvesine uzaklığı",
        "warmup": 210,
        "build": _g_range_position,
    },
    "ema": {
        "label": "Hareketli ortalamalar",
        "desc": "EMA 7/21/50/200 uzaklığı, eğim ve kesişim",
        "warmup": 220,
        "build": _g_ema,
    },
    "rsi_macd": {
        "label": "RSI / MACD",
        "desc": "Aşırı alım-satım ve momentum",
        "warmup": 40,
        "build": _g_rsi_macd,
    },
    "bollinger": {
        "label": "Bollinger",
        "desc": "Bant içi konum, bant genişliği, orta banda uzaklık",
        "warmup": 30,
        "build": _g_bollinger,
    },
    "volatility": {
        "label": "Volatilite / trend gücü",
        "desc": "ATR%, ADX, oynaklık oranı",
        "warmup": 40,
        "build": _g_volatility,
    },
    "volume": {
        "label": "Hacim",
        "desc": "Log hacim z-skoru, hacim değişimi, hacim oranı",
        "warmup": 30,
        "build": _g_volume,
    },
    "candle": {
        "label": "Mum yapısı",
        "desc": "Gövde/fitil oranları, kapanışın aralık içindeki yeri",
        "warmup": 5,
        "build": _g_candle,
    },
    "time": {
        "label": "Saat / gün",
        "desc": "Döngüsel saat ve haftanın günü",
        "warmup": 5,
        "build": _g_time,
    },
    "donchian": {
        "label": "Donchian kanalı",
        "desc": "Kanal içi konum ve üst bant kırılımı",
        "warmup": 60,
        "build": _g_donchian,
    },
    "stochastic": {
        "label": "Stokastik",
        "desc": "Stochastic %K, %D ve farkı",
        "warmup": 20,
        "build": _g_stochastic,
    },
    "local_extremes": {
        "label": "Yerel dip/zirve (nedensel)",
        "desc": "Son 5/13/21 mumun dip ve zirvesine uzaklık — Local_Min_Max'ın geleceğe bakmayan hali",
        "warmup": 25,
        "build": _g_local_extremes,
    },
    "trend": {
        "label": "Trend yönü ve gücü",
        "desc": "EMA yığını, eğimler ve fiyatın EMA'lara ATR cinsinden uzaklığı",
        "warmup": 230,
        "build": _g_trend,
    },
    "atr_position": {
        "label": "Dibe/tepeye ATR uzaklığı",
        "desc": "Fiyatın son salınım dibine ve zirvesine ATR cinsinden uzaklığı",
        "warmup": 120,
        "build": _g_atr_position,
    },
    "regime": {
        "label": "Piyasa rejimi",
        "desc": "Oynaklık z-skoru, ATR oranı, trend verimliliği (testere mi trend mi)",
        "warmup": 120,
        "build": _g_regime,
    },
    "htf_trend": {
        "label": "Üst zaman dilimi",
        "desc": "Son 4/12/48 mumun risk ayarlı getirisi ve ortalama eğimi",
        "warmup": 120,
        "build": _g_htf_trend,
    },
}

_GROUP_COLUMNS: Dict[str, List[str]] = {}


def _columns_for(group_id: str) -> List[str]:
    if group_id in _GROUP_COLUMNS:
        return _GROUP_COLUMNS[group_id]
    n = 260
    rng = np.random.default_rng(7)
    base = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    dummy = {
        "open": base * (1 + rng.normal(0, 0.0005, n)),
        "high": base * (1 + np.abs(rng.normal(0, 0.003, n))),
        "low": base * (1 - np.abs(rng.normal(0, 0.003, n))),
        "close": base,
        "volume_usdt": rng.lognormal(10, 1, n),
        "opendate": (np.arange(n) * 3_600_000).astype(float),
    }
    ctx = _Ctx(dummy)
    try:
        cols = list(GROUPS[group_id]["build"](ctx).keys())
    except Exception:
        cols = []
    _GROUP_COLUMNS[group_id] = cols
    return cols


def group_catalog() -> List[Dict[str, Any]]:
    """Panelde gösterilecek gruplar: kimlik, ad, açıklama, kolon sayısı."""
    items: List[Dict[str, Any]] = []
    for key, meta in GROUPS.items():
        cols = _columns_for(key)
        items.append(
            {
                "id": key,
                "label": meta["label"],
                "desc": meta["desc"],
                "warmup": meta["warmup"],
                "columns": cols,
                "column_count": len(cols),
                "default": key in DEFAULT_GROUPS,
            }
        )
    return items


def normalize_groups(groups: Optional[Sequence[str]]) -> List[str]:
    if not groups:
        return list(DEFAULT_GROUPS)
    chosen: List[str] = []
    for name in groups:
        key = str(name)
        if key in GROUPS and key not in chosen:
            chosen.append(key)
    return chosen or list(DEFAULT_GROUPS)


def warmup_for(groups: Optional[Sequence[str]]) -> int:
    chosen = normalize_groups(groups)
    return max(int(GROUPS[g]["warmup"]) for g in chosen)


def build_feature_frame(
    data: Dict[str, Sequence[float]],
    groups: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """OHLCV sözlüğünden nedensel özellik tablosu üretir.

    ``groups`` verilmezse varsayılan set kullanılır. Seçilmeyen gruplar
    hiç hesaplanmaz; böylece model o bilgiyi görmez.
    """
    ctx = _Ctx(data)
    chosen = normalize_groups(groups)
    frames: Dict[str, pd.Series] = {}
    for key in chosen:
        for name, series in GROUPS[key]["build"](ctx).items():
            frames[name] = series
    frame = pd.DataFrame(frames)
    frame = frame.replace([np.inf, -np.inf], np.nan)
    # Tamamen boş kolonlar modele bilgi taşımaz.
    keep = [col for col in frame.columns if frame[col].notna().any()]
    return frame[keep]


def build_features(
    data: Dict[str, Sequence[float]],
    groups: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Eğitim ve canlı çıkarım için ortak özellik sözlüğü döndürür."""
    frame = build_feature_frame(data, groups)
    close = np.asarray(data["close"], dtype=float)
    return {
        "frame": frame,
        "X": frame.to_numpy(dtype=float),
        "feature_names": list(frame.columns),
        "groups": normalize_groups(groups),
        "close": close,
        "high": np.asarray(data["high"], dtype=float),
        "low": np.asarray(data["low"], dtype=float),
        "opendate": list(data["opendate"]) if data.get("opendate") is not None else [],
        "warmup": warmup_for(groups),
    }


def feature_catalog() -> List[Dict[str, str]]:
    """Geriye uyumlu kısa liste (grup adı + açıklama)."""
    return [{"name": meta["label"], "desc": meta["desc"]} for meta in GROUPS.values()]
