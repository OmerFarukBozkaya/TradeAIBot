from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.jobs import create_job, get_job, list_jobs
from app.strategies.builtin import builtin_names  # noqa: F401
from app.strategies.compiler import compile_strategy, validate_definition
from app.strategies.registry import catalog
from app.strategies.service import (
    create_custom,
    delete_custom,
    duplicate_builtin,
    duplicate_custom,
    get_custom,
    get_version,
    list_builtin,
    list_custom,
    rename_builtin,
    set_builtin_archived,
    set_status,
    update_custom,
)

router = APIRouter()


class StrategyBody(BaseModel):
    definition: Dict[str, Any]


class PreviewBody(BaseModel):
    definition: Dict[str, Any]
    coin: str = "BTCUSDT"
    period: str = "1h"


class BacktestBody(BaseModel):
    strategy: Dict[str, Any]
    coin: str = "BTCUSDT"
    period: str = "1h"
    limit: int = 20000
    cash: float = 100.0
    risk: Dict[str, Any] = {}


class BacktestAllBody(BaseModel):
    coin: str = "BTCUSDT"
    period: str = "1h"
    limit: int = 20000
    cash: float = 100.0
    include_archived: bool = False
    keys: Optional[List[str]] = None


@router.get("/indicators")
async def indicators():
    return catalog()


@router.get("/builtin")
async def builtin(include_archived: bool = False):
    return list_builtin(include_archived)


class BuiltinRenameBody(BaseModel):
    label: str


class BuiltinArchiveBody(BaseModel):
    archived: bool


@router.post("/builtin/{name}/rename")
async def builtin_rename(name: str, body: BuiltinRenameBody):
    try:
        return rename_builtin(name, body.label)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/builtin/{name}/archive")
async def builtin_archive(name: str, body: BuiltinArchiveBody):
    try:
        return set_builtin_archived(name, body.archived)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/builtin/{name}/duplicate")
async def builtin_duplicate(name: str):
    try:
        return duplicate_builtin(name)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/custom")
async def custom_list(include_archived: bool = False):
    return list_custom(include_archived)


@router.get("/custom/{strategy_id}")
async def custom_get(strategy_id: str):
    item = get_custom(strategy_id)
    if not item:
        raise HTTPException(404, "Strateji bulunamadı")
    return item


@router.post("/custom")
async def custom_create(body: StrategyBody):
    try:
        return create_custom(body.definition)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.put("/custom/{strategy_id}")
async def custom_update(strategy_id: str, body: StrategyBody):
    try:
        return update_custom(strategy_id, body.definition)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/custom/{strategy_id}/duplicate")
async def custom_duplicate(strategy_id: str):
    try:
        return duplicate_custom(strategy_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/custom/{strategy_id}/activate")
async def custom_activate(strategy_id: str):
    set_status(strategy_id, "active")
    return {"ok": True}


@router.post("/custom/{strategy_id}/archive")
async def custom_archive(strategy_id: str):
    set_status(strategy_id, "archived")
    return {"ok": True}


@router.delete("/custom/{strategy_id}")
async def custom_delete(strategy_id: str, force: bool = False):
    try:
        return delete_custom(strategy_id, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/custom/{strategy_id}/versions")
async def custom_versions(strategy_id: str):
    return db.rows(
        "SELECT version, created_at FROM strategy_versions WHERE strategy_id=? ORDER BY version DESC",
        (strategy_id,),
    )


@router.post("/validate")
async def validate(body: StrategyBody):
    errors = validate_definition(body.definition)
    warmup = None
    if not errors:
        try:
            if body.definition.get("builtin"):
                from app.strategies.builtin import BuiltinStrategy

                warmup = BuiltinStrategy(body.definition["builtin"]).warmup
            else:
                warmup = compile_strategy(body.definition, "validate").warmup
        except Exception:
            warmup = None
    return {"valid": not errors, "errors": errors, "warmup": warmup}


@router.post("/preview")
async def preview(body: PreviewBody):
    errors = validate_definition(body.definition)
    if errors:
        raise HTTPException(400, "; ".join(errors))
    from core import Binance

    try:
        data = Binance().get_coin_data(body.coin, body.period, 1000)
        if body.definition.get("builtin"):
            from app.strategies.builtin import BuiltinStrategy

            evaluator = BuiltinStrategy(body.definition["builtin"])
            if hasattr(evaluator, "prepare"):
                evaluator.prepare(data)
            result = evaluator.evaluate(data)
            warmup = evaluator.warmup
        else:
            compiled = compile_strategy(body.definition, "preview")
            result = compiled.evaluate(data)
            warmup = compiled.warmup
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Önizleme hatası: {exc}")
    return {
        "result": result,
        "warmup": warmup,
        "coin": body.coin,
        "period": body.period,
        "candles": len(data.get("close") or []),
        "close": (data.get("close") or [None])[-1],
    }


@router.post("/backtest")
async def backtest(body: BacktestBody):
    job = create_job(
        "backtest",
        {
            "strategy": body.strategy,
            "coin": body.coin,
            "period": body.period,
            "limit": body.limit,
            "cash": body.cash,
            "risk": body.risk,
        },
    )
    return job


@router.post("/backtest-all")
async def backtest_all(body: BacktestAllBody):
    """Tüm stratejileri aynı coin/periyotla backtest eder (karşılaştırma tablosu)."""
    job = create_job(
        "backtest_all",
        {
            "coin": body.coin,
            "period": body.period,
            "limit": body.limit,
            "cash": body.cash,
            "include_archived": body.include_archived,
            "keys": body.keys,
        },
    )
    return job


@router.get("/backtests")
async def backtests(strategy_id: Optional[str] = None, limit: int = 50):
    if strategy_id:
        return db.rows(
            "SELECT * FROM strategy_backtests WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?",
            (strategy_id, limit),
        )
    return db.rows(
        "SELECT * FROM strategy_backtests ORDER BY created_at DESC LIMIT ?", (limit,)
    )
