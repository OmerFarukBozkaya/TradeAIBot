"""Local_Min_Max hedefi: etiketler, uyum ölçümü ve eşik seçimi."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts
from app.ai.labels import build_labels
from app.ai.objective import (
    agreement,
    band_labels,
    choose_agreement_threshold,
    objective_score,
    pivot_marks,
)
from app.ai.trainer import train_model, _atr_pct, _auto_moves


def _series(n=400, seed=11):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    close[100] = close[95:105].min() * 0.99
    close[200] = close[195:205].max() * 1.01
    return close, close * 1.004, close * 0.996


def test_pivot_marks_find_obvious_extremes():
    close, high, low = _series()
    marks = pivot_marks(high, low, window=5)
    assert marks["buy"].any() and marks["sell"].any()
    assert marks["buy"].sum() < len(close) * 0.2


def test_band_labels_are_balanced_and_causal():
    close, high, low = _series()
    labels = band_labels(close, high, low, window=5, band=0.001)
    positives = float(np.mean(labels["buy"][5:-5] == 1))
    assert 0.01 < positives < 0.6
    # İlk/son pencere etiketsiz kalmalı (gelecek gerekli).
    assert labels["buy"][0] == -1


def test_build_labels_defaults_to_local_min_max():
    close, high, low = _series()
    labels = build_labels(close, high, low, {})
    assert labels["valid"].sum() > 0
    # `window` sonrası pozitifler var, son `window` mum geçersiz.
    assert labels["valid"][-3:].tolist() == [False, False, False]


def test_agreement_matches_with_tolerance():
    close, high, low = _series()
    marks = pivot_marks(high, low, window=5)
    oracle = np.where(marks["buy"])[0]
    idx = np.arange(len(close))
    prob = np.zeros(len(close))
    # Gerçek pivotların 1 mum sağında sinyal üret: tolerans sayesinde tutmalı.
    prob[np.clip(oracle + 1, 0, len(close) - 1)] = 0.95
    result = agreement(
        prob, np.zeros(len(close)), idx, high, low,
        buy_threshold=0.6, sell_threshold=0.6, window=5, tolerance=1,
    )
    assert result["buy"]["tp"] > 0
    assert result["buy"]["precision"] >= 0.9
    # tolerans 0 → aynı sinyaller tutmamalı
    strict = agreement(
        prob, np.zeros(len(close)), idx, high, low,
        buy_threshold=0.6, sell_threshold=0.6, window=5, tolerance=0,
    )
    assert strict["buy"]["tp"] == 0


def test_choose_agreement_threshold_respects_min_precision():
    close, high, low = _series()
    marks = pivot_marks(high, low, window=5)
    oracle = np.where(marks["buy"])[0]
    idx = np.arange(len(close))
    prob = np.full(len(close), 0.2)
    prob[oracle] = 0.9
    prob[oracle + 2] = 0.55  # gürültü
    pick = choose_agreement_threshold(
        prob, idx, marks["buy"], tolerance=1, min_precision=0.5
    )
    assert pick["threshold"] > 0.5
    assert (pick["precision"] or 0) >= 0.5


def test_objective_score_rewards_agreement_and_edge():
    good = objective_score({"f1": 0.5}, {"trade_count": 30, "edge_pct": 10, "total_return_pct": 5})
    bad = objective_score({"f1": 0.05}, {"trade_count": 30, "edge_pct": -10, "total_return_pct": -15})
    assert good > bad
    # Az işlem cezalandırılır.
    few = objective_score({"f1": 0.5}, {"trade_count": 1, "edge_pct": 10, "total_return_pct": 5})
    assert few < good


def test_atr_moves_are_volatility_scaled():
    close, high, low = _series(600)
    cfg = {"target_move": 0.01, "stop_move": 0.01}
    _auto_moves(cfg, high, low, close)
    assert cfg["moves_source"] == "atr"
    assert cfg["target_move"] > cfg["stop_move"]
    assert 0.002 <= cfg["stop_move"] <= 0.2
    assert _atr_pct(high, low, close) > 0


def test_training_uses_local_min_max_objective(tmp_path, monkeypatch):
    close, high, low = _series(3000)
    data = {
        "open": close.tolist(), "high": high.tolist(), "low": low.tolist(),
        "close": close.tolist(),
        "volume_usdt": np.linspace(1e6, 2e6, len(close)).tolist(),
        "opendate": (np.arange(len(close)) * 3_600_000.0).tolist(),
    }
    meta = {
        "source": "synthetic", "rows": len(close), "coin": "TESTLMM",
        "period": "1h", "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))

    result = train_model(
        {
            "name": "lmm", "coin": "TESTLMM", "period": "1h", "limit": len(close),
            "walk_forward": False, "use_feedback": False, "refine": True,
            "iterations": 2, "patience": 1, "min_trades": 2,
            "spec": {
                "engine": "mlp", "output_mode": "dual_binary",
                "hidden_layers": [16], "epochs": 25, "patience": 6,
                "feature_groups": ["returns", "range_position", "local_extremes"],
            },
        }
    )
    report = result["report"]
    assert report["objective"]["kind"] == "local_min_max"
    assert report["objective"]["moves_source"] == "atr"
    assert report["agreement"]["test"]["buy"]["oracle"] >= 0
    assert "f1" in report["agreement"]["test"]
    # Manifest metriklerinde uyum kayıtlı olmalı (panel/otomatik seçim için).
    assert "agreement" in result["model"]["metrics"]
