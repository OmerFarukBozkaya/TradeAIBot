"""Anlık fiyat servisi (bot pozisyonlarındaki gerçekleşmemiş K/Z için).

Binance public ticker'ından yalnızca istenen sembolleri çeker ve kısa süre
bellekte tutar. Ağ hatasında önbellekteki son fiyat döner; hiç fiyat yoksa
çağıran taraf mum kapanış fiyatına düşer.
"""

from __future__ import annotations

import json
import time
from typing import Dict, Iterable

import requests

TTL_SECONDS = 4.0
RETRY_AFTER_ERROR_SECONDS = 20.0
_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"

_cache: Dict[str, float] = {}
_fetched_at = 0.0
_fail_until = 0.0


def prices(symbols: Iterable[str]) -> Dict[str, float]:
    """İstenen semboller için son fiyatlar. Eksik/kullanılamazsa boş döner."""
    wanted = {str(s).strip().upper() for s in symbols if s and str(s).strip()}
    if not wanted:
        return {}
    global _fetched_at, _fail_until
    now = time.time()
    missing = wanted - set(_cache)
    if (now - _fetched_at >= TTL_SECONDS or missing) and now >= _fail_until:
        try:
            resp = requests.get(
                _ENDPOINT,
                params={"symbols": json.dumps(sorted(wanted), separators=(",", ":"))},
                timeout=3,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, list):
                for item in payload:
                    try:
                        _cache[str(item["symbol"]).upper()] = float(item["price"])
                    except (KeyError, TypeError, ValueError):
                        continue
            _fetched_at = now
        except Exception:
            # Kısa süre tekrar denemeyi bırak (hata fırtınası olmasın).
            _fail_until = now + RETRY_AFTER_ERROR_SECONDS
    return {symbol: _cache[symbol] for symbol in wanted if symbol in _cache}