"""Piyasa verisi sağlayıcıları."""

from app.market_data.providers import binance, derived, tefas, yahoo

PROVIDERS = {
    "binance": binance,
    "yahoo": yahoo,
    "tefas": tefas,
    "derived": derived,
}

__all__ = ["PROVIDERS", "binance", "derived", "tefas", "yahoo"]
