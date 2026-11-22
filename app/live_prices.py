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
from typing import Dict, Iterable, List

import requests

TTL_SECONDS = 4.0
RETRY_AFTER_ERROR_SECONDS = 5.0
_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"
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
        _refresh(due, now)
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
