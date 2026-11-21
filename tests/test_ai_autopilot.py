"""Otomatik öğrenme: kalite kapısı, terfi ve tekrar deneme mantığı."""

from __future__ import annotations

import pytest

from app.ai import autopilot, artifacts
from app import db


def _report(*, test_ret=12.0, edge=4.0, trades=20, train_ret=30.0, folds_ret=(5.0, 3.0, -1.0), folds_edge=(2.0, 1.5, 0.5)):
    folds = [
        {"fold": i + 1, "trading": {"total_return_pct": r, "edge_pct": e}}
        for i, (r, e) in enumerate(zip(folds_ret, folds_edge))
    ]
    return {
        "test": {"trading": {"total_return_pct": test_ret, "edge_pct": edge, "trade_count": trades}},
        "train": {"trading": {"total_return_pct": train_ret}},
        "walk_forward": folds,
        "walk_forward_summary": {
            "folds": len(folds),
            "avg_edge_pct": sum(folds_edge) / len(folds_edge),
        },
    }


def test_gate_rejects_negative_edge_and_low_trades():
    gate = autopilot.evaluate_gate(
        _report(test_ret=-2, edge=-1, trades=3), autopilot.PRESETS["balanced"]
    )
    assert not gate["passed"]
    joined = " ".join(gate["reasons"])
    assert "işlem sayısı" in joined
    assert "edge negatif" in joined


def test_gate_rejects_overfit_model():
    # Eğitimde %100, testte %5 → aşırı öğrenme.
    gate = autopilot.evaluate_gate(
        _report(test_ret=5.0, edge=2.0, trades=25, train_ret=100.0),
        autopilot.PRESETS["balanced"],
    )
    assert not gate["passed"]
    assert any("Aşırı öğrenme" in reason for reason in gate["reasons"])


def test_gate_rejects_inconsistent_walk_forward():
    gate = autopilot.evaluate_gate(
        _report(folds_ret=(-4.0, -3.0, 1.0), folds_edge=(-2.0, -1.0, 0.2)),
        autopilot.PRESETS["balanced"],
    )
    assert not gate["passed"]
    assert any("Walk-forward" in reason for reason in gate["reasons"])


def test_gate_accepts_reasonable_model():
    gate = autopilot.evaluate_gate(_report(), autopilot.PRESETS["balanced"])
    assert gate["passed"], gate["reasons"]
    assert gate["score"] > 0


def test_save_settings_and_next_run(tmp_path):
    saved = autopilot.save_settings(
        {"enabled": True, "coin": "ethusdt", "period": "4h", "preset": "cautious", "interval_hours": 6}
    )
    assert saved["coin"] == "ETHUSDT"
    assert saved["period"] == "4h"
    assert saved["preset"] == "cautious"
    cfg = autopilot.load_settings()
    due = autopilot.next_run_at(cfg)
    assert due is not None


def test_build_params_uses_preset():
    cfg = autopilot.load_settings()
    params = autopilot.build_params({**cfg, "preset": "aggressive"}, "manual")
    assert params["horizon"] == autopilot.PRESETS["aggressive"]["horizon"]
    assert params["walk_forward"] is True
    assert params["use_feedback"] is True


def test_run_once_promotes_first_good_model(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    autopilot.save_settings({"enabled": True, "coin": "TESTUSDT", "period": "1h", "preset": "balanced"})

    def fake_train(params):
        report = _report()
        manifest = artifacts.save_model(
            name="fake",
            bundle={"dummy": True},
            params=params,
            metrics={"test": report["test"]["trading"], "walk_forward": report["walk_forward_summary"]},
            data_meta={"rows": 1000},
            feature_names=["a"],
            thresholds={"buy": 0.6, "sell": 0.6},
        )
        return {"ok": True, "model": manifest, "report": report}

    monkeypatch.setattr("app.ai.trainer.train_model", fake_train)
    result = autopilot.run_once("test")
    assert result["decision"] == "promoted"
    manifest = artifacts.load_manifest(result["model_id"])
    assert manifest["status"] == "active"


def test_run_once_keeps_champion_when_challenger_not_better(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    autopilot.save_settings({"enabled": True, "coin": "TESTUSDT", "period": "1h", "preset": "balanced"})

    def make_train(test_ret, edge):
        def fake_train(params):
            report = _report(test_ret=test_ret, edge=edge)
            manifest = artifacts.save_model(
                name="fake",
                bundle={"dummy": True},
                params=params,
                metrics={"test": report["test"]["trading"], "walk_forward": report["walk_forward_summary"]},
                data_meta={"rows": 1000},
                feature_names=["a"],
                thresholds={"buy": 0.6, "sell": 0.6},
            )
            return {"ok": True, "model": manifest, "report": report}
        return fake_train

    monkeypatch.setattr("app.ai.trainer.train_model", make_train(20.0, 8.0))
    first = autopilot.run_once("test")
    assert first["decision"] == "promoted"

    monkeypatch.setattr("app.ai.trainer.train_model", make_train(12.0, 4.0))
    second = autopilot.run_once("test")
    assert second["decision"] == "kept"
    assert artifacts.load_manifest(first["model_id"])["status"] == "active"


def _saved_archived_model(tmp_path, monkeypatch):
    from app.ai import model as ai_model

    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    X = [[float(i), 1.0] for i in range(200)]
    y = [i % 2 for i in range(200)]
    bundle = {
        "buy_model": ai_model.fit_classifier(X, y),
        "sell_model": ai_model.fit_classifier(X, y),
        "feature_names": ["f1", "f2"],
        "fill_values": [0.0, 0.0],
        "thresholds": {"buy": 0.6, "sell": 0.6},
        "params": {},
        "horizon": 5,
    }
    manifest = artifacts.save_model(
        name="archived",
        bundle=bundle,
        params={"coin": "BTCUSDT", "period": "1h"},
        metrics={},
        data_meta={"rows": 200},
        feature_names=["f1", "f2"],
        thresholds={"buy": 0.6, "sell": 0.6},
    )
    artifacts.set_status(manifest["id"], "archived")
    return manifest["id"]


def test_archived_model_blocked_for_bots(tmp_path, monkeypatch):
    from app.strategies.service import build_evaluator

    model_id = _saved_archived_model(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        build_evaluator({"type": "ai", "model_id": model_id})


def test_archived_model_allowed_for_backtest(tmp_path, monkeypatch):
    from app.strategies.service import build_evaluator

    model_id = _saved_archived_model(tmp_path, monkeypatch)
    evaluator = build_evaluator({"type": "ai", "model_id": model_id}, allow_archived=True)
    assert evaluator.id == model_id


def test_autopilot_persists_architecture_spec():
    saved = autopilot.save_settings({
        "spec": {
            "engine": "mlp",
            "output_mode": "ternary",
            "hidden_layers": [32, 16],
            "activation": "tanh",
            "feature_groups": ["returns", "rsi_macd"],
        }
    })
    assert saved["spec"]["hidden_layers"] == [32, 16]
    assert saved["spec"]["output_mode"] == "ternary"
    params = autopilot.build_params(autopilot.load_settings(), "test")
    assert params["spec"]["activation"] == "tanh"
    assert params["spec"]["feature_groups"] == ["returns", "rsi_macd"]
