"""Coin listeleri: CRUD, hazır listeler ve tarama/bot çözümlemesi."""

import pytest

from app import coin_lists, db
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def test_presets_seeded(temp_db):
    lists = coin_lists.list_lists()
    builtin = [item for item in lists if item["builtin"]]
    assert len(builtin) == len(coin_lists.PRESETS)
    names = {item["name"] for item in builtin}
    assert {"Top 10", "Layer 1", "Meme"} <= names
    assert all(item["count"] > 0 for item in builtin)


def test_ensure_presets_is_idempotent(temp_db):
    coin_lists.ensure_presets()
    coin_lists.ensure_presets()
    assert len(coin_lists.list_lists()) == len(coin_lists.PRESETS)


def test_create_update_delete(temp_db):
    created = coin_lists.create_list("Benim liste", ["btcusdt", "ETHUSDT", "btcusdt"])
    assert created["coins"] == ["BTCUSDT", "ETHUSDT"]
    assert created["builtin"] is False

    updated = coin_lists.update_list(created["id"], coins=["SOLUSDT"])
    assert updated["coins"] == ["SOLUSDT"]
    assert updated["name"] == "Benim liste"

    coin_lists.delete_list(created["id"])
    assert coin_lists.get_list(created["id"]) is None


def test_duplicate_and_name_conflict(temp_db):
    copy = coin_lists.duplicate_list("list_top10")
    assert copy["name"] != "Top 10"
    assert copy["builtin"] is False
    assert copy["coins"] == coin_lists.get_list("list_top10")["coins"]

    with pytest.raises(ValueError):
        coin_lists.create_list("Top 10", ["BTCUSDT"])


def test_builtin_is_read_only(temp_db):
    with pytest.raises(PermissionError):
        coin_lists.update_list("list_top10", coins=["BTCUSDT"])
    with pytest.raises(PermissionError):
        coin_lists.delete_list("list_top10")


def test_invalid_inputs(temp_db):
    with pytest.raises(ValueError):
        coin_lists.create_list("", ["BTCUSDT"])
    with pytest.raises(ValueError):
        coin_lists.create_list("Boş", [])
    with pytest.raises(ValueError):
        coin_lists.create_list("Kötü coin", ["btc-usdt"])


def test_list_coins_resolution(temp_db):
    assert coin_lists.list_coins("list_top10")[0] == "BTCUSDT"
    assert coin_lists.list_coins("yok_böyle") is None


def test_scan_coins_uses_list_when_empty(temp_db):
    from app.job_runner import _scan_coins

    resolved = _scan_coins({"list_id": "list_top10", "coins": []})
    assert resolved == coin_lists.list_coins("list_top10")

    explicit = _scan_coins({"list_id": "list_top10", "coins": ["fetUSDT"]})
    assert explicit == ["FETUSDT"]


def test_bot_config_resolves_coin_list(temp_db):
    from app.api.bots import BotBody, _bot_config

    body = BotBody(
        name="Liste botu",
        period="1h",
        strategies=[{"type": "builtin", "name": "MACD"}],
        coin_list_id="list_meme",
    )
    config = _bot_config(body)
    assert config["coins"] == coin_lists.list_coins("list_meme")
    assert config["coin_list"]["id"] == "list_meme"
    assert config["coin_list"]["name"] == "Meme"


def test_bot_config_unknown_list_rejected(temp_db):
    from fastapi import HTTPException

    from app.api.bots import BotBody, _bot_config

    with pytest.raises(HTTPException):
        _bot_config(
            BotBody(
                name="X",
                period="1h",
                strategies=[{"type": "builtin", "name": "MACD"}],
                coin_list_id="yok_böyle",
            )
        )


def test_bot_config_inherits_strategy_risk(temp_db):
    """Arayüz 4 boolean gönderse bile stratejinin stop/kâr koruma ayarları devralınır."""
    from app.api.bots import BotBody, _bot_config
    from app.strategies.service import create_custom

    created = create_custom(
        {
            "name": "Riskli",
            "risk": {"stop_atr": 35, "cooldown": 10, "profit_exit_donchian": 10},
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
    )
    body = BotBody(
        name="Bot",
        period="1h",
        strategies=[{"type": "custom", "id": created["id"]}],
        risk={"dynamic_stop": False, "static_stop": False},
    )
    config = _bot_config(body)
    # Eski stratejideki 35×ATR, kayıt sırasında güvenli sınıra çekilir.
    assert config["risk"]["stop_atr"] == 6.0
    assert config["risk"]["cooldown"] == 10
    assert config["risk"]["profit_exit_donchian"] == 10
    # Açıkça verilen değer devralınanı ezer (yine güvenli sınıra çekilir).
    body2 = BotBody(
        name="Bot2",
        period="1h",
        strategies=[{"type": "custom", "id": created["id"]}],
        risk={"stop_atr": 3},
    )
    assert _bot_config(body2)["risk"]["stop_atr"] == 3


def test_engine_inherits_risk_from_strategy(temp_db):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(
        {
            "name": "Motor riski",
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
    )
    engine = TradingEngine(
        "bot_x",
        {
            "period": "1h",
            "strategies": [{"type": "custom", "id": created["id"]}],
            "cash": 100,
            "risk": {"dynamic_stop": False},
        },
        "paper",
    )
    assert engine.risk["stop_atr"] == 6.0
    assert engine.risk["cooldown"] == 10


def test_serialize_refreshes_coin_list_name(temp_db):
    from app.api.bots import _enrich_coin_list

    config = {"coins": [], "coin_list": {"id": "list_meme", "name": "eski ad", "count": 1}}
    _enrich_coin_list(config)
    assert config["coin_list"]["name"] == "Meme"
    assert config["coin_list"]["current_count"] == len(coin_lists.list_coins("list_meme"))
