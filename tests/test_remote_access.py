"""Uzaktan erişim kapısı: cihaz anahtarı + sertifika başlığı, yalnız hedef host.

Senaryo: Cloudflare Tunnel üzerinden ``tradeai.studiowl.com.tr`` yayınlanıyor.
Sertifikası/anahtarı olmayan biri hiçbir sayfaya ulaşamamalı ve Türkçe
"Buraya erişim yetkiniz yok" sayfası görmeli; yerel ağ erişimi ise bozulmamalı.
"""

from __future__ import annotations

import pytest

from app import db, remote_access as ra
from app.paths import paths

HOST = "tradeai.studiowl.com.tr"


class _URL:
    def __init__(self, path: str):
        self.path = path
        self.scheme = "http"


class _Client:
    def __init__(self, host: str):
        self.host = host


class FakeRequest:
    def __init__(
        self,
        path: str = "/",
        headers: dict | None = None,
        cookies: dict | None = None,
        client_ip: str = "203.0.113.9",
    ):
        self.url = _URL(path)
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = _Client(client_ip) if client_ip else None


@pytest.fixture()
def db_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "t.db")
    monkeypatch.setattr(db, "_WAL_READY", False)
    db.init_db()
    ra.reset_attempts()
    yield
    ra.reset_attempts()


@pytest.fixture()
def gate(monkeypatch):
    """Kapıyı yalnız test hostname'inde, anahtar modunda aç."""
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", True)
    monkeypatch.setattr(ra.settings, "DEVICE_COOKIE_NAME", "tradeai_device")
    return ra.settings


# --- Kapsam ---------------------------------------------------------------
def test_other_hostnames_are_untouched(gate):
    """Kural yalnızca hedef hostname'de; başka siteler etkilenmez."""
    req = FakeRequest(headers={"host": "baska.ornek.com"}, client_ip="203.0.113.9")
    allowed, reason = ra.check(req)
    assert allowed is True
    assert reason == "other-host"


def test_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "off")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    req = FakeRequest(headers={"host": HOST}, client_ip="203.0.113.9")
    assert ra.check(req) == (True, "off")


def test_gate_needs_hostname_configured(monkeypatch):
    """Hostname boşsa kimse kilitlenmesin (yanlış yapılandırma koruması)."""
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", "")
    req = FakeRequest(headers={"host": HOST}, client_ip="203.0.113.9")
    assert ra.check(req)[0] is True


# --- Yerel ağ vs uzak -----------------------------------------------------
def test_lan_request_allowed(gate):
    req = FakeRequest(headers={"host": HOST}, client_ip="192.168.1.50")
    assert ra.check(req) == (True, "lan")


def test_tunnel_request_from_docker_ip_is_not_lan(gate):
    """cloudflared isteği docker iç ağından (172.x) gelir; LAN sayılmamalı."""
    req = FakeRequest(
        headers={
            "host": HOST,
            "cf-connecting-ip": "203.0.113.9",
            "cf-ray": "8f00-IST",
            "x-forwarded-for": "172.18.0.5",
        },
        client_ip="172.18.0.5",
    )
    assert ra.is_lan_request(req) is False
    assert ra.client_ip(req) == "203.0.113.9"
    assert ra.check(req)[0] is False


def test_public_ip_direct_request_denied(gate):
    req = FakeRequest(headers={"host": HOST}, client_ip="203.0.113.9")
    assert ra.check(req)[0] is False


# --- Cihaz anahtarı -------------------------------------------------------
def test_key_grants_access(db_ready, gate):
    raw, meta = ra.create_key("Telefon")
    assert raw.startswith("tk_")
    assert meta["name"] == "Telefon"
    req = FakeRequest(
        headers={"host": HOST}, cookies={"tradeai_device": raw}, client_ip="203.0.113.9"
    )
    assert ra.check(req) == (True, "key")
    # Son kullanım kaydı güncellenir.
    row = db.row("SELECT last_used_at, last_ip FROM device_keys WHERE id=?", (meta["id"],))
    assert row["last_used_at"]
    assert row["last_ip"] == "203.0.113.9"


def test_key_via_header(db_ready, gate):
    raw, _ = ra.create_key("Telefon")
    req = FakeRequest(headers={"host": HOST, "x-device-key": raw}, client_ip="203.0.113.9")
    assert ra.check(req)[0] is True


