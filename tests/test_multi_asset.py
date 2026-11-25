"""Çoklu varlık: döviz, gram altın/gümüş ve sağlayıcıya özel periyotlar."""

from __future__ import annotations

import importlib

import pytest

from app.market_data import available_periods, load_history, resolve_symbol
from app.market_data.catalog import TROY_OUNCE_GRAMS, search_symbols
from app.market_data.providers.derived import merge_with_fx

catalog_mod = importlib.import_module("app.market_data.catalog")
derived_mod = importlib.import_module("app.market_data.providers.derived")


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setattr(catalog_mod, "_binance_symbols", lambda: [])
    monkeypatch.setattr(catalog_mod, "_tefas_funds", lambda: [])
    monkeypatch.setattr(catalog_mod, "_yahoo_search", lambda q, limit=12: [])


def test_grams_and_forex_resolution():
    gold = resolve_symbol("GAUTRY")
    assert gold.provider == "derived"
    assert gold.asset_class == "metal"
    assert "Gram" in gold.label

    silver = resolve_symbol("GUMUSTRY")
    assert silver.provider == "derived"

    # Türkçe yaygın yazımlar kanonik sembole döner.
    assert resolve_symbol("GRAMALTIN").symbol == "GAUTRY"
    assert resolve_symbol("ALTIN").symbol == "XAUUSD"

    forex = resolve_symbol("USDTRY")
    assert forex.provider == "yahoo"
    assert forex.native == "USDTRY=X"
    assert forex.asset_class == "forex"
    assert resolve_symbol("USDTRY=X").asset_class == "forex"


def test_available_periods_follow_provider_capabilities():
    fund = [item["id"] for item in available_periods("TEFAS:AFT")]
    assert fund == ["1d", "1w", "1M", "1y"]

    stock = [item["id"] for item in available_periods("GARAN.IS")]
    assert "1m" in stock and "1d" in stock and "1h" in stock
    assert "3m" not in stock

    crypto = [item["id"] for item in available_periods("BTCUSDT")]
    assert "3m" in crypto and "45m" in crypto

    metal = [item["id"] for item in available_periods("GAUTRY")]
    assert "1h" in metal and "1d" in metal


def test_search_lists_ounce_and_gram_metals(offline):
    metals = search_symbols("altın", "metal", 20)
    symbols = [item["symbol"] for item in metals]
    assert "XAUUSD" in symbols
    assert "GAUTRY" in symbols

    grams = search_symbols("gram", "metal", 20)
    assert {item["symbol"] for item in grams} >= {"GAUTRY", "GUMUSTRY"}

    forex = search_symbols("dolar", "forex", 20)
    assert any(item["symbol"] == "USDTRY" for item in forex)
    assert all(item["asset_class"] == "forex" for item in forex)


def test_merge_with_fx_converts_ounce_to_gram_try():
    stamps = [1_700_000_000_000, 1_700_086_400_000]
    metal = {
        "opendate": stamps,
        "open": [2000.0, 2050.0],
        "high": [2010.0, 2060.0],
        "low": [1990.0, 2040.0],
        "close": [2000.0, 2050.0],
        "closedate": [s + 86_400_000 - 1 for s in stamps],
    }
    fx = {
        "opendate": stamps,
        "close": [40.0, 41.0],
    }
    out = merge_with_fx(metal, fx, interval="1d")
    assert len(out["close"]) == 2
    assert out["close"][0] == pytest.approx(2000.0 * 40.0 / TROY_OUNCE_GRAMS)
    assert out["close"][1] == pytest.approx(2050.0 * 41.0 / TROY_OUNCE_GRAMS)
    assert out["high"][0] >= out["close"][0] >= out["low"][0]
    assert out["volume_coin"] == [0.0, 0.0]


def test_derived_fetch_combines_base_and_fx(monkeypatch):
    stamps = [1_700_000_000_000]
    metal = {
        "opendate": stamps, "open": [2000.0], "high": [2010.0],
        "low": [1990.0], "close": [2000.0],
        "closedate": [stamps[0] + 86_400_000 - 1],
    }
    fx = {"opendate": stamps, "close": [40.0]}

    def fake_fetch(info, interval, limit, *, start=None, end=None):
        return (metal if info.native == "GC=F" else fx), {"provider": "yahoo"}

    monkeypatch.setattr(derived_mod.yahoo, "fetch", fake_fetch)
    data, meta = derived_mod.fetch(
        resolve_symbol("GAUTRY"), "1d", 10
    )
    assert data["close"][0] == pytest.approx(2000.0 * 40.0 / TROY_OUNCE_GRAMS)
    assert meta["derived"] is True
    assert meta["derived_from"] == ["GC=F", "USDTRY=X"]


def test_load_history_uses_derived_provider(monkeypatch):
    """Registry, türetilmiş sağlayıcıyı doğru seçip önbelleğe yazmalı."""
    stamps = [1_700_000_000_000]
    data = {
        "opendate": stamps, "open": [5900.0], "high": [5950.0],
        "low": [5850.0], "close": [5900.0],
        "volume_coin": [0.0], "volume_usdt": [0.0],
        "trade_number": [0.0], "buy_coin_volume": [0.0],
        "buy_usdt_volume": [0.0], "closedate": [stamps[0] + 86_399_999],
    }
    called = {}

    def fake_fetch(info, interval, limit, *, start=None, end=None):
        called["provider"] = info.provider
        called["interval"] = interval
        return dict(data), {"derived": True, "derived_from": ["GC=F", "USDTRY=X"]}

    monkeypatch.setattr(derived_mod, "fetch", fake_fetch)
    loaded, meta = load_history("GAUTRY", "1d", 10, use_cache=False)
    assert called["provider"] == "derived"
    assert loaded["close"] == [5900.0]
    assert meta["provider"] == "derived"
    assert meta["asset_class"] == "metal"
