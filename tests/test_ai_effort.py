"""Uğraşma düzeyi (effort) ve profil uçları: regresyon testleri."""

from __future__ import annotations

import asyncio

import pytest

from app.ai import auto


def test_profile_exposes_effort_levels():
    """Panelin seçim kutusunu besleyen düzeyler yanıtın kökünde olmalı."""
    from app.api.ai import profile_get

    payload = asyncio.run(profile_get())
    assert "effortLevels" in payload
    levels = payload["effortLevels"]
    assert set(levels) == {"quick", "balanced", "thorough"}
    assert all("label" in v and "desc" in v for v in levels.values())


@pytest.mark.parametrize(
    "level, budget, iterations, folds, walk_forward",
    [
        ("quick", 1, 2, 0, False),
        ("balanced", 3, 5, 3, True),
        ("thorough", 6, 8, 4, True),
    ],
)
def test_effort_level_sets_search_budget(level, budget, iterations, folds, walk_forward):
    saved = auto.save_profile({"effort": level})
    assert saved["effort"] == level
    assert saved["search_budget"] == budget
    assert saved["refine_iterations"] == iterations
    assert saved["folds"] == folds
    assert saved["walk_forward"] is walk_forward


def test_explicit_fields_override_effort():
    """Uğraşma düzeyi varsayılan verir; açıkça verilen alan onu ezer."""
    saved = auto.save_profile({"effort": "thorough", "search_budget": 2, "walk_forward": False})
    assert saved["effort"] == "thorough"
    assert saved["search_budget"] == 2
    assert saved["walk_forward"] is False


def test_unknown_effort_keeps_previous():
    auto.save_profile({"effort": "balanced"})
    saved = auto.save_profile({"effort": "yok"})
    assert saved["effort"] == "balanced"


def test_profile_defaults_are_sane():
    profile = auto.load_profile()
    assert profile["effort"] in auto.EFFORT_LEVELS
    assert profile["objective"] in {"profit", "local_min_max", "forward"}
    assert 0 < profile["proximity_band"] <= 0.05
