"""Sağlayıcı seçimi, önbellek ve ortak geçmiş yükleme."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from app.market_data import cache
from app.market_data.catalog import SymbolInfo, resolve_symbol
from app.market_data.periods import choose_base_period, parse_period
from app.market_data.providers import PROVIDERS
from app.market_data.resample import resample_data


def _provider(name: str):
    module = PROVIDERS.get(name)
    if module is None:
        raise ValueError(f"Bilinmeyen veri sağlayıcısı: {name}")
    return module


def _fetch_limit(target, base, limit: int) -> int:
    ratio = max(1.0, float(target.ms) / max(1.0, float(base.ms)))
    needed = int(math.ceil(int(limit) * ratio)) + 10
    return max(int(limit), min(needed, 250_000))


def load_history(
    symbol: str,
    period: str = "1h",
    limit: int = 20_000,
    *,
    source: str = "auto",
    asset_class: str = "",
    start: Any = None,
    end: Any = None,
    use_cache: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Herhangi bir sembol/periyot için ortak OHLCV verisi döndürür.

    Dönen ikinci değer rapor/meta bilgisidir. Ağ hatasında yerel önbellek
    varsa onunla devam edilir; meta içinde ``cached`` ve ``cache_error``
    alanları bunu belirtir.
    """
    info = resolve_symbol(symbol, source=source, asset_class=asset_class)
    target = parse_period(period)
    limit = max(1, min(int(limit), 250_000))
    provider = _provider(info.provider)
    available = getattr(provider, "NATIVE_PERIODS", [])
    base_text = choose_base_period(target, available)
    if not base_text:
        native = ", ".join(available) or "-"
        raise ValueError(
            f"{info.symbol} için {target.text} periyodu üretilemiyor. "
            f"En küçük kaynak periyodu: {native}. Daha büyük bir periyot seçin."
        )
    base = parse_period(base_text)
    fetch_limit = _fetch_limit(target, base, limit)

    meta: Dict[str, Any] = {
        "requested": limit,
        "source": info.provider,
        "provider": info.provider,
        "symbol": info.symbol,
        "native_symbol": info.native,
        "asset_class": info.asset_class,
        "live_supported": info.live_supported,
        "period": target.text,
        "requested_period": target.text,
        "base_period": base.text,
        "resampled": base.text != target.text,
        "start": start,
        "end": end,
    }

    raw: Optional[Dict[str, Any]] = None
    fetch_error: Optional[str] = None
    try:
        raw, provider_meta = provider.fetch(info, base.text, fetch_limit, start=start, end=end)
        meta.update(provider_meta or {})
        meta["fetch_requested"] = fetch_limit
        meta["requested"] = limit
    except Exception as exc:  # noqa: BLE001 - ağ/sağlayıcı hatası önbellekle telafi edilir
        fetch_error = str(exc)
        if use_cache:
            raw = cache.read(info.provider, info.native, base.text)
        if not raw:
            raise

    if not raw or not raw.get("close"):
        raise RuntimeError(f"{info.symbol} için veri boş döndü")

    if use_cache:
        try:
            cache.write(info.provider, info.native, base.text, raw)
        except OSError:
            pass

    data = (
        resample_data(raw, target, session_based=info.asset_class in {"stock", "metal", "fund", "forex"})
        if base.text != target.text
        else raw
    )
    if not data.get("close"):
        raise RuntimeError(f"{info.symbol} için {target.text} periyodunda veri oluşmadı")
    if len(data["close"]) > limit:
        for key in list(data.keys()):
            data[key] = data[key][-limit:]

    meta.update(
        {
            "rows": len(data["close"]),
            "start": data["opendate"][0] if data.get("opendate") else None,
            "end": data["opendate"][-1] if data.get("opendate") else None,
            "cached": bool(fetch_error and raw),
            "cache_error": fetch_error,
        }
    )
    return data, meta


def clear_cache(provider: str = "", symbol: str = "") -> Dict[str, Any]:
    """Önbelleği siler. Sembol verilmezse sağlayıcının tamamı silinir."""
    root = cache.cache_root()
    removed = 0
    if provider and symbol:
        path = cache.path_for(provider, symbol, "")
        target = path.parent
    elif provider:
        target = root / provider
    else:
        target = root
    if target.exists():
        import shutil

        shutil.rmtree(target, ignore_errors=True)
        removed = 1
    return {"ok": True, "removed": removed}


def describe(symbol: str, *, source: str = "auto", asset_class: str = "") -> SymbolInfo:
    return resolve_symbol(symbol, source=source, asset_class=asset_class)