def test_wrong_or_missing_key_denied(db_ready, gate):
    ra.create_key("Telefon")
    assert ra.check(FakeRequest(headers={"host": HOST}))[0] is False
    bad = FakeRequest(headers={"host": HOST, "x-device-key": "tk_yanlis"})
    assert ra.check(bad)[0] is False


def test_raw_key_is_not_stored(db_ready):
    raw, meta = ra.create_key("Telefon")
    stored = db.row("SELECT key_hash FROM device_keys WHERE id=?", (meta["id"],))
    assert stored["key_hash"] != raw
    assert len(stored["key_hash"]) == 64  # sha256 hex
    # Düz metin hiçbir yerde yok.
    assert db.row("SELECT COUNT(*) c FROM device_keys WHERE key_hash=?", (raw,))["c"] == 0


def test_revoked_key_is_rejected(db_ready, gate):
    raw, meta = ra.create_key("Eski telefon")
    assert ra.revoke_key(meta["id"]) is True
    req = FakeRequest(headers={"host": HOST, "x-device-key": raw})
    assert ra.check(req)[0] is False
    assert ra.list_keys()[0]["revoked"] is True


# --- Sertifika modu -------------------------------------------------------
def test_cert_mode_uses_forwarded_header(db_ready, monkeypatch):
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "cert-or-key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_CERT_HEADER", "cf-client-cert-verified")

    ok = FakeRequest(headers={"host": HOST, "cf-client-cert-verified": "true"})
    assert ra.check(ok) == (True, "cert")

    bad = FakeRequest(headers={"host": HOST, "cf-client-cert-verified": "false"})
    assert ra.check(bad)[0] is False

    # RFC 9440 başlığı da kabul edilir.
    rfc = FakeRequest(headers={"host": HOST, "client-cert": "MIIC..."})
    assert ra.check(rfc) == (True, "cert")


def test_cert_mode_rejects_key_when_only_cert_allowed(db_ready, monkeypatch):
    """mod=cert ise anahtar tek başına yetmez (sertifika zorunlu)."""
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "cert")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", False)
    raw, _ = ra.create_key("Telefon")
    req = FakeRequest(headers={"host": HOST, "x-device-key": raw})
    assert ra.check(req)[0] is False


# --- Deneme sınırı --------------------------------------------------------
def test_attempt_limit_blocks_bruteforce(db_ready, gate):
    ip = "198.51.100.7"
    for _ in range(ra._ATTEMPT_LIMIT):
        ra.record_attempt(ip)
    assert ra.rate_limited(ip) is True
    assert ra.attempts_left(ip) == 0
    ra.reset_attempts()
    assert ra.rate_limited(ip) is False


# --- Sayfalar -------------------------------------------------------------
def test_denied_page_is_turkish_and_has_no_leaks():
    page = ra.denied_page(HOST, "http://192.168.1.100:8089/")
    assert "Buraya erişim yetkiniz yok" in page
    assert HOST in page
    assert "192.168.1.100:8089" in page
    assert "/device-login" in page
    # Anahtar/şifre gibi bir sır sızdırmamalı.
    assert "tk_" not in page


def test_setup_page_shows_key_once_and_revoke(db_ready):
    raw, meta = ra.create_key("Telefon")
    html = ra.setup_page(ra.list_keys(), new_key=raw, csrf="abc")
    assert raw in html
    assert "yalnızca şimdi" in html
    assert meta["name"] in html
    assert "/setup/device/revoke" in html
    assert 'name="csrf" value="abc"' in html
    # Anahtar gösterilmezse sayfada olmamalı.
    assert raw not in ra.setup_page(ra.list_keys(), csrf="abc")


# --- Entegrasyon: cihaz girişi uç noktası --------------------------------
class _BodyRequest(FakeRequest):
    """`request.body()` destekleyen istek (form gövdesi ayrıştırması için)."""

    def __init__(self, raw: bytes, **kwargs):
        super().__init__(**kwargs)
        self._raw = raw
        self.method = "POST"

    async def body(self):
        return self._raw

    async def json(self):
        import json

        return json.loads(self._raw.decode("utf-8"))


