import math

import numpy as np
import pytest

from app.strategies.compiler import (
    StrategyValidationError,
    compile_strategy,
    validate_definition,
)
from app.strategies.registry import IndicatorCache, catalog


def make_data(n=300, start=100.0, step=0.1):
    close = [start + i * step for i in range(n)]
    return {
        "open": close,
        "high": [c * 1.01 for c in close],
        "low": [c * 0.99 for c in close],
        "close": close,
        "volume_coin": [1.0] * n,
        "volume_usdt": [100.0] * n,
        "opendate": list(range(n)),
    }


def rsi_definition():
    return {
        "name": "RSI test",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
                    "op": "lt",
                    "right": {"type": "constant", "value": 35},
                }
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
                    "op": "gt",
                    "right": {"type": "constant", "value": 65},
                }
            ],
        },
    }


def test_catalog_not_empty():
    items = catalog()
    assert len(items) >= 15
    assert all("id" in i and "params" in i for i in items)


def test_validation_ok():
    assert validate_definition(rsi_definition()) == []


def test_validation_catches_bad_indicator():
    definition = rsi_definition()
    definition["buy"]["conditions"][0]["left"]["id"] = "NOPE"
    errors = validate_definition(definition)
    assert any("bilinmeyen indikatör" in e for e in errors)


def test_validation_catches_contradiction():
    definition = rsi_definition()
    definition["buy"]["conditions"] = [
        {
            "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
            "op": "lt",
            "right": {"type": "constant", "value": 20},
        },
        {
            "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
            "op": "gt",
            "right": {"type": "constant", "value": 80},
        },
    ]
    assert any("çelişkili" in e for e in validate_definition(definition))


def test_compile_and_evaluate():
    strategy = compile_strategy(rsi_definition(), "rsi")
    data = make_data()
    result = strategy.evaluate(data)
    assert result["warmup_ok"] is True
    assert result["candle_index"] == len(data["close"]) - 2
    assert isinstance(result["buy"], bool)


def test_rising_market_has_no_buy_but_sell():
    strategy = compile_strategy(rsi_definition(), "rsi")
    result = strategy.evaluate(make_data())
    assert result["sell"] is True
    assert result["buy"] is False


def test_crosses_above():
    definition = {
        "name": "cross",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "crosses_above",
                    "right": {"type": "indicator", "id": "EMA", "params": {"length": 5}, "output": "value"},
                }
            ],
        },
        "sell": {"logic": "AND", "conditions": []},
    }
    strategy = compile_strategy(definition, "cross")
    data = make_data(120, start=110)
    # keskin düşüş sonrası toparlanma
    for i in range(90, 100):
        data["close"][i] = 100 - (i - 90)
        data["high"][i] = data["close"][i] * 1.01
        data["low"][i] = data["close"][i] * 0.99
    for i in range(100, 110):
        data["close"][i] = 95 + (i - 100) * 3
        data["high"][i] = data["close"][i] * 1.01
        data["low"][i] = data["close"][i] * 0.99
    result = strategy.evaluate(data)
    assert isinstance(result["buy"], bool)


def test_normalization_lengths():
    data = make_data(200)
    cache = IndicatorCache(data)
    for name, spec in [(i["id"], i) for i in catalog()]:
        series = cache.compute(name, {p["name"]: p["default"] for p in spec["params"]}, spec["outputs"][0])
        assert len(series) == len(data["close"]), name


def test_parity_slice_vs_at():
    data = make_data(300)
    strategy = compile_strategy(rsi_definition(), "rsi")
    idx = 250
    cache = IndicatorCache(data)
    at_result = strategy.evaluate_at(data, cache, idx)
    sliced = {k: v[: idx + 2] for k, v in data.items()}
    slice_result = strategy.evaluate(sliced)
    assert at_result["buy"] == slice_result["buy"]
    assert at_result["sell"] == slice_result["sell"]


def test_operand_memo_matches_fresh_cache():
    """Önbellekli operand çözümü, her mum için taze cache ile aynı sonucu verir."""
    data = make_data(260)
    strategy = compile_strategy(rsi_definition(), "rsi")
    shared = IndicatorCache(data)
    for idx in range(strategy.warmup, len(data["close"]) - 1, 7):
        expected = strategy.evaluate_at(data, IndicatorCache(data), idx)
        actual = strategy.evaluate_at(data, shared, idx)
        assert actual["buy"] == expected["buy"]
        assert actual["sell"] == expected["sell"]
        assert actual["buy_detail"] == expected["buy_detail"]


def test_operand_series_cached_across_candles():
    """Aynı cache ile farklı mumlar değerlendirilince seriler yeniden kurulmaz."""
    data = make_data(120)
    strategy = compile_strategy(rsi_definition(), "rsi")
    cache = IndicatorCache(data)
    strategy.evaluate_at(data, cache, 60)
    produced = len(cache._operand_memo)
    assert produced > 0
    strategy.evaluate_at(data, cache, 61)
    assert len(cache._operand_memo) == produced


