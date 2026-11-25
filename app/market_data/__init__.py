"""Çoklu piyasa verisi katmanı.

Kripto (Binance), altın/gümüş ve hisse ile döviz (Yahoo Finance), türetilmiş
gram altın/gümüş (ons × USDTRY) ve TEFAS fonlarını tek bir OHLCV formatında
sunar. Canlı emir yalnızca Binance kripto sembolleriyle yapılabilir; diğer
varlıklar test/paper bot, backtest ve analiz içindir.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from app.market_data.catalog import (
    ASSET_CLASSES,
    SymbolInfo,
    available_periods,
    catalog,
    is_live_symbol,
    normalize_symbol,
    periods_for_provider,
    resolve_symbol,
    search_symbols,
)
from app.market_data.periods import Period, choose_base_period, parse_period, period_ms
from app.market_data.registry import clear_cache, load_history

__all__ = [
    "ASSET_CLASSES",
    "Period",
    "SymbolInfo",
    "available_periods",
    "catalog",
    "choose_base_period",
    "clear_cache",
    "is_live_symbol",
    "load_history",
    "normalize_symbol",
    "parse_period",
    "period_ms",
    "periods_for_provider",
    "resolve_symbol",
    "search_symbols",
]
