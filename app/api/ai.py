"""Dashboard AI model yönetimi."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.ai import artifacts
from app.ai.features import feature_catalog
from app.ai.model import SKLEARN_AVAILABLE
from app.config import settings
from app.jobs import create_job

router = APIRouter()


class TrainBody(BaseModel):
    name: str = ""
    coin: str = "BTCUSDT"
    period: str = "1h"
    limit: int = 20000
    source: str = "binance"
    csv_path: str = ""
    label_kind: str = "forward"
    horizon: int = 12
    target_move: float = 0.01
    stop_move: float = 0.01
    extreme_window: int = 13
    extreme_tolerance: float = 0.002
    fee: float = 0.001
    slippage: float = 0.0005
    min_precision: float = 0.35
    walk_forward: bool = True
    folds: int = 3
    use_feedback: bool = True
    feedback_weight: float = 0.5
    refine: bool = True
    iterations: int = 5
    patience: int = 2
    timing_tolerance: float = 0.004
    min_trades: int = 8
    notes: str = ""


class BacktestBody(BaseModel):
    coin: Optional[str] = None
    period: Optional[str] = None
    limit: int = 20000
    cash: float = 100.0


class AutopilotBody(BaseModel):
    enabled: Optional[bool] = None
    coin: Optional[str] = None
    period: Optional[str] = None
    preset: Optional[str] = None
    interval_hours: Optional[int] = None
    limit: Optional[int] = None


@router.get("/autopilot")
async def autopilot_state():
    from app.ai.autopilot import PRESETS, history, load_settings, next_run_at

    cfg = load_settings()
    due = next_run_at(cfg)
    runs = []
    try:
        runs = history(10)
    except Exception:
        pass
    return {
        "settings": cfg,
        "presets": [
            {"id": key, "label": value["label"], "desc": value["desc"]}
            for key, value in PRESETS.items()
        ],
        "next_run_at": due.isoformat(timespec="seconds") if due else None,
        "history": runs,
    }


@router.put("/autopilot")
async def autopilot_save(body: AutopilotBody):
    from app.ai.autopilot import save_settings

    values = {k: v for k, v in body.model_dump().items() if v is not None}
    return {"ok": True, "settings": save_settings(values)}


@router.post("/autopilot/run")
async def autopilot_run():
    if not settings.AI_ENABLED:
        raise HTTPException(400, "AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    return create_job("ai_auto", {"trigger": "manual"})


@router.get("/status")
async def status():
    count = 0
    try:
        row = db.row("SELECT COUNT(*) AS c FROM ai_models")
        count = int((row or {}).get("c") or 0)
    except Exception:
        pass
    return {
        "enabled": bool(settings.AI_ENABLED),
        "sklearn": SKLEARN_AVAILABLE,
        "models": count,
        "experiences": artifacts.experience_count(),
        "note": (
            "AI özellikleri açık. Otomatik öğrenmeyi başlatabilirsin."
            if settings.AI_ENABLED
            else "AI kapalı. Ayarlar → Sistem → Yapay zekâ özelliklerini açın."
        ),
    }


@router.get("/features")
async def features():
    return {"catalog": feature_catalog()}


@router.get("/models")
async def models(include_archived: bool = False):
    return artifacts.list_models(include_archived=include_archived)


@router.get("/models/{model_id}")
async def model_detail(model_id: str):
    manifest = artifacts.load_manifest(model_id)
    if not manifest:
        raise HTTPException(404, "Model bulunamadı")
    return {
        "model": manifest,
        "report": artifacts.read_report(model_id),
        "experiences": artifacts.experience_count(model_id),
    }


@router.post("/train")
async def train(body: TrainBody):
    if not settings.AI_ENABLED:
        raise HTTPException(
            400,
            "AI eğitimi kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın "
            "ve docker compose --profile ai ile ai servisini başlatın.",
        )
    job = create_job("ai_train", body.model_dump())
    return job


@router.post("/models/{model_id}/promote")
async def promote(model_id: str):
    try:
        manifest = artifacts.set_status(model_id, "active")
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "model": manifest}


@router.post("/models/{model_id}/archive")
async def archive(model_id: str):
    try:
        manifest = artifacts.set_status(model_id, "archived")
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "model": manifest}


@router.delete("/models/{model_id}")
async def delete(model_id: str):
    try:
        result = artifacts.delete_model(model_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return result


@router.post("/models/{model_id}/backtest")
async def backtest(model_id: str, body: BacktestBody):
    manifest = artifacts.load_manifest(model_id)
    if not manifest:
        raise HTTPException(404, "Model bulunamadı")
    params = manifest.get("params") or {}
    job = create_job(
        "backtest",
        {
            "strategy": {"type": "ai", "model_id": model_id},
            "coin": (body.coin or params.get("coin") or "BTCUSDT").upper(),
            "period": body.period or params.get("period") or "1h",
            "limit": body.limit,
            "cash": body.cash,
        },
    )
    return job


@router.get("/experiences")
async def experiences(model_id: Optional[str] = None, limit: int = 200):
    return artifacts.list_experiences(model_id, limit=min(int(limit), 1000))
