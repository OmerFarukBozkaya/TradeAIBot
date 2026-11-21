"""Local_Min_Max hedefi: etiket, referans işaretler ve uyum ölçümü.

`Local_Min_Max` stratejisi geleceğe baktığı için canlıda kullanılamaz. Burada
yaptığımız şey onu **taklit etmek değil, yaklaşmak**:

- ``pivot_marks``: Local_Min_Max'ın işaretlediği gerçek dip/zirve noktaları.
  Bunlar ``window`` mum sonra kesinleşir (etiket olarak kullanılabilir).
- ``band_labels``: modelin öğreneceği hedef. Fiyat yerel dibe/zirveye
  ``band`` kadar yaklaştığında 1 olur. Böylece sınıf dengesi makul kalır;
  model "dibe yaklaşıyorum" sinyalini öğrenir.
- ``agreement``: modelin AL/SAT sinyalleri ile gerçek pivotlar arasındaki
  uyum (precision / recall / F1). ±`tolerance` mum kayma kabul edilir.

Bu modül yalnızca **eğitim ve değerlendirme** içindir; canlı çıkarımda
kullanılmaz.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import numpy as np


def pivot_marks(
    high: Sequence[float],
    low: Sequence[float],
    window: int = 13,
) -> Dict[str, np.ndarray]:
    """Local_Min_Max'ın referans dip/zirve maskeleri.

    ``i`` noktası, ``i-window .. i+window`` aralığında en düşük low ise dip,
    en yüksek high ise zirve sayılır. Bu bilgi ancak ``window`` mum sonra
    kesinleşir; eğitimde embargo ile korunur.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(low)
    w = max(1, int(window))
    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)
    if n < 2 * w + 1:
        return {"buy": buy, "sell": sell}
    for i in range(w, n - w):
        seg_low = low[i - w : i + w + 1]
        seg_high = high[i - w : i + w + 1]
        if low[i] <= float(seg_low.min()):
            buy[i] = True
        if high[i] >= float(seg_high.max()):
            sell[i] = True
    return {"buy": buy, "sell": sell}


def band_labels(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    window: int = 13,
    band: float = 0.004,
) -> Dict[str, np.ndarray]:
    """Öğrenilebilir hedef: yerel dibe/zirveye yakınlık.

    ``band`` = fiyatın yerel dibin en fazla %kaç üstünde olduğu. Örneğin
    0.004 → yerel dibin %0,4 üstündeki tüm mumlar "dip bölgesi" sayılır.
    Sadece tek mumu pozitif yapmak sınıfı aşırı dengesizleştirirdi.
    """
    close = np.asarray(close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(low)
    w = max(1, int(window))
    b = max(0.0, float(band))
    buy = np.full(n, -1, dtype=int)
    sell = np.full(n, -1, dtype=int)
    if n < 2 * w + 1:
        return {"buy": buy, "sell": sell}
    for i in range(w, n - w):
        local_low = float(low[i - w : i + w + 1].min())
        local_high = float(high[i - w : i + w + 1].max())
        # Dip bölgesi: düşük fiyat, yerel dibin band kadar üstünde.
        buy[i] = 1 if low[i] <= local_low * (1 + b) else 0
        # Zirve bölgesi: yüksek fiyat, yerel zirvenin band kadar altında.
        sell[i] = 1 if high[i] >= local_high * (1 - b) else 0
    return {"buy": buy, "sell": sell}


def _match_mask(pred_idx: np.ndarray, oracle_idx: np.ndarray, tolerance: int) -> Dict[str, Any]:
    """İki işaret kümesini ±tolerance mum toleransla eşleştirir."""
    pred_idx = np.sort(np.asarray(pred_idx, dtype=int))
    oracle_idx = np.sort(np.asarray(oracle_idx, dtype=int))
    if len(pred_idx) == 0 or len(oracle_idx) == 0:
        return {
            "precision": 0.0 if len(pred_idx) else None,
            "recall": 0.0 if len(oracle_idx) else None,
            "f1": 0.0,
            "tp": 0,
            "predicted": int(len(pred_idx)),
            "oracle": int(len(oracle_idx)),
        }
    tol = max(0, int(tolerance))
    matched_oracle = set()
    tp = 0
    for p in pred_idx:
        left = int(np.searchsorted(oracle_idx, p - tol, side="left"))
        right = int(np.searchsorted(oracle_idx, p + tol, side="right"))
        hit = None
        for k in range(left, right):
            o = int(oracle_idx[k])
            if o not in matched_oracle:
                hit = o
                break
        if hit is None and right > left:
            # Hepsi eşleşmişse en yakını tekrar sayılmasın.
            hit = None
        if hit is not None:
            matched_oracle.add(hit)
            tp += 1
    precision = tp / len(pred_idx) if len(pred_idx) else 0.0
    recall = tp / len(oracle_idx) if len(oracle_idx) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "predicted": int(len(pred_idx)),
        "oracle": int(len(oracle_idx)),
    }


