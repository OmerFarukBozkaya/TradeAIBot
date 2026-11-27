"""Host-network tüneli senaryosu: istek 127.0.0.1'den gelir ama CF başlığı vardır.

Sunucuda cloudflared `network_mode: host` ile çalışıyor; uygulamaya bağlantı
loopback'ten gelir. "Loopback = LAN" sayılırsa tünelden gelen herkes kapıyı
atlar. Bu test bunun olmadığını doğrular.
"""

from __future__ import annotations

from app import remote_access as ra

HOST = "tradeai.studiowl.com.tr"


class _URL:
    path = "/"


class _Client:
    host = "127.0.0.1"


class Req:
    url = _URL()
    cookies: dict = {}

    def __init__(self, headers):
        self.headers = headers
        self.client = _Client()


def test_host_network_tunnel_is_not_treated_as_lan(monkeypatch):
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", True)

    # Tünelden gelen istek: loopback'ten ama CF başlıkları var.
    tunnel = Req({"host": HOST, "cf-connecting-ip": "203.0.113.7", "cf-ray": "8f-IST"})
    assert ra.client_ip(tunnel) == "203.0.113.7"
    assert ra.is_lan_request(tunnel) is False, "tünel trafiği LAN sayıldı (kapı atlanır)"
    assert ra.check(tunnel)[0] is False

    # Gerçek LAN erişimi (başlıksız, özel IP) serbest kalmalı.
    class LanClient:
        host = "192.168.1.50"

    lan = Req({"host": HOST})
    lan.client = LanClient()
    assert ra.check(lan) == (True, "lan")


def test_loopback_without_cf_headers_is_local(monkeypatch):
    """Sunucunun kendisinden (curl localhost) erişim LAN sayılır — beklenen."""
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", True)
    req = Req({"host": HOST})
    assert ra.check(req) == (True, "lan")


def test_strict_mode_blocks_even_loopback(monkeypatch):
    """REMOTE_ALLOW_LAN=false: LAN/loopback da anahtar ister (en sıkı)."""
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_MODE", "key")
    monkeypatch.setattr(ra.settings, "REMOTE_ACCESS_HOST", HOST)
    monkeypatch.setattr(ra.settings, "REMOTE_ALLOW_LAN", False)
    req = Req({"host": HOST})
    assert ra.check(req)[0] is False
