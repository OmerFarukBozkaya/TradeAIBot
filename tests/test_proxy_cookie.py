"""Ters proxy arkasında güvenli çerez ve HSTS davranışı.

Cloudflare Tunnel tarayıcı↔Cloudflare arasında HTTPS kurar, uygulamaya ise
HTTP iletir. Uygulama ``X-Forwarded-Proto: https`` gördüğünde çerezi `Secure`
işaretlemeli; yerel HTTP erişiminde ise oturum çalışmaya devam etmelidir.
"""

from __future__ import annotations

import pytest

from app import proxy


class FakeURL:
    def __init__(self, scheme: str):
        self.scheme = scheme


class FakeRequest:
    def __init__(self, headers: dict | None = None, scheme: str = "http"):
        self.headers = headers or {}
        self.url = FakeURL(scheme)


@pytest.fixture()
def trust_proxy(monkeypatch):
    monkeypatch.setattr(proxy.settings, "TRUST_PROXY", True)
    monkeypatch.setattr(proxy.settings, "COOKIE_SECURE", False)


def test_forwarded_proto_https(trust_proxy):
    req = FakeRequest({"x-forwarded-proto": "https"})
    assert proxy.is_secure_request(req) is True
    assert proxy.cookie_secure(req) is True


def test_forwarded_proto_chain_takes_first(trust_proxy):
    req = FakeRequest({"x-forwarded-proto": "https, http"})
    assert proxy.forwarded_proto(req.headers) == "https"


def test_local_http_stays_insecure_so_lan_login_works(trust_proxy):
    req = FakeRequest({})
    assert proxy.is_secure_request(req) is False
    assert proxy.cookie_secure(req) is False


def test_standard_forwarded_header(trust_proxy):
    req = FakeRequest({"forwarded": 'for=1.2.3.4;proto=https;by=cf'})
    assert proxy.forwarded_proto(req.headers) == "https"
    assert proxy.cookie_secure(req) is True


def test_direct_tls_is_secure(trust_proxy):
    req = FakeRequest({}, scheme="https")
    assert proxy.cookie_secure(req) is True


def test_trust_proxy_disabled_ignores_header(monkeypatch):
    monkeypatch.setattr(proxy.settings, "TRUST_PROXY", False)
    monkeypatch.setattr(proxy.settings, "COOKIE_SECURE", False)
    req = FakeRequest({"x-forwarded-proto": "https"})
    assert proxy.is_secure_request(req) is False
    assert proxy.cookie_secure(req) is False


def test_explicit_setting_forces_secure_even_on_http(monkeypatch):
    monkeypatch.setattr(proxy.settings, "TRUST_PROXY", True)
    monkeypatch.setattr(proxy.settings, "COOKIE_SECURE", True)
    assert proxy.cookie_secure(FakeRequest({})) is True


def test_login_cookie_is_secure_behind_tunnel(tmp_path, monkeypatch):
    """Uçtan uca: HTTPS başlığıyla giriş → Set-Cookie Secure içerir."""
    import asyncio
    import os

    from fastapi import Response

    from app import db, security
    from app.api import auth as auth_api
    from app.paths import paths

    monkeypatch.setattr(paths, "db", tmp_path / "t.db")
    monkeypatch.setattr(db, "_WAL_READY", False)
    db.init_db()
    security.bootstrap_admin()
    monkeypatch.setattr(proxy.settings, "TRUST_PROXY", True)
    monkeypatch.setattr(proxy.settings, "COOKIE_SECURE", False)

    user = db.row("SELECT username FROM users LIMIT 1") or {"username": "admin"}
    password = os.getenv("ADMIN_PASSWORD", "DegistirBeni123!")
    body = auth_api.LoginBody(username=user["username"], password=password)

    # Cloudflare Tunnel: tarayıcı HTTPS, uygulama HTTP + X-Forwarded-Proto.
    res = Response()
    asyncio.run(auth_api.login(body, FakeRequest({"x-forwarded-proto": "https"}), res))
    cookie = res.headers.get("set-cookie", "")
    assert "secure" in cookie.lower()
    assert "httponly" in cookie.lower()

    # Aynı giriş yerel HTTP'de Secure olmamalı (LAN'da oturum bozulmasın).
    res2 = Response()
    asyncio.run(auth_api.login(body, FakeRequest({}), res2))
    assert "secure" not in res2.headers.get("set-cookie", "").lower()