def agreement(
    buy_prob: np.ndarray,
    sell_prob: np.ndarray,
    abs_indices: np.ndarray,
    high: Sequence[float],
    low: Sequence[float],
    *,
    buy_threshold: float,
    sell_threshold: float,
    window: int,
    tolerance: int = 2,
) -> Dict[str, Any]:
    """Model sinyalleri ile Local_Min_Max pivotları arasındaki uyum."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    abs_indices = np.asarray(abs_indices, dtype=int)
    marks = pivot_marks(high, low, window)
    buy_prob = np.asarray(buy_prob, dtype=float)
    sell_prob = np.asarray(sell_prob, dtype=float)
    if len(abs_indices) == 0:
        return {"buy": _match_mask([], [], tolerance), "sell": _match_mask([], [], tolerance)}

    pred_buy = abs_indices[buy_prob >= float(buy_threshold)]
    pred_sell = abs_indices[sell_prob >= float(sell_threshold)]
    oracle_buy = np.where(marks["buy"])[0]
    oracle_sell = np.where(marks["sell"])[0]
    # Yalnızca değerlendirilen zaman aralığındaki pivotları say.
    lo_i, hi_i = int(abs_indices.min()), int(abs_indices.max())
    oracle_buy = oracle_buy[(oracle_buy >= lo_i) & (oracle_buy <= hi_i)]
    oracle_sell = oracle_sell[(oracle_sell >= lo_i) & (oracle_sell <= hi_i)]

    buy = _match_mask(pred_buy, oracle_buy, tolerance)
    sell = _match_mask(pred_sell, oracle_sell, tolerance)
    f1s = [v for v in (buy["f1"], sell["f1"]) if v is not None]
    return {
        "buy": buy,
        "sell": sell,
        "f1": round(float(np.mean(f1s)) if f1s else 0.0, 4),
        "window": int(window),
        "tolerance": int(tolerance),
    }


def choose_agreement_threshold(
    prob: np.ndarray,
    abs_indices: np.ndarray,
    oracle_mask: np.ndarray,
    *,
    tolerance: int = 2,
    min_precision: float = 0.25,
    grid: int = 24,
) -> Dict[str, Any]:
    """Eşiği doğrudan Local_Min_Max uyumuna göre seçer.

    Amaç: modele "her muma sinyal ver" dedirtmemek. ``min_precision``
    sağlanamıyorsa en iyi F1'e düşer, ama en azından uyarı raporlanır.
    """
    prob = np.asarray(prob, dtype=float)
    abs_indices = np.asarray(abs_indices, dtype=int)
    oracle_idx = np.where(np.asarray(oracle_mask, dtype=bool))[0]
    if len(prob) == 0:
        return {"threshold": 0.6, "f1": 0.0, "precision": 0.0, "recall": 0.0, "constrained": False}
    oracle_idx = oracle_idx[
        (oracle_idx >= int(abs_indices.min())) & (oracle_idx <= int(abs_indices.max()))
    ]
    if len(oracle_idx) == 0:
        return {"threshold": 0.9, "f1": 0.0, "precision": None, "recall": 0.0, "constrained": False}

    quantiles = np.linspace(0.50, 0.98, max(6, int(grid)))
    candidates = sorted({round(float(np.quantile(prob, q)), 4) for q in quantiles})
    best_any = None
    best_ok = None
    for thr in candidates:
        pred = abs_indices[prob >= thr]
        m = _match_mask(pred, oracle_idx, tolerance)
        m["threshold"] = thr
        if best_any is None or (m["f1"] or 0) > (best_any["f1"] or 0):
            best_any = m
        if (m["precision"] or 0) >= float(min_precision):
            if best_ok is None or (m["f1"] or 0) > (best_ok["f1"] or 0):
                best_ok = m
    chosen = best_ok or best_any
    return {
        "threshold": float(chosen["threshold"]),
        "f1": float(chosen.get("f1") or 0.0),
        "precision": chosen.get("precision"),
        "recall": chosen.get("recall"),
        "predicted": chosen.get("predicted"),
        "oracle": chosen.get("oracle"),
        "constrained": bool(best_ok is not None),
    }


def trading_score(metrics: Dict[str, Any], min_trades: int = 6, bars: int = 0) -> float:
    """Tek bir dönemin işlem kalitesini puanlar (kâr odaklı).

    Ana ölçüt **al-tut farkı** (edge): strateji gerçekten endeksin önüne
    geçiyor mu? Ardından getiri, kâr faktörü ve düşüş cezası gelir.
    """
    metrics = metrics or {}
    trades = int(metrics.get("trade_count") or 0)
    edge = float(metrics.get("edge_pct") or 0.0)
    ret = float(metrics.get("total_return_pct") or 0.0)
    pf = metrics.get("profit_factor")
    pf = 1.0 if pf is None else float(pf)
    dd = float(metrics.get("max_drawdown_pct") or 0.0)
    win = float(metrics.get("win_rate") or 0.0)

    score = max(-40.0, min(edge, 80.0)) * 1.0
    score += max(-40.0, min(ret, 80.0)) * 0.6
    score += max(-1.0, min(pf - 1.0, 3.0)) * 6.0
    score -= max(0.0, (-dd) - 20.0) * 0.3
    score += max(-10.0, min(win - 50.0, 25.0)) * 0.15
    if trades == 0:
        score -= 25.0
    elif trades < min_trades:
        score -= (min_trades - trades) * 1.5
    # İşlem yoğunluğu cezası: 1000 mumda 6'dan fazla işlem maliyetle erir.
    if bars and bars > 0:
        rate = trades / float(bars) * 1000.0
        score -= max(0.0, rate - 6.0) * 1.2
    return round(score, 4)


def robust_trading_score(
    metrics_list: Sequence[Dict[str, Any]],
    min_trades: int = 6,
    bars_list: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Birkaç ayrı dönemin ortalamasını ve tutarlılığını birleştirir.

    Tek bir şanslı dönem yüksek puan alamasın: ortalama + pozitif dönem oranı.
    """
    valid = [m for m in metrics_list if m]
    if not valid:
        return {"score": -50.0, "windows": 0, "positive_windows": 0}
    bars_seq = list(bars_list or [])
    scores = [
        trading_score(m, min_trades, bars_seq[i] if i < len(bars_seq) else 0)
        for i, m in enumerate(valid)
    ]
    edges = [float(m.get("edge_pct") or 0.0) for m in valid]
    rets = [float(m.get("total_return_pct") or 0.0) for m in valid]
    trades = [int(m.get("trade_count") or 0) for m in valid]
    positive = sum(1 for e in edges if e > 0)
    mean_score = float(np.mean(scores))
    consistency = (positive / len(valid) - 0.5) * 12.0
    return {
        "score": round(mean_score + consistency, 4),
        "windows": len(valid),
        "positive_windows": positive,
        "avg_score": round(mean_score, 4),
        "avg_edge_pct": round(float(np.mean(edges)), 2),
        "avg_return_pct": round(float(np.mean(rets)), 2),
        "avg_trades": round(float(np.mean(trades)), 1),
        "scores": [round(s, 2) for s in scores],
    }


