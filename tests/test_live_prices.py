"""Anlık fiyat servisi: sembol bazlı önbellek ve hata yalıtımı."""

from __future__ import annotations

import json
import time

import pytest
import requests

from app import live_prices


@pytest.fixture(autouse=True)
def _clean_cache():
    live_prices.reset()
    yield
    live_prices.reset()


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def test_prices_fetch_and_cache(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(json.loads(params["symbols"]))
        symbols = json.loads(params["symbols"])
        return FakeResponse([{"symbol": s, "price": "1.5"} for s in symbols])

    monkeypatch.setattr(live_prices.requests, "get", fake_get)

    assert live_prices.prices(["BTCUSDT"]) == {"BTCUSDT": 1.5}
    # TTL içinde tekrar istek yok.
    assert live_prices.prices(["BTCUSDT"]) == {"BTCUSDT": 1.5}
    assert len(calls) == 1


def test_expired_symbol_refreshes_only_itself(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        symbols = json.loads(params["symbols"])
        calls.append(symbols)
        return FakeResponse([{"symbol": s, "price": "2"} for s in symbols])

    monkeypatch.setattr(live_prices.requests, "get", fake_get)
    live_prices.prices(["BTCUSDT"])
    live_prices._seen_at["BTCUSDT"] = time.time() - 100  # BTC süresi doldu

    out = live_prices.prices(["BTCUSDT", "ETHUSDT"])
    assert out == {"BTCUSDT": 2.0, "ETHUSDT": 2.0}
    # İkisi de süresi dolmuş kabul edilir; tek partide istenir.
    assert calls[-1] == ["BTCUSDT", "ETHUSDT"]
    assert len(calls) == 2


def test_invalid_symbol_does_not_block_valid_symbols(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        symbols = json.loads(params["symbols"])
        calls.append(list(symbols))
        if "BADUSDT" in symbols:
            return FakeResponse({"code": -1121, "msg": "Invalid symbol."}, status=400)
        return FakeResponse([{"symbol": s, "price": "3"} for s in symbols])

    monkeypatch.setattr(live_prices.requests, "get", fake_get)

    out = live_prices.prices(["BADUSDT", "BTCUSDT"])
    assert out == {"BTCUSDT": 3.0}
    assert "BADUSDT" not in out
    # Geçersiz sembol kısa süre tekrar denenmez; geçerli sembol önbellekten gelir.
    before = len(calls)
    assert live_prices.prices(["BADUSDT", "BTCUSDT"]) == {"BTCUSDT": 3.0}
    assert len(calls) == before


def test_network_error_keeps_previous_prices(monkeypatch):
    def ok_get(url, params=None, timeout=None):
        symbols = json.loads(params["symbols"])
        return FakeResponse([{"symbol": s, "price": "4"} for s in symbols])

    monkeypatch.setattr(live_prices.requests, "get", ok_get)
    assert live_prices.prices(["BTCUSDT"]) == {"BTCUSDT": 4.0}

    def broken_get(url, params=None, timeout=None):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(live_prices.requests, "get", broken_get)
    live_prices._seen_at["BTCUSDT"] = time.time() - 100

    # Ağ hatasında son bilinen fiyat korunur (gösterge sıfırlanmaz).
    assert live_prices.prices(["BTCUSDT"]) == {"BTCUSDT": 4.0}
