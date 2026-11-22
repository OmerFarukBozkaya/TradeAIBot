"""Borsa emir yardımcıları: parite filtreleri, adet yuvarlama, hata sınıflandırma.

Emir gönderirken en sık yapılan hatalar burada tek yerde toplanır:

- Adet ``stepSize``'a göre **aşağı** yuvarlanmalı (``minQty`` ile karıştırılmaz).
- Fiyat ``tickSize``'a göre yuvarlanmalı.
- ``minNotional`` (minimum işlem tutarı) ve ``maxQty`` kontrol edilmeli.
- Kalıcı hatalar (geçersiz anahtar, filtre ihlali, yetersiz bakiye) ile geçici
  hatalar (zaman aşımı, 429, 5xx) ayrılmalı; yalnızca geçici olanlar tekrar
  denenmeli.
"""

from __future__ import annotations

import re
import secrets
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, Optional

DEFAULT_MIN_NOTIONAL = 5.0

# Aynı isteği tekrar denemek anlamsız (parametre/anahtar/bakiye kaynaklı).
PERMANENT_CODES = frozenset(
    {
        -1013,  # filtre ihlali (LOT_SIZE, MIN_NOTIONAL...)
        -1022,  # imza hatası
        -1099,  # istek bulunamadı / imza
        -1100, -1101, -1102, -1104, -1106, -1111, -1117, -1118, -1121,
        -1130,
        -2010,  # emir reddedildi (yetersiz bakiye, minimum tutar...)
        -2011,  # iptal reddedildi
        -2013,  # emir yok
        -2014,  # API anahtarı biçimi
        -2015,  # geçersiz anahtar / izinler
    }
)

# Kısa bekleme sonrası tekrar denenebilir.
TRANSIENT_CODES = frozenset(
    {
        -1000, -1001, -1003, -1006, -1007, -1015, -1016, -1021,
    }
)

_TRANSIENT_TEXT = (
    "429", "418", "500", "502", "503", "504",
    "timed out", "timeout", "connection", "temporary", "unavailable",
    "disconnect", "too many requests", "service unavailable", "bad gateway",
    "gateway timeout", "name resolution", "ssl", "unable to open database file",
    "database is locked",
)

_QUOTES = ("USDT", "FDUSD", "BUSD", "USDC", "TUSD", "TRY", "BTC", "ETH", "BNB", "EUR")


def asset_of(symbol: str) -> str:
    """``BTCUSDT`` → ``BTC`` (bilinen quote varlıkları sırayla denenir)."""
    text = str(symbol or "").upper()
    for quote in _QUOTES:
        if text.endswith(quote) and len(text) > len(quote):
            return text[: -len(quote)]
    return text


def error_code(exc: BaseException) -> Optional[int]:
    """Binance hata kodunu (``-2010`` gibi) çıkarır."""
    for attr in ("code", "status_code"):
        try:
            value = getattr(exc, attr, None)
        except Exception:  # pragma: no cover - egzotik istisna
            value = None
        if isinstance(value, int):
            return value
    match = re.search(r"(-1\d{3}|-2\d{3})\b", str(exc))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def http_status(exc: BaseException) -> Optional[int]:
    try:
        value = getattr(exc, "status_code", None)
    except Exception:  # pragma: no cover
        return None
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    match = re.search(r"\b(4\d{2}|5\d{2})\b", str(exc))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def is_permanent(exc: BaseException) -> bool:
    """Tekrar denemek sonucu değiştirmeyecek hata mı?"""
    code = error_code(exc)
    if code in PERMANENT_CODES:
        return True
    text = str(exc).lower()
    if "invalid api-key" in text or "invalid api key" in text:
        return True
    if "signature" in text and "invalid" in text:
        return True
    if code in TRANSIENT_CODES:
        return False
    status = http_status(exc)
    if status in (429, 418) or (status is not None and status >= 500):
        return False
    return any(token in text for token in ("lot_size", "min_notional", "filter failure",
                                           "insufficient balance", "rejected"))


def is_transient(exc: BaseException) -> bool:
    """Kısa bekleyip tekrar denemeye değer hata mı?"""
    if is_permanent(exc):
        return False
    code = error_code(exc)
    if code in TRANSIENT_CODES:
        return True
    status = http_status(exc)
    if status in (429, 418) or (status is not None and status >= 500):
        return True
    text = str(exc).lower()
    return any(token in text for token in _TRANSIENT_TEXT)


