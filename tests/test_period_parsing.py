"""Periyot ayrıştırma: serbest yazım, büyük harf ve Türkçe kısaltmalar."""

from __future__ import annotations

import pytest

from app.market_data.periods import choose_base_period, parse_period, period_ms


@pytest.mark.parametrize(
    "text,expected",
    [
        ("15m", "15m"),
        ("45m", "45m"),
        ("30dk", "30m"),
        ("2 h", "2h"),
        ("1H", "1h"),
        ("4H", "4h"),
        ("1D", "1d"),
        ("3D", "3d"),
        ("1W", "1w"),
        ("1w", "1w"),
        ("1M", "1M"),
        ("1ay", "1M"),
        ("1hafta", "1w"),
        ("1hf", "1w"),
        ("1gün", "1d"),
        ("1gun", "1d"),
        ("1G", "1d"),
        ("1yıl", "1y"),
        ("1Y", "1y"),
        ("1saat", "1h"),
        ("12h", "12h"),
        ("  5m  ", "5m"),
    ],
)
def test_parse_period_accepts_aliases(text, expected):
    assert parse_period(text).text == expected


@pytest.mark.parametrize("text", ["", "abc", "1", "0h", "1x", "1zzz", "-5m"])
def test_parse_period_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_period(text)


def test_period_ms_matches_canonical():
    assert period_ms("1H") == period_ms("1h")
    assert period_ms("1gün") == 86_400_000
    assert period_ms("1M") == period_ms("1ay")
    assert period_ms("bozuk") is None


def test_choose_base_period_uppercase_input():
    assert choose_base_period("2H", ["1m", "1h", "4h"]) == "1h"
    assert choose_base_period("1W", ["1d", "1w"]) == "1w"