def test_invalid_strategy_raises():
    with pytest.raises(StrategyValidationError):
        compile_strategy({"name": "x", "buy": {"conditions": []}}, "x")


def test_builtin_parity_prepared():
    from app.strategies.builtin import BuiltinStrategy

    data = make_data(400)
    strategy = BuiltinStrategy("BB_RSI")
    lazy = strategy.evaluate(data)
    strategy.prepare(data)
    fast = strategy.evaluate_at(data, len(data["close"]) - 2)
    assert lazy["buy"] == fast["buy"]
    assert lazy["sell"] == fast["sell"]


def _eq(left, right):
    return {
        "left": {"type": "constant", "value": left},
        "op": "eq",
        "right": {"type": "constant", "value": right},
    }


def test_nested_group_or_of_and():
    t, f = _eq(1, 1), _eq(1, 2)
    definition = {
        "name": "gruplu",
        "buy": {
            "logic": "OR",
            "conditions": [
                {"logic": "AND", "conditions": [t, f]},
                {"logic": "AND", "conditions": [t, t]},
            ],
        },
        "sell": {"logic": "AND", "conditions": [f]},
    }
    assert validate_definition(definition) == []
    result = compile_strategy(definition, "gruplu").evaluate(make_data())
    assert result["buy"] is True
    assert result["sell"] is False
    detail = result["buy_detail"]
    assert detail["logic"] == "OR"
    assert detail["conditions"][0]["result"] is False
    assert detail["conditions"][1]["result"] is True


def test_nested_group_and_of_or():
    t, f = _eq(1, 1), _eq(1, 2)
    definition = {
        "name": "gruplu2",
        "buy": {
            "logic": "AND",
            "conditions": [
                {"logic": "OR", "conditions": [f, t]},
                t,
            ],
        },
        "sell": {"logic": "AND", "conditions": [t]},
    }
    result = compile_strategy(definition, "gruplu2").evaluate(make_data())
    assert result["buy"] is True


def _flat_data(n=100, value=50.0):
    return {
        "open": [value] * n,
        "high": [value] * n,
        "low": [value] * n,
        "close": [value] * n,
        "volume_coin": [1.0] * n,
        "volume_usdt": [100.0] * n,
        "opendate": list(range(n)),
    }


def test_offset_reads_previous_candle():
    """offset operandı, seriyi N mum kaydırır: karşılaştırma önceki muma bakar."""
    data = _flat_data(100)
    data["close"][-3] = 100.0   # önceki mum (idx-1)
    data["close"][-2] = 101.0   # değerlendirilen mum (idx)
    definition = {
        "name": "offset",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "gt",
                    "right": {
                        "type": "offset",
                        "shift": 1,
                        "operand": {"type": "price", "field": "close"},
                    },
                }
            ],
        },
        "sell": {"logic": "AND", "conditions": []},
    }
    result = compile_strategy(definition, "offset").evaluate(data)
    assert result["buy"] is True


def test_crosses_above_previous_equals_current_crosses():
    """Önceki mumda eşitlik kesişmeyi engellemez: a>b ve a_prev<=b_prev yeterli."""
    data = _flat_data(100)
    data["close"][-3] = 100.0  # önceki mum: eşit
    data["close"][-2] = 101.0  # bu mum: yukarıda
    definition = {
        "name": "cross-eq-prev",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "crosses_above",
                    "right": {"type": "constant", "value": 100},
                }
            ],
        },
        "sell": {"logic": "AND", "conditions": []},
    }
    assert compile_strategy(definition, "c1").evaluate(data)["buy"] is True


def test_crosses_above_current_equal_is_not_cross():
    """Bu mumda eşitlik kesişme sayılmaz (a > b şartı sağlanmaz)."""
    data = _flat_data(100)
    data["close"][-3] = 99.0   # önceki mum altta
    data["close"][-2] = 100.0  # bu mum eşit
    definition = {
        "name": "cross-eq-now",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "crosses_above",
                    "right": {"type": "constant", "value": 100},
                }
            ],
        },
        "sell": {"logic": "AND", "conditions": []},
    }
    assert compile_strategy(definition, "c2").evaluate(data)["buy"] is False


def test_crosses_below_previous_equals():
    data = _flat_data(100)
    data["close"][-3] = 100.0
    data["close"][-2] = 99.0
    definition = {
        "name": "cross-below-eq",
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "constant", "value": 1},
                    "op": "eq",
                    "right": {"type": "constant", "value": 1},
                }
            ],
        },
        "sell": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "crosses_below",
                    "right": {"type": "constant", "value": 100},
                }
            ],
        },
    }
    assert compile_strategy(definition, "c3").evaluate(data)["sell"] is True
