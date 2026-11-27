"""BTC rejim filtresi: backtest girişini gerçekten veto ediyor mu?"""

from __future__ import annotations

from app.job_runner import run_backtest

STEP_MS = 4 * 3600 * 1000  # 4h


def _times(n: int) -> list[int]:
    return [i * STEP_MS for i in range(n)]


def _series(n=600):
    """TrendRider'ın alım ürettiği yapay seri (konsolidasyon → yükseliş)."""
    close, high, low = [], [], []
    price = 100.0
    for i in range(n):
        if i < 260:
            price = 100.0 + ((i % 7) - 3) * 0.2
        elif i < 420:
            price *= 1.010 if (i % 7) < 5 else 0.985
        else:
            price *= 0.990 if (i % 7) < 5 else 1.004
        close.append(price)
        high.append(price * 1.008)
        low.append(price * 0.992)
    return high, low, close


def _run(btc_up: bool) -> dict:
    high, low, close = _series()
    n = len(close)
    data = {
        "close": close,
        "high": high,
        "low": low,
        "open": close,
        "opendate": _times(n),
        "volume_usdt": [1.0] * n,
    }
    btc_close = [100.0 + i for i in range(n)] if btc_up else [1000.0 - i for i in range(n)]
    btc_data = {"close": btc_close, "opendate": _times(n)}
    return run_backtest(
        {
            "strategy": {"type": "builtin", "name": "TrendRider"},
            "coin": "TESTUSDT",
            "period": "4h",
            "cash": 100.0,
            "limit": n,
            "risk": {
                "stop_atr": 3,
                "trail_atr": 6,
                "trail_after_pct": 8,
                "breakeven_pct": 15,
                "profit_exit_donchian": 10,
                "cooldown": 5,
                "risk_per_trade_pct": 4.0,
            },
            "filters": {"btc_regime": True},
            "_data": data,
            "_btc_data": btc_data,
        }
    )


def test_buy_blocked_when_btc_below_ema200():
    result = _run(btc_up=False)
    assert result["metrics"]["trade_count"] == 0


def test_trades_allowed_when_btc_above_ema200():
    result = _run(btc_up=True)
    assert result["metrics"]["trade_count"] > 0


def test_filter_off_by_default():
    high, low, close = _series()
    n = len(close)
    data = {
        "close": close, "high": high, "low": low, "open": close,
        "opendate": _times(n), "volume_usdt": [1.0] * n,
    }
    btc_data = {"close": [1000.0 - i for i in range(n)], "opendate": _times(n)}
    result = run_backtest(
        {
            "strategy": {"type": "builtin", "name": "TrendRider"},
            "coin": "TESTUSDT", "period": "4h", "cash": 100.0, "limit": n,
            "risk": {"stop_atr": 3, "risk_per_trade_pct": 4.0},
            "filters": {},
            "_data": data,
            "_btc_data": btc_data,
        }
    )
    assert result["metrics"]["trade_count"] > 0