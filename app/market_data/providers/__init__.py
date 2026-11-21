"""Piyasa verisi sağlayıcıları."""

from app.market_data.providers import binance, tefas, yahoo

PROVIDERS = {
    "binance": binance,
    "yahoo": yahoo,
    "tefas": tefas,
}

__all__ = ["PROVIDERS", "binance", "tefas", "yahoo"]
