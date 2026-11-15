"""Web portunun `.env` içindeki TRADEAI_PORT'tan geldiğini doğrular.

Regresyon: port bir zamanlar Dockerfile ve docker-compose içinde sabit 8080
yazılıydı; `.env` değişse bile uygulama 8080'de kalıyordu.
"""

from app.config import BASE_DIR, _int


def test_dockerfile_port_from_env():
    text = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "${TRADEAI_PORT:-8080}" in text, "uvicorn portu env'den okunmalı"
    assert '"--port", "8080"' not in text, "sabit port kalmamalı"
    assert "os.getenv('TRADEAI_PORT'" in text, "healthcheck env portunu kullanmalı"


def test_compose_port_from_env():
    text = (BASE_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:${TRADEAI_PORT:-8080}:${TRADEAI_PORT:-8080}" in text
    assert "TRADEAI_PORT" in text.split("healthcheck:")[-1], "healthcheck env portunu kullanmalı"


def test_int_parses_port(monkeypatch):
    monkeypatch.setenv("TRADEAI_PORT", "8089")
    assert _int("TRADEAI_PORT", 8080) == 8089
    monkeypatch.setenv("TRADEAI_PORT", "bozuk")
    assert _int("TRADEAI_PORT", 8080) == 8080