def retry_delay(exc: BaseException, attempt: int) -> float:
    """Artan bekleme; 429/418'de daha uzun (borsa kendini korumaya alır)."""
    status = http_status(exc)
    base = 8.0 if status in (429, 418) else 2.0
    delay = base * (attempt + 1)
    # Küçük rastgelelik: aynı anda deneyen botlar üst üste binmesin.
    jitter = 1 + (secrets.randbelow(500) / 1000.0)
    return min(60.0, delay * jitter)


# ----------------------------------------------------------------------
# Parite filtreleri
# ----------------------------------------------------------------------
def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def symbol_filters(exchange_info: Optional[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """``exchangeInfo`` yanıtından sembolün emir filtreleri.

    ``filterType`` adıyla aranır; listedeki sıraya (ör. ``filters[1]``) güvenilmez.
    Sembol bulunamazsa güvenli varsayılanlar döner.
    """
    result: Dict[str, Any] = {
        "symbol": str(symbol or "").upper(),
        "status": "",
        "step_size": 0.0,
        "min_qty": 0.0,
        "max_qty": None,
        "market_max_qty": None,
        "min_notional": 0.0,
        "tick_size": 0.0,
        "found": False,
    }
    info = exchange_info or {}
    item = None
    for entry in info.get("symbols") or []:
        if str(entry.get("symbol") or "") == result["symbol"]:
            item = entry
            break
    if not item:
        result["min_notional"] = DEFAULT_MIN_NOTIONAL
        return result
    result["found"] = True
    result["status"] = str(item.get("status") or "")
    for flt in item.get("filters") or []:
        kind = str(flt.get("filterType") or "")
        if kind == "LOT_SIZE":
            result["min_qty"] = _float(flt.get("minQty"))
            result["step_size"] = _float(flt.get("stepSize")) or result["min_qty"]
            result["max_qty"] = _float(flt.get("maxQty")) or None
        elif kind == "MARKET_LOT_SIZE":
            result["market_max_qty"] = _float(flt.get("maxQty")) or None
        elif kind in ("NOTIONAL", "MIN_NOTIONAL"):
            # Bazı paritelerde iki filtre birden bulunur; büyük olan geçerlidir.
            value = _float(flt.get("minNotional"))
            if value > 0:
                result["min_notional"] = max(result["min_notional"], value)
        elif kind == "PRICE_FILTER":
            result["tick_size"] = _float(flt.get("tickSize"))
    if result["min_notional"] <= 0:
        result["min_notional"] = DEFAULT_MIN_NOTIONAL
    return result


def _step_decimals(step: float) -> int:
    text = f"{Decimal(str(step)):f}"
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1].rstrip("0"))


def round_step(quantity: float, step: float, mode: str = "down") -> float:
    """Adedi ``step`` katına yuvarlar (varsayılan: aşağı)."""
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return 0.0
    try:
        step_value = float(step or 0)
    except (TypeError, ValueError):
        step_value = 0.0
    if step_value <= 0:
        return max(0.0, qty)
    rounds = ROUND_UP if mode == "up" else ROUND_DOWN
    step_d = Decimal(str(step_value))
    value = (Decimal(str(qty)) / step_d).to_integral_value(rounding=rounds) * step_d
    decimals = _step_decimals(step_value)
    return float(round(value, decimals)) if decimals >= 0 else float(value)


def round_price(price: float, tick: float, mode: str = "down") -> float:
    """Fiyatı ``tickSize`` katına yuvarlar."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return 0.0
    try:
        tick_value = float(tick or 0)
    except (TypeError, ValueError):
        tick_value = 0.0
    if tick_value <= 0:
        return value
    rounds = ROUND_UP if mode == "up" else ROUND_DOWN
    tick_d = Decimal(str(tick_value))
    rounded = (Decimal(str(value)) / tick_d).to_integral_value(rounding=rounds) * tick_d
    decimals = _step_decimals(tick_value)
    return float(round(rounded, decimals))


def new_client_id(bot_id: str, side: str) -> str:
    """Benzersiz emir kimliği.

    Aynı kimlikle tekrar gönderim Binance tarafından reddedilir; böylece
    zaman aşımı sonrası tekrar deneme **çift emir** oluşturmaz.
    """
    prefix = re.sub(r"[^A-Za-z0-9]", "", str(bot_id or "bot"))[:12] or "bot"
    tag = "B" if str(side).upper().startswith("B") else "S"
    return f"{prefix}{tag}{secrets.token_hex(6)}"[:36]


def order_quantity(order: Dict[str, Any], fallback: float = 0.0) -> float:
    return _float((order or {}).get("executedQty"), fallback)


def order_quote(order: Dict[str, Any], fallback: float = 0.0) -> float:
    return _float((order or {}).get("cummulativeQuoteQty"), fallback)