def test_device_login_form_sets_long_lived_cookie(db_ready, monkeypatch):
    """Form POST → 303 + HttpOnly çerez; python-multipart gerekmez."""
    import asyncio
    import urllib.parse

    from app import main as main_module

    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    raw_key, _ = ra.create_key("Telefon")

    body = urllib.parse.urlencode({"key": raw_key, "next": "/"}).encode()
    request = _BodyRequest(
        body,
        path="/api/device/login",
        headers={
            "host": HOST,
            "content-type": "application/x-www-form-urlencoded",
            "cf-connecting-ip": "203.0.113.77",
        },
    )
    res = asyncio.run(main_module.device_login(request))
    assert res.status_code == 303
    cookie = res.headers.get("set-cookie", "")
    assert raw_key in cookie
    assert "httponly" in cookie.lower()
    assert "max-age=31536000" in cookie.lower()


def test_device_login_rejects_bad_key(db_ready, monkeypatch):
    import asyncio
    import urllib.parse

    from app import main as main_module

    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    ra.create_key("Telefon")

    body = urllib.parse.urlencode({"key": "tk_yanlis"}).encode()
    request = _BodyRequest(
        body,
        path="/api/device/login",
        headers={"host": HOST, "content-type": "application/x-www-form-urlencoded"},
    )
    res = asyncio.run(main_module.device_login(request))
    assert res.status_code == 403
    assert "set-cookie" not in {k.lower() for k in res.headers}


def test_body_fields_parses_json_and_form():
    import asyncio

    from app import main as main_module

    json_req = _BodyRequest(
        b'{"key":"tk_abc","next":"/x"}',
        headers={"content-type": "application/json"},
    )
    assert asyncio.run(main_module._body_fields(json_req)) == {
        "key": "tk_abc",
        "next": "/x",
    }

    form_req = _BodyRequest(
        b"key=tk_abc&next=%2Fy",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert asyncio.run(main_module._body_fields(form_req)) == {
        "key": "tk_abc",
        "next": "/y",
    }


# --- Entegrasyon: middleware ---------------------------------------------
def test_middleware_blocks_remote_without_key(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    monkeypatch.setattr(paths, "db", tmp_path / "t.db")
    monkeypatch.setattr(db, "_WAL_READY", False)
    db.init_db()
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", True)
    ra.reset_attempts()

    from app import main as main_module

    # Yalnız middleware'i sınamak için küçük bir uygulama kur.
    mini = FastAPI()
    mini.middleware("http")(main_module.security_headers)

    @mini.get("/")
    async def home():
        return PlainTextResponse("gizli panel")

    @mini.get("/api/health")
    async def health():
        return {"ok": True}

    class _Client:
        def __init__(self, host):
            self.host = host

    captured = {}

    def handler(request):
        # Gerçek sunucu olmadan middleware'i doğrudan çağır.
        request.scope["type"] = "http"
        return request

    # Middleware fonksiyonunu doğrudan test edelim (TestClient bağımlılığı yok).
    import asyncio

    class Req:
        url = _URL("/")
        headers = {"host": HOST}
        cookies = {}
        client = _Client("203.0.113.9")

        async def form(self):
            return {}

        async def json(self):
            raise ValueError

    async def fake_call_next(_request):
        from fastapi.responses import PlainTextResponse as PR

        return PR("gizli panel")

    res = asyncio.run(main_module.security_headers(Req(), fake_call_next))
    assert res.status_code == 403
    assert "erişim yetkiniz yok" in res.body.decode("utf-8").lower()

    # API yolu JSON 403 döner (SPA hatası yerine).
    class ApiReq(Req):
        url = _URL("/api/bots")

    res = asyncio.run(main_module.security_headers(ApiReq(), fake_call_next))
    assert res.status_code == 403
    assert b"yetkiniz yok" in res.body

    # Sağlık kontrolü muaftır.
    class HealthReq(Req):
        url = _URL("/api/health")

    res = asyncio.run(main_module.security_headers(HealthReq(), fake_call_next))
    assert res.status_code == 200

    # Anahtarla geçer.
    raw, _ = ra.create_key("Telefon")

    class KeyReq(Req):
        cookies = {"tradeai_device": raw}

    res = asyncio.run(main_module.security_headers(KeyReq(), fake_call_next))
    assert res.status_code == 200
    assert res.body == b"gizli panel"
