"""Zamanlama hatası analizi ve yinelemeli eğitim raporu."""

from __future__ import annotations

import numpy as np

from app.ai import artifacts
from app.ai.timing import analyze_trades, classify_trade, summarize
from app.ai.trainer import _reweight_from_timing


def _flat(n=60, value=100.0):
    return [value] * n


def test_entry_early_when_price_drops_after_entry():
    high = _flat()
    low = _flat()
    low[20] = 90.0  # girişten sonra fiyat belirgin düştü
    trade = {"entry_idx": 10, "exit_idx": 30, "entry": 100.0, "exit": 101.0, "pnl_pct": 1.0, "reason": "signal"}
    out = classify_trade(trade, high, low, window=12, tolerance=0.004)
    assert out["entry_verdict"] == "erken"
    assert out["ideal_entry_idx"] == 20


def test_entry_late_when_dip_is_behind():
    high = _flat()
    low = _flat()
    low[8] = 90.0  # dip geçmişte kaldı, sonrasında daha aşağı inmadi
    trade = {"entry_idx": 20, "exit_idx": 30, "entry": 100.0, "exit": 101.0, "pnl_pct": 1.0, "reason": "signal"}
    out = classify_trade(trade, high, low, window=12, tolerance=0.004)
    assert out["entry_verdict"] == "geç"
    assert out["ideal_entry_idx"] == 8


def test_exit_early_when_price_keeps_rising():
    high = _flat()
    low = _flat()
    high[40] = 110.0  # çıkıştan sonra yükseliş devam etti
    trade = {"entry_idx": 10, "exit_idx": 30, "entry": 100.0, "exit": 100.0, "pnl_pct": 0.0, "reason": "signal"}
    out = classify_trade(trade, high, low, window=12, tolerance=0.004)
    assert out["exit_verdict"] == "erken"
    assert out["ideal_exit_idx"] == 40


def test_exit_late_when_peak_is_behind():
    high = _flat()
    low = _flat()
    high[24] = 110.0  # zirve geçmişte kaldı
    trade = {"entry_idx": 10, "exit_idx": 30, "entry": 100.0, "exit": 100.0, "pnl_pct": 0.0, "reason": "signal"}
    out = classify_trade(trade, high, low, window=12, tolerance=0.004)
    assert out["exit_verdict"] == "geç"


def test_summary_and_reweighting():
    high = _flat()
    low = _flat()
    low[20] = 90.0
    high[40] = 110.0
    trades = [
        {"entry_idx": 10, "exit_idx": 30, "entry": 100.0, "exit": 100.0, "pnl_pct": -1.0, "reason": "signal"},
    ]
    timed = analyze_trades(trades, high, low, window=12)
    summary = summarize(timed)
    assert summary["trades"] == 1
    assert sum(summary["entry"].values()) == 1

    y_buy = np.zeros(50, dtype=int)
    y_sell = np.zeros(50, dtype=int)
    y_buy[10] = 1
    y_buy[20] = 1
    y_sell[30] = 1
    y_sell[40] = 1
    pos = {i: i for i in range(50)}
    w_buy = np.ones(50)
    w_sell = np.ones(50)
    nb, ns = _reweight_from_timing(w_buy, w_sell, timed, pos, y_buy, y_sell)
    # Erken giriş örneği zayıflar, ideal dip örneği güçlenir.
    assert nb[10] < nb[20]
    # Erken çıkış örneği zayıflar, ideal zirve örneği güçlenir.
    assert ns[30] < ns[40]
    assert abs(float(np.mean(nb)) - 1.0) < 1e-9


def test_training_report_contains_refinement(tmp_path, monkeypatch):
    n = 4000
    rng = np.random.default_rng(21)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    data = {
        "open": (close * (1 + rng.normal(0, 0.0005, n))).tolist(),
        "high": (close * (1 + abs(rng.normal(0, 0.003, n)))).tolist(),
        "low": (close * (1 - abs(rng.normal(0, 0.003, n)))).tolist(),
        "close": close.tolist(),
        "volume_usdt": rng.lognormal(10, 1, n).tolist(),
        "opendate": (np.arange(n) * 3_600_000).tolist(),
    }
    meta = {
        "source": "synthetic", "rows": n, "coin": "TESTREF", "period": "1h",
        "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    from app.ai.trainer import train_model

    result = train_model(
        {
            "name": "refine", "coin": "TESTREF", "period": "1h", "limit": n,
            "source": "synthetic", "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
            "walk_forward": False, "use_feedback": False,
            "refine": True, "iterations": 3, "patience": 1, "min_trades": 2,
        }
    )
    report = result["report"]
    assert report["split_policy"]["learn_pct"] == 70
    assert report["split_policy"]["test_pct"] == 30
    ref = report["refinement"]
    assert ref["enabled"] is True
    assert 1 <= ref["iterations_run"] <= 3
    assert 1 <= ref["best_iteration"] <= ref["iterations_run"]
    assert "timing" in ref
    # Test kümesi hiçbir seçimde kullanılmadı: en iyi tur test değil validation
    # metrikleriyle seçilmiş olmalı.
    assert ref["history"][ref["best_iteration"] - 1]["score"] == ref["best_score"]
