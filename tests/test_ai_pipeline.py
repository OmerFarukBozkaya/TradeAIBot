"""AI zaman serisi hattı: nedensellik, etiketler ve uçtan uca eğitim."""

from __future__ import annotations

import numpy as np

from app.ai import artifacts
from app.ai.features import build_features
from app.ai.labels import build_forward_labels
from app.ai.model import choose_threshold, fit_classifier, predict_positive
from app.ai.trainer import train_model


def _synthetic(n: int = 4000, seed: int = 7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    data = {
        "open": (close * (1 + rng.normal(0, 0.0005, n))).tolist(),
        "high": (close * (1 + abs(rng.normal(0, 0.003, n)))).tolist(),
        "low": (close * (1 - abs(rng.normal(0, 0.003, n)))).tolist(),
        "close": close.tolist(),
        "volume_usdt": rng.lognormal(10, 1, n).tolist(),
        "opendate": (np.arange(n) * 3_600_000).tolist(),
    }
    return data, close


def test_features_are_causal():
    data, _ = _synthetic(600)
    base = build_features(data)["X"]
    # 300. mumdan SONRAKİ tüm fiyatları değiştir. 300'e kadar olan
    # özellikler değişmemeli; aksi halde gelecekten veri sızıyor demektir.
    mutated = {k: list(v) for k, v in data.items()}
    for key in ("open", "high", "low", "close"):
        arr = np.asarray(mutated[key], dtype=float)
        arr[301:] = arr[301:] * 1.5
        mutated[key] = arr.tolist()
    changed = build_features(mutated)["X"]
    assert np.allclose(base[:301], changed[:301], equal_nan=True)


def test_forward_labels_leave_tail_unknown():
    data, close = _synthetic(500)
    labels = build_forward_labels(close, data["high"], data["low"], horizon=10, target_move=0.01, stop_move=0.01)
    assert labels["buy"][-10:].tolist() == [-1] * 10
    assert labels["sell"][-10:].tolist() == [-1] * 10
    assert labels["buy"][:100].max() in (0, 1)


def test_threshold_selection_and_model():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(1000, 4))
    y = (X[:, 0] + rng.normal(0, 0.5, 1000) > 0.8).astype(int)
    model = fit_classifier(X[:700], y[:700])
    p = predict_positive(model, X[700:])
    thr, metrics = choose_threshold(y[700:], p, min_precision=0.2)
    assert 0.35 <= thr <= 0.95
    assert metrics["support"] == 300
    assert 0 <= metrics["precision"] <= 1


def test_training_pipeline_saves_candidate(tmp_path, monkeypatch):
    data, _ = _synthetic(4000, seed=11)
    meta = {
        "source": "synthetic",
        "rows": len(data["close"]),
        "coin": "TESTUSDT",
        "period": "1h",
        "start": data["opendate"][0],
        "end": data["opendate"][-1],
    }
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "ai_models")
    monkeypatch.setattr("app.ai.trainer.load_market_data", lambda *a, **k: (data, meta))
    result = train_model(
        {
            "name": "pytest model",
            "coin": "TESTUSDT",
            "period": "1h",
            "limit": len(data["close"]),
            "source": "synthetic",
            "horizon": 10,
            "target_move": 0.01,
            "stop_move": 0.01,
            "walk_forward": False,
            "use_feedback": False,
        }
    )
    manifest = result["model"]
    report = result["report"]
    assert manifest["status"] == "candidate"
    assert report["split"]["train"]["rows"] > 0
    assert report["split"]["validation"]["rows"] > 0
    assert report["split"]["test"]["rows"] > 0
    # Varsayılan hedef Local_Min_Max: embargo en az pivot penceresi kadar olmalı.
    assert report["label"]["embargo_bars"] == int(report["config"]["extreme_window"]) + 2
    assert report["test"]["trading"]["trade_count"] >= 0
    assert (tmp_path / "ai_models" / manifest["id"] / "model.pkl").exists()
