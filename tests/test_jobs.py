"""Tarama/iş yardımcıları."""

from app.jobs import _strategy_names, job_label


def test_strategy_names_builtin():
    params = {"strategies": [{"type": "builtin", "name": "MACD"}]}
    assert _strategy_names(params) == {"MACD": "MACD"}


def test_strategy_names_string_specs():
    params = {"strategies": ["BB_RSI", "MACD"]}
    assert _strategy_names(params) == {"BB_RSI": "BB_RSI", "MACD": "MACD"}


def test_job_label_turkish():
    assert job_label("scan") == "Tarama"
    assert job_label("backtest") == "Backtest"
    assert job_label("bilinmeyen") == "bilinmeyen"
