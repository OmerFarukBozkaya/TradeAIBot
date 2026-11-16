from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.api.analysis import router as analysis_router
from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.bots import router as bots_router
from app.api.coin_lists import router as coin_lists_router
from app.api.settings_api import router as settings_router
from app.api.strategies import router as strategies_router
from app.api.system_api import router as system_router
from app.api.trades import router as trades_router
from app.config import BASE_DIR, settings
from app.security import bootstrap_admin, csrf_protect, current_user
from app.supervisor import supervisor
from fastapi import Depends

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tradeai")

WEB_DIR = BASE_DIR / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    bootstrap_admin()
    logger.info("Veritabanı hazır: %s", db.paths.db)
    try:
        from app.migrate_legacy import migrate

        migrate(BASE_DIR / "Log" / "islem_gecmisi.log")
    except Exception as exc:
        logger.warning("Eski kayıt aktarımı atlandı: %s", exc)
    supervisor.resume_all()
    supervisor.start_monitor()
    try:
        from app.ai.autopilot import autopilot

        autopilot.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI otomatik öğrenme başlatılamadı: %s", exc)
    yield
    supervisor.stop_monitor()
    try:
        from app.ai.autopilot import autopilot

        autopilot.stop()
    except Exception:
        pass


app = FastAPI(title="TradeAIBot", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("Beklenmeyen hata: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Sunucu hatası"})


# --- auth (korumasız) ---
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# --- korumalı API ---
_protected = [Depends(current_user), Depends(csrf_protect)]
app.include_router(bots_router, prefix="/api/bots", tags=["bots"], dependencies=_protected)
app.include_router(coin_lists_router, prefix="/api/coin-lists", tags=["coin-lists"], dependencies=_protected)
app.include_router(strategies_router, prefix="/api/strategies", tags=["strategies"], dependencies=_protected)
app.include_router(analysis_router, prefix="/api/analysis", tags=["analysis"], dependencies=_protected)
app.include_router(ai_router, prefix="/api/ai", tags=["ai"], dependencies=_protected)
app.include_router(trades_router, prefix="/api", tags=["trades"], dependencies=_protected)
app.include_router(settings_router, prefix="/api/settings", tags=["settings"], dependencies=_protected)
app.include_router(system_router, prefix="/api/system", tags=["system"], dependencies=_protected)


@app.get("/api/health")
async def health():
    return {"ok": True, "app": settings.APP_NAME}


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Bulunamadı"})
    target = WEB_DIR / full_path
    if target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(WEB_DIR / "index.html")
