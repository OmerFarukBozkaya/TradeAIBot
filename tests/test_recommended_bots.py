"""Dashboard: önerilen 4h botlarını tek tıkla oluşturma."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from app import coin_lists, db
from app.api import bots as bots_api
from app.api.bots import RecommendedBotsBody, create_recommended_bots
from app.paths import paths

COINS = ["BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
         "SUIUSDT", "ENAUSDT", "WLDUSDT", "PEPEUSDT"]


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _create(**kwargs):
    return asyncio.run(create_recommended_bots(RecommendedBotsBody(**kwargs)))


def test_creates_eight_bots_and_splits_cash(temp_db):
    coin_lists.create_list("Trend 4h", COINS)

    result = _create(cash=800, mode="paper", risk=4)

    assert len(result["created"]) == 8
    assert result["skipped"] == []
    assert result["per_bot"] == 100
    assert result["coins"] == COINS

    rows = db.rows("SELECT * FROM bots ORDER BY name")
    assert len(rows) == 8
    for row in rows:
        config = json.loads(row["config_json"])
        assert row["period"] == "4h"
        assert row["mode"] == "paper"
        assert row["status"] == "stopped"
        assert config["period"] == "4h"
        assert len(config["coins"]) == 1
        assert config["coins"][0] in COINS
        assert config["strategies"][0]["name"] == "TrendRider"
        assert config["filters"] == {"btc_regime": True}
        assert config["risk"]["risk_per_trade_pct"] == 4
        assert config["risk"]["trail_after_pct"] == 10
        assert config["risk"]["breakeven_pct"] == 20
        # Paper modda günlük limit kapalı.
        assert "daily_loss_limit_pct" not in config["risk"]


def test_live_mode_adds_daily_loss_limit(temp_db, monkeypatch):
    coin_lists.create_list("Trend 4h", COINS)
    monkeypatch.setattr(bots_api, "_live_gate", lambda: None)

    result = _create(cash=1000, mode="live", risk=2.5)

    assert len(result["created"]) == 8
    rows = db.rows("SELECT * FROM bots")
    for row in rows:
        risk = json.loads(row["config_json"])["risk"]
        assert risk["daily_loss_limit_pct"] == 3.0
        assert risk["risk_per_trade_pct"] == 2.5


def test_is_idempotent(temp_db):
    coin_lists.create_list("Trend 4h", COINS)

    first = _create(cash=800)
    second = _create(cash=800)

    assert len(first["created"]) == 8
    assert second["created"] == []
    assert len(second["skipped"]) == 8
    assert len(db.rows("SELECT id FROM bots")) == 8


def test_live_mode_requires_gate(temp_db, monkeypatch):
    coin_lists.create_list("Trend 4h", COINS)

    def blocked():
        raise HTTPException(403, "Canlı işlem anahtarı kapalı")

    monkeypatch.setattr(bots_api, "_live_gate", blocked)

    with pytest.raises(HTTPException) as exc:
        _create(mode="live")
    assert exc.value.status_code == 403
    assert db.rows("SELECT id FROM bots") == []


def test_rejects_invalid_cash_and_risk(temp_db):
    coin_lists.create_list("Trend 4h", COINS)

    with pytest.raises(HTTPException):
        _create(cash=1)
    with pytest.raises(HTTPException):
        _create(cash=1000, risk=20)


def test_falls_back_to_fixed_list_without_coin_list(temp_db):
    result = _create(cash=80)

    assert result["coins"] == COINS
    assert len(result["created"]) == 8
    assert result["per_bot"] == 10