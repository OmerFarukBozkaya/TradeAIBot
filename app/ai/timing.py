"""İşlem zamanlaması hatası analizi.

Kapanan sanal işlemleri "erken / geç / zamanında" olarak sınıflandırır.
Amaç, modelin bir sonraki turda hangi örneklere daha çok ağırlık vereceğini
belirlemektir.

Bu modül **yalnızca eğitim kümesindeki** işlemler için kullanılır. Etiketler
zaten gelecekteki fiyatı içerdiği için burada geleceğe bakmak yeni bir sızıntı
değildir; test kümesi bu analize hiç girmez.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def _window_bounds(i: int, window: int, n: int) -> tuple[int, int]:
    return max(0, i - window), min(n, i + window + 1)


def classify_trade(
    trade: Dict[str, Any],
    high: Sequence[float],
    low: Sequence[float],
    window: int,
    tolerance: float,
) -> Dict[str, Any]:
    """Bir işlemin giriş ve çıkış zamanlamasını değerlendirir.

    Giriş için:
    - ``erken``: Girdikten sonra fiyat belirgin biçimde daha aşağı indi.
    - ``geç``: Fiyat zaten dipten yukarı dönmüşken girdik.
    - ``zamanında``: Giriş, yerel dibe yakın.

    Çıkış için simetriktir (yükseliş devam ettiyse ``erken``).
    """
    n = len(high)
    entry_idx = int(trade.get("entry_idx") or 0)
    exit_idx = int(trade.get("exit_idx") or entry_idx)
    entry = float(trade.get("entry") or 0.0)
    exit_price = float(trade.get("exit") or 0.0)
    tol = max(0.0, float(tolerance))

    # ---------------- Giriş ----------------
    fwd_start, fwd_end = entry_idx + 1, min(n, entry_idx + window + 1)
    fwd_low = min(low[fwd_start:fwd_end]) if fwd_start < fwd_end else entry
    fwd_low_idx = (
        fwd_start + int(np.argmin(low[fwd_start:fwd_end])) if fwd_start < fwd_end else entry_idx
    )
    bwd_start, bwd_end = _window_bounds(entry_idx, window, n)
    bwd_low = min(low[bwd_start:bwd_end]) if bwd_start < bwd_end else entry
    bwd_low_idx = (
        bwd_start + int(np.argmin(low[bwd_start:bwd_end])) if bwd_start < bwd_end else entry_idx
    )

    if entry > 0 and (entry - fwd_low) / entry > tol:
        entry_verdict = "erken"
        ideal_entry_idx = fwd_low_idx
        entry_error_pct = (entry - fwd_low) / entry * 100.0
    elif entry > 0 and (entry - bwd_low) / entry < tol:
        entry_verdict = "zamanında"
        ideal_entry_idx = entry_idx
        entry_error_pct = max(0.0, (entry - fwd_low) / entry * 100.0)
    else:
        entry_verdict = "geç"
        ideal_entry_idx = bwd_low_idx
        entry_error_pct = max(0.0, (entry - bwd_low) / entry * 100.0)

    # ---------------- Çıkış ----------------
    ex_start, ex_end = _window_bounds(exit_idx, window, n)
    fwd_high = max(high[exit_idx + 1 : min(n, exit_idx + window + 1)]) if exit_idx + 1 < n else exit_price
    fwd_high_idx = exit_idx
    if exit_idx + 1 < min(n, exit_idx + window + 1):
        seg = high[exit_idx + 1 : min(n, exit_idx + window + 1)]
        fwd_high_idx = exit_idx + 1 + int(np.argmax(seg))
    bwd_high = max(high[ex_start:ex_end]) if ex_start < ex_end else exit_price

    if exit_price > 0 and (fwd_high - exit_price) / exit_price > tol:
        exit_verdict = "erken"
        ideal_exit_idx = fwd_high_idx
        exit_error_pct = (fwd_high - exit_price) / exit_price * 100.0
    elif exit_price > 0 and (bwd_high - exit_price) / exit_price < tol:
        exit_verdict = "zamanında"
        ideal_exit_idx = exit_idx
        exit_error_pct = max(0.0, (fwd_high - exit_price) / exit_price * 100.0)
    else:
        exit_verdict = "geç"
        ideal_exit_idx = int(np.argmax(high[ex_start:ex_end])) + ex_start if ex_start < ex_end else exit_idx
        exit_error_pct = max(0.0, (bwd_high - exit_price) / exit_price * 100.0)

    return {
        **trade,
        "entry_verdict": entry_verdict,
        "exit_verdict": exit_verdict,
        "entry_error_pct": round(entry_error_pct, 3),
        "exit_error_pct": round(exit_error_pct, 3),
        "ideal_entry_idx": int(ideal_entry_idx),
        "ideal_exit_idx": int(ideal_exit_idx),
    }


def analyze_trades(
    trades: List[Dict[str, Any]],
    high: Sequence[float],
    low: Sequence[float],
    window: int,
    tolerance: float = 0.004,
) -> List[Dict[str, Any]]:
    return [
        classify_trade(t, high, low, max(1, int(window)), tolerance)
        for t in trades
        if t.get("reason") != "end"
    ]


def summarize(timed: List[Dict[str, Any]]) -> Dict[str, Any]:
    def counts(key: str) -> Dict[str, int]:
        out = {"erken": 0, "geç": 0, "zamanında": 0}
        for item in timed:
            verdict = item.get(key)
            if verdict in out:
                out[verdict] += 1
        return out

    losses = [t for t in timed if float(t.get("pnl_pct") or 0) <= 0]
    loss_entry = counts_for(losses, "entry_verdict")
    loss_exit = counts_for(losses, "exit_verdict")
    return {
        "trades": len(timed),
        "entry": counts("entry_verdict"),
        "exit": counts("exit_verdict"),
        "loss_entry": loss_entry,
        "loss_exit": loss_exit,
        "avg_entry_error_pct": round(
            float(np.mean([t.get("entry_error_pct") or 0 for t in timed])) if timed else 0.0, 2
        ),
        "avg_exit_error_pct": round(
            float(np.mean([t.get("exit_error_pct") or 0 for t in timed])) if timed else 0.0, 2
        ),
    }


def counts_for(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out = {"erken": 0, "geç": 0, "zamanında": 0}
    for item in items:
        verdict = item.get(key)
        if verdict in out:
            out[verdict] += 1
    return out
