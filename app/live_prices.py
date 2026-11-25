"""Anlık fiyat servisi (bot pozisyonlarındaki gerçekleşmemiş K/Z için).

Binance public ticker'ından yalnızca istenen sembolleri çeker ve kısa süre
bellekte tutar. Ağ hatasında önbellekteki son fiyat döner; hiç fiyat yoksa
çağıran taraf mum kapanış fiyatına düşer.

Önbellek **sembol bazındadır**: geçersiz bir sembol veya tek bir ağ hatası
diğer coinlerin fiyatını dondurmaz. Panel birden fazla botu tek seferde
sorduğunda istekler tek bir toplu çağrıda birleştirilir.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Tuple

import requests

TTL_SECONDS = 4.0
RETRY_AFTER_ERROR_SECONDS = 5.0
_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"
_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}
_CHUNK = 100

_cache: Dict[str, float] = {}
_seen_at: Dict[str, float] = {}
_retry_at: Dict[str, float] = {}


def _fetch(symbols: List[str]) -> Dict[str, float]:
    """Tek istekte verilen sembollerin fiyatlarını döndürür."""
    resp = requests.get(
        _ENDPOINT,
        params={"symbols": json.dumps(sorted(symbols), separators=(",", ":"))},
        timeout=3,
    )
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        payload = [payload]
    result: Dict[str, float] = {}
    if not isinstance(payload, list):
        return result
    for item in payload:
        try:
            result[str(item["symbol"]).upper()] = float(item["price"])
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _split_markets(symbols: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Binance (gerçek zamanlı) ve Yahoo (gecikmeli) sembollerini ayırır."""
    from app.market_data import resolve_symbol

    binance: List[str] = []
    yahoo: List[str] = []
    for symbol in symbols:
        try:
            info = resolve_symbol(symbol)
        except ValueError:
            binance.append(symbol)
            continue
        if info.provider == "binance":
            binance.append(symbol)
        else:
            yahoo.append(symbol)
    return binance, yahoo


def _yahoo_price(native: str) -> float:
    response = requests.get(
        f"{_YAHOO_CHART}/{native}",
        params={"interval": "1m", "range": "1d"},
        headers=_YAHOO_HEADERS,
        timeout=5,
    )
    if response.status_code == 404:
        raise RuntimeError(f"Yahoo sembolü bulunamadı: {native}")
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo hatası: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError("Yahoo fiyat döndürmedi")
    result = results[0] or {}
    meta = result.get("meta") or {}
    for key in ("regularMarketPrice",):
        try:
            value = float(meta.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    # Meta yoksa son geçerli 1m kapanışına düş.
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    for value in reversed(quote.get("close") or []):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    raise RuntimeError("Yahoo fiyatı okunamadı")


def _refresh_yahoo(symbols: List[str], now: float) -> None:
    from app.market_data import resolve_symbol
    from app.market_data.catalog import TROY_OUNCE_GRAMS
    from app.market_data.providers.derived import SPECS as DERIVED_SPECS

    requested: Dict[str, Tuple[str, str]] = {}
    for symbol in symbols:
        try:
            info = resolve_symbol(symbol)
        except ValueError:
            _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS
            continue
        spec = DERIVED_SPECS.get(str(info.native or "").upper())
        if spec:
            requested[symbol] = ("derived", spec["base"] + "|" + spec["fx"])
        else:
            requested[symbol] = ("plain", info.native)

    natives = {native for _kind, native in requested.values() if "|" not in native}
    for native in natives:
        try:
            _cache[f"__yahoo__{native}"] = _yahoo_price(native)
            _seen_at[f"__yahoo__{native}"] = now
        except Exception:  # noqa: BLE001 - tek sembol hatası diğerlerini durdurmaz
            _retry_at[native] = now + RETRY_AFTER_ERROR_SECONDS

    for symbol, (kind, native) in requested.items():
        try:
            if kind == "derived":
                base, fx = native.split("|", 1)
                base_price = _cache.get(f"__yahoo__{base}")
                fx_price = _cache.get(f"__yahoo__{fx}")
                if not base_price or not fx_price:
                    raise RuntimeError("Türetilmiş fiyat kaynağı eksik")
                value = float(base_price) * float(fx_price) / TROY_OUNCE_GRAMS
            else:
                value = _cache.get(f"__yahoo__{native}")
                if not value:
                    raise RuntimeError("Fiyat alınamadı")
            _cache[symbol] = float(value)
            _seen_at[symbol] = now
        except Exception:  # noqa: BLE001
            _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS


def _store(found: Dict[str, float], wanted: List[str], now: float) -> None:
    for symbol in wanted:
        if symbol in found:
            _cache[symbol] = found[symbol]
            _seen_at[symbol] = now
        else:
            # Sembol bu partide dönmedi (geçersiz/askıda): kısa süre tekrar
            # denenmesin, diğer coinler etkilenmesin.
            _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS


def _due(symbols: Iterable[str], now: float) -> List[str]:
    due: List[str] = []
    for symbol in symbols:
        if now - float(_seen_at.get(symbol) or 0.0) < TTL_SECONDS:
            continue
        if now < float(_retry_at.get(symbol) or 0.0):
            continue
        due.append(symbol)
    return due


def _refresh(due: List[str], now: float) -> None:
    for start in range(0, len(due), _CHUNK):
        chunk = due[start:start + _CHUNK]
        try:
            _store(_fetch(chunk), chunk, now)
            continue
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Geçersiz sembol tüm partiyi düşürür; küçük partilerde tek tek
            # deneyerek geçerli coinlerin fiyatını kurtar.
            if status == 400 and len(chunk) <= 20:
                for symbol in chunk:
                    try:
                        _store(_fetch([symbol]), [symbol], now)
                    except Exception:  # noqa: BLE001 - tek sembol hatası yalıtılır
                        _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS
                continue
            for symbol in chunk:
                _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS
        except Exception:  # noqa: BLE001 - ağ hatası: partiyi kısa süre askıya al
            for symbol in chunk:
                _retry_at[symbol] = now + RETRY_AFTER_ERROR_SECONDS


def prices(symbols: Iterable[str]) -> Dict[str, float]:
    """İstenen semboller için son fiyatlar. Eksik/kullanılamazsa boş döner."""
    wanted = sorted({str(s).strip().upper() for s in symbols if s and str(s).strip()})
    if not wanted:
        return {}
    now = time.time()
    due = _due(wanted, now)
    if due:
        binance, yahoo = _split_markets(due)
        if binance:
            _refresh(binance, now)
        if yahoo:
            _refresh_yahoo(yahoo, now)
    return {symbol: _cache[symbol] for symbol in wanted if symbol in _cache}


def ages(symbols: Iterable[str]) -> Dict[str, float]:
    """Sembolün son başarılı fiyat güncellemesinden bu yana geçen saniye."""
    now = time.time()
    result: Dict[str, float] = {}
    for symbol in symbols:
        key = str(symbol or "").strip().upper()
        seen = _seen_at.get(key)
        if seen:
            result[key] = round(now - float(seen), 1)
    return result


def reset() -> None:
    """Testler/önbellek temizliği için bellekteki fiyatları sıfırlar."""
    _cache.clear()
    _seen_at.clear()
    _retry_at.clear()
