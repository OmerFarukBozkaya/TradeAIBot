"""Yapılandırılabilir mimari: özellik grupları, MLP ve çıktı biçimleri."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts
from app.ai.features import GROUPS, build_features, group_catalog, normalize_groups
from app.ai.model import fit_model, predict_signals
from app.ai.nn import MLP
from app.ai.spec import (
    DEFAULT_SPEC,
    architecture_catalog,
    normalize_spec,
    spec_from_params,
    validate_spec,
)


def _synthetic(n=1200, seed=3):
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


def test_feature_groups_change_matrix_width():
    data = _synthetic(400)
    small = build_features(data, ["returns"])
    big = build_features(data, ["returns", "range_position", "volume"])
    assert 0 < small["X"].shape[1] < big["X"].shape[1]
    assert small["warmup"] < big["warmup"]


def test_feature_selection_is_honoured():
    data = _synthetic(400)
    frame = build_features(data, ["rsi_macd"])["frame"]
    assert all(name.startswith(("rsi", "macd")) for name in frame.columns)


def test_group_catalog_is_complete():
    catalog = group_catalog()
    assert len(catalog) == len(GROUPS)
    assert all(item["column_count"] > 0 for item in catalog)
    assert sum(1 for item in catalog if item["default"]) == len(DEFAULT_SPEC["feature_groups"])


def test_normalize_groups_falls_back():
    assert normalize_groups([]) == list(DEFAULT_SPEC["feature_groups"])
    assert normalize_groups(["returns", "yok"]) == ["returns"]


def test_spec_normalization_and_validation():
    spec = normalize_spec({"hidden_layers": [32, 16], "feature_groups": ["returns"]})
    assert spec["hidden_layers"] == [32, 16]
    assert spec["feature_groups"] == ["returns"]
    assert validate_spec(spec) == []

    bad = normalize_spec({"feature_groups": []})
    assert bad["feature_groups"]  # varsayılana döner
    assert validate_spec({**bad, "hidden_layers": []})


def test_spec_from_params_prefers_explicit_fields():
    spec = spec_from_params({"spec": {"hidden_layers": [8]}, "hidden_layers": [16, 8]})
    assert spec["hidden_layers"] == [16, 8]


def test_architecture_catalog_shape():
    catalog = architecture_catalog()
    assert {item["id"] for item in catalog["engines"]} == {"mlp", "gbm", "lstm", "transformer"}
    assert any(item["id"] == "ternary" for item in catalog["output_modes"])


def test_mlp_learns_separable_pattern():
    rng = np.random.default_rng(5)
    X = rng.normal(size=(900, 6))
    y = (X[:, 0] + X[:, 1] * 0.5 > 0).astype(int)
    model = MLP(hidden_layers=[24, 12], epochs=60, learning_rate=0.01, dropout=0.0, patience=10)
    model.fit(X[:700], y[:700], X_val=X[700:], y_val=y[700:])
    p = model.predict_proba(X[700:])[:, 1]
    acc = float(np.mean((p >= 0.5) == y[700:]))
    assert acc > 0.8
    assert model.history and model.best_epoch >= 1


def test_predict_signals_all_output_modes():
    rng = np.random.default_rng(9)
    X = rng.normal(size=(300, 5))
    y_bin = (X[:, 0] > 0).astype(int)
    spec = normalize_spec({"hidden_layers": [8], "epochs": 80, "patience": 10, "dropout": 0.0})

    buy = fit_model(spec, "binary", X, y_bin, random_state=1)
    sell = fit_model(spec, "binary", X, 1 - y_bin, random_state=2)
    p_buy, p_sell = predict_signals({"output_mode": "dual_binary", "buy_model": buy, "sell_model": sell}, X)
    assert len(p_buy) == len(X) == len(p_sell)
    assert float(p_buy.mean()) > float(p_sell.mean())

    action = np.where(X[:, 0] > 0.5, 1, np.where(X[:, 0] < -0.5, 2, 0))
    multi = fit_model(spec, "multiclass", X, action, n_classes=3, random_state=3)
    p_buy_t, p_sell_t = predict_signals({"output_mode": "ternary", "action_model": multi}, X)
    assert len(p_buy_t) == len(X) and float(p_buy_t.mean()) > 0

    reg = fit_model(spec, "regression", X, X[:, 0] * 0.01, random_state=4)
    scale = float(np.std(reg.predict(X))) or 0.01
    bundle = {"output_mode": "regression", "return_model": reg, "prob_scale": scale}
    p_buy_r, p_sell_r = predict_signals(bundle, X)
    assert len(p_buy_r) == len(X)
    # Getiri tahmini pozitif olduğunda alım olasılığı artmalı.
    assert np.corrcoef(p_buy_r, X[:, 0])[0, 1] > 0.5


def test_training_with_custom_architecture(tmp_path, monkeypatch):
    data = _synthetic(4000, seed=17)
    meta = {
        "source": "synthetic", "rows": len(data["close"]), "coin": "TESTARCH", "period": "1h",
        "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    from app.ai.trainer import train_model

    result = train_model(
        {
            "name": "arch", "coin": "TESTARCH", "period": "1h", "limit": len(data["close"]),
            "source": "synthetic", "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
            "walk_forward": False, "use_feedback": False, "refine": True, "iterations": 2,
            "patience": 1, "min_trades": 2,
            "spec": {
                "engine": "mlp",
                "output_mode": "ternary",
                "hidden_layers": [24, 12],
                "activation": "tanh",
                "dropout": 0.1,
                "epochs": 25,
                "patience": 8,
                "feature_groups": ["returns", "rsi_macd", "local_extremes"],
            },
        }
    )
    report = result["report"]
    assert report["spec"]["hidden_layers"] == [24, 12]
    assert report["spec"]["output_mode"] == "ternary"
    assert report["spec"]["feature_groups"] == ["returns", "rsi_macd", "local_extremes"]
    model_info = report["model"]["models"]
    assert len(model_info) == 1
    assert model_info[0]["layers"] == [24, 12]
    assert model_info[0]["activation"] == "tanh"
    assert report["thresholds"]["buy"] > 0
    # Özellik önemi raporlanır.
    assert model_info[0].get("top_features")


def test_unknown_output_mode_rejected(tmp_path):
    from app.ai.spec import validate_spec as check

    spec = normalize_spec({"output_mode": "yok"})
    assert spec["output_mode"] == "dual_binary"
    assert check(spec) == []


def test_autopilot_body_accepts_spec():
    """Regresyon: ``spec`` alanı Pydantic modelinde yoksa sessizce düşüyordu."""
    from app.api.ai import AutopilotBody

    assert "spec" in AutopilotBody.model_fields
    body = AutopilotBody(**{"spec": {"hidden_layers": [10, 5], "feature_groups": ["returns"]}})
    assert body.model_dump()["spec"]["hidden_layers"] == [10, 5]


def test_autopilot_endpoint_persists_spec():
    """PUT /ai/autopilot mimariyi gerçekten kaydetmeli."""
    import asyncio

    from app.api.ai import AutopilotBody, autopilot_save, autopilot_state

    spec = {
        "engine": "mlp",
        "output_mode": "ternary",
        "hidden_layers": [32, 16],
        "activation": "gelu",
        "dropout": 0.2,
        "feature_groups": ["returns", "volume"],
    }
    result = asyncio.run(autopilot_save(AutopilotBody(spec=spec)))
    assert result["ok"] is True
    assert result["spec"]["hidden_layers"] == [32, 16]

    state = asyncio.run(autopilot_state())
    assert state["spec"]["output_mode"] == "ternary"
    assert state["spec"]["activation"] == "gelu"
    assert state["spec"]["feature_groups"] == ["returns", "volume"]


def test_autopilot_endpoint_rejects_invalid_spec():
    import asyncio

    import pytest
    from fastapi import HTTPException

    from app.api.ai import AutopilotBody, autopilot_save

    with pytest.raises(HTTPException) as exc:
        asyncio.run(autopilot_save(AutopilotBody(spec={"feature_groups": ["yok"]})))
    assert exc.value.status_code in (400, 422)


def test_autopilot_rejects_empty_feature_groups():
    import asyncio

    import pytest
    from fastapi import HTTPException

    from app.api.ai import AutopilotBody, autopilot_save

    with pytest.raises(HTTPException) as exc:
        asyncio.run(autopilot_save(AutopilotBody(spec={"feature_groups": []})))
    assert exc.value.status_code == 400
