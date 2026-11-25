"""Canlı izleme arayüzü: düğme yeri, 10 sn yenileme, mum grafiği ve kaydırma."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")


def _bot_card() -> str:
    return JS.split("function botCard(bot, seriesMap = {}) {", 1)[1].split(
        "async function botAction(", 1
    )[0]


def test_live_watch_button_is_next_to_analysis_magnifier():
    card = _bot_card()
    # İnceleme (büyüteç) düğmesiyle aynı başlık satırında ve ondan hemen önce.
    assert 'data-action="livewatch"' in card
    assert 'class="icon-btn live-watch-btn"' in card
    live_at = card.index('data-action="livewatch"')
    analysis_at = card.index('data-action="analysis"')
    assert live_at < analysis_at, "Canlı izle, büyütecin yanında/solunda olmalı"
    # Aradaki tek şey kapanış etiketi; aynı satır bloğunda kalmalı.
    between = card[live_at:analysis_at]
    assert "icon-btn" in between or "</button>" in between
    # Düğme yalnızca açık pozisyon varken üretilir.
    assert '${pos ? `<button class="icon-btn live-watch-btn"' in card
    # Eski kopyalar (pozisyon şeridi / aksiyon satırı) kaldırıldı: tek yer.
    assert card.count('data-action="livewatch"') == 1


def test_dashboard_row_has_live_watch_only_with_position():
    row = JS.split("function botRow(bot, seriesMap = {}) {", 1)[1].split(
        "function quickBot()", 1
    )[0]
    assert 'data-live-watch="${esc(bot.id)}"' in row
    assert "Canlı izle" in row
    assert "pozisyon yok" in row


def test_live_watch_refreshes_every_ten_seconds():
    match = re.search(r"const LIVE_WATCH_MS = (\d+);", JS)
    assert match, "canlı izleme aralığı tanımlı değil"
    assert int(match.group(1)) == 10000
    assert "setInterval(() => {" in JS
    # Mum sayısı ayarlanabilir (daha fazla geçmiş yükleme) ve ilk değer 150.
    assert "live-chart?candles=${watch.limit}" in JS
    assert "limit: 150" in JS
    assert '"live-more"' in JS


def test_live_watch_timer_is_cleared_on_modal_close():
    assert "function stopLiveWatch()" in JS
    modal_body = JS.split("function modal(title, content) {", 1)[1].split(
        "function closeModal()", 1
    )[0]
    assert "stopLiveWatch()" in modal_body
    close_body = JS.split("function closeModal() {", 1)[1].split("\n}", 1)[0]
    assert "stopLiveWatch()" in close_body


def test_live_watch_chart_is_candlestick_with_levels():
    assert "function _applyLiveChart(" in JS
    assert 'refs.push({ value: entryPrice, color: "#34d399", label: "alış" })' in JS
    assert 'refs.push({ value: stop, color: "#fb7185", label: "stop"' in JS
    assert "last.c = live;" in JS
    assert "refs: d.refs || []" in JS
    assert "const useCandles = pts.length <= 320 && spacing >= 2.2;" in JS
    assert "const medianStep" in JS


def test_pan_is_pixel_based_and_survives_redraws():
    """Sürükleme SVG düğümüne bağlı olmamalı; her yeniden çizimde kopuyordu."""
    down = JS.split("window.tcDown = (ev) => {", 1)[1].split("let _tcDragRaf", 1)[0]
    assert "startX: ev.clientX" in down
    assert "lo0: d.lo" in down and "hi0: d.hi" in down
    assert "plotPx" in down
    # Eski hata: düğüm ayrıldığında sürükleme duruyordu.
    move = JS.split('document.addEventListener("pointermove", (ev) => {', 1)[1].split(
        '["pointerup"', 1
    )[0]
    assert "isConnected" not in move
    assert "_svgPoint" not in move
    assert "ev.clientX - g.startX" in move
    # Kare başına tek çizim ve sınır koruması.
    assert "requestAnimationFrame" in move
    assert "g.lo0 + shift" in move
    assert "d.fullLo" in move and "d.fullHi" in move


def test_chart_supports_pointer_pan_wheel_zoom_double_click_reset():
    assert 'onpointerdown="window.tcDown(event)"' in JS
    assert 'ondblclick="window.tcReset()"' in JS
    assert 'onwheel="return window.tcWheel(event)"' in JS
    wheel = JS.split("window.tcWheel = (ev) => {", 1)[1].split("window.tcDown", 1)[0]
    # Shift+tekerlek / yatay tekerlek kaydırır, dikey tekerlek imleçte yakınlaştırır.
    assert "ev.shiftKey" in wheel
    assert "ev.deltaX" in wheel
    assert "Math.pow(1.0018" in wheel
    # Sürükleme sırasında crosshair kapalı.
    hover = JS.split("function _chartHoverMove(ev) {", 1)[1].split("\n}", 1)[0]
    assert "if (TC.drag) return;" in hover


def test_pan_cursor_styles_exist():
    assert "svg.trade-chart { cursor: grab; }" in CSS
    assert "svg.trade-chart.is-panning { cursor: grabbing; }" in CSS
    assert "body.tc-panning" in CSS
    assert "button.live-watch-btn" in CSS
    assert "livePulse" in CSS
