/* TradeAIBot web arayüzü — bağımlılıksız vanilla JS */
"use strict";

const state = {
  user: null,
  csrf: null,
  catalog: null,
  bots: [],
  stats: null,
  liveEnabled: false,
  liveUnlocked: false,
  booted: false,
  view: "dashboard",
  nav: 0,
  routeBusy: false,
  routeQueued: false,
  routeSeq: 0,
  renderedView: null,
  refreshTimer: null,
  liveTimer: null,
  jobTimer: null,
  jobMonitorTimer: null,
};
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("tr-TR", { maximumFractionDigits: digits });
}
function money(value) { return fmt(value, 2) + " USDT"; }
function signedMoney(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${money(n)}`;
}
function pnlClass(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? "pos" : Number.isFinite(n) && n < 0 ? "neg" : "";
}
function stopDistanceText(distancePct) {
  const d = Number(distancePct);
  if (!Number.isFinite(d)) return "";
  if (d >= 90) return "(geniş — felaket koruması)";
  return `(${fmt(d, 1)}% uzak)`;
}
function botTotalPnl(bot) {
  const st = (bot && bot.state) || {};
  if (st.total_pnl !== null && st.total_pnl !== undefined) return Number(st.total_pnl);
  return Number(st.total_realized_pnl) || 0;
}
/* Anlık değerleri (fiyat, K/Z) tam yeniden çizim yapmadan günceller. */
function applyLiveValues(bots) {
  const set = (key, text, cls) => {
    const el = document.querySelector(`[data-live="${key}"]`);
    if (!el) return;
    el.textContent = text;
    if (cls !== undefined) {
      el.classList.remove("pos", "neg");
      if (cls) el.classList.add(cls);
    }
  };
  let totalSum = 0;
  let unrealSum = 0;
  bots.forEach((b) => {
    const st = b.state || {};
    const total = botTotalPnl(b);
    totalSum += total;
    unrealSum += Number(st.unrealized_pnl) || 0;
    set(`unreal-${b.id}`, st.unrealized_pnl === null || st.unrealized_pnl === undefined ? "—" : signedMoney(st.unrealized_pnl), pnlClass(st.unrealized_pnl));
    set(`total-${b.id}`, st.total_pnl === null || st.total_pnl === undefined ? "—" : signedMoney(st.total_pnl), pnlClass(st.total_pnl));
    set(`equity-${b.id}`, money(st.equity));
    const pos = st.position;
    if (pos) {
      set(`price-${b.id}`, fmt(pos.last_price, 8));
      set(`pnlpct-${b.id}`, `${fmt(pos.unrealized_pnl_pct, 2)}%`, pnlClass(pos.unrealized_pnl_pct));
      set(`rowpnl-${b.id}`, `${Number(pos.unrealized_pnl_pct) > 0 ? "+" : ""}${fmt(pos.unrealized_pnl_pct, 2)}%`, pnlClass(pos.unrealized_pnl_pct));
      if (pos.stop_price) {
        set(`stop-${b.id}`, fmt(pos.stop_price, 8));
        set(`stopdist-${b.id}`, stopDistanceText(pos.stop_distance_pct));
      }
    }
  });
  const tb = $("#tb-pnl");
  if (tb) {
    tb.textContent = signedMoney(totalSum);
    tb.className = pnlClass(totalSum);
    tb.title = `Toplam K/Z = gerçekleşen + anlık açık K/Z (anlık: ${signedMoney(unrealSum)})`;
  }
  set("dash-total", signedMoney(totalSum), pnlClass(totalSum));
  set("dash-unreal", `anlık ${signedMoney(unrealSum)}`, pnlClass(unrealSum));
  return { totalSum, unrealSum };
}
async function refreshLivePnl() {
  try {
    const bots = await api("/bots");
    state.bots = bots;
    applyLiveValues(bots);
  } catch (err) { /* anlık güncelleme kritik değil */ }
}

/** Grafik ekseni için kısa tarih: 12.11.26 14:00 veya 12.11.26 */
function shortDate(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  const ms = n > 1e11 ? n : n * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  const day = d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "2-digit" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${day} ${hh}:${mm}`;
}

/** Epoch (ms/sn) veya ISO metnini okunur yerel tarih-saate çevirir. */
function fmtTime(value, opts = {}) {
  if (value === null || value === undefined || value === "") return "—";
  let date = null;
  if (typeof value === "number" || /^\d+$/.test(String(value))) {
    let n = Number(value);
    if (n > 1e11) n = n;            // milisaniye
    else if (n > 1e9) n = n * 1000; // saniye
    else return String(value);      // tarih değil (mum sayacı vb.)
    date = new Date(n);
  } else {
    date = new Date(String(value).replace(" ", "T"));
  }
  if (!date || Number.isNaN(date.getTime())) return String(value);
  const withTime = opts.time !== false;
  const day = date.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" });
  if (!withTime) return day;
  const time = date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  return `${day} ${time}`;
}

/** Dashboard ve tablolarda kullanılan kısa ISO biçimi (yerel saate çevirir). */
function fmtIso(value) {
  return value ? fmtTime(value) : "—";
}
function pct(value) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return `<span class="${n >= 0 ? "tag green" : "tag red"}">${n >= 0 ? "+" : ""}${fmt(n, 2)}%</span>`;
}
// Mum sayısı × periyot → "3 yıl 4 ay 12 gün" (teorik kapsam).
const TF_MS = { "1m": 6e4, "3m": 18e4, "5m": 3e5, "15m": 9e5, "30m": 18e5, "1h": 36e5, "2h": 72e5, "4h": 144e5, "6h": 216e5, "8h": 288e5, "12h": 432e5, "1d": 864e5 };
function periodSpanText(candles, period) {
  const ms = TF_MS[period] || 36e5;
  const days = (Number(candles || 0) * ms) / 864e5;
  const y = Math.floor(days / 365);
  const rem = days - y * 365;
  const m = Math.floor(rem / 30);
  const d = Math.floor(rem - m * 30);
  const parts = [];
  if (y) parts.push(`${y} yıl`);
  if (m) parts.push(`${m} ay`);
  if (d || !parts.length) parts.push(`${d} gün`);
  return parts.join(" ");
}
// Mum sayısı seçenekleri: periyoda göre kapsanan süreyi gösterir.
// Borsa geçmişi ~9 yıl olduğundan bunu aşan istekler "tüm geçmiş" olarak etiketlenir.
const HISTORY_YEARS = 9;
function limitSpanLabel(candles, period) {
  const ms = TF_MS[period] || 36e5;
  const fullCandles = (HISTORY_YEARS * 365 * 864e5) / ms;
  if (Number(candles) > fullCandles) return "tüm geçmiş";
  return `≈ ${periodSpanText(candles, period)}`;
}
const LIMIT_CHOICES = [3000, 5000, 10000, 20000, 50000, 100000, 250000];
function limitOptionsHtml(period, selected) {
  return LIMIT_CHOICES.map((l) => `<option value="${l}" ${Number(l) === Number(selected) ? "selected" : ""}>${l.toLocaleString("tr-TR")} mum ${limitSpanLabel(l, period)}</option>`).join("");
}
function refreshLimitOptions(select, period) {
  if (!select) return;
  const current = select.value || "20000";
  select.innerHTML = limitOptionsHtml(period, current);
  select.value = current;
}
function statusTag(status) {
  const map = {
    running: ["green", "çalışıyor"], stopped: ["gray", "durdu"], stopping: ["amber", "duruyor"],
    error: ["red", "hata"], reconciliation_required: ["amber", "mutabakat gerekli"],
  };
  const [cls, label] = map[status] || ["gray", status || "—"];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " err" : "");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 4000);
}
function modal(title, content) {
  $("#modal-title").textContent = title;
  const body = $("#modal-body");
  body.innerHTML = "";
  if (typeof content === "string") body.innerHTML = content;
  else body.appendChild(content);
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal-close").addEventListener("click", closeModal);

function confirmDialog(title, message, okLabel = "Onayla", danger = false) {
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <p class="muted confirm-text">${esc(message)}</p>
      <div class="row end mt">
        <button class="ghost" id="cd-no" type="button">Vazgeç</button>
        <button class="${danger ? "danger" : "primary"}" id="cd-yes" type="button">${esc(okLabel)}</button>
      </div>`;
    modal(title, wrap);
    $("#cd-yes").addEventListener("click", () => { closeModal(); resolve(true); });
    $("#cd-no").addEventListener("click", () => { closeModal(); resolve(false); });
  });
}

/* ------------------------------------------------------------------ */
/* Grafikler (bağımlılıksız SVG)                                       */
/* ------------------------------------------------------------------ */
let _chartSeq = 0;

function chartEmpty(height, message = "Veri bekleniyor") {
  return `<div class="chart-empty" style="height:${height}px">
    <svg viewBox="0 0 400 ${height}" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="${height - 30}" x2="400" y2="${height - 30}" stroke="rgba(120,156,210,.18)" stroke-dasharray="4 6"/>
    </svg>
    <span>${esc(message)}</span>
  </div>`;
}

/* ---------------- Etkileşimli fiyat grafiği (zoom / kaydırma) ---------------- */
const TC = { drag: null };

function tcData() {
  return window.__btData || null;
}

function tcClampView(lo, hi) {
  const d = tcData();
  if (!d) return { lo, hi };
  const full = d.fullHi - d.fullLo;
  const minSpan = Math.max(4, full / 4000);
  let span = Math.min(Math.max(hi - lo, minSpan), full);
  if (lo < d.fullLo) { lo = d.fullLo; hi = lo + span; }
  if (hi > d.fullHi) { hi = d.fullHi; lo = hi - span; }
  return { lo, hi };
}

function tcRedraw() {
  const d = tcData();
  if (!d) return;
  const wrap = document.getElementById("tc-wrap");
  if (!wrap) return;
  const vis = d.price.filter((p) => Number(p.idx) >= d.lo && Number(p.idx) <= d.hi);
  const ms = d.markers.filter((m) => Number(m.idx) >= d.lo && Number(m.idx) <= d.hi);
  wrap.innerHTML = tradePriceChart(vis.length >= 2 ? vis : d.price, ms, {
    height: 380, lo: d.lo, hi: d.hi,
  });
  const info = document.getElementById("tc-info");
  if (info) {
    const trades = new Set(ms.map((m) => m.no)).size;
    info.textContent = `${trades} işlem görünür · ${vis.length} mum · tekerlekle yakınlaş, sürükleyerek kaydır`;
  }
}
window.tcRedraw = tcRedraw;

window.tcZoom = (factor, anchorIdx) => {
  const d = tcData();
  if (!d) return;
  const span = d.hi - d.lo;
  const anchor = anchorIdx == null ? (d.lo + d.hi) / 2 : Number(anchorIdx);
  const full = d.fullHi - d.fullLo;
  let newSpan = span * factor;
  newSpan = Math.max(Math.max(4, full / 4000), Math.min(full, newSpan));
  const frac = span ? (anchor - d.lo) / span : 0.5;
  const v = tcClampView(anchor - newSpan * frac, anchor - newSpan * frac + newSpan);
  d.lo = v.lo;
  d.hi = v.hi;
  tcRedraw();
};

window.tcReset = () => {
  const d = tcData();
  if (!d) return;
  d.lo = d.fullLo;
  d.hi = d.fullHi;
  tcRedraw();
};

window.tcWheel = (ev) => {
  const d = tcData();
  if (!d) return true;
  ev.preventDefault();
  const r = ev.currentTarget.getBoundingClientRect();
  const padL = 58, padR = 16, vw = 760;
  const innerW = Math.max(1, r.width * (vw - padL - padR) / vw);
  const leftPx = r.width * padL / vw;
  const frac = Math.min(1, Math.max(0, (ev.clientX - r.left - leftPx) / innerW));
  const span = d.hi - d.lo;
  window.tcZoom(ev.deltaY > 0 ? 1.28 : 1 / 1.28, d.lo + span * frac);
  return false;
};

window.tcDown = (ev) => {
  const d = tcData();
  if (!d || ev.button !== 0) return;
  const r = ev.currentTarget.getBoundingClientRect();
  TC.drag = { x: ev.clientX, lo: d.lo, hi: d.hi, width: r.width };
  ev.preventDefault();
};

document.addEventListener("mousemove", (ev) => {
  const g = TC.drag, d = tcData();
  if (!g || !d) return;
  const span = g.hi - g.lo;
  const shift = -((ev.clientX - g.x) / Math.max(1, g.width)) * span;
  let lo = g.lo + shift, hi = g.hi + shift;
  if (lo < d.fullLo) { lo = d.fullLo; hi = lo + span; }
  if (hi > d.fullHi) { hi = d.fullHi; lo = hi - span; }
  d.lo = lo;
  d.hi = hi;
  tcRedraw();
});
document.addEventListener("mouseup", () => { TC.drag = null; });

window.tcFocus = (no) => {
  const d = tcData();
  if (!d) return;
  const ms = d.markers.filter((m) => Number(m.no) === Number(no));
  if (!ms.length) return;
  const lo = Math.min(...ms.map((m) => Number(m.idx)));
  const hi = Math.max(...ms.map((m) => Number(m.idx)));
  const padv = Math.max(10, Math.round((hi - lo) * 0.8));
  const v = tcClampView(lo - padv, hi + padv);
  d.lo = v.lo;
  d.hi = v.hi;
  tcRedraw();
  const wrap = document.getElementById("tc-wrap");
  if (wrap) wrap.scrollIntoView({ block: "center", behavior: "smooth" });
};


/* Satış nedeni renkleri: sinyal kırmızı, stop turuncu, kâr koruma camgöbeği. */
const SELL_REASON_STYLE = {
  signal: { color: "#fb7185", light: "#fda4af", label: "sinyal satışı" },
  stop: { color: "#f97316", light: "#fdba74", label: "stop" },
  trail: { color: "#f97316", light: "#fdba74", label: "takipli stop" },
  "takipli-stop": { color: "#f97316", light: "#fdba74", label: "takipli stop" },
  "profit-exit": { color: "#22d3ee", light: "#a5f3fc", label: "kâr koruma" },
  "kâr-koruma": { color: "#22d3ee", light: "#a5f3fc", label: "kâr koruma" },
  "take-profit": { color: "#34d399", light: "#6ee7b7", label: "kâr al" },
  end: { color: "#94a3b8", light: "#cbd5e1", label: "test sonu" },
};

function sellStyle(reason) {
  return SELL_REASON_STYLE[reason] || { color: "#fb7185", light: "#fda4af", label: reason || "sinyal satışı" };
}

function tradePriceChart(prices, markers, opts = {}) {
  const pts = (prices || [])
    .map((p) => ({
      idx: Number(p.idx), t: Number(p.t),
      o: Number(p.o != null ? p.o : p.c),
      h: Number(p.h != null ? p.h : p.c),
      l: Number(p.l != null ? p.l : p.c),
      c: Number(p.c),
    }))
    .filter((p) => Number.isFinite(p.idx) && Number.isFinite(p.c) && p.c > 0
      && Number.isFinite(p.h) && Number.isFinite(p.l) && p.h >= p.l);
  if (pts.length < 2) return chartEmpty(opts.height || 320);
  const h = opts.height || 320;
  const w = 760;
  const pad = { top: 16, right: 16, bottom: 34, left: 58 };
  const i0 = opts.lo != null ? Number(opts.lo) : pts[0].idx;
  const i1 = opts.hi != null ? Number(opts.hi) : pts[pts.length - 1].idx;
  const span = i1 - i0 || 1;
  const vals = pts.map((p) => p.c);
  let min = Math.min(...pts.map((p) => p.l));
  let max = Math.max(...pts.map((p) => p.h));
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    min = Math.min(...vals);
    max = Math.max(...vals);
  }
  const grip = (max - min) * 0.06 || max * 0.01;
  min -= grip;
  max += grip;
  const vspan = max - min || 1;
  const x = (idx) => pad.left + ((idx - i0) / span) * (w - pad.left - pad.right);
  const y = (v) => h - pad.bottom - ((v - min) / vspan) * (h - pad.top - pad.bottom);

  const labels = [0, 0.25, 0.5, 0.75, 1].map((r) => {
    const gy = pad.top + r * (h - pad.top - pad.bottom);
    const val = max - r * vspan;
    return `<line x1="${pad.left}" y1="${gy.toFixed(1)}" x2="${w - pad.right}" y2="${gy.toFixed(1)}"
              stroke="rgba(120,156,210,.10)" stroke-dasharray="3 5"/>
            <text x="${pad.left - 8}" y="${(gy + 4).toFixed(1)}" text-anchor="end"
              fill="#64748b" font-size="10">${fmt(val, 2)}</text>`;
  }).join("");

  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.idx).toFixed(1)},${y(p.c).toFixed(1)}`).join(" ");

  // Yakınlaşınca mum çiz; uzakta çizgi kullan.
  const slotW = (w - pad.left - pad.right) / Math.max(1, pts.length);
  const useCandles = pts.length <= 320 && slotW >= 2.6;
  const candleW = Math.max(1.2, Math.min(9, slotW * 0.62));
  const candlesSvg = useCandles ? pts.map((p) => {
    const up = p.c >= p.o;
    const col = up ? "#34d399" : "#fb7185";
    const cx = x(p.idx);
    const yo = y(p.o);
    const yc = y(p.c);
    const top = Math.min(yo, yc);
    const bodyH = Math.max(1, Math.abs(yc - yo));
    return `<g><title>${esc(fmtTime(p.t))} · A ${fmt(p.o, 4)} Y ${fmt(p.c, 4)} · Yük ${fmt(p.h, 4)} Düş ${fmt(p.l, 4)}</title>
      <line x1="${cx.toFixed(1)}" y1="${y(p.h).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(p.l).toFixed(1)}"
        stroke="${col}" stroke-width="1" opacity=".75"/>
      <rect x="${(cx - candleW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${candleW.toFixed(1)}"
        height="${bodyH.toFixed(1)}" fill="${col}" opacity=".85"/>
    </g>`;
  }).join("") : "";

  // X ekseninde tarih etiketleri (yakınlaşınca anlamlı)
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((r) => {
    const target = i0 + span * r;
    let best = pts[0], bestD = Infinity;
    for (const p of pts) {
      const d = Math.abs(p.idx - target);
      if (d < bestD) { bestD = d; best = p; }
    }
    return `<text x="${x(best.idx).toFixed(1)}" y="${(h - 8).toFixed(1)}" text-anchor="middle"
        fill="#64748b" font-size="9.5">${esc(shortDate(best.t))}</text>`;
  }).join("");

  // İşlem çiftleri: giriş → çıkış bağlantı çizgisi (hangi işlem olduğu görünsün)
  const ms = (markers || []).filter((m) => Number.isFinite(Number(m.idx)) && Number.isFinite(Number(m.price)));
  const byNo = {};
  for (const m of ms) {
    const n = Number(m.no);
    (byNo[n] = byNo[n] || {})[m.side === "sell" ? "sell" : "buy"] = m;
  }
  const tradeLines = Object.values(byNo)
    .filter((t) => t.buy && t.sell)
    .map((t) => {
      const st = sellStyle(t.sell.reason);
      return `<line x1="${x(Number(t.buy.idx)).toFixed(1)}" y1="${y(Number(t.buy.price)).toFixed(1)}"
        x2="${x(Number(t.sell.idx)).toFixed(1)}" y2="${y(Number(t.sell.price)).toFixed(1)}"
        stroke="${st.color}" stroke-width="1" opacity=".26"/>`;
    }).join("");

  const shownTrades = Object.keys(byNo).length;
  const showNums = shownTrades <= 60;
  const marks = Object.values(byNo).map((t) => {
    let svg = "";
    if (t.buy) {
      const bx = x(Number(t.buy.idx));
      const by = y(Number(t.buy.price));
      const title = `#${t.buy.no} AL · ${fmtTime(t.buy.time)} · ${fmt(t.buy.price, 4)}`;
      svg += `<g class="trade-mark"><title>${esc(title)}</title>
        <polygon points="${bx.toFixed(1)},${(by + 8).toFixed(1)} ${(bx - 5).toFixed(1)},${(by + 17).toFixed(1)} ${(bx + 5).toFixed(1)},${(by + 17).toFixed(1)}"
          fill="#34d399" stroke="#060b14" stroke-width="1"/>
        ${showNums ? `<text x="${bx.toFixed(1)}" y="${(by + 29).toFixed(1)}" text-anchor="middle" fill="#6ee7b7" font-size="9">${t.buy.no}</text>` : ""}
      </g>`;
    }
    if (t.sell) {
      const sx = x(Number(t.sell.idx));
      const sy = y(Number(t.sell.price));
      const pnl = Number(t.sell.pnl_pct);
      const st = sellStyle(t.sell.reason);
      const title = `#${t.sell.no} SAT · ${st.label} · ${fmtTime(t.sell.time)} · ${fmt(t.sell.price, 4)} · K/Z ${pnl >= 0 ? "+" : ""}${fmt(pnl, 2)}%`;
      svg += `<g class="trade-mark"><title>${esc(title)}</title>
        <polygon points="${sx.toFixed(1)},${(sy - 8).toFixed(1)} ${(sx - 5).toFixed(1)},${(sy - 17).toFixed(1)} ${(sx + 5).toFixed(1)},${(sy - 17).toFixed(1)}"
          fill="${st.color}" stroke="#060b14" stroke-width="1"/>
        ${showNums ? `<text x="${sx.toFixed(1)}" y="${(sy - 21).toFixed(1)}" text-anchor="middle" fill="${st.light}" font-size="9">${t.sell.no}</text>` : ""}
      </g>`;
    }
    return svg;
  }).join("");

  return `<svg class="chart-svg trade-chart" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img"
      style="cursor:grab;touch-action:none"
      onwheel="return window.tcWheel(event)"
      onmousedown="window.tcDown(event)">
    ${labels}
    ${xTicks}
    ${useCandles ? candlesSvg : `<path d="${line}" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linejoin="round"/>`}
    ${tradeLines}
    ${marks}
    <text x="${pad.left}" y="12" fill="#7f90aa" font-size="10">
      ${shownTrades} işlem · ${pts.length} mum · ${useCandles ? "mum" : "çizgi"} görünümü · tekerlek = yakınlaştır, sürükle = kaydır
    </text>
    <text x="${w - pad.right}" y="12" text-anchor="end" fill="#64748b" font-size="10">
      ${esc(shortDate(pts[0].t))} → ${esc(shortDate(pts[pts.length - 1].t))}
    </text>
  </svg>`;
}

function lineChart(values, opts = {}) {
  const nums = (values || []).map(Number).filter((n) => Number.isFinite(n));
  const h = opts.height || 220;
  if (nums.length < 2) return chartEmpty(h);
  const w = 760;
  const pad = { top: 18, right: 14, bottom: 26, left: 46 };
  const compare = (opts.compare || []).map(Number).filter((n) => Number.isFinite(n));
  const all = compare.length ? nums.concat(compare) : nums;
  const min = opts.includeZero === false ? Math.min(...all) : Math.min(...all, 0);
  const max = opts.includeZero === false ? Math.max(...all) : Math.max(...all, 0);
  const span = max - min || 1;
  const rawPts = Array.isArray(opts.points) ? opts.points : null;
  const idxs = rawPts && rawPts.length === nums.length
    ? rawPts.map((p) => Number(p.idx))
    : null;
  const hasIdx = idxs && idxs.every((v) => Number.isFinite(v)) && idxs[idxs.length - 1] !== idxs[0];
  const i0 = hasIdx ? idxs[0] : 0;
  const i1 = hasIdx ? idxs[idxs.length - 1] : nums.length - 1;
  const x = (i) => pad.left + (i / (nums.length - 1)) * (w - pad.left - pad.right);
  const xIdx = (v) => pad.left + ((v - i0) / (i1 - i0)) * (w - pad.left - pad.right);
  const y = (v) => h - pad.bottom - ((v - min) / span) * (h - pad.top - pad.bottom);
  const id = "lc" + (++_chartSeq);
  const posX = (i) => (hasIdx ? xIdx(idxs[i]) : x(i));
  const pts = nums.map((v, i) => `${posX(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `M ${posX(0).toFixed(1)},${(h - pad.bottom).toFixed(1)} L ` +
    nums.map((v, i) => `${posX(i).toFixed(1)},${y(v).toFixed(1)}`).join(" L ") +
    ` L ${posX(nums.length - 1).toFixed(1)},${(h - pad.bottom).toFixed(1)} Z`;
  const zeroY = y(0);
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((r) => {
    const gy = pad.top + r * (h - pad.top - pad.bottom);
    const val = max - r * span;
    return `<line x1="${pad.left}" y1="${gy.toFixed(1)}" x2="${w - pad.right}" y2="${gy.toFixed(1)}"
              stroke="rgba(120,156,210,.10)" stroke-dasharray="3 5"/>
            <text x="${pad.left - 8}" y="${(gy + 4).toFixed(1)}" text-anchor="end"
              fill="#64748b" font-size="10">${fmt(val, 1)}</text>`;
  }).join("");
  const up = nums[nums.length - 1] >= 0;
  const color = opts.color || (up ? "#34d399" : "#fb7185");
  let compareSvg = "";
  if (compare.length >= 2) {
    const cpts = compare.map((v, i) => {
      const cx = pad.left + (i / (compare.length - 1)) * (w - pad.left - pad.right);
      return `${cx.toFixed(1)},${y(v).toFixed(1)}`;
    }).join(" ");
    compareSvg = `<polyline points="${cpts}" fill="none" stroke="#94a3b8" stroke-width="1.6"
        stroke-dasharray="5 4" stroke-linejoin="round" opacity=".85"/>`;
  }

  // İşlem işaretleri: idx → en yakın örnek değeri
  let markerSvg = "";
  const mk = Array.isArray(opts.markers) ? opts.markers : [];
  if (mk.length && hasIdx) {
    const nearest = (target) => {
      let best = 0, bestD = Infinity;
      for (let i = 0; i < idxs.length; i++) {
        const d = Math.abs(idxs[i] - target);
        if (d < bestD) { bestD = d; best = i; }
      }
      return best;
    };
    const showNo = mk.length <= 80;
    markerSvg = mk.map((m) => {
      const pos = nearest(Number(m.idx));
      const mx = posX(pos);
      const my = y(nums[pos]);
      const isBuy = m.side === "buy";
      const pnl = Number(m.pnl_pct || 0);
      const fill = isBuy ? "#34d399" : (pnl >= 0 ? "#34d399" : "#fb7185");
      const d = isBuy
        ? `${mx.toFixed(1)},${(my - 4).toFixed(1)} ${(mx - 3.5).toFixed(1)},${(my + 3).toFixed(1)} ${(mx + 3.5).toFixed(1)},${(my + 3).toFixed(1)}`
        : `${mx.toFixed(1)},${(my + 4).toFixed(1)} ${(mx - 3.5).toFixed(1)},${(my - 3).toFixed(1)} ${(mx + 3.5).toFixed(1)},${(my - 3).toFixed(1)}`;
      const title = `#${m.no} ${isBuy ? "AL" : "SAT"} · ${fmtTime(m.time)} · K/Z ${pnl >= 0 ? "+" : ""}${fmt(pnl, 2)}%`;
      return `<g><title>${esc(title)}</title>
        <polygon points="${d}" fill="${fill}" stroke="#060b14" stroke-width=".8"/>
        ${showNo && m.side === "buy" ? `<text x="${mx.toFixed(1)}" y="${(my - 7).toFixed(1)}" text-anchor="middle" fill="#6ee7b7" font-size="8">${m.no}</text>` : ""}
      </g>`;
    }).join("");
  }

  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img">
    <defs>
      <linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${color}" stop-opacity=".34"/>
        <stop offset="1" stop-color="${color}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${gridLines}
    <line x1="${pad.left}" y1="${zeroY.toFixed(1)}" x2="${w - pad.right}" y2="${zeroY.toFixed(1)}"
      stroke="rgba(148,163,184,.35)" stroke-dasharray="5 5"/>
    <path d="${area}" fill="url(#${id})"/>
    ${compareSvg}
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.2"
      stroke-linejoin="round" stroke-linecap="round"/>
    ${markerSvg}
    <circle cx="${posX(nums.length - 1).toFixed(1)}" cy="${y(nums[nums.length - 1]).toFixed(1)}" r="3.6"
      fill="${color}" stroke="#060b14" stroke-width="2"/>
    <text x="${pad.left}" y="12" fill="#7f90aa" font-size="10">${esc(opts.caption || "")}</text>
  </svg>`;
}

function donutChart(segments, opts = {}) {
  const size = opts.size || 150;
  const stroke = opts.stroke || 16;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const total = segments.reduce((sum, s) => sum + Math.max(0, Number(s.value) || 0), 0);
  let offset = 0;
  const rings = total > 0 ? segments.map((s) => {
    const frac = Math.max(0, Number(s.value) || 0) / total;
    const dash = frac * circ;
    const ring = `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none"
      stroke="${s.color}" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${dash.toFixed(2)} ${(circ - dash).toFixed(2)}"
      stroke-dashoffset="${(-offset).toFixed(2)}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>`;
    offset += dash;
    return ring;
  }).join("") : `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none"
      stroke="rgba(120,156,210,.16)" stroke-width="${stroke}"/>`;
  return `<div class="donut-wrap">
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img">
      ${rings}
      <text x="50%" y="47%" text-anchor="middle" fill="#e9f0fb" font-size="22" font-weight="700">${esc(opts.center ?? "")}</text>
      <text x="50%" y="63%" text-anchor="middle" fill="#7f90aa" font-size="10">${esc(opts.sub ?? "")}</text>
    </svg>
    <div class="donut-legend">
      ${segments.map((s) => `<div class="legend-row">
        <span class="legend-dot" style="background:${s.color}"></span>
        <span>${esc(s.label)}</span><b>${esc(s.display ?? s.value)}</b>
      </div>`).join("")}
    </div>
  </div>`;
}

