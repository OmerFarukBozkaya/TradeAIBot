"""Yeni indikatörler: Tillson T3 ve QQE MOD."""

import random

from app.strategies.compiler import compile_strategy
from app.strategies.registry import INDICATORS, IndicatorCache


def synthetic(n=300, seed=7):
    random.seed(seed)
    close = [100.0]
    for _ in range(n - 1):
        close.append(max(1.0, close[-1] * (1 + random.uniform(-0.02, 0.02))))
    return {
        "open": close,
        "high": [c * 1.01 for c in close],
        "low": [c * 0.99 for c in close],
        "close": close,
        "volume_coin": [1.0] * n,
        "volume_usdt": [100.0] * n,
        "opendate": list(range(n)),
    }


def constant(n=200, value=42.0):
    return {
        "open": [value] * n,
        "high": [value] * n,
        "low": [value] * n,
        "close": [value] * n,
        "volume_coin": [1.0] * n,
        "volume_usdt": [100.0] * n,
        "opendate": list(range(n)),
    }


def test_t3_registered_with_expected_outputs():
    spec = INDICATORS["T3"]
    assert spec["category"] == "trend"
    assert set(spec["outputs"]) == {"value", "direction", "slope"}
    names = {p["name"] for p in spec["params"]}
    assert names == {"length", "factor"}


def test_t3_of_constant_series_is_constant():
    # T3 katsayılarının toplamı 1'dir; sabit seride çıktı sabit kalmalı.
    data = constant(200, 42.0)
    cache = IndicatorCache(data)
    values = cache.compute("T3", {"length": 8, "factor": 0.7}, "value")
    assert len(values) == len(data["close"])
    assert all(abs(v - 42.0) < 1e-6 for v in values)


def test_t3_direction_matches_slope():
    data = synthetic()
    cache = IndicatorCache(data)
    values = cache.compute("T3", {"length": 8, "factor": 0.7}, "value")
    direction = cache.compute("T3", {"length": 8, "factor": 0.7}, "direction")
    for i in range(1, len(values)):
        if values[i] is None or values[i - 1] is None:
            continue
        expected = 1 if values[i] > values[i - 1] else (-1 if values[i] < values[i - 1] else 0)
        assert direction[i] == expected


def test_qqe_registered_with_outputs():
    spec = INDICATORS["QQE_MOD"]
    assert spec["category"] == "momentum"
    for output in ("signal", "direction", "trend", "rsi", "upper", "lower",
                   "secondary_rsi", "secondary_trend"):
        assert output in spec["outputs"]


def test_qqe_signal_values_are_valid():
    data = synthetic()
    cache = IndicatorCache(data)
    params = {p["name"]: p["default"] for p in INDICATORS["QQE_MOD"]["params"]}
    signal = cache.compute("QQE_MOD", params, "signal")
    assert len(signal) == len(data["close"])
    assert set(signal) <= {-1, 0, 1}
    # Sinyal üretebilmesi için en az bir yönlü sinyal beklenir.
    assert any(v != 0 for v in signal)


def test_qqe_bands_ordering():
    data = synthetic()
    cache = IndicatorCache(data)
    upper = cache.compute("QQE_MOD", {}, "upper")
    lower = cache.compute("QQE_MOD", {}, "lower")
    checked = 0
    for u, l in zip(upper, lower):
        if u is None or l is None:
            continue
        assert u >= l
        checked += 1
    assert checked > 0


def test_qqe_hist_state_matches_signal():
    data = synthetic()
    cache = IndicatorCache(data)
    signal = cache.compute("QQE_MOD", {}, "signal")
    state = cache.compute("QQE_MOD", {}, "hist_state")
    histogram = cache.compute("QQE_MOD", {}, "histogram")
    assert len(state) == len(signal) == len(histogram)
    assert set(state) <= {"blue", "red", "gray", "none"}
    for i, value in enumerate(signal):
        if value == 1:
            assert state[i] == "blue"
        elif value == -1:
            assert state[i] == "red"
        else:
            # Sinyal yoksa mavi/kırmızı olmamalı.
            assert state[i] in {"gray", "none"}
    assert any(s == "blue" for s in state)
    assert any(s == "red" for s in state)


def test_warmup_accounts_for_indicator_defaults():
    from app.strategies.registry import warmup_of

    definition = {
        "name": "QQE",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "indicator", "id": "QQE_MOD", "params": {}, "output": "signal"},
                    "op": "eq",
                    "right": {"type": "constant", "value": 1},
                }
            ],
        },
        "sell": {"logic": "AND", "conditions": []},
    }
    # QQE'nin varsayılan bb_length=50 olması ısınmayı 150 mum yapar.
    assert warmup_of(definition) >= 150


def test_strategy_with_t3_and_qqe_compiles():
    definition = {
        "name": "T3 + QQE",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "indicator", "id": "T3", "params": {"length": 8, "factor": 0.7}, "output": "direction"},
                    "op": "eq",
                    "right": {"type": "constant", "value": 1},
                },
                {
                    "left": {"type": "indicator", "id": "QQE_MOD", "params": {}, "output": "signal"},
                    "op": "eq",
                    "right": {"type": "constant", "value": 1},
                },
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "indicator", "id": "T3", "params": {"length": 8, "factor": 0.7}, "output": "direction"},
                    "op": "eq",
                    "right": {"type": "constant", "value": -1},
                },
                {
                    "left": {"type": "indicator", "id": "QQE_MOD", "params": {}, "output": "signal"},
                    "op": "eq",
                    "right": {"type": "constant", "value": -1},
                },
            ],
        },
    }
    strategy = compile_strategy(definition, "t3qqe")
    result = strategy.evaluate(synthetic(400))
    assert isinstance(result["buy"], bool)
    assert isinstance(result["sell"], bool)
