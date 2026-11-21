from __future__ import annotations

import os
import platform
import shutil
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import backup, db, snapshots
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
    from app.market_data.periods import parse_period

    try:
        period = parse_period(body.period).text
    except ValueError:
        raise HTTPException(400, f"Desteklenmeyen periyot: {body.period}")
    if period not in snapshots.SUPPORTED_PERIODS:
        raise HTTPException(400, f"Desteklenmeyen periyot: {period}")
    return create_job(
        "snapshot_record",
        {
            "coin": body.coin,
            "period": period,
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


# ---------------------------------------------------------------------------
# Yedekleme / geri yükleme
# ---------------------------------------------------------------------------
class BackupBody(BaseModel):
    note: str = ""
    include_logs: bool = False
    include_env: bool = False
    include_datasets: bool = False
    include_snapshots: bool = False
    include_models: bool = False


@router.get("/backups")
async def backup_list():
    return backup.list_backups()


@router.post("/backups")
async def backup_create(body: BackupBody):
    """Yedek arşivi oluşturur (iş kuyruğunda; DB kopyası tutarlı alınır)."""
    return create_job(
        "backup_create",
        {
            "note": body.note,
            "include_logs": body.include_logs,
            "include_env": body.include_env,
            "include_datasets": body.include_datasets,
            "include_snapshots": body.include_snapshots,
            "include_models": body.include_models,
        },
    )


@router.post("/backups/upload")
async def backup_upload(request: Request, name: str):
    """Tarayıcıdan gelen `.zip` arşivini `Data/backups/` içine kaydeder.

    Gövde ham bayt olarak (application/octet-stream) gönderilir; multipart
    bağımlılığı gerekmez. Dosya belleğe tamamen alınmadan diske yazılır.
    """
    try:
        temp = backup.staging_path(name)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    limit = backup.MAX_UPLOAD_MB * 1048576
    size = 0
    try:
        with open(temp, "wb") as out:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"Dosya çok büyük (>{backup.MAX_UPLOAD_MB} MB)")
                out.write(chunk)
        return backup.finalize_upload(name, temp)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        temp.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise HTTPException(500, f"Yükleme başarısız: {exc}")


@router.get("/backups/{name}/download")
async def backup_download(name: str):
    from fastapi.responses import FileResponse

    try:
        path = backup._resolve(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not path.exists():
        raise HTTPException(404, "Yedek bulunamadı")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post("/backups/{name}/restore")
async def backup_restore(name: str):
    """Yedeği geri yükler. Botlar durdurulur, önce güvenlik yedeği alınır."""
    try:
        path = backup._resolve(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not path.exists():
        raise HTTPException(404, "Yedek bulunamadı")
    return create_job("backup_restore", {"name": name})


@router.delete("/backups/{name}")
async def backup_delete(name: str):
    try:
        ok = backup.delete_backup(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not ok:
        raise HTTPException(404, "Yedek bulunamadı")
    return {"ok": True}