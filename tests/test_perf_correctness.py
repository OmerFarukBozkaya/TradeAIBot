"""Performans optimizasyonlarının doğruluğu bozmadığını kanıtlayan testler.

Bu testler, optimize edilmiş indikatörleri **referans (saf) uygulamalarla**
karşılaştırır. Formülde en ufak sapma testi kırar.
"""

import math

import numpy as np
import pytest

from app.strategies.compiler import compile_strategy
from app.strategies.registry import INDICATORS, IndicatorCache


def make_data(n=800, seed=11, vol=0.005):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    spread = np.abs(rng.normal(0, 0.003, n)) * close
    return {
        "open": np.concatenate([[close[0]], close[:-1]]).tolist(),
        "high": (close + spread).tolist(),
        "low": (close - spread).tolist(),
        "close": close.tolist(),
        "volume_coin": rng.uniform(1, 5, n).tolist(),
        "volume_usdt": (rng.uniform(1, 5, n) * close).tolist(),
        "opendate": list(range(n)),
    }


def test_bollinger_matches_reference_definition():
    data = make_data()
    cache = IndicatorCache(data)
    lower = cache.compute("BB", {"length": 20, "std": 2.0}, "lower")
    upper = cache.compute("BB", {"length": 20, "std": 2.0}, "upper")
    close = data["close"]
    for i in range(19, len(close)):
        window = close[i - 19:i + 1]
        mean = sum(window) / 20
        # Referans: popülasyon standart sapması (np.std varsayılanı)
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / 20)
        assert lower[i] == pytest.approx(mean - 2 * std, rel=1e-9, abs=1e-9)
        assert upper[i] == pytest.approx(mean + 2 * std, rel=1e-9, abs=1e-9)


def test_supertrend_matches_reference_loop():
    """Optimize edilmiş Super_Trend, satır satır referansla aynı olmalı."""
    data = make_data(n=600, seed=5)
    high, low, close = data["high"], data["low"], data["close"]
    atr_length, factor = 10, 5.0

    # Referans uygulama (pandas'siz, düz Python — eski algoritmanın birebir hâli)
    tr = []
    for i in range(len(close)):
        prev = close[i - 1] if i > 0 else None
        if prev is None:
            tr.append(high[i] - low[i])
        else:
            tr.append(max(high[i] - low[i], abs(high[i] - prev), abs(low[i] - prev)))
    atr = [None] * len(close)
    for i in range(atr_length - 1, len(close)):
        atr[i] = sum(tr[i - atr_length + 1:i + 1]) / atr_length
    hl2 = [(high[i] + low[i]) / 2 for i in range(len(close))]
    upper = [hl2[i] + factor * atr[i] if atr[i] is not None else None for i in range(len(close))]
    lower = [hl2[i] - factor * atr[i] if atr[i] is not None else None for i in range(len(close))]

    st = [None] * len(close)
    direction = [None] * len(close)
    for i in range(atr_length, len(close)):
        if i == atr_length:
            st[i] = lower[i]
            direction[i] = 1
            continue
        if close[i] > st[i - 1]:
            st[i], d = lower[i], 1
        elif close[i] < st[i - 1]:
            st[i], d = upper[i], -1
        else:
            st[i], d = st[i - 1], direction[i - 1]
        if d == 1:
            st[i] = min(st[i], upper[i])
        elif d == -1:
            st[i] = max(st[i], lower[i])
        direction[i] = d

    cache = IndicatorCache(data)
    got_st = cache.compute("SUPERTREND", {"atr_length": atr_length, "factor": factor}, "value")
    got_dir = cache.compute("SUPERTREND", {"atr_length": atr_length, "factor": factor}, "direction")

    assert len(got_st) == len(st)
    for i in range(len(st)):
        if st[i] is None:
            assert got_st[i] is None
        else:
            assert got_st[i] == pytest.approx(st[i], rel=1e-9, abs=1e-9)
        assert got_dir[i] == direction[i]


def _entry_definition(conditions):
    return {
        "name": "regresyon",
        "buy": {"logic": "AND", "conditions": conditions},
        "sell": {"logic": "AND", "conditions": conditions},
    }


def test_detail_mode_and_shortcircuit_agree():
    """Kısa devre (backtest) ile detaylı mod aynı sinyali vermeli."""
    data = make_data(n=400, seed=3)
    gap = {
        "left": {"type": "price", "field": "close"},
        "op": "gt",
        "right": {"type": "constant", "value": 1e9},  # her zaman False
    }
    second = {
        "left": {"type": "price", "field": "close"},
        "op": "gt",
        "right": {"type": "constant", "value": 0},
    }
    definition = _entry_definition([gap, second])
    compiled = compile_strategy(definition, "reg", 1)
    cache = IndicatorCache(data)
    for idx in range(compiled.warmup, len(data["close"]) - 1):
        fast = compiled.evaluate_at(data, cache, idx, detail=False)
        full = compiled.evaluate_at(data, cache, idx, detail=True)
        assert fast["buy"] == full["buy"]
        assert fast["sell"] == full["sell"]
        # Detaylı modda tüm koşulların açıklaması bulunmalı
        assert len(full["buy_detail"]["conditions"]) == 2


def test_operand_cache_is_keyed_by_identity_not_json():
    """Aynı operand nesnesi tekrar çözülürken yeniden hesaplanmamalı."""
    data = make_data(n=300, seed=9)
    cache = IndicatorCache(data)
    operand = {
        "left": {"type": "indicator", "id": "EMA", "params": {"length": 20}, "output": "value"},
        "op": "gt",
        "right": {"type": "constant", "value": 0},
    }
    definition = _entry_definition([operand])
    compiled = compile_strategy(definition, "reg2", 1)
    calls = {"n": 0}

    original = INDICATORS["EMA"]["fn"]

    def counting(data_arg, params):
        calls["n"] += 1
        return original(data_arg, params)

    INDICATORS["EMA"]["fn"] = counting
    try:
        for idx in range(60, 120):
            compiled.evaluate_at(data, cache, idx, detail=False)
    finally:
        INDICATORS["EMA"]["fn"] = original
    # 60 mum için EMA bir kez hesaplanmalı (cache)
    assert calls["n"] == 1
