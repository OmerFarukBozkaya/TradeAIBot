"""Bot varlık sınıfı: kripto dışı semboller yalnızca paper modda."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import db
from app.api.bots import BotBody, _bot_config


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    from app.paths import paths

    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _body(**overrides):
    payload = {
        "name": "Test",
        "period": "1d",
        "strategies": [{"type": "builtin", "name": "MACD"}],
        "coins": ["XAUUSD"],
        "cash": 100.0,
        "mode": "paper",
        "asset_class": "metal",
    }
    payload.update(overrides)
    return BotBody(**payload)


def test_paper_bot_accepts_gold():
    config = _bot_config(_body())
    assert config["coins"] == ["XAUUSD"]
    assert config["asset_class"] == "metal"


def test_live_bot_rejects_non_crypto():
    with pytest.raises(HTTPException) as exc:
        _bot_config(_body(mode="live"))
    assert exc.value.status_code == 400
    assert "test (paper)" in exc.value.detail


def test_fund_bot_rejects_intraday_period():
    with pytest.raises(HTTPException) as exc:
        _bot_config(_body(
            period="1h", coins=["TEFAS:AFT"], asset_class="fund",
        ))
    assert exc.value.status_code == 400
    assert "TEFAS:AFT" in exc.value.detail


def test_forex_bot_accepts_hourly():
    config = _bot_config(_body(
        period="1h", coins=["USDTRY"], asset_class="forex",
    ))
    assert config["asset_class"] == "forex"


def test_crypto_bot_still_works():
    config = _bot_config(_body(
        period="1h", coins=["BTCUSDT"], asset_class="crypto", mode="live",
    ))
    assert config["coins"] == ["BTCUSDT"]
