"""Tek compose dosyası: tunnel ve AI profillerle ayrılmış olmalı.

Regresyon: tunnel ayrı bir `docker-compose.tunnel.yml` dosyasındaydı; kullanıcı
tek dosya ve profil tabanlı ayrım istedi. Ayrıca tunnel'ın varsayılan
kurulumda **başlamaması** güvenlik açısından önemlidir (yanlışlıkla açık
kalmasın).
"""

from __future__ import annotations

import re

from app.config import BASE_DIR

COMPOSE = (BASE_DIR / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    """`services:` altındaki tek bir servis bloğunu döndürür."""
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)",
        COMPOSE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"{name} servisi yok"
    return match.group(1)


def test_single_compose_file_and_no_tunnel_file():
    assert (BASE_DIR / "docker-compose.yml").exists()
    assert not (BASE_DIR / "docker-compose.tunnel.yml").exists(), (
        "tunnel ayrı dosyada olmamalı; tek compose + profil kullanılmalı"
    )


def test_cloudflared_behind_tunnel_profile():
    block = _service_block("cloudflared")
    assert 'profiles: ["tunnel"]' in block
    assert "TUNNEL_TOKEN" in block
    assert "cloudflare/cloudflared" in block
    # Aynı docker ağında servis adıyla çözülsün: ayrı network tanımı yok.
    assert "networks:" not in block


def test_tradeai_has_no_profile_so_it_always_starts():
    block = _service_block("tradeai")
    assert "profiles:" not in block, "panel profilsiz olmalı (varsayılan başlar)"


def test_ai_still_uses_ai_profile():
    block = _service_block("ai")
    assert 'profiles: ["ai"]' in block


def test_tunnel_is_hardened():
    block = _service_block("cloudflared")
    assert "read_only: true" in block
    assert "no-new-privileges:true" in block
    assert "cap_drop:" in block and "ALL" in block
    # Tradeai sağlıklı olmadan başlamasın (boş sayfa göstermesin).
    assert "service_healthy" in block


def test_tunnel_documents_profile_usage():
    assert "profiles: [\"tunnel\"]" in COMPOSE
    assert "--profile tunnel" in COMPOSE
