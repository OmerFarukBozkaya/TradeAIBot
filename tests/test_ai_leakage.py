"""Sızıntı korumaları, sınıf dengeleme ve uzun eğitim davranışı."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import artifacts
from app.ai.nn import MLP
from app.ai.trainer import _class_balance_weights, train_model


def _synthetic(n=5000, seed=17):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    return {
        "open": close.tolist(),
        "high": high.tolist(),
        "low": low.tolist(),
        "close": close.tolist(),
        "volume_usdt": rng.lognormal(10, 1, n).tolist(),
        "opendate": (np.arange(n) * 3_600_000).tolist(),
    }


@pytest.fixture()
def trained(tmp_path, monkeypatch):
    data = _synthetic()
    meta = {
        "source": "synthetic", "rows": len(data["close"]), "coin": "TESTLEAK",
        "period": "1h", "start": data["opendate"][0], "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    result = train_model(
        {
            "name": "leak", "coin": "TESTLEAK", "period": "1h",
            "limit": len(data["close"]), "source": "synthetic",
            "walk_forward": True, "folds": 3, "use_feedback": False,
            "refine": True, "iterations": 2, "patience": 1, "min_trades": 2,
            "extreme_window": 20, "horizon": 12,
            "spec": {
                "engine": "mlp", "output_mode": "dual_binary",
                "hidden_layers": [16, 8], "epochs": 30, "patience": 8,
                "feature_groups": ["returns", "range_position", "local_extremes"],
            },
        }
    )
    return result


def test_embargo_covers_extreme_window_not_horizon(trained):
    """Local_Min_Max etiketi pencere kadar ileri bakar; embargo onu kapsamalı."""
    report = trained["report"]
    assert int(report["config"]["extreme_window"]) == 20
    assert report["label"]["embargo_bars"] == 22  # 20 + 2


def test_splits_are_chronological_and_disjoint(trained):
    split = trained["report"]["split"]
    assert split["train"]["end"] < split["validation"]["start"]
    assert split["validation"]["end"] < split["test"]["start"]


def test_walk_forward_never_touches_test_period(trained):
    """Walk-forward yalnızca öğrenme+validation bölgesinde kalmalı."""
    report = trained["report"]
    test_start = report["split"]["test"]["start"]
    folds = [f for f in (report.get("walk_forward") or []) if isinstance(f, dict)]
    assert folds, "en az bir kat olmalı"
    for fold in folds:
        assert fold.get("test_start"), "kat tarihi raporlanmalı"
        assert fold["test_start"] < test_start, "test dönemi çapraz doğrulamaya girmemeli"


def test_class_balance_weights_boost_positives():
    y = np.array([0] * 95 + [1] * 5)
    w = np.ones(len(y))
    out = _class_balance_weights(y, w, 0.6)
    assert out[y == 1].mean() > out[y == 0].mean() * 2
    # Ağırlık ortalaması 1'e çekilir: öğrenme hızı ölçeklenmez.
    assert abs(float(out.mean()) - 1.0) < 1e-6


def test_class_balance_is_safe_on_degenerate_labels():
    y = np.zeros(50)
    w = np.ones(50)
    assert np.allclose(_class_balance_weights(y, w, 0.6), w)
    assert np.allclose(_class_balance_weights(np.ones(50), w, 0.6), w)


def test_class_balance_off_keeps_weights():
    y = np.array([0] * 90 + [1] * 10)
    w = np.ones(len(y))
    assert np.allclose(_class_balance_weights(y, w, 0.0), w)


def test_training_reports_class_balance_and_epochs(trained):
    report = trained["report"]
    assert float(report["config"]["class_balance"]) > 0
    # Model bilgisi gerçek epoch sayısını ve erken durmayı raporlamalı.
    model = (report.get("model") or {}).get("models") or []
    assert model
    info = model[0]
    assert int(info.get("epochs_run") or 0) >= 1
    assert int(info.get("best_epoch") or 0) <= int(info.get("epochs_run") or 0)


def test_mlp_uses_longer_training_with_small_min_delta():
    """Küçük min_delta daha uzun eğitime izin verir; sabır yine sınırlar."""
    rng = np.random.default_rng(3)
    X = rng.normal(size=(600, 6))
    y = (X[:, 0] + X[:, 1] * 0.5 > 0).astype(int)
    model = MLP(
        hidden_layers=[8], epochs=60, patience=50, min_delta=1e-6,
        learning_rate=0.01, dropout=0.0, random_state=1,
    )
    model.fit(X[:400], y[:400], X_val=X[400:], y_val=y[400:])
    assert len(model.history) > 5
    assert model.best_epoch >= 1
    assert model.best_val_loss is not None


def test_mlp_early_stops_on_plateau():
    """Öğrenilecek sinyal yoksa erken durma devreye girer."""
    rng = np.random.default_rng(4)
    X = rng.normal(size=(600, 6))
    y = rng.integers(0, 2, size=600)
    model = MLP(
        hidden_layers=[8], epochs=200, patience=3, min_delta=1e-3,
        learning_rate=0.01, dropout=0.0, random_state=2,
    )
    model.fit(X[:400], y[:400], X_val=X[400:], y_val=y[400:])
    assert len(model.history) < 200
