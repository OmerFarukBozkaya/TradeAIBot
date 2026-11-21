from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.jobs import active_jobs, cancel_job, create_job, get_job, list_jobs, scan_results

router = APIRouter()


class ScanBody(BaseModel):
    period: str = "1h"
    strategies: List[Any] = []
    coins: List[str] = []
    list_id: Optional[str] = None
    source: str = "auto"
    asset_class: str = ""


class BacktestResultsBody(BaseModel):
    pass


class GenericBody(BaseModel):
    coin: str = "BTCUSDT"
    period: str = "1h"
    count: int = 20
    price: Optional[float] = None
    window: int = 14
    tolerance: float = 0.01
    strategies: List[Any] = []
    coins: List[str] = []
    max_coins: int = 30
    sort: bool = False
    mode: str = "test"
    source: str = "auto"
    asset_class: str = ""
    start: Optional[str] = None
    end: Optional[str] = None


@router.post("/scan")
async def scan(body: ScanBody):
    if body.list_id:
        from app.coin_lists import get_list

        if not get_list(body.list_id):
            raise HTTPException(404, "Coin listesi bulunamadı")
    return create_job("scan", body.model_dump())


@router.post("/indicator-values")
async def indicator_values(body: GenericBody):
    return create_job("indicator_values", body.model_dump())


@router.post("/strategy-values")
async def strategy_values(body: GenericBody):
    return create_job("strategy_values", body.model_dump())


@router.post("/support-resistance")
async def support_resistance(body: GenericBody):
    return create_job("support_resistance", body.model_dump())


@router.post("/market")
async def market(body: GenericBody):
    return create_job("market", body.model_dump())


@router.post("/monthly")
async def monthly(body: GenericBody):
    return create_job("monthly", body.model_dump())


@router.post("/coinlist")
async def coinlist(body: GenericBody):
    return create_job("coinlist", body.model_dump())


@router.post("/buy-result")
async def buy_result(body: GenericBody):
    return create_job("buy_result", body.model_dump())


@router.post("/dataset")
async def dataset(body: GenericBody):
    return create_job("dataset", body.model_dump())


@router.post("/strategy-results")
async def strategy_results(body: GenericBody):
    return create_job("strategy_results", body.model_dump())


@router.post("/strategy-analyze-save")
async def strategy_analyze_save(body: GenericBody):
    return create_job("strategy_analyze_save", body.model_dump())


@router.post("/ai-train")
async def ai_train(body: GenericBody):
    return create_job("ai_train", body.model_dump())


@router.get("/scans")
async def scans(limit: int = 5):
    """Biten taramaların sonuçları (dashboard)."""
    return scan_results(limit)


@router.get("/jobs/active")
async def active():
    """Dashboard için devam eden ve yeni biten işler."""
    return active_jobs()


@router.get("/jobs")
async def jobs(type: Optional[str] = None, limit: int = 50):
    return list_jobs(type, limit)


@router.get("/jobs/{job_id}")
async def job(job_id: str):
    item = get_job(job_id)
    if not item:
        raise HTTPException(404, "İş bulunamadı")
    return item


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    try:
        return cancel_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/strategys")
async def strategys():
    from core import Araclar

    result = {}
    for period, funcs in Araclar.get_strategys().items():
        result[period] = [f.__name__ for f in funcs]
    return result
