"""Bot işlem analizi: tur bazında K/Z, tutma süresi, toplamlar."""

from __future__ import annotations

import asyncio

import pytest

from app import db
from app.api import trades as trades_api


def _trade(bot_id, side, qty, price, fee, when, reason="sinyal", coin="BTCUSDT"):
    db.execute(
        "INSERT INTO trades(bot_id,run_id,coin,side,quantity,price,fee,order_id,client_order_id,mode,reason,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (bot_id, 1, coin, side, qty, price, fee, None, None, "paper", reason, None, when),
    )


def test_round_trip_pnl_and_hold_time():
    bot = "bot_an_1"
    _trade(bot, "BUY", 1.0, 100.0, 0.10, "2026-01-01T10:00:00+00:00")
    _trade(bot, "SELL", 1.0, 110.0, 0.11, "2026-01-01T13:30:00+00:00")
    result = trades_api.pair_round_trips(
        db.rows("SELECT * FROM trades WHERE bot_id=? ORDER BY created_at", (bot,))
    )
    summary = result["summary"]
    assert summary["closed_trades"] == 1
    assert summary["wins"] == 1
    assert summary["win_rate"] == 100.0
    trade = result["trades"][0]
    # Maliyet 100 + 0.10 = 100.10, gelir 110 − 0.11 = 109.89
    assert trade["pnl_money"] == pytest.approx(9.79, abs=1e-6)
    assert trade["pnl_pct"] == pytest.approx(9.78, abs=0.02)
    assert trade["hold_seconds"] == 3 * 3600 + 30 * 60
    assert summary["pnl_money"] == pytest.approx(9.79, abs=1e-6)


def test_partial_sells_split_one_entry():
    bot = "bot_an_2"
    _trade(bot, "BUY", 2.0, 100.0, 0.20, "2026-01-01T00:00:00+00:00")
    _trade(bot, "SELL", 1.0, 120.0, 0.12, "2026-01-01T01:00:00+00:00")
    _trade(bot, "SELL", 1.0, 80.0, 0.08, "2026-01-01T02:00:00+00:00")
    result = trades_api.pair_round_trips(
        db.rows("SELECT * FROM trades WHERE bot_id=? ORDER BY created_at", (bot,))
    )
    assert result["summary"]["closed_trades"] == 2
    assert result["summary"]["wins"] == 1
    assert result["summary"]["losses"] == 1
    # İlk satış kârlı, ikincisi zararlı.
    trades = sorted(result["trades"], key=lambda t: t["exit_time"])
    assert trades[0]["pnl_money"] > 0
    assert trades[1]["pnl_money"] < 0
    # Net toplam: (120-0.12) + (80-0.08) − (200+0.20) = -0.40
    assert result["summary"]["pnl_money"] == pytest.approx(-0.40, abs=1e-6)


def test_open_lot_reported_separately():
    bot = "bot_an_3"
    _trade(bot, "BUY", 1.0, 100.0, 0.10, "2026-01-01T00:00:00+00:00")
    result = trades_api.pair_round_trips(
        db.rows("SELECT * FROM trades WHERE bot_id=? ORDER BY created_at", (bot,))
    )
    assert result["summary"]["closed_trades"] == 0
    assert result["summary"]["open_positions"] == 1
    assert result["open_lots"][0]["coin"] == "BTCUSDT"
    assert result["open_lots"][0]["invested"] == pytest.approx(100.0)


def test_coin_and_reason_breakdown():
    bot = "bot_an_4"
    _trade(bot, "BUY", 1.0, 100.0, 0.0, "2026-01-01T00:00:00+00:00", coin="AAAUSDT")
    _trade(bot, "SELL", 1.0, 110.0, 0.0, "2026-01-01T01:00:00+00:00", reason="stop", coin="AAAUSDT")
    _trade(bot, "BUY", 1.0, 100.0, 0.0, "2026-01-02T00:00:00+00:00", coin="BBBUSDT")
    _trade(bot, "SELL", 1.0, 90.0, 0.0, "2026-01-02T05:00:00+00:00", reason="signal", coin="BBBUSDT")
    result = trades_api.pair_round_trips(
        db.rows("SELECT * FROM trades WHERE bot_id=? ORDER BY created_at", (bot,))
    )
    coins = {c["coin"]: c for c in result["by_coin"]}
    assert coins["AAAUSDT"]["pnl_money"] == pytest.approx(10.0)
    assert coins["BBBUSDT"]["pnl_money"] == pytest.approx(-10.0)
    reasons = {r["reason"]: r for r in result["by_exit_reason"]}
    assert set(reasons) == {"stop", "signal"}
    assert result["summary"]["pnl_money"] == pytest.approx(0.0)


def test_analysis_endpoint_shape():
    bot = "bot_an_5"
    _trade(bot, "BUY", 1.0, 100.0, 0.10, "2026-01-01T10:00:00+00:00")
    _trade(bot, "SELL", 1.0, 105.0, 0.10, "2026-01-01T12:00:00+00:00")
    data = asyncio.run(trades_api.bot_trade_analysis(bot, 2000))
    assert data["bot_id"] == bot
    assert data["summary"]["closed_trades"] == 1
    assert data["summary"]["fees"] == pytest.approx(0.20, abs=1e-9)
    assert data["series"]
    assert data["orders"] == 2


def test_unmatched_sell_is_not_counted_as_profit():
    bot = "bot_an_6"
    _trade(bot, "SELL", 1.0, 100.0, 0.10, "2026-01-01T10:00:00+00:00", reason="manuel")
    result = trades_api.pair_round_trips(
        db.rows("SELECT * FROM trades WHERE bot_id=? ORDER BY created_at", (bot,))
    )
    assert result["summary"]["closed_trades"] == 0
    assert result["summary"]["pnl_money"] == 0.0
    assert result["unmatched_sells"]
