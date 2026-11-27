"""Günlük zarar limiti (canlı bot devre kesicisi)."""

from __future__ import annotations

from app.risk import daily_loss_exceeded


def test_limit_blocks_after_threshold():
    assert daily_loss_exceeded(1000, 970, 3) is True
    assert daily_loss_exceeded(1000, 970.01, 3) is False


def test_limit_is_disabled_when_zero_or_negative():
    assert daily_loss_exceeded(1000, 500, 0) is False
    assert daily_loss_exceeded(1000, 500, -2) is False


def test_unknown_start_does_not_block():
    assert daily_loss_exceeded(0, 500, 3) is False
    assert daily_loss_exceeded(None, 500, 3) is False


def test_profit_never_blocks():
    assert daily_loss_exceeded(1000, 1200, 3) is False


def test_invalid_values_do_not_block():
    assert daily_loss_exceeded("x", 900, 3) is False
    assert daily_loss_exceeded(1000, "x", 3) is False