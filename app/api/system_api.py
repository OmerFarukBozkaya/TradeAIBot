from __future__ import annotations

import os
import platform
import shutil
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, snapshots
from app.config import BASE_DIR, settings
from app.jobs import create_job

router = APIRouter()

_START = time.time()


@router.get("")
async def system_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _START),
    }
    try:
        import psutil

        info.update(
            {
                "cpu_percent": psutil.cpu_percent(interval=0.2),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(str(BASE_DIR)).percent,
                "process_count": len(psutil.pids()),
            }
        )
    except Exception:
        info.update({"cpu_percent": None, "memory_percent": None, "disk_percent": None})
    return info


@router.get("/bot-usage")
async def bot_usage() -> Dict[str, Any]:
    try:
        import psutil

        items = []
        for bot in db.rows("SELECT id,name,pid,status FROM bots"):
            pid = bot["pid"]
            cpu = mem = None
            if pid and psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    cpu = proc.cpu_percent(interval=0.1)
                    mem = proc.memory_info().rss / (1024 * 1024)
                except Exception:
                    pass
            items.append({**bot, "cpu_percent": cpu, "memory_mb": mem})
        return {"bots": items}
    except Exception:
        return {"bots": []}


@router.get("/health")
async def health():
    return {"ok": True, "app": settings.APP_NAME, "time": db.utcnow()}


# ---------------------------------------------------------------------------
# Regresyon testi (snapshot)
# ---------------------------------------------------------------------------
class SnapshotBody(BaseModel):
    coin: str = "BTCUSDT"
    period: str = "15m"
    candles: int = 20000
    note: str = ""


class VerifyBody(BaseModel):
    tolerance: Optional[float] = None


@router.get("/snapshots")
async def snapshot_list():
    return snapshots.list_snapshots()


@router.post("/snapshots")
async def snapshot_create(body: SnapshotBody):
    """Fiyat + indikatör + strateji çıktılarını kaydeder (iş kuyruğunda çalışır)."""
    if body.period not in snapshots.SUPPORTED_PERIODS:
        raise HTTPException(400, f"Desteklenmeyen periyot: {body.period}")
    return create_job(
        "snapshot_record",
        {
            "coin": body.coin,
            "period": body.period,
            "candles": body.candles,
            "note": body.note,
        },
    )


@router.post("/snapshots/{snapshot_id}/verify")
async def snapshot_verify(snapshot_id: str, body: Optional[VerifyBody] = None):
    if not snapshots.get_snapshot(snapshot_id):
        raise HTTPException(404, "Snapshot bulunamadı")
    return create_job(
        "snapshot_verify",
        {
            "snapshot_id": snapshot_id,
            "tolerance": (body.tolerance if body else None) or snapshots.DEFAULT_TOL,
        },
    )


@router.delete("/snapshots/{snapshot_id}")
async def snapshot_delete(snapshot_id: str):
    try:
        ok = snapshots.delete_snapshot(snapshot_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not ok:
        raise HTTPException(404, "Snapshot bulunamadı")
    return {"ok": True}