def objective_score(
    agreement_result: Dict[str, Any],
    trading: Dict[str, Any],
    min_trades: int = 8,
) -> float:
    """Tek sayıya indirgenmiş hedef.

    Local_Min_Max uyumu (F1) **belirgin biçimde baskındır**: 1 puan F1 artışı
    ≈ 1 puan skor. Al-tut farkı ve getiri yalnızca eşitliği bozan ikincil
    ölçütlerdir; tek bir validation dilimindeki gürültü skoru ele geçirmesin.
    Yine de al-tut'u açık ara kaybeden model cezalandırılır.
    """
    f1 = float(agreement_result.get("f1") or 0.0)
    trades = int(trading.get("trade_count") or 0)
    edge = float(trading.get("edge_pct") or 0.0)
    ret = float(trading.get("total_return_pct") or 0.0)
    score = f1 * 100.0
    score += max(-15.0, min(edge, 30.0)) * 0.2
    score += max(-10.0, min(ret, 30.0)) * 0.1
    # Al-tut'u açık ara kaybeden model terfi etmesin (kırılganlık koruması).
    if edge < -15.0:
        score -= min(8.0, (-15.0 - edge) * 0.25)
    if trades < min_trades:
        score -= (min_trades - trades) * 1.5
    return round(score, 4)
