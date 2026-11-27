"""Strateji + coin listesi kütüphanesi: dışa/içe aktarma (Git dostu)."""

from __future__ import annotations

import json

from app import coin_lists, library_sync
from app.strategies import service


def rsi_definition(name: str = "Kütüphane testi") -> dict:
    return {
        "name": name,
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {
                        "type": "indicator",
                        "id": "RSI",
                        "params": {"length": 14},
                        "output": "value",
                    },
                    "op": "lt",
                    "right": {"type": "constant", "value": 35},
                }
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {
                        "type": "indicator",
                        "id": "RSI",
                        "params": {"length": 14},
                        "output": "value",
                    },
                    "op": "gt",
                    "right": {"type": "constant", "value": 65},
                }
            ],
        },
        "risk": {"stop_atr": 3, "trail_atr": 5},
    }


def test_export_writes_git_friendly_files(tmp_path):
    strategy = service.create_custom(rsi_definition())
    coin_list = coin_lists.create_list("Test listesi", ["btcusdt", "ethusdt"])

    summary = library_sync.export_library(tmp_path)

    assert summary["strategies"] == 1
    assert summary["coinlists"] == 1
    files = list((tmp_path / "strategies").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["kind"] == "strategy"
    assert payload["id"] == strategy["id"]
    assert payload["definition"]["name"] == "Kütüphane testi"

    lists = list((tmp_path / "coinlists").glob("*.json"))
    assert len(lists) == 1
    listed = json.loads(lists[0].read_text(encoding="utf-8"))
    assert listed["id"] == coin_list["id"]
    assert listed["coins"] == ["BTCUSDT", "ETHUSDT"]


def test_export_skips_builtin_lists_by_default(tmp_path):
    library_sync.export_library(tmp_path)
    assert list((tmp_path / "coinlists").glob("*.json")) == []

    library_sync.export_library(tmp_path, include_builtin_lists=True)
    files = list((tmp_path / "coinlists").glob("*.json"))
    assert len(files) == len(coin_lists.PRESETS)


def test_export_prunes_stale_files(tmp_path):
    library_sync.export_library(tmp_path)
    stale = tmp_path / "strategies" / "eski--custom_0000000000.json"
    stale.write_text("{}", encoding="utf-8")

    summary = library_sync.export_library(tmp_path, prune=True)

    assert summary["removed"] == 1
    assert not stale.exists()


def test_import_restores_deleted_strategy_and_list(tmp_path):
    strategy = service.create_custom(rsi_definition())
    coin_list = coin_lists.create_list("Test listesi", ["BTCUSDT", "ETHUSDT"])
    library_sync.export_library(tmp_path)

    service.delete_custom(strategy["id"], force=True)
    coin_lists.delete_list(coin_list["id"])
    assert service.get_custom(strategy["id"]) is None

    preview = library_sync.import_library(tmp_path)
    assert [e["action"] for e in preview["strategies"]] == ["create"]
    assert [e["action"] for e in preview["coinlists"]] == ["create"]

    report = library_sync.import_library(tmp_path, apply=True)
    assert report["errors"] == []

    restored = service.get_custom(strategy["id"])
    assert restored is not None
    assert restored["definition"]["name"] == "Kütüphane testi"
    assert restored["version"] == 1

    restored_list = coin_lists.get_list(coin_list["id"])
    assert restored_list is not None
    assert restored_list["coins"] == ["BTCUSDT", "ETHUSDT"]


def test_import_is_idempotent(tmp_path):
    service.create_custom(rsi_definition())
    coin_lists.create_list("Test listesi", ["BTCUSDT"])
    library_sync.export_library(tmp_path)

    report = library_sync.import_library(tmp_path, apply=True)

    assert [e["action"] for e in report["strategies"]] == ["skip"]
    assert [e["action"] for e in report["coinlists"]] == ["skip"]
    assert service.list_custom()[0]["version"] == 1


def test_import_matches_by_name_when_id_changes(tmp_path):
    strategy = service.create_custom(rsi_definition())
    library_sync.export_library(tmp_path)

    path = next((tmp_path / "strategies").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["id"] = "custom_ffffffff00"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = library_sync.import_library(tmp_path, apply=True)

    assert report["errors"] == []
    entry = report["strategies"][0]
    assert entry["matched"] == "isim"
    assert entry["id"] == strategy["id"]
    assert entry["action"] == "skip"


def test_import_only_missing_keeps_local_edits(tmp_path):
    strategy = service.create_custom(rsi_definition())
    coin_list = coin_lists.create_list("Test listesi", ["BTCUSDT"])
    library_sync.export_library(tmp_path)

    # Kullanıcı panelden stratejiyi ve listeyi değiştirir.
    edited = rsi_definition()
    edited["risk"] = {"stop_atr": 4, "trail_atr": 7}
    service.update_custom(strategy["id"], edited)
    coin_lists.update_list(coin_list["id"], "Test listesi", ["BTCUSDT", "SOLUSDT"])

    report = library_sync.import_library(tmp_path, apply=True, only_missing=True)

    assert report["errors"] == []
    assert [e["action"] for e in report["strategies"]] == ["skip"]
    assert [e["action"] for e in report["coinlists"]] == ["skip"]
    assert service.get_custom(strategy["id"])["definition"]["risk"]["stop_atr"] == 4
    assert coin_lists.get_list(coin_list["id"])["coins"] == ["BTCUSDT", "SOLUSDT"]


def test_import_only_missing_still_creates_new_records(tmp_path):
    service.create_custom(rsi_definition())
    library_sync.export_library(tmp_path)
    service.delete_custom(service.list_custom()[0]["id"], force=True)

    report = library_sync.import_library(tmp_path, apply=True, only_missing=True)

    assert [e["action"] for e in report["strategies"]] == ["create"]
    assert len(service.list_custom()) == 1


def test_import_builtin_list_creates_user_copy(tmp_path):
    payload = {
        "kind": "coinlist",
        "schema": 1,
        "id": "list_top10",
        "name": "Top 10",
        "coins": ["BTCUSDT"],
    }
    folder = tmp_path / "coinlists"
    folder.mkdir(parents=True)
    (folder / "top-10--list_top10.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    report = library_sync.import_library(tmp_path, apply=True)

    assert report["errors"] == []
    entry = report["coinlists"][0]
    assert entry["action"] == "create"
    assert entry["matched"] == "hazır-liste"
    created = coin_lists.get_list(entry["id"])
    assert created is not None
    assert created["builtin"] is False
    assert created["name"] != "Top 10"


def test_invalid_file_is_reported_not_raised(tmp_path):
    folder = tmp_path / "strategies"
    folder.mkdir(parents=True)
    (folder / "bozuk--custom_x.json").write_text("{bozuk", encoding="utf-8")

    report = library_sync.import_library(tmp_path, apply=True)

    assert len(report["errors"]) == 1
    assert report["errors"][0]["file"] == "bozuk--custom_x.json"
