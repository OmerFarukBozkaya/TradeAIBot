"""Tek düğme otomatik eğitim: profil, aday arama ve gerilemesiz karar."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts, auto


def _synthetic(n=4000, seed=51):
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


@pytest.fixture()
def patched(tmp_path, monkeypatch):
    data = _synthetic()
    meta = {
        "source": "synthetic", "rows": len(data["close"]), "coin": "TESTAUTO",
        "period": "1h", "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    auto.save_profile(
        {
            "coin": "TESTAUTO", "period": "1h", "limit": len(data["close"]),
            "search_budget": 2, "refine_iterations": 2, "refine_patience": 1,
            "walk_forward": False, "use_feedback": False, "min_trades": 2,
            "hidden_layers": [16, 8], "activation": "relu",
            "feature_groups": ["returns", "rsi_macd"],
            "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
            "engine": "mlp", "auto_snapshot": False, "dataset_id": "",
        }
    )
    return len(data["close"])


def test_profile_roundtrip_and_validation():
    saved = auto.save_profile(
        {
            "coin": "ethusdt", "period": "4h", "limit": 5000, "search_budget": 3,
            "refine_iterations": 4, "horizon": 20, "target_move": 0.02,
            "feature_groups": ["returns", "yok"], "min_gain": 0.5,
        }
    )
    assert saved["coin"] == "ETHUSDT"
    assert saved["period"] == "4h"
    assert saved["search_budget"] == 3
    assert saved["horizon"] == 20
    assert saved["feature_groups"] == ["returns"]
    # Sınır dışı değerler kırpılır.
    clamped = auto.save_profile({"limit": 10, "search_budget": 99, "horizon": 9999})
    assert clamped["limit"] == 2000
    assert clamped["search_budget"] == 8
    assert clamped["horizon"] == 500


def test_candidate_specs_respects_budget():
    auto.save_profile({"engine": "mlp", "search_budget": 3, "feature_groups": [], "hidden_layers": []})
    specs = auto.candidate_specs(auto.load_profile())
    assert 1 <= len(specs) <= 3
    assert all(s["engine"] == "mlp" for s in specs)
    assert all(s["feature_groups"] for s in specs)


def test_auto_train_creates_first_model(patched):
    result = auto.auto_train({})
    assert result["ok"] is True
    assert result["decision"] == "created"
    assert result["active_model_id"]
    manifest = artifacts.load_manifest(result["active_model_id"])
    assert manifest["status"] == "active"
    assert result["attempts"]
    assert result["report"]["test"]["trading"]


def test_auto_train_updates_same_model_on_improvement(patched, monkeypatch):
    first = auto.auto_train({})
    champ_id = first["active_model_id"]
    assert artifacts.load_manifest(champ_id)["version"] == 1

    # Adayları yapay olarak çok iyi göster: güncelleme beklenir.
    real = auto.train_model
    monkeypatch.setattr(
        auto, "train_model",
        lambda p: _boost(real(p), 500.0),
    )
    second = auto.auto_train({})
    assert second["decision"] == "updated"
    assert second["active_model_id"] == champ_id
    manifest = artifacts.load_manifest(champ_id)
    assert manifest["version"] == 2


def test_auto_train_keeps_champion_when_not_better(patched, monkeypatch):
    """Şampiyon aynı ölçütle karşılaştırılabiliyorsa gerileme kabul edilmez."""
    first = auto.auto_train({})
    champ_id = first["active_model_id"]
    champ = artifacts.load_manifest(champ_id)
    # Şampiyona yeni ölçütü ekle: artık kıyaslanabilir.
    champ.setdefault("metrics", {})["quality"] = {"robust": {"score": 50.0}}
    artifacts.save_model(
        name=champ["name"], bundle=artifacts.load_bundle(champ_id),
        model_id=champ_id, params=champ.get("params") or {}, metrics=champ["metrics"],
        data_meta=champ.get("data") or {}, feature_names=champ.get("feature_names") or [],
        thresholds=champ.get("thresholds") or {},
    )

    real = auto.train_model
    monkeypatch.setattr(auto, "train_model", lambda p: _boost(real(p), -500.0))
    second = auto.auto_train({})
    assert second["decision"] == "kept"
    assert second["active_model_id"] == champ_id


def test_auto_train_replaces_legacy_model_without_comparable_metric(patched, monkeypatch):
    """Eski ölçütle eğitilmiş şampiyon, yeni adayla elma-armut kıyaslanmaz."""
    first = auto.auto_train({})
    champ_id = first["active_model_id"]
    champ = artifacts.load_manifest(champ_id)
    champ.setdefault("metrics", {}).pop("quality", None)
    artifacts.save_model(
        name=champ["name"], bundle=artifacts.load_bundle(champ_id),
        model_id=champ_id, params=champ.get("params") or {}, metrics=champ["metrics"],
        data_meta=champ.get("data") or {}, feature_names=champ.get("feature_names") or [],
        thresholds=champ.get("thresholds") or {},
    )
    second = auto.auto_train({})
    assert second["decision"] in {"created", "updated"}


def _boost(result, delta):
    result["model"]["metrics"].setdefault("refinement", {})["best_score"] = delta
    if "validation" in result["model"]["metrics"]:
        result["model"]["metrics"]["validation"]["edge_pct"] = delta
    return result

def test_auto_train_never_raises_when_all_candidates_fail(patched, monkeypatch):
    first = auto.auto_train({})
    champ_id = first["active_model_id"]

    def boom(params):
        raise RuntimeError("aday patladı")

    monkeypatch.setattr(auto, "train_model", boom)
    second = auto.auto_train({})
    assert second["ok"] is True
    assert second["decision"] == "kept"
    assert second["active_model_id"] == champ_id
    assert second["attempts"]
