"""Nedensel (causal) özellik üretimi.

Buradaki her özellik ``i`` anındaki kapanmış mum ve öncesinden hesaplanır.
Hiçbir yerde ``shift(-n)``, merkezlenmiş pencere veya gelecekteki satır
kullanılmaz. Etiketler ayrı modüldedir (``labels.py``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd

# Özellik penceresi: en uzun geriye bakış. Canlı strateji bu kadar mum
# birikmeden sinyal üretmez.
WARMUP = 210

RETURN_LAGS = (1, 2, 3, 5, 10, 20, 50)
RANGE_WINDOWS = (10, 20, 50, 100, 200)
EMA_LENGTHS = (7, 21, 50, 200)


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = _safe_div(avg_gain, avg_loss)
    return 100 - (100 / (1 + rs))


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    atr = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    plus_di = 100 * _safe_div(plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean(), atr)
    minus_di = 100 * _safe_div(minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean(), atr)
    dx = 100 * _safe_div((plus_di - minus_di).abs(), plus_di + minus_di)
    return dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def build_feature_frame(data: Dict[str, Sequence[float]]) -> pd.DataFrame:
    """OHLCV sözlüğünden nedensel özellik tablosu üretir."""
    close = pd.Series(np.asarray(data["close"], dtype=float))
    high = pd.Series(np.asarray(data["high"], dtype=float))
    low = pd.Series(np.asarray(data["low"], dtype=float))
    open_ = pd.Series(np.asarray(data["open"], dtype=float))
    volume_values = data.get("volume_usdt")
    if volume_values is None:
        volume_values = data.get("volume_coin")
    if volume_values is None:
        volume_values = [0.0] * len(close)
    volume = pd.Series(np.asarray(volume_values, dtype=float))

    f: Dict[str, pd.Series] = {}

    # Getiri ve momentum
    for lag in RETURN_LAGS:
        f[f"ret_{lag}"] = close.pct_change(lag)

    # Fiyatın son N mumun aralığındaki konumu (0 = dip, 1 = zirve)
    for w in RANGE_WINDOWS:
        roll_low = low.rolling(w, min_periods=max(5, w // 2)).min()
        roll_high = high.rolling(w, min_periods=max(5, w // 2)).max()
        width = (roll_high - roll_low).replace(0, np.nan)
        f[f"range_pos_{w}"] = _safe_div(close - roll_low, width)
        f[f"dist_low_{w}"] = _safe_div(close - roll_low, close)
        f[f"dist_high_{w}"] = _safe_div(roll_high - close, close)

    # Hareketli ortalamalara uzaklık
    for length in EMA_LENGTHS:
        ema = close.ewm(span=length, adjust=False, min_periods=length).mean()
        f[f"ema_dist_{length}"] = _safe_div(close - ema, ema)

    # RSI / MACD
    f["rsi_14"] = _rsi(close, 14) / 100.0
    f["rsi_28"] = _rsi(close, 28) / 100.0
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    f["macd_hist"] = _safe_div(macd - macd_signal, close)

    # Bollinger konumu ve genişliği
    mid = close.rolling(20, min_periods=10).mean()
    std = close.rolling(20, min_periods=10).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    f["bb_percent_b"] = _safe_div(close - lower, (upper - lower).replace(0, np.nan))
    f["bb_width"] = _safe_div(upper - lower, mid)

    # Volatilite / trend gücü
    atr = _atr(high, low, close, 14)
    f["atr_pct"] = _safe_div(atr, close)
    f["adx_14"] = _adx(high, low, close, 14) / 100.0

    # Hacim (log + z-score). Sıfır hacimde NaN bırakılır, model tolere eder.
    log_vol = np.log1p(volume.clip(lower=0))
    vol_mean = log_vol.rolling(20, min_periods=10).mean()
    vol_std = log_vol.rolling(20, min_periods=10).std()
    f["volume_z_20"] = _safe_div(log_vol - vol_mean, vol_std)
    f["volume_change_5"] = volume.pct_change(5).replace([np.inf, -np.inf], np.nan)

    # Mum yapısı
    candle_range = (high - low).replace(0, np.nan)
    f["body_ratio"] = _safe_div(close - open_, candle_range)
    f["upper_wick_ratio"] = _safe_div(high - pd.concat([open_, close], axis=1).max(axis=1), candle_range)
    f["lower_wick_ratio"] = _safe_div(pd.concat([open_, close], axis=1).min(axis=1) - low, candle_range)

    # Zaman (döngüsel). Kripto 7/24 olsa da saatlik likidite değişimi vardır.
    ts_values = data.get("opendate")
    if ts_values is not None and len(ts_values) == len(close):
        ts = pd.to_datetime(pd.Series(ts_values), unit="ms", utc=True, errors="coerce")
        hour = ts.dt.hour.astype(float)
        dow = ts.dt.dayofweek.astype(float)
        f["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        f["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        f["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
        f["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)

    frame = pd.DataFrame(f)
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame


def build_features(data: Dict[str, Sequence[float]]) -> Dict[str, Any]:
    """Eğitim ve canlı çıkarım için ortak özellik sözlüğü döndürür."""
    frame = build_feature_frame(data)
    close = np.asarray(data["close"], dtype=float)
    return {
        "frame": frame,
        "X": frame.to_numpy(dtype=float),
        "feature_names": list(frame.columns),
        "close": close,
        "high": np.asarray(data["high"], dtype=float),
        "low": np.asarray(data["low"], dtype=float),
        "opendate": list(data["opendate"]) if data.get("opendate") is not None else [],
        "warmup": WARMUP,
    }


def feature_catalog() -> List[Dict[str, str]]:
    """Panelde gösterilecek kısa özellik listesi."""
    return [
        {"name": "Getiri (1..50 mum)", "desc": "Geçmiş getiri ve momentum"},
        {"name": "Aralık konumu (10..200)", "desc": "Fiyat son N mumun dibine/zirvesine ne kadar yakın"},
        {"name": "EMA uzaklığı", "desc": "7/21/50/200 EMA'lara göre konum"},
        {"name": "RSI / MACD", "desc": "Aşırı alım-satım ve momentum"},
        {"name": "Bollinger", "desc": "Bant içi konum ve bant genişliği"},
        {"name": "ATR / ADX", "desc": "Volatilite ve trend gücü"},
        {"name": "Hacim", "desc": "Log hacim z-skoru ve değişim"},
        {"name": "Mum yapısı", "desc": "Gövde ve fitil oranları"},
        {"name": "Saat / gün", "desc": "Döngüsel zaman özellikleri"},
    ]
