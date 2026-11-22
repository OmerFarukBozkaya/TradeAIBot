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


def test_trade_chart_matches_entry_and_returns_candles(monkeypatch):
    bot = "bot_chart_1"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot, "Grafik", "trade", "paper", "15m", '{"period": "15m"}',
         "stopped", 1, "2026-01-01T09:00:00+00:00", "2026-01-01T09:00:00+00:00"),
    )
    _trade(bot, "BUY", 2.0, 100.0, 0.2, "2026-01-01T10:00:00+00:00")
    _trade(bot, "SELL", 2.0, 108.0, 0.2, "2026-01-01T11:00:00+00:00", reason="take-profit")
    sell_id = db.row("SELECT id FROM trades WHERE side='SELL' AND bot_id=?", (bot,))["id"]

    def fake_history(symbol, period, limit, start=None, end=None):
        base = 1_767_265_200_000  # 2026-01-01T10:00:00Z civarı
        step = 15 * 60 * 1000
        count = 8
        data = {
            "opendate": [base + i * step for i in range(count)],
            "open": [100.0] * count,
            "high": [109.0] * count,
            "low": [99.0] * count,
            "close": [101.0 + i for i in range(count)],
            "volume_usdt": [10.0] * count,
        }
        return data, {"rows": count}

    monkeypatch.setattr("app.market_data.load_history", fake_history)
    result = trades_api.trade_chart(sell_id)

    assert result["coin"] == "BTCUSDT"
    assert result["entry"]["price"] == pytest.approx(100.0)
    assert result["exit"]["price"] == pytest.approx(108.0)
    assert result["exit"]["reason"] == "take-profit"
    assert result["pnl_pct"] == pytest.approx(8.0)
    # 1 saatlik işlem: giriş/çıkış ayrı mumlarda görünsün diye ince periyot.
    assert result["period"] in {"1m", "3m", "5m"}
    assert len(result["candles"]) == 8
    assert result["error"] is None
    assert result["after_exit"]["bars"] >= 1
    assert result["after_exit"]["high_pct"] == pytest.approx(round((109.0 / 108.0 - 1) * 100, 3))
    assert result["after_exit"]["low_pct"] == pytest.approx(round((99.0 / 108.0 - 1) * 100, 3))


def test_trade_chart_returns_info_when_history_fails(monkeypatch):
    bot = "bot_chart_2"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot, "Grafik 2", "trade", "paper", "1h", '{"period": "1h"}',
         "stopped", 1, "2026-01-01T09:00:00+00:00", "2026-01-01T09:00:00+00:00"),
    )
    _trade(bot, "BUY", 1.0, 50.0, 0.0, "2026-01-01T10:00:00+00:00")
    buy_id = db.row("SELECT id FROM trades WHERE side='BUY' AND bot_id=?", (bot,))["id"]

    def broken_history(*args, **kwargs):
        raise RuntimeError("veri yok")

    monkeypatch.setattr("app.market_data.load_history", broken_history)
    result = trades_api.trade_chart(buy_id)

    assert result["coin"] == "BTCUSDT"
    assert result["entry"]["price"] == pytest.approx(50.0)
    assert result["candles"] == []
    assert "veri yok" in result["error"]


def test_after_exit_skipped_when_price_mismatches_candles(monkeypatch):
    """Fiyat mum verisiyle uyuşmuyorsa satış sonrası yüzdeler üretilmez."""
    bot = "bot_chart_3"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot, "Grafik 3", "trade", "paper", "1h", '{"period": "1h"}',
         "stopped", 1, "2026-01-01T09:00:00+00:00", "2026-01-01T09:00:00+00:00"),
    )
    _trade(bot, "BUY", 1.0, 100.0, 0.0, "2026-01-01T10:00:00+00:00")
    _trade(bot, "SELL", 1.0, 1000.0, 0.0, "2026-01-01T11:00:00+00:00")
    sell_id = db.row("SELECT id FROM trades WHERE side='SELL' AND bot_id=?", (bot,))["id"]

    def fake_history(symbol, period, limit, start=None, end=None):
        base = 1_767_265_200_000
        step = 60 * 60 * 1000
        return {
            "opendate": [base + i * step for i in range(6)],
            "open": [100.0] * 6, "high": [105.0] * 6, "low": [95.0] * 6,
            "close": [101.0] * 6, "volume_usdt": [1.0] * 6,
        }, {"rows": 6}

    monkeypatch.setattr("app.market_data.load_history", fake_history)
    result = trades_api.trade_chart(sell_id)

    assert result["after_exit"]["bars"] == 0
    assert result["after_exit"]["high_pct"] is None
    # İşlem bilgisi yine gelir.
    assert result["exit"]["price"] == pytest.approx(1000.0)


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


