"""Strateji kartlarındaki 'en iyi zaman dilimi' alanlarının doğruluğu."""

import pytest

from app.strategies import service


class FakeDB:
    def __init__(self, meta):
        self.meta = meta

    def get_setting(self, key, default=None):
        if key == "strategy_timeframes":
            return self.meta
        return default


def test_attach_timeframes_adds_best(monkeypatch):
    monkeypatch.setattr(service, "db", FakeDB({
        "custom_1": {
            "best": "4h",
            "edge": "üstün",
            "reliable": True,
            "periods": {
                "4h": {"ret": 1525.4, "bh": 500.1, "ex": 1025.3, "dd": 56.1, "trades": 96},
                "1d": {"ret": 657.7, "bh": 1325.0, "ex": -667.3, "dd": 66.9, "trades": 13},
            },
        }
    }))
    items = service.attach_timeframes([{"id": "custom_1", "name": "X"}])
    item = items[0]
    assert item["best_timeframe"] == "4h"
    assert item["timeframe_edge"] == "üstün"
    assert item["timeframe_reliable"] is True
    assert item["timeframe_periods"]["4h"]["diff"] == 1025.3
    assert "1d" in item["timeframe_periods"]


def test_attach_timeframes_unknown_strategy(monkeypatch):
    monkeypatch.setattr(service, "db", FakeDB({}))
    item = service.attach_timeframes([{"id": "custom_yok"}])[0]
    assert item["best_timeframe"] is None
    assert item["timeframe_periods"] == {}


def test_attach_timeframes_flags_unreliable(monkeypatch):
    monkeypatch.setattr(service, "db", FakeDB({
        "custom_2": {
            "best": None,
            "edge": None,
            "reliable": False,
            "periods": {"4h": {"ret": 7e13, "bh": 1605.0, "ex": 7e13, "dd": 19.3, "trades": 479}},
        }
    }))
    item = service.attach_timeframes([{"id": "custom_2"}])[0]
    assert item["timeframe_reliable"] is False
    assert item["best_timeframe"] is None
