from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app import remote_access
from app.api.analysis import router as analysis_router
from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.bots import router as bots_router
from app.api.coin_lists import router as coin_lists_router
from app.api.market import router as market_router
from app.api.settings_api import router as settings_router
from app.api.strategies import router as strategies_router
from app.api.system_api import router as system_router
from app.api.trades import router as trades_router
from app.config import BASE_DIR, settings
from app.security import COOKIE_NAME, _session_from_token, bootstrap_admin, csrf_protect, current_user
from app.supervisor import supervisor
from fastapi import Depends

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tradeai")

WEB_DIR = BASE_DIR / "web"

# Uzaktan erişim kapısının **dokunmadığı** yollar: sağlık kontrolü ve cihaz
# girişi. Bunlar sertifikasız/anahtarsız da açık olmalı; aksi halde anahtarı
# girmek imkânsız olurdu.
GATE_EXEMPT = {"/api/health", "/device-login", "/api/device/login"}


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
    if settings.LIBRARY_AUTO_IMPORT:
        # Repodaki `library/` dosyaları doğrudan kullanılabilsin: klonlayan
        # kişi elle `import` çalıştırmadan stratejilere ve coin listesine
        # erişir. Yalnızca **eksik** kayıtlar eklenir; panelden düzenlenmiş
        # bir kayıt dosyadaki eski sürümle ezilmez.
        try:
            from app import library_sync

            report = library_sync.import_library(
                BASE_DIR / "library", apply=True, only_missing=True
            )
            created = sum(
                1
                for key in ("strategies", "coinlists")
                for entry in report.get(key) or []
                if entry["action"] == "create"
            )
            if created:
                logger.info("Kütüphaneden %d kayıt eklendi (library/)", created)
            for err in report.get("errors") or []:
                logger.warning(
                    "Kütüphane dosyası atlandı: %s (%s)", err["file"], err["error"]
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kütüphane otomatik içe aktarma atlandı: %s", exc)
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


def _is_api(request: Request) -> bool:
    path = request.url.path or ""
    return path.startswith("/api/")


async def _body_fields(request: Request) -> dict:
    """Form (urlencoded) veya JSON gövdesini sözlüğe çevirir.

    ``request.form()`` kullanmıyoruz: Starlette bunun için ``python-multipart``
    ister. Tek bir bağımlılık uğruna imajı büyütmemek için gövde doğrudan
    ayrıştırılır (yalnızca ``application/x-www-form-urlencoded`` ve JSON).
    """
    import urllib.parse

    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001 - bozuk gövde
            return {}
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v is not None}
        return {}
    try:
        raw = await request.body()
    except Exception:  # noqa: BLE001
        raw = b""
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return {}
    parsed = urllib.parse.parse_qs(text, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def _lan_hint(request: Request) -> str:
    """Yerel erişim için kullanışlı bir adres önerisi (engel sayfasında)."""
    try:
        host = request.headers.get("host") or ""
        port = ""
        if ":" in host:
            port = ":" + host.rsplit(":", 1)[1]
        # İstemci aynı LAN'dan geldiyse kendi kullandığı adresi öner.
        ip = remote_access.client_ip(request)
        if ip and remote_access.is_private_ip(ip):
            return f"http://{ip}{port}/"
    except Exception:  # noqa: BLE001
        pass
    return ""


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # --- 1) Uzaktan erişim kapısı -------------------------------------
    # Cloudflare Tunnel trafiği TLS'i edge'de sonlandırdığı için uygulama
    # istemci sertifikasını doğrudan göremez. Bu yüzden ya cihaz anahtarı ya
    # da Cloudflare'in ilettiği doğrulama başlığı kontrol edilir.
    path = request.url.path or ""
    if path not in GATE_EXEMPT:
        try:
            allowed, reason = remote_access.check(request)
        except Exception as exc:  # noqa: BLE001 - hata olursa güvenli taraf: engelle
            logger.warning("Uzaktan erişim kontrolü başarısız: %s", exc)
            allowed, reason = False, "error"
        if not allowed:
            remote_access.log_denied(request)
            if _is_api(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Buraya erişim yetkiniz yok. Cihaz anahtarı gerekli.",
                        "reason": reason,
                    },
                )
            return HTMLResponse(
                status_code=403,
                content=remote_access.denied_page(
                    remote_access.request_host(request), _lan_hint(request)
                ),
            )

    # --- 2) Yanıt ve güvenlik başlıkları -------------------------------
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    # HTTPS (doğrudan veya Cloudflare Tunnel üzerinden) ise HSTS gönder.
    from app.proxy import is_secure_request

    try:
        if is_secure_request(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
    except Exception:  # noqa: BLE001 - başlık eklenemezse istek bozulmasın
        pass
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
app.include_router(market_router, prefix="/api/market", tags=["market"], dependencies=_protected)
app.include_router(trades_router, prefix="/api", tags=["trades"], dependencies=_protected)
app.include_router(settings_router, prefix="/api/settings", tags=["settings"], dependencies=_protected)
app.include_router(system_router, prefix="/api/system", tags=["system"], dependencies=_protected)


@app.get("/api/health")
async def health():
    return {"ok": True, "app": settings.APP_NAME}


# ---------------------------------------------------------------------------
# Cihaz anahtarı: giriş (dış ağdan da erişilebilir) ve yönetim (yalnız LAN)
# ---------------------------------------------------------------------------
@app.get("/device-login", response_class=HTMLResponse)
async def device_login_form(request: Request):
    return HTMLResponse(remote_access.device_login_page(next_url="/"))


@app.post("/api/device/login")
async def device_login(request: Request):
    """Anahtarı doğrular ve cihaz çerezini yazar; form ve JSON desteklenir."""
    ip = remote_access.client_ip(request)
    if remote_access.rate_limited(ip):
        message = "Çok fazla deneme. Birkaç dakika sonra tekrar deneyin."
        if "application/json" in (request.headers.get("content-type") or ""):
            return JSONResponse(status_code=429, content={"detail": message})
        return HTMLResponse(remote_access.device_login_page(message), status_code=429)

    payload = await _body_fields(request)
    raw = str(payload.get("key") or "").strip()
    next_url = str(payload.get("next") or "/")
    if not next_url.startswith("/"):
        next_url = "/"

    row = remote_access.verify_key(raw, ip)
    if not row:
        remote_access.record_attempt(ip)
        message = "Anahtar geçersiz veya iptal edilmiş."
        if "application/json" in (request.headers.get("content-type") or ""):
            return JSONResponse(status_code=403, content={"detail": message})
        return HTMLResponse(remote_access.device_login_page(message), status_code=403)

    from app.proxy import cookie_secure

    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        str(getattr(settings, "DEVICE_COOKIE_NAME", "tradeai_device")),
        raw,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        max_age=60 * 60 * 24 * 365,
        path="/",
    )
    db.log_event(None, f"Cihaz girişi: {row['name']} ({ip})", "info")
    return response


