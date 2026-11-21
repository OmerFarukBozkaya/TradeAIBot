"""Sembol arama: yerel katalog, sınıf filtresi ve sağlayıcı sonuçları."""

from __future__ import annotations

import pytest

import importlib

from app.market_data.catalog import search_symbols

catalog_mod = importlib.import_module("app.market_data.catalog")


@pytest.fixture()
def offline(monkeypatch):
    """Ağa çıkmadan arama yap."""
    monkeypatch.setattr(catalog_mod, "_binance_symbols", lambda: [
        {"symbol": "FETUSDT", "label": "FET / USDT", "asset_class": "crypto", "provider": "binance"},
        {"symbol": "BTCUSDT", "label": "BTC / USDT", "asset_class": "crypto", "provider": "binance"},
    ])
    monkeypatch.setattr(catalog_mod, "_tefas_funds", lambda: [
        {"symbol": "TEFAS:AFT", "label": "AFT - Ak Portföy Teknoloji", "asset_class": "fund", "provider": "tefas"},
        {"symbol": "TEFAS:MAC", "label": "MAC - Marmara Capital", "asset_class": "fund", "provider": "tefas"},
    ])
    monkeypatch.setattr(catalog_mod, "_yahoo_search", lambda q, limit=12: [
        {"symbol": "GARAN.IS", "label": "Garanti BBVA", "asset_class": "stock", "provider": "yahoo"},
    ])


def test_catalog_lists_crypto_and_classes():
    data = catalog_mod.catalog()
    assert data["crypto"]
    assert any(item["symbol"] == "BTCUSDT" for item in data["crypto"])
    assert {item["id"] for item in data["classes"]} == {"crypto", "metal", "stock", "fund"}


def test_empty_query_returns_popular_for_class(offline):
    metals = search_symbols("", "metal", 10)
    assert [item["symbol"] for item in metals][:2] == ["XAUUSD", "XAUUSDSPOT"]
    assert all(item["asset_class"] == "metal" for item in metals)

    crypto = search_symbols("", "crypto", 5)
    assert all(item["asset_class"] == "crypto" for item in crypto)
    assert crypto[0]["live"] is True


def test_search_folds_turkish_characters(offline):
    gold = search_symbols("altın", "", 10)
    assert "XAUUSD" in [item["symbol"] for item in gold]

    silver = search_symbols("gümüş", "", 10)
    assert "XAGUSD" in [item["symbol"] for item in silver]


def test_search_matches_symbol_prefix_first(offline):
    items = search_symbols("btc", "crypto", 10)
    assert items[0]["symbol"].startswith("BTC")
    assert all(item["asset_class"] == "crypto" for item in items)


def test_search_includes_remote_providers(offline):
    stocks = search_symbols("garanti", "", 10)
    assert any(item["symbol"] == "GARAN.IS" for item in stocks)

    funds = search_symbols("aft", "fund", 10)
    assert any(item["symbol"] == "TEFAS:AFT" for item in funds)

    crypto = search_symbols("fet", "crypto", 10)
    assert any(item["symbol"] == "FETUSDT" for item in crypto)


def test_search_filters_class_and_deduplicates(offline):
    items = search_symbols("btc", "", 20)
    symbols = [item["symbol"] for item in items]
    assert len(symbols) == len(set(symbols))
    # Sınıf filtresi verilince yahoo/tefas sonuçları karışmamalı.
    only_funds = search_symbols("a", "fund", 10)
    assert all(item["asset_class"] == "fund" for item in only_funds)


def test_search_respects_limit(offline):
    items = search_symbols("a", "", 3)
    assert len(items) <= 3
