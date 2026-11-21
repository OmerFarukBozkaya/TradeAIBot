"""Sabit fiyat veri setleri: ağa çıkmadan tekrar tekrar eğitim."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai import datasets
from app.ai import artifacts


def _market(n=1200, seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    return {
        "open": (close * (1 + rng.normal(0, 0.0005, n))).tolist(),
        "high": (close * (1 + np.abs(rng.normal(0, 0.003, n)))).tolist(),
        "low": (close * (1 - np.abs(rng.normal(0, 0.003, n)))).tolist(),
        "close": close.tolist(),
        "volume_usdt": rng.lognormal(10, 1, n).tolist(),
        "opendate": (np.arange(n) * 3_600_000.0).tolist(),
    }


def test_save_load_and_list(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    data = _market()
    meta = datasets.save(data, coin="BTCUSDT", period="1h", source="binance")
    assert meta["rows"] == 1200
    assert (tmp_path / "datasets" / meta["id"] / "data.npz").exists()

    loaded, loaded_meta = datasets.load(meta["id"])
    assert len(loaded["close"]) == 1200
    np.testing.assert_allclose(loaded["close"], data["close"])
    assert loaded_meta["coin"] == "BTCUSDT"

    items = datasets.list_datasets()
    assert len(items) == 1
    assert items[0]["id"] == meta["id"]


def test_latest_picks_newest_for_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    first = datasets.save(_market(600), coin="ETHUSDT", period="1h")
    second = datasets.save(_market(800), coin="ETHUSDT", period="1h")
    assert datasets.latest("ETHUSDT", "1h")["id"] == second["id"]
    assert datasets.latest("BTCUSDT", "1h") is None
    datasets.delete(first["id"])
    assert len(datasets.list_datasets()) == 1


def test_resolve_uses_snapshot_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    saved = datasets.save(_market(900), coin="BTCUSDT", period="1h")

    def boom(*args, **kwargs):
        raise AssertionError("Ağa çıkılmamalıydı")

    monkeypatch.setattr("app.ai.data.load_market_data", boom)

    data, meta = datasets.resolve("BTCUSDT", "1h", 5000, auto_snapshot=True)
    assert meta["reused"] is True
    assert meta["dataset_id"] == saved["id"]
    assert len(data["close"]) == 900


def test_resolve_pinned_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    old = datasets.save(_market(700), coin="BTCUSDT", period="1h")
    new = datasets.save(_market(800), coin="BTCUSDT", period="1h")

    def boom(*args, **kwargs):
        raise AssertionError("Ağa çıkılmamalıydı")

    monkeypatch.setattr("app.ai.data.load_market_data", boom)
    data, meta = datasets.resolve("BTCUSDT", "1h", 500, dataset_id=old["id"])
    assert meta["pinned"] is True
    assert meta["dataset_id"] == old["id"]
    assert len(data["close"]) == 500  # limit uygulandı
    assert new["id"] != old["id"]


def test_resolve_fetches_and_saves_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    calls = {"n": 0}

    def fake_live(coin, period, limit, source, csv_path):
        calls["n"] += 1
        return _market(1000), {"source": "binance", "rows": 1000, "coin": coin, "period": period}

    monkeypatch.setattr("app.ai.data.load_market_data", fake_live)
    data, meta = datasets.resolve("SOLUSDT", "4h", 500, auto_snapshot=True)
    assert calls["n"] == 1
    assert meta["saved_snapshot"] is True
    assert meta["dataset_id"]

    # İkinci çağrı ağa çıkmamalı.
    data2, meta2 = datasets.resolve("SOLUSDT", "4h", 500, auto_snapshot=True)
    assert calls["n"] == 1
    assert meta2["reused"] is True


def test_resolve_refresh_forces_new_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    datasets.save(_market(1000), coin="BTCUSDT", period="1h")
    calls = {"n": 0}

    def fake_live(coin, period, limit, source, csv_path):
        calls["n"] += 1
        return _market(1100), {"source": "binance", "rows": 1100, "coin": coin, "period": period}

    monkeypatch.setattr("app.ai.data.load_market_data", fake_live)
    _, meta = datasets.resolve("BTCUSDT", "1h", 1000, refresh=True, auto_snapshot=True)
    assert calls["n"] == 1
    assert meta["reused"] is False


def test_training_uses_pinned_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "DATASET_ROOT", tmp_path / "datasets")
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    data = _market(4000)
    saved = datasets.save(data, coin="TESTDS", period="1h")

    def boom(*args, **kwargs):
        raise AssertionError("Eğitim ağa çıkmamalıydı")

    monkeypatch.setattr("app.ai.data.load_market_data", boom)
    from app.ai.trainer import train_model

    result = train_model(
        {
            "name": "ds", "coin": "TESTDS", "period": "1h", "limit": 4000,
            "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
            "walk_forward": False, "use_feedback": False, "refine": False,
            "min_trades": 2, "dataset_id": saved["id"],
            "spec": {
                "engine": "mlp", "output_mode": "dual_binary",
                "hidden_layers": [16], "epochs": 20, "patience": 5,
                "feature_groups": ["returns", "rsi_macd"],
            },
        }
    )
    report = result["report"]
    assert report["data"]["dataset_id"] == saved["id"]
    assert report["data"]["reused"] is True
    assert result["model"]["params"]["dataset_id"] == saved["id"]


def test_training_without_dataset_does_not_touch_network_when_disabled(tmp_path, monkeypatch):
    """auto_snapshot kapalıyken mevcut load_market_data yolu kullanılır."""
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    calls = {"n": 0}

    def fake_live(*args, **kwargs):
        calls["n"] += 1
        return _market(3000), {"source": "synthetic", "rows": 3000, "coin": "X", "period": "1h"}

    monkeypatch.setattr("app.ai.trainer.load_market_data", fake_live)
    from app.ai.trainer import train_model

    result = train_model(
        {
            "name": "live", "coin": "X", "period": "1h", "limit": 3000,
            "source": "synthetic", "horizon": 10, "target_move": 0.01, "stop_move": 0.01,
            "walk_forward": False, "use_feedback": False, "refine": False, "min_trades": 2,
            "auto_snapshot": False,
            "spec": {"hidden_layers": [8], "epochs": 10, "feature_groups": ["returns"]},
        }
    )
    assert calls["n"] == 1
    assert result["report"]["data"]["dataset_id"] is None
