"""Strateji adlarının bot yapılandırmasına ve loglara yansıması."""

from app import db
from app.strategies.service import create_custom, get_custom


def _cleanup(sid):
    db.execute("DELETE FROM strategy_versions WHERE strategy_id=?", (sid,))
    db.execute("DELETE FROM strategies WHERE id=?", (sid,))


def test_bot_config_pins_display_name():
    from app.api.bots import BotBody, _bot_config

    item = create_custom(
        {
            "name": "Ad Testi Stratejisi",
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
            "sell": {"logic": "AND", "conditions": []},
        }
    )
    try:
        body = BotBody(
            name="Test Bot",
            period="1h",
            strategies=[{"type": "custom", "id": item["id"], "version": item["version"]}],
        )
        config = _bot_config(body)
        spec = config["strategies"][0]
        assert spec["name"] == "Ad Testi Stratejisi"
        assert spec["id"] == item["id"]
    finally:
        _cleanup(item["id"])


def test_engine_labels_resolve_custom_name():
    from app.api.bots import BotBody, _bot_config
    from app.engine import TradingEngine

    item = create_custom(
        {
            "name": "Etiket Stratejisi",
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
            "sell": {"logic": "AND", "conditions": []},
        }
    )
    try:
        body = BotBody(
            name="Etiket Botu",
            period="1h",
            strategies=[{"type": "custom", "id": item["id"], "version": item["version"]}],
        )
        config = _bot_config(body)
        engine = TradingEngine("bot_test_labels", config, "paper")
        assert engine._evaluator_name(engine.evaluators[0]) == "Etiket Stratejisi"
        assert engine.strategy_labels[item["id"]] == "Etiket Stratejisi"
    finally:
        _cleanup(item["id"])
