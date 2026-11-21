"""Piyasa verisi kataloğu ve geçmiş önizleme."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.market_data import catalog, clear_cache, load_history
from app.market_data.catalog import search_symbols

router = APIRouter()


@router.get("/symbols")
async def symbols():
    return catalog()


@router.get("/search")
def search(
    q: str = Query(""),
    asset_class: str = Query(""),
    limit: int = Query(25, ge=1, le=50),
):
    try:
        items = search_symbols(q, asset_class, limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Sembol araması başarısız: {exc}")
    return {"query": q, "asset_class": asset_class, "count": len(items), "items": items}


@router.get("/history")
def history(
    symbol: str = Query("BTCUSDT"),
    period: str = Query("1h"),
    limit: int = Query(1000, ge=10, le=250_000),
    source: str = Query("auto"),
    asset_class: str = Query(""),
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    try:
        data, meta = load_history(
            symbol, period, limit, source=source, asset_class=asset_class,
            start=start, end=end,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    from app.job_runner import _data_report

    report = _data_report(data, period, meta)
    from app.job_runner import _format_span

    meta = {key: value for key, value in meta.items() if key not in {"cached_data"}}
    tail = min(100, len(data.get("close") or []))
    candles = []
    for i in range(len(data["close"]) - tail, len(data["close"])):
        candles.append(
            {
                "time": data["opendate"][i],
                "open": data["open"][i],
                "high": data["high"][i],
                "low": data["low"][i],
                "close": data["close"][i],
                "volume": (data.get("volume_usdt") or data.get("volume_coin") or [0])[i],
            }
        )
    return {
        "meta": meta,
        "report": report,
        "candles": candles,
        "last": data["close"][-1],
        "span_text": _format_span(report.get("span_ms") or 0),
    }


@router.post("/cache/clear")
def cache_clear(provider: str = "", symbol: str = ""):
    return clear_cache(provider, symbol)