function barChart(items, opts = {}) {
  const data = (items || []).filter((i) => Number.isFinite(Number(i.value)));
  const h = opts.height || 180;
  if (!data.length) return chartEmpty(h);
  const w = 760;
  const pad = { top: 14, right: 10, bottom: 30, left: 40 };
  const vals = data.map((i) => Number(i.value));
  const min = Math.min(...vals, 0);
  const max = Math.max(...vals, 0);
  const span = max - min || 1;
  const slot = (w - pad.left - pad.right) / data.length;
  const barW = Math.max(4, Math.min(34, slot * 0.58));
  const zeroY = h - pad.bottom - ((0 - min) / span) * (h - pad.top - pad.bottom);
  const bars = data.map((item, i) => {
    const v = Number(item.value);
    const cx = pad.left + slot * i + slot / 2;
    const vy = h - pad.bottom - ((v - min) / span) * (h - pad.top - pad.bottom);
    const top = Math.min(vy, zeroY);
    const height = Math.max(2, Math.abs(zeroY - vy));
    const color = v >= 0 ? "#34d399" : "#fb7185";
    return `<rect x="${(cx - barW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}"
        height="${height.toFixed(1)}" rx="3" fill="${color}" opacity=".85">
        <title>${esc(item.label)}: ${fmt(v, 2)}</title>
      </rect>
      <text x="${cx.toFixed(1)}" y="${(h - 10).toFixed(1)}" text-anchor="middle" fill="#64748b" font-size="9.5">${esc(item.label)}</text>`;
  }).join("");
  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img">
    <line x1="${pad.left}" y1="${zeroY.toFixed(1)}" x2="${w - pad.right}" y2="${zeroY.toFixed(1)}"
      stroke="rgba(148,163,184,.28)"/>
    <text x="${pad.left - 8}" y="${(zeroY + 3).toFixed(1)}" text-anchor="end" fill="#64748b" font-size="10">0</text>
    ${bars}
  </svg>`;
}

function sparkline(values, opts = {}) {
  const nums = (values || []).map(Number).filter((n) => Number.isFinite(n));
  if (nums.length < 2) return "";
  const w = opts.width || 120, h = opts.height || 34, pad = 3;
  const min = Math.min(...nums), max = Math.max(...nums);
  const span = max - min || 1;
  const pts = nums.map((v, i) => {
    const x = pad + (i / (nums.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const up = nums[nums.length - 1] >= 0;
  const color = opts.color || (up ? "#34d399" : "#fb7185");
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8"
      stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

/* ------------------------------------------------------------------ */
/* Canlı işlem anahtarı                                                */
/* ------------------------------------------------------------------ */
function renderLiveToggle() {
  const btn = $("#live-toggle");
  if (!btn) return;
  btn.classList.toggle("on", !!state.liveUnlocked);
  btn.classList.toggle("server-off", !state.liveEnabled);
  const label = $("#live-state");
  if (label) label.textContent = state.liveUnlocked ? "Açık" : "Kapalı";
  btn.title = state.liveUnlocked
    ? "Canlı işlem açık — kapatmak için tıkla"
    : "Canlı işlem kapalı — açmak için tıkla";
}

async function toggleLiveTrading() {
  const next = !state.liveUnlocked;
  if (next && !state.liveEnabled) {
    toast("Sunucuda canlı işlem kapalı (.env → LIVE_TRADING_ENABLED=true)", true);
    return;
  }
  const ok = await confirmDialog(
    next ? "Canlı işlemi aç" : "Canlı işlemi kapat",
    next
      ? "Canlı işlem açılacak. Canlı moda aldığın botlar gerçek emir gönderebilir."
      : "Canlı işlem kapatılacak. Çalışan canlı botlar güvenli şekilde durdurulacak.",
    next ? "Aç" : "Kapat",
    !next,
  );
  if (!ok) return;
  try {
    const res = await api("/settings/live-toggle", { method: "POST", body: { enabled: next } });
    state.liveUnlocked = !!res.enabled;
    renderLiveToggle();
    toast(next ? "Canlı işlem açıldı" : "Canlı işlem kapatıldı", next);
    if (["dashboard", "bots", "settings"].includes(state.view)) route();
  } catch (err) { toast(err.message, true); }
}
$("#live-toggle").addEventListener("click", toggleLiveTrading);
const _refreshBtn = $("#topbar-refresh");
if (_refreshBtn) _refreshBtn.addEventListener("click", () => { route(); toast("Güncellendi"); });

async function api(path, options = {}) {
  const opts = { method: "GET", headers: {}, credentials: "same-origin", ...options };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
    opts.headers["Content-Type"] = "application/json";
  }
  if (opts.method !== "GET" && state.csrf) opts.headers["X-CSRF-Token"] = state.csrf;
  const res = await fetch("/api" + path, opts);
  if (res.status === 401) { showLogin(); throw new Error("Oturum gerekli"); }
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!res.ok) {
    const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText;
    throw new Error(detail);
  }
  return data;
}

/* ------------------------------------------------------------------ */
/* Auth                                                                */
/* ------------------------------------------------------------------ */
function showLogin() {
  state.booted = false;
  $("#login-overlay").classList.remove("hidden");
  $("#app").classList.add("hidden");
}
function showApp() {
  $("#login-overlay").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#current-user").textContent = state.user || "";
  const avatar = $("#user-avatar");
  if (avatar) avatar.textContent = (state.user || "A").charAt(0).toUpperCase();
  startClock();
}
function startClock() {
  const el = $("#clock");
  if (!el) return;
  const dateEl = $("#clock-date");
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if (dateEl) dateEl.textContent = now.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", weekday: "short" });
  };
  tick();
  clearInterval(el._t);
  el._t = setInterval(tick, 1000);
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: { username: $("#login-user").value.trim(), password: $("#login-pass").value },
    });
    state.user = data.user;
    state.csrf = data.csrf;
    if (data.must_change_password) {
      toast("Lütfen şifrenizi değiştirin.", true);
      location.hash = "#settings";
    }
    await boot();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});

$("#logout").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch (e) {}
  state.user = null; state.csrf = null; showLogin();
});

async function boot() {
  if (!state.catalog) state.catalog = await api("/strategies/indicators");
  await loadCatalog();
  try {
    const cfg = await api("/settings");
    state.liveEnabled = !!cfg.app.live_enabled;
    state.liveUnlocked = !!cfg.app.live_unlocked;
  } catch (e) { /* ayarlar okunamazsa varsayılan kapalı */ }
  renderLiveToggle();
  route();
}

async function loadCatalog() {
  try { state.extra = await api("/strategies/builtin"); } catch (e) { state.extra = []; }
  try { state.custom = await api("/strategies/custom"); } catch (e) { state.custom = []; }
  state.indicators = state.catalog || [];
}

/* ------------------------------------------------------------------ */
/* Routing                                                             */
/* ------------------------------------------------------------------ */
/* KURAL: aynı anda YALNIZCA BİR sayfa render edilir. Gezinmeler
   serileştirilir; render sürerken yeni bir gezinme gelirse mevcut render
   bitirilir, ardından EN SON hedef sayfa çizilir. Böylece iki render aynı
   anda #content'e yazamaz — eski sayfa takılı kalamaz, yeni sayfa ezilemez.
   Ayrıca her gezinmede eski içerik SENKRON olarak temizlenir. */

const VIEW_TITLES = {
  dashboard: "Dashboard", bots: "Botlar", strategies: "Stratejiler", scan: "Tarama",
  lists: "Coin Listeleri", analysis: "Analiz", trades: "İşlem Geçmişi",
  settings: "Ayarlar", system: "Sistem",
};
const VIEW_SUBS = {
  dashboard: "Genel bakış ve performans",
  bots: "Bot oluştur, başlat ve izle",
  strategies: "Görsel kurallarla strateji tasarla",
  scan: "Piyasayı seçili stratejilerle tara",
  lists: "Coin listesi oluştur, düzenle ve yeniden kullan",
  analysis: "İndikatör ve piyasa analizi",
  trades: "İşlem geçmişi ve grafikler",
  settings: "Canlı işlem, coin listesi ve güvenlik",
  system: "Kaynak kullanımı ve sürüm",
};

function stopTimers() {
  clearInterval(state.refreshTimer);
  clearInterval(state.jobTimer);
  clearInterval(state.jobMonitorTimer);
  clearInterval(state.liveTimer);
  state.refreshTimer = state.jobTimer = state.jobMonitorTimer = state.liveTimer = null;
}

window.addEventListener("hashchange", route);

async function route() {
  state.routeSeq += 1;
  if (state.routeBusy) {
    // Render sürüyor: son hedefi sonra çizeceğiz (istek birleştirilir).
    state.routeQueued = true;
    return;
  }
  state.routeBusy = true;
  try {
    let laps = 0;
    do {
      state.routeQueued = false;
      const seq = state.routeSeq;
      try {
        await renderRoute();
      } catch (err) {
        console.error("Sayfa çizilemedi:", err);
      }
      // Render sırasında gezinme değiştiyse bir kez daha (en son hedefle) çiz.
      if (seq !== state.routeSeq) state.routeQueued = true;
      laps += 1;
    } while (state.routeQueued && laps < 8);
  } finally {
    state.routeBusy = false;
    // Son anda gelen bir gezinme kaçmasın.
    if (state.routeQueued) {
      state.routeQueued = false;
      setTimeout(route, 0);
    }
  }
}

async function renderRoute() {
  stopTimers();
  const hash = (location.hash || "#dashboard").slice(1);
  const view = hash.split("/")[0] || "dashboard";
  state.view = view;

  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  const title = VIEW_TITLES[view] || view;
  const titleEl = $("#view-title");
  if (titleEl) titleEl.textContent = title;
  const crumb = $("#view-crumb");
  if (crumb) crumb.textContent = title;
  const sub = $("#view-sub");
  if (sub) sub.textContent = VIEW_SUBS[view] || "";

  refreshTopbar(); // kritik değil: beklenmez

  const content = $("#content");
  if (!content) return;

  const initial = !state.booted;
  const sameView = state.renderedView === view;
  content.classList.toggle("is-refresh", sameView || initial);
  content.dataset.view = view; // render fonksiyonları buna bakıyor
  if (!sameView && !initial) {
    // Eski sayfa ekranda kalmasın: içeriği hemen boşalt.
    delete content.dataset.sig;
    content.innerHTML = `<div class="muted">Yükleniyor…</div>`;
  }

  const render = {
    dashboard: renderDashboard, bots: renderBots, strategies: renderStrategies,
    scan: renderScan, lists: renderLists, analysis: renderAnalysis, trades: renderTrades,
    settings: renderSettings, system: renderSystem,
  }[view] || renderDashboard;

  try {
    await render(content);
  } catch (err) {
    console.error("Sayfa hatası:", view, err);
    content.innerHTML = `<div class="card"><h3>Hata</h3>
      <div class="error">${esc(err && err.message ? err.message : String(err))}</div></div>`;
  } finally {
    state.renderedView = view;
    content.dataset.view = view;
    content.classList.remove("is-refresh");
  }

  if (initial) {
    state.booted = true;
    showApp();
  }
}

/* ---------- Üst çubuk özeti ---------- */
async function refreshTopbar() {
  try {
    const [bots, summary] = await Promise.all([api("/bots"), api("/summary")]);
    state.bots = bots;
    const running = bots.filter((b) => b.status === "running").length;
    const open = bots.filter((b) => b.state && b.state.position).length;
    const pnl = bots.reduce((sum, b) => sum + botTotalPnl(b), 0);
    const unreal = bots.reduce((sum, b) => sum + (Number(b.state && b.state.unrealized_pnl) || 0), 0);
    const total = summary.total || {};
    const wins = Number(total.wins || 0), losses = Number(total.losses || 0);
    const winRate = wins + losses ? `${Math.round((wins / (wins + losses)) * 100)}%` : "—";
    const set = (id, value, cls) => {
      const el = $(id);
      if (!el) return;
      el.textContent = value;
      el.className = cls || "";
    };
    set("#tb-bots", `${running}/${bots.length}`);
    set("#tb-pos", String(open));
    set("#tb-win", winRate);
    set("#tb-pnl", signedMoney(pnl), pnlClass(pnl));
    const pnlEl = $("#tb-pnl");
    if (pnlEl) pnlEl.title = `Toplam K/Z = gerçekleşen + anlık açık K/Z (anlık: ${signedMoney(unreal)})`;
  } catch (err) { /* üst çubuk özeti kritik değil */ }
}

/* ------------------------------------------------------------------ */
/* Dashboard                                                           */
/* ------------------------------------------------------------------ */
async function renderDashboard(root) {
  const [bots, events, summary, stats, jobs, scans] = await Promise.all([
    api("/bots"), api("/events?limit=7"), api("/summary"), api("/stats"),
    api("/analysis/jobs/active"), api("/analysis/scans?limit=5"),
  ]);
  state.bots = bots;
  state.stats = stats;
  renderLiveToggle();

  // Veri değişmediyse DOM'a dokunma: yenilemede öğeler kaybolmaz/titremez.
  const signature = JSON.stringify({
    bots: bots.map((b) => [b.id, b.status, b.mode, b.auto_restart, b.state && b.state.cash,
      b.state && b.state.trade_count, b.state && b.state.last_update,
      b.state && b.state.total_realized_pnl, !!(b.state && b.state.position),
      b.state && b.state.unrealized_pnl]),
    events: events.map((e) => e.id),
    totals: summary.total || {},
    stats: stats.totals || {},
    jobs: (jobs.active || []).map((j) => [j.id, j.status, j.progress, j.message]),
    scans: (scans || []).map((s) => [s.id, s.finished_at]),
  });
  if (root.dataset.sig === signature && root.dataset.view === "dashboard") {
    scheduleDashboardRefresh();
    refreshJobMonitor();
    return;
  }
  root.dataset.sig = signature;
  const running = bots.filter((b) => b.status === "running").length;
  const openPositions = bots.filter((b) => b.state && b.state.position).length;
  const total = summary.total || {};
  const wins = Number(total.wins || 0), losses = Number(total.losses || 0);
  const winRate = wins + losses ? (wins / (wins + losses) * 100).toFixed(1) : null;
  const hasLive = bots.some((b) => b.mode === "live");
  const totals = stats.totals || {};
  const eqValues = (stats.equity || []).map((p) => p.value);
  const eqLast = eqValues.length ? eqValues[eqValues.length - 1] : null;
  const daily = (stats.daily || []).slice(-14).map((d) => ({ label: (d.date || "").slice(5), value: d.pnl }));
  const seriesMap = {};
  (stats.by_bot || []).forEach((b) => { if (b.bot_id) seriesMap[b.bot_id] = b.series; });
  const modes = stats.modes || { paper: 0, live: 0 };
  const totalPnl = bots.reduce((sum, b) => sum + botTotalPnl(b), 0);
  const unrealizedPnl = bots.reduce((sum, b) => sum + (Number(b.state && b.state.unrealized_pnl) || 0), 0);

  root.innerHTML = `
    <div class="card hero-card">
      <div class="hero-glow" aria-hidden="true"></div>
      <div class="hero-body">
        <div>
          <span class="eyebrow">${hasLive ? "Canlı portföy" : "Test ortamı"}</span>
          <h1 class="hero-title">${running ? "Sistem aktif" : "Sistem hazır"}<span class="hero-dot ${running ? "on" : ""}"></span></h1>
          <p class="muted hero-sub">${running} bot çalışıyor · ${openPositions} açık pozisyon · ${bots.length} kayıtlı bot · ${hasLive ? "canlı bot var" : "canlı bot yok"} · ${state.liveUnlocked ? "canlı işlem açık" : "canlı işlem kapalı"}</p>
        </div>
        <div class="row">
          <button class="primary" onclick="location.hash='#bots'">Botları Yönet</button>
          <button class="ghost" onclick="quickBot()">Hızlı Bot</button>
          <button class="ghost" onclick="location.hash='#strategies'">Strateji Oluştur</button>
        </div>
      </div>
    </div>

    <div class="grid c4 mt">
      ${kpi("Çalışan bot", running, `${bots.length} kayıtlı`, "M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6v-9h-6v9Zm0-16v5h6V4h-6Z")}
      ${kpi("Açık pozisyon", openPositions, openPositions ? "takip ediliyor" : "pozisyon yok", "M12 2 2 7l10 5 10-5-10-5Zm0 7.2L4.4 5.4 12 9.1l7.6-3.7L12 9.2Z")}
      <div class="card kpi">
        <div class="kpi-top">
          <h3>Toplam K/Z</h3>
          <span class="kpi-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10a2 2 0 0 1 2 2v16l-3.5-2-3.5 2-3.5-2L5 21V5a2 2 0 0 1 2-2Z"/></svg></span>
        </div>
        <div class="stat ${pnlClass(totalPnl)}" data-live="dash-total">${signedMoney(totalPnl)}</div>
        <div class="muted"><span data-live="dash-unreal" class="${pnlClass(unrealizedPnl)}">anlık ${signedMoney(unrealizedPnl)}</span> · ${totals.trades || 0} kapanan işlem</div>
      </div>
      ${kpi("Kazanma oranı", winRate === null ? "—" : `${winRate}%`, winRate === null ? "veri bekleniyor" : `${wins} kârlı · ${losses} zararlı`, "M4 20h16v2H4v-2Zm1-3 4-6 3 3 5-7 2 1.5-6.4 9L9.6 14 6.6 18.5 5 17Z")}
    </div>

    <div id="active-jobs">${jobMonitorHtml(jobs)}</div>
    ${scanResultsHtml(scans)}

    <div class="dash-grid mt">
      <div class="card chart-card">
        <div class="row between">
          <div>
            <h3>Kümülatif K/Z</h3>
            <p class="muted small">Kapanan işlemlerin bileşik getirisi</p>
          </div>
          <span class="chart-big ${eqLast === null ? "" : eqLast >= 0 ? "pos" : "neg"}">
            ${eqLast === null ? "—" : `${eqLast >= 0 ? "+" : ""}${fmt(eqLast, 2)}%`}
          </span>
        </div>
        ${lineChart(eqValues, { height: 230, caption: `${eqValues.length} kapanan işlem` })}
      </div>
      <div class="card chart-card">
        <h3>Kazanma oranı</h3>
        <p class="muted small">Kapanan işlemlerin dağılımı</p>
        ${donutChart([
          { label: "Kârlı", value: wins, color: "#34d399", display: wins },
          { label: "Zararlı", value: losses, color: "#fb7185", display: losses },
        ], { center: winRate === null ? "—" : `${winRate}%`, sub: "kazanma oranı" })}
      </div>
    </div>

    <div class="dash-grid2 mt">
      <div class="card chart-card">
        <div class="row between"><h3>Günlük K/Z</h3><span class="tag gray">son 14 gün</span></div>
        ${barChart(daily, { height: 180 })}
      </div>
      <div class="card chart-card">
        <h3>Mod dağılımı</h3>
        ${donutChart([
          { label: "Test", value: modes.paper || 0, color: "#38bdf8", display: modes.paper || 0 },
          { label: "Canlı", value: modes.live || 0, color: "#fbbf24", display: modes.live || 0 },
        ], { center: (modes.paper || 0) + (modes.live || 0), sub: "kapanan işlem", size: 138 })}
      </div>
    </div>

    <div class="split mt">
      <div class="card">
        <div class="row between"><h3>Botlar</h3><button class="ghost small" onclick="location.hash='#bots'">Tümünü gör</button></div>
        ${bots.length ? bots.slice(0, 4).map((b) => botRow(b, seriesMap)).join("") : '<div class="empty-state">Henüz bot yok.<br><span class="muted">Botlar sayfasından ilk botunuzu oluşturun.</span></div>'}
      </div>
      <div class="card">
        <div class="row between"><h3>Son olaylar</h3><span class="tag gray">canlı</span></div>
        <div class="timeline">
          ${events.length ? events.map((e) => `<div class="timeline-item level-${esc(e.level || "info")}"><span class="timeline-dot"></span><div><div class="timeline-msg">${esc(e.message)}</div><div class="timeline-time">${esc(fmtIso(e.created_at))}</div></div></div>`).join("") : '<div class="empty-state">Olay kaydı yok.</div>'}
        </div>
      </div>
    </div>`;
  scheduleDashboardRefresh();
  startJobMonitor();
  bindScanResults();
}

function scheduleDashboardRefresh() {
  if (state.view !== "dashboard") return; // eski sayfa yeni sayfanın timer'ını ezmesin
  clearInterval(state.refreshTimer);
  clearInterval(state.liveTimer);
  state.refreshTimer = setInterval(() => {
    if (state.routeBusy || state.view !== "dashboard") return;
    renderDashboard($("#content")).catch(() => {});
  }, 15000);
  state.liveTimer = setInterval(() => {
    if (state.routeBusy || state.view !== "dashboard") return;
    refreshLivePnl();
  }, 5000);
}

/* ------------------------------------------------------------------ */
/* Aktif işler (tarama / backtest / analiz)                            */
/* ------------------------------------------------------------------ */
function fmtDuration(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  if (s < 60) return `${s} sn`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return `${m} dk ${r} sn`;
  const h = Math.floor(m / 60);
  return `${h} sa ${m % 60} dk`;
}

function jobMonitorHtml(data) {
  const active = (data && data.active) || [];
  const recent = (data && data.recent) || [];
  const recentShown = recent.filter((j) => j.status !== "done" || j.finished_at).slice(0, 3);

  if (!active.length && !recentShown.length) {
    return `<div class="card job-monitor empty">
      <div class="job-monitor-head">
        <div class="row" style="gap:10px"><span class="job-live-dot idle"></span><h3 style="margin:0">Aktif taramalar</h3></div>
        <span class="tag gray">boşta</span>
      </div>
      <p class="muted small" style="margin:8px 0 0">Şu anda çalışan tarama, backtest veya analiz yok. <a href="#scan">Tarama başlat</a></p>
    </div>`;
  }

  const row = (job, live) => {
    const pct = Math.max(0, Math.min(100, Number(job.progress) || 0));
    const isDone = job.status === "done";
    const isError = job.status === "error";
    const isCancelled = job.status === "cancelled";
    const cls = isError ? "neg" : isCancelled ? "muted" : isDone ? "pos" : "run";
    const statusText = job.status === "queued" ? "Sırada"
      : job.status === "running" ? `${pct}%`
      : isDone ? "Bitti" : isError ? "Hata" : isCancelled ? "İptal" : job.status;
    const detail = [];
    if (job.period) detail.push(job.period);
    if (job.summary && job.summary.coins) detail.push(`${job.summary.coins} coin`);
    else if (job.summary && job.summary.scope) detail.push(job.summary.scope);
    if (job.summary && job.summary.coin) detail.push(job.summary.coin);
    if (job.summary && job.summary.strategies) detail.push(`${job.summary.strategies} strateji`);
    return `<div class="job-row ${live ? "live" : ""} ${cls}">
      <div class="job-row-main">
        <div class="job-row-title">
          <span class="job-kind">${esc(job.label)}</span>
          ${detail.length ? `<span class="muted small">${esc(detail.join(" · "))}</span>` : ""}
          ${live ? `<span class="job-timer mono">${fmtDuration(job.elapsed)}</span>` : ""}
        </div>
        <div class="job-bar"><span style="width:${isDone ? 100 : pct}%"></span></div>
        <div class="job-row-sub">
          <span class="job-state ${cls}">${esc(statusText)}</span>
          <span class="muted small">${esc(job.message || "")}</span>
        </div>
      </div>
      ${live ? `<button class="ghost small job-cancel" data-cancel="${esc(job.id)}" type="button">İptal</button>` : ""}
    </div>`;
  };

  return `<div class="card job-monitor mt">
    <div class="job-monitor-head">
      <div class="row" style="gap:10px">
        <span class="job-live-dot ${active.length ? "on" : "idle"}"></span>
        <h3 style="margin:0">Aktif taramalar</h3>
        ${active.length ? `<span class="tag green">${active.length} çalışıyor</span>` : `<span class="tag gray">boşta</span>`}
      </div>
      <button class="ghost small" id="job-refresh" type="button">Yenile</button>
    </div>
    <div class="job-list">
      ${active.map((j) => row(j, true)).join("")}
      ${recentShown.length ? `<div class="job-recent-label">Son işler</div>` + recentShown.map((j) => row(j, false)).join("") : ""}
    </div>
  </div>`;
}

function bindJobMonitor() {
  $$("#active-jobs [data-cancel]").forEach((btn) => btn.addEventListener("click", async () => {
    const ok = await confirmDialog("İşi iptal et", "Çalışan iş durdurulacak. Devam edilsin mi?", "İptal et", true);
    if (!ok) return;
    try {
      await api(`/analysis/jobs/${btn.dataset.cancel}/cancel`, { method: "POST" });
      toast("İş iptal edildi");
      refreshJobMonitor();
    } catch (e) { toast(e.message, true); }
  }));
  const refresh = $("#job-refresh");
  if (refresh) refresh.addEventListener("click", () => refreshJobMonitor(true));
}

async function refreshJobMonitor(showToast = false) {
  const host = $("#active-jobs");
  if (!host || state.routeBusy || state.view !== "dashboard") return;
  try {
    const data = await api("/analysis/jobs/active");
    const signature = JSON.stringify(data.active.map((j) => [j.id, j.status, j.progress, j.message]))
      + JSON.stringify((data.recent || []).slice(0, 3).map((j) => [j.id, j.status]));
    if (signature !== host.dataset.sig || showToast) {
      host.dataset.sig = signature;
      host.innerHTML = jobMonitorHtml(data);
      bindJobMonitor();
      if (showToast) toast("Aktif işler güncellendi");
    }
  } catch (e) { /* sessiz */ }
}

function startJobMonitor() {  bindJobMonitor();
  clearInterval(state.jobMonitorTimer);
  state.jobMonitorTimer = setInterval(() => refreshJobMonitor(), 4000);
}

/* ------------------------------------------------------------------ */
/* Tarama sonuçları                                                    */
/* ------------------------------------------------------------------ */
function scanResultsHtml(scans) {
  const list = scans || [];
  if (!list.length) {
    return `<div class="card scan-results empty mt">
      <div class="row between">
        <div class="row" style="gap:10px"><h3 style="margin:0">Tarama sonuçları</h3></div>
        <button class="ghost small" onclick="location.hash='#scan'" type="button">Tarama başlat</button>
      </div>
      <p class="muted small" style="margin:8px 0 0">Henüz tamamlanmış tarama yok. Tarama sayfasından strateji seçip piyasayı tarayabilirsin.</p>
    </div>`;
  }
  const latest = list[0];
  const options = list.map((s, i) => {
    const when = fmtIso(s.finished_at || s.created_at);
    return `<option value="${esc(s.id)}" ${i === 0 ? "selected" : ""}>${esc(s.period || "")} · ${esc(when)} · ${s.buy_total} al / ${s.sell_total} sat</option>`;
  }).join("");

  const strategyNames = (latest.strategies || []).map((s) => s.name);
  const coinRisk = (c) => c.buy_count && c.sell_count ? "both" : c.buy_count ? "buy" : "sell";
  const coinList = latest.coins || [];
  const onlyBuyCount = coinList.filter((c) => c.buy_count && !c.sell_count).length;
  const onlySellCount = coinList.filter((c) => c.sell_count && !c.buy_count).length;
  const bothCount = coinList.filter((c) => c.buy_count && c.sell_count).length;

  const badges = (names, side) => (names || []).length
    ? names.map((n) => `<span class="sig-badge ${side}">${esc(n)}</span>`).join("")
    : "";

  const signalCell = (c) => {
    const buy = badges(c.buy, "buy");
    const sell = badges(c.sell, "sell");
    if (!buy && !sell) return `<span class="muted small">—</span>`;
    if (buy && sell) {
      return `<div class="sig-split">
        <div class="sig-group"><span class="sig-label buy">AL</span>${buy}</div>
        <div class="sig-group"><span class="sig-label sell">SAT</span>${sell}</div>
      </div>`;
    }
    return `<div class="sig-strategies">${buy}${sell}</div>`;
  };

  const rows = coinList.map((c) => `
    <tr class="sig-row" data-side="${coinRisk(c)}" data-coin="${esc(c.coin)}" data-strength="${c.buy_count + c.sell_count}">
      <td class="sig-coin">
        <span class="sig-coin-name">${esc(c.coin)}</span>
        ${c.buy_count && c.sell_count ? '<span class="sig-tag">çelişkili</span>' : ""}
      </td>
      <td>
        <div class="sig-side">
          ${c.buy_count ? `<span class="sig-count buy">${c.buy_count} AL</span>` : ""}
          ${c.sell_count ? `<span class="sig-count sell">${c.sell_count} SAT</span>` : ""}
        </div>
      </td>
      <td><div class="sig-strategies">${signalCell(c)}</div></td>
      <td class="sig-strength">
        <span class="strength-bar"><span style="width:${Math.min(100, (c.buy_count + c.sell_count) / Math.max(1, strategyNames.length) * 100)}%"></span></span>
        <span class="small muted">${c.buy_count + c.sell_count}/${strategyNames.length}</span>
      </td>
    </tr>`).join("");

  const strategyRows = (latest.strategies || []).map((s) => {
    const buys = (s.buy || []).map((c) => `<span class="scan-chip buy">${esc(c)}</span>`).join("");
    const sells = (s.sell || []).map((c) => `<span class="scan-chip sell">${esc(c)}</span>`).join("");
    if (!s.buy_count && !s.sell_count) return "";
    return `<div class="strat-detail">
      <div class="strat-detail-head">
        <strong>${esc(s.name)}</strong>
        ${s.buy_count ? `<span class="tag green">${s.buy_count} AL</span>` : ""}
        ${s.sell_count ? `<span class="tag red">${s.sell_count} SAT</span>` : ""}
      </div>
      ${buys ? `<div class="strat-detail-line"><span class="rule-badge buy">AL</span><div class="scan-chips">${buys}</div></div>` : ""}
      ${sells ? `<div class="strat-detail-line"><span class="rule-badge sell">SAT</span><div class="scan-chips">${sells}</div></div>` : ""}
    </div>`;
  }).join("");

  return `<div class="card scan-results mt" id="scan-results" data-id="${esc(latest.id)}">
    <div class="row between scan-head">
      <div>
        <div class="row" style="gap:10px">
          <h3 style="margin:0">Tarama sonuçları</h3>
          <span class="tag gray">${esc(latest.period || "")}</span>
          <span class="tag gray">${latest.scanned} coin</span>
          ${latest.status === "error" ? `<span class="tag red">hata</span>` : `<span class="tag green">tamamlandı</span>`}
        </div>
        <p class="muted small" style="margin:4px 0 0">
          ${esc(fmtIso(latest.finished_at || latest.created_at))}
          ${latest.error ? ` · <span class="error-inline">${esc(latest.error)}</span>` : ""}
        </p>
      </div>
      <div class="row">
        ${list.length > 1 ? `<select id="scan-picker" class="scan-picker">${options}</select>` : ""}
        <button class="ghost small" onclick="location.hash='#scan'" type="button">Yeni tarama</button>
      </div>
    </div>

    <div class="scan-kpis">
      <div class="scan-kpi buy"><span>AL sinyali</span><b>${latest.buy_total}</b><small>${latest.buy_coins.length} farklı coin</small></div>
      <div class="scan-kpi sell"><span>SAT sinyali</span><b>${latest.sell_total}</b><small>${latest.sell_coins.length} farklı coin</small></div>
      <div class="scan-kpi"><span>Taranan</span><b>${latest.scanned}</b><small>${(latest.strategies || []).length} strateji</small></div>
    </div>

    <div class="sig-toolbar">
      <div class="sig-filters" id="sig-filters">
        <button class="chip active" data-filter="all" type="button">Tümü <b>${coinList.length}</b></button>
        <button class="chip" data-filter="buy" type="button">Yalnız AL <b>${onlyBuyCount}</b></button>
        <button class="chip" data-filter="sell" type="button">Yalnız SAT <b>${onlySellCount}</b></button>
        <button class="chip" data-filter="both" type="button">Çelişkili <b>${bothCount}</b></button>
      </div>
      <input id="sig-search" class="sig-search" placeholder="Coin ara… (örn. BTC)">
    </div>

    ${rows ? `<div class="result-scroll sig-table-wrap">
      <table class="result-table sig-table">
        <thead><tr>
          <th>Coin</th>
          <th>Sinyal</th>
          <th>Strateji</th>
          <th>Güç</th>
        </tr></thead>
        <tbody id="sig-body">${rows}</tbody>
      </table>
      <div id="sig-empty" class="scan-empty hidden" style="padding:16px">Eşleşen coin yok.</div>
    </div>` : `<div class="scan-empty" style="padding:14px 0">Bu taramada sinyal veren coin bulunmadı. Tüm coinler taranmış olsa da seçili stratejiler alım/satım koşulunu sağlamadı.</div>`}

    ${strategyRows ? `<details class="scan-breakdown">
      <summary>Strateji bazında coinler</summary>
      <div class="strat-detail-list">${strategyRows}</div>
    </details>` : ""}
  </div>`;
}

async function loadScanResult(jobId) {
  const host = $("#scan-results");
  if (!host) return;
  try {
    const all = await api("/analysis/scans?limit=20");
    const scan = (all || []).find((s) => s.id === jobId);
    if (!scan) return;
    const temp = document.createElement("div");
    temp.innerHTML = scanResultsHtml([scan, ...all.filter((s) => s.id !== jobId)]);
    const next = temp.firstElementChild;
    host.replaceWith(next);
    bindScanResults();
  } catch (e) { toast(e.message, true); }
}

function bindScanResults() {
  const picker = $("#scan-picker");
  if (picker) picker.addEventListener("change", () => loadScanResult(picker.value));

  const body = $("#sig-body");
  if (!body) return;
  const empty = $("#sig-empty");
  const search = $("#sig-search");
  let filter = "all";

  const apply = () => {
    const q = (search && search.value || "").trim().toUpperCase();
    let shown = 0;
    $$("#sig-body .sig-row").forEach((tr) => {
      const side = tr.dataset.side || "";
      const coin = (tr.dataset.coin || "").toUpperCase();
      // "buy" = yalnız alım, "sell" = yalnız satım, "both" = çelişkili
      const sideOk = filter === "all"
        || (filter === "buy" && side === "buy")
        || (filter === "sell" && side === "sell")
        || (filter === "both" && side === "both");
      const textOk = !q || coin.includes(q);
      const ok = sideOk && textOk;
      tr.classList.toggle("hidden", !ok);
      if (ok) shown += 1;
    });
    if (empty) empty.classList.toggle("hidden", shown > 0);
  };

  $$("#sig-filters [data-filter]").forEach((btn) => btn.addEventListener("click", () => {
    filter = btn.dataset.filter;
    $$("#sig-filters [data-filter]").forEach((b) => b.classList.toggle("active", b === btn));
    apply();
  }));
  if (search) search.addEventListener("input", apply);
  apply();
}

function kpi(label, value, sub, icon) {
  return `<div class="card kpi">
    <div class="kpi-top">
      <h3>${esc(label)}</h3>
      <span class="kpi-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icon}"/></svg></span>
    </div>
    <div class="stat">${esc(value)}</div>
    <div class="muted">${esc(sub)}</div>
  </div>`;
}

function botRow(bot, seriesMap = {}) {
  const pos = bot.state && bot.state.position;
  const running = bot.status === "running";
  const series = seriesMap[bot.id] || [];
  return `<div class="bot-mini">
    <div class="row between">
      <div class="bot-mini-title">
        <span class="status-dot ${running ? "on" : ""}"></span>
        <strong>${esc(bot.name)}</strong>
        <span class="tag gray">${esc(bot.period)}</span>
        <span class="tag ${bot.mode === "live" ? "amber" : "green"}">${esc(bot.mode)}</span>
      </div>
      <div class="row" style="gap:10px">
        ${sparkline(series)}
        ${statusTag(bot.status)}
      </div>
    </div>
    <div class="row mt bot-mini-meta">
      <span><span class="muted">Nakit</span> <b>${money(bot.state && bot.state.cash)}</b></span>
      <span><span class="muted">Toplam K/Z</span> <b data-live="total-${esc(bot.id)}" class="${pnlClass(bot.state && bot.state.total_pnl)}">${bot.state && bot.state.total_pnl !== null && bot.state.total_pnl !== undefined ? signedMoney(bot.state.total_pnl) : "—"}</b></span>
      <span><span class="muted">İşlem</span> <b>${esc((bot.state && bot.state.trade_count) || 0)}</b></span>
      ${pos ? `<span class="tag amber">${esc(pos.coin)} @ ${fmt(pos.entry_price, 6)}</span>
        <span><span class="muted">güncel</span> <b data-live="price-${esc(bot.id)}">${fmt(pos.last_price, 8)}</b></span>
        <span><b data-live="rowpnl-${esc(bot.id)}" class="${pnlClass(pos.unrealized_pnl_pct)}">${Number(pos.unrealized_pnl_pct) > 0 ? "+" : ""}${fmt(pos.unrealized_pnl_pct, 2)}%</b></span>` : '<span class="muted">pozisyon yok</span>'}
    </div>
  </div>`;
}

function quickBot() {
  openBotForm(null, { quick: true });
}

/* ------------------------------------------------------------------ */
/* Bots                                                                */
/* ------------------------------------------------------------------ */
async function renderBots(root) {
  const [bots, stats] = await Promise.all([api("/bots"), api("/stats")]);
  state.bots = bots;
  state.stats = stats;
  renderLiveToggle();
  const signature = JSON.stringify({
    bots: bots.map((b) => [b.id, b.status, b.mode, b.auto_restart, b.state && b.state.cash,
      b.state && b.state.trade_count, b.state && b.state.last_update,
      b.state && b.state.total_realized_pnl, !!(b.state && b.state.position),
      b.state && b.state.unrealized_pnl, b.state && b.state.position && b.state.position.last_price]),
    live: state.liveUnlocked,
  });
  if (root.dataset.sig === signature && root.dataset.view === "bots") {
    scheduleBotsRefresh();
    return;
  }
  root.dataset.sig = signature;
  const seriesMap = {};
  (stats.by_bot || []).forEach((b) => { if (b.bot_id) seriesMap[b.bot_id] = b.series; });
  const liveCount = bots.filter((b) => b.mode === "live").length;
  root.innerHTML = `
    <div class="row between page-head">
      <div>
        <p class="muted">Botlar varsayılan olarak test modunda çalışır. Canlıya geçmek için üst çubuktaki anahtarı aç, sonra botun modunu değiştir.</p>
        <div class="row small">
          <span class="tag ${state.liveUnlocked ? "amber" : "gray"}">Canlı işlem ${state.liveUnlocked ? "açık" : "kapalı"}</span>
          <span class="tag gray">${liveCount} canlı bot</span>
        </div>
      </div>
      <div class="row">
        <button class="ghost" id="quick-bot">Hızlı Bot</button>
        <button class="primary" id="new-bot">Yeni Bot</button>
      </div>
    </div>
    <div class="stack mt" id="bot-list"></div>`;
  $("#new-bot").addEventListener("click", () => openBotForm());
  $("#quick-bot").addEventListener("click", quickBot);
  const list = $("#bot-list");
  if (!bots.length) {
    list.innerHTML = `<div class="card empty-state">
      <strong>Henüz bot yok</strong>
      <p class="muted">“Hızlı Bot” ile mantıklı varsayılanlarla 5 saniyede başla, ya da “Yeni Bot” ile adım adım kur.</p>
    </div>`;
    return;
  }
  list.innerHTML = bots.map((b) => botCard(b, seriesMap)).join("");
  $$("[data-action]", list).forEach((btn) => {
    btn.addEventListener("click", () => botAction(btn.dataset.action, btn.dataset.id, btn.dataset.mode));
  });
  scheduleBotsRefresh();
}

function scheduleBotsRefresh() {
  if (state.view !== "bots") return; // eski sayfa yeni sayfanın timer'ını ezmesin
  clearInterval(state.refreshTimer);
  clearInterval(state.liveTimer);
  state.refreshTimer = setInterval(() => {
    if (state.routeBusy || state.view !== "bots") return;
    renderBots($("#content")).catch(() => {});
  }, 15000);
  state.liveTimer = setInterval(() => {
    if (state.routeBusy || state.view !== "bots") return;
    refreshLivePnl();
  }, 5000);
}

const TRADE_REASONS = {
  signal: ["gray", "sinyal"], stop: ["amber", "stop"], "takipli-stop": ["amber", "takipli stop"],
  trail: ["amber", "takipli stop"], "profit-exit": ["blue", "kâr koruma"],
  "take-profit": ["green", "kâr al"], tp: ["green", "kâr al"], end: ["gray", "test sonu"],
  manuel: ["red", "manuel satış"], harici: ["red", "harici işlem"],
};
function tradeReason(reason) {
  const [cls, label] = TRADE_REASONS[reason] || ["gray", reason || "sinyal"];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}

function riskSummary(risk) {
  const r = risk || {};
  const parts = [];
  if (r.stop_atr) parts.push(`stop ${fmt(r.stop_atr, 0)}×ATR${r.max_stop_pct ? ` (en çok %${fmt(r.max_stop_pct, 0)})` : ""}`);
  if (r.trail_atr) parts.push(`takipli ${fmt(r.trail_atr, 0)}×ATR${r.trail_after_pct ? ` (kâr>%${fmt(r.trail_after_pct, 0)})` : ""}`);
  if (r.profit_exit_donchian) parts.push(`kâr koruma Donchian(${r.profit_exit_donchian})`);
  if (r.take_profit_atr) parts.push(`kâr al ${fmt(r.take_profit_atr, 1)}×ATR`);
  if (r.take_profit_pct) parts.push(`kâr al %${fmt(r.take_profit_pct, 1)}`);
  if (r.cooldown) parts.push(`bekleme ${r.cooldown} mum`);
  return parts.join(" · ");
}

function botCard(bot, seriesMap = {}) {
  const cfg = bot.config || {};
  const specs = (cfg.strategies || []).map((s) => s.name || s.label || s.id).join(", ");
  const listTag = cfg.coin_list ? `<span class="tag gray">liste: ${esc(cfg.coin_list.name)}</span> ` : "";
  const coins = (cfg.coins || []).length ? cfg.coins.join(", ") : "tüm coinler";
  const pos = bot.state && bot.state.position;
  const running = bot.status === "running";
  const live = bot.mode === "live";
  const series = seriesMap[bot.id] || [];
  const liveLocked = !state.liveUnlocked;
  return `<div class="card bot-card ${running ? "is-running" : ""} ${live ? "is-live" : ""}">
    <div class="row between">
      <div class="row" style="gap:12px;align-items:flex-start">
        <span class="status-dot big ${running ? "on" : ""}"></span>
        <div>
          <div class="bot-name">${esc(bot.name)}</div>
          <div class="muted bot-sub">${esc(bot.period)} · ${listTag}${esc(coins)} · ${esc(specs || "strateji yok")}</div>
        </div>
      </div>
      <div class="row">
        ${statusTag(bot.status)}
        <button class="mode-pill ${live ? "live" : "paper"}" data-action="mode" data-mode="${live ? "paper" : "live"}"
          data-id="${esc(bot.id)}" ${live || !liveLocked ? "" : "disabled"}
          title="${live ? "Test moduna al" : liveLocked ? "Önce canlı işlem anahtarını aç" : "Canlı moda geç"}">
          <span class="dot"></span>${live ? "CANLI" : "TEST"}
        </button>
        ${sparkline(series, { width: 90, height: 26 })}
      </div>
    </div>
    <div class="stat-grid mt">
      <div><div class="muted">Nakit</div><div class="stat small">${money(bot.state && bot.state.cash)}</div></div>
      <div><div class="muted">Toplam K/Z</div><div class="stat small ${pnlClass(bot.state && bot.state.total_pnl)}" data-live="total-${esc(bot.id)}">${bot.state && bot.state.total_pnl !== null && bot.state.total_pnl !== undefined ? signedMoney(bot.state.total_pnl) : "—"}</div></div>
      <div><div class="muted">Anlık (açık)</div><div class="stat small ${pnlClass(bot.state && bot.state.unrealized_pnl)}" data-live="unreal-${esc(bot.id)}">${bot.state && bot.state.unrealized_pnl !== null && bot.state.unrealized_pnl !== undefined ? signedMoney(bot.state.unrealized_pnl) : "—"}</div></div>
      <div><div class="muted">Portföy değeri</div><div class="stat small" data-live="equity-${esc(bot.id)}">${money(bot.state && bot.state.equity)}</div></div>
    </div>
    ${pos ? `
    <div class="position-strip mt">
      <span class="tag amber">${esc(pos.coin)}</span>
      <span>adet <b>${fmt(pos.quantity, 8)}</b></span>
      <span>giriş <b>${fmt(pos.entry_price, 8)}</b></span>
      <span>güncel <b data-live="price-${esc(bot.id)}">${fmt(pos.last_price, 8)}</b>
        <span class="muted small">${pos.price_source === "live" ? "canlı" : "mum"}</span></span>
      <span>K/Z <b data-live="pnlpct-${esc(bot.id)}" class="${pnlClass(pos.unrealized_pnl_pct)}">${fmt(pos.unrealized_pnl_pct, 2)}%</b></span>
      ${pos.stop_price ? `<span>stop <b data-live="stop-${esc(bot.id)}">${fmt(pos.stop_price, 8)}</b>
        <span class="muted small" data-live="stopdist-${esc(bot.id)}">${stopDistanceText(pos.stop_distance_pct)}</span></span>` : ""}
      <span>mum <b>${esc(pos.candles || 0)}</b></span>
    </div>` : '<div class="mt muted small">Açık pozisyon yok.</div>'}
    ${bot.state && bot.state.last_error ? `<div class="error mt">${esc(String(bot.state.last_error).split("\n").slice(-3).join("\n"))}</div>` : ""}
    <div class="muted small mt" title="Canlı motor, backtest ile aynı risk kurallarını uygular">
      Risk: ${esc(riskSummary(cfg.risk) || "yok (yalnızca sinyalle kapanır)")}
    </div>
    <div class="row mt">
      <button data-action="start" data-id="${esc(bot.id)}" ${bot.status === "running" ? "disabled" : ""}>Başlat</button>
      <button data-action="stop" data-id="${esc(bot.id)}" ${bot.status !== "running" && bot.status !== "stopping" ? "disabled" : ""}>Durdur</button>
      <button data-action="restart" data-id="${esc(bot.id)}">Yeniden Başlat</button>
      <button data-action="edit" data-id="${esc(bot.id)}" ${bot.status === "running" ? "disabled" : ""}>Düzenle</button>
      <button data-action="logs" data-id="${esc(bot.id)}">Loglar</button>
      <button data-action="delete" data-id="${esc(bot.id)}" class="ghost" ${bot.status === "running" ? "disabled" : ""}>Sil</button>
    </div>
  </div>`;
}

async function botAction(action, id, mode) {
  try {
    if (action === "start") { await api(`/bots/${id}/start`, { method: "POST" }); toast("Bot başlatıldı"); }
    else if (action === "stop") { await api(`/bots/${id}/stop`, { method: "POST" }); toast("Bot durduruldu"); }
    else if (action === "restart") { await api(`/bots/${id}/restart`, { method: "POST" }); toast("Bot yeniden başlatıldı"); }
    else if (action === "logs") { return showLogs(id); }
    else if (action === "edit") {
      const bot = (state.bots || []).find((b) => b.id === id);
      if (bot) return openBotForm(bot);
      return;
    }
    else if (action === "mode") { return switchBotMode(id, mode); }
    else if (action === "delete") {
      if (!confirm("Bu bot silinsin mi? Geçmiş işlemler korunur.")) return;
      await api(`/bots/${id}`, { method: "DELETE" }); toast("Bot silindi");
    }
    route();
  } catch (err) { toast(err.message, true); }
}

async function switchBotMode(id, mode) {
  const bot = (state.bots || []).find((b) => b.id === id);
  const name = bot ? bot.name : "Bot";
  const toLive = mode === "live";
  if (toLive && !state.liveUnlocked) {
    toast("Önce üst çubuktan canlı işlemi aç", true);
    return;
  }
  const ok = await confirmDialog(
    toLive ? "Canlı moda geç" : "Test moduna al",
    toLive
      ? `${name} gerçek emir gönderecek. Bot güvenli şekilde yeniden başlatılacak.`
      : `${name} test moduna alınacak. Açık pozisyon varsa önce kapatılır.`,
    toLive ? "Canlıya geç" : "Teste al",
    toLive,
  );
  if (!ok) return;
  try {
    await api(`/bots/${id}/mode`, { method: "POST", body: { mode } });
    toast(toLive ? "Bot canlı moda alındı" : "Bot test moduna alındı", toLive);
    route();
  } catch (err) { toast(err.message, true); }
}

function field(label, inputHtml) {
  return `<label>${esc(label)}${inputHtml}</label>`;
}

const BOT_PERIODS = ["1m", "5m", "15m", "1h", "4h", "1d"];
const BOT_COIN_PRESETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT"];
const RISK_ITEMS = [
  ["dynamic_stop", "Dinamik stop", "Fiyat yükseldikçe stop seviyesini yukarı taşır."],
  ["static_stop", "Sabit stop", "Giriş fiyatının belirli bir yüzdesi altında çıkar."],
  ["support_stop", "Destek stop", "Destek seviyesi kırılırsa pozisyonu kapatır."],
  ["take_profit", "Kâr al", "Hedef kâra ulaşınca satar."],
];

function botStrategyCatalog() {
  const custom = (state.custom || [])
    .filter((c) => c.status === "active")
    .map((c) => ({
      key: "custom:" + c.id, kind: "custom", name: c.name, version: c.version,
      definition: c.definition, spec: { type: "custom", id: c.id, version: c.version },
    }));
  const builtin = (state.extra || [])
    .filter((b) => !b.archived)
    .map((b) => ({
      key: "builtin:" + b.name,
      kind: "builtin",
      name: b.label || b.name,
      motor: b.name,
      spec: { type: "builtin", name: b.name },
    }));
  return [...custom, ...builtin];
}

async function openBotForm(existing = null, options = {}) {
  if (!state.extra || !state.custom) {
    try {
      const [builtin, custom] = await Promise.all([api("/strategies/builtin"), api("/strategies/custom?include_archived=true")]);
      state.extra = builtin;
      state.custom = custom;
    } catch (err) { toast(err.message, true); return; }
  }

  const catalog = botStrategyCatalog();
  const quick = !existing && !!options.quick;
  const quickPick = catalog.find((c) => c.kind === "custom") || catalog[0] || null;
  const cfg = existing && existing.config ? existing.config : null;
  let lists = [];
  try { lists = await api("/coin-lists"); } catch (e) { lists = []; }
  const presetCoins = options.coins ? options.coins.slice() : null;
  const draft = {
    name: existing ? existing.name : quick ? "Hızlı Bot" : "",
    period: existing ? existing.period : "1h",
    mode: existing ? existing.mode : "paper",
    cash: cfg ? cfg.cash : 100,
    maxPos: cfg ? (cfg.max_position_pct ?? 100) : quick ? 25 : 100,
    coins: cfg ? (cfg.coins || []).slice() : presetCoins ? presetCoins.slice() : quick ? ["BTCUSDT", "ETHUSDT"] : [],
    coinListId: cfg && cfg.coin_list ? cfg.coin_list.id : options.coinListId || "",
    strategies: existing
      ? ((cfg && cfg.strategies) || []).map((s) => (s.type === "custom" ? "custom:" + s.id : "builtin:" + s.name))
      : quick && quickPick ? [quickPick.key] : [],
    risk: Object.assign({ dynamic_stop: false, static_stop: false, support_stop: true, take_profit: true }, (cfg && cfg.risk) || {}),
    filters: Object.assign({ buy_ma_control: false, buy_bb_control: false }, (cfg && cfg.filters) || {}),
    autoRestart: existing ? !!existing.auto_restart : true,
  };
  const pick = (key) => catalog.find((c) => c.key === key);

  const wrap = document.createElement("div");
  wrap.className = "strat-editor";
  wrap.innerHTML = `
    <div class="editor-section">
      <div class="section-head">
        <span class="step">1</span>
        <div><h4>Çalışma modu</h4><p class="muted">Test modunda gerçek emir gönderilmez.</p></div>
      </div>
      <div class="section-body">
        <div class="mode-grid" id="mode-grid">
          <button type="button" class="mode-card" data-mode="paper">
            <strong>Test (paper)</strong><span>Sanal bakiye ile dener, gerçek emir yok.</span>
          </button>
          <button type="button" class="mode-card ${state.liveUnlocked ? "" : "locked"}" data-mode="live"
            ${state.liveUnlocked ? "" : 'disabled title="Önce üst çubuktan canlı işlemi aç"'}>
            <strong>Canlı ${state.liveUnlocked ? "" : '<span class="tag gray">kilitli</span>'}</strong>
            <span>${state.liveUnlocked ? "Gerçek emir gönderir. Tek tıkla açıp kapatabilirsin." : "Canlı işlem anahtarı kapalı. Üst çubuktaki anahtardan aç."}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">2</span>
        <div><h4>Bot kimliği</h4><p class="muted">Ad, zaman dilimi ve bakiye.</p></div>
      </div>
      <div class="section-body">
        <label class="pf wide"><span>Bot adı</span><input id="b-name" value="${esc(draft.name)}" placeholder="Örn. 1h RSI + EMA"></label>
        <div class="pf mt"><span>Zaman dilimi</span><div class="chip-cloud" id="period-chips"></div></div>
        <div class="row mt">
          <label class="pf"><span>Başlangıç nakdi (USDT)</span><input id="b-cash" type="number" min="1" step="1" value="${draft.cash}"></label>
          <label class="pf"><span>Maksimum pozisyon (%)</span><input id="b-pos" type="number" min="1" max="100" value="${draft.maxPos}"></label>
        </div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">3</span>
        <div><h4>Coinler</h4><p class="muted">Hiç seçmezsen <code>coin_list.txt</code> içindeki tüm coinler izlenir.</p></div>
      </div>
      <div class="section-body">
        <label class="pf wide"><span>Coin listesi (isteğe bağlı)</span>
          <select id="b-coin-list">
            <option value="">— Liste seçme —</option>
            ${(lists || []).map((l) => `<option value="${esc(l.id)}">${esc(l.name)} (${l.count})</option>`).join("")}
          </select>
        </label>
        <p class="muted small" id="b-coin-list-hint">Liste seçince coinler aşağıya eklenir. Sonradan listeyi değiştirirsen bot kayıtlı coinleriyle çalışır.</p>
        <div class="chip-cloud mt" id="coin-chips"></div>
        <div class="row mt">
          <input id="coin-add" placeholder="Başka coin ekle (örn. FETUSDT)" style="max-width:230px">
          <button type="button" class="small" id="coin-add-btn">Ekle</button>
        </div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">4</span>
        <div><h4>Stratejiler</h4><p class="muted">Bir veya birden fazla strateji seç. Sinyal aldığında bot işlem yapar.</p></div>
      </div>
      <div class="section-body">
        <input id="strat-search" placeholder="Strateji ara…" class="mb">
        <div class="pick-grid" id="strat-picks"></div>
        <div id="strat-empty" class="empty-state small hidden">
          Hiç özel stratejin yok. <a href="#strategies">Stratejiler</a> ekranından 1 dakikada oluşturabilirsin.
        </div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">5</span>
        <div><h4>Risk koruması</h4><p class="muted">Sinyal gelmese bile pozisyonu güvenli kapatır.</p></div>
      </div>
      <div class="section-body">
        <div class="toggle-list" id="risk-list"></div>
        <div class="toggle-list mt" id="filter-list"></div>
      </div>
    </div>

    <div class="plain-summary bot-summary" id="bot-summary"></div>

    <div class="editor-actions">
      <span id="bot-hint" class="muted small"></span>
      <div class="row">
        <button class="ghost" id="b-cancel" type="button">Vazgeç</button>
        <button class="primary" id="b-save" type="button">${existing ? "Kaydet" : "Botu oluştur"}</button>
      </div>
    </div>`;
  modal(existing ? "Botu Düzenle" : "Yeni Bot", wrap);

  const summary = () => {
    const coins = draft.coins.length ? draft.coins.join(", ") : "tüm coin listesi";
    const parts = [
      draft.mode === "live" ? "CANLI" : "Test",
      draft.period,
      money(draft.cash),
      `%${draft.maxPos} pozisyon`,
      coins,
      draft.strategies.length
        ? draft.strategies.map((k) => (pick(k) || {}).name || k).join(" + ")
        : "strateji yok",
    ];
    $("#bot-summary").innerHTML = `<span class="summary-label">${draft.mode === "live" ? "CANLI" : "TEST"}</span>
      <span class="summary-text">${esc(parts.slice(1).join(" · "))}</span>`;
    const ready = draft.strategies.length > 0 && draft.cash > 0;
    $("#bot-hint").textContent = ready ? "Hazır." : "En az bir strateji seçin.";
    $("#b-save").disabled = !ready;
  };

  /* Mod kartları */
  const renderMode = () => {
    $$("#mode-grid .mode-card").forEach((b) => b.classList.toggle("selected", b.dataset.mode === draft.mode));
    summary();
  };
  $$("#mode-grid .mode-card").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.mode === "live" && !state.liveUnlocked) { toast("Önce üst çubuktan canlı işlemi aç", true); return; }
    draft.mode = b.dataset.mode;
    renderMode();
  }));
  renderMode();

  /* Periyot */
  const renderPeriods = () => {
    const box = $("#period-chips");
    box.innerHTML = "";
    BOT_PERIODS.forEach((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (draft.period === p ? " active" : "");
      b.textContent = p;
      b.addEventListener("click", () => { draft.period = p; renderPeriods(); summary(); });
      box.appendChild(b);
    });
  };
  renderPeriods();

  /* Coinler */
  const renderCoins = () => {
    const box = $("#coin-chips");
    box.innerHTML = "";
    const all = Array.from(new Set([...BOT_COIN_PRESETS, ...draft.coins]));
    all.forEach((coin) => {
      const on = draft.coins.includes(coin);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (on ? " active" : "");
      b.textContent = coin;
      b.title = on ? "Kaldır" : "Ekle";
      b.addEventListener("click", () => {
        draft.coins = on ? draft.coins.filter((c) => c !== coin) : [...draft.coins, coin];
        renderCoins();
        summary();
      });
      box.appendChild(b);
    });
  };
  renderCoins();
  const addCoin = () => {
    const input = $("#coin-add");
    const value = input.value.trim().toUpperCase();
    if (!value) return;
    if (!/^[A-Z0-9]{3,20}$/.test(value)) { toast("Geçersiz coin sembolü", true); return; }
    if (!draft.coins.includes(value)) draft.coins.push(value);
    input.value = "";
    renderCoins();
    summary();
  };
  $("#coin-add-btn").addEventListener("click", addCoin);
  $("#coin-add").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCoin(); } });

  /* Coin listesi seçimi: seçilen listenin coinleri aşağıya eklenir. */
  const listSelect = $("#b-coin-list");
  const applyList = (id) => {
    draft.coinListId = id || "";
    const found = (lists || []).find((l) => l.id === id);
    if (found) {
      const merged = draft.coins.slice();
      found.coins.forEach((c) => { if (!merged.includes(c)) merged.push(c); });
      draft.coins = merged;
    }
    const hint = $("#b-coin-list-hint");
    if (hint) {
      hint.innerHTML = found
        ? `“${esc(found.name)}” listesindeki <b>${found.count}</b> coin eklendi. Kaydettiğinde bu coinler sabitlenir.`
        : 'Liste seçince coinler aşağıya eklenir. Sonradan listeyi değiştirirsen bot kayıtlı coinleriyle çalışır.';
    }
    renderCoins();
    summary();
  };
  if (listSelect) {
    listSelect.value = draft.coinListId || "";
    listSelect.addEventListener("change", () => applyList(listSelect.value));
    if (draft.coinListId) applyList(draft.coinListId);
  }

  /* Strateji seçimi */
  const renderPicks = (filter = "") => {
    const box = $("#strat-picks");
    box.innerHTML = "";
    const q = filter.trim().toLowerCase();
    const items = catalog.filter((c) => !q || c.name.toLowerCase().includes(q));
    $("#strat-empty").classList.toggle("hidden", catalog.length > 0);
    if (!items.length) {
      box.innerHTML = `<div class="muted small" style="padding:6px">Eşleşen strateji yok.</div>`;
      return;
    }
    items.forEach((item) => {
      const on = draft.strategies.includes(item.key);
      const card = document.createElement("button");
      card.type = "button";
      card.className = "pick-card" + (on ? " selected" : "");
      let rules = "";
      if (item.kind === "custom" && item.definition) {
        rules = `<span class="pick-rules"><span class="rule-badge buy">AL</span> ${esc(groupText(item.definition.buy) || "—")}</span>
                 <span class="pick-rules"><span class="rule-badge sell">SAT</span> ${esc(groupText(item.definition.sell) || "—")}</span>`;
      } else {
        rules = `<span class="pick-rules muted">Hazır strateji — mevcut motorla çalışır.</span>`;
      }
      card.innerHTML = `
        <span class="pick-head">
          <strong>${esc(item.name)}</strong>
          <span class="tag ${item.kind === "custom" ? "green" : "gray"}">${item.kind === "custom" ? "özel v" + item.version : "hazır"}</span>
        </span>
        ${item.motor && item.motor !== item.name ? `<span class="muted small mono">${esc(item.motor)}</span>` : ""}
        ${rules}`;
      card.addEventListener("click", () => {
        draft.strategies = on ? draft.strategies.filter((k) => k !== item.key) : [...draft.strategies, item.key];
        renderPicks($("#strat-search").value);
        summary();
      });
      box.appendChild(card);
    });
  };
  renderPicks();
  $("#strat-search").addEventListener("input", (e) => renderPicks(e.target.value));

  /* Risk anahtarları */
  const renderToggles = () => {
    const box = $("#risk-list");
    box.innerHTML = "";
    RISK_ITEMS.forEach(([key, label, desc]) => {
      const on = !!draft.risk[key];
      const row = document.createElement("button");
      row.type = "button";
      row.className = "toggle-row" + (on ? " on" : "");
      row.innerHTML = `<span class="switch"></span><span class="toggle-text"><strong>${esc(label)}</strong><small>${esc(desc)}</small></span>`;
      row.addEventListener("click", () => { draft.risk[key] = !draft.risk[key]; renderToggles(); });
      box.appendChild(row);
    });
  };
  renderToggles();

  const FILTER_ITEMS = [
    ["buy_ma_control", "EMA50 üzeri alım filtresi", "Fiyat EMA50 üzerindeyken alım yapar."],
    ["buy_bb_control", "BB orta bandı altı alım filtresi", "Yalnızca Bollinger orta bandının altında alım yapar."],
  ];
  const renderFilters = () => {
    const box = $("#filter-list");
    box.innerHTML = "";
    FILTER_ITEMS.forEach(([key, label, desc]) => {
      const on = !!draft.filters[key];
      const row = document.createElement("button");
      row.type = "button";
      row.className = "toggle-row" + (on ? " on" : "");
      row.innerHTML = `<span class="switch"></span><span class="toggle-text"><strong>${esc(label)}</strong><small>${esc(desc)}</small></span>`;
      row.addEventListener("click", () => { draft.filters[key] = !draft.filters[key]; renderFilters(); });
      box.appendChild(row);
    });
    const auto = document.createElement("button");
    auto.type = "button";
    auto.className = "toggle-row" + (draft.autoRestart ? " on" : "");
    auto.innerHTML = `<span class="switch"></span><span class="toggle-text"><strong>Çökmede otomatik yeniden başlat</strong><small>Bot beklenmedik şekilde kapanırsa supervisor yeniden ayağa kaldırır.</small></span>`;
    auto.addEventListener("click", () => { draft.autoRestart = !draft.autoRestart; renderFilters(); });
    box.appendChild(auto);
  };
  renderFilters();

  /* Kaydet */
  $("#b-cancel").addEventListener("click", closeModal);
  $("#b-save").addEventListener("click", async () => {
    try {
      const specs = draft.strategies.map(pick).filter(Boolean).map((item) => item.spec);
      if (!specs.length) throw new Error("En az bir strateji seçin");
      if (draft.mode === "live" && !state.liveUnlocked) throw new Error("Canlı işlem anahtarı kapalı. Üst çubuktan açın.");
      const body = {
        name: $("#b-name").value.trim() || "İsimsiz bot",
        period: draft.period,
        mode: draft.mode,
        cash: Number($("#b-cash").value),
        max_position_pct: Number($("#b-pos").value),
        coins: draft.coins,
        coin_list_id: draft.coinListId || null,
        strategies: specs,
        risk: Object.assign({}, draft.risk),
        filters: draft.filters,
        auto_restart: draft.autoRestart,
      };
      if (existing) await api(`/bots/${existing.id}`, { method: "PATCH", body });
      else await api("/bots", { method: "POST", body });
      closeModal(); toast("Bot kaydedildi"); route();
    } catch (err) { toast(err.message, true); }
  });
  summary();
}

async function showLogs(id) {
  const LEVELS = { info: "bilgi", warning: "uyarı", error: "hata", debug: "ayrıntı" };
  const render = (data) => {
    const fileLines = data.lines || [];
    const events = (data.events || []).slice(-40).reverse();
    return `
      <div class="log-box" id="log-box">${esc(fileLines.join("\n") || "Henüz log satırı yok. Bot ilk mumu bekliyor olabilir.")}</div>
      <div class="row between mt"><strong class="small">Son olaylar</strong><button class="small" id="log-refresh">Yenile</button></div>
      <div class="event-list">${events.map((e) => `
        <div class="event-row">
          <span class="tag ${e.level === "error" ? "red" : e.level === "warning" ? "amber" : "gray"}">${esc(LEVELS[e.level] || e.level || "bilgi")}</span>
          <span class="mono small">${esc(fmtIso(e.created_at))}</span>
          <span class="event-msg">${esc(e.message)}</span>
        </div>`).join("") || '<div class="muted small">Olay kaydı yok.</div>'}
      </div>`;
  };
  const data = await api(`/bots/${id}/logs?lines=400`);
  modal("Bot Logları", render(data));
  const refresh = async () => {
    const d = await api(`/bots/${id}/logs?lines=400`);
    $("#modal-body").innerHTML = render(d);
    $("#log-refresh").addEventListener("click", refresh);
    const box = $("#log-box"); box.scrollTop = box.scrollHeight;
  };
  $("#log-refresh").addEventListener("click", refresh);
  const box = $("#log-box"); box.scrollTop = box.scrollHeight;
}

/* ------------------------------------------------------------------ */
/* Stratejiler                                                         */
/* ------------------------------------------------------------------ */
/* ---------- Model yardımcıları ---------- */
function indicatorSpec(id) { return (state.indicators || []).find((i) => i.id === id); }

function defaultParams(id) {
  const spec = indicatorSpec(id);
  const params = {};
  (spec ? spec.params : []).forEach((p) => { params[p.name] = p.default; });
  return params;
}

function ind(id, params, output) {
  const spec = indicatorSpec(id);
  return {
    type: "indicator",
    id,
    params: params || defaultParams(id),
    output: output || (spec ? spec.outputs[0] : "value"),
  };
}
function px(field = "close") { return { type: "price", field }; }
function prev(operand, shift = 1) { return { type: "offset", shift, operand }; }
function num(value) { return { type: "constant", value }; }
function mkCond(left, op, right, extra) { return Object.assign({ left, op, right }, extra || {}); }

function newOperand(kind = "indicator") {
  if (kind === "price") return px();
  if (kind === "constant") return num(30);
  if (kind === "offset") return { type: "offset", shift: 1, operand: px("close") };
  const preferred = (state.indicators || []).find((i) => i.id === "RSI") || (state.indicators || [])[0];
  return ind(preferred ? preferred.id : "RSI");
}

function newCondition() {
  return { left: newOperand("indicator"), op: "lt", right: newOperand("constant") };
}

function newGroup(logic = "AND") { return { logic, conditions: [newCondition()] }; }

/* ---------- İnsan dili ---------- */
const OPS = [
  ["gt", ">", "büyüktür"],
  ["gte", "≥", "büyük veya eşit"],
  ["lt", "<", "küçüktür"],
  ["lte", "≤", "küçük veya eşit"],
  ["eq", "=", "eşittir"],
  ["neq", "≠", "eşit değildir"],
  ["crosses_above", "↗", "yukarı keser"],
  ["crosses_below", "↘", "aşağı keser"],
  ["rising", "↑", "yükseliyor"],
  ["falling", "↓", "düşüyor"],
  ["rising_for_n", "↑↑", "ardışık yükseliyor"],
  ["falling_for_n", "↓↓", "ardışık düşüyor"],
  ["between", "↔", "arasında"],
  ["outside", "↮", "dışında"],
  ["pct_change_gt", "%>", "% değişimi büyüktür"],
  ["pct_change_lt", "%<", "% değişimi küçüktür"],
];
const DEFAULT_OPS = ["gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below", "rising", "falling"];

const PRICE_LABELS = {
  close: "kapanış", open: "açılış", high: "en yüksek", low: "en düşük",
  hl2: "orta (HL/2)", hlc3: "tipik (HLC/3)", ohlc4: "OHLC/4",
};

function operandText(operand) {
  if (!operand) return "?";
  if (operand.type === "constant") return String(operand.value);
  if (operand.type === "price") return PRICE_LABELS[operand.field] || operand.field || "kapanış";
  if (operand.type === "volume") return "hacim";
  if (operand.type === "indicator") {
    const spec = indicatorSpec(operand.id);
    const params = Object.values(operand.params || {}).join(", ");
    const label = spec ? spec.label : operand.id;
    const out = operand.output && operand.output !== (spec ? spec.outputs[0] : "value")
      ? ` · ${operand.output}` : "";
    return `${label}${params ? `(${params})` : ""}${out}`;
  }
  if (operand.type === "offset") return `${operandText(operand.operand)} (${operand.shift} mum önce)`;
  if (operand.type === "math") {
    const sym = { add: "+", sub: "−", mul: "×", div: "÷", pct_diff: "%fark" }[operand.op] || operand.op;
    return `(${operandText(operand.left)} ${sym} ${operandText(operand.right)})`;
  }
  return "?";
}

function opSymbol(op) { const row = OPS.find((o) => o[0] === op); return row ? row[1] : op; }

function conditionText(cond) {
  if (!cond) return "";
  if (cond.op === "between" || cond.op === "outside") {
    const sym = cond.op === "between" ? "↔" : "↮";
    return `${operandText(cond.left)} ${sym} ${cond.min ?? "?"} – ${cond.max ?? "?"}`;
  }
  let text = `${operandText(cond.left)} ${opSymbol(cond.op)} ${operandText(cond.right)}`;
  if (["rising_for_n", "falling_for_n"].includes(cond.op)) text += ` (${cond.lookback || 3} mum)`;
  if (["pct_change_gt", "pct_change_lt"].includes(cond.op)) text += ` (${cond.lookback || 1} mum)`;
  return text;
}

function groupText(group) {
  if (!group) return "";
  const parts = (group.conditions || []).map((c) => (c.conditions ? `(${groupText(c)})` : conditionText(c)));
  const joiner = (group.logic || "AND").toUpperCase() === "OR" ? " VEYA " : " VE ";
  return parts.filter(Boolean).join(joiner) || "—";
}

/* ---------- Şablonlar ---------- */
function strategyTemplates() {
  return [
    {
      key: "rsi",
      title: "RSI Dip / Zirve",
      desc: "RSI aşırı satımda al, aşırı alımda sat. En basit başlangıç.",
      build: () => ({
        name: "RSI Dip / Zirve",
        buy: { logic: "AND", conditions: [mkCond(ind("RSI", { length: 14 }), "lt", num(30))] },
        sell: { logic: "OR", conditions: [mkCond(ind("RSI", { length: 14 }), "gt", num(70))] },
      }),
    },
    {
      key: "ema",
      title: "EMA Kesişimi",
      desc: "Fiyat hareketli ortalamayı yukarı kestiğinde al, aşağı kestiğinde sat.",
      build: () => ({
        name: "EMA Kesişimi",
        buy: { logic: "AND", conditions: [mkCond(px("close"), "crosses_above", ind("EMA", { length: 50 }))] },
        sell: { logic: "OR", conditions: [mkCond(px("close"), "crosses_below", ind("EMA", { length: 50 }))] },
      }),
    },
    {
      key: "bollinger",
      title: "Bollinger Dönüşü",
      desc: "Fiyat alt banda indiğinde al, üst banda çıktığında sat.",
      build: () => ({
        name: "Bollinger Dönüşü",
        buy: { logic: "AND", conditions: [mkCond(px("close"), "lt", ind("BB", { length: 20, std: 2 }, "lower"))] },
        sell: { logic: "OR", conditions: [mkCond(px("close"), "gt", ind("BB", { length: 20, std: 2 }, "upper"))] },
      }),
    },
    {
      key: "macd",
      title: "MACD Momentum",
      desc: "MACD histogramı pozitife döndüğünde al, negatife döndüğünde sat.",
      build: () => ({
        name: "MACD Momentum",
        buy: { logic: "AND", conditions: [mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "gt", num(0))] },
        sell: { logic: "OR", conditions: [mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "lt", num(0))] },
      }),
    },
    {
      key: "trend",
      title: "Trend Takibi",
      desc: "Fiyat EMA200 üzerinde ve trend güçlüyken al, EMA altına inince sat.",
      build: () => ({
        name: "Trend Takibi",
        buy: {
          logic: "AND",
          conditions: [
            mkCond(px("close"), "gt", ind("EMA", { length: 200 })),
            mkCond(ind("ADX", { length: 14 }), "gt", num(25)),
          ],
        },
        sell: { logic: "OR", conditions: [mkCond(px("close"), "lt", ind("EMA", { length: 200 }))] },
      }),
    },
    {
      key: "supertrend",
      title: "SuperTrend",
      desc: "SuperTrend yönü yukarı olduğunda al, aşağı olduğunda sat.",
      build: () => ({
        name: "SuperTrend",
        buy: { logic: "AND", conditions: [mkCond(ind("SUPERTREND", { atr_length: 10, factor: 3 }, "direction"), "eq", num(1))] },
        sell: { logic: "OR", conditions: [mkCond(ind("SUPERTREND", { atr_length: 10, factor: 3 }, "direction"), "eq", num(-1))] },
      }),
    },
    {
      key: "volume",
      title: "RSI + Hacim",
      desc: "RSI düşükken hacim ortalamanın üzerindeyse al.",
      build: () => ({
        name: "RSI + Hacim",
        buy: {
          logic: "AND",
          conditions: [
            mkCond(ind("RSI", { length: 14 }), "lt", num(35)),
            mkCond(ind("VOLUME_SMA", { length: 20 }, "ratio"), "gt", num(1.5)),
          ],
        },
        sell: { logic: "OR", conditions: [mkCond(ind("RSI", { length: 14 }), "gt", num(65))] },
      }),
    },
    {
      key: "t3qqe",
      title: "T3 + QQE MOD",
      desc: "T3 yukarı dönerken QQE alım sinyali verirse al; T3 aşağı dönerken QQE satım sinyali verirse sat.",
      build: () => ({
        name: "T3 + QQE MOD",
        buy: {
          logic: "AND",
          conditions: [
            mkCond(ind("T3", { length: 8, factor: 0.7 }, "direction"), "eq", num(1)),
            mkCond(ind("QQE_MOD", {}, "signal"), "eq", num(1)),
          ],
        },
        sell: {
          logic: "OR",
          conditions: [
            mkCond(ind("T3", { length: 8, factor: 0.7 }, "direction"), "eq", num(-1)),
            mkCond(ind("QQE_MOD", {}, "signal"), "eq", num(-1)),
          ],
        },
      }),
    },
    {
      key: "t3trend",
      title: "T3 Trend Takibi",
      desc: "Fiyat T3 çizgisini yukarı kesince al, aşağı kesince sat.",
      build: () => ({
        name: "T3 Trend Takibi",
        buy: { logic: "AND", conditions: [mkCond(px("close"), "crosses_above", ind("T3", { length: 8, factor: 0.7 }))] },
        sell: { logic: "OR", conditions: [mkCond(px("close"), "crosses_below", ind("T3", { length: 8, factor: 0.7 }))] },
      }),
    },
    {
      key: "combo",
      title: "Karma: (A ve B) veya (C ve D)",
      desc: "İki farklı senaryodan biri gerçekleşince alır. Gruplu VE/VEYA mantığı örneği.",
      build: () => ({
        name: "Karma Sinyal",
        buy: {
          logic: "OR",
          conditions: [
            {
              logic: "AND",
              conditions: [
                mkCond(ind("RSI", { length: 14 }), "lt", num(35)),
                mkCond(px("close"), "gt", ind("EMA", { length: 200 })),
              ],
            },
            {
              logic: "AND",
              conditions: [
                mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "gt", num(0)),
                mkCond(ind("ADX", { length: 14 }), "gt", num(20)),
              ],
            },
          ],
        },
        sell: {
          logic: "OR",
          conditions: [
            {
              logic: "AND",
              conditions: [
                mkCond(ind("RSI", { length: 14 }), "gt", num(70)),
                mkCond(px("close"), "lt", ind("EMA", { length: 50 })),
              ],
            },
            {
              logic: "AND",
              conditions: [
                mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "lt", num(0)),
                mkCond(ind("ADX", { length: 14 }), "lt", num(20)),
              ],
            },
          ],
        },
      }),
    },
    {
      key: "blank",
      title: "Boş Başla",
      desc: "Sıfırdan kendi kurallarını yaz.",
      build: () => ({ name: "", buy: newGroup("AND"), sell: newGroup("OR") }),
    },
  ];
}

/* ---------- Hızlı kural ekleme ---------- */
const QUICK_RULES = {
  buy: [
    { label: "RSI düşük", make: () => mkCond(ind("RSI", { length: 14 }), "lt", num(30)) },
    { label: "EMA'yı yukarı kes", make: () => mkCond(px("close"), "crosses_above", ind("EMA", { length: 50 })) },
    { label: "Alt bandın altında", make: () => mkCond(px("close"), "lt", ind("BB", { length: 20, std: 2 }, "lower")) },
    { label: "MACD pozitif", make: () => mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "gt", num(0)) },
    { label: "Trend güçlü", make: () => mkCond(ind("ADX", { length: 14 }), "gt", num(25)) },
    { label: "Hacim yüksek", make: () => mkCond(ind("VOLUME_SMA", { length: 20 }, "ratio"), "gt", num(1.5)) },
    { label: "Fiyat yükseliyor", make: () => mkCond(px("close"), "rising", px("close")) },
    { label: "T3 yükseliyor", make: () => mkCond(ind("T3", { length: 8, factor: 0.7 }, "direction"), "eq", num(1)) },
    { label: "Fiyat T3 üzerinde", make: () => mkCond(px("close"), "gt", ind("T3", { length: 8, factor: 0.7 })) },
    { label: "QQE alım sinyali", make: () => mkCond(ind("QQE_MOD", {}, "signal"), "eq", num(1)) },
    { label: "Fiyat önceki mumdan yüksek", make: () => mkCond(px("close"), "gt", prev(px("close"))) },
    { label: "RSI önceki mumdan yüksek", make: () => mkCond(ind("RSI", { length: 14 }), "gt", prev(ind("RSI", { length: 14 }))) },
  ],
  sell: [
    { label: "RSI yüksek", make: () => mkCond(ind("RSI", { length: 14 }), "gt", num(70)) },
    { label: "EMA'yı aşağı kes", make: () => mkCond(px("close"), "crosses_below", ind("EMA", { length: 50 })) },
    { label: "Üst bandın üstünde", make: () => mkCond(px("close"), "gt", ind("BB", { length: 20, std: 2 }, "upper")) },
    { label: "MACD negatif", make: () => mkCond(ind("MACD", { fast: 12, slow: 26, signal: 9 }, "histogram"), "lt", num(0)) },
    { label: "Trend zayıf", make: () => mkCond(ind("ADX", { length: 14 }), "lt", num(20)) },
    { label: "Fiyat düşüyor", make: () => mkCond(px("close"), "falling", px("close")) },
    { label: "T3 düşüyor", make: () => mkCond(ind("T3", { length: 8, factor: 0.7 }, "direction"), "eq", num(-1)) },
    { label: "Fiyat T3 altında", make: () => mkCond(px("close"), "lt", ind("T3", { length: 8, factor: 0.7 })) },
    { label: "QQE satım sinyali", make: () => mkCond(ind("QQE_MOD", {}, "signal"), "eq", num(-1)) },
    { label: "Fiyat önceki mumdan düşük", make: () => mkCond(px("close"), "lt", prev(px("close"))) },
    { label: "RSI önceki mumdan düşük", make: () => mkCond(ind("RSI", { length: 14 }), "lt", prev(ind("RSI", { length: 14 }))) },
  ],
};

/* ---------- Editörler ---------- */
function operandEditor(operand, onStructural, onValue, depth = 0) {
  const box = document.createElement("div");
  box.className = "operand-box";
  if (depth > 0) box.classList.add("operand-nested");

  const typeSel = document.createElement("select");
  typeSel.className = "type-select";
  typeSel.title = "Değer türü";
  const types = [["indicator", "İndikatör"], ["price", "Fiyat"], ["constant", "Sayı"]];
  if (depth === 0) types.push(["offset", "Önceki mum"]);
  types.forEach(([v, l]) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = l;
    if ((operand.type || "indicator") === v) o.selected = true;
    typeSel.appendChild(o);
  });
  typeSel.addEventListener("change", () => {
    const next = newOperand(typeSel.value);
    Object.keys(operand).forEach((k) => delete operand[k]);
    Object.assign(operand, next);
    onStructural();
  });
  box.appendChild(typeSel);

  const fields = document.createElement("div");
  fields.className = "operand-fields";

  if (operand.type === "offset") {
    const shiftWrap = document.createElement("label");
    shiftWrap.className = "pf";
    const shiftLabel = document.createElement("span");
    shiftLabel.textContent = "Kaç mum önce";
    const shiftInput = document.createElement("input");
    shiftInput.type = "number";
    shiftInput.min = "1";
    shiftInput.max = "50";
    shiftInput.value = operand.shift || 1;
    shiftInput.addEventListener("input", () => {
      operand.shift = Math.max(1, Number(shiftInput.value) || 1);
      onValue();
    });
    shiftWrap.appendChild(shiftLabel);
    shiftWrap.appendChild(shiftInput);
    fields.appendChild(shiftWrap);

    if (!operand.operand) operand.operand = px("close");
    const innerBox = operandEditor(operand.operand, onStructural, onValue, depth + 1);
    innerBox.classList.add("offset-inner");
    fields.appendChild(innerBox);
  } else if (operand.type === "indicator") {
    const indSel = document.createElement("select");
    indSel.className = "ind-select";
    (state.indicators || []).forEach((spec) => {
      const o = document.createElement("option");
      o.value = spec.id; o.textContent = spec.label;
      if (operand.id === spec.id) o.selected = true;
      indSel.appendChild(o);
    });
    indSel.addEventListener("change", () => {
      operand.id = indSel.value;
      operand.params = defaultParams(indSel.value);
      operand.output = indicatorSpec(indSel.value).outputs[0];
      onStructural();
    });
    fields.appendChild(indSel);

    const spec = indicatorSpec(operand.id);
    if (spec && spec.params.length) {
      const params = document.createElement("div");
      params.className = "params";
      spec.params.forEach((p) => {
        const wrap = document.createElement("label");
        wrap.className = "pf";
        const span = document.createElement("span");
        span.textContent = p.label;
        const inp = document.createElement("input");
        inp.type = "number"; inp.step = p.step; inp.min = p.min; inp.max = p.max;
        inp.value = operand.params && operand.params[p.name] != null ? operand.params[p.name] : p.default;
        inp.addEventListener("input", () => {
          operand.params = operand.params || {};
          operand.params[p.name] = Number(inp.value);
          onValue();
        });
        wrap.appendChild(span);
        wrap.appendChild(inp);
        params.appendChild(wrap);
      });
      fields.appendChild(params);
    }

    if (spec && spec.outputs.length > 1) {
      const wrap = document.createElement("label");
      wrap.className = "pf";
      const span = document.createElement("span"); span.textContent = "Değer";
      const outSel = document.createElement("select");
      spec.outputs.forEach((out) => {
        const o = document.createElement("option");
        o.value = out; o.textContent = out;
        if (operand.output === out) o.selected = true;
        outSel.appendChild(o);
      });
      outSel.addEventListener("change", () => { operand.output = outSel.value; onStructural(); });
      wrap.appendChild(span); wrap.appendChild(outSel);
      fields.appendChild(wrap);
    }
  } else if (operand.type === "price") {
    const wrap = document.createElement("label");
    wrap.className = "pf";
    const span = document.createElement("span"); span.textContent = "Fiyat";
    const sel = document.createElement("select");
    Object.entries(PRICE_LABELS).forEach(([v, l]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = l;
      if (operand.field === v) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => { operand.field = sel.value; onStructural(); });
    wrap.appendChild(span); wrap.appendChild(sel);
    fields.appendChild(wrap);
  } else {
    const wrap = document.createElement("label");
    wrap.className = "pf";
    const span = document.createElement("span"); span.textContent = "Değer";
    const inp = document.createElement("input");
    inp.type = "number"; inp.step = "any"; inp.value = operand.value;
    inp.addEventListener("input", () => { operand.value = Number(inp.value); onValue(); });
    wrap.appendChild(span); wrap.appendChild(inp);
    fields.appendChild(wrap);
  }

  box.appendChild(fields);
  return box;
}

function conditionEditor(cond, onStructural, onValue, onRemove) {
  const wrap = document.createElement("div");
  wrap.className = "rule";

  const sentence = document.createElement("div");
  sentence.className = "rule-sentence";
  sentence.textContent = conditionText(cond);
  const refresh = () => {
    sentence.textContent = conditionText(cond);
    if (onValue) onValue();
  };

  const main = document.createElement("div");
  main.className = "rule-main";
  main.appendChild(operandEditor(cond.left, onStructural, refresh));

  const opWrap = document.createElement("label");
  opWrap.className = "pf op";
  const opLabel = document.createElement("span"); opLabel.textContent = "Karşılaştırma";
  const opSel = document.createElement("select");
  DEFAULT_OPS.forEach((value) => {
    const row = OPS.find((o) => o[0] === value);
    const o = document.createElement("option");
    o.value = value; o.textContent = `${row[1]}  ${row[2]}`;
    if (cond.op === value) o.selected = true;
    opSel.appendChild(o);
  });
  if (!DEFAULT_OPS.includes(cond.op)) {
    const row = OPS.find((o) => o[0] === cond.op);
    const o = document.createElement("option");
    o.value = cond.op; o.textContent = row ? `${row[1]}  ${row[2]}` : cond.op;
    o.selected = true; opSel.appendChild(o);
  }
  const OP_HELP = {
    crosses_above: "Yukarı keser: bu mumda sol değer sağdan BÜYÜK, önceki mumda KÜÇÜK veya EŞİT olmalı.",
    crosses_below: "Aşağı keser: bu mumda sol değer sağdan KÜÇÜK, önceki mumda BÜYÜK veya EŞİT olmalı.",
    rising: "Yükseliyor: bu mumdaki değer önceki mumdaki değerden büyük.",
    falling: "Düşüyor: bu mumdaki değer önceki mumdaki değerden küçük.",
  };
  const applyOpHelp = () => {
    opSel.title = OP_HELP[cond.op] || "";
    opWrap.title = opSel.title;
  };
  opSel.addEventListener("change", () => { cond.op = opSel.value; onStructural(); });
  opWrap.appendChild(opLabel); opWrap.appendChild(opSel);
  if (OP_HELP[cond.op]) {
    const help = document.createElement("small");
    help.className = "op-help";
    help.textContent = cond.op === "crosses_above" || cond.op === "crosses_below"
      ? "Bu mum + önceki mum birlikte kontrol edilir"
      : "Önceki muma göre kontrol edilir";
    opWrap.appendChild(help);
  }
  applyOpHelp();
  main.appendChild(opWrap);

  if (cond.op === "between" || cond.op === "outside") {
    const minWrap = document.createElement("label");
    minWrap.className = "pf";
    minWrap.innerHTML = "<span>Alt sınır</span>";
    const min = document.createElement("input");
    min.type = "number"; min.step = "any"; min.value = cond.min ?? "";
    min.addEventListener("input", () => { cond.min = Number(min.value); refresh(); });
    minWrap.appendChild(min);
    const maxWrap = document.createElement("label");
    maxWrap.className = "pf";
    maxWrap.innerHTML = "<span>Üst sınır</span>";
    const max = document.createElement("input");
    max.type = "number"; max.step = "any"; max.value = cond.max ?? "";
    max.addEventListener("input", () => { cond.max = Number(max.value); refresh(); });
    maxWrap.appendChild(max);
    main.appendChild(minWrap);
    main.appendChild(maxWrap);
  } else {
    main.appendChild(operandEditor(cond.right, onStructural, refresh));
  }

  if (["rising_for_n", "falling_for_n", "pct_change_gt", "pct_change_lt"].includes(cond.op)) {
    const w = document.createElement("label");
    w.className = "pf";
    w.innerHTML = "<span>Mum sayısı</span>";
    const lb = document.createElement("input");
    lb.type = "number"; lb.min = 1; lb.value = cond.lookback ?? 3;
    lb.addEventListener("input", () => { cond.lookback = Number(lb.value); refresh(); });
    w.appendChild(lb);
    main.appendChild(w);
  }

  const del = document.createElement("button");
  del.type = "button";
  del.className = "icon-btn rule-remove";
  del.title = "Bu kuralı sil";
  del.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3 1.4 1.4Z"/></svg>';
  del.addEventListener("click", onRemove);
  main.appendChild(del);

  wrap.appendChild(main);
  wrap.appendChild(sentence);

  return wrap;
}

function logicToggle(group, onStructural, depth = 0) {
  const wrap = document.createElement("div");
  wrap.className = "logic-toggle";
  const label = document.createElement("span");
  label.className = "logic-label";
  label.textContent = depth ? "Bu grup nasıl birleşsin?" : "Kurallar nasıl birleşsin?";
  wrap.appendChild(label);
  [["AND", "Tümü sağlanmalı (VE)"], ["OR", "Herhangi biri (VEYA)"]].forEach(([v, l]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip" + ((group.logic || "AND") === v ? " active" : "");
    b.textContent = l;
    b.addEventListener("click", () => { group.logic = v; onStructural(); });
    wrap.appendChild(b);
  });
  return wrap;
}

function groupEditor(group, side, onChange, onValue, onRemove = null, depth = 0, groupNo = null) {
  const wrap = document.createElement("div");
  wrap.className = "rule-group" + (depth ? " nested" : "");

  if (depth) {
    const head = document.createElement("div");
    head.className = "group-head";
    head.innerHTML = `<span class="group-title">Alt grup ${groupNo ?? ""}</span>
      <span class="muted small">${(group.logic || "AND") === "OR" ? "içindekilerden biri yeterli" : "içindekilerin tümü gerekli"}</span>`;
    wrap.appendChild(head);
  }

  wrap.appendChild(logicToggle(group, onChange, depth));

  if (!group.conditions.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state small";
    empty.textContent = "Henüz kural yok. Aşağıdan bir kural veya alt grup ekleyin.";
    wrap.appendChild(empty);
  }

  group.conditions.forEach((item, index) => {
    const remove = () => { group.conditions.splice(index, 1); onChange(); };
    if (item.conditions) wrap.appendChild(groupEditor(item, side, onChange, onValue, remove, depth + 1, index + 1));
    else wrap.appendChild(conditionEditor(item, onChange, onValue, remove));
  });

  wrap.appendChild(quickAddBar(group, side, onChange, depth));

  if (onRemove) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "ghost small";
    del.textContent = "Bu grubu sil";
    del.addEventListener("click", onRemove);
    wrap.appendChild(del);
  }
  return wrap;
}

function quickAddBar(group, side, onChange, depth = 0) {
  const bar = document.createElement("div");
  bar.className = "quick-add" + (depth ? " nested" : "");
  const label = document.createElement("span");
  label.className = "quick-label";
  label.textContent = depth ? "Bu gruba ekle:" : "Hızlı ekle:";
  bar.appendChild(label);

  if (depth < 2) {
    [["AND", "+ VE grubu"], ["OR", "+ VEYA grubu"]].forEach(([logic, text]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip group";
      b.textContent = text;
      b.title = logic === "AND"
        ? "İçindeki tüm koşulların birlikte sağlanması gereken alt grup"
        : "İçindeki koşullardan birinin sağlanmasının yeterli olduğu alt grup";
      b.addEventListener("click", () => {
        group.conditions.push(newGroup(logic));
        onChange();
      });
      bar.appendChild(b);
    });
  }

  (QUICK_RULES[side] || []).forEach((rule) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = "+ " + rule.label;
    b.addEventListener("click", () => { group.conditions.push(rule.make()); onChange(); });
    bar.appendChild(b);
  });
  const prevRule = document.createElement("button");
  prevRule.type = "button";
  prevRule.className = "chip group";
  prevRule.textContent = "+ Önceki mum";
  prevRule.title = "Soldaki değeri N mum önceki değerle karşılaştır";
  prevRule.addEventListener("click", () => {
    const cond = newCondition();
    cond.right = { type: "offset", shift: 1, operand: px("close") };
    group.conditions.push(cond);
    onChange();
  });
  bar.appendChild(prevRule);

  const empty = document.createElement("button");
  empty.type = "button";
  empty.className = "chip outline";
  empty.textContent = "+ Boş kural";
  empty.addEventListener("click", () => { group.conditions.push(newCondition()); onChange(); });
  bar.appendChild(empty);
  return bar;
}

async function renderStrategies(root) {
  state.catalog = await api("/strategies/indicators");
  state.indicators = state.catalog;
  const [builtin, custom] = await Promise.all([
    api("/strategies/builtin?include_archived=true"),
    api("/strategies/custom?include_archived=true"),
  ]);
  state.extra = builtin;
  state.custom = custom;

  const activeCustom = custom.filter((s) => s.status !== "archived").length;
  const activeBuiltin = builtin.filter((b) => !b.archived).length;

  const tfBadge = (item) => {
    const periods = item.timeframe_periods || {};
    const best = item.best_timeframe;
    if (!item.timeframe_reliable) {
      return `<span class="tag tf-tag bad" title="Ölçüm güvenilmez: aşırı/uçuk getiri">zaman dilimi ?</span>`;
    }
    if (!Object.keys(periods).length) {
      if (!best) return `<span class="tag tf-tag" title="Yeterli işlem yok">zaman dilimi ?</span>`;
      return `<span class="tag tf-tag ${item.timeframe_edge === "üstün" ? "green" : "amber"}" title="En iyi zaman dilimi: ${esc(best)}">en iyi ${esc(best)}${item.timeframe_edge === "üstün" ? "" : " (zayıf)"}</span>`;
    }
    if (!best) return `<span class="tag tf-tag" title="Yeterli işlem yok">zaman dilimi ?</span>`;
    const m = periods[best] || {};
    const good = item.timeframe_edge === "üstün";
    const rows = ["15m", "1h", "4h", "1d"].filter((p) => periods[p])
      .map((p) => {
        const x = periods[p];
        const d = Number(x.diff || 0);
        return `${p}: ${fmt(x.return_pct, 1)}% (al-tut ${fmt(x.buy_hold_pct, 1)}%, fark ${d >= 0 ? "+" : ""}${fmt(d, 1)})`;
      }).join("\n");
    const title = `En iyi zaman dilimi: ${best}\n${rows}`;
    return `<span class="tag tf-tag ${good ? "green" : "amber"}" title="${esc(title)}">en iyi ${esc(best)}${good ? "" : " (zayıf)"}</span>`;
  };

  const customCard = (s) => {
    const def = s.definition || {};
    const isWrapper = !!def.builtin;
    const buy = isWrapper ? "Hazır motordan türetilmiş kopya" : groupText(def.buy);
    const sell = isWrapper ? "" : groupText(def.sell);
    return `<div class="strat-item ${s.status === "archived" ? "is-archived" : ""}">
      <div class="strat-item-main">
        <div class="row" style="gap:10px">
          <strong>${esc(s.name)}</strong>
          <span class="tag ${isWrapper ? "amber" : "green"}">${isWrapper ? "hazır kopya" : "özel"}</span>
          <span class="tag ${s.status === "active" ? "green" : "gray"}">${s.status === "active" ? "aktif" : "arşiv"}</span>
          <span class="tag gray">v${s.version}</span>
          ${tfBadge(s)}
        </div>
        <div class="strat-rules"><span class="rule-badge buy">AL</span> ${esc(buy || "—")}</div>
        ${sell ? `<div class="strat-rules"><span class="rule-badge sell">SAT</span> ${esc(sell)}</div>` : ""}
      </div>
      <div class="row">
        <button class="small primary" data-edit="${esc(s.id)}">Düzenle</button>
        <button class="small" data-bt="${esc(s.id)}" data-btkind="custom">Backtest</button>
        <button class="small ghost" data-dup="${esc(s.id)}">Kopyala</button>
        <button class="small ghost" data-arch="${esc(s.id)}">${s.status === "archived" ? "Aktifleştir" : "Arşivle"}</button>
        <button class="small danger" data-del="${esc(s.id)}" data-delname="${esc(s.name)}">Sil</button>
      </div>
    </div>`;
  };

  const builtinCard = (b) => `<div class="strat-item ${b.archived ? "is-archived" : ""}">
      <div class="strat-item-main">
        <div class="row" style="gap:10px">
          <strong>${esc(b.label || b.name)}</strong>
          <span class="tag gray">hazır</span>
          <span class="tag ${b.archived ? "gray" : "green"}">${b.archived ? "arşiv" : "aktif"}</span>
          ${b.label && b.label !== b.name ? `<span class="mono small muted">${esc(b.name)}</span>` : ""}
          ${tfBadge(b)}
        </div>
        <div class="strat-rules muted small">Kod tabanlı hazır motor · kuralları görsel düzenlenemez, kopyalayıp kullanabilirsin.</div>
      </div>
      <div class="row">
        <button class="small primary" data-bedt="${esc(b.name)}">Düzenle</button>
        <button class="small" data-bt="${esc(b.name)}" data-btkind="builtin">Backtest</button>
        <button class="small ghost" data-bdup="${esc(b.name)}">Kopyala</button>
        <button class="small ghost" data-barch="${esc(b.name)}">${b.archived ? "Aktifleştir" : "Arşivle"}</button>
      </div>
    </div>`;

  root.innerHTML = `
    <div class="row between">
      <div>
        <h1 style="font-size:24px;margin:0 0 4px">Stratejiler</h1>
        <p class="muted" style="margin:0">Hazır ve kendi stratejilerin tek listede; düzenle, backtest et, kopyala, arşivle veya sil.</p>
      </div>
      <div class="row">
        <button class="ghost" id="compare-strategies">Tümünü Karşılaştır</button>
        <button class="primary" id="new-strategy">+ Yeni Strateji</button>
      </div>
    </div>

    <div class="card mt">
      <div class="row between">
        <h3>Strateji kütüphanesi</h3>
        <div class="row small">
          <span class="tag green">${activeCustom} özel</span>
          <span class="tag gray">${activeBuiltin} hazır</span>
        </div>
      </div>
      <div class="strat-filter row mt">
        <button class="chip active" data-filter="all" type="button">Tümü</button>
        <button class="chip" data-filter="custom" type="button">Kendi stratejilerim</button>
        <button class="chip" data-filter="builtin" type="button">Hazır stratejiler</button>
        <button class="chip" data-filter="archived" type="button">Arşiv</button>
      </div>
      <div class="strat-list mt" id="strat-list">
        ${custom.map((s) => `<div data-kind="custom" data-archived="${s.status === "archived"}" class="${s.status === "archived" ? "hidden" : ""}">${customCard(s)}</div>`).join("")}
        ${builtin.map((b) => `<div data-kind="builtin" data-archived="${b.archived}" class="${b.archived ? "hidden" : ""}">${builtinCard(b)}</div>`).join("")}
      </div>
      ${custom.length + builtin.length ? "" : '<div class="empty-state">Henüz strateji yok. “Yeni Strateji” ile başla.</div>'}
    </div>

    <div class="card mt ind-note">
      <span class="muted small">
        <b>Hazır stratejiler</b> kod tabanlıdır: silinemez, <b>Arşivle</b> ile listeden gizlenir.
        <b>Kendi stratejilerin</b> ise <b>Sil</b> ile kalıcı olarak silinir (sürüm geçmişi ve
        backtest kayıtları dahil). Bir botun kullandığı strateji silinmek istendiğinde uyarı çıkar.
      </span>
    </div>`;

  $("#new-strategy").addEventListener("click", () => openStrategyEditor(null));
  $("#compare-strategies").addEventListener("click", () => openStrategyCompare());

  $$("[data-edit]").forEach((b) => b.addEventListener("click", () => openStrategyEditor(custom.find((s) => s.id === b.dataset.edit))));
  $$("[data-dup]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/strategies/custom/${b.dataset.dup}/duplicate`, { method: "POST" }); toast("Kopyalandı"); route(); }
    catch (e) { toast(e.message, true); }
  }));
  $$("[data-arch]").forEach((b) => b.addEventListener("click", async () => {
    const s = custom.find((x) => x.id === b.dataset.arch);
    try {
      await api(`/strategies/custom/${s.id}/${s.status === "archived" ? "activate" : "archive"}`, { method: "POST" });
      route();
    } catch (e) { toast(e.message, true); }
  }));
  $$("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.dataset.del;
    const name = b.dataset.delname || "Strateji";
    if (!confirm(`"${name}" kalıcı olarak silinsin mi?\n\nSürüm geçmişi ve backtest kayıtları da silinir. Bu işlem geri alınamaz.`)) return;
    const remove = async (force) => {
      await api(`/strategies/custom/${id}${force ? "?force=true" : ""}`, { method: "DELETE" });
      toast("Strateji silindi");
      route();
    };
    try {
      await remove(false);
    } catch (e) {
      if (String(e.message).includes("bot tarafından kullanılıyor")) {
        if (confirm(`${e.message}\n\nYine de silinsin mi? Bu botlar bu stratejiyle başlatılamaz.`)) {
          try { await remove(true); } catch (err) { toast(err.message, true); }
        }
      } else {
        toast(e.message, true);
      }
    }
  }));
  $$("[data-bt]").forEach((b) => {
    const kind = b.dataset.btkind || "custom";
    b.addEventListener("click", () => {
      if (kind === "builtin") {
        const item = builtin.find((x) => x.name === b.dataset.bt) || {};
        return openBacktest({ type: "builtin", name: b.dataset.bt },
          { bestTimeframe: item.best_timeframe, periods: item.timeframe_periods });
      }
      const s = custom.find((x) => x.id === b.dataset.bt);
      openBacktest({ type: "custom", id: b.dataset.bt, version: s ? s.version : undefined },
        { bestTimeframe: s && s.best_timeframe, periods: (s && s.timeframe_periods) || {} });
    });
  });
  $$("[data-bedt]").forEach((b) => b.addEventListener("click", () => openBuiltinEditor(b.dataset.bedt, builtin)));
  $$("[data-bdup]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/strategies/builtin/${encodeURIComponent(b.dataset.bdup)}/duplicate`, { method: "POST" }); toast("Kopyalandı"); route(); }
    catch (e) { toast(e.message, true); }
  }));
  $$("[data-barch]").forEach((b) => b.addEventListener("click", async () => {
    const item = builtin.find((x) => x.name === b.dataset.barch);
    try {
      await api(`/strategies/builtin/${encodeURIComponent(b.dataset.barch)}/archive`, {
        method: "POST", body: { archived: !(item && item.archived) },
      });
      toast(item && item.archived ? "Aktifleştirildi" : "Arşivlendi");
      route();
    } catch (e) { toast(e.message, true); }
  }));

  $$(".strat-filter [data-filter]").forEach((btn) => btn.addEventListener("click", () => {
    const filter = btn.dataset.filter;
    $$(".strat-filter [data-filter]").forEach((x) => x.classList.toggle("active", x === btn));
    $$("#strat-list > [data-kind]").forEach((wrap) => {
      const kind = wrap.dataset.kind;
      const archived = wrap.dataset.archived === "true";
      const show = filter === "all" ? !archived
        : filter === "archived" ? archived
        : kind === filter && !archived;
      wrap.classList.toggle("hidden", !show);
    });
  }));
}

