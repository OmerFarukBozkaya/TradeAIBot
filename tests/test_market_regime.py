"""Piyasa rejimi (BTC risk-on/risk-off) yardımcıları."""

from __future__ import annotations

from app.market_regime import ema, last_regime, regime_flags, regime_map


def test_ema_matches_manual_recursion():
    values = [1, 2, 3, 4, 5]
    result = ema(values, 3)
    k = 2 / 4
    expected = 1.0
    for value in values[1:]:
        expected = expected + k * (value - expected)
    assert result[0] == 1.0
    assert abs(result[-1] - expected) < 1e-9


def test_ema_handles_none_without_breaking():
    result = ema([None, 10, None, 20], 2)
    assert result[0] is None
    assert result[1] == 10.0
    assert result[2] == 10.0  # None mumda önceki değer korunur
    assert result[3] > 10.0


def test_regime_requires_enough_history():
    closes = list(range(1, 10))
    flags = regime_flags(closes, 20)
    assert flags == [True] * 9, "yetersiz geçmişte filtre uygulanmamalı"


def test_regime_tracks_uptrend_and_downtrend():
    up = [100.0 + i for i in range(300)]
    down = [400.0 - i for i in range(300)]
    assert last_regime(up, 200) is True
    assert last_regime(down, 200) is False


def test_regime_map_uses_candle_timestamps():
    closes = [100.0 + i for i in range(300)]
    data = {"opendate": [i * 1000 for i in range(300)], "close": closes}
    mapping = regime_map(data, 200)
    assert len(mapping) == 300
    assert mapping[0] is True
    assert mapping[299000] is True

    falling = {"opendate": [i * 1000 for i in range(300)],
               "close": [400.0 - i for i in range(300)]}
    assert regime_map(falling, 200)[299000] is False


def test_regime_map_empty_data():
    assert regime_map({}, 200) == {}
    assert regime_flags([], 200) == []
    assert last_regime([], 200) is True
