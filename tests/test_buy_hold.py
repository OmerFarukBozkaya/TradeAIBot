"""Al-tut metriğinin doğruluğu (sabit artan seri)."""

from app.strategies.compiler import compile_strategy
from app.strategies.registry import IndicatorCache


def make_data(n=300, start=100.0, step=1.0):
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


def buy_hold_math(data, warmup, cash=100.0, fee=0.001, slippage=0.0005):
    start_idx = max(warmup, 2) - 1
    end_idx = len(data["close"]) - 2
    entry = data["close"][start_idx] * (1 + slippage) * (1 + fee)
    qty = cash / entry
    final = qty * data["close"][end_idx] * (1 - slippage) * (1 - fee)
    return (final / cash - 1) * 100, start_idx, end_idx


def test_buy_hold_formula_monotonic():
    data = make_data(300, 100.0, 1.0)
    pct, s, e = buy_hold_math(data, 60)
    # artan seride al-tut pozitif olmalı
    assert pct > 0
    assert e > s
    # kabaca fiyat artışına yakın (komisyon/kayma düşük)
    price_gain = (data["close"][e] / data["close"][s] - 1) * 100
    assert abs(pct - price_gain) < 1.0


def test_buy_hold_flat_series_is_negative():
    data = make_data(300, 100.0, 0.0)
    pct, _, _ = buy_hold_math(data, 60)
    # sabit fiyatta maliyetler nedeniyle negatif
    assert pct < 0
