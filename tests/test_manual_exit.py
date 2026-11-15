"""Canlı modda manuel (harici) satışın algılanması."""

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
        "name": "Manuel test",
        "risk": {"stop_atr": 35, "cooldown": 10},
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


class FakeClient:
    def __init__(self, balances):
        self._balances = balances

    def get_account(self):
        return {"balances": self._balances}


class FakeBinance:
    def __init__(self, balances):
        self.client = FakeClient(balances)


def make_engine(monkeypatch, balances, position, cash=0.0, mode="live"):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(_definition())
    engine = TradingEngine(
        "bot_manual",
        {"period": "1h", "strategies": [{"type": "custom", "id": created["id"]}], "cash": 100},
        mode,
    )
    engine.binance = FakeBinance(balances)
    engine.state = {
        "bot_id": "bot_manual",
        "cash": cash,
        "initial_cash": 100.0,
        "position": position,
        "total_realized_pnl": 0.0,
        "trade_count": 1,
        "candle_seq": 5,
    }
    engine.state["position"]["last_price"] = 120.0
    monkeypatch.setattr(engine, "_save_state", lambda: None)
    monkeypatch.setattr(engine, "_log", lambda *a, **k: None)
    monkeypatch.setattr("app.engine.notifier.send", lambda *a, **k: None)
    return engine


def _bal(asset, free=0.0, locked=0.0):
    return {"asset": asset, "free": str(free), "locked": str(locked)}


def test_manual_full_sell_closes_position(temp_db, monkeypatch):
    # Kullanıcı 0.5 BTC'yi elle satmış: coin bakiyesi 0, nakit 50 → 110 olmuş.
    engine = make_engine(
        monkeypatch,
        [_bal("BTC", 0, 0), _bal("USDT", 110)],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=50.0,
    )
    changes = engine._sync_live_position()
    assert changes and "manuel" in changes[0]
    assert engine.state["position"] is None
    assert engine.state["cash"] == 110.0            # borsadaki gerçek nakit
    assert engine.state["total_realized_pnl"] == 10.0  # (120 - 100) * 0.5
    trades = [t for t in db.rows("SELECT * FROM trades WHERE bot_id='bot_manual'")]
    assert len(trades) == 1
    assert trades[0]["reason"] == "manuel"
    assert trades[0]["price"] == 120.0
    assert trades[0]["pnl_pct"] == pytest.approx(20.0)
    # cooldown ayarlanır (hemen yeniden giriş yok)
    assert engine.state["cooldown_until"] == 15


def test_manual_partial_sell_updates_quantity(temp_db, monkeypatch):
    # 0.5'in 0.3'ü elle satılmış, 0.2 kalmış; nakit 50 → 86
    engine = make_engine(
        monkeypatch,
        [_bal("BTC", 0.2, 0), _bal("USDT", 86)],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=50.0,
    )
    engine._sync_live_position()
    assert engine.state["position"]["quantity"] == pytest.approx(0.2)
    trades = [t for t in db.rows("SELECT * FROM trades WHERE bot_id='bot_manual'")]
    assert len(trades) == 1
    assert trades[0]["reason"] == "manuel"
    assert trades[0]["quantity"] == pytest.approx(0.3)
    assert trades[0]["price"] == pytest.approx(120.0)  # 36 USDT / 0.3


def test_external_buy_updates_quantity(temp_db, monkeypatch):
    engine = make_engine(
        monkeypatch,
        [_bal("BTC", 0.7, 0), _bal("USDT", 0)],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=0.0,
    )
    engine._sync_live_position()
    assert engine.state["position"]["quantity"] == pytest.approx(0.7)
    assert not [t for t in db.rows("SELECT * FROM trades WHERE bot_id='bot_manual'")]


def test_dust_remaining_counts_as_full_sell(temp_db, monkeypatch):
    engine = make_engine(
        monkeypatch,
        [_bal("BTC", 0.0001, 0), _bal("USDT", 60)],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=0.0,
    )
    engine._sync_live_position()
    assert engine.state["position"] is None


def test_paper_mode_is_untouched(temp_db, monkeypatch):
    engine = make_engine(
        monkeypatch,
        [_bal("BTC", 0, 0), _bal("USDT", 160)],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=0.0,
        mode="paper",
    )
    assert engine._sync_live_position() == []
    assert engine.state["position"] is not None


def test_balance_read_failure_keeps_position(temp_db, monkeypatch):
    engine = make_engine(
        monkeypatch,
        [],
        {"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "highest_price": 120.0},
        cash=0.0,
    )

    def boom():
        raise RuntimeError("api yok")

    engine.binance.client.get_account = boom
    assert engine._sync_live_position() == []
    assert engine.state["position"] is not None


def test_asset_symbol_parsing():
    from app.engine import TradingEngine

    assert TradingEngine._asset_of("BTCUSDT") == "BTC"
    assert TradingEngine._asset_of("XRPUSDT") == "XRP"
    assert TradingEngine._asset_of("ETHBTC") == "ETH"
    assert TradingEngine._asset_of("USDT") == "USDT"
