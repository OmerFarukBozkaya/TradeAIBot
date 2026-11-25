"""Canlı izleme arayüzü: düğme, 10 sn yenileme, mum grafiği ve seviyeler."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")


def test_live_watch_button_only_with_position():
    # Pozisyon varken hem bot kartında hem dashboard satırında düğme çıkar.
    assert 'data-action="livewatch"' in JS
    assert 'data-live-watch="${esc(bot.id)}"' in JS
    assert "Canlı izle" in JS
    # Bot kartındaki düğme yalnızca açık pozisyon bloğunda üretilir.
    marker = "${pos ? `"
    strip = JS.split(marker, 1)[1].split("Açık pozisyon yok.", 1)[0]
    assert "live-watch-btn" in strip
    # Aksiyon satırındaki düğme de pozisyon koşuluna bağlı.
    assert 'pos ? `<button class="ghost live-watch-btn"' in JS


def test_live_watch_refreshes_every_ten_seconds():
    match = re.search(r"const LIVE_WATCH_MS = (\d+);", JS)
    assert match, "canlı izleme aralığı tanımlı değil"
    assert int(match.group(1)) == 10000
    assert "setInterval(() => {" in JS
    assert "/live-chart?candles=150" in JS


def test_live_watch_timer_is_cleared_on_modal_close():
    assert "function stopLiveWatch()" in JS
    # Modal açılırken ve kapanırken eski izleme durdurulur.
    modal_body = JS.split("function modal(title, content) {", 1)[1].split("function closeModal()", 1)[0]
    assert "stopLiveWatch()" in modal_body
    close_body = JS.split("function closeModal() {", 1)[1].split("\n}", 1)[0]
    assert "stopLiveWatch()" in close_body


def test_live_watch_chart_is_candlestick_with_levels():
    assert "function _applyLiveChart(" in JS
    assert 'refs.push({ value: entryPrice, color: "#34d399", label: "alış" })' in JS
    assert 'refs.push({ value: stop, color: "#fb7185", label: "stop"' in JS
    # Son mum canlı fiyatla güncellenir (10 sn'de bir "canlı" mum).
    assert "last.c = live;" in JS
    # Referans çizgileri çizime aktarılır (yeniden çizim yolu).
    assert "refs: d.refs || []" in JS
    # Canlı izleme grafiği mum çizer: eşik ve mum genişliği zaman aralığından.
    assert "const useCandles = pts.length <= 320 && spacing >= 2.2;" in JS
    assert "const medianStep" in JS


def test_live_watch_button_has_style():
    assert "button.live-watch-btn" in CSS
    assert "livePulse" in CSS
