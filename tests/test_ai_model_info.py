"""AI model metriklerinde katman alanının tipi (Transformer/MLP çakışması)."""

from __future__ import annotations

import numpy as np

from app.ai import artifacts
from app.ai.model import build_sequence_model
from app.ai.trainer import _layers_metric, _model_info


def test_layers_metric_normalizes_scalars():
    assert _layers_metric([64, 32]) == [64, 32]
    assert _layers_metric((32, 16)) == [32, 16]
    # Eski Transformer kayıtlarında blok sayısı (int) yazılıyordu.
    assert _layers_metric(1) is None
    assert _layers_metric("1") is None
    assert _layers_metric(None) is None
    assert _layers_metric([]) is None
    assert _layers_metric(["64", "x", 32]) == [64, 32]


def test_transformer_info_reports_depth_not_layers():
    model = build_sequence_model(
        {"engine": "transformer", "trans_dim": 16, "trans_heads": 2, "trans_layers": 2},
        6,
        seed=1,
    )
    model.params = model._seed_params()
    info = model.info()
    assert info["type"] == "Transformer"
    assert info["depth"] == 2
    assert "layers" not in info, "layers yalnızca MLP gizli katman listesi için"
    assert info["heads"] == 2


def test_lstm_info_has_no_layers_key():
    model = build_sequence_model({"engine": "lstm", "lstm_hidden": 12}, 6, seed=1)
    model._init_params()
    info = model.info()
    assert info["type"] == "LSTM"
    assert "layers" not in info
    assert info["hidden"] == 12


def test_model_info_for_mlp_lists_hidden_layers(tmp_path, monkeypatch):
    from app.ai.model import fit_model

    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    rng = np.random.default_rng(3)
    X = rng.normal(size=(200, 5))
    y = (X[:, 0] > 0).astype(int)
    model = fit_model(
        {"engine": "mlp", "hidden_layers": [16, 8], "epochs": 12, "patience": 5},
        "binary", X, y,
    )
    info = _model_info({"buy_model": model}, ["a", "b", "c", "d", "e"])
    item = info["models"][0]
    assert item["layers"] == [16, 8]
    assert _layers_metric(item["layers"]) == [16, 8]
