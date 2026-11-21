"""Canlı/paper motorun çıkış kuralları: stop, kâr al, kısmi kâr, breakeven.

Backtest ile aynı `app.risk` fonksiyonları kullanıldığı için burada motorun
seviyeleri gerçekten uyguladığı doğrulanır.
"""

from __future__ import annotations

import pytest

from app import db
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _definition():
    return {
        "name": "Çıkış testi",
        "risk": {},
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "gt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "lt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
    }


def make_engine(monkeypatch, risk, position=None):
    from app.engine import TradingEngine

    created = _definition()
    created["risk"] = risk
    from app.strategies.service import create_custom

    item = create_custom(created)
    engine = TradingEngine(
        "bot_exit",
        {
            "period": "1h",
            "strategies": [{"type": "custom", "id": item["id"]}],
            "cash": 100,
            "risk": risk,
        },
        "paper",
    )
    engine.state = {
        "bot_id": "bot_exit",
        "cash": 50.0,
        "initial_cash": 100.0,
        "position": position
        or {
            "coin": "BTCUSDT",
            "quantity": 0.5,
            "entry_price": 100.0,
            "highest_price": 100.0,
            "atr": 2.0,
            "candles": 0,
            "strategy_id": item["id"],
            "strategy_version": item["version"],
        },
        "total_realized_pnl": 0.0,
        "trade_count": 1,
        "candle_seq": 5,
    }
    monkeypatch.setattr(engine, "_save_state", lambda: None)
    monkeypatch.setattr(engine, "_log", lambda *a, **k: None)
    monkeypatch.setattr("app.engine.notifier.send", lambda *a, **k: None)
    return engine


def _data(close, high=None, low=None):
    close = list(close)
    return {
        "open": close,
        "high": high or close,
        "low": low or close,
        "close": close,
        "opendate": [i * 3_600_000 for i in range(len(close))],
    }


def _patch_data(monkeypatch, engine, data):
    monkeypatch.setattr(engine, "_data", lambda coin: data)


def test_take_profit_exits_at_level(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, {"take_profit_pct": 5})
    _patch_data(monkeypatch, engine, _data([106.0], [108.0], [104.0]))
    engine._manage_position()
    assert engine.state["position"] is None
    # paper: seviyeden çıkış + kayma (%0,1 varsayılan)
    trades = db.rows("SELECT side, reason, price FROM trades WHERE bot_id='bot_exit'")
    assert trades[-1]["side"] == "SELL"
    assert trades[-1]["reason"] == "take-profit"
    assert trades[-1]["price"] == pytest.approx(105.0 * (1 - engine.slippage))
    assert engine.state["exit_reasons"]["take-profit"] == 1


def test_stop_exits_at_stop_level(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, {"stop_atr": 2})
    data = _data([95.0], [100.0], [94.0])
    data["open"] = [100.0]  # mum stopun üstünde açıldı, sonra düştü
    _patch_data(monkeypatch, engine, data)
    engine._manage_position()
    assert engine.state["position"] is None
    trades = db.rows("SELECT reason, price FROM trades WHERE bot_id='bot_exit'")
    assert trades[-1]["reason"] == "stop"
    assert trades[-1]["price"] == pytest.approx(96.0 * (1 - engine.slippage))


def test_stop_gap_fills_at_open(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, {"stop_atr": 2})
    data = _data([90.0], [92.0], [89.0])
    data["open"] = [91.0]  # stopun (96) altında açıldı → 91'den çıkılır
    _patch_data(monkeypatch, engine, data)
    engine._manage_position()
    trades = db.rows("SELECT reason, price FROM trades WHERE bot_id='bot_exit'")
    assert trades[-1]["reason"] == "stop"
    assert trades[-1]["price"] == pytest.approx(91.0 * (1 - engine.slippage))


def test_partial_take_profit_keeps_position_and_moves_stop(temp_db, monkeypatch):
    engine = make_engine(
        monkeypatch,
        {"partial_tp_pct": 4, "partial_tp_fraction": 0.5, "stop_atr": 5},
    )
    _patch_data(monkeypatch, engine, _data([104.0], [105.0], [103.0]))
    engine._manage_position()
    position = engine.state["position"]
    assert position is not None
    assert position["quantity"] == pytest.approx(0.25)
    assert position["partial_taken"] is True
    assert position["stop_floor"] == 100.0
    # stop girişe çekildi (breakeven)
    assert position["stop_price"] == pytest.approx(100.0)
    trades = db.rows("SELECT reason, quantity FROM trades WHERE bot_id='bot_exit'")
    assert trades[-1]["reason"] == "take-profit-partial"
    assert trades[-1]["quantity"] == pytest.approx(0.25)


def test_breakeven_stop_hit_after_profit(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, {"stop_atr": 5, "breakeven_pct": 3})
    engine.state["position"]["highest_price"] = 104.0
    _patch_data(monkeypatch, engine, _data([99.0], [104.0], [99.0]))
    engine._manage_position()
    assert engine.state["position"] is None
    trades = db.rows("SELECT reason FROM trades WHERE bot_id='bot_exit'")
    assert trades[-1]["reason"] == "breakeven"


def test_take_profit_can_be_disabled(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, {"take_profit": False, "take_profit_pct": 5})
    _patch_data(monkeypatch, engine, _data([106.0], [108.0], [104.0]))
    engine._manage_position()
    assert engine.state["position"] is not None
    assert engine.state["position"]["take_profit_price"] is None
