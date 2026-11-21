"""Aday/arşiv model birikimini önleme ve toplu silme."""

from __future__ import annotations

import asyncio

import pytest

from app.ai import artifacts


@pytest.fixture()
def model_root(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODEL_ROOT", tmp_path / "models")
    return tmp_path


def _make(name: str, status: str | None = None) -> str:
    manifest = artifacts.save_model(
        name=name,
        bundle={"buy_model": None},
        params={"coin": "X", "period": "1h"},
        metrics={"refinement": {"best_score": 1.0}},
        data_meta={"rows": 10},
        feature_names=["a"],
        thresholds={"buy": 0.5, "sell": 0.5},
    )
    if status:
        artifacts.set_status(manifest["id"], status)
    return manifest["id"]


def test_bulk_delete_removes_candidates_and_archives(model_root):
    active_id = _make("aktif", "active")
    cand_ids = [_make(f"aday{i}") for i in range(3)]
    arch_ids = [_make(f"arsiv{i}") for i in range(2)]
    for mid in arch_ids:
        artifacts.set_status(mid, "archived")

    result = artifacts.bulk_delete(["candidate", "archived"])

    assert result["deleted"] == 5
    remaining = artifacts.list_models(include_archived=True)
    assert [m["id"] for m in remaining] == [active_id]
    assert not artifacts.model_dir(cand_ids[0]).exists()
    assert not artifacts.model_dir(arch_ids[0]).exists()


def test_bulk_delete_never_touches_active(model_root):
    active_id = _make("aktif", "active")
    _make("aday")

    # Yalnızca aday/arşiv istense bile 'active' listede olsa da silinmez.
    artifacts.bulk_delete(["candidate", "archived", "active"])
    assert artifacts.load_manifest(active_id) is not None


def test_bulk_delete_single_status(model_root):
    _make("aday")
    arch = _make("arsiv")
    artifacts.set_status(arch, "archived")

    accepted = artifacts.bulk_delete(["archived"])
    assert accepted["deleted"] == 1
    assert artifacts.load_manifest(arch) is None
    assert len(artifacts.list_models(include_archived=True)) == 1


def test_bulk_delete_rejects_unknown_status(model_root):
    _make("aday")
    with pytest.raises(ValueError):
        artifacts.bulk_delete(["multi"])


def test_bulk_delete_endpoint(model_root):
    from app.api.ai import BulkDeleteBody, bulk_delete

    _make("aday")
    _make("aday2")
    _make("aktif", "active")

    payload = asyncio.run(bulk_delete(BulkDeleteBody(statuses=["candidate"])))
    assert payload["deleted"] == 2
    assert len(artifacts.list_models(include_archived=True)) == 1


def test_bulk_delete_endpoint_defaults_to_candidate_and_archive(model_root):
    from app.api.ai import bulk_delete

    _make("aday")
    arch = _make("arsiv")
    artifacts.set_status(arch, "archived")
    _make("aktif", "active")

    payload = asyncio.run(bulk_delete(None))
    assert payload["deleted"] == 2
    assert sorted(payload["statuses"]) == ["archived", "candidate"]