function openWrapperEditor(existing) {
  const def = existing.definition || {};
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <p class="muted">Bu kayıt, <b>${esc(def.builtin)}</b> hazır motorundan türetilmiş bir kopyadır. Kuralları görsel olarak düzenlenemez; adını değiştirebilir, backtest edebilir veya arşivleyebilirsin.</p>
    ${field("Strateji adı", `<input id="we-name" value="${esc(existing.name)}" maxlength="80">`)}
    <div class="tool-note">Motor: <code>${esc(def.builtin)}</code> · sürüm v${esc(existing.version)}</div>
    <div class="row end mt">
      <button class="ghost" id="we-cancel" type="button">Vazgeç</button>
      <button class="primary" id="we-save" type="button">Adı kaydet</button>
    </div>`;
  modal("Strateji Kopyası", wrap);
  $("#we-cancel").addEventListener("click", closeModal);
  $("#we-save").addEventListener("click", async () => {
    try {
      const name = $("#we-name").value.trim() || existing.name;
      await api(`/strategies/custom/${existing.id}`, {
        method: "PUT",
        body: { definition: { ...def, name } },
      });
      closeModal(); toast("Kaydedildi"); route();
    } catch (e) { toast(e.message, true); }
  });
}

function openBuiltinEditor(name, builtin) {
  const item = (builtin || []).find((b) => b.name === name) || { name, label: name, archived: false };
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <p class="muted">Bu strateji <b>kod tabanlı</b> hazır bir motordur; görsel kural düzenleyicisiyle değiştirilemez. Görünen adını değiştirebilir veya kendi listene kopyalayabilirsin.</p>
    ${field("Görünen ad", `<input id="be-label" value="${esc(item.label || item.name)}" maxlength="80">`)}
    <div class="tool-note">Motor adı: <code>${esc(item.name)}</code></div>
    <div class="row end mt">
      <button class="ghost" id="be-copy" type="button">Kopyala</button>
      <button class="ghost" id="be-cancel" type="button">Vazgeç</button>
      <button class="primary" id="be-save" type="button">Adı kaydet</button>
    </div>`;
  modal("Hazır Strateji", wrap);
  $("#be-cancel").addEventListener("click", closeModal);
  $("#be-copy").addEventListener("click", async () => {
    try {
      await api(`/strategies/builtin/${encodeURIComponent(item.name)}/duplicate`, { method: "POST" });
      closeModal(); toast("Kopyalandı"); route();
    } catch (e) { toast(e.message, true); }
  });
  $("#be-save").addEventListener("click", async () => {
    try {
      await api(`/strategies/builtin/${encodeURIComponent(item.name)}/rename`, {
        method: "POST", body: { label: $("#be-label").value.trim() },
      });
      closeModal(); toast("Ad güncellendi"); route();
    } catch (e) { toast(e.message, true); }
  });
}

