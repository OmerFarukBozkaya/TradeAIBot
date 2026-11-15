"""Bot kartındaki anlık K/Z ve pozisyon durumu hesapları."""

import pytest

from app import db, live_prices
from app.api import bots as bots_api
from app.paths import paths


def _state(bot_id, **kwargs):
    payload = {
        "bot_id": bot_id,
        "cash": 100.0,
        "initial_cash": 100.0,
        "position": None,
        "total_realized_pnl": 0.0,
        "trade_count": 0,
    }
    payload.update(kwargs)
    db.atomic_write_json(bots_api.bot_state.state_path(bot_id), payload)


def test_position_uses_live_price(monkeypatch):
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 120.0})
    position = {
        "coin": "BTCUSDT",
        "quantity": 0.5,
        "entry_price": 100.0,
        "last_price": 100.0,
        "stop_price": 90.0,
    }
    pos = bots_api._live_position(position)
    assert pos["price_source"] == "live"
    assert pos["last_price"] == 120.0
    assert pos["unrealized_pnl"] == 10.0
    assert pos["unrealized_pnl_pct"] == 20.0
    assert pos["value"] == 60.0
    assert pos["stop_distance_pct"] == round((120.0 / 90.0 - 1) * 100, 2)


def test_position_falls_back_to_candle_price(monkeypatch):
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {})
    position = {
        "coin": "XRPUSDT",
        "quantity": 10.0,
        "entry_price": 2.0,
        "last_price": 2.1,
    }
    pos = bots_api._live_position(position)
    assert pos["price_source"] == "candle"
    assert pos["last_price"] == 2.1
    assert pos["unrealized_pnl"] == 1.0


def test_no_position_returns_none():
    assert bots_api._live_position(None) is None


def test_stop_price_computed_from_atr(monkeypatch):
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 100.0})
    position = {
        "coin": "BTCUSDT",
        "quantity": 1.0,
        "entry_price": 100.0,
        "atr": 2.0,
        "highest_price": 100.0,
    }
    pos = bots_api._live_position(position, {"stop_atr": 5})
    assert pos["stop_price"] == 90.0
    assert pos["stop_distance_pct"] == round((100.0 / 90.0 - 1) * 100, 2)


def test_trailing_stop_arms_after_threshold(monkeypatch):
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 130.0})
    position = {
        "coin": "BTCUSDT",
        "quantity": 1.0,
        "entry_price": 100.0,
        "atr": 2.0,
        "highest_price": 130.0,
    }
    pos = bots_api._live_position(
        position, {"stop_atr": 5, "trail_atr": 8, "trail_after_pct": 20}
    )
    # 130 - 8*2 = 114 > 100 - 5*2 = 90 → takipli stop devrede
    assert pos["stop_price"] == 114.0


def test_max_stop_pct_caps_wide_stop(monkeypatch):
    """Yüksek volatiliteli coin: 35×ATR neredeyse sıfıra inerken tavan devreye girer."""
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"DODOUSDT": 0.0312})
    position = {
        "coin": "DODOUSDT",
        "quantity": 3196.2,
        "entry_price": 0.03125562,
        "atr": 0.0008631765124977679,
        "highest_price": 0.03406,
    }
    pos = bots_api._live_position(position, {"stop_atr": 35, "max_stop_pct": 15})
    # sınırsız stop 0.00104 olurdu; tavan %15 → 0.02657
    assert pos["stop_price"] == pytest.approx(0.02656728, rel=1e-6)
    assert pos["stop_distance_pct"] == pytest.approx(round((0.0312 / 0.02656728 - 1) * 100, 2))


def test_saved_stop_is_also_capped(monkeypatch):
    """Eski kayıtta çok aşağıda kayıtlı stop varsa tavan yine uygulanır."""
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 100.0})
    position = {
        "coin": "BTCUSDT",
        "quantity": 1.0,
        "entry_price": 100.0,
        "stop_price": 3.0,
        "atr": 0.0,
        "highest_price": 100.0,
    }
    pos = bots_api._live_position(position, {"stop_atr": 5, "max_stop_pct": 15})
    assert pos["stop_price"] == 85.0


def test_serialize_computes_equity_and_total(monkeypatch):
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"BTCUSDT": 120.0})
    bot_id = "bot_live_test"
    _state(
        bot_id,
        cash=40.0,
        initial_cash=100.0,
        position={"coin": "BTCUSDT", "quantity": 0.5, "entry_price": 100.0, "last_price": 100.0},
    )
    row = {
        "id": bot_id,
        "name": "Test",
        "type": "trade",
        "mode": "paper",
        "period": "1h",
        "config_json": '{"strategies": [], "coins": []}',
        "status": "running",
        "auto_restart": 1,
    }
    item = bots_api._serialize(row)
    state = item["state"]
    assert state["unrealized_pnl"] == 10.0
    assert state["equity"] == 100.0  # 40 nakit + 60 pozisyon
    assert state["total_pnl"] == 0.0
    assert state["position"]["price_source"] == "live"


def test_topbar_total_includes_unrealized(monkeypatch):
    """Toplam K/Z = nakit + pozisyon - başlangıç (gerçekleşmemiş dahil)."""
    monkeypatch.setattr(live_prices, "prices", lambda symbols: {"ETHUSDT": 200.0})
    bot_id = "bot_live_test2"
    _state(
        bot_id,
        cash=50.0,
        initial_cash=100.0,
        position={"coin": "ETHUSDT", "quantity": 0.5, "entry_price": 100.0, "last_price": 100.0},
    )
    row = {
        "id": bot_id,
        "name": "Test 2",
        "type": "trade",
        "mode": "paper",
        "period": "1h",
        "config_json": '{"strategies": [], "coins": []}',
        "status": "running",
        "auto_restart": 1,
    }
    state = bots_api._serialize(row)["state"]
    assert state["equity"] == 150.0
    assert state["total_pnl"] == 50.0
    assert state["total_pnl_pct"] == 50.0
