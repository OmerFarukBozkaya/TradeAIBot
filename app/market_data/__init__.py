"""Çoklu piyasa verisi katmanı.

Kripto (Binance), altın/gümüş ve hisse (Yahoo Finance) ile TEFAS fonlarını
tek bir OHLCV formatında sunar. Yalnızca test/backtest/analiz içindir;
canlı işlem yalnızca Binance kripto sembolleriyle yapılabilir.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from app.market_data.catalog import (
    ASSET_CLASSES,
    SymbolInfo,
    catalog,
    is_live_symbol,
    normalize_symbol,
    resolve_symbol,
    search_symbols,
)
from app.market_data.periods import Period, choose_base_period, parse_period, period_ms
from app.market_data.registry import clear_cache, load_history

__all__ = [
    "ASSET_CLASSES",
    "Period",
    "SymbolInfo",
    "catalog",
    "choose_base_period",
    "clear_cache",
    "is_live_symbol",
    "load_history",
    "normalize_symbol",
    "parse_period",
    "period_ms",
    "resolve_symbol",
    "search_symbols",
]
