"""Mobil uyumluluk: stil ve menü davranışının kalıcı denetimi."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def test_viewport_meta_present():
    assert 'name="viewport"' in HTML
    assert "width=device-width" in HTML


def test_mobile_drawer_markup_exists():
    assert 'id="nav-toggle"' in HTML
    assert 'id="nav-backdrop"' in HTML
    assert "aria-expanded" in HTML
    assert "aria-controls" in HTML


def test_drawer_breakpoint_matches_js_and_css():
    """Mobil menü kırılma noktası CSS ile JS'te aynı olmalı."""
    js_break = re.search(r'matchMedia\("\(max-width: (\d+)px\)"\)', JS)
    assert js_break, "JS'te mobil menü sorgusu yok"
    limit = int(js_break.group(1))
    assert limit == 1020
    # Çekmece kuralı bu genişlikte devreye girmeli.
    assert f"@media (max-width: {limit}px)" in CSS
    assert ".sidebar.open" in CSS
    assert "transform: translateX(-104%)" in CSS


def test_drawer_helpers_wire_up_events():
    for name in ("setupMobileNav", "setNavOpen", "closeNav"):
        assert f"function {name}" in JS
    assert "nav-backdrop" in JS
    assert "body.classList.toggle(\"nav-open\"" in JS
    assert "Escape" in JS  # klavye ile kapatma
    # Menüden sayfa seçilince kapanmalı.
    assert '$$("#nav a").forEach((a) => a.addEventListener("click", closeNav))' in JS


def test_modal_closes_drawer():
    """Modal açılırken çekmece açık kalırsa arka plan kilitli görünür."""
    start = JS.index("function modal(title, content)")
    block = JS[start : start + 400]
    assert "closeNav()" in block


def test_touch_targets_and_table_scroll():
    assert "min-height: 38px" in CSS
    assert "-webkit-overflow-scrolling: touch" in CSS
    # iOS'ta odakta zoom olmaması için 16px giriş fontu.
    assert re.search(r"input, select, textarea \{ font-size: 16px", CSS)
    # Uzun tablolar yatay kaydırılır, dar tablolar zorlanmaz.
    assert ".ana-table, .trade-table, .cmp-table { min-width: 620px; }" in CSS
    assert ".ind-table { min-width: 100%; }" in CSS


def test_stat_grid_reflows_on_mobile():
    assert ".stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }" in CSS
    assert ".ana-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in CSS
    # Çok dar ekranda tek sütun.
    assert "@media (max-width: 380px)" in CSS


def test_safe_area_and_overflow_guards():
    assert "overflow-x: hidden" in CSS
    assert "100dvh" in CSS
    assert "overscroll-behavior: contain" in CSS


def test_print_and_landscape_rules():
    assert "@media print" in CSS
    assert "orientation: landscape" in CSS


def test_bot_card_icon_button_is_scoped():
    """Daire ikon stili yalnızca bot kartına uygulanmalı (üst çubuk bozulmasın)."""
    assert ".bot-card button.icon-btn {" in CSS
    # Genel kural olarak kalmamalı.
    assert not re.search(r"^button\.icon-btn \{", CSS, re.MULTILINE)
