"""Sıcak başlangıç ve nesiller boyu eğitim (evolve)."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts
from app.ai.evolve import evolve
from app.ai.trainer import train_model


def _synthetic(n=5000, seed=31):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    return {
        "open": (close * (1 + rng.normal(0, 0.0005, n))).tolist(),
        "high": (close * (1 + np.abs(rng.normal(0, 0.003, n)))).tolist(),
        "low": (close * (1 - np.abs(rng.normal(0, 0.003, n)))).tolist(),
        "close": close.tolist(),
        "volume_usdt": rng.lognormal(10, 1, n).tolist(),
        "opendate": (np.arange(n) * 3_600_000).tolist(),
    }


def _base(n):
    return {
        "coin": "TESTEVO", "period": "1h", "limit": n, "source": "synthetic",
        "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
        "walk_forward": False, "use_feedback": False,
        "refine": True, "iterations": 2, "patience": 1, "min_trades": 2,
        "spec": {
            "engine": "mlp", "output_mode": "dual_binary",
            "hidden_layers": [24, 12], "epochs": 25, "patience": 6,
            "feature_groups": ["returns", "rsi_macd", "local_extremes"],
        },
    }


def _patch(tmp_path, monkeypatch, data):
    meta = {
        "source": "synthetic", "rows": len(data["close"]), "coin": "TESTEVO",
        "period": "1h", "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))


def test_warm_start_builds_on_parent(tmp_path, monkeypatch):
    data = _synthetic()
    _patch(tmp_path, monkeypatch, data)
    first = train_model({**_base(len(data["close"])), "name": "gen1"})
    assert first["report"]["lineage"]["warm_start_used"] is False

    second = train_model(
        {**_base(len(data["close"])), "name": "gen2", "parent_model_id": first["model"]["id"], "generation": 2}
    )
    lineage = second["report"]["lineage"]
    assert lineage["warm_start_used"] is True
    assert lineage["parent_id"] == first["model"]["id"]
    assert lineage["parent_validation"] is not None
    # Modelin ilk katmanı önceki nesilden devralınmış olmalı.
    head = second["report"]["model"]["models"][0]
    assert head["warm_started"] is True


def test_warm_start_skipped_when_features_differ(tmp_path, monkeypatch):
    data = _synthetic()
    _patch(tmp_path, monkeypatch, data)
    first = train_model({**_base(len(data["close"])), "name": "gen1"})
    changed = _base(len(data["close"]))
    changed["spec"] = {**changed["spec"], "feature_groups": ["returns", "volume", "bollinger"]}
    second = train_model(
        {**changed, "name": "gen2", "parent_model_id": first["model"]["id"]}
    )
    lineage = second["report"]["lineage"]
    assert lineage["warm_start_used"] is False
    assert "Özellik şeması farklı" in lineage["warm_start_note"]


def test_skip_test_leaves_test_empty(tmp_path, monkeypatch):
    data = _synthetic()
    _patch(tmp_path, monkeypatch, data)
    result = train_model({**_base(len(data["close"])), "skip_test": True})
    assert result["report"]["skip_test"] is True
    assert result["report"]["test"]["trading"] == {}


def test_evolve_runs_generations_and_keeps_best(tmp_path, monkeypatch):
    data = _synthetic()
    _patch(tmp_path, monkeypatch, data)
    result = evolve(
        {
            **_base(len(data["close"])),
            "generations": 3,
            "evolve_patience": 1,
            "preset": "balanced",
        }
    )
    assert result["ok"] is True
    assert result["decision"] in {"promoted", "kept", "rejected", "candidate"}
    assert result["best_generation"] >= 1
    # Nesil kayıtları var ve en az bir sıcak başlangıç denenmiş olmalı.
    assert len(result["history"]) >= 2
    assert any(h.get("warm_start_used") for h in result["history"])
    # Nihai rapor testi içerir.
    assert (result.get("report") or {}).get("test") is not None


def test_evolve_does_not_regress_selection_score(tmp_path, monkeypatch):
    data = _synthetic()
    _patch(tmp_path, monkeypatch, data)
    result = evolve(
        {**_base(len(data["close"])), "generations": 3, "evolve_patience": 1, "preset": "balanced"}
    )
    scores = [h["score"] for h in result["history"] if not h.get("final_audit")]
    # Nesil kabulü min_delta (varsayılan 0.02) kadar fark ister; nihai skor
    # en iyi neslin skorudur, en yüksek anlık skordan bu tolerans kadar
    # düşük olabilir.
    assert result["best_score"] >= max(scores) - 0.02
