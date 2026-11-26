"""Canlı izleme grafiği: açık pozisyon için mum verisi + seviyeler."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import bot_state, db
from app.api import bots as bots_api


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_state, "STATE_DIR", tmp_path / "state")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bots_api.live_prices, "prices", lambda symbols: {})
    monkeypatch.setattr(bots_api.live_prices, "ages", lambda symbols: {})
    yield


def _seed_bot(bot_id="bot_live", with_position=True):
    now = db.utcnow()
    config = {
        "period": "15m",
        "strategies": [{"type": "builtin", "name": "MACD"}],
        "coins": ["BTCUSDT"],
        "cash": 100.0,
        "risk": {"stop_atr": 2.0, "max_stop_pct": 15, "take_profit_pct": 5},
    }
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "Canlı", "trade", "paper", "15m", db.json.dumps(config),
         "running", 1, now, now),
    )
    state = {
        "bot_id": bot_id,
        "cash": 50.0,
        "initial_cash": 100.0,
        "total_realized_pnl": 0.0,
        "trade_count": 1,
        "position": None,
    }
    if with_position:
        state["position"] = {
            "coin": "BTCUSDT",
            "quantity": 0.001,
            "entry_price": 100.0,
            "highest_price": 104.0,
            "last_price": 103.0,
            "atr": 1.0,
            "opened_at": "2026-01-01T10:00:00+00:00",
            "candles": 3,
        }
    bot_state.save_state(bot_id, state)
    return bot_id


def _fake_history(calls):
    def fake(symbol, period, limit, *, asset_class="", use_cache=True, **kwargs):
        calls.append({
            "symbol": symbol, "period": period, "limit": limit,
            "asset_class": asset_class, "use_cache": use_cache,
        })
        base = 1_767_265_200_000  # 2026-01-01T10:00:00Z
        step = 15 * 60 * 1000
        n = 40
        data = {
            "opendate": [base + i * step for i in range(n)],
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume_usdt": [1000.0] * n,
            "closedate": [base + i * step + step - 1 for i in range(n)],
        }
        return data, {"provider": "binance", "source": "binance"}

    return fake


def test_live_chart_returns_candles_and_levels(monkeypatch):
    bot_id = _seed_bot()
    calls = []
    monkeypatch.setattr("app.market_data.load_history", _fake_history(calls))

    res = bots_api.bot_live_chart(bot_id, candles=40)

    assert res["coin"] == "BTCUSDT"
    assert res["period"] == "15m"
    assert res["mode"] == "paper"
    assert len(res["candles"]) == 40
    first = res["candles"][0]
    assert set(first) >= {"time", "open", "high", "low", "close", "volume"}
    assert first["high"] >= first["close"] >= first["low"]
    assert res["live_price"] == pytest.approx(103.0)
    assert res["position"]["entry_price"] == pytest.approx(100.0)
    # ATR stop 100 - 2*1 = 98; pozisyon %4 kâra ulaştığı için breakeven
    # devreye girer ve stop girişe (100) çekilir — "kârdan zarara dönme" koruması.
    assert res["position"]["stop_price"] == pytest.approx(100.0)
    # Stop girişe çekildiği için güncel fiyat (103) stopun %3 üzerinde.
    assert res["position"]["stop_distance_pct"] == pytest.approx(3.0)
    assert res["position"]["take_profit_price"] == pytest.approx(105.0)
    assert res["position"]["opened_at"] == "2026-01-01T10:00:00+00:00"

    # Canlı izleme önbelleği yazmamalı (uzun geçmişi küçültmesin).
    assert calls and calls[0]["use_cache"] is False
    assert calls[0]["symbol"] == "BTCUSDT"
    assert calls[0]["limit"] == 40


def test_live_chart_requires_open_position():
    bot_id = _seed_bot("bot_flat", with_position=False)
    with pytest.raises(HTTPException) as exc:
        bots_api.bot_live_chart(bot_id)
    assert exc.value.status_code == 409
    assert "pozisyon" in exc.value.detail.lower()


def test_live_chart_unknown_bot():
    with pytest.raises(HTTPException) as exc:
        bots_api.bot_live_chart("yok")
    assert exc.value.status_code == 404


def test_live_chart_reports_provider_error(monkeypatch):
    bot_id = _seed_bot()

    def broken(*args, **kwargs):
        raise RuntimeError("ağ yok")

    monkeypatch.setattr("app.market_data.load_history", broken)
    with pytest.raises(HTTPException) as exc:
        bots_api.bot_live_chart(bot_id)
    assert exc.value.status_code == 400
    assert "BTCUSDT" in exc.value.detail
