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
    buy_i = np.where(valid, buy.astype(int), -1)
    sell_i = np.where(valid, sell.astype(int), -1)
    return {
        "buy": buy_i,
        "sell": sell_i,
        "future_up": up,
        "future_down": down,
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


def build_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    config: Dict[str, Any] | None = None,
) -> Dict[str, np.ndarray]:
    """Panelden gelen parametrelerle etiket seçici."""
    cfg = dict(config or {})
    kind = str(cfg.get("kind") or "forward").lower()
    if kind == "local_extreme":
        return build_local_extreme_labels(
            close,
            high,
            low,
            window=int(cfg.get("extreme_window", 13)),
            tolerance=float(cfg.get("extreme_tolerance", 0.002)),
        )
    return build_forward_labels(
        close,
        high,
        low,
        horizon=int(cfg.get("horizon", 12)),
        target_move=float(cfg.get("target_move", 0.01)),
        stop_move=float(cfg.get("stop_move", 0.01)),
    )
