"""Dashboard AI model yönetimi."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.ai import artifacts
from app.ai.features import feature_catalog, group_catalog
from app.ai.model import SKLEARN_AVAILABLE
from app.ai.spec import architecture_catalog, normalize_spec, spec_from_params, validate_spec
from app.config import settings
from app.jobs import create_job

router = APIRouter()


class TrainBody(BaseModel):
    name: str = ""
    coin: str = "BTCUSDT"
    period: str = "1h"
    limit: int = 20000
    source: str = "binance"
    asset_class: str = ""
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
    threshold_adjust: bool = True
    dataset_id: str = ""
    auto_snapshot: bool = True
    refresh_data: bool = False
    # Mimari (doğrudan alanlar; ``spec`` verilirse o kullanılır)
    engine: Optional[str] = None
    output_mode: Optional[str] = None
    hidden_layers: Optional[list] = None
    activation: Optional[str] = None
    dropout: Optional[float] = None
    learning_rate: Optional[float] = None
    epochs: Optional[int] = None
    batch_size: Optional[int] = None
    l2: Optional[float] = None
    feature_groups: Optional[list] = None
    spec: Optional[Dict[str, Any]] = None
    notes: str = ""


class BacktestBody(BaseModel):
    coin: Optional[str] = None
    period: Optional[str] = None
    limit: int = 20000
    cash: float = 100.0
    source: str = "auto"
    asset_class: str = ""


class AutopilotBody(BaseModel):
    enabled: Optional[bool] = None
    coin: Optional[str] = None
    period: Optional[str] = None
    preset: Optional[str] = None
    interval_hours: Optional[int] = None
    limit: Optional[int] = None
    dataset_id: Optional[str] = None
    auto_snapshot: Optional[bool] = None
    spec: Optional[Dict[str, Any]] = None


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
        "spec": normalize_spec(cfg.get("spec")),
        "presets": [
            {"id": key, "label": value["label"], "desc": value["desc"]}
            for key, value in PRESETS.items()
        ],
        "next_run_at": due.isoformat(timespec="seconds") if due else None,
        "history": runs,
    }


@router.put("/autopilot")
async def autopilot_save(body: AutopilotBody):
    from app.ai.autopilot import load_settings, save_settings

    values = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        saved = save_settings(values)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "settings": saved, "spec": normalize_spec(saved.get("spec"))}


@router.post("/autopilot/run")
async def autopilot_run():
    if not settings.AI_ENABLED:
        raise HTTPException(400, "AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    return create_job("ai_auto", {"trigger": "manual"})


@router.post("/evolve")
async def evolve_endpoint(body: Optional[Dict[str, Any]] = None):
    if not settings.AI_ENABLED:
        raise HTTPException(400, "AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    payload = dict(body or {})
    spec = spec_from_params(payload)
    errors = validate_spec(spec)
    if errors:
        raise HTTPException(400, "; ".join(errors))
    payload["spec"] = spec
    job = create_job("ai_evolve", payload)
    return job


class RetrainBody(BaseModel):
    repeats: int = 1
    coin: Optional[str] = None
    period: Optional[str] = None
    limit: Optional[int] = None
    dataset_id: Optional[str] = None
    auto_snapshot: Optional[bool] = None
    refresh_data: Optional[bool] = None
    min_gain: float = 0.0


@router.post("/models/{model_id}/retrain")
async def retrain_endpoint(model_id: str, body: Optional[RetrainBody] = None):
    """Aynı modeli tekrar eğitir; kimlik sabit kalır, sürüm artar."""
    if not settings.AI_ENABLED:
        raise HTTPException(400, "AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    manifest = artifacts.load_manifest(model_id)
    if not manifest:
        raise HTTPException(404, "Model bulunamadı")
    payload = {"model_id": model_id}
    if body:
        payload.update({k: v for k, v in body.model_dump().items() if v is not None})
    payload["repeats"] = max(1, min(int(payload.get("repeats") or 1), 10))
    return create_job("ai_retrain", payload)


@router.get("/profile")
async def profile_get():
    from app.ai.auto import EFFORT_LEVELS, load_profile

    return {
        "profile": load_profile(),
        "effortLevels": EFFORT_LEVELS,
        "last": db.get_setting("ai_last_auto", {}) or {},
    }


@router.put("/profile")
async def profile_put(body: Optional[Dict[str, Any]] = None):
    from app.ai.auto import save_profile

    try:
        return {"ok": True, "profile": save_profile(dict(body or {}))}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/auto")
async def auto_train_endpoint(body: Optional[Dict[str, Any]] = None):
    """Tek düğme: profili uygular, aramayı yapar, en iyiyi aktifleştirir."""
    if not settings.AI_ENABLED:
        raise HTTPException(400, "AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    payload = dict(body or {})
    if payload:
        try:
            from app.ai.auto import save_profile

            save_profile(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return create_job("ai_auto_train", {})


@router.get("/datasets")
async def datasets_list():
    from app.ai import datasets

    return {"items": datasets.list_datasets()}


@router.post("/datasets")
async def datasets_create(body: Optional[Dict[str, Any]] = None):
    """Fiyat verisini bir kez çekip sabit veri seti olarak diske yazar."""
    from app.ai import datasets
    from app.ai.data import load_market_data

    payload = dict(body or {})
    coin = str(payload.get("coin") or "BTCUSDT").upper()
    period = str(payload.get("period") or "1h")
    limit = max(500, min(int(payload.get("limit") or 25000), 250_000))
    source = str(payload.get("source") or "auto")
    asset_class = str(payload.get("asset_class") or "")
    data, meta = load_market_data(
        coin, period, limit, source, "", asset_class=asset_class,
        start=str(payload.get("start") or ""), end=str(payload.get("end") or ""),
    )
    saved = datasets.save(
        data, coin=coin, period=period, source=str(meta.get("source") or source),
        name=str(payload.get("name") or ""),
        extra={"limit": limit, "asset_class": asset_class},
    )
    return saved


@router.delete("/datasets/{dataset_id}")
async def datasets_delete(dataset_id: str):
    from app.ai import datasets

    try:
        return datasets.delete(dataset_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/datasets/{dataset_id}")
async def datasets_detail(dataset_id: str):
    from app.ai import datasets

    meta = datasets.manifest(dataset_id)
    if not meta:
        raise HTTPException(404, "Veri seti bulunamadı")
    return meta


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
    return {"catalog": feature_catalog(), "groups": group_catalog()}


@router.get("/architecture")
async def architecture():
    return architecture_catalog()


@router.post("/architecture/validate")
async def architecture_validate(body: Dict[str, Any]):
    spec = normalize_spec(body)
    return {"valid": not validate_spec(spec), "errors": validate_spec(spec), "spec": spec}


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
            "AI eğitimi kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.",
        )
    payload = body.model_dump()
    spec = spec_from_params(payload)
    errors = validate_spec(spec)
    if errors:
        raise HTTPException(400, "; ".join(errors))
    payload["spec"] = spec
    job = create_job("ai_train", payload)
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


class BulkDeleteBody(BaseModel):
    statuses: Optional[List[str]] = None


@router.post("/models/bulk-delete")
async def bulk_delete(body: Optional[BulkDeleteBody] = None):
    """Aday ve arşiv modellerini toplu siler. Aktif modeller korunur."""
    statuses = list((body.statuses if body else None) or ["candidate", "archived"])
    try:
        result = artifacts.bulk_delete(statuses)
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
            "source": body.source,
            "asset_class": body.asset_class,
        },
    )
    return job


@router.get("/experiences")
async def experiences(model_id: Optional[str] = None, limit: int = 200):
    return artifacts.list_experiences(model_id, limit=min(int(limit), 1000))