def test_pair_history_keeps_bots_apart():
    """Aynı coin iki botta işlem görse de turlar birbirine karışmaz."""
    rows = [
        {"id": 1, "bot_id": "bot_a", "bot_name": "Alfa", "coin": "BTCUSDT",
         "side": "BUY", "quantity": 1.0, "price": 100.0, "fee": 0.1,
         "created_at": "2026-01-01T00:00:00+00:00", "mode": "paper", "reason": "sinyal"},
        {"id": 2, "bot_id": "bot_b", "bot_name": "Beta", "coin": "BTCUSDT",
         "side": "BUY", "quantity": 1.0, "price": 200.0, "fee": 0.2,
         "created_at": "2026-01-01T00:30:00+00:00", "mode": "paper", "reason": "sinyal"},
        {"id": 3, "bot_id": "bot_a", "bot_name": "Alfa", "coin": "BTCUSDT",
         "side": "SELL", "quantity": 1.0, "price": 110.0, "fee": 0.11,
         "created_at": "2026-01-01T01:00:00+00:00", "mode": "paper", "reason": "stop"},
    ]

    result = trades_api.pair_history(rows)

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["bot_id"] == "bot_a"
    assert trade["bot_name"] == "Alfa"
    assert trade["entry_price"] == pytest.approx(100.0)
    assert trade["exit_price"] == pytest.approx(110.0)
    assert trade["exit_id"] == 3
    assert trade["exit_reason"] == "stop"
    # Beta'nın alımı eşleşmedi: açık pozisyon olarak duruyor.
    assert len(result["open"]) == 1
    assert result["open"][0]["bot_id"] == "bot_b"


def test_pair_history_reports_unmatched_sell():
    """Alışı pencerede olmayan satış kaybolmaz; K/Z hesaplanmaz."""
    rows = [
        {"id": 7, "bot_id": "bot_x", "bot_name": "X", "coin": "ETHUSDT",
         "side": "SELL", "quantity": 2.0, "price": 50.0, "fee": 0.05,
         "created_at": "2026-01-02T00:00:00+00:00", "mode": "live", "reason": "manuel"},
    ]

    result = trades_api.pair_history(rows)

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["unmatched"] is True
    assert trade["entry_price"] is None
    assert trade["pnl_money"] is None
    assert trade["exit_price"] == pytest.approx(50.0)


def test_trade_history_endpoint_returns_bot_name(monkeypatch):
    bot = "bot_hist_1"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot, "Momentum Botu", "trade", "paper", "1h", "{}", "stopped", 1,
         "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    _trade(bot, "BUY", 5.0, 0.2, 0.001, "2026-01-01T00:00:00+00:00", coin="DODOUSDT")
    _trade(bot, "SELL", 5.0, 0.25, 0.001, "2026-01-01T02:00:00+00:00",
           reason="take-profit", coin="DODOUSDT")

    result = trades_api.trade_history(limit=2000)

    assert result["orders"] == 2
    trade = result["trades"][0]
    assert trade["bot_name"] == "Momentum Botu"
    assert trade["coin"] == "DODOUSDT"
    assert trade["entry_price"] == pytest.approx(0.2)
    assert trade["exit_price"] == pytest.approx(0.25)
    assert trade["quantity"] == pytest.approx(5.0)
    assert trade["hold_seconds"] == 2 * 3600
    assert trade["pnl_pct"] > 0


def test_trades_endpoint_includes_bot_name():
    bot = "bot_hist_2"
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot, "Scalp Botu", "trade", "paper", "15m", "{}", "stopped", 1,
         "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    _trade(bot, "BUY", 1.0, 10.0, 0.0, "2026-01-01T00:00:00+00:00")

    rows = asyncio.run(trades_api.trades(bot_id=bot, limit=50))

    assert rows[0]["bot_name"] == "Scalp Botu"
    assert rows[0]["bot_id"] == bot


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
