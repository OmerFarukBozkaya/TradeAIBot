"""Backtest risk oranları: Sharpe / Sortino (yıllıklandırılmış)."""

from __future__ import annotations

from app.job_runner import _periods_per_year, _risk_ratios


def test_periods_per_year_for_4h():
    # 365,25 gün × 6 mum/gün
    assert abs(_periods_per_year("4h") - 2191.5) < 1e-6


def test_sharpe_positive_for_rising_equity():
    equity = [100, 101, 100.5, 102, 103, 102.5, 104, 105]
    sharpe, sortino = _risk_ratios(equity, "4h")
    assert sharpe is not None and sharpe > 0
    assert sortino is not None and sortino > sharpe  # downside daha küçük


def test_sharpe_negative_for_falling_equity():
    equity = [100, 99, 99.5, 98, 97, 97.5, 96, 95]
    sharpe, _ = _risk_ratios(equity, "4h")
    assert sharpe is not None and sharpe < 0


def test_flat_equity_has_no_ratio():
    assert _risk_ratios([100, 100, 100, 100], "4h") == (None, None)
    assert _risk_ratios([100, 101], "4h") == (None, None)


def test_unknown_period_returns_none():
    assert _risk_ratios([100, 101, 102, 103], "bilinmeyen") == (None, None)