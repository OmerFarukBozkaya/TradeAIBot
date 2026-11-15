"""Stop üst sınırı (max_stop_pct) backtest ve canlı motorda aynı uygulanmalı."""

import pytest

from app import db, job_runner as jr
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _position(entry=100.0, atr=10.0, highest=None):
    return {
        "entry": entry,
        "atr": atr,
        "highest": highest if highest is not None else entry,
    }


def _data(high=101.0, low=99.0, close=100.0):
    return {"high": [high], "low": [low], "close": [close]}


def test_backtest_stop_uncapped():
    # 35×ATR = 70 → stop 30; low 29.5 stopun altında → tetiklenir
    pos = _position(entry=100.0, atr=2.0)
    hit = jr._risk_exit(pos, _data(low=29.5), 0, [], {"stop_atr": 35})
    assert hit is not None and hit[1] == "stop"
    # Stopun üstünde kalan mum tetiklemez
    assert jr._risk_exit(pos, _data(low=31.0), 0, [], {"stop_atr": 35}) is None


def test_backtest_stop_capped_at_pct():
    # 35×2 = 70 → stop 30; tavan %15 → stop 85
    pos = _position(entry=100.0, atr=2.0)
    hit = jr._risk_exit(pos, _data(low=84.0), 0, [], {"stop_atr": 35, "max_stop_pct": 15})
    assert hit is not None
    assert hit[1] == "stop"
    assert hit[0] == pytest.approx(85.0)
    # Tavan olmadan 84 tetiklenmez
    assert jr._risk_exit(pos, _data(low=84.0), 0, [], {"stop_atr": 35}) is None


def test_engine_stop_capped(temp_db, monkeypatch):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(
        {
            "name": "Stop cap",
            "risk": {"stop_atr": 35, "max_stop_pct": 15, "cooldown": 0},
            "buy": {
                "logic": "AND",
                "conditions": [
                    {"left": {"type": "price", "field": "close"}, "op": "gt", "right": {"type": "constant", "value": 0}}
                ],
            },
            "sell": {
                "logic": "OR",
                "conditions": [
                    {"left": {"type": "price", "field": "close"}, "op": "lt", "right": {"type": "constant", "value": 0}}
                ],
            },
        }
    )
    engine = TradingEngine(
        "bot_cap",
        {"period": "1h", "strategies": [{"type": "custom", "id": created["id"]}], "cash": 100},
        "paper",
    )
    assert engine.risk["max_stop_pct"] == 15
    # sembolik hesap: entry 100, atr 2 → stop 85
    entry, atr = 100.0, 2.0
    stop = entry - engine.risk["stop_atr"] * atr
    cap = engine.risk["max_stop_pct"]
    stop = max(stop, entry * (1 - cap / 100))
    assert stop == pytest.approx(85.0)