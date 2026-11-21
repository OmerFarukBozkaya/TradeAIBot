"""Etiket üretimi.

İki tür etiket vardır:

1. ``forward`` (varsayılan ve önerilen): Karar anından sonraki ``horizon``
   mum içinde fiyatın lehte/hilaf hareketine bakar. Alım için "dip civarı"
   = yukarı potansiyel var **ve** aşağı risk sınırlı. Satım simetriktir.
2. ``local_extreme``: ``Local_Min_Max`` indikatörüne daha doğrudan benzeyen,
   onay penceresi kullanılan yerel dip/zirve etiketi. Sadece teşhis/karşılaştırma
   içindir; varsayılan eğitimde kullanılmaz.

Etiketler gelecekteki fiyatları kullanır. Bu **normaldir** (denetimli öğrenmede
hedef budur); yasak olan, bu bilginin özelliklere veya eğitim/test ayrımına
sızmasıdır. ``trainer`` etiket ufku kadar embargo uygular.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

import numpy as np

from app.ai.objective import band_labels


def build_forward_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    horizon: int = 12,
    target_move: float = 0.01,
    stop_move: float = 0.01,
) -> Dict[str, np.ndarray]:
    """Gelecek ``horizon`` mumun en iyi/en kötü hareketinden etiket üretir.

    Döndürür:
    - ``buy`` / ``sell``: 1/0 etiketleri; ufkun yetmediği son satırlar -1.
    - ``future_up`` / ``future_down``: teşhis ve simülasyon için.
    """
    close = np.asarray(close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(close)
    h = int(horizon)
    if h <= 0:
        raise ValueError("horizon pozitif olmalı")

    future_high = np.full(n, np.nan)
    future_low = np.full(n, np.nan)
    for step in range(1, h + 1):
        if step >= n:
            break
        future_high[:-step] = np.fmax(future_high[:-step], high[step:])
        future_low[:-step] = np.fmin(future_low[:-step], low[step:])

    up = np.where(close > 0, future_high / close - 1.0, np.nan)
    down = np.where(close > 0, future_low / close - 1.0, np.nan)

    # Dip civarı: yukarı hedefe ulaşmış ve aşağı stop sınırı aşılmamış.
    buy = (up >= float(target_move)) & (down >= -abs(float(stop_move)))
    # Zirve civarı: aşağı hedefe ulaşmış ve yukarı stop sınırı aşılmamış.
    sell = (down <= -abs(float(target_move))) & (up <= abs(float(stop_move)))

    valid = np.isfinite(up) & np.isfinite(down)
    # Son ``horizon`` mumun geleceği eksiktir; etiketi kesinleşmemiştir.
    valid &= np.arange(n) < (n - h)
    # Ufuk sonundaki getiri: regresyon çıktısı için hedef.
    future_return = np.full(n, np.nan)
    if h < n:
        future_return[:-h] = close[h:] / close[:-h] - 1.0
    buy_i = np.where(valid, buy.astype(int), -1)
    sell_i = np.where(valid, sell.astype(int), -1)
    return {
        "buy": buy_i,
        "sell": sell_i,
        "future_up": up,
        "future_down": down,
        "future_return": np.where(valid, future_return, np.nan),
        "valid": valid,
    }


def build_local_extreme_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    window: int = 13,
    tolerance: float = 0.002,
) -> Dict[str, np.ndarray]:
    """Onay pencereli yerel dip/zirve etiketi (teşhis amaçlı).

    ``i`` noktası, ``i-window .. i+window`` aralığındaki en düşük low ise
    "local_min", en yüksek high ise "local_max" kabul edilir. Bu etiket
    ``window`` mum sonra kesinleşir; eğitimde kullanılırsa embargo şarttır.
    """
    close = np.asarray(close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(close)
    w = int(window)
    buy = np.full(n, -1, dtype=int)
    sell = np.full(n, -1, dtype=int)
    if w <= 0:
        raise ValueError("window pozitif olmalı")
    for i in range(w, n - w):
        lo = float(np.min(low[i - w : i + w + 1]))
        hi = float(np.max(high[i - w : i + w + 1]))
        if low[i] <= lo * (1 + tolerance) and close[i] <= lo * (1 + 2 * tolerance):
            buy[i] = 1
        else:
            buy[i] = 0
        if high[i] >= hi * (1 - tolerance) and close[i] >= hi * (1 - 2 * tolerance):
            sell[i] = 1
        else:
            sell[i] = 0
    return {"buy": buy, "sell": sell}


def _atr_pct_series(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    """ATR'nin fiyata oranı (nedensel, pandas kullanmadan)."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 2:
        return out
    prev_close = close[:-1]
    tr = np.maximum.reduce(
        [high[1:] - low[1:], np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)]
    )
    atr = np.convolve(tr, np.ones(length) / length, mode="valid")
    idx = np.arange(length, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[idx] = atr[: len(idx)] / close[idx]
    return out


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Nedensel üstel hareketli ortalama."""
    alpha = 2.0 / (span + 1.0)
    out = np.full(len(values), np.nan)
    if len(values) == 0:
        return out
    acc = float(values[0])
    for i, v in enumerate(values):
        if not np.isfinite(v):
            out[i] = acc
            continue
        acc = alpha * float(v) + (1 - alpha) * acc
        out[i] = acc
    return out


def build_excess_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    horizon: int = 24,
    *,
    quantile: float = 0.65,
    trend_gate: bool = True,
    dip_gate: bool = True,
    top_gate: bool = True,
    train_frac: float = 0.55,
) -> Dict[str, np.ndarray]:
    """Risk ayarlı gelecek getirisi etiketi (kazanç odaklı).

    ``z = (close[i+h]/close[i] - 1) / ATR%[i]`` → gelecek ``h`` mumun
    oynaklığa göre normalize edilmiş getirisi.

    - **AL**: ``z`` eşiğin üstünde (iyi alım) **ve** trend yukarı **ve**
      fiyat kısa vadeli ortalamanın altında (dip alımı).
    - **SAT**: ``z`` alt eşiğin altında (düşüş beklentisi).

    Eşikler yalnızca serinin **ilk ``train_frac``** bölümünden (eğitim
    döneminden) hesaplanır; test döneminin dağılımı etiketi etkilemez.
    """
    close = np.asarray(close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(close)
    h = max(2, int(horizon))
    valid = np.zeros(n, dtype=bool)
    if h >= n:
        empty = np.full(n, -1, dtype=int)
        return {
            "buy": empty,
            "sell": empty,
            "future_return": np.full(n, np.nan),
            "z": np.full(n, np.nan),
            "trend_up": np.zeros(n, dtype=bool),
            "valid": valid,
        }

    atr_pct = _atr_pct_series(high, low, close)
    fwd = np.full(n, np.nan)
    fwd[:-h] = close[h:] / close[:-h] - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        z = fwd / np.where(atr_pct > 1e-9, atr_pct, np.nan)

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    trend_up = (ema20 > ema50) & (ema50 > ema200)
    dip = close < ema20

    valid = np.isfinite(z) & np.isfinite(ema200)
    valid &= np.arange(n) < (n - h)
    # Eşikler yalnızca eğitim bölgesinden: sızıntı yok.
    limit = int(max(300, n * float(train_frac)))
    sample = z[:limit][valid[:limit]]
    sample = sample[np.isfinite(sample)]
    if len(sample) < 100:
        sample = z[valid]
        sample = sample[np.isfinite(sample)]
    q = float(max(0.5, min(quantile, 0.95)))
    hi = float(np.quantile(sample, q))
    lo = float(np.quantile(sample, 1.0 - q))

    buy = valid & (z >= hi)
    if trend_gate:
        buy &= trend_up
    if dip_gate:
        buy &= dip
    sell = valid & (z <= lo)
    if top_gate:
        # Tepe satışı: fiyat kısa vadeli ortalamanın üstünde (aşırı uzanmış)
        # ve gelecek getiri zayıf.
        sell &= close >= ema20

    return {
        "buy": np.where(valid, buy.astype(int), -1),
        "sell": np.where(valid, sell.astype(int), -1),
        "future_return": np.where(valid, fwd, np.nan),
        "z": z,
        "trend_up": trend_up,
        "thresholds": {"high": round(hi, 4), "low": round(lo, 4), "quantile": q},
        "valid": valid,
    }


def build_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    config: Dict[str, Any] | None = None,
) -> Dict[str, np.ndarray]:
    """Hedef seçici.

    Varsayılan artık ``local_min_max``: model, ``Local_Min_Max``'ın işaretlediği
    dip/zirve bölgelerine yaklaşmayı öğrenir.

    ``forward`` eski yöntemdir (gelecek hareket eşiği); uyumluluk için korunur.
    """
    cfg = dict(config or {})
    kind = str(cfg.get("kind") or "local_min_max").lower()
    window = max(2, int(cfg.get("extreme_window") or 13))
    if kind in {"excess_return", "excess"}:
        return build_excess_labels(
            close,
            high,
            low,
            horizon=int(cfg.get("horizon") or 24),
            quantile=float(cfg.get("excess_quantile") or 0.65),
            trend_gate=bool(cfg.get("trend_gate", True)),
            dip_gate=bool(cfg.get("dip_gate", True)),
            train_frac=float(cfg.get("label_train_frac") or 0.55),
        )
    if kind in {"local_min_max", "local_extreme"}:
        band = float(cfg.get("proximity_band") or cfg.get("extreme_tolerance") or 0.004)
        result = band_labels(close, high, low, window=window, band=band)
        # Etiket `window` mum sonra kesinleşir; gelecek getirisi de bu ufukla
        # hesaplanır ki bölme/embargo tutarlı olsun.
        arr = np.asarray(close, dtype=float)
        n = len(arr)
        fwd = np.full(n, np.nan)
        if window < n:
            fwd[:-window] = arr[window:] / arr[:-window] - 1.0
        result["future_return"] = fwd
        # Son `window` mumun etiketi kesinleşmemiştir.
        valid = np.zeros(n, dtype=bool)
        valid[window : n - window] = True
        result["valid"] = valid & (result["buy"] >= 0) & (result["sell"] >= 0)
        return result
    return build_forward_labels(
        close,
        high,
        low,
        horizon=int(cfg.get("horizon", 12)),
        target_move=float(cfg.get("target_move", 0.01)),
        stop_move=float(cfg.get("stop_move", 0.01)),
    )


def action_targets(labels: Dict[str, np.ndarray]) -> np.ndarray:
    """Sınıflandırma çıktısı: 0 = nötr, 1 = dip/al, 2 = zirve/sat.

    Hem alım hem satım işaretliyse (nadiren) nötr sayılır; çelişkili sinyalle
    işlem açmak istemeyiz.
    """
    buy = np.asarray(labels["buy"], dtype=int)
    sell = np.asarray(labels["sell"], dtype=int)
    action = np.zeros(len(buy), dtype=int)
    action[(buy == 1) & (sell != 1)] = 1
    action[(sell == 1) & (buy != 1)] = 2
    return action