function openStrategyEditor(existing) {
  if (existing && existing.definition && existing.definition.builtin) {
    return openWrapperEditor(existing);
  }
  const draft = existing
    ? JSON.parse(JSON.stringify(existing.definition))
    : { name: "", buy: newGroup("AND"), sell: newGroup("OR") };
  if (!draft.buy) draft.buy = newGroup("AND");
  if (!draft.sell) draft.sell = newGroup("OR");
  if (!Array.isArray(draft.buy.conditions)) draft.buy.conditions = [];
  if (!Array.isArray(draft.sell.conditions)) draft.sell.conditions = [];

  const wrap = document.createElement("div");
  wrap.className = "strat-editor";
  wrap.innerHTML = `
    ${!existing ? `
      <div class="editor-section templates">
        <div class="section-head">
          <span class="step">0</span>
          <div><h4>Hazır şablonla başla</h4><p class="muted">Bir mantık seç, sonra istediğin gibi düzenle. Boş da başlayabilirsin.</p></div>
        </div>
        <div class="tpl-grid" id="tpl-grid"></div>
      </div>` : ""}

    <div class="editor-section">
      <div class="section-head">
        <span class="step">1</span>
        <div><h4>Strateji adı</h4><p class="muted">Bot listesinde görünecek isim.</p></div>
      </div>
      <div class="section-body">
        <input id="s-name" value="${esc(draft.name || "")}" placeholder="Örn. RSI Dip + EMA Trend">
      </div>
    </div>

    <div class="editor-section buy">
      <div class="section-head">
        <span class="step buy">2</span>
        <div><h4>Ne zaman AL?</h4><p class="muted">Bu kurallar sağlandığında bot alım yapar.</p></div>
      </div>
      <div class="section-body">
        <div class="rule-hint">Alt grup ekleyerek <b>(A ve B) veya (C ve D)</b> gibi karma kurallar kurabilirsin. Sağdaki değeri <b>Önceki mum</b> yaparak geçmiş mumla karşılaştırabilirsin. <b>Yukarı/Aşağı keser</b> bu mum ile önceki mumu birlikte kontrol eder.</div>
        <div id="buy-editor"></div>
        <div class="plain-summary buy" id="buy-summary"></div>
      </div>
    </div>

    <div class="editor-section sell">
      <div class="section-head">
        <span class="step sell">3</span>
        <div><h4>Ne zaman SAT?</h4><p class="muted">Pozisyon açıkken bu kurallar sağlandığında satar.</p></div>
      </div>
      <div class="section-body">
        <div class="rule-hint">Alt grup ekleyerek <b>(A ve B) veya (C ve D)</b> gibi karma kurallar kurabilirsin. Sağdaki değeri <b>Önceki mum</b> yaparak geçmiş mumla karşılaştırabilirsin. <b>Yukarı/Aşağı keser</b> bu mum ile önceki mumu birlikte kontrol eder.</div>
        <div id="sell-editor"></div>
        <div class="plain-summary sell" id="sell-summary"></div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">4</span>
        <div><h4>Test et</h4><p class="muted">Kaydetmeden önce son mumda ne olduğunu görebilirsin.</p></div>
      </div>
      <div class="section-body">
        <div class="row">
          <label class="pf"><span>Coin</span><input id="p-coin" value="BTCUSDT"></label>
          <label class="pf"><span>Periyot</span><select id="p-period">${["15m","1h","4h","1d"].map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select></label>
          <button id="s-preview" type="button">Son mumu dene</button>
          <button id="s-validate" type="button" class="ghost">Kuralları doğrula</button>
        </div>
        <div id="preview-result" class="mt"></div>
      </div>
    </div>

    <div class="editor-actions">
      <span id="save-hint" class="muted small"></span>
      <div class="row">
        <button class="ghost" id="s-cancel" type="button">Vazgeç</button>
        <button class="primary" id="s-save" type="button">${existing ? "Yeni sürüm kaydet" : "Stratejiyi kaydet"}</button>
      </div>
    </div>`;
  modal(existing ? "Strateji Düzenle" : "Yeni Strateji", wrap);

  const updateSummaries = () => {
    const buyEl = $("#buy-summary");
    const sellEl = $("#sell-summary");
    const buyText = groupText(draft.buy);
    const sellText = groupText(draft.sell);
    buyEl.innerHTML = `<span class="summary-label">AL</span><span class="summary-text">${esc(buyText || "Henüz kural yok — aşağıdan ekleyin.")}</span>`;
    sellEl.innerHTML = `<span class="summary-label">SAT</span><span class="summary-text">${esc(sellText || "Henüz kural yok — aşağıdan ekleyin.")}</span>`;
    const hint = $("#save-hint");
    const ready = draft.buy.conditions.length > 0 && draft.sell.conditions.length > 0;
    hint.textContent = ready ? "Hazır görünüyor." : "İpucu: en az bir alım ve bir satım kuralı ekleyin.";
  };

  const render = () => {
    const be = $("#buy-editor");
    be.innerHTML = "";
    be.appendChild(groupEditor(draft.buy, "buy", render, updateSummaries));

    const se = $("#sell-editor");
    se.innerHTML = "";
    se.appendChild(groupEditor(draft.sell, "sell", render, updateSummaries));
    updateSummaries();
  };
  render();

  if (!existing) {
    const grid = $("#tpl-grid");
    strategyTemplates().forEach((tpl) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "tpl-card";
      card.innerHTML = `<strong>${esc(tpl.title)}</strong><span>${esc(tpl.desc)}</span>`;
      card.addEventListener("click", () => {
        const built = tpl.build();
        draft.buy = built.buy;
        draft.sell = built.sell;
        if (!draft.name && built.name) {
          draft.name = built.name;
          $("#s-name").value = built.name;
        }
        render();
        toast(`${tpl.title} şablonu yüklendi`);
      });
      grid.appendChild(card);
    });
  }

  const definition = () => {
    draft.name = $("#s-name").value.trim() || "İsimsiz strateji";
    return draft;
  };

  $("#s-validate").addEventListener("click", async () => {
    try {
      const res = await api("/strategies/validate", { method: "POST", body: { definition: definition() } });
      $("#preview-result").innerHTML = res.valid
        ? `<div class="hint">Kurallar geçerli. Backtest için en az ${res.warmup} mum gerekir.</div>`
        : `<div class="error">${esc(res.errors.join("\n"))}</div>`;
    } catch (e) { toast(e.message, true); }
  });

  $("#s-preview").addEventListener("click", async () => {
    $("#preview-result").innerHTML = '<span class="muted">Hesaplanıyor…</span>';
    try {
      const res = await api("/strategies/preview", {
        method: "POST",
        body: { definition: definition(), coin: $("#p-coin").value.trim().toUpperCase(), period: $("#p-period").value },
      });
      $("#preview-result").innerHTML = previewHtml(res);
    } catch (e) { $("#preview-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });

  $("#s-cancel").addEventListener("click", closeModal);

  $("#s-save").addEventListener("click", async () => {
    try {
      const body = { definition: definition() };
      if (existing) await api(`/strategies/custom/${existing.id}`, { method: "PUT", body });
      else await api("/strategies/custom", { method: "POST", body });
      closeModal(); toast("Strateji kaydedildi"); route();
    } catch (e) { toast(e.message, true); }
  });
}

function previewHtml(res) {
  const r = res.result;
  const nodeBlock = (node, title, cls) => {
    if (!node) return `<div class="preview-block"><div class="preview-title">${esc(title)}</div><div class="muted small">Kural tanımlı değil.</div></div>`;
    const rows = (node.conditions || []).map((c) => {
      if (c.conditions) return `<div class="preview-nested">${nodeBlock(c, (c.logic || "AND"), cls)}</div>`;
      return `<div class="preview-row">
        <span class="mono small">${esc(c.left)} ${esc(c.op)} ${esc(c.right)}</span>
        <span class="muted small">${fmt(c.left_value, 6)} / ${fmt(c.right_value, 6)}</span>
        <span class="${c.result ? "tag green" : "tag red"}">${c.result ? "✓" : "✗"}</span>
      </div>`;
    }).join("") || '<div class="muted small">Kural yok.</div>';
    return `<div class="preview-block ${cls}">
      <div class="preview-title">${esc(title)} <span class="tag ${node.result ? "green" : "gray"}">${node.result ? "SAĞLANDI" : "SAĞLANMADI"}</span></div>
      ${rows}
    </div>`;
  };
  return `<div class="preview-card">
    <div class="row between"><strong>${esc(res.coin)} · ${esc(res.period)}</strong><span class="muted small">kapanmış mum: ${esc(fmtTime(r.candle_time))}</span></div>
    <div class="row mt">
      <span class="${r.buy ? "tag green" : "tag gray"}">ALIM ${r.buy ? "VAR" : "YOK"}</span>
      <span class="${r.sell ? "tag red" : "tag gray"}">SATIM ${r.sell ? "VAR" : "YOK"}</span>
      <span class="muted small">${res.candles} mumdan ${res.warmup} tanesi ısınma için kullanıldı</span>
    </div>
    <div class="split mt">
      ${nodeBlock(r.buy_detail, "Alım kuralları", "buy")}
      ${nodeBlock(r.sell_detail, "Satım kuralları", "sell")}
    </div>
  </div>`;
}

function openBacktest(spec, info = {}) {
  const best = info.bestTimeframe || null;
  const periods = info.periods || {};
  const selected = best || "1h";
  const summary = ["15m", "1h", "4h", "1d"].filter((p) => periods[p]).map((p) => {
    const x = periods[p];
    const d = Number(x.diff || 0);
    return `<span class="tag ${p === best ? "green" : "gray"}">${p}: ${fmt(x.return_pct, 1)}% <small>(${d >= 0 ? "+" : ""}${fmt(d, 1)})</small></span>`;
  }).join(" ");
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="row">
      ${field("Coin", `<input id="bt-coin" value="BTCUSDT">`)}
      ${field("Periyot", `<select id="bt-period">${["15m","1h","4h","1d"].map((p) => `<option ${p === selected ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
      ${field("Nakit", `<input id="bt-cash" type="number" value="100">`)}
      ${field("Mum sayısı", `<select id="bt-limit">${limitOptionsHtml(selected, 20000)}</select>`)}
      <button class="primary" id="bt-run">Çalıştır</button>
    </div>
    <div id="bt-estimate" class="muted small" style="margin:8px 0 0"></div>
    ${best ? `<div class="mt small">Ölçülen en iyi zaman dilimi: <b>${esc(best)}</b> ${summary}</div>` : ""}
    <p class="muted small" style="margin:8px 0 0">
      Trend stratejileri uzun geçmişte anlam kazanır. Kısa pencerede al-tut önde görünüyorsa
      daha uzun geçmiş seçin; yıllık tablo hangi yıllarda önde olduğunu gösterir.
      Çalıştırdıktan sonra <b>veri raporu</b> gerçekte kaç mum geldiğini, hangi tarih aralığını
      kapsadığını ve verinin temiz olup olmadığını gösterir.
    </p>
    <div id="bt-result" class="mt"></div>`;
  const estimate = () => {
    const lim = Number($("#bt-limit").value || 20000);
    const per = $("#bt-period").value;
    const el = $("#bt-estimate");
    if (el) el.innerHTML = `${lim.toLocaleString("tr-TR")} mum × ${esc(per)} → <b>${limitSpanLabel(lim, per)}</b>. Gerçek süre çalıştırınca veri raporunda görünür.`;
  };
  modal("Backtest", wrap);
  $("#bt-period").addEventListener("change", () => {
    refreshLimitOptions($("#bt-limit"), $("#bt-period").value);
    estimate();
  });
  $("#bt-limit").addEventListener("change", estimate);
  estimate();
  $("#bt-run").addEventListener("click", async () => {
    $("#bt-result").innerHTML = '<span class="muted">İş başlatıldı…</span>';
    try {
      const job = await api("/strategies/backtest", {
        method: "POST",
        body: {
          strategy: spec, coin: $("#bt-coin").value.trim().toUpperCase(),
          period: $("#bt-period").value, cash: Number($("#bt-cash").value),
          limit: Number($("#bt-limit").value || 20000),
        },
      });
      pollJob(job.id, (j) => { $("#bt-result").innerHTML = renderBacktest(j); });
    } catch (e) { $("#bt-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });
}

function renderBacktest(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") return `<span class="muted">Durum: ${esc(job.status)}…</span>`;
  const r = job.result || {};
  const m = r.metrics || {};
  const bh = r.buy_hold || null;
  const points = r.equity || [];
  const values = points.map((p) => Number(p.value)).filter((n) => Number.isFinite(n));
  const start = values.length ? values[0] : null;
  const end = values.length ? values[values.length - 1] : null;
  const change = start && end !== null && start !== 0 ? ((end - start) / start) * 100 : null;
  const count = Number(m.trade_count || 0);
  const rate = Number(m.win_rate || 0);
  const wins = Math.round((count * rate) / 100);
  const losses = Math.max(0, count - wins);

  const stratRet = Number(m.total_return_pct || 0);
  const bhRet = bh ? Number(bh.return_pct || 0) : 0;
  const diff = bh ? stratRet - bhRet : 0;
  const bhCurve = bh && bh.equity ? bh.equity.map((p) => Number(p.value)).filter((n) => Number.isFinite(n)) : [];
  const cagr = Number(m.cagr_pct || 0);
  const bhCagr = bh ? Number(bh.cagr_pct || 0) : 0;
  const calmar = m.calmar;
  const bhCalmar = bh ? bh.calmar : null;
  const yearly = Array.isArray(r.yearly) ? r.yearly : [];
  const winYears = yearly.filter((y) => y.diff > 0).length;
  const lossYears = yearly.filter((y) => y.diff < 0).length;

  const PERIOD_MS = { "15m": 9e5, "1h": 36e5, "4h": 144e5, "1d": 864e5 };
  const pms = PERIOD_MS[r.period] || 36e5;
  const toDays = (c) => (Number(c || 0) * pms) / 864e5;
  const holdFmt = (c) => {
    const d = toDays(c);
    if (d >= 1) return `${fmt(d, 1)} gün`;
    return `${fmt(d * 24, 1)} saat`;
  };
  const reasons = (r.risk && r.risk.exit_reasons) || {};
  const reasonLabels = { signal: "sinyal", time: "zaman limiti", stop: "stop", "takipli-stop": "takipli stop", trail: "takipli stop", "profit-exit": "kâr koruma", "take-profit": "kâr al", tp: "kâr al", end: "test sonu", manuel: "manuel satış", harici: "harici işlem" };
  const reasonText = Object.entries(reasons)
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${reasonLabels[k] || k}: ${n}`)
    .join(" · ") || "—";
  const riskOn = r.risk && (r.risk.stop_atr || r.risk.trail_atr || r.risk.take_profit_pct || r.risk.take_profit_atr || r.risk.profit_exit_donchian);  const holdBlock = m.trade_count ? `<div class="card mt">
    <div class="row between">
      <div>
        <h3 style="margin:0">Pozisyon süreleri</h3>
        <p class="muted small" style="margin:3px 0 0">
          ${riskOn ? `Risk kuralları: ${[
            r.risk.stop_atr ? `stop ${fmt(r.risk.stop_atr, 1)}×ATR` : "",
            r.risk.trail_atr ? `takipli stop ${fmt(r.risk.trail_atr, 1)}×ATR${r.risk.trail_after_pct ? ` (kâr >%${fmt(r.risk.trail_after_pct, 0)} sonrası)` : ""}` : "",
            r.risk.take_profit_pct ? `kâr al %${fmt(r.risk.take_profit_pct, 1)}` : "",
            r.risk.take_profit_atr ? `kâr al ${fmt(r.risk.take_profit_atr, 1)}×ATR` : "",
            r.risk.profit_exit_donchian ? `kâr koruma: Donchian(${r.risk.profit_exit_donchian}) kırılımı` : "",
            r.risk.cooldown ? `çıkış sonrası ${r.risk.cooldown} mum bekleme` : "",
          ].filter(Boolean).join(" · ")}` : "Risk kuralı yok — pozisyon yalnızca sinyalle kapanır."}
        </p>
      </div>
      <span class="muted small">çıkış nedenleri: ${esc(reasonText)}</span>
    </div>
    <div class="grid c3 mt">
      <div class="card"><h3>Ortalama tutuş</h3><div class="stat small">${holdFmt(m.avg_hold_candles)}</div><div class="muted">${fmt(m.avg_hold_candles, 1)} mum</div></div>
      <div class="card"><h3>Medyan tutuş</h3><div class="stat small">${holdFmt(m.median_hold_candles)}</div><div class="muted">${fmt(m.median_hold_candles, 1)} mum</div></div>
      <div class="card"><h3>En uzun tutuş</h3><div class="stat small">${holdFmt(m.max_hold_candles)}</div><div class="muted">${m.max_hold_candles} mum</div></div>
    </div>
  </div>` : "";

  // --- Fiyat grafiği + numaralı işlem işaretleri ---
  const markers = Array.isArray(r.markers) ? r.markers : [];
  const priceSeries = Array.isArray(r.price_series) ? r.price_series : [];
  const fullLo = priceSeries.length ? Number(priceSeries[0].idx) : 0;
  const fullHi = priceSeries.length ? Number(priceSeries[priceSeries.length - 1].idx) : 0;
  if (markers.length && priceSeries.length) {
    window.__btData = {
      markers,
      price: priceSeries,
      fullLo,
      fullHi,
      lo: fullLo,
      hi: fullHi,
      label: `${r.coin || ""} ${r.period || ""}`.trim(),
    };
  }
  const tradeCountShown = markers.length / 2;
  const usedReasons = Array.from(new Set(markers.filter((m) => m.side === "sell").map((m) => m.reason || "signal")));
  const legend = usedReasons.map((rs) => {
    const st = sellStyle(rs);
    return `<span class="legend-chip"><i style="background:${st.color}"></i>${esc(st.label)}</span>`;
  }).join("");
  const priceBlock = priceSeries.length && markers.length
    ? `<div class="card mt chart-card">
        <div class="row between" style="flex-wrap:wrap;gap:10px">
          <div>
            <h3 style="margin:0">Fiyat ve işlem noktaları</h3>
            <p class="muted small" style="margin:3px 0 0">
              <b>Fare tekerleği</b> ile yakınlaş, <b>sürükle</b> ile kaydır. Yakınlaşınca mumlar görünür.
              Yeşil ▲ = alım; ▼ rengi çıkış nedenini gösterir. Tablodaki satıra tıklayınca grafik o işleme odaklanır.
            </p>
            <div class="chart-legend">
              <span class="legend-chip"><i style="background:#34d399"></i>alım</span>
              ${legend}
            </div>
          </div>
          <div class="row small" style="gap:8px;align-items:center">
            <span id="tc-info" class="muted">${tradeCountShown} işlem · tekerlekle yakınlaş, sürükleyerek kaydır</span>
            <button type="button" class="small ghost" onclick="window.tcZoom(1/1.7)" title="Yakınlaş">＋</button>
            <button type="button" class="small ghost" onclick="window.tcZoom(1.7)" title="Uzaklaş">−</button>
            <button type="button" class="small ghost" onclick="window.tcReset()" title="Tüm görünüm">Sıfırla</button>
          </div>
        </div>
        <div id="tc-wrap">${tradePriceChart(priceSeries, markers, { height: 380, lo: fullLo, hi: fullHi })}</div>
      </div>`
    : "";

  // Bakiye grafiği için işaretler (örnek değerine oturtulur)
  const eqMarkers = (() => {
    if (!markers.length || !points.length) return [];
    const sample = points.map((p) => Number(p.idx)).filter((v) => Number.isFinite(v));
    if (sample.length !== points.length) return [];
    const nearest = (target) => {
      let best = 0, bestD = Infinity;
      for (let i = 0; i < sample.length; i++) {
        const d = Math.abs(sample[i] - target);
        if (d < bestD) { bestD = d; best = i; }
      }
      return best;
    };
    return markers.map((mk) => ({ ...mk, idx: sample[nearest(Number(mk.idx))] }));
  })();

  // İşlem tablosu: grafikteki numaralarla aynı sırada (eskiden yeniye)
  const tradeTotal = Number((r.metrics && r.metrics.trade_count) || 0);
  const tradeList = r.trades || [];
  const firstNo = tradeTotal - tradeList.length + 1;
  const tradeRows = tradeList.map((t, i) => `<tr class="trade-row" onclick="window.tcFocus(${firstNo + i})" title="Grafikte göster">
      <td><span class="trade-no">${firstNo + i}</span></td>
      <td>${esc(fmtTime(t.entry_time))}</td>
      <td>${esc(fmtTime(t.exit_time))}</td>
      <td>${fmt(t.entry, 6)} → ${fmt(t.exit, 6)}</td>
      <td>${pct(t.pnl_pct)}</td>
      <td>${esc(holdFmt(t.candles))}</td>
      <td>${esc(reasonLabels[t.reason] || t.reason || "sinyal")}</td>
    </tr>`).reverse().join("");


  const dr = r.data_report || null;
  const dataBlock = dr ? (() => {
    const received = Number(dr.received || 0);
    const requested = Number(dr.requested || 0);
    const missing = Math.max(0, requested - received);
    const pct = requested ? Math.round((received / requested) * 100) : 100;
    const clean = !!dr.clean && Number(dr.gaps || 0) === 0;
    const cleanBits = [];
    if (Number(dr.nan_count || 0)) cleanBits.push(`${dr.nan_count} geçersiz fiyat`);
    if (Number(dr.bad_ohlc_count || 0)) cleanBits.push(`${dr.bad_ohlc_count} bozuk OHLC`);
    if (Number(dr.bad_price_count || 0)) cleanBits.push(`${dr.bad_price_count} kapanış aralık dışı`);
    if (Number(dr.gaps || 0)) cleanBits.push(`${dr.gaps} boşluk (${dr.missing_candles} mum eksik)`);
    if (Number(dr.duplicates_removed || 0)) cleanBits.push(`${dr.duplicates_removed} tekrar ayıklandı`);
    const status = clean
      ? `<span class="tag green">temiz</span>`
      : `<span class="tag amber">uyarı: ${esc(cleanBits.join(" · "))}</span>`;
    const completeTag = received >= requested
      ? `<span class="tag green">istek karşılandı</span>`
      : `<span class="tag amber">${missing} mum eksik</span>`;
    return `<div class="card mt data-card">
      <div class="row between">
        <div>
          <h3 style="margin:0">Veri raporu — gerçekte kaç mum geldi?</h3>
          <p class="muted small" style="margin:3px 0 0">
            İstediğiniz ${requested.toLocaleString("tr-TR")} mum · gelen <b>${received.toLocaleString("tr-TR")}</b> mum
            (${pct}%) · ${status} ${completeTag}
          </p>
        </div>
      </div>
      <div class="grid c4 mt">
        <div class="card"><h3>İstenen → Gelen</h3><div class="stat small">${requested.toLocaleString("tr-TR")} → ${received.toLocaleString("tr-TR")}</div><div class="muted">${dr.pages || 0} API isteği${Number(dr.duplicates_removed || 0) ? ` · ${dr.duplicates_removed} tekrar ayıklandı` : ""}</div></div>
        <div class="card"><h3>Veri aralığı</h3><div class="stat small">${esc(dr.span_text || "—")}</div><div class="muted">${esc(dr.first || "—")} → ${esc(dr.last || "—")}</div></div>
        <div class="card"><h3>Test edilen aralık</h3><div class="stat small">${esc(dr.backtest_span_text || "—")}</div><div class="muted">${esc(dr.backtest_start || "—")} → ${esc(dr.backtest_end || "—")}</div></div>
        <div class="card"><h3>Isınma (warmup)</h3><div class="stat small">${Number(r.warmup || 0).toLocaleString("tr-TR")}</div><div class="muted">indikatörler için ayrılan mum</div></div>
      </div>
      <p class="muted small" style="margin:10px 0 0">
        ${received.toLocaleString("tr-TR")} mumun ${Number(r.warmup || 0).toLocaleString("tr-TR")} tanesi ısınma,
        ${Number(dr.backtest_candles || 0).toLocaleString("tr-TR")} tanesi gerçek testte kullanıldı.
        ${Number(dr.gaps || 0) > 0
          ? `Aralıkta ${dr.gaps} boşluk var (toplam ${Number(dr.missing_candles || 0)} mum eksik); kapsama %${fmt(dr.coverage_pct, 2)}. Borsa kesintisi veya listeleme öncesi dönem olabilir.`
          : `Aralıkta eksik mum yok (kapsama %${fmt(dr.coverage_pct, 2)}).`}
      </p>
    </div>`;
  })() : "";

  const yearlyBlock = yearly.length ? `<div class="card mt">
    <div class="row between">
      <div>
        <h3 style="margin:0">Yıl bazında</h3>
        <p class="muted small" style="margin:3px 0 0">${winYears} yıl önde · ${lossYears} yıl geride</p>
      </div>
      <span class="muted small">strateji − al-tut</span>
    </div>
    <div class="result-scroll mt">
      <table>
        <thead><tr><th>Yıl</th><th>Strateji</th><th>Al ve tut</th><th>Fark</th></tr></thead>
        <tbody>${yearly.map((y) => `<tr>
          <td>${esc(y.year)}</td>
          <td class="${Number(y.strategy_pct) >= 0 ? "pos" : "neg"}">${fmt(y.strategy_pct, 1)}%</td>
          <td class="${Number(y.buy_hold_pct) >= 0 ? "pos" : "neg"}">${fmt(y.buy_hold_pct, 1)}%</td>
          <td class="${Number(y.diff) >= 0 ? "pos" : "neg"}">${Number(y.diff) >= 0 ? "+" : ""}${fmt(y.diff, 1)}</td>
        </tr>`).join("")}</tbody>
      </table>
    </div>
    <p class="muted small" style="margin:8px 0 0">
      Trend takibi güçlü boğa yıllarında al-tut'un gerisinde kalır; sert düşüş yıllarında
      büyük fark atar. Bu yüzden tek bir yıl değil, tüm geçmiş ve düşüş derinliği birlikte okunmalı.
    </p>
  </div>` : "";

  const verdict = !bh ? "" : diff > 0
    ? `<span class="bh-verdict pos">Strateji, al-tut'tan ${fmt(Math.abs(diff), 2)} puan daha iyi</span>`
    : diff < 0
      ? `<span class="bh-verdict neg">Al-tut, stratejiden ${fmt(Math.abs(diff), 2)} puan daha iyi</span>`
      : `<span class="bh-verdict">İkisi de aynı sonucu verdi</span>`;

  return `<div class="grid c4">
    <div class="card"><h3>İşlem</h3><div class="stat small">${count}</div><div class="muted">${wins} kârlı · ${losses} zararlı</div></div>
    <div class="card"><h3>Strateji getirisi</h3><div class="stat small ${stratRet >= 0 ? "pos" : "neg"}">${fmt(stratRet, 2)}%</div><div class="muted">${r.candles || 0} mum</div></div>
    <div class="card"><h3>Al-tut getirisi</h3><div class="stat small ${bhRet >= 0 ? "pos" : "neg"}">${bh ? fmt(bhRet, 2) + "%" : "—"}</div><div class="muted">hiç satmasaydım</div></div>
    <div class="card"><h3>Maks. düşüş</h3><div class="stat small neg">${fmt(m.max_drawdown_pct, 2)}%</div><div class="muted">al-tut ${bh ? fmt(bh.max_drawdown_pct, 2) + "%" : "—"}</div></div>
  </div>

  <div class="grid c3 mt">
    <div class="card"><h3>Yıllık bileşik (CAGR)</h3><div class="stat small ${cagr >= 0 ? "pos" : "neg"}">${fmt(cagr, 1)}%</div><div class="muted">al-tut ${bh ? fmt(bhCagr, 1) + "%" : "—"}</div></div>
    <div class="card"><h3>Calmar (CAGR / düşüş)</h3><div class="stat small ${Number(calmar) >= Number(bhCalmar) ? "pos" : "neg"}">${calmar === null || calmar === undefined ? "—" : fmt(calmar, 2)}</div><div class="muted">al-tut ${bhCalmar === null || bhCalmar === undefined ? "—" : fmt(bhCalmar, 2)} · yüksek = daha iyi</div></div>
    <div class="card"><h3>Kâr faktörü</h3><div class="stat small">${m.profit_factor ? fmt(m.profit_factor, 2) : "—"}</div><div class="muted">kazanç / kayıp</div></div>
  </div>

  ${holdBlock}

  ${bh ? `<div class="card bh-card mt">
    <div class="row between bh-head">
      <div>
        <h3 style="margin:0">Al ve tut karşılaştırması</h3>
        <p class="muted small" style="margin:3px 0 0">
          Başlangıçta ${fmt(bh.start_price, 4)} → bitiş ${fmt(bh.end_price, 4)} ·
          ${bh.candles} mum · komisyon ve kayma dahil
        </p>
      </div>
      ${verdict}
    </div>
    <div class="bh-grid">
      <div class="bh-box">
        <span class="muted">Strateji</span>
        <b class="${stratRet >= 0 ? "pos" : "neg"}">${fmt(stratRet, 2)}%</b>
        <small>son bakiye ${fmt(r.final_cash || 0, 2)} USDT</small>
      </div>
      <div class="bh-box">
        <span class="muted">Al ve tut</span>
        <b class="${bhRet >= 0 ? "pos" : "neg"}">${fmt(bhRet, 2)}%</b>
        <small>son değer ${fmt(bh.final_value, 2)} USDT</small>
      </div>
      <div class="bh-box">
        <span class="muted">Fark</span>
        <b class="${diff >= 0 ? "pos" : "neg"}">${diff >= 0 ? "+" : ""}${fmt(diff, 2)} puan</b>
        <small>strateji − al-tut</small>
      </div>
      <div class="bh-box">
        <span class="muted">Al-tut düşüşü</span>
        <b class="neg">${fmt(bh.max_drawdown_pct, 2)}%</b>
        <small>tepe → dip</small>
      </div>
    </div>
  </div>` : ""}

  ${dataBlock}

  ${yearlyBlock}

  ${priceBlock}

  <div class="dash-grid mt">
    <div class="card chart-card">
      <div class="row between">
        <div>
          <h3>Bakiye eğrisi</h3>
          <p class="muted small">${points.length} örnek${bhCurve.length ? " · gri kesikli çizgi = al-tut" : ""} · ▲ AL / ▼ SAT işaretleri</p>
        </div>
        <span class="chart-big ${change === null ? "" : change >= 0 ? "pos" : "neg"}">${change === null ? "—" : `${change >= 0 ? "+" : ""}${fmt(change, 2)}%`}</span>
      </div>
      ${lineChart(values, { height: 220, includeZero: false, compare: bhCurve, markers: eqMarkers, points, caption: start === null ? "" : `başlangıç ${fmt(start, 2)}` })}
    </div>
    <div class="card chart-card">
      <h3>Kazanma oranı</h3>
      <p class="muted small">Backtest işlem dağılımı</p>
      ${donutChart([
        { label: "Kârlı", value: wins, color: "#34d399", display: wins },
        { label: "Zararlı", value: losses, color: "#fb7185", display: losses },
      ], { center: `${rate}%`, sub: "kazanma oranı" })}
    </div>
  </div>
  <div class="card mt"><h3>İşlemler <span class="muted small">(grafikteki numaralarla aynı)</span></h3>
    <div class="result-scroll"><table class="trade-table"><thead><tr><th>#</th><th>Giriş</th><th>Çıkış</th><th>Fiyat</th><th>K/Z</th><th>Süre</th><th>Çıkış nedeni</th></tr></thead><tbody>
    ${tradeRows || '<tr><td colspan="7" class="muted">İşlem yok</td></tr>'}
  </tbody></table></div></div>`;
}

/* ------------------------------------------------------------------ */
/* Tüm stratejileri karşılaştırma                                      */
/* ------------------------------------------------------------------ */
const CMP_COLUMNS = [
  { key: "name", label: "Strateji" },
  { key: "return_pct", label: "Getiri %", num: true },
  { key: "buy_hold_pct", label: "Al-tut %", num: true },
  { key: "diff", label: "Fark", num: true },
  { key: "drawdown_pct", label: "Düşüş %", num: true },
  { key: "calmar", label: "Calmar", num: true },
  { key: "trades", label: "İşlem", num: true },
  { key: "win_rate", label: "Kazanma %", num: true },
];

function openStrategyCompare() {
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="row">
      ${field("Coin", `<input id="cmp-coin" value="BTCUSDT">`)}
      ${field("Periyot", `<select id="cmp-period">${["15m","1h","4h","1d"].map((p) => `<option ${p === "4h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
      ${field("Nakit", `<input id="cmp-cash" type="number" value="100">`)}
      ${field("Mum sayısı", `<select id="cmp-limit">${limitOptionsHtml("4h", 20000)}</select>`)}
      <button class="primary" id="cmp-run">Karşılaştır</button>
    </div>
    <div id="cmp-estimate" class="muted small" style="margin:8px 0 0"></div>
    <p class="muted small" style="margin:8px 0 0">
      Tüm hazır ve özel stratejiler aynı fiyat serisiyle backtest edilir. Tablo <b>al-tut'a göre farka</b>
      göre sıralanır; sütun başlığına tıklayarak sıralamayı değiştirebilirsin. Bir strateji satırına
      tıklayınca o stratejinin tam backtest raporu (grafik, işlemler, yıl tablosu) açılır.
    </p>
    <div id="cmp-result" class="mt"></div>`;
  state.compare = null;
  state.cmpSort = { key: "diff", dir: -1 };
  modal("Tüm Stratejiler — Karşılaştırma", wrap);
  const updateEstimate = () => {
    const lim = Number($("#cmp-limit").value || 20000);
    const per = $("#cmp-period").value;
    const el = $("#cmp-estimate");
    if (el) el.innerHTML = `${lim.toLocaleString("tr-TR")} mum × ${esc(per)} → <b>${limitSpanLabel(lim, per)}</b>. Gerçek aralık sonuç başlığında tarihlerle görünür.`;
  };
  $("#cmp-period").addEventListener("change", () => {
    refreshLimitOptions($("#cmp-limit"), $("#cmp-period").value);
    updateEstimate();
  });
  $("#cmp-limit").addEventListener("change", updateEstimate);
  updateEstimate();
  $("#cmp-run").addEventListener("click", async () => {
    const meta = {
      coin: $("#cmp-coin").value.trim().toUpperCase() || "BTCUSDT",
      period: $("#cmp-period").value,
      cash: Number($("#cmp-cash").value) || 100,
      limit: Number($("#cmp-limit").value) || 20000,
    };
    $("#cmp-result").innerHTML = '<span class="muted">Karşılaştırma başlatıldı...</span>';
    try {
      const job = await api("/strategies/backtest-all", { method: "POST", body: meta });
      pollJob(job.id, (j) => {
        if (j.status === "done") {
          const res = j.result || {};
          state.compare = { meta, rows: res.rows || [], info: res };
          state.cmpSort = { key: "diff", dir: -1 };
          renderCompare();
        } else {
          const el = $("#cmp-result");
          if (el) el.innerHTML = `<span class="muted">${esc(j.message || j.status)}${j.progress ? ` · %${j.progress}` : ""}...</span>`;
        }
      });
    } catch (e) { $("#cmp-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });
}

function compareSortedRows() {
  const sort = state.cmpSort || { key: "diff", dir: -1 };
  const rows = ((state.compare && state.compare.rows) || []).slice();
  rows.sort((a, b) => {
    const av = a[sort.key];
    const bv = b[sort.key];
    if (typeof av === "number" || typeof bv === "number") {
      const an = typeof av === "number" ? av : -Infinity;
      const bn = typeof bv === "number" ? bv : -Infinity;
      return (an - bn) * (sort.dir < 0 ? -1 : 1);
    }
    return String(av || "").localeCompare(String(bv || ""), "tr") * (sort.dir < 0 ? -1 : 1);
  });
  return rows;
}

function compareHtml() {
  const info = (state.compare && state.compare.info) || {};
  const rows = compareSortedRows();
  const sort = state.cmpSort || { key: "diff", dir: -1 };
  const dr = info.data_report || {};
  const fetched = Number(info.candles || 0);
  const spanText = dr.backtest_span_text || limitSpanLabel(info.limit || fetched, info.period).replace(/^≈ /, "");
  const head = CMP_COLUMNS.map((c) => `<th class="${c.num ? "num " : ""}sortable" data-sort="${c.key}">${esc(c.label)}${sort.key === c.key ? (sort.dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("");
  const sign = (v) => (Number(v) > 0 ? "cmp-pos" : Number(v) < 0 ? "cmp-neg" : "");
  const winners = rows.filter((r) => !r.error && Number(r.diff) > 0).length;
  const body = rows.map((r, i) => {
    if (r.error) {
      return `<tr><td class="num">${i + 1}</td><td><strong>${esc(r.name)}</strong></td><td colspan="8" class="error-inline">${esc(r.error)}</td></tr>`;
    }
    return `<tr class="cmp-row" data-cmp-detail="${esc(r.key)}">
      <td class="num">${i + 1}</td>
      <td>
        <div class="row" style="gap:8px">
          <strong>${esc(r.name)}</strong>
          <span class="tag ${r.kind === "custom" ? "green" : "gray"}">${r.kind === "custom" ? "özel" : "hazır"}</span>
          ${r.best_timeframe ? `<span class="tag tf-tag">en iyi ${esc(r.best_timeframe)}</span>` : ""}
        </div>
        ${r.kind === "builtin" && r.motor !== r.name ? `<span class="mono small muted">${esc(r.motor)}</span>` : ""}
      </td>
      <td class="num ${sign(r.return_pct)}">${fmt(r.return_pct, 1)}</td>
      <td class="num">${fmt(r.buy_hold_pct, 1)}</td>
      <td class="num ${sign(r.diff)}">${Number(r.diff) > 0 ? "+" : ""}${fmt(r.diff, 1)}</td>
      <td class="num">${fmt(r.drawdown_pct, 1)}</td>
      <td class="num">${r.calmar == null ? "—" : fmt(r.calmar, 2)}</td>
      <td class="num">${r.trades}</td>
      <td class="num">${fmt(r.win_rate, 1)}</td>
      <td class="cmp-go" title="Detaylı backtest">›</td>
    </tr>`;
  }).join("");
  return `
    <div class="row between">
      <div class="row small">
        <span class="tag blue">${rows.length} strateji</span>
        <span class="tag ${winners ? "green" : "gray"}">${winners} tanesi al-tut'u geçti</span>
        <span class="tag gray">${esc(info.coin || "")} · ${esc(info.period || "")}</span>
        <span class="tag gray" title="Çekilen toplam mum">${fetched.toLocaleString("tr-TR")} mum çekildi</span>
        <span class="tag gray" title="Testte kullanılan gerçek zaman aralığı">test ≈ ${esc(spanText)}</span>
        ${dr.backtest_start ? `<span class="tag gray">${esc(dr.backtest_start)} → ${esc(dr.backtest_end)}</span>` : ""}
      </div>
      <button class="ghost small" id="cmp-new" type="button">Yeni karşılaştırma</button>
    </div>
    <div class="result-scroll mt"><table class="result-table cmp-table">
      <thead><tr><th class="num">#</th>${head}<th></th></tr></thead>
      <tbody>${body || '<tr><td colspan="10" class="muted">Sonuç yok</td></tr>'}</tbody>
    </table></div>`;
}

function renderCompare() {
  const body = $("#modal-body");
  if (!body || !state.compare) return;
  $("#modal-title").textContent = "Tüm Stratejiler — Karşılaştırma";
  body.innerHTML = compareHtml();
  $$("#modal-body th.sortable").forEach((th) => th.addEventListener("click", () => {
    const key = th.dataset.sort;
    const cur = state.cmpSort || { key: "diff", dir: -1 };
    state.cmpSort = { key, dir: cur.key === key ? -cur.dir : (key === "name" ? 1 : -1) };
    renderCompare();
  }));
  $$("#modal-body tr[data-cmp-detail]").forEach((tr) => tr.addEventListener("click", () => {
    const row = (state.compare.rows || []).find((r) => r.key === tr.dataset.cmpDetail);
    if (row) openCompareDetail(row);
  }));
  const fresh = $("#cmp-new");
  if (fresh) fresh.addEventListener("click", () => openStrategyCompare());
}

async function openCompareDetail(row) {
  const meta = (state.compare && state.compare.meta) || { coin: "BTCUSDT", period: "1h", cash: 100, limit: 20000 };
  const body = $("#modal-body");
  $("#modal-title").textContent = "Backtest — " + row.name;
  body.innerHTML = `
    <div class="row between">
      <button class="ghost small" id="cmp-back" type="button">← Karşılaştırmaya dön</button>
      <span class="muted small">${esc(meta.coin)} · ${esc(meta.period)} · ${Number(meta.limit).toLocaleString("tr-TR")} mum ${esc(limitSpanLabel(meta.limit, meta.period))}</span>
    </div>
    <div id="cmp-detail" class="mt"><span class="muted">Backtest başlatıldı...</span></div>`;
  $("#cmp-back").addEventListener("click", () => renderCompare());
  try {
    const job = await api("/strategies/backtest", {
      method: "POST",
      body: { strategy: row.spec, coin: meta.coin, period: meta.period, cash: meta.cash, limit: meta.limit },
    });
    pollJob(job.id, (j) => {
      const el = $("#cmp-detail");
      if (el) el.innerHTML = renderBacktest(j);
    });
  } catch (e) {
    const el = $("#cmp-detail");
    if (el) el.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function pollJob(jobId, onUpdate) {
  clearInterval(state.jobTimer);
  const tick = async () => {
    try {
      const job = await api(`/analysis/jobs/${jobId}`);
      onUpdate(job);
      if (["done", "error", "cancelled"].includes(job.status)) clearInterval(state.jobTimer);
    } catch (e) { clearInterval(state.jobTimer); toast(e.message, true); }
  };
  tick();
  state.jobTimer = setInterval(tick, 1500);
}

/* ------------------------------------------------------------------ */
/* Coin listeleri                                                      */
/* ------------------------------------------------------------------ */
function parseCoins(text) {
  return String(text || "")
    .split(/[\s,;]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}

async function renderLists(root) {
  const lists = await api("/coin-lists");
  let selected = lists.some((l) => l.id === state.coinListId) ? state.coinListId : (lists[0] ? lists[0].id : null);
  state.coinListId = selected;
  let creating = !lists.length;

  root.innerHTML = `
    <div class="lists-layout">
      <div class="card">
        <div class="row between">
          <h3 style="margin:0">Listeler</h3>
          <button class="primary small" id="list-new" type="button">Yeni liste</button>
        </div>
        <p class="muted small" style="margin:8px 0 10px">Bir kez oluştur; taramada ve bot formunda tek seçimle kullan. Hazır listeler salt-okunurdur, kopyalayıp düzenleyebilirsin.</p>
        <div class="list-nav" id="list-nav"></div>
      </div>
      <div class="card" id="list-detail"></div>
    </div>`;

  const renderNav = () => {
    $("#list-nav").innerHTML = lists.map((l) => `
      <button type="button" class="list-item ${l.id === selected ? "active" : ""}" data-id="${esc(l.id)}">
        <span class="list-item-name">${esc(l.name)}</span>
        <span class="list-item-meta">
          ${l.builtin ? '<span class="tag gray">hazır</span>' : ""}
          <span class="tag blue">${l.count}</span>
        </span>
      </button>`).join("");
    $$("#list-nav .list-item").forEach((b) => b.addEventListener("click", () => {
      selected = b.dataset.id;
      state.coinListId = selected;
      creating = false;
      renderNav();
      renderDetail();
    }));
  };

  const renderDetail = () => {
    const item = lists.find((l) => l.id === selected);
    const box = $("#list-detail");
    if (creating || !item) {
      box.innerHTML = `
        <h3>Yeni liste</h3>
        <p class="muted small" style="margin:8px 0 10px">Listeye bir ad ver; coinleri virgül veya boşlukla ayır.</p>
        ${field("Liste adı", `<input id="list-new-name" placeholder="Örn. Yüksek hacim">`)}
        <label class="pf wide mt"><span>Coinler</span><textarea id="list-new-coins" rows="6" placeholder="BTCUSDT, ETHUSDT, SOLUSDT"></textarea></label>
        <div class="row mt">
          <button class="primary" id="list-create" type="button">Listeyi oluştur</button>
          ${lists.length ? '<button class="ghost" id="list-cancel" type="button">Vazgeç</button>' : ""}
        </div>`;
      const cancel = $("#list-cancel");
      if (cancel) cancel.addEventListener("click", () => { creating = false; renderDetail(); });
      $("#list-create").addEventListener("click", async () => {
        try {
          const created = await api("/coin-lists", {
            method: "POST",
            body: { name: $("#list-new-name").value, coins: parseCoins($("#list-new-coins").value) },
          });
          toast("Liste oluşturuldu");
          state.coinListId = created.id;
          route();
        } catch (e) { toast(e.message, true); }
      });
      return;
    }
    const ro = item.builtin;
    box.innerHTML = `
      <div class="row between">
        <h3 style="margin:0">${esc(item.name)} ${ro ? '<span class="tag gray">hazır liste</span>' : '<span class="tag blue">özel</span>'}</h3>
        <span class="muted small">${item.count} coin</span>
      </div>
      <p class="muted small" style="margin:8px 0 10px">${ro
        ? "Hazır liste salt-okunurdur. Kopyalarsan kendi listene dönüştürüp düzenleyebilirsin."
        : "Bu listeyi taramada ve bot oluştururken seçebilirsin."}</p>
      ${field("Liste adı", `<input id="list-name" value="${esc(item.name)}" ${ro ? "disabled" : ""}>`)}
      <label class="pf wide mt"><span>Coinler (virgül veya boşlukla ayır)</span><textarea id="list-coins" rows="7" ${ro ? "disabled" : ""}>${esc(item.coins.join(", "))}</textarea></label>
      <div class="row mt">
        ${ro ? "" : '<button class="primary" id="list-save" type="button">Kaydet</button>'}
        <button class="ghost" id="list-dup" type="button">Kopyala</button>
        ${ro ? "" : '<button class="danger" id="list-del" type="button">Sil</button>'}
      </div>
      <div class="row mt">
        <button id="list-use-scan" type="button">Bu listeyle tara</button>
        <button id="list-use-bot" type="button">Bu listeyle bot oluştur</button>
      </div>`;

    const save = $("#list-save");
    if (save) save.addEventListener("click", async () => {
      try {
        await api(`/coin-lists/${item.id}`, {
          method: "PUT",
          body: { name: $("#list-name").value, coins: parseCoins($("#list-coins").value) },
        });
        toast("Liste kaydedildi");
        route();
      } catch (e) { toast(e.message, true); }
    });
    $("#list-dup").addEventListener("click", async () => {
      try {
        const copy = await api(`/coin-lists/${item.id}/duplicate`, { method: "POST", body: {} });
        toast("Liste kopyalandı");
        state.coinListId = copy.id;
        route();
      } catch (e) { toast(e.message, true); }
    });
    const del = $("#list-del");
    if (del) del.addEventListener("click", async () => {
      const ok = await confirmDialog("Listeyi sil", `“${item.name}” listesi silinsin mi? Bu listeyle kaydedilmiş botların coinleri etkilenmez.`, "Sil", true);
      if (!ok) return;
      try {
        await api(`/coin-lists/${item.id}`, { method: "DELETE" });
        toast("Liste silindi");
        state.coinListId = null;
        route();
      } catch (e) { toast(e.message, true); }
    });
    $("#list-use-scan").addEventListener("click", () => {
      state.scanListId = item.id;
      location.hash = "#scan";
    });
    $("#list-use-bot").addEventListener("click", () => {
      openBotForm(null, { coins: item.coins, coinListId: item.id });
    });
  };

  $("#list-new").addEventListener("click", () => { creating = true; renderNav(); renderDetail(); });
  renderNav();
  renderDetail();
}

/* ------------------------------------------------------------------ */
/* Tarama                                                              */
/* ------------------------------------------------------------------ */
async function renderScan(root) {
  const [builtin, custom, lists] = await Promise.all([
    api("/strategies/builtin"), api("/strategies/custom"), api("/coin-lists"),
  ]);
  const presetId = lists.some((l) => l.id === state.scanListId) ? state.scanListId : "";
  const preset = lists.find((l) => l.id === presetId);
  const opts = [
    ...builtin.filter((b) => !b.archived).map((b) => ({
      id: "builtin:" + b.name, name: b.label || b.name, spec: { type: "builtin", name: b.name },
    })),
    ...custom.filter((c) => c.status === "active").map((c) => ({ id: "custom:" + c.id, name: c.name, spec: { type: "custom", id: c.id, version: c.version } })),
  ];
  root.innerHTML = `
    <div class="card">
      <div class="row">
        ${field("Periyot", `<select id="scan-period">${["15m","1h","4h","1d"].map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
        ${field("Coin listesi", `<select id="scan-list">
          <option value="">— Tüm liste (coin_list.txt) —</option>
          ${lists.map((l) => `<option value="${esc(l.id)}" ${l.id === presetId ? "selected" : ""}>${esc(l.name)} (${l.count})</option>`).join("")}
        </select>`)}
        ${field("Coinler (boş = tüm liste)", `<input id="scan-coins" value="${preset ? esc(preset.coins.join(", ")) : ""}" placeholder="BTCUSDT, ETHUSDT">`)}
        <button class="primary" id="scan-run">Taramayı Başlat</button>
      </div>
      <p class="muted small" id="scan-list-hint" style="margin:8px 0 0"></p>
      <div class="card mt" style="padding:10px"><div class="muted">Stratejiler</div>
        ${opts.map((o) => `<label class="check"><input type="checkbox" class="scan-strategy" value="${o.id}" checked> ${esc(o.name)}</label>`).join("")}
      </div>
    </div>
    <div id="scan-result" class="mt"></div>`;
  const updateHint = () => {
    const found = lists.find((l) => l.id === $("#scan-list").value);
    $("#scan-list-hint").innerHTML = found
      ? `“${esc(found.name)}” seçili — ${found.count} coin taranacak. Coin alanından düzenleyebilirsin.`
      : 'Coin listesi seçersen yalnız o listenin coinleri taranır. Yeni liste için <a href="#lists">Coin Listeleri</a>.';
    return found;
  };
  updateHint();
  $("#scan-list").addEventListener("change", () => {
    state.scanListId = $("#scan-list").value;
    const found = updateHint();
    $("#scan-coins").value = found ? found.coins.join(", ") : "";
  });
  $("#scan-run").addEventListener("click", async () => {
    const specs = $$(".scan-strategy:checked").map((cb) => opts.find((o) => o.id === cb.value).spec);
    if (!specs.length) return toast("Strateji seçin", true);
    $("#scan-result").innerHTML = '<span class="muted">Tarama başlatıldı…</span>';
    try {
      const job = await api("/analysis/scan", {
        method: "POST",
        body: {
          period: $("#scan-period").value,
          strategies: specs,
          coins: $("#scan-coins").value.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean),
          list_id: $("#scan-list").value || null,
        },
      });
      pollJob(job.id, (j) => {
        $("#scan-result").innerHTML = renderScanResult(j);
        if (j.status === "done") bindScanResults();
      });
    } catch (e) { $("#scan-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });
}

function renderScanResult(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") return `<span class="muted">Durum: ${esc(job.status)}…</span>`;
  const r = job.result || {};
  const specs = (job.params && job.params.strategies) || [];
  const nameOf = (key) => {
    for (const spec of specs) {
      if (typeof spec === "string") { if (spec === key) return spec; continue; }
      const kind = spec.type || spec.kind;
      const id = kind === "builtin" ? (spec.name || spec.id) : spec.id;
      if (String(id) === String(key)) return spec.name || spec.id || key;
    }
    return key;
  };
  const raw = r.results || {};

  // Coin merkezli detay: aynı yapıyı dashboard ile paylaş.
  const coinMap = {};
  const strategies = [];
  let buyTotal = 0, sellTotal = 0;
  Object.keys(raw).forEach((key) => {
    const name = nameOf(key);
    const buys = (raw[key].BUY || []).map(String);
    const sells = (raw[key].SELL || []).map(String);
    buyTotal += buys.length;
    sellTotal += sells.length;
    strategies.push({ id: key, name, buy: buys, sell: sells, buy_count: buys.length, sell_count: sells.length });
    buys.forEach((coin) => {
      const e = coinMap[coin] || (coinMap[coin] = { coin, buy: [], sell: [], buy_count: 0, sell_count: 0 });
      if (!e.buy.includes(name)) e.buy.push(name);
      e.buy_count += 1;
    });
    sells.forEach((coin) => {
      const e = coinMap[coin] || (coinMap[coin] = { coin, buy: [], sell: [], buy_count: 0, sell_count: 0 });
      if (!e.sell.includes(name)) e.sell.push(name);
      e.sell_count += 1;
    });
  });
  const coins = Object.values(coinMap).sort((a, b) => (b.buy_count + b.sell_count) - (a.buy_count + a.sell_count) || a.coin.localeCompare(b.coin));

  return scanResultsHtml([{
    id: job.id,
    status: job.status,
    period: (job.params && job.params.period) || "",
    scanned: r.scanned || 0,
    created_at: job.created_at,
    finished_at: job.finished_at,
    error: null,
    strategies,
    coins,
    buy_total: buyTotal,
    sell_total: sellTotal,
    buy_coins: coins.filter((c) => c.buy_count).map((c) => c.coin),
    sell_coins: coins.filter((c) => c.sell_count).map((c) => c.coin),
  }]);
}

/* ------------------------------------------------------------------ */
/* Analiz                                                              */
/* ------------------------------------------------------------------ */
async function renderAnalysis(root) {
  const [builtin, custom] = await Promise.all([api("/strategies/builtin"), api("/strategies/custom")]);
  const opts = [
    ...builtin.filter((b) => !b.archived).map((b) => ({
      id: "builtin:" + b.name, name: b.label || b.name, spec: { type: "builtin", name: b.name },
    })),
    ...custom.filter((c) => c.status === "active").map((c) => ({ id: "custom:" + c.id, name: c.name, spec: { type: "custom", id: c.id, version: c.version } })),
  ];
  const periods = ["15m", "1h", "4h", "1d"];

  const tool = (icon, title, desc, body, action, job) => `
    <div class="tool-card">
      <div class="tool-head">
        <span class="tool-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icon}"/></svg></span>
        <div class="tool-title"><strong>${esc(title)}</strong><small>${esc(desc)}</small></div>
      </div>
      <div class="tool-body">${body}</div>
      <div class="tool-foot"><button class="primary" data-job="${job}" type="button">${esc(action)}</button></div>
    </div>`;

  root.innerHTML = `
    <div class="analysis-hero">
      <div>
        <span class="eyebrow">Analiz</span>
        <h2>Piyasa ve strateji analizi</h2>
        <p class="muted">İndikatör değerleri, destek/direnç, piyasa taraması ve strateji analizini tek yerden çalıştır.</p>
      </div>
      <div class="analysis-hero-badges">
        <span class="tag gray">${builtin.length} hazır strateji</span>
        <span class="tag ${custom.length ? "green" : "gray"}">${custom.length} özel strateji</span>
      </div>
    </div>

    <div class="analysis-section-head"><h3>Fiyat ve seviye</h3><span class="muted small">Tek coin üzerinde hesaplama</span></div>
    <div class="tool-grid">
      ${tool(
        "M3 17h2v4H3v-4Zm4-6h2v10H7V11Zm4-5h2v15h-2V6Zm4 8h2v7h-2v-7Zm4-9h2v16h-2V5Z",
        "İndikatör değerleri",
        "Seçili coin için son mumların indikatör tablosu.",
        `<div class="tool-fields">
          ${field("Coin", `<input id="an-coin" value="BTCUSDT">`)}
          ${field("Periyot", `<select id="an-period">${periods.map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
          ${field("Adet", `<input id="an-count" type="number" value="20" min="1" max="500">`)}
        </div>`,
        "Getir", "indicator_values")}
      ${tool(
        "M12 2 2 7l10 5 10-5-10-5Zm0 7.2L4.4 5.4 12 9.1l7.6-3.7L12 9.2ZM2 12l10 5 10-5v5l-10 5-10-5v-5Z",
        "Destek / Direnç",
        "Fiyatın altındaki destek ve üstündeki direnç seviyeleri.",
        `<div class="tool-fields">
          ${field("Coin", `<input id="sr-coin" value="BTCUSDT">`)}
          ${field("Periyot", `<select id="sr-period">${periods.map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
          ${field("Fiyat (boş = son)", `<input id="sr-price" type="number" step="any">`)}
        </div>`,
        "Hesapla", "support_resistance")}
      ${tool(
        "M7 2h10a2 2 0 0 1 2 2v18l-4-2-3 2-3-2-4 2V4a2 2 0 0 1 2-2Zm1 5v2h8V7H8Zm0 4v2h8v-2H8Z",
        "Aylık sonuç",
        "Coin'in ay bazında toplam getirisi ve yükseliş/düşüş günleri.",
        `<div class="tool-fields">
          ${field("Coin", `<input id="mo-coin" value="BTCUSDT">`)}
          ${field("Periyot", `<select id="mo-period">${["1d", "4h", "1h"].map((p) => `<option>${p}</option>`).join("")}</select>`)}
        </div>`,
        "Getir", "monthly")}
    </div>

    <div class="analysis-section-head"><h3>Piyasa</h3><span class="muted small">Tüm coin listesi üzerinde</span></div>
    <div class="tool-grid">
      ${tool(
        "M3 3h18v18H3V3Zm2 2v14h14V5H5Zm2 9 3-4 2.5 2.5L16 8l2 1.5-4.7 6.2-2.3-2.3L9 16l-2-2Z",
        "Piyasa durumu",
        "Seçili stratejilerle coinlerin ortalama sinyal durumu.",
        `<div class="tool-fields">
          ${field("Periyot", `<select id="mk-period">${periods.map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
          ${field("Maks coin", `<input id="mk-max" type="number" value="30" min="1">`)}
        </div>
        <div class="tool-checks">${opts.slice(0, 12).map((o) => `<label class="check"><input type="checkbox" class="mk-strategy" value="${o.id}"> ${esc(o.name)}</label>`).join("")}</div>`,
        "Analiz et", "market")}
      ${tool(
        "M4 4h16v2H4V4Zm0 5h16v2H4V9Zm0 5h10v2H4v-2Zm0 5h10v2H4v-2Z",
        "Coin listesi",
        "Borsadaki işlem gören coinleri listeler ve kaydeder.",
        `<div class="tool-fields">
          ${field("Periyot", `<select id="cl-period">${periods.map((p) => `<option ${p === "1h" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
        </div>
        <label class="check"><input type="checkbox" id="cl-sort"> Hacme göre sırala</label>`,
        "Oluştur", "coinlist")}
    </div>

    <div class="analysis-section-head"><h3>Strateji ve yapay zekâ</h3><span class="muted small">Toplu işler</span></div>
    <div class="tool-grid">
      ${tool(
        "M4 20h16v2H4v-2Zm1-3 4-6 3 3 5-7 2 1.5-6.4 9L9.6 14 6.6 18.5 5 17Z",
        "Strateji analizi",
        "Backtest sonuçlarını kaydeder ve strateji listesini günceller. Uzun sürebilir.",
        `<div class="tool-note">Tüm coin/periyot kombinasyonlarını tarar. Dashboard'daki <b>Aktif taramalar</b> kartından izleyip iptal edebilirsin.</div>`,
        "Backtest sonuçlarını kaydet", "strategy_results")}
      ${tool(
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v5.6l4 2.4-.9 1.5L11 13V7h2Z",
        "Strategys.json",
        "Mevcut strateji tanımlarını dosyaya yazar.",
        `<div class="tool-note">Strateji listesini yeniden oluşturur; mevcut kayıtları bozmaz.</div>`,
        "Oluştur", "strategy_analyze_save")}
      ${tool(
        "M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.3l-6-3.4V9.7Zm8 9.6V13l6-3.3v6.2l-6 3.4Z",
        "AI eğitimi",
        "Model test, veri seti ve hiperparametre işleri.",
        `<div class="tool-fields">
          ${field("Mod", `<select id="ai-mode"><option value="test">Modeli test et</option><option value="dataset">Veri seti oluştur</option><option value="random_search">Hiperparametre arama</option><option value="best_model">En iyi modeli eğit</option></select>`)}
        </div>
        <div class="tool-note">AI profili etkin değilse iş hata verir.</div>`,
        "AI işini başlat", "ai_train")}
    </div>

    <div id="analysis-result" class="mt"></div>`;
  $$("[data-job]").forEach((btn) => btn.addEventListener("click", () => runAnalysisJob(btn.dataset.job, opts, btn)));
}

function analysisProgressHtml(type, job, label) {
  const pct = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const live = job.status === "queued" || job.status === "running";
  const barPct = live ? Math.max(8, pct) : pct;
  const statusText = job.status === "queued" ? "Sırada bekliyor"
    : job.status === "running" ? "Çalışıyor"
    : job.status === "error" ? "Hata"
    : job.status === "cancelled" ? "İptal edildi" : "Tamamlandı";
  return `<div class="card job-progress">
    <div class="row between">
      <div class="row" style="gap:10px">
        <span class="job-live-dot ${job.status === "queued" || job.status === "running" ? "on" : "idle"}"></span>
        <strong>${esc(label || type)}</strong>
        <span class="muted small">${esc(statusText)}</span>
      </div>
      <span class="mono small">${pct}%</span>
    </div>
    <div class="job-bar mt"><span style="width:${barPct}%"></span></div>
    <p class="muted small" style="margin:8px 0 0">${esc(job.message && job.message !== statusText ? job.message : "Sonuç bekleniyor…")}</p>
  </div>`;
}

async function runAnalysisJob(type, opts, btn = null) {
  const LABELS = {
    indicator_values: "İndikatör değerleri",
    support_resistance: "Destek / direnç",
    market: "Piyasa analizi",
    monthly: "Aylık sonuç",
    coinlist: "Coin listesi",
    strategy_results: "Strateji sonuçları",
    strategy_analyze_save: "Strateji analizi",
    ai_train: "AI eğitimi",
  };
  const body = { coin: "BTCUSDT", period: "1h", count: 20, max_coins: 30 };
  if (type === "indicator_values") {
    body.coin = $("#an-coin").value.trim().toUpperCase(); body.period = $("#an-period").value;
    body.count = Number($("#an-count").value);
  } else if (type === "support_resistance") {
    body.coin = $("#sr-coin").value.trim().toUpperCase(); body.period = $("#sr-period").value;
    const price = $("#sr-price").value;
    body.price = price ? Number(price) : null;
  } else if (type === "market") {
    body.period = $("#mk-period").value; body.max_coins = Number($("#mk-max").value);
    body.strategies = $$(".mk-strategy:checked")
      .map((cb) => (opts.find((o) => o.id === cb.value) || {}).spec)
      .filter(Boolean);
    if (!body.strategies.length) return toast("En az bir strateji seçin", true);
  } else if (type === "monthly") {
    body.coin = $("#mo-coin").value.trim().toUpperCase(); body.period = $("#mo-period").value;
  } else if (type === "coinlist") {
    body.period = $("#cl-period").value; body.sort = $("#cl-sort").checked;
  } else if (type === "ai_train") {
    body.mode = $("#ai-mode").value;
  }
  const endpoint = {
    indicator_values: "/analysis/indicator-values",
    support_resistance: "/analysis/support-resistance",
    market: "/analysis/market",
    monthly: "/analysis/monthly",
    coinlist: "/analysis/coinlist",
    strategy_results: "/analysis/strategy-results",
    strategy_analyze_save: "/analysis/strategy-analyze-save",
    ai_train: "/analysis/ai-train",
  }[type];

  const result = $("#analysis-result");
  const oldLabel = btn ? btn.textContent : "";
  const restore = () => { if (btn) { btn.disabled = false; btn.textContent = oldLabel; } };
  if (btn) { btn.disabled = true; btn.textContent = "Çalışıyor…"; }
  result.innerHTML = analysisProgressHtml(type, { status: "queued", progress: 0, message: "İş oluşturuluyor…" }, LABELS[type]);
  result.scrollIntoView({ behavior: "smooth", block: "center" });

  try {
    const job = await api(endpoint, { method: "POST", body });
    if (job.status === "error") {
      result.innerHTML = `<div class="card"><div class="error">${esc(job.error || job.message || "İş başlatılamadı")}</div></div>`;
      toast(job.error || "İş başlatılamadı", true);
      restore();
      return;
    }
    const render = (j) => {
      if (j.status === "done") {
        result.innerHTML = renderAnalysisResult(type, j);
        restore();
      } else if (j.status === "error") {
        result.innerHTML = `<div class="card"><div class="error">${esc(j.error || j.message || "İş hatası")}</div></div>`;
        toast(j.message || "İş hatası", true);
        restore();
      } else if (j.status === "cancelled") {
        result.innerHTML = `<div class="card"><div class="muted">İş iptal edildi.</div></div>`;
        restore();
      } else {
        result.innerHTML = analysisProgressHtml(type, j, LABELS[type]);
      }
    };
    render(job);
    pollJob(job.id, render);
  } catch (e) {
    result.innerHTML = `<div class="card error">${esc(e.message)}</div>`;
    toast(e.message, true);
    restore();
  }
}

function analysisResultHeader(title, sub, actions = "") {
  return `<div class="result-head">
    <div>
      <h3 style="margin:0">${esc(title)}</h3>
      <p class="muted small" style="margin:3px 0 0">${esc(sub)}</p>
    </div>
    <div class="row">${actions}</div>
  </div>`;
}

function copyTableCsv(btn) {
  const card = btn.closest(".card");
  const table = card ? card.querySelector("table") : null;
  if (!table) return;
  const rows = Array.from(table.querySelectorAll("tr")).map((tr) =>
    Array.from(tr.children).map((cell) => `"${(cell.innerText || "").trim().replaceAll('"', '""')}"`).join(";")
  );
  const blob = new Blob(["\ufeff" + rows.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tradeai-analiz.csv";
  a.click();
  URL.revokeObjectURL(url);
  toast("CSV indirildi");
}

function renderAnalysisResult(type, job) {
  if (job.status === "error") return `<div class="card"><div class="error">${esc(job.error)}</div></div>`;
  if (job.status !== "done") return `<div class="card"><span class="muted">Durum: ${esc(job.status)}…</span></div>`;
  const r = job.result || {};
  const csvBtn = `<button class="ghost small" onclick="copyTableCsv(this)" type="button">CSV indir</button>`;

  if (type === "indicator_values") {
    const s = r.series || {};
    const columns = (r.columns && r.columns.length)
      ? r.columns
      : Object.keys(s).filter((k) => k !== "opendate").map((k) => ({
          id: k, indicator: k, label: k, output: k, category: "",
        }));

    // Başlıkları indikatöre göre grupla (ilk satır grup, ikinci satır çıktı).
    const groups = [];
    columns.forEach((c) => {
      const last = groups[groups.length - 1];
      if (last && last.indicator === c.indicator) last.span += 1;
      else groups.push({ indicator: c.indicator, label: c.label, category: c.category || "", span: 1 });
    });

    const catClass = (cat) => ({
      trend: "cat-trend", momentum: "cat-momentum",
      volatility: "cat-volatility", volume: "cat-volume",
    }[cat] || "cat-other");

    const stateBadge = (value) => {
      const map = {
        blue: ["hist-blue", "mavi"],
        red: ["hist-red", "kırmızı"],
        gray: ["hist-gray", "gri"],
        none: ["hist-none", "—"],
      };
      const [cls, label] = map[value] || ["hist-none", String(value)];
      return `<span class="hist-chip ${cls}">${esc(label)}</span>`;
    };

    const rows = (s.opendate || []).map((ts, i) => {
      const when = fmtTime(ts);
      const parts = when.split(" ");
      const dayPart = parts[0] || when;
      const timePart = parts[1] || "";
      return `<tr>
        <td class="mono sticky-col time-cell"><span class="t-date">${esc(dayPart)}</span><span class="t-time">${esc(timePart)}</span></td>
        ${columns.map((c) => {
          const value = s[c.id] ? s[c.id][i] : null;
          if (c.output === "hist_state") return `<td>${stateBadge(value)}</td>`;
          if (c.output === "direction") {
            const n = Number(value);
            const cls = n > 0 ? "dir-up" : n < 0 ? "dir-down" : "dir-flat";
            const glyph = n > 0 ? "\u25b2" : n < 0 ? "\u25bc" : "\u2013";
            return `<td><span class="dir-chip ${cls}">${glyph}</span></td>`;
          }
          return `<td>${fmt(value, 4)}</td>`;
        }).join("")}
      </tr>`;
    }).join("");

    const minWidth = 190 + columns.length * 88;
    return `<div class="card">
      ${analysisResultHeader(
        `${r.coin} · ${r.period}`,
        `Son ${s.opendate ? s.opendate.length : 0} mum · ${columns.length} sütun · ${groups.length} indikatör`,
        `${csvBtn}<button class="ghost small" onclick="document.querySelector('.result-scroll').scrollLeft=0" type="button">Başa dön</button>`
      )}
      <div class="ind-note">
        <span class="muted small">Başlıktaki renkli grup adı sütunun hangi indikatöre ait olduğunu gösterir. Tabloyu yatay kaydırabilirsin; tarih/saat sütunu sabit kalır.</span>
        <span class="ind-cats">
          <span class="ind-cat cat-trend">trend</span>
          <span class="ind-cat cat-momentum">momentum</span>
          <span class="ind-cat cat-volatility">volatilite</span>
          <span class="ind-cat cat-volume">hacim</span>
        </span>
      </div>
      ${columns.some((c) => c.indicator === "QQE_MOD") ? `<div class="qqe-legend">
        <span class="muted small"><b>QQE histogram</b></span>
        <span class="hist-chip hist-blue">mavi</span><span class="muted small">AL — ikincil RSI eşiği aştı ve birincil RSI üst bandın üzerinde</span>
        <span class="hist-chip hist-red">kırmızı</span><span class="muted small">SAT — alt bandın altında</span>
        <span class="hist-chip hist-gray">gri</span><span class="muted small">eşik aşıldı, onay yok</span>
        <span class="hist-chip hist-none">—</span><span class="muted small">eşik içinde (çizilmez)</span>
      </div>` : ""}
      <div class="result-scroll ind-scroll">
        <table class="result-table ind-table" style="min-width:${minWidth}px">
          <thead>
            <tr>
              <th class="sticky-col" rowspan="2">Tarih / Saat</th>
              ${groups.map((g) => `<th colspan="${g.span}" class="ind-group-head ${catClass(g.category)}">${esc(g.label)}</th>`).join("")}
            </tr>
            <tr>
              ${columns.map((c) => `<th class="ind-sub-head" title="${esc(c.indicator)} · ${esc(c.output)}">${esc(c.output)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }
  if (type === "support_resistance") {
    const levels = (r.levels || []).map((l) => `<span class="scan-chip">${fmt(l, 6)}</span>`).join("");
    return `<div class="card">
      ${analysisResultHeader(`${r.coin} destek / direnç`, `Fiyat ${fmt(r.price, 6)}`)}
      <div class="scan-kpis">
        <div class="scan-kpi buy"><span>Destek</span><b>${fmt(r.support, 4)}</b><small>en yakın alt seviye</small></div>
        <div class="scan-kpi sell"><span>Direnç</span><b>${fmt(r.resistance, 4)}</b><small>en yakın üst seviye</small></div>
        <div class="scan-kpi"><span>Seviye</span><b>${(r.levels || []).length}</b><small>hesaplanan</small></div>
      </div>
      <div class="scan-col mt"><div class="scan-col-head"><span class="muted small">Tüm seviyeler</span></div><div class="scan-chips">${levels || '<span class="scan-empty">Seviye yok</span>'}</div></div>
    </div>`;
  }
  if (type === "market") {
    const table = r.table || [];
    const avg = table.length ? table.reduce((sum, x) => sum + Number(x.average || 0), 0) / table.length : 0;
    const positive = table.filter((x) => Number(x.average) > 0).length;
    return `<div class="card">
      ${analysisResultHeader(`Piyasa durumu · ${r.period || ""}`, `${table.length} coin · ortalama sinyal ${fmt(avg, 2)}`, csvBtn)}
      <div class="scan-kpis">
        <div class="scan-kpi buy"><span>Pozitif</span><b>${positive}</b><small>coin</small></div>
        <div class="scan-kpi"><span>İncelenen</span><b>${table.length}</b><small>coin</small></div>
        <div class="scan-kpi"><span>Ortalama</span><b>${fmt(avg, 2)}</b><small>sinyal skoru</small></div>
      </div>
      <div class="result-scroll mt"><table class="result-table"><thead><tr><th>Coin</th><th>Ortalama</th></tr></thead><tbody>${table.map((x) => `<tr><td>${esc(x.coin)}</td><td>${fmt(x.average, 2)}</td></tr>`).join("")}</tbody></table></div>
    </div>`;
  }
  if (type === "monthly") {
    const names = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"];
    const rows = Object.entries(r.monthly || {});
    return `<div class="card">
      ${analysisResultHeader(`${r.coin} aylık sonuç`, `${rows.length} ay`, csvBtn)}
      <div class="result-scroll"><table class="result-table"><thead><tr><th>Ay</th><th>Toplam %</th><th>Yükseliş</th><th>Düşüş</th></tr></thead><tbody>${rows.map(([m, v]) => `<tr><td>${names[Number(m) - 1] || m}</td><td>${pct(v.sum)}</td><td>${v.up}</td><td>${v.down}</td></tr>`).join("")}</tbody></table></div>
    </div>`;
  }
  if (type === "coinlist") {
    return `<div class="card">
      ${analysisResultHeader("Coin listesi", `${r.count || 0} işlem gören coin`)}
      <div class="scan-chips mt">${(r.coins || []).map((c) => `<span class="scan-chip">${esc(c)}</span>`).join("")}</div>
    </div>`;
  }
  if (type === "buy_result") {
    return `<div class="card">${analysisResultHeader("Alım sonuçları", "buy_result.log özeti")}<pre>${esc(JSON.stringify(r.counts || {}, null, 2))}</pre></div>`;
  }
  if (type === "ai_train") {
    return `<div class="card">${analysisResultHeader("AI işi tamamlandı", "Ham çıktı")}<pre>${esc(JSON.stringify(r, null, 2))}</pre></div>`;
  }
  return `<div class="card">${analysisResultHeader("Sonuç", job.type || "")}<pre>${esc(JSON.stringify(r, null, 2))}</pre></div>`;
}

/* ------------------------------------------------------------------ */
/* İşlem geçmişi                                                       */
/* ------------------------------------------------------------------ */
async function renderTrades(root) {
  const [trades, summary, positions, stats] = await Promise.all([
    api("/trades?limit=200"), api("/summary"), api("/positions?status=open"), api("/stats"),
  ]);
  const total = summary.total || {};
  const t = stats.totals || {};
  const eq = (stats.equity || []).map((p) => p.value);
  const eqLast = eq.length ? eq[eq.length - 1] : null;
  const coinItems = (stats.by_coin || []).map((c) => ({ label: c.coin, value: c.pnl }));
  const daily = (stats.daily || []).slice(-14).map((d) => ({ label: (d.date || "").slice(5), value: d.pnl }));
  root.innerHTML = `
    <div class="grid c4">
      <div class="card"><h3>Toplam işlem</h3><div class="stat">${total.trades || 0}</div><div class="muted">kapanan işlem</div></div>
      <div class="card"><h3>Kârlı</h3><div class="stat">${total.wins || 0}</div><div class="muted">kazanan</div></div>
      <div class="card"><h3>Zararlı</h3><div class="stat">${total.losses || 0}</div><div class="muted">kaybeden</div></div>
      <div class="card"><h3>Açık pozisyon</h3><div class="stat">${positions.length}</div><div class="muted">takip ediliyor</div></div>
    </div>

    <div class="dash-grid mt">
      <div class="card chart-card">
        <div class="row between">
          <div><h3>Kümülatif K/Z</h3><p class="muted small">Kapanan işlemlerin bileşik getirisi</p></div>
          <span class="chart-big ${eqLast === null ? "" : eqLast >= 0 ? "pos" : "neg"}">${eqLast === null ? "—" : `${eqLast >= 0 ? "+" : ""}${fmt(eqLast, 2)}%`}</span>
        </div>
        ${lineChart(eq, { height: 220, caption: `${eq.length} kapanan işlem` })}
      </div>
      <div class="card chart-card">
        <h3>Kazanma oranı</h3>
        <p class="muted small">Kapanan işlemlerin dağılımı</p>
        ${donutChart([
          { label: "Kârlı", value: t.wins || 0, color: "#34d399", display: t.wins || 0 },
          { label: "Zararlı", value: t.losses || 0, color: "#fb7185", display: t.losses || 0 },
        ], { center: t.win_rate == null ? "—" : `${t.win_rate}%`, sub: "kazanma oranı" })}
      </div>
    </div>

    <div class="dash-grid2 mt">
      <div class="card chart-card">
        <div class="row between"><h3>Coin bazında K/Z</h3><span class="tag gray">%</span></div>
        ${barChart(coinItems, { height: 190 })}
      </div>
      <div class="card chart-card">
        <div class="row between"><h3>Günlük K/Z</h3><span class="tag gray">son 14 gün</span></div>
        ${barChart(daily, { height: 190 })}
      </div>
    </div>

    <div class="card mt">
      <div class="row between"><h3>İşlemler</h3><a class="small" href="/api/export.csv" target="_blank">CSV indir</a></div>
      <div style="overflow:auto"><table><thead><tr><th>Zaman</th><th>Bot</th><th>Coin</th><th>Yön</th><th>Adet</th><th>Fiyat</th><th>K/Z</th><th>Mod</th><th>Neden</th></tr></thead><tbody>
      ${trades.map((tr) => `<tr><td class="mono">${esc(fmtIso(tr.created_at))}</td><td>${esc(tr.bot_id || "—")}</td><td>${esc(tr.coin)}</td><td>${tr.side === "BUY" ? '<span class="tag green">AL</span>' : '<span class="tag red">SAT</span>'}</td><td>${fmt(tr.quantity, 8)}</td><td>${fmt(tr.price, 8)}</td><td>${tr.pnl_pct == null ? "—" : pct(tr.pnl_pct)}</td><td>${esc(tr.mode)}</td><td>${tradeReason(tr.reason)}</td></tr>`).join("") || '<tr><td colspan="9" class="muted">Henüz işlem yok.</td></tr>'}
      </tbody></table></div>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* Ayarlar                                                             */
/* ------------------------------------------------------------------ */
async function renderSettings(root) {
  const [settings, coinlist] = await Promise.all([api("/settings"), api("/settings/coinlist")]);
  const app = settings.app;
  const groups = settings.groups || [];

  const tabs = [
    ...groups.map((g) => ({ id: g.id, label: g.label })),
    { id: "coins", label: "Coin listesi" },
    { id: "security", label: "Güvenlik" },
  ];

  root.innerHTML = `
    <div class="card settings-hero">
      <div class="settings-hero-main">
        <span class="eyebrow">Canlı işlem</span>
        <h2>${app.live_unlocked ? "Canlı işlem açık" : "Canlı işlem kapalı"}</h2>
        <p class="muted">${app.live_unlocked
          ? "Canlı moda aldığın botlar gerçek emir gönderebilir. Kapatınca tüm canlı botlar güvenli şekilde durur."
          : "Tüm botlar test modunda çalışıyor. Gerçek emir gönderilmiyor."}</p>
        <div class="row mt">
          <button class="${app.live_unlocked ? "" : "primary"}" id="set-live" type="button">
            ${app.live_unlocked ? "Canlı işlemi kapat" : "Canlı işlemi aç"}
          </button>
          <span class="tag ${app.live_enabled ? "green" : "red"}">Sunucu izni ${app.live_enabled ? "açık" : "kapalı"}</span>
          <span class="tag ${app.live_unlocked ? "amber" : "gray"}">Panel anahtarı ${app.live_unlocked ? "açık" : "kapalı"}</span>
        </div>
      </div>
      <div class="settings-hero-side">
        <div class="hero-metric"><span>Varsayılan mod</span><b>${app.default_mode === "live" ? "Canlı" : "Test"}</b></div>
        <div class="hero-metric"><span>Varsayılan nakit</span><b>${money(app.default_cash)}</b></div>
        <div class="hero-metric"><span>Komisyon / kayma</span><b>${(app.paper_fee * 100).toFixed(2)}% / ${(app.paper_slippage * 100).toFixed(2)}%</b></div>
      </div>
    </div>

    <div class="settings-tabs" id="set-tabs">
      ${tabs.map((t, i) => `<button class="settings-tab ${i === 0 ? "active" : ""}" data-tab="${t.id}" type="button">${esc(t.label)}</button>`).join("")}
    </div>
    <div id="set-panel" class="settings-panel"></div>

    <div class="settings-savebar" id="set-savebar">
      <span class="muted small" id="set-hint">Değişiklikler kaydedilince anında uygulanır.</span>
      <div class="row">
        <button class="ghost" id="set-reset" type="button">Geri al</button>
        <button class="primary" id="set-save" type="button">Kaydet</button>
      </div>
    </div>`;

  let active = (state.settingsTab && tabs.some((t) => t.id === state.settingsTab)) ? state.settingsTab : tabs[0].id;

  const renderTab = (tabId) => {
    active = tabId;
    state.settingsTab = tabId;
    $$("#set-tabs .settings-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
    const panel = $("#set-panel");
    const savebar = $("#set-savebar");
    savebar.classList.toggle("hidden", tabId === "security");

    if (tabId === "coins") {
      panel.innerHTML = `
        <div class="card">
          <div class="row between"><h3>İzlenen coinler</h3><span class="muted small">Virgül veya satır ile ayır</span></div>
          <p class="muted small">Botlarda coin seçilmezse bu liste kullanılır. Değişiklikler yeni taramalarda geçerli olur.</p>
          <textarea id="cl-coins" class="mt" style="min-height:180px">${esc((coinlist.coins || []).join(", "))}</textarea>
          <div class="row mt"><button class="primary" id="cl-save" type="button">Coin listesini kaydet</button></div>
        </div>`;
      $("#cl-save").addEventListener("click", async () => {
        try {
          const coins = $("#cl-coins").value.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
          await api("/settings/coinlist", { method: "PUT", body: { coins } });
          toast("Coin listesi kaydedildi");
        } catch (e) { toast(e.message, true); }
      });
      return;
    }

    if (tabId === "security") {
      panel.innerHTML = `
        <div class="grid c2">
          <div class="card">
            <h3>Şifre değiştir</h3>
            ${field("Mevcut şifre", `<input id="pw-old" type="password" autocomplete="current-password">`)}
            ${field("Yeni şifre", `<input id="pw-new" type="password" autocomplete="new-password">`)}
            <button class="primary mt" id="pw-save" type="button">Şifreyi değiştir</button>
          </div>
          <div class="card danger-card">
            <h3>Tehlikeli işlemler</h3>
            <p class="muted">Bu işlemler gerçek hesapta emir gönderir. Dikkatli kullan.</p>
            ${field("Şifre", `<input id="dg-pass" type="password">`)}
            ${field("Onay metni", `<input id="dg-confirm" placeholder="KAPAT / NAKIT">`)}
            <div class="row">
              <button class="danger" data-danger="close-all" type="button">Tüm pozisyonları kapat</button>
              <button class="danger" data-danger="full-cash" type="button">Full nakite geç</button>
            </div>
          </div>
        </div>`;
      $("#pw-save").addEventListener("click", async () => {
        try {
          await api("/auth/change-password", { method: "POST", body: { current_password: $("#pw-old").value, new_password: $("#pw-new").value } });
          toast("Şifre değiştirildi"); $("#pw-old").value = ""; $("#pw-new").value = "";
        } catch (e) { toast(e.message, true); }
      });
      $$("[data-danger]").forEach((btn) => btn.addEventListener("click", async () => {
        const confirmText = prompt("Onay metnini yazın (KAPAT veya NAKIT):");
        if (!confirmText) return;
        const ok = await confirmDialog("Gerçek emir gönderilecek", "Bu işlem gerçek hesapta emir gönderir. Emin misin?", "Gönder", true);
        if (!ok) return;
        try {
          const res = await api(`/settings/danger/${btn.dataset.danger}`, {
            method: "POST",
            body: { password: $("#dg-pass").value, confirm: confirmText },
          });
          toast(`${res.results.length} işlem sonucu alındı`);
        } catch (e) { toast(e.message, true); }
      }));
      return;
    }

    const group = groups.find((g) => g.id === tabId);
    if (!group) return;
    panel.innerHTML = `
      <div class="card">
        <div class="settings-group-head">
          <div><h3>${esc(group.label)}</h3><p class="muted small">${esc(group.description || "")}</p></div>
        </div>
        <div class="settings-form">${group.items.map(settingsField).join("")}</div>
        ${settingsActions(tabId)}
      </div>`;

    $$("#set-panel [data-key]").forEach((el) => {
      el.addEventListener("input", () => $("#set-hint").textContent = "Kaydedilmemiş değişiklikler var.");
      el.addEventListener("change", () => $("#set-hint").textContent = "Kaydedilmemiş değişiklikler var.");
    });
    $$("#set-panel [data-clear]").forEach((btn) => btn.addEventListener("click", async () => {
      const ok = await confirmDialog("Gizli değeri kaldır", "Bu gizli değer silinecek. Devam edilsin mi?", "Kaldır", true);
      if (!ok) return;
      try {
        await api(`/settings/secret/${btn.dataset.clear}`, { method: "DELETE" });
        toast("Gizli değer kaldırıldı");
        route();
      } catch (e) { toast(e.message, true); }
    }));
    bindSettingsActions(tabId);
  };

  const collect = () => {
    const values = {};
    $$("#set-panel [data-key]").forEach((el) => {
      const key = el.dataset.key;
      const kind = el.dataset.kind;
      if (kind === "bool") values[key] = el.checked;
      else if (kind === "secret") { if (el.value.trim()) values[key] = el.value.trim(); }
      else if (kind === "int") values[key] = Number(el.value);
      else if (kind === "float") values[key] = Number(el.value);
      else values[key] = el.value;
    });
    return values;
  };

  const save = async () => {
    const values = collect();
    if (!Object.keys(values).length) { toast("Kaydedilecek değişiklik yok"); return; }
    const btn = $("#set-save");
    btn.disabled = true; btn.textContent = "Kaydediliyor...";
    try {
      const res = await api("/settings", { method: "PUT", body: { values } });
      toast(`${res.saved.length} ayar kaydedildi`);
      state.liveEnabled = !!res.live_enabled;
      const fresh = await api("/settings");
      state.liveUnlocked = !!fresh.app.live_unlocked;
      renderLiveToggle();
      route();
    } catch (e) {
      toast(e.message, true);
      btn.disabled = false; btn.textContent = "Kaydet";
    }
  };

  $("#set-save").addEventListener("click", save);
  $("#set-reset").addEventListener("click", () => route());
  $("#set-live").addEventListener("click", toggleLiveTrading);
  $$("#set-tabs .settings-tab").forEach((b) => b.addEventListener("click", () => renderTab(b.dataset.tab)));
  renderTab(active);
}

function settingsField(item) {
  const key = esc(item.key);
  const help = item.help ? `<small class="setting-help">${esc(item.help)}</small>` : "";
  if (item.kind === "bool") {
    return `<label class="setting-row">
      <span class="setting-text"><strong>${esc(item.label)}</strong>${help}</span>
      <span class="switch-wrap">
        <input type="checkbox" class="switch-input" data-key="${key}" data-kind="bool" ${item.value ? "checked" : ""}>
        <span class="switch"></span>
      </span>
    </label>`;
  }
  if (item.kind === "select") {
    return `<label class="setting-row">
      <span class="setting-text"><strong>${esc(item.label)}</strong>${help}</span>
      <select data-key="${key}" data-kind="select">
        ${item.options.map((o) => `<option value="${esc(o.value)}" ${o.value === item.value ? "selected" : ""}>${esc(o.label)}</option>`).join("")}
      </select>
    </label>`;
  }
  if (item.kind === "secret") {
    const badge = item.configured
      ? `<span class="tag green">kayıtlı · ${esc(item.preview || "••••")}</span>`
      : `<span class="tag gray">tanımsız</span>`;
    const clear = item.configured
      ? `<button type="button" class="ghost small secret-clear" data-clear="${key}">Kaldır</button>`
      : "";
    return `<div class="setting-row">
      <span class="setting-text"><strong>${esc(item.label)}</strong> ${badge}${help}</span>
      <span class="secret-control">
        <input type="password" data-key="${key}" data-kind="secret" placeholder="${esc(item.placeholder || "••••••••")}" autocomplete="new-password">
        ${clear}
      </span>
    </div>`;
  }
  const type = item.kind === "int" || item.kind === "float" ? "number" : "text";
  const step = item.kind === "float" ? "any" : "1";
  const bounds = `${item.min != null ? ` min="${item.min}"` : ""}${item.max != null ? ` max="${item.max}"` : ""}`;
  return `<label class="setting-row">
    <span class="setting-text"><strong>${esc(item.label)}</strong>${help}</span>
    <input type="${type}" ${item.kind === "float" ? `step="${step}"` : ""}${bounds}
      data-key="${key}" data-kind="${esc(item.kind)}" value="${esc(item.value ?? "")}" placeholder="${esc(item.placeholder || "")}">
  </label>`;
}

function settingsActions(tabId) {
  if (tabId === "binance") {
    return `<div class="settings-actions">
      <button type="button" class="ghost" id="test-binance">Bağlantıyı test et</button>
      <span class="muted small">Anahtarlar yalnızca bulunduğun sunucuda, şifreli olarak saklanır.</span>
    </div>`;
  }
  if (tabId === "notifications") {
    return `<div class="settings-actions">
      <button type="button" class="ghost" id="test-mail">Test e-postası</button>
      <button type="button" class="ghost" id="test-telegram">Test Telegram</button>
    </div>`;
  }
  return "";
}

function bindSettingsActions(tabId) {
  const run = async (id, url, label) => {
    const btn = $(id);
    if (!btn) return;
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = "Gönderiliyor...";
    try {
      const res = await api(url, { method: "POST" });
      toast(res.message || `${label} başarılı`);
    } catch (e) { toast(e.message, true); }
    btn.disabled = false; btn.textContent = old;
  };
  if (tabId === "binance") $("#test-binance")?.addEventListener("click", () => run("#test-binance", "/settings/test/binance", "Bağlantı"));
  if (tabId === "notifications") {
    $("#test-mail")?.addEventListener("click", () => run("#test-mail", "/settings/test/mail", "E-posta"));
    $("#test-telegram")?.addEventListener("click", () => run("#test-telegram", "/settings/test/telegram", "Telegram"));
  }
}

/* ------------------------------------------------------------------ */
/* Sistem                                                              */
/* ------------------------------------------------------------------ */
async function renderSystem(root) {
  const [info, usage, snaps, backups] = await Promise.all([
    api("/system"),
    api("/system/bot-usage"),
    api("/system/snapshots").catch(() => []),
    api("/system/backups").catch(() => []),
  ]);
  renderSystemView(root, info, usage, snaps, backups);
}

function backupRows(backups) {
  if (!backups.length) {
    return '<tr><td colspan="5" class="muted">Henüz yedek yok. Yukarıdan “Yedek oluştur” deyin.</td></tr>';
  }
  return backups.map((b) => `<tr>
    <td><div class="mono small">${esc(b.path)}</div>${b.kind === "pre-restore" ? '<span class="tag amber">güvenlik</span>' : ""}</td>
    <td class="muted small">${esc(fmtIso(b.created_at))}</td>
    <td class="num">${fmt(b.size_mb, 2)} MB</td>
    <td class="muted small">${esc(b.note || "")}</td>
    <td class="row" style="gap:6px">
      <a class="small" href="/api/system/backups/${encodeURIComponent(b.path)}/download">İndir</a>
      <button class="small primary" data-restore="${esc(b.path)}" type="button">Geri yükle</button>
      <button class="small ghost" data-del-bak="${esc(b.path)}" type="button">Sil</button>
    </td>
  </tr>`).join("");
}

function snapshotRows(snaps) {
  if (!snaps.length) {
    return '<tr><td colspan="6" class="muted">Henüz kayıt yok. Yukarıdan 20.000 mumluk referans oluşturun.</td></tr>';
  }
  return snaps.map((s) => `<tr>
    <td><div class="mono small">${esc(s.id)}</div>${s.note ? `<div class="muted small">${esc(s.note)}</div>` : ""}</td>
    <td>${esc(s.coin)} · ${esc(s.period)}</td>
    <td>${Number(s.candles || 0).toLocaleString("tr-TR")}</td>
    <td>${s.indicator_count || 0} / ${s.strategy_count || 0}</td>
    <td class="muted small">${esc(fmtIso(s.created_at))}<br>${fmt(s.size_mb, 2)} MB</td>
    <td class="row" style="gap:6px">
      <button class="small primary" data-verify="${esc(s.id)}" type="button">Doğrula</button>
      <button class="small ghost" data-del-snap="${esc(s.id)}" type="button">Sil</button>
    </td>
  </tr>`).join("");
}

function renderSystemView(root, info, usage, snaps, backups = []) {
  root.innerHTML = `
    <div class="grid c4">
      <div class="card"><h3>CPU</h3><div class="stat">${fmt(info.cpu_percent, 1)}%</div></div>
      <div class="card"><h3>RAM</h3><div class="stat">${fmt(info.memory_percent, 1)}%</div></div>
      <div class="card"><h3>Disk</h3><div class="stat">${fmt(info.disk_percent, 1)}%</div></div>
      <div class="card"><h3>Uptime</h3><div class="stat small">${Math.floor((info.uptime_seconds || 0) / 60)} dk</div></div>
    </div>
    <div class="card mt"><h3>Sistem</h3><div class="muted">Python ${esc(info.python)} · ${esc(info.platform)} · ${esc(info.hostname)}</div></div>
    <div class="card mt"><h3>Bot kaynak kullanımı</h3><table><thead><tr><th>Bot</th><th>PID</th><th>Durum</th><th>CPU</th><th>RAM (MB)</th></tr></thead><tbody>
      ${(usage.bots || []).map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.pid || "—")}</td><td>${statusTag(b.status)}</td><td>${fmt(b.cpu_percent, 1)}</td><td>${fmt(b.memory_mb, 1)}</td></tr>`).join("")}
    </tbody></table></div>

    <div class="card mt">
      <div class="row between">
        <div>
          <h3 style="margin:0">Yedekleme</h3>
          <p class="muted small" style="margin:4px 0 0">
            Varsayılan olarak yalnızca sistemin çalışması için gerekli olanlar alınır:
            botlar, stratejiler, ayarlar ve coin listeleri (<code>tradeai.db</code>), mevcut
            botların açık pozisyon/nakit durumları ve şifreli ayarların anahtarı (<code>.secret_key</code>).
            Regresyon kayıtları, AI modelleri ve büyük veri dosyaları isteğe bağlıdır.
            <b>Geri yüklemede botlar önce durdurulur</b> ve mevcut veri otomatik olarak güvenlik yedeğine alınır.
          </p>
        </div>
      </div>
      <div class="row mt">
        ${field("Not (isteğe bağlı)", `<input id="bak-note" placeholder="örn. v4 öncesi">`)}
        <label class="check"><input type="checkbox" id="bak-logs"> Bot logları</label>
        <label class="check" title="Data/ altındaki GB'lık geçmiş veri dökümleri"><input type="checkbox" id="bak-datasets"> Büyük veri dosyaları</label>
        <label class="check" title="Data/snapshots — regresyon referans kayıtları"><input type="checkbox" id="bak-snapshots"> Regresyon kayıtları</label>
        <label class="check" title="Data/Model — AI model dosyaları"><input type="checkbox" id="bak-models"> AI modelleri</label>
        <label class="check"><input type="checkbox" id="bak-env"> .env (API anahtarları)</label>
        <button class="primary" id="bak-create" type="button">Yedek oluştur</button>
      </div>
      <div class="row mt">
        ${field("Bilgisayarınızdan yedek yükle", `<input type="file" id="bak-file" accept=".zip,application/zip">`)}
        <button class="ghost" id="bak-upload" type="button">Yükle</button>
      </div>
      <div id="bak-status" class="mt"></div>
      <div class="result-scroll mt"><table>
        <thead><tr><th>Arşiv</th><th>Oluşturma</th><th>Boyut</th><th>Not</th><th></th></tr></thead>
        <tbody id="bak-body">${backupRows(backups)}</tbody>
      </table></div>
      <div id="bak-result" class="mt"></div>
      <p class="muted small mt">
        Yedekler <code>Data/backups/</code> altında tutulur (kalıcı klasör). <b>İndir</b> ile bilgisayarınıza
        alabilirsiniz; bilgisayarınızdaki bir arşivi <b>Yükle</b> ile gönderip <b>Geri yükle</b> ile açabilirsiniz.
        Alternatif: <code>docker cp yedek.zip tradeai:/app/Data/backups/</code>.
        <br><b>Not:</b> Geri yükleme kullanıcıları da değiştirdiği için oturumunuz kapanabilir;
        yedekteki kullanıcı bilgileriyle yeniden giriş yapmanız gerekir.
      </p>
    </div>

    <div class="card mt">
      <div class="row between">
        <div>
          <h3 style="margin:0">Regresyon testi (snapshot)</h3>
          <p class="muted small" style="margin:4px 0 0">
            Fiyat geçmişi + tüm indikatör değerleri + tüm strateji sinyalleri kaydedilir.
            Kod değişikliğinden sonra <b>Doğrula</b> ile aynı fiyatlar kullanılarak çıktılar yeniden
            üretilir ve <b>birebir</b> karşılaştırılır; fark varsa hangi indikatör/strateji ve hangi mum olduğu gösterilir.
          </p>
        </div>
      </div>
      <div class="row mt">
        ${field("Coin", `<input id="snap-coin" value="BTCUSDT">`)}
        ${field("Periyot", `<select id="snap-period">${["15m", "1h", "4h", "1d"].map((p) => `<option ${p === "15m" ? "selected" : ""}>${p}</option>`).join("")}</select>`)}
        ${field("Mum sayısı", `<input id="snap-candles" type="number" min="200" max="50000" value="20000">`)}
        ${field("Not (isteğe bağlı)", `<input id="snap-note" placeholder="örn. v4 referans">`)}
        <button class="primary" id="snap-create" type="button">Referans kaydet</button>
      </div>
      <div id="snap-status" class="mt"></div>
      <div class="result-scroll mt"><table>
        <thead><tr><th>Kayıt</th><th>Veri</th><th>Mum</th><th>İndikatör / Strateji</th><th>Oluşturma</th><th></th></tr></thead>
        <tbody id="snap-body">${snapshotRows(snaps)}</tbody>
      </table></div>
      <div id="snap-result" class="mt"></div>
    </div>`;

  const reload = async () => {
    const fresh = await api("/system/snapshots").catch(() => []);
    const body = $("#snap-body");
    if (body) body.innerHTML = snapshotRows(fresh);
    bindSnapButtons();
  };

  const reloadBackups = async () => {
    const fresh = await api("/system/backups").catch(() => []);
    const body = $("#bak-body");
    if (body) body.innerHTML = backupRows(fresh);
    bindBackupButtons();
  };

  const bindBackupButtons = () => {
    $$("[data-restore]").forEach((btn) => btn.addEventListener("click", async () => {
      const name = btn.dataset.restore;
      const ok = await confirmDialog(
        "Yedekten geri yükle",
        `“${name}” geri yüklenecek.\n\n• Çalışan botlar durdurulacak\n• Mevcut veri otomatik güvenlik yedeğine alınacak\n• Kullanıcılar yedekten geldiği için oturumunuz kapanabilir; yedekteki bilgilerle yeniden giriş yapın\n• Geri yükleme sonrası botları yeniden başlatmanız gerekir\n\nDevam edilsin mi?`,
        "Geri yükle",
        true,
      );
      if (!ok) return;
      $("#bak-result").innerHTML = '<span class="muted">Geri yükleme başlatıldı…</span>';
      try {
        const job = await api(`/system/backups/${encodeURIComponent(name)}/restore`, { method: "POST", body: {} });
        pollJob(job.id, (j) => {
          $("#bak-result").innerHTML = renderRestore(j);
          if (j.status === "done") reloadBackups();
        });
      } catch (e) { $("#bak-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
    }));
    $$("[data-del-bak]").forEach((btn) => btn.addEventListener("click", async () => {
      const ok = await confirmDialog("Yedeği sil", "Bu arşiv kalıcı olarak silinsin mi?", "Sil", true);
      if (!ok) return;
      try {
        await api(`/system/backups/${encodeURIComponent(btn.dataset.delBak)}`, { method: "DELETE" });
        toast("Yedek silindi");
        reloadBackups();
      } catch (e) { toast(e.message, true); }
    }));
  };

  $("#bak-create").addEventListener("click", async () => {
    $("#bak-status").innerHTML = '<span class="muted">Yedek hazırlanıyor…</span>';
    try {
      const job = await api("/system/backups", {
        method: "POST",
        body: {
          note: $("#bak-note").value,
          include_logs: $("#bak-logs").checked,
          include_env: $("#bak-env").checked,
          include_datasets: $("#bak-datasets").checked,
          include_snapshots: $("#bak-snapshots").checked,
          include_models: $("#bak-models").checked,
        },
      });
      pollJob(job.id, (j) => {
        $("#bak-status").innerHTML = renderBackup(j);
        if (j.status === "done") reloadBackups();
      });
    } catch (e) { $("#bak-status").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });

  $("#bak-upload").addEventListener("click", async () => {
    const input = $("#bak-file");
    const file = input.files && input.files[0];
    if (!file) { toast("Önce bir .zip dosyası seçin", true); return; }
    if (!/\.zip$/i.test(file.name)) { toast("Yalnızca .zip yedek dosyası yüklenebilir", true); return; }
    $("#bak-status").innerHTML = `<span class="muted">${esc(file.name)} yükleniyor (${fmt(file.size / 1048576, 2)} MB)...</span>`;
    try {
      const res = await fetch(`/api/system/backups/upload?name=${encodeURIComponent(file.name)}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/octet-stream", "X-CSRF-Token": state.csrf },
        body: file,
      });
      if (res.status === 401) { showLogin(); throw new Error("Oturum gerekli"); }
      const text = await res.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
      if (!res.ok) throw new Error((data && data.detail) ? data.detail : res.statusText);
      input.value = "";
      $("#bak-status").innerHTML = `<div class="hint ok">Yüklendi: <b>${esc(data.path)}</b> · ${fmt(data.size_mb, 2)} MB — listeden <b>Geri yükle</b> ile açabilirsiniz.</div>`;
      await reloadBackups();
      toast("Yedek yüklendi");
    } catch (e) {
      $("#bak-status").innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  });

  bindBackupButtons();

  const bindSnapButtons = () => {
    $$("[data-verify]").forEach((btn) => btn.addEventListener("click", async () => {
      const id = btn.dataset.verify;
      $("#snap-result").innerHTML = '<span class="muted">Doğrulama başlatıldı…</span>';
      try {
        const job = await api(`/system/snapshots/${id}/verify`, { method: "POST", body: {} });
        pollJob(job.id, (j) => { $("#snap-result").innerHTML = renderSnapshotVerify(j); });
      } catch (e) { $("#snap-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
    }));
    $$("[data-del-snap]").forEach((btn) => btn.addEventListener("click", async () => {
      const ok = await confirmDialog("Kaydı sil", "Bu referans kaydı silinsin mi? Doğrulama için tekrar oluşturmanız gerekir.", "Sil", true);
      if (!ok) return;
      try {
        await api(`/system/snapshots/${btn.dataset.delSnap}`, { method: "DELETE" });
        toast("Kayıt silindi");
        reload();
      } catch (e) { toast(e.message, true); }
    }));
  };

  $("#snap-create").addEventListener("click", async () => {
    $("#snap-status").innerHTML = '<span class="muted">Kayıt başlatıldı…</span>';
    try {
      const job = await api("/system/snapshots", {
        method: "POST",
        body: {
          coin: $("#snap-coin").value.trim().toUpperCase() || "BTCUSDT",
          period: $("#snap-period").value,
          candles: Number($("#snap-candles").value) || 20000,
          note: $("#snap-note").value,
        },
      });
      pollJob(job.id, (j) => {
        $("#snap-status").innerHTML = renderSnapshotRecord(j);
        if (j.status === "done") reload();
      });
    } catch (e) { $("#snap-status").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });

  bindSnapButtons();
}

function renderBackup(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") {
    return `<span class="muted">Durum: ${esc(job.message || job.status)}${job.progress ? ` · %${job.progress}` : ""}…</span>`;
  }
  const r = job.result || {};
  const inc = r.includes || {};
  const parts = [];
  if (inc.db) parts.push("veritabanı");
  if (inc.secret_key) parts.push("gizli anahtar");
  if (inc.coin_lists) parts.push("coin listeleri");
  if (inc.strategies) parts.push("stratejiler");
  if (inc.state) parts.push(`${inc.state} bot durumu`);
  if (inc.snapshots) parts.push("regresyon kayıtları");
  if (inc.models) parts.push("AI modelleri");
  if (inc.data_files) parts.push("veri dosyaları");
  if (inc.logs) parts.push("loglar");
  if (inc.env) parts.push(".env");
  return `<div class="hint ok">
    Yedek hazır: <b>${esc(r.path || r.id)}</b> · ${fmt(r.size_mb, 2)} MB
    · ${r.file_count || 0} dosya${parts.length ? ` · ${parts.map(esc).join(", ")}` : ""}
  </div>`;
}

function renderRestore(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") {
    return `<span class="muted">Durum: ${esc(job.message || job.status)}${job.progress ? ` · %${job.progress}` : ""}…</span>`;
  }
  const r = job.result || {};
  const f = r.files || {};
  const stopped = (r.bots_stopped || []).length;
  return `<div class="hint ok">
    <div>
      <b>Geri yükleme tamamlandı</b> · kaynak <span class="mono">${esc(r.restored_from)}</span><br>
      Veritabanı: ${f.db || 0} · veri: ${f.data || 0} · regresyon: ${f.snapshots || 0} ·
      durum: ${f.state || 0}${f.logs ? ` · log: ${f.logs}` : ""}${f.env ? " · .env" : ""}<br>
      ${stopped ? `${stopped} bot durduruldu.` : ""} ${r.safety_backup ? `Güvenlik yedeği: <span class="mono">${esc(r.safety_backup)}</span>.` : ""}
      ${esc(r.note || "")}
    </div>
  </div>
  <div class="row mt"><button class="primary" onclick="location.hash='#bots'" type="button">Botlara git ve başlat</button></div>`;
}

function renderSnapshotRecord(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") {
    return `<span class="muted">Durum: ${esc(job.message || job.status)}${job.progress ? ` · %${job.progress}` : ""}…</span>`;
  }
  const r = job.result || {};
  const summary = `
    <div class="hint">
      Kaydedildi: <b>${esc(r.id)}</b> · ${esc(r.coin)} ${esc(r.period)} ·
      ${Number(r.candles || 0).toLocaleString("tr-TR")} mum ·
      ${r.indicator_count || 0} indikatör serisi · ${r.strategy_count || 0} strateji ·
      ${fmt(r.size_mb, 2)} MB
    </div>`;
  if (r.version_warnings && r.version_warnings.length) {
    return summary + `<div class="error mt">${r.version_warnings.map(esc).join("<br>")}</div>`;
  }
  return summary;
}

function renderSnapshotVerify(job) {
  if (job.status === "error") return `<div class="error">${esc(job.error)}</div>`;
  if (job.status !== "done") {
    return `<span class="muted">Durum: ${esc(job.message || job.status)}${job.progress ? ` · %${job.progress}` : ""}…</span>`;
  }
  const r = job.result || {};
  const snap = r.snapshot || {};
  const head = `
    <div class="row small" style="gap:8px">
      <span class="tag gray">${esc(snap.coin || "")} · ${esc(snap.period || "")}</span>
      <span class="tag gray">${Number(snap.candles || 0).toLocaleString("tr-TR")} mum</span>
      <span class="tag blue">${r.checked ? r.checked.indicators : 0} indikatör</span>
      <span class="tag blue">${r.checked ? r.checked.strategies : 0} strateji</span>
      <span class="tag gray">tolerans ${r.tolerance}</span>
    </div>`;
  if (r.version_warnings && r.version_warnings.length) {
    head += `<div class="error mt small">${r.version_warnings.map(esc).join("<br>")}</div>`;
  }
  if (r.ok) {
    return `${head}<div class="hint ok mt"><b>Birebir aynı.</b> Tüm indikatör değerleri ve strateji sinyalleri kayıtla eşleşiyor.</div>`;
  }
  const rows = (r.failures || []).map((f) => `<tr>
    <td>${f.type === "indicator" ? '<span class="tag amber">indikatör</span>'
        : f.type === "strategy" ? '<span class="tag red">strateji</span>'
        : '<span class="tag red">veri</span>'}</td>
    <td><b>${esc(f.name)}</b>${f.side ? ` <span class="tag gray">${esc(f.side)}</span>` : ""}</td>
    <td class="num">${f.diffs == null ? "—" : f.diffs}</td>
    <td class="num">${f.first_index == null ? "—" : Number(f.first_index).toLocaleString("tr-TR")}</td>
    <td class="mono small">${f.expected == null ? "—" : esc(String(f.expected).slice(0, 24))}</td>
    <td class="mono small">${f.actual == null ? "—" : esc(String(f.actual).slice(0, 24))}</td>
    <td class="muted small">${esc(f.message || "")}</td>
  </tr>`).join("");
  return `${head}
    <div class="error mt"><b>${r.failure_count} fark bulundu.</b> Aşağıdaki indikatör/strateji kayıtla eşleşmiyor.
      ${r.truncated ? " (ilk 50 gösteriliyor)" : ""}</div>
    <div class="result-scroll mt"><table class="result-table">
      <thead><tr><th>Tür</th><th>Ad</th><th class="num">Fark</th><th class="num">İlk mum</th><th>Beklenen</th><th>Şimdiki</th><th>Not</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

/* ------------------------------------------------------------------ */
/* Başlangıç                                                           */
/* ------------------------------------------------------------------ */
(async function init() {
  try {
    const me = await api("/auth/me");
    state.user = me.user; state.csrf = me.csrf;
    await boot();
  } catch (e) {
    if (!state.user) showLogin();
  }
})();
