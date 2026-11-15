"""Arayüz yönlendirme (routing) regresyon testleri.

Sayfa geçişlerinde eski sayfanın takılı kalması / yeni sayfanın ezilmesi
sorununun geri dönmemesi için kaynak kod üzerinde yapısal kontroller.
"""

from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "web" / "app.js"


def source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_route_is_serialized():
    """Aynı anda yalnızca bir render: serileştirme bayrakları bulunmalı."""
    src = source()
    assert "state.routeBusy" in src, "render serileştirme bayrağı yok"
    assert "state.routeQueued" in src, "gezinme birleştirme bayrağı yok"
    assert "state.routeSeq" in src, "gezinme sıra numarası yok"
    # route() içinde kuyruk döngüsü olmalı
    assert "while (state.routeQueued" in src


def test_old_nav_guard_removed():
    """Eski (yetersiz) innerHTML yaması kaldırılmış olmalı."""
    src = source()
    assert "installNavGuard" not in src
    assert "state.nav" not in src


def test_single_bots_refresh_timer():
    """Botlar sayfası için tek bir yenileme timer'ı kurulmalı (çift timer olmaz)."""
    src = source()
    body = src.split("function scheduleBotsRefresh()", 1)[1].split("\n}", 1)[0]
    assert body.count("setInterval") == 2  # 15 sn yenileme + 5 sn anlık K/Z
    # renderBots içinde ayrıca timer kurulmamalı
    render_bots = src.split("async function renderBots(root)", 1)[1].split("\n}", 1)[0]
    assert "setInterval" not in render_bots, "renderBots kendi timer'ını kurmamalı"
    assert "scheduleBotsRefresh()" in render_bots


def test_timers_respect_route_busy():
    """Arka plan yenilemeleri render sürerken içeriğe yazmamalı."""
    src = source()
    for fn in ("scheduleDashboardRefresh", "scheduleBotsRefresh", "refreshJobMonitor"):
        chunk = src.split(f"function {fn}", 1)[1][:900]
        assert "state.routeBusy" in chunk, f"{fn} render sürerken durmalı"


def test_route_clears_content_synchronously():
    """Gezinmede eski içerik beklemeden temizlenmeli."""
    src = source()
    route_body = src.split("async function renderRoute()", 1)[1]
    assert "Yükleniyor" in route_body
    # temizlik, render çağrısından ÖNCE olmalı
    assert route_body.index("Yükleniyor") < route_body.index("await render(content)")


def test_route_always_marks_rendered_view():
    """Render hata verse bile görünüm işaretlenir (yeniden çizim doğru karar verir)."""
    src = source()
    body = src.split("async function renderRoute()", 1)[1].split("\n}", 1)[0]
    assert "state.renderedView = view" in body
    assert "finally" in body


def test_route_handles_badge_nav_links():
    """Hızlı ardışık gezinmeler birleştirilir; son hedef kazanır."""
    src = source()
    assert "state.routeSeq += 1" in src
    assert "if (seq !== state.routeSeq) state.routeQueued = true;" in src