def _setup_session(request: Request) -> Optional[dict]:
    return _session_from_token(request.cookies.get(COOKIE_NAME))


def _setup_blocked_response() -> HTMLResponse:
    return HTMLResponse(
        remote_access.denied_page(
            "Kurulum sayfası",
            "",
        ).replace(
            "Buraya erişim yetkiniz yok",
            "Kurulum sayfası yalnızca yerel ağda açılabilir",
        ),
        status_code=403,
    )


@app.get("/setup/device", response_class=HTMLResponse)
async def setup_device_page(request: Request):
    if not remote_access.is_lan_request(request):
        return _setup_blocked_response()
    session = _setup_session(request)
    if not session:
        return RedirectResponse("/?login=1", status_code=303)
    return HTMLResponse(
        remote_access.setup_page(
            remote_access.list_keys(), csrf=str(session.get("csrf_token") or "")
        )
    )


@app.post("/setup/device")
async def setup_device_create(request: Request):
    if not remote_access.is_lan_request(request):
        return _setup_blocked_response()
    session = _setup_session(request)
    if not session:
        return RedirectResponse("/?login=1", status_code=303)
    form = await _body_fields(request)
    csrf = str(form.get("csrf") or "")
    if not csrf or csrf != str(session.get("csrf_token") or ""):
        return HTMLResponse(
            remote_access.setup_page(
                remote_access.list_keys(),
                error="Oturum doğrulaması başarısız; sayfayı yenileyip tekrar deneyin.",
                csrf=str(session.get("csrf_token") or ""),
            ),
            status_code=400,
        )
    raw, _meta = remote_access.create_key(str(form.get("name") or "Cihaz"))
    return HTMLResponse(
        remote_access.setup_page(
            remote_access.list_keys(), new_key=raw, csrf=str(session.get("csrf_token") or "")
        )
    )


@app.post("/setup/device/revoke")
async def setup_device_revoke(request: Request):
    if not remote_access.is_lan_request(request):
        return _setup_blocked_response()
    session = _setup_session(request)
    if not session:
        return RedirectResponse("/?login=1", status_code=303)
    form = await _body_fields(request)
    csrf = str(form.get("csrf") or "")
    if not csrf or csrf != str(session.get("csrf_token") or ""):
        return HTMLResponse(status_code=400, content="Oturum doğrulaması başarısız")
    remote_access.revoke_key(str(form.get("id") or ""))
    return RedirectResponse("/setup/device", status_code=303)


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
