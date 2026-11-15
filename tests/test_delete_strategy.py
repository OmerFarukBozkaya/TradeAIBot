"""Strateji silme: bot referansı koruması ve kalıcı silme."""

import json

import pytest

from app.strategies import service
from app.strategies.compiler import StrategyValidationError


class FakeDB:
    """service.db yerine geçen, yalnızca gereken sorguları yanıtlayan sahte DB."""

    def __init__(self, strategy=None, bots=None):
        self.strategy = strategy
        self.bots = bots or []
        self.executed = []

    def row(self, sql, params=()):
        if sql.startswith("SELECT * FROM strategies"):
            if self.strategy and params and params[0] == self.strategy["id"]:
                item = dict(self.strategy)
                return item
            return None
        return None

    def rows(self, sql, params=()):
        if sql.startswith("SELECT id,name,status,config_json FROM bots"):
            return self.bots
        return []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return 1

    def get_setting(self, key, default=None):
        return default


def make_strategy():
    return {
        "id": "custom_test01",
        "name": "Test",
        "definition_json": json.dumps({"name": "Test", "buy": {}, "sell": {}}),
        "version": 1,
        "status": "active",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }


def bot_using(strategy_id="custom_test01"):
    return {
        "id": "bot_1",
        "name": "Bot A",
        "status": "running",
        "config_json": json.dumps({"strategies": [{"type": "custom", "id": strategy_id}]}),
    }


def test_delete_removes_strategy_and_versions(monkeypatch):
    fake = FakeDB(strategy=make_strategy(), bots=[])
    monkeypatch.setattr(service, "db", fake)

    result = service.delete_custom("custom_test01")

    assert result["ok"] is True
    sqls = " ".join(sql for sql, _ in fake.executed)
    assert "DELETE FROM strategies" in sqls
    assert "DELETE FROM strategy_versions" in sqls
    assert "DELETE FROM strategy_backtests" in sqls


def test_delete_blocks_when_bot_uses_strategy(monkeypatch):
    fake = FakeDB(strategy=make_strategy(), bots=[bot_using()])
    monkeypatch.setattr(service, "db", fake)

    with pytest.raises(StrategyValidationError) as exc:
        service.delete_custom("custom_test01")

    assert "Bot A" in str(exc.value)
    assert not any("DELETE FROM strategies" in sql for sql, _ in fake.executed)


def test_delete_force_ignores_bot_reference(monkeypatch):
    fake = FakeDB(strategy=make_strategy(), bots=[bot_using()])
    monkeypatch.setattr(service, "db", fake)

    result = service.delete_custom("custom_test01", force=True)

    assert result["ok"] is True
    assert result["bots"][0]["name"] == "Bot A"
    assert any("DELETE FROM strategies" in sql for sql, _ in fake.executed)


def test_delete_missing_strategy_raises(monkeypatch):
    fake = FakeDB(strategy=None, bots=[])
    monkeypatch.setattr(service, "db", fake)

    with pytest.raises(StrategyValidationError):
        service.delete_custom("custom_yok")


def test_bots_using_matches_only_referenced_strategy(monkeypatch):
    other = {
        "id": "bot_2",
        "name": "Bot B",
        "status": "stopped",
        "config_json": json.dumps({"strategies": [{"type": "custom", "id": "custom_baska"}]}),
    }
    fake = FakeDB(strategy=make_strategy(), bots=[bot_using(), other])
    monkeypatch.setattr(service, "db", fake)

    used = service.bots_using("custom_test01")

    assert [b["name"] for b in used] == ["Bot A"]
