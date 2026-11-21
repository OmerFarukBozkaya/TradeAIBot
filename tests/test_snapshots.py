"""Snapshot (regresyon) sistemi: kayıt, doğrulama, hata raporlama."""

import gzip
import json

import pytest

from app import db, snapshots
from app.paths import paths


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")
    db.init_db()
    yield


def make_data(n=300, seed=4):
    import numpy as np

    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    spread = np.abs(rng.normal(0, 0.003, n)) * close
    return {
        "open": np.concatenate([[close[0]], close[:-1]]).tolist(),
        "high": (close + spread).tolist(),
        "low": (close - spread).tolist(),
        "close": close.tolist(),
        "volume_coin": rng.uniform(1, 5, n).tolist(),
        "volume_usdt": (rng.uniform(1, 5, n) * close).tolist(),
        "opendate": [1700000000000 + i * 900000 for i in range(n)],
    }


@pytest.fixture()
def fake_record(monkeypatch):
    """Ağa çıkmadan snapshot üretir (gerçek fiyatlar sentetik)."""
    data = make_data()
    meta = {"requested": 300, "raw_rows": 300, "pages": 0}
    monkeypatch.setattr(snapshots.jr, "_client", lambda: object())
    monkeypatch.setattr(snapshots.jr, "_history", lambda client, coin, period, n: (data, meta))
    return snapshots.record("BTCUSDT", "15m", 300, "test")


def test_record_contains_prices_indicators_strategies(fake_record):
    payload = snapshots.get_snapshot(fake_record["id"])
    assert len(payload["data"]["close"]) == 300
    assert payload["indicators"], "indikatör serileri kaydedilmeli"
    assert payload["strategies"], "strateji sinyalleri kaydedilmeli"
    # Sinyaller mum sayısı kadar '0'/'1'
    sample = next(iter(payload["strategies"].values()))
    assert len(sample["buy"]) == 300
    assert set(sample["buy"]) <= {"0", "1"}
    assert payload["meta"]["price_sha256"]


def test_verify_identical_is_ok(fake_record):
    report = snapshots.verify(fake_record["id"])
    assert report["ok"] is True
    assert report["failure_count"] == 0
    assert report["checked"]["indicators"] > 0
    assert report["checked"]["strategies"] > 0


def test_verify_detects_indicator_drift(fake_record):
    """Kayıttaki bir indikatör değeri bozulursa o indikatör raporlanmalı."""
    path = snapshots._path(fake_record["id"])
    with gzip.open(path, "rb") as fh:
        payload = json.loads(fh.read().decode())
    key = next(k for k in payload["indicators"] if k.startswith("EMA"))
    series = payload["indicators"][key]
    idx = 150
    series[idx] = (series[idx] or 0) + 1.5
    with gzip.open(path, "wb") as fh:
        fh.write(json.dumps(payload).encode())

    report = snapshots.verify(fake_record["id"])
    assert report["ok"] is False
    found = [f for f in report["failures"] if f["type"] == "indicator" and f["name"] == key]
    assert found, report["failures"]
    assert found[0]["first_index"] == idx
    assert found[0]["diffs"] == 1


def test_verify_detects_strategy_signal_drift(fake_record):
    path = snapshots._path(fake_record["id"])
    with gzip.open(path, "rb") as fh:
        payload = json.loads(fh.read().decode())
    key, saved = next(iter(payload["strategies"].items()))
    signals = list(saved["buy"])
    pos = 200
    signals[pos] = "1" if signals[pos] == "0" else "0"
    saved["buy"] = "".join(signals)
    with gzip.open(path, "wb") as fh:
        fh.write(json.dumps(payload).encode())

    report = snapshots.verify(fake_record["id"])
    assert report["ok"] is False
    found = [
        f for f in report["failures"]
        if f["type"] == "strategy" and f.get("side") == "AL"
    ]
    assert found
    assert found[0]["first_index"] == pos
    assert found[0]["name"]


def test_verify_detects_price_tampering(fake_record):
    path = snapshots._path(fake_record["id"])
    with gzip.open(path, "rb") as fh:
        payload = json.loads(fh.read().decode())
    payload["data"]["close"][10] = 1.0
    with gzip.open(path, "wb") as fh:
        fh.write(json.dumps(payload).encode())

    report = snapshots.verify(fake_record["id"])
    assert any(f["type"] == "data" for f in report["failures"])


def test_list_and_delete(fake_record):
    items = snapshots.list_snapshots()
    assert any(i["id"] == fake_record["id"] for i in items)
    assert snapshots.delete_snapshot(fake_record["id"]) is True
    assert snapshots.get_snapshot(fake_record["id"]) is None
    assert snapshots.delete_snapshot(fake_record["id"]) is False


def test_invalid_period_and_id(fake_record):
    # 2h artık geçerli (serbest periyot); geçersiz bir birim hata vermeli.
    with pytest.raises(ValueError):
        snapshots.record("BTCUSDT", "5x", 300)
    with pytest.raises(ValueError):
        snapshots.record("BTCUSDT", "0d", 300)
    with pytest.raises(ValueError):
        snapshots._path("../etc/passwd")


def test_tolerance_controls_comparison(fake_record):
    """Küçük bir sapma tolerans içinde kalırsa fark sayılmaz."""
    path = snapshots._path(fake_record["id"])
    with gzip.open(path, "rb") as fh:
        payload = json.loads(fh.read().decode())
    key = next(k for k in payload["indicators"] if k.startswith("EMA"))
    payload["indicators"][key][100] = (payload["indicators"][key][100] or 0) + 1e-9
    with gzip.open(path, "wb") as fh:
        fh.write(json.dumps(payload).encode())

    assert snapshots.verify(fake_record["id"], tol=1e-6)["ok"] is True
    assert snapshots.verify(fake_record["id"], tol=1e-12)["ok"] is False