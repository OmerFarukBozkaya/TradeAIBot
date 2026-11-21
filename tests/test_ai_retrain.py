"""Aynı modeli tekrar tekrar eğitme (kimlik sabit, sürüm artar)."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts
from app.ai.trainer import train_model


def _synthetic(n=4000, seed=41):
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
        "source": "synthetic", "rows": len(data["close"]), "coin": "TESTRT",
        "period": "1h", "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    return len(data["close"])


def _params(n):
    return {
        "coin": "TESTRT", "period": "1h", "limit": n, "source": "synthetic",
        "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
        "walk_forward": False, "use_feedback": False,
        "refine": True, "iterations": 2, "patience": 1, "min_trades": 2,
        "spec": {
            "engine": "mlp", "output_mode": "dual_binary",
            "hidden_layers": [16, 8], "epochs": 20, "patience": 5,
            "feature_groups": ["returns", "rsi_macd"],
        },
    }


def test_save_model_updates_same_id_and_bumps_version(patched):
    n = patched
    base = {"hidden_layers": [4], "feature_names": ["a"], "bundle": {"x": 1}}
    first = artifacts.save_model(
        name="m", bundle={"v": 1}, params={"p": 1}, metrics={"test": {"total_return_pct": 1}},
        data_meta={"rows": n}, feature_names=["a"], thresholds={"buy": 0.6, "sell": 0.6},
    )
    assert first["version"] == 1
    second = artifacts.save_model(
        name="m", bundle={"v": 2}, params={"p": 1}, metrics={"test": {"total_return_pct": 2}},
        data_meta={"rows": n}, feature_names=["a"], thresholds={"buy": 0.5, "sell": 0.5},
        model_id=first["id"],
    )
    assert second["id"] == first["id"]
    assert second["version"] == 2
    assert second["created_at"] == first["created_at"]
    assert len(second["history"]) == 1
    assert artifacts.load_bundle(first["id"])["v"] == 2
    listed = [m for m in artifacts.list_models() if m["id"] == first["id"]][0]
    assert listed["version"] == 2


def test_retrain_model_id_keeps_identity(patched):
    n = patched
    first = train_model({**_params(n), "name": "retrain-me"})
    model_id = first["model"]["id"]
    assert first["model"]["version"] == 1

    second = train_model({**_params(n), "retrain_model_id": model_id})
    assert second["model"]["id"] == model_id, "kimlik değişmemeli"
    assert second["model"]["version"] == 2
    assert second["report"]["lineage"]["warm_start_used"] is True
    assert second["report"]["lineage"]["parent_id"] == model_id
    assert second["model"]["name"] == first["model"]["name"]
    # Mimari mevcut modelden korunur.
    assert second["report"]["spec"]["hidden_layers"] == [16, 8]


def test_retrain_preserves_architecture_despite_params(patched):
    n = patched
    first = train_model({**_params(n), "name": "keep-arch"})
    model_id = first["model"]["id"]
    changed = _params(n)
    changed["spec"] = {**changed["spec"], "hidden_layers": [64, 64, 64]}
    second = train_model({**changed, "retrain_model_id": model_id})
    assert second["report"]["spec"]["hidden_layers"] == [16, 8]


def test_retrain_unknown_model_raises(patched):
    n = patched
    with pytest.raises(ValueError):
        train_model({**_params(n), "retrain_model_id": "ai_yok_boyle_model"})


def test_retrain_handler_keeps_model_when_worse(monkeypatch, patched):
    from app.job_runner import run_ai_retrain

    n = patched
    first = train_model({**_params(n), "name": "handler"})
    model_id = first["model"]["id"]
    version_before = first["model"]["version"]

    calls = {"n": 0}
    real_train = train_model

    def fake_train(params):
        calls["n"] += 1
        result = real_train(params)
        # Her adayı bilerek kötüleştir: skor ve çoklu-pencere uyumu düşsün.
        result["model"]["metrics"]["refinement"] = {"best_score": -999.0}
        agr = result["model"]["metrics"].setdefault("agreement", {})
        agr["robust"] = {"f1": 0.01, "windows": 3}
        lineage = result["report"].setdefault("lineage", {})
        lineage["parent_robust_f1"] = 0.5
        return result

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    out = run_ai_retrain({"model_id": model_id, "repeats": 2})
    assert out["model_id"] == model_id
    assert out["promoted"] == 0
    assert all(not a["improved"] for a in out["attempts"])
    manifest = artifacts.load_manifest(model_id)
    assert manifest["version"] == version_before
    assert len(artifacts.load_bundle(model_id)) > 0
    assert calls["n"] == 2


def test_retrain_repeats_use_distinct_seeds(monkeypatch, patched):
    """Aynı veri + aynı tohum birebir aynı modeli üretir; her tur farklı tohum almalı."""
    from app.job_runner import run_ai_retrain

    n = patched
    first = train_model({**_params(n), "name": "seeds"})
    model_id = first["model"]["id"]

    real_train = train_model
    seen = []

    def fake_train(params):
        seen.append(int(params.get("seed_offset") or 0))
        result = real_train({**params, "seed_offset": 0})
        result["model"]["metrics"]["refinement"] = {"best_score": -999.0}
        return result

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    run_ai_retrain({"model_id": model_id, "repeats": 3})
    assert seen == [997, 1994, 2991], "her tur farklı tohum kullanmalı"


def test_retrain_forwards_refresh_data(monkeypatch, patched):
    """Yeni mum çekme isteği eğitime kadar ulaşmalı."""
    from app.job_runner import run_ai_retrain

    n = patched
    first = train_model({**_params(n), "name": "refresh"})
    model_id = first["model"]["id"]

    real_train = train_model
    seen = {}

    def fake_train(params):
        seen.update({k: params.get(k) for k in ("refresh_data", "dataset_id")})
        result = real_train({**params, "refresh_data": False})
        result["model"]["metrics"]["refinement"] = {"best_score": -999.0}
        return result

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    run_ai_retrain({"model_id": model_id, "repeats": 1, "refresh_data": True})
    assert seen["refresh_data"] is True
    assert not seen["dataset_id"]


def test_seed_offset_changes_weights(patched):
    """Farklı tohum farklı ağırlıklar üretmeli (tekrar eğitim kör kopya olmasın)."""
    n = patched
    a = train_model({**_params(n), "name": "seed-a", "seed_offset": 0})
    b = train_model({**_params(n), "name": "seed-b", "seed_offset": 997})
    wa = artifacts.load_bundle(a["model"]["id"])["buy_model"].weights_[0]
    wb = artifacts.load_bundle(b["model"]["id"])["buy_model"].weights_[0]
    assert np.any(np.abs(np.asarray(wa) - np.asarray(wb)) > 1e-9)


def test_retrain_explores_distinct_learning_each_round(monkeypatch, patched):
    """Aynı veri kalır; her tur farklı öğrenme yapılandırması denemeli."""
    from app.job_runner import run_ai_retrain

    n = patched
    base = train_model({**_params(n), "name": "explore-base"})
    model_id = base["model"]["id"]

    real_train = train_model
    seen = []

    def fake_train(params):
        out = real_train(params)
        spec = out["report"]["spec"]
        seen.append((spec["learning_rate"], spec["dropout"], spec["hidden_layers"]))
        out["model"]["metrics"]["refinement"] = {"best_score": -999.0}
        return out

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    run_ai_retrain({"model_id": model_id, "repeats": 3})

    assert len(seen) == 3
    assert len({(lr, drop) for lr, drop, _ in seen}) == 3, "her tur farklı öğrenme ayarı"
    assert all(layers == [16, 8] for _, _, layers in seen), "mimari korunmalı"


def test_retrain_focus_weights_hard_examples(patched):
    """Aynı veri: önceki neslin yanıldığı örnekler daha yüksek ağırlık almalı."""
    n = patched
    base = train_model({**_params(n), "name": "focus-base"})
    model_id = base["model"]["id"]
    focused = train_model({
        **_params(n),
        "parent_model_id": model_id,
        "warm_start": True,
        "focus": 1.0,
        "seed_offset": 997,
    })
    info = focused["report"]["lineage"].get("focus") or {}
    assert info.get("weight") == 1.0
    assert float(info.get("mean_error") or 0) > 0
    assert int(info.get("boosted") or 0) > 0, "bazı örnekler ek ağırlık almalı"
    # Odak yoksa ağırlık 0 kalır.
    plain = train_model({**_params(n), "name": "focus-none"})
    assert (plain["report"]["lineage"].get("focus") or {}).get("weight") == 0.0


def test_focus_changes_weights(patched):
    n = patched
    base = train_model({**_params(n), "name": "focus-w0"})
    model_id = base["model"]["id"]
    a = train_model({
        **_params(n), "parent_model_id": model_id, "warm_start": True,
        "focus": 0.0, "seed_offset": 5,
    })
    b = train_model({
        **_params(n), "parent_model_id": model_id, "warm_start": True,
        "focus": 1.5, "seed_offset": 5,
    })
    wa = artifacts.load_bundle(a["model"]["id"])["buy_model"].weights_[0]
    wb = artifacts.load_bundle(b["model"]["id"])["buy_model"].weights_[0]
    assert np.any(np.abs(np.asarray(wa) - np.asarray(wb)) > 1e-9)


def test_retrain_handler_passes_growing_focus(monkeypatch, patched):
    from app.job_runner import run_ai_retrain

    n = patched
    base = train_model({**_params(n), "name": "focus-handler"})
    model_id = base["model"]["id"]

    real_train = train_model
    seen = []

    def fake_train(params):
        seen.append(round(float(params.get("focus") or 0.0), 3))
        result = real_train({**params, "focus": 0.0})
        result["model"]["metrics"]["refinement"] = {"best_score": -999.0}
        return result

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    run_ai_retrain({"model_id": model_id, "repeats": 3})
    assert seen == [0.5, 0.75, 1.0], "odak turdan tura artmalı"


def test_retrain_handler_accepts_improvement(monkeypatch, patched):
    from app.job_runner import run_ai_retrain

    n = patched
    first = train_model({**_params(n), "name": "handler2"})
    model_id = first["model"]["id"]

    real_train = train_model
    counter = {"n": 0}

    def fake_train(params):
        counter["n"] += 1
        result = real_train(params)
        result["model"]["metrics"]["refinement"] = {"best_score": 100.0 + counter["n"]}
        # Çoklu-pencere uyumu da iyileşsin; aksi halde terfi reddedilir.
        agr = result["model"]["metrics"].setdefault("agreement", {})
        agr["robust"] = {"f1": 0.30 + 0.05 * counter["n"], "windows": 3}
        lineage = result["report"].setdefault("lineage", {})
        lineage["parent_robust_f1"] = 0.30 + 0.05 * (counter["n"] - 1)
        return result

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    monkeypatch.setattr("app.job_runner.settings.AI_ENABLED", True, raising=False)
    out = run_ai_retrain({"model_id": model_id, "repeats": 2, "min_gain": 0})
    assert out["promoted"] == 2
    manifest = artifacts.load_manifest(model_id)
    assert manifest["version"] == 3
    assert len(manifest["history"]) == 2
