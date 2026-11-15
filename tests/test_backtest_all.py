"""Toplu backtest (tüm stratejileri karşılaştır) testleri."""

import pytest

from app import db, job_runner as jr
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def make_data(n=400, start=100.0, step=0.5):
    close = [start + i * step for i in range(n)]
    return {
        "open": close,
        "high": [c * 1.01 for c in close],
        "low": [c * 0.99 for c in close],
        "close": close,
        "volume_coin": [1.0] * n,
        "volume_usdt": [100.0] * n,
        "opendate": [1700000000000 + i * 3600000 for i in range(n)],
    }


def test_backtest_uses_injected_data():
    data = make_data()

    def boom(*args, **kwargs):  # pragma: no cover - çağrılırsa test başarısız
        raise AssertionError("Veri yeniden çekilmemeli")

    original = jr._history
    jr._history = boom
    try:
        result = jr.run_backtest(
            {
                "strategy": {"type": "builtin", "name": "MACD"},
                "coin": "BTCUSDT",
                "period": "1h",
                "_data": data,
                "_history_meta": {"requested": len(data["close"])},
            }
        )
    finally:
        jr._history = original
    assert result["candles"] == len(data["close"])
    assert "total_return_pct" in result["metrics"]


def test_collect_all_specs_includes_builtin_and_custom(temp_db):
    specs = jr.collect_all_specs()
    keys = [item["key"] for item in specs]
    assert len(keys) == len(set(keys))
    assert any(item["kind"] == "builtin" for item in specs)
    assert all({"key", "spec", "name", "kind"} <= set(item) for item in specs)


def test_run_backtest_all_compares_shared_data(temp_db, monkeypatch):
    data = make_data()
    monkeypatch.setattr(jr, "_history", lambda *a, **k: (data, {"requested": len(data["close"])}))
    monkeypatch.setattr(
        jr,
        "collect_all_specs",
        lambda include_archived=False: [
            {
                "key": "builtin:MACD",
                "spec": {"type": "builtin", "name": "MACD"},
                "name": "MACD",
                "motor": "MACD",
                "kind": "builtin",
                "best_timeframe": "4h",
            },
            {
                "key": "builtin:Yok",
                "spec": {"type": "builtin", "name": "Yok_Boyle_Strateji"},
                "name": "Yok Böyle",
                "motor": "Yok",
                "kind": "builtin",
                "best_timeframe": None,
            },
        ],
    )
    result = jr.run_backtest_all({"coin": "BTCUSDT", "period": "1h", "limit": 400, "cash": 100})
    assert result["candles"] == len(data["close"])
    assert len(result["rows"]) == 2
    ok, broken = result["rows"]
    assert ok["error"] is None
    assert ok["key"] == "builtin:MACD"
    assert "return_pct" in ok and "diff" in ok and "buy_hold_pct" in ok
    # Bozuk strateji tabloyu bozmaz; satır hatayı taşır.
    assert broken["error"]
