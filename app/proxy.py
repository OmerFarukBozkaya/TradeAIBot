"""Ters proxy (Cloudflare Tunnel / nginx) arkasında gerçek şema tespiti.

Cloudflare Tunnel, tarayıcı ile Cloudflare arasında HTTPS kurar; Cloudflare ile
uygulama arasındaki bağlantı ise ``http://`` olabilir. Bu nedenle uygulama
``request.url.scheme`` ile yalnızca ``http`` görür ve ``Secure`` çerez
işaretlenmez. Tarayıcının gördüğü şema ``X-Forwarded-Proto`` başlığındadır.

Güvenlik notu: bu başlığa yalnızca güvenilen bir proxy'den geliyorsa güvenilir.
Uygulama normalde yalnızca yerel ağa/loopback'e bağlanır; dışarıdan doğrudan
erişim yoksa başlık sahtelemesi mümkün değildir. ``TRADEAI_TRUST_PROXY=false``
ile tamamen kapatılabilir.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings


def _first_header(value: Optional[str]) -> str:
    """``a, b`` biçimindeki başlık zincirinden ilk (istemciye en yakın) değeri alır."""
    if not value:
        return ""
    return str(value).split(",")[0].strip().lower()


def forwarded_proto(headers) -> str:
    """İsteğin gerçek şeması: ``https`` / ``http`` / boş."""
    if not getattr(settings, "TRUST_PROXY", True):
        return ""
    proto = _first_header(headers.get("x-forwarded-proto"))
    if proto:
        return proto
    # Standart `Forwarded: for=...;proto=https` biçimi.
    forwarded = headers.get("forwarded")
    if forwarded:
        for part in str(forwarded).split(";"):
            key, _, value = part.partition("=")
            if key.strip().lower() == "proto":
                return value.strip().strip('"').lower()
    return ""


def is_secure_request(request) -> bool:
    """İstek tarayıcı tarafında HTTPS mi?

    Doğrudan TLS (``request.url.scheme``) veya güvenilen proxy başlığı.
    """
    if getattr(request.url, "scheme", "") == "https":
        return True
    return forwarded_proto(request.headers) == "https"


def cookie_secure(request=None) -> bool:
    """Çerez ``Secure`` bayrağı: ayar açıksa veya istek HTTPS ise.

    Cloudflare Tunnel arkasında ayarı elle açmayı unutsan bile oturum çerezi
    HTTPS'te ``Secure`` olur; yerel HTTP erişiminde (telefonun aynı ağda
    olması) ise çerez çalışmaya devam eder.
    """
    if bool(getattr(settings, "COOKIE_SECURE", False)):
        return True
    if request is None:
        return False
    try:
        return is_secure_request(request)
    except Exception:  # noqa: BLE001 - tespit başarısızsa ayara dön
        return False
