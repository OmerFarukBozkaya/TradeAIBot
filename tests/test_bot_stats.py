"""Bot kartı: işlem geçmişinden K/Z, çalışma süresi ve manuel satış."""

from __future__ import annotations

import asyncio

import pytest

from app import bot_state, db
from app.api import bots as bots_api


def _state(bot_id, **kwargs):
    payload = {
        "bot_id": bot_id,
        "cash": 100.0,
        "initial_cash": 100.0,
        "position": None,
        "total_realized_pnl": 0.0,
        "trade_count": 0,
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    payload.update(kwargs)
    db.atomic_write_json(bot_state.state_path(bot_id), payload)


def _trade(bot_id, side, qty, price, fee):
    db.execute(
        "INSERT INTO trades(bot_id,run_id,coin,side,quantity,price,fee,order_id,mode,reason,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "run1", "BTCUSDT", side, qty, price, fee, None, "paper", "sinyal", None, db.utcnow()),
    )


def _bot(bot_id, **kwargs):
    row = {
        "id": bot_id,
        "name": "Test",
        "type": "trade",
        "mode": "paper",
        "period": "1h",
        "config_json": '{"strategies": [], "coins": [], "fee": 0.001}',
        "status": "running",
        "auto_restart": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(kwargs)
    return row


def test_total_pnl_uses_trade_history_and_fees(monkeypatch):
    """Kart K/Z'si işlem geçmişinden (komisyon dahil) hesaplanır."""
    from app import live_prices

    monkeypatch.setattr(live_prices, "prices", lambda symbols: {})
    bot_id = "bot_stats_1"
    _state(bot_id)
    _trade(bot_id, "BUY", 1.0, 100.0, 0.1)     # −100.1
    _trade(bot_id, "SELL", 1.0, 110.0, 0.11)   # +109.89
    state = bots_api._serialize(_bot(bot_id))["state"]
    assert state["pnl_source"] == "trades"
    assert state["total_pnl"] == pytest.approx(9.79, abs=1e-6)
    assert state["equity"] == pytest.approx(109.79, abs=1e-6)
    assert state["total_pnl_pct"] == pytest.approx(9.79, abs=1e-6)


def test_open_position_moves_total_pnl(monkeypatch):
    """Açık pozisyon piyasa değeriyle K/Z'ye yansır."""
    from app import live_prices

    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 120.0})
    bot_id = "bot_stats_2"
    _state(
        bot_id,
        position={
            "coin": "BTCUSDT",
            "quantity": 1.0,
            "entry_price": 100.0,
            "last_price": 100.0,
        },
    )
    _trade(bot_id, "BUY", 1.0, 100.0, 0.1)
    state = bots_api._serialize(_bot(bot_id))["state"]
    # equity = 100 − 100.1 + 120 = 119.9 → K/Z = 19.9
    assert state["equity"] == pytest.approx(119.9, abs=1e-6)
    assert state["total_pnl"] == pytest.approx(19.9, abs=1e-6)
    assert state["unrealized_pnl"] == pytest.approx(20.0, abs=1e-6)
    # Gerçekleşen = toplam − anlık (giriş komisyonu burada kalır).
    assert state["total_realized_pnl"] == pytest.approx(-0.1, abs=1e-6)


def test_uptime_is_reported():
    bot_id = "bot_stats_3"
    _state(bot_id, started_at="2020-01-01T00:00:00+00:00")
    state = bots_api._serialize(_bot(bot_id))["state"]
    assert state["uptime_seconds"] > 86400
    assert state["started_at"]


def test_manual_sell_queues_request():
    bot_id = "bot_stats_4"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "Sat", "trade", "paper", "1h", '{"strategies": [], "coins": []}', "running", 1,
         db.utcnow(), db.utcnow()),
    )
    _state(
        bot_id,
        position={"coin": "BTCUSDT", "quantity": 1.0, "entry_price": 100.0, "last_price": 100.0},
    )
    out = asyncio.run(bots_api.sell_position(bot_id, bots_api.SellBody()))
    assert out["ok"] and out["queued"]
    request = bot_state.sell_requested(bot_id)
    assert request is not None
    assert request.get("note") == "panel"
    bot_state.clear_sell(bot_id)


def test_manual_sell_requires_position():
    bot_id = "bot_stats_5"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "Bos", "trade", "paper", "1h", '{"strategies": [], "coins": []}', "running", 1,
         db.utcnow(), db.utcnow()),
    )
    _state(bot_id)
    with pytest.raises(Exception):
        asyncio.run(bots_api.sell_position(bot_id, bots_api.SellBody()))


def test_sell_request_clears_after_handling():
    bot_id = "bot_stats_6"
    bot_state.request_sell(bot_id, note="test")
    assert bot_state.sell_requested(bot_id) is not None
    bot_state.clear_sell(bot_id)
    assert bot_state.sell_requested(bot_id) is None
