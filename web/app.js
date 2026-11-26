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
/** Fiyat: büyüklüğe göre anlamlı hane (0,03125562 gibi fiyatlar kırpılmasın). */
function priceText(value) {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n) || n === 0) return "—";
  const abs = Math.abs(n);
  const digits = abs >= 1000 ? 2 : abs >= 1 ? 4 : abs >= 0.1 ? 6 : 8;
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: digits });
}
function signedMoney(value) {  const n = Number(value);
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
    unrealSum += Number(st.position_pnl !== undefined ? st.position_pnl : st.unrealized_pnl) || 0;
    set(`total-${b.id}`, signedMoney(total), pnlClass(total));
    set(`realized-${b.id}`, signedMoney(st.total_realized_pnl), pnlClass(st.total_realized_pnl));
    // Pozisyon kutusu fiyat farkını (brüt) gösterir.
    set(`pospnl-${b.id}`,
      st.position ? signedMoney(st.position_pnl_gross) : "—",
      st.position ? pnlClass(st.position_pnl_gross) : "");
    set(`equity-${b.id}`, money(st.equity));
    const pos = st.position;
    if (pos) {
      set(`price-${b.id}`, fmt(pos.last_price, 8));
      set(`rowpnl-${b.id}`,
        `${Number(st.position_pnl_gross_pct) > 0 ? "+" : ""}${fmt(st.position_pnl_gross_pct, 2)}%`,
        pnlClass(st.position_pnl_gross_pct));
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
    tb.title = `Tüm botların toplam K/Z'si (komisyon dahil net). Açık pozisyonların anlık kısmı: ${signedMoney(unrealSum)}`;
  }
  set("dash-total", signedMoney(totalSum), pnlClass(totalSum));
  set("dash-unreal", `pozisyonlarda ${signedMoney(unrealSum)}`, pnlClass(unrealSum));
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

/** ISO metnini de kabul eden kısa tarih-saat (tablo hücreleri için). */
function shortStamp(value) {
  if (value === null || value === undefined || value === "") return "";
  let ms;
  if (typeof value === "number" || /^\d+$/.test(String(value))) {
    const n = Number(value);
    ms = n > 1e11 ? n : n * 1000;
  } else {
    const t = new Date(String(value).replace(" ", "T")).getTime();
    ms = Number.isFinite(t) ? t : null;
  }
  return ms === null || ms === undefined ? "" : shortDate(ms);
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
const TF_MS = {
  "1m": 6e4, "3m": 18e4, "5m": 3e5, "15m": 9e5, "30m": 18e5, "45m": 27e5,
  "1h": 36e5, "2h": 72e5, "4h": 144e5, "6h": 216e5, "8h": 288e5, "12h": 432e5,
  "1d": 864e5, "2d": 1728e5, "3d": 2592e5, "1w": 6048e5, "1M": 2592e6, "1y": 31536e6,
};
/** Serbest periyot metnini ms'e çevirir (ör. "10m", "90m", "7d", "1G"). */
const PERIOD_UNIT_MS = { m: 6e4, h: 36e5, d: 864e5, w: 6048e5, M: 2592e6, y: 31536e6 };
function periodToMs(period) {
  const text = normalizePeriod(period) || String(period || "").trim();
  const m = text.match(/^(\d{1,4})([mhdwMy])$/);
  if (!m) return null;
  const unit = PERIOD_UNIT_MS[m[2]];
  return unit ? Number(m[1]) * unit : null;
}
function periodMsOf(period) {
  return periodToMs(period) || TF_MS[period] || 36e5;
}
function periodSpanText(candles, period) {
  const ms = periodMsOf(period);
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
  const ms = periodMsOf(period);
  const fullCandles = (HISTORY_YEARS * 365 * 864e5) / ms;
  if (Number(candles) > fullCandles) return "tüm geçmiş";
  return `≈ ${periodSpanText(candles, period)}`;
}
const LIMIT_CHOICES = [3000, 5000, 10000, 20000, 50000, 100000, 250000];
/* Varlık sınıfları: test/backtest için kripto dışı da seçilebilir. */
/* Sağlayıcı yetenekleri sunucudan gelir; aşağıdakiler çevrimdışı yedektir. */
const ASSET_CLASS_OPTIONS = [
  { id: "crypto", label: "Kripto", source: "binance", provider: "binance" },
  { id: "metal", label: "Altın / Gümüş", source: "yahoo", provider: "yahoo" },
  { id: "forex", label: "Döviz", source: "yahoo", provider: "yahoo" },
  { id: "stock", label: "Hisse", source: "yahoo", provider: "yahoo" },
  { id: "fund", label: "TEFAS Fonu", source: "tefas", provider: "tefas" },
];
const ASSET_DEFAULT_SYMBOL = { crypto: "BTCUSDT", metal: "XAUUSD", forex: "USDTRY", stock: "AAPL", fund: "TEFAS:AFT" };
const PERIOD_PRESETS = ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M", "1y"];
const PROVIDER_PERIOD_FALLBACK = {
  binance: PERIOD_PRESETS,
  yahoo: ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "1w", "1M", "1y"],
  derived: ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "1w", "1M", "1y"],
  tefas: ["1d", "1w", "1M", "1y"],
};
function providerForAsset(assetClass) {
  const found = ASSET_CLASS_OPTIONS.find((c) => c.id === assetClass);
  return found ? found.provider : "";
}
function periodsForProvider(provider) {
  const seen = state.marketCatalog && state.marketCatalog.periods_by_provider;
  const items = seen && seen[provider];
  if (Array.isArray(items) && items.length) return items;
  return (PROVIDER_PERIOD_FALLBACK[provider] || PERIOD_PRESETS).map((id) => ({
    id, label: PERIOD_LABELS[id] || id, note: "",
  }));
}
function periodsForAsset(assetClass) {
  return periodsForProvider(providerForAsset(assetClass)).map((p) => p.id);
}
const PERIOD_LABELS = {
  "1m": "1 dakika", "3m": "3 dakika", "5m": "5 dakika", "15m": "15 dakika",
  "30m": "30 dakika", "45m": "45 dakika", "1h": "1 saat", "2h": "2 saat",
  "4h": "4 saat", "6h": "6 saat", "8h": "8 saat", "12h": "12 saat",
  "1d": "günlük", "3d": "3 gün", "1w": "haftalık", "1M": "aylık", "1y": "yıllık",
};
const PERIOD_MS = {
  "1m": 6e4, "3m": 18e4, "5m": 3e5, "15m": 9e5, "30m": 18e5, "45m": 27e5,
  "1h": 36e5, "2h": 72e5, "4h": 144e5, "6h": 216e5, "8h": 288e5, "12h": 432e5,
  "1d": 864e5, "2d": 1728e5, "3d": 2592e5, "1w": 6048e5, "1M": 2592e6, "1y": 31536e6,
};
const PERIOD_UNIT_ALIAS = {
  m: "m", dk: "m", min: "m", mins: "m", dakika: "m",
  h: "h", hr: "h", saat: "h", st: "h",
  d: "d", g: "d", gun: "d", "gün": "d", day: "d",
  w: "w", hf: "w", hafta: "w", week: "w", wk: "w",
  ay: "M", mo: "M", month: "M",
  y: "y", yil: "y", "yıl": "y", year: "y", yr: "y",
};
/** Serbest periyot metnini kanonik biçime çevirir; geçersizse "" döner. */
function normalizePeriod(text) {
  const raw = String(text || "").trim().replace(/\s+/g, "");
  const m = raw.match(/^(\d{1,4})(\D+)$/);
  if (!m) return "";
  const count = Number(m[1]);
  if (!Number.isFinite(count) || count < 1 || count > 1000) return "";
  const token = m[2];
  let unit = "";
  if (token === "M") {
    unit = "M"; // büyük M = ay
  } else if (token.length === 1) {
    const low = token.toLowerCase();
    if (low === "g") unit = "d"; // Türkçe "gün"
    else unit = "mhdwy".includes(low) ? low : "";
  } else {
    const key = token.replaceAll("İ", "i").replaceAll("I", "ı").toLowerCase();
    unit = PERIOD_UNIT_ALIAS[key] || "";
  }
  return unit ? `${count}${unit}` : "";
}
/** Periyot alanı: hazır seçenekler + "Özel" serbest giriş.
 *  opts.periods verilirse yalnız sağlayıcının ürettiği periyotlar listelenir. */
function periodFieldHtml(id, value = "1h", extra = "", opts = {}) {
  const allowed = Array.from(new Set((opts.periods && opts.periods.length ? opts.periods : PERIOD_PRESETS)
    .filter((p) => p === "custom" || normalizePeriod(p) === p || PERIOD_PRESETS.includes(p))));
  const list = allowed.length ? allowed : PERIOD_PRESETS.slice();
  let current = normalizePeriod(value) || String(value || "");
  if (!list.includes(current)) current = list.includes("1h") ? "1h" : list.includes("1d") ? "1d" : list[0];
  const preset = list.includes(current);
  const options = list.map(
    (p) => `<option value="${p}" ${p === current ? "selected" : ""}>${p} — ${esc(PERIOD_LABELS[p] || p)}</option>`,
  ).join("");
  return `<div class="period-picker" data-period-picker="${id}" data-period-provider="${esc(opts.provider || "")}">
    <select id="${id}-preset" class="period-preset">
      ${options}
      <option value="custom" ${preset ? "" : "selected"}>Özel…</option>
    </select>
    <input id="${id}" class="period-custom ${preset ? "hidden" : ""}" value="${esc(preset ? "" : current)}"
      placeholder="ör. 10m, 90m, 2w" autocomplete="off" spellcheck="false" ${extra}>
  </div>`;
}

/** Seçili sağlayıcıya göre periyot listesini yeniden kurar. */
function setPeriodOptions(id, periods, preferred = "", allowCustom = true) {
  const select = document.getElementById(`${id}-preset`);
  const input = document.getElementById(id);
  if (!select) return;
  const allowed = Array.from(new Set((periods && periods.length ? periods : PERIOD_PRESETS)
    .filter((p) => PERIOD_PRESETS.includes(p) || normalizePeriod(p) === p)));
  if (!allowed.length) return;
  let current = select.value;
  if (current === "custom") current = input ? normalizePeriod(input.value) : "";
  const has = (p) => allowed.includes(p);
  const next = has(current) ? current
    : preferred && has(preferred) ? preferred
    : has("1h") ? "1h" : has("1d") ? "1d" : allowed[0];
  select.innerHTML = allowed.map(
    (p) => `<option value="${p}">${p} — ${esc(PERIOD_LABELS[p] || p)}</option>`,
  ).join("") + (allowCustom ? '<option value="custom">Özel…</option>' : "");
  select.value = next;
  if (input) {
    input.classList.toggle("hidden", next !== "custom");
    if (next !== "custom") input.value = next;
  }
  select.dispatchEvent(new Event("period-change", { bubbles: true }));
}

/** Sembol/varlık değişince ilgili periyot alanını sağlayıcıya göre daraltır. */
function bindSymbolPeriods(inputId, assetSelectId, periodId) {
  const input = document.getElementById(inputId);
  const assetSelect = assetSelectId ? document.getElementById(assetSelectId) : null;
  if (!input || !periodId) return;
  let token = 0;
  const localPeriods = () => {
    const cls = assetSelect ? assetSelect.value : "";
    const provider = cls && cls !== "auto" ? providerForAsset(cls) : "";
    const items = provider ? periodsForProvider(provider) : periodsForProvider("binance")
      .concat(periodsForProvider("yahoo"), periodsForProvider("tefas"));
    const seen = new Set();
    const ids = [];
    items.forEach((p) => { if (!seen.has(p.id)) { seen.add(p.id); ids.push(p.id); } });
    return { provider, ids };
  };
  const sync = async () => {
    const { provider, ids } = localPeriods();
    const current = periodValueOf(periodId) || "1h";
    setPeriodOptions(periodId, ids, listToTimeline(ids, current), provider !== "tefas");
    const wrap = document.querySelector(`[data-period-picker="${periodId}"]`);
    if (wrap) wrap.dataset.periodProvider = provider;
    // Sembolün gerçek sağlayıcısını sunucudan doğrula (TEFAS, türetilmiş altın…).
    const symbol = String(input.value || "").trim();
    if (!symbol) return;
    const mine = ++token;
    try {
      const params = new URLSearchParams({
        symbol,
        asset_class: assetSelect && assetSelect.value !== "auto" ? assetSelect.value : "",
        source: assetSelect ? assetSourceOf(assetSelect.value) : "auto",
      });
      const data = await api(`/market/periods?${params.toString()}`);
      if (mine !== token) return;
      const ids2 = (data.items || []).map((p) => p.id);
      if (!ids2.length) return;
      const wrap2 = document.querySelector(`[data-period-picker="${periodId}"]`);
      if (wrap2) wrap2.dataset.periodProvider = data.provider || provider;
      setPeriodOptions(periodId, ids2, listToTimeline(ids2, current), data.provider !== "tefas");
    } catch (e) { /* yerel listeyle devam */ }
  };
  if (assetSelect && assetSelect.dataset.symbolPeriodsBound !== "1") {
    assetSelect.dataset.symbolPeriodsBound = "1";
    assetSelect.addEventListener("change", sync);
  }
  if (input.dataset.symbolPeriodsBound !== "1") {
    input.dataset.symbolPeriodsBound = "1";
    input.addEventListener("change", sync);
  }
  sync();
}
/** Yalnız varlık sınıfı seçiciye bağlı periyot daraltması. */
function bindAssetPeriods(assetSelectId, periodId) {
  const assetSelect = assetSelectId ? document.getElementById(assetSelectId) : null;
  if (!assetSelect || !periodId) return;
  const sync = () => {
    const cls = assetSelect.value;
    const provider = cls && cls !== "auto" ? providerForAsset(cls) : "";
    const ids = provider
      ? periodsForProvider(provider).map((p) => p.id)
      : ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M", "1y"];
    setPeriodOptions(periodId, ids, listToTimeline(ids, "1h"), provider !== "tefas");
  };
  assetSelect.addEventListener("change", sync);
  sync();
}

/** Tercih edilen periyot listede yoksa ona en yakın üst periyodu seçer. */
function listToTimeline(ids, preferred) {
  if (!preferred || ids.includes(preferred)) return preferred;
  const order = ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "2d", "3d", "1w", "1M", "1y"];
  const start = order.indexOf(preferred);
  for (let i = start; i < order.length; i += 1) if (ids.includes(order[i])) return order[i];
  for (let i = start; i >= 0; i -= 1) if (ids.includes(order[i])) return order[i];
  return ids[0] || "";
}
function periodValueOf(id) {
  const select = document.getElementById(`${id}-preset`);
  if (!select) {
    const input = document.getElementById(id);
    return input ? normalizePeriod(input.value) || String(input.value || "").trim() : "";
  }
  if (select.value !== "custom") return select.value;
  const input = document.getElementById(id);
  return input ? normalizePeriod(input.value) : "";
}
function markPeriodInvalid(id, invalid) {
  const wrap = document.querySelector(`[data-period-picker="${id}"]`);
  if (!wrap) return;
  wrap.classList.toggle("invalid", !!invalid);
  const input = document.getElementById(id);
  if (input) input.setAttribute("aria-invalid", invalid ? "true" : "false");
}
function bindPeriodField(id) {
  const select = document.getElementById(`${id}-preset`);
  const input = document.getElementById(id);
  if (!select || !input || select.dataset.periodBound === "1") return;
  select.dataset.periodBound = "1";
  const sync = (fire) => {
    const custom = select.value === "custom";
    input.classList.toggle("hidden", !custom);
    markPeriodInvalid(id, false);
    if (fire) select.dispatchEvent(new Event("period-change", { bubbles: true }));
  };
  select.addEventListener("change", () => {
    sync(true);
    if (select.value === "custom") input.focus();
  });
  input.addEventListener("input", () => {
    markPeriodInvalid(id, false);
    select.dispatchEvent(new Event("period-change", { bubbles: true }));
  });
  input.addEventListener("blur", () => {
    const normal = normalizePeriod(input.value);
    if (normal) input.value = normal;
    markPeriodInvalid(id, !normal && !!input.value.trim());
  });
  // value erişimi için: gizli olsa da input her zaman güncel değeri taşısın.
  const keepValue = () => {
    input.value = select.value === "custom" ? input.value : select.value;
  };
  select.addEventListener("change", keepValue);
  sync(false);
  keepValue();
}
/** Form gönderiminde periyodu okur; geçersizse uyarı verir. */
function readPeriod(id) {
  const value = periodValueOf(id);
  if (!value) {
    markPeriodInvalid(id, true);
    toast("Geçerli bir periyot gir (ör. 15m, 4h, 1d, 1w, 1M)", true);
    return null;
  }
  markPeriodInvalid(id, false);
  return value;
}
function assetSelectHtml(id, selected = "crypto", includeAuto = false) {
  const items = includeAuto
    ? [{ id: "auto", label: "Otomatik" }, ...ASSET_CLASS_OPTIONS]
    : ASSET_CLASS_OPTIONS;
  return `<select id="${id}">${items.map((c) => `<option value="${c.id}" ${c.id === selected ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select>`;
}
function assetSourceOf(assetClass) {
  const found = ASSET_CLASS_OPTIONS.find((c) => c.id === assetClass);
  return found ? found.source : "auto";
}
function assetIntervalMs(period) {
  return PERIOD_MS[period] || 36e5;
}
function limitOptionsHtml(period, selected) {
  return LIMIT_CHOICES.map((l) => `<option value="${l}" ${Number(l) === Number(selected) ? "selected" : ""}>${l.toLocaleString("tr-TR")} mum ${limitSpanLabel(l, period)}</option>`).join("");
}
function refreshLimitOptions(select, period) {
  if (!select) return;
  const current = select.value || "20000";
  select.innerHTML = limitOptionsHtml(period, current);
  select.value = current;
  if (select.selectedIndex < 0 && current) {
    // Seçili değer listede yoksa (ör. özel limit) koru.
    const opt = document.createElement("option");
    opt.value = current;
    opt.textContent = `${Number(current).toLocaleString("tr-TR")} mum ${limitSpanLabel(current, period)}`;
    select.appendChild(opt);
    select.value = current;
  }
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
  // Mobilde menü açıkken modal açılırsa çekmeceyi kapat.
  try { closeNav(); } catch (e) { /* henüz hazır değilse yoksay */ }
  // Açık bir canlı izleme varsa durdur: yeni modalın grafiğini ezmesin.
  if (typeof stopLiveWatch === "function") {
    try { stopLiveWatch(); } catch (e) { /* henüz tanımlı değilse yoksay */ }
  }
  $("#modal-title").textContent = title;
  const body = $("#modal-body");
  body.innerHTML = "";
  if (typeof content === "string") body.innerHTML = content;
  else body.appendChild(content);
  $("#modal").classList.remove("hidden");
}
function closeModal() {
  if (typeof stopLiveWatch === "function") {
    try { stopLiveWatch(); } catch (e) { /* yoksay */ }
  }
  $("#modal").classList.add("hidden");
}
$("#modal-close").addEventListener("click", closeModal);

/* ------------------------------------------------------------------ */
/* Sembol seçici: arama, öneri ve katalog                              */
/* ------------------------------------------------------------------ */
const ASSET_LABELS = Object.fromEntries(ASSET_CLASS_OPTIONS.map((c) => [c.id, c.label]));

function symbolFieldHtml(id, value = "", opts = {}) {
  const asset = opts.asset || "";
  const placeholder = opts.placeholder || "Sembol yaz (ör. BTCUSDT, XAUUSD, AAPL)";
  return `<div class="symbol-picker">
    <input id="${id}" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off" spellcheck="false">
    <button type="button" class="ghost small symbol-pick-btn" data-symbol-pick="${id}" data-symbol-asset="${asset}" title="Sembol ara ve listele">Ara</button>
  </div>`;
}

function symbolMultiFieldHtml(id, value = "", opts = {}) {
  const asset = opts.asset || "";
  return `<div class="symbol-picker">
    <input id="${id}" value="${esc(value)}" placeholder="${esc(opts.placeholder || "BTCUSDT, XAUUSD, AAPL")}" autocomplete="off" spellcheck="false">
    <button type="button" class="ghost small symbol-pick-btn" data-symbol-add="${id}" data-symbol-asset="${asset}" title="Listeye sembol ekle">Ekle</button>
  </div>`;
}

function assetValueOf(selectId) {
  const el = selectId ? document.getElementById(selectId) : null;
  if (!el) return "";
  return el.value === "auto" ? "" : el.value;
}

function applyAssetClass(selectId, assetClass) {
  const el = selectId ? document.getElementById(selectId) : null;
  if (!el || !assetClass) return;
  if (!Array.from(el.options).some((opt) => opt.value === assetClass)) return;
  if (el.value === assetClass) return;
  el.value = assetClass;
  // Periyot listesi ve diğer bağımlı alanlar güncellensin.
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function symbolRowHtml(item, attrs) {
  const cls = item.asset_class || "";
  const live = item.live ? `<span class="tag green">canlı</span>` : `<span class="tag blue">test</span>`;
  return `<button type="button" class="symbol-row" ${attrs} data-sym-value="${esc(item.symbol)}" data-sym-class="${esc(cls)}">
    <span class="symbol-code">${esc(item.symbol)}</span>
    <span class="symbol-name">${esc(item.label || "")}</span>
    <span class="symbol-tags">${cls ? `<span class="tag gray">${esc(ASSET_LABELS[cls] || cls)}</span>` : ""}${live}</span>
  </button>`;
}

async function fetchSymbolSearch(query, assetClass, limit = 8) {
  const params = new URLSearchParams({
    q: String(query || "").trim(),
    asset_class: String(assetClass || ""),
    limit: String(limit),
  });
  const data = await api(`/market/search?${params.toString()}`);
  return (data && data.items) || [];
}

/** Sembol alanına yazarken öneri listesi bağlar. */
function bindSymbolField(inputId, assetSelectId = "", periodId = "") {
  const input = document.getElementById(inputId);
  if (!input || input.dataset.symbolBound === "1") return;
  const wrap = input.closest(".symbol-picker");
  if (!wrap) return;
  input.dataset.symbolBound = "1";
  const box = document.createElement("div");
  box.className = "symbol-suggest hidden";
  wrap.appendChild(box);
  // Varlık sınıfı değişince sembol hâlâ varsayılan ise onu da güncelle.
  const assetSelect = assetSelectId ? document.getElementById(assetSelectId) : null;
  if (assetSelect && assetSelect.dataset.symbolDefaultBound !== "1") {
    assetSelect.dataset.symbolDefaultBound = "1";
    assetSelect.addEventListener("change", () => {
      const known = Object.values(ASSET_DEFAULT_SYMBOL);
      const current = String(input.value || "").trim().toUpperCase();
      if (!current || known.includes(current)) {
        input.value = ASSET_DEFAULT_SYMBOL[assetSelect.value] || "BTCUSDT";
      }
    });
  }
  let timer = null;
  let token = 0;
  const hide = () => box.classList.add("hidden");
  const choose = (row) => {
    input.value = row.dataset.symValue || "";
    applyAssetClass(assetSelectId, row.dataset.symClass || "");
    hide();
    input.dispatchEvent(new Event("change"));
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (!query) {
      hide();
      return;
    }
    const mine = ++token;
    timer = setTimeout(async () => {
      try {
        const items = await fetchSymbolSearch(query, assetValueOf(assetSelectId), 8);
        if (mine !== token) return;
        if (!items.length) {
          hide();
          return;
        }
        box.innerHTML = items.map((item) => symbolRowHtml(item, "")).join("");
        box.classList.remove("hidden");
      } catch (e) {
        hide();
      }
    }, 250);
  });
  box.addEventListener("mousedown", (event) => {
    const row = event.target.closest("[data-sym-value]");
    if (!row) return;
    event.preventDefault();
    choose(row);
  });
  input.addEventListener("blur", () => setTimeout(hide, 160));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
    if (event.key === "Enter" && !box.classList.contains("hidden")) {
      const first = box.querySelector("[data-sym-value]");
      if (first) {
        event.preventDefault();
        choose(first);
      }
    }
  });
  if (periodId) bindSymbolPeriods(inputId, assetSelectId, periodId);
}

function closeSymbolModal() {
  $("#symbol-modal").classList.add("hidden");
  $("#symbol-modal-body").innerHTML = "";
}
$("#symbol-modal-close").addEventListener("click", closeSymbolModal);

/** Sembol arama / seçme penceresi. */
function openSymbolPicker(inputId, assetSelectId = "", append = false) {
  const input = document.getElementById(inputId);
  if (!input) return;
  try { closeNav(); } catch (e) { /* henüz hazır değilse yoksay */ }
  let assetClass = assetValueOf(assetSelectId);
  const wrap = document.createElement("div");
  wrap.className = "symbol-modal";
  wrap.innerHTML = `
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <input id="sym-q" class="grow" placeholder="Sembol veya ad yaz: garanti, altın, AFT, bitcoin..." style="flex:1 1 240px">
      <button class="primary" id="sym-go" type="button">Ara</button>
    </div>
    <div class="chip-cloud mt" id="sym-classes">
      <button type="button" class="chip ${assetClass ? "" : "active"}" data-sym-cls="">Tümü</button>
      ${ASSET_CLASS_OPTIONS.map((c) => `<button type="button" class="chip ${assetClass === c.id ? "active" : ""}" data-sym-cls="${c.id}">${esc(c.label)}</button>`).join("")}
    </div>
    <div id="sym-results" class="symbol-results mt"><span class="muted">Yükleniyor…</span></div>
    <p class="muted small mt" id="sym-hint"></p>
    <div class="row mt" style="justify-content:flex-end">
      <button class="ghost" id="sym-manual" type="button">Yazdığım sembolü kullan</button>
    </div>`;
  $("#symbol-modal-title").textContent = append ? "Sembol ekle" : "Sembol seç";
  const host = $("#symbol-modal-body");
  host.innerHTML = "";
  host.appendChild(wrap);
  $("#symbol-modal").classList.remove("hidden");

  const q = $("#sym-q");
  const results = $("#sym-results");
  const hint = $("#sym-hint");
  q.value = String(input.value || "").trim();
  if (append) q.value = "";
  let token = 0;

  const run = async () => {
    const mine = ++token;
    results.innerHTML = '<span class="muted">Aranıyor…</span>';
    hint.textContent = "";
    try {
      const items = await fetchSymbolSearch(q.value, assetClass, 25);
      if (mine !== token) return;
      if (!items.length) {
        results.innerHTML = `<div class="empty-state small">Sonuç yok. Farklı bir kelime dene veya sembolü elle yaz.</div>`;
        hint.textContent = assetClass === "metal"
          ? "Ons (USD): XAUUSD / XAGUSD · Gram (TL): GAUTRY / GUMUSTRY."
          : assetClass === "forex"
            ? "Döviz: USDTRY, EURTRY, EURUSD, GBPUSD gibi Yahoo pariteleri."
            : assetClass === "fund"
              ? "Fon kodu ile arayabilirsin (ör. AFT, MAC, TTE)."
              : "";
        return;
      }
      results.innerHTML = items.map((item) => symbolRowHtml(item, "")).join("");
      hint.textContent = `${items.length} sonuç. Seçmek için satıra tıkla.`;
    } catch (e) {
      if (mine !== token) return;
      results.innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };

  const select = (value, cls) => {
    if (!value) return;
    if (append) {
      const parts = String(input.value || "").split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
      const upper = value.toUpperCase();
      if (!parts.some((p) => p.toUpperCase() === upper)) parts.push(upper);
      input.value = parts.join(", ");
      if (cls) applyAssetClass(assetSelectId, cls);
      closeSymbolModal();
      return;
    }
    input.value = value;
    if (cls) applyAssetClass(assetSelectId, cls);
    closeSymbolModal();
    input.dispatchEvent(new Event("change"));
  };

  results.addEventListener("click", (event) => {
    const row = event.target.closest("[data-sym-value]");
    if (!row) return;
    select(row.dataset.symValue || "", row.dataset.symClass || "");
  });
  $("#sym-classes").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-sym-cls]");
    if (!chip) return;
    assetClass = chip.dataset.symCls || "";
    $$("#sym-classes .chip").forEach((el) => el.classList.toggle("active", el === chip));
    run();
  });
  $("#sym-go").addEventListener("click", run);
  q.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      run();
    }
  });
  $("#sym-manual").addEventListener("click", () => {
    const value = String(q.value || "").trim().toUpperCase();
    if (!value) {
      toast("Önce sembol yaz", true);
      return;
    }
    select(value, assetClass);
  });
  run();
  setTimeout(() => q.focus(), 60);
}

document.addEventListener("click", (event) => {
  const watch = event.target.closest("[data-live-watch]");
  if (watch) {
    event.preventDefault();
    window.openLiveChart(watch.dataset.liveWatch || "");
    return;
  }
  const add = event.target.closest("[data-symbol-add]");
  if (add) {
    event.preventDefault();
    openSymbolPicker(add.dataset.symbolAdd, add.dataset.symbolAsset || "", true);
    return;
  }
  const pick = event.target.closest("[data-symbol-pick]");
  if (pick) {
    event.preventDefault();
    openSymbolPicker(pick.dataset.symbolPick, pick.dataset.symbolAsset || "", false);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const box = document.getElementById("symbol-modal");
  if (box && !box.classList.contains("hidden")) {
    event.stopPropagation();
    closeSymbolModal();
  }
});

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
  const minSpan = Math.max(4, Number(d.minSpan) || full / 4000);
  let span = Math.min(Math.max(hi - lo, minSpan), full);
  if (lo < d.fullLo) { lo = d.fullLo; hi = lo + span; }
  if (hi > d.fullHi) { hi = d.fullHi; lo = hi - span; }
  return { lo, hi };
}

/** Grafiği kapsayıcı genişliğine oturtarak çizer.
 *
 * İlk çizim 760 birim genişlikle üretilir; gerçek piksel genişliği farklıysa
 * `viewBox` o genişlikle yeniden oluşturulur. Böylece çizim kutuyu tam doldurur
 * (yanlarda boşluk kalmaz) ve imleç tam olarak mumun üzerine gelir.
 */
function renderTradeChart(container, prices, markers, opts = {}) {
  if (!container) return;
  container.innerHTML = tradePriceChart(prices, markers, opts);
  const svg = container.querySelector("svg.trade-chart");
  if (!svg) return;
  const width = Math.round(svg.getBoundingClientRect().width);
  const current = Number(opts.width) || 760;
  if (width >= 240 && Math.abs(width - current) > 2) {
    container.innerHTML = tradePriceChart(prices, markers, { ...opts, width });
  }
}

// Pencere/panel yeniden boyutlanınca grafik yeniden ölçeklensin: aksi halde
// viewBox ile kutu oranı bozulur ve imleç yeniden kaymaya başlar.
let _chartResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_chartResizeTimer);
  _chartResizeTimer = setTimeout(() => {
    if (window.__btData && document.getElementById("tc-wrap")) {
      window.tcRedraw();
    }
  }, 180);
});

function tcRedraw() {
  const d = tcData();
  if (!d) return;
  const wrap = document.getElementById("tc-wrap");
  if (!wrap) return;
  const vis = d.price.filter((p) => Number(p.idx) >= d.lo && Number(p.idx) <= d.hi);
  const ms = d.markers.filter((m) => Number(m.idx) >= d.lo && Number(m.idx) <= d.hi);
  const height = Number(d.height) || 380;
  renderTradeChart(wrap, vis.length >= 2 ? vis : d.price, ms, {
    height, lo: d.lo, hi: d.hi,
    extraPrices: (d.markers || []).map((m) => Number(m.price)),
    entryPrice: d.entryPrice,
    exitPrice: d.exitPrice,
    refs: d.refs || [],
    hover: true,
    width: d.chartWidth,
  });
  const svg = wrap.querySelector("svg.trade-chart");
  if (svg && svg.dataset.chartId) {
    const geom = _chartGeom.get(svg.dataset.chartId);
    if (geom) d.chartWidth = geom.w;
  }
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
  newSpan = Math.max(Math.max(4, Number(d.minSpan) || full / 4000), Math.min(full, newSpan));
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
  if (ev.preventDefault) ev.preventDefault();
  const svg = ev.currentTarget;
  const geom = svg && svg.dataset ? _chartGeom.get(svg.dataset.chartId) : null;
  if (!geom) return false;
  const local = _svgPoint(svg, ev.clientX, ev.clientY);
  if (!local) return false;
  const plotW = Math.max(1, geom.w - geom.pad.left - geom.pad.right);
  const frac = Math.min(1, Math.max(0, (local.x - geom.pad.left) / plotW));

  // Yatay tekerlek veya Shift+tekerlek: sağa/sola kaydır (TradingView gibi).
  const horizontal = ev.shiftKey || Math.abs(ev.deltaX) > Math.abs(ev.deltaY);
  if (horizontal) {
    const span = d.hi - d.lo;
    const raw = ev.deltaX || ev.deltaY;
    const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? 400 : 1;
    const shift = (raw * unit / plotW) * span;
    const v = tcClampView(d.lo + shift, d.hi + shift);
    d.lo = v.lo;
    d.hi = v.hi;
    tcRedraw();
    return false;
  }

  // Kademeli değil, tekerlek miktarına bağlı yumuşak yakınlaştırma.
  const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? 400 : 1;
  const factor = Math.pow(1.0018, ev.deltaY * unit);
  window.tcZoom(Math.min(1.7, Math.max(1 / 1.7, factor)), d.lo + (d.hi - d.lo) * frac);
  return false;
};

/** Sürükleme: piksel tabanlı, yeniden çizimden etkilenmeyen (TradingView benzeri).
 *
 * Her `pointermove`'da grafik yeniden çizilir ve SVG düğümü değişir. Eski
 * uygulama sürükleme durumunu SVG düğümüne bağlıyordu; ilk yeniden çizimde
 * düğüm ayrıldığı için kaydırma tek adımda durup "takılıyordu". Artık durum
 * başlangıçtaki **piksel konumuna** ve görünüm aralığına bağlıdır; düğüm
 * değişse de kaydırma kesintisiz sürer.
 */
window.tcDown = (ev) => {
  const d = tcData();
  if (!d) return;
  if (ev.button != null && ev.button !== 0) return;
  if (ev.pointerType === "mouse" && ev.buttons === 0) return;
  const svg = ev.currentTarget;
  const geom = svg && svg.dataset ? _chartGeom.get(svg.dataset.chartId) : null;
  if (!svg || !geom) return;
  const rect = svg.getBoundingClientRect();
  const plotUnits = Math.max(1, geom.w - geom.pad.left - geom.pad.right);
  // viewBox birimi → CSS pikseli. Grafik kutuyu tam doldurduğu için oran
  // rect.width / geom.w olur; sürükleme süresince genişlik değişmez.
  const plotPx = Math.max(1, (rect.width || geom.w) * (plotUnits / geom.w));
  TC.drag = {
    startX: ev.clientX,
    startY: ev.clientY,
    lo0: d.lo,
    hi0: d.hi,
    plotPx,
    moved: false,
  };
  _chartHideHover(svg);
  svg.classList.add("is-panning");
  document.body && document.body.classList.add("tc-panning");
  try {
    if (ev.pointerId != null && svg.setPointerCapture) {
      svg.setPointerCapture(ev.pointerId);
    }
  } catch (e) { /* yakalama desteklenmiyorsa belge dinleyicileri yeterli */ }
  if (ev.preventDefault) ev.preventDefault();
};

let _tcDragRaf = 0;

function _tcEndDrag() {
  const active = !!TC.drag;
  TC.drag = null;
  if (_tcDragRaf) {
    cancelAnimationFrame(_tcDragRaf);
    _tcDragRaf = 0;
  }
  if (document.body) document.body.classList.remove("tc-panning");
  if (active) tcRedraw();
}

document.addEventListener("pointermove", (ev) => {
  const g = TC.drag;
  if (!g) return;
  const d = tcData();
  if (!d) return;
  const dx = ev.clientX - g.startX;
  if (Math.abs(dx) > 1) g.moved = true;
  const span0 = g.hi0 - g.lo0 || 1;
  const shift = -(dx / g.plotPx) * span0;
  let lo = g.lo0 + shift;
  let hi = g.hi0 + shift;
  // Sınırda aralık korunur (kaydırma "kaçmaz"), geri çekince görünüm döner.
  if (lo < d.fullLo) { lo = d.fullLo; hi = lo + span0; }
  if (hi > d.fullHi) { hi = d.fullHi; lo = hi - span0; }
  d.lo = lo;
  d.hi = hi;
  // Kare başına tek çizim: sürükleme akıcı kalır, DOM boğulmaz.
  if (_tcDragRaf) return;
  _tcDragRaf = requestAnimationFrame(() => {
    _tcDragRaf = 0;
    if (TC.drag) tcRedraw();
  });
});

["pointerup", "pointercancel", "blur"].forEach((name) => {
  document.addEventListener(name, _tcEndDrag);
});

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

/* ---------------- Eksen / imleç yardımcıları ---------------- */

/** Eksen için "yuvarlak" adım (1, 2, 2.5, 5 × 10^n). */
function niceStep(span, target = 4) {
  const raw = Math.abs(Number(span)) / Math.max(1, target);
  if (!Number.isFinite(raw) || raw <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return mult * mag;
}

/** Adım büyüklüğüne göre gereken ondalık sayısı (0,04'lük coinlerde 5 hane). */
function axisDecimals(step) {
  const s = Math.abs(Number(step));
  if (!Number.isFinite(s) || s <= 0) return 2;
  return Math.max(0, Math.min(10, -Math.floor(Math.log10(s))));
}

function axisLabel(value, decimals) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("tr-TR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Grafik geometrisi: imleç (crosshair) için saklanır. */
const _chartGeom = new Map();

function _chartHideHover(svg) {
  const g = svg && svg.querySelector(".tc-hover");
  if (g) {
    g.style.display = "none";
    g.innerHTML = "";
  }
}

/** İmleç koordinatını SVG kullanıcı uzayına çevirir.
 *
 * Grafik `viewBox` ile ölçeklendiği için ekran pikselini doğrudan oranlamak
 * yanlış muma denk gelir (kenar boşlukları, letterbox, farklı en/boy oranı).
 * `getScreenCTM` ters matrisi bu dönüşümü birebir yapar.
 */
function _svgPoint(svg, clientX, clientY) {
  const ctm = svg.getScreenCTM ? svg.getScreenCTM() : null;
  if (!ctm) return null;
  try {
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const local = pt.matrixTransform(ctm.inverse());
    if (!Number.isFinite(local.x) || !Number.isFinite(local.y)) return null;
    return local;
  } catch (e) {
    return null;
  }
}

function _chartHoverMove(ev) {
  // Sürükleme sırasında imleç kutusu kapalı kalsın (kaydırmayı engellemesin).
  if (TC.drag) return;
  const svg = ev.target && ev.target.closest ? ev.target.closest("svg.trade-chart") : null;
  if (!svg) return;
  const geom = _chartGeom.get(svg.dataset.chartId);
  if (!geom) return;
  const local = _svgPoint(svg, ev.clientX, ev.clientY);
  if (!local) return;
  const vx = local.x;
  if (vx < geom.pad.left || vx > geom.w - geom.pad.right) {
    _chartHideHover(svg);
    return;
  }
  const target =
    geom.i0 + ((vx - geom.pad.left) / (geom.w - geom.pad.left - geom.pad.right)) * geom.span;
  let best = null;
  let bestD = Infinity;
  for (const p of geom.pts) {
    const d = Math.abs(p.idx - target);
    if (d < bestD) {
      bestD = d;
      best = p;
    }
  }
  if (!best) {
    _chartHideHover(svg);
    return;
  }
  const cx = geom.x(best.idx);
  const cy = geom.y(best.c);
  const change = best.o > 0 ? (best.c / best.o - 1) * 100 : 0;
  const up = change >= 0;
  const col = up ? "#34d399" : "#fb7185";
  const hasVol = best.v > 0;
  // Kutu değerleri fiyat büyüklüğüne göre tek bir hassasiyette yazılır
  // (0,04'lük coinlerde 0,040022 gibi gerçek seviyeler görünür) ve dört
  // değer birbiriyle hizalı kalır.
  const magnitudeDecimals = Math.abs(best.c) >= 1000 ? 2
    : Math.abs(best.c) >= 1 ? 4
      : Math.abs(best.c) >= 0.01 ? 6
        : 8;
  const valueDecimals = Math.min(10, Math.max(geom.decimals + 2, magnitudeDecimals));
  const valueText = (v) => axisLabel(v, valueDecimals);
  const boxW = 216;
  const boxH = hasVol ? 58 : 45;
  const boxX = Math.min(Math.max(geom.pad.left + 4, cx + 12), geom.w - geom.pad.right - boxW - 4);
  const boxY = geom.pad.top + 18;
  const row = (label, value, x, yy, anchor = "start") =>
    `<text x="${x}" y="${yy}" text-anchor="${anchor}" font-size="9.5" fill="#94a3b8">${esc(label)}</text>
     <text x="${x + (anchor === "start" ? 34 : -34)}" y="${yy}" text-anchor="${anchor}" font-size="9.5" fill="#e2e8f0">${esc(value)}</text>`;
  let g = svg.querySelector(".tc-hover");
  if (!g) {
    g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "tc-hover");
    svg.appendChild(g);
  }
  g.style.display = "";
  g.innerHTML = `
    <line x1="${cx.toFixed(1)}" y1="${geom.pad.top}" x2="${cx.toFixed(1)}" y2="${(geom.h - geom.pad.bottom).toFixed(1)}"
      stroke="rgba(148,163,184,.42)" stroke-width="1" stroke-dasharray="3 3"/>
    <line x1="${geom.pad.left}" y1="${cy.toFixed(1)}" x2="${(geom.w - geom.pad.right).toFixed(1)}" y2="${cy.toFixed(1)}"
      stroke="rgba(148,163,184,.22)" stroke-width="1" stroke-dasharray="3 3"/>
    <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.4" fill="${col}" stroke="#0b1220" stroke-width="1.2"/>
    <rect x="${boxX.toFixed(1)}" y="${boxY}" width="${boxW}" height="${boxH}" rx="7"
      fill="rgba(9,15,26,.94)" stroke="rgba(120,156,210,.28)"/>
    <text x="${(boxX + 9).toFixed(1)}" y="${boxY + 14}" font-size="9.5" fill="#7f90aa">${esc(fmtTime(best.t))}</text>
    <text x="${(boxX + boxW - 9).toFixed(1)}" y="${boxY + 14}" text-anchor="end" font-size="9.5" fill="${col}">
      ${up ? "+" : ""}${fmt(change, 2)}%</text>
    ${row("Açılış", valueText(best.o), boxX + 9, boxY + 27)}
    ${row("Yüksek", valueText(best.h), boxX + 116, boxY + 27)}
    ${row("Düşük", valueText(best.l), boxX + 9, boxY + 40)}
    ${row("Kapanış", valueText(best.c), boxX + 116, boxY + 40)}
    ${hasVol ? row("Hacim", fmt(best.v, 0), boxX + 9, boxY + 53) : ""}`;
}

document.addEventListener("mousemove", _chartHoverMove);
document.addEventListener("mouseleave", (ev) => {
  if (ev.target && ev.target.closest && ev.target.closest("svg.trade-chart")) {
    _chartHideHover(ev.target.closest("svg.trade-chart"));
  }
}, true);

function tradePriceChart(prices, markers, opts = {}) {
  const pts = (prices || [])
    .map((p) => ({
      idx: Number(p.idx), t: Number(p.t),
      o: Number(p.o != null ? p.o : p.c),
      h: Number(p.h != null ? p.h : p.c),
      l: Number(p.l != null ? p.l : p.c),
      c: Number(p.c),
      v: Number(p.v != null ? p.v : 0),
    }))
    .filter((p) => Number.isFinite(p.idx) && Number.isFinite(p.c) && p.c > 0
      && Number.isFinite(p.h) && Number.isFinite(p.l) && p.h >= p.l);
  if (pts.length < 2) return chartEmpty(opts.height || 320);
  const h = opts.height || 320;
  // Genişlik kapsayıcıdan gelir. `viewBox` oranı kutunun oranıyla eşleşmezse
  // tarayıcı çizimi ortaya alıp yanlara boşluk koyar (letterbox); o durumda
  // imleç birkaç mum kayar. Genişliği ölçüp vermek boşluğu kaldırır.
  const w = Number(opts.width) >= 240 ? Math.round(Number(opts.width)) : 760;
  // Sağ tarafta son fiyat balonu için yer bırakılır.
  const showLast = opts.showLast !== false && opts.hover !== false;
  const pad = { top: 24, right: showLast ? 68 : 16, bottom: 34, left: 64 };
  const i0 = opts.lo != null ? Number(opts.lo) : pts[0].idx;
  const i1 = opts.hi != null ? Number(opts.hi) : pts[pts.length - 1].idx;
  const span = i1 - i0 || 1;
  const vals = pts.map((p) => p.c);
  let min = Math.min(...pts.map((p) => p.l));
  let max = Math.max(...pts.map((p) => p.h));
  // İşlem işaretleri (alış/satış) mum aralığının dışında kalırsa grafik
  // ölçeği onları da kapsar; aksi halde üçgenler kırpılıp görünmezdi.
  const refs = (Array.isArray(opts.refs) ? opts.refs : [])
    .map((r) => ({
      v: Number(r.value),
      color: r.color || "#94a3b8",
      label: String(r.label || ""),
      band: String(r.band || ""),
    }))
    .filter((r) => Number.isFinite(r.v) && r.v > 0);
  const extras = (opts.extraPrices || [])
    .concat(opts.entryPrice ? [opts.entryPrice] : [])
    .concat(opts.exitPrice ? [opts.exitPrice] : [])
    .concat(refs.map((r) => r.v))
    .map(Number)
    .filter((v) => Number.isFinite(v) && v > 0);
  if (extras.length) {
    min = Math.min(min, ...extras);
    max = Math.max(max, ...extras);
  }
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    min = Math.min(...vals);
    max = Math.max(...vals);
  }
  // Tamamen yatay seride bile okunabilir bir bant kalsın.
  const rawSpan = max - min;
  const grip = rawSpan > 0 ? rawSpan * 0.08 : Math.max(Math.abs(max) * 0.005, 1e-9);
  min -= grip;
  max += grip;
  const vspan = max - min || 1;
  const x = (idx) => pad.left + ((idx - i0) / span) * (w - pad.left - pad.right);
  const y = (v) => h - pad.bottom - ((v - min) / vspan) * (h - pad.top - pad.bottom);

  // Y ekseni: "yuvarlak" adımlar + adıma göre ondalık (0,04'lük coinler
  // "0,04" gibi tekrar eden etiketler yerine 0,0403 / 0,0406 gösterir).
  const plotH = Math.max(60, h - pad.top - pad.bottom);
  const step = niceStep(vspan, Math.max(3, Math.min(8, Math.round(plotH / 46))));
  const decimals = axisDecimals(step);
  const ticks = [];
  const firstTick = Math.ceil(min / step) * step;
  for (let v = firstTick; v <= max + step * 1e-6; v += step) {
    const rounded = Number(v.toFixed(10));
    ticks.push({ value: rounded, y: y(rounded) });
    if (ticks.length > 12) break;
  }
  const labels = ticks.map((tick) => `
      <line x1="${pad.left}" y1="${tick.y.toFixed(1)}" x2="${w - pad.right}" y2="${tick.y.toFixed(1)}"
        stroke="rgba(120,156,210,.10)" stroke-dasharray="3 5"/>
      <text x="${pad.left - 8}" y="${(tick.y + 3.5).toFixed(1)}" text-anchor="end"
        fill="#7b8ba6" font-size="9.5" style="font-variant-numeric:tabular-nums">${axisLabel(tick.value, decimals)}</text>`).join("");

  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.idx).toFixed(1)},${y(p.c).toFixed(1)}`).join(" ");

  // Mum genişliği gerçek zaman aralığından hesaplanır: hafta sonu/tatil
  // boşluğu olan serilerde (hisse, altın, döviz) eşit genişlik varsayımı
  // mumların üst üste binmesine yol açardı.
  const diffs = [];
  for (let i = 1; i < pts.length; i += 1) diffs.push(pts[i].idx - pts[i - 1].idx);
  diffs.sort((a, b) => a - b);
  const medianStep = diffs.length ? diffs[Math.floor(diffs.length / 2)] : 0;
  const pxPerIdx = (w - pad.left - pad.right) / Math.max(1e-9, span);
  const spacing = Math.max(0.0001, medianStep * pxPerIdx);
  const candleW = Math.max(1.2, Math.min(10, spacing * 0.66));
  const useCandles = pts.length <= 320 && spacing >= 2.2;
  const candlesSvg = useCandles ? pts.map((p) => {
    const up = p.c >= p.o;
    const col = up ? "#34d399" : "#fb7185";
    const cx = x(p.idx);
    const yo = y(p.o);
    const yc = y(p.c);
    const top = Math.min(yo, yc);
    const bodyH = Math.max(1, Math.abs(yc - yo));
    return `<g><title>${esc(fmtTime(p.t))} · A ${priceText(p.o)} · Y ${priceText(p.c)} · Yük ${priceText(p.h)} · Düş ${priceText(p.l)}</title>
      <line x1="${cx.toFixed(1)}" y1="${y(p.h).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(p.l).toFixed(1)}"
        stroke="${col}" stroke-width="1" opacity=".9"/>
      <rect x="${(cx - candleW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${candleW.toFixed(1)}"
        height="${bodyH.toFixed(1)}" fill="${col}" opacity=".92"/>
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

  // Referans ve son fiyat etiketleri, eksen adımından daha hassas yazılır:
  // alış 0,0406 yerine 0,040622 gibi gerçek işlem seviyesi görünür.
  const preciseDecimals = Math.min(10, Math.max(decimals + 2, axisDecimals(step / 100)));

  // Alış/satış yatay referans çizgileri: seviyeyi eksende birebir okutur.
  const refLines = refs.map((ref) => {
    const ry = Math.min(h - pad.bottom, Math.max(pad.top, y(ref.v)));
    return `<line x1="${pad.left}" y1="${ry.toFixed(1)}" x2="${w - pad.right}" y2="${ry.toFixed(1)}"
        stroke="${ref.color}" stroke-width="1.2" stroke-dasharray="${ref.band === "strong" ? "" : "6 4"}" opacity=".55"/>
      <text x="${(w - pad.right + 4).toFixed(1)}" y="${(ry + 3).toFixed(1)}"
        fill="${ref.color}" font-size="8.5" opacity=".95">${esc(ref.label)} ${axisLabel(ref.v, preciseDecimals)}</text>`;
  }).join("") + [
    opts.entryPrice > 0 ? { v: Number(opts.entryPrice), color: "#34d399", label: "alış" } : null,
    opts.exitPrice > 0 ? { v: Number(opts.exitPrice), color: "#fb7185", label: "satış" } : null,
  ].filter(Boolean).map((ref) => {
    const ry = Math.min(h - pad.bottom, Math.max(pad.top, y(ref.v)));
    return `<line x1="${pad.left}" y1="${ry.toFixed(1)}" x2="${w - pad.right}" y2="${ry.toFixed(1)}"
        stroke="${ref.color}" stroke-width="1" stroke-dasharray="6 4" opacity=".38"/>
      <text x="${(w - pad.right + 4).toFixed(1)}" y="${(ry + 3).toFixed(1)}"
        fill="${ref.color}" font-size="8.5" opacity=".9">${esc(ref.label)} ${axisLabel(ref.v, preciseDecimals)}</text>`;
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
  const topEdge = pad.top;
  const bottomEdge = h - pad.bottom;
  const marks = Object.values(byNo).map((t) => {
    let svg = "";
    if (t.buy) {
      const bx = x(Number(t.buy.idx));
      const by = Math.min(bottomEdge - 2, Math.max(topEdge + 2, y(Number(t.buy.price))));
      // Üçgen normalde fiyatın altında; yer yoksa üstüne çevrilir ki
      // grafiğin kenarındaki işlemler kırpılıp kaybolmasın.
      const below = by + 18 <= bottomEdge;
      const base = below ? by + 8 : by - 8;
      const tip = below ? by + 17 : by - 17;
      const labelY = below ? by + 29 : by - 21;
      const title = `#${t.buy.no} AL · ${fmtTime(t.buy.time)} · ${priceText(t.buy.price)}`;
      svg += `<g class="trade-mark"><title>${esc(title)}</title>
        <polygon points="${bx.toFixed(1)},${base.toFixed(1)} ${(bx - 5).toFixed(1)},${tip.toFixed(1)} ${(bx + 5).toFixed(1)},${tip.toFixed(1)}"
          fill="#34d399" stroke="#060b14" stroke-width="1"/>
        ${showNums ? `<text x="${bx.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" fill="#6ee7b7" font-size="9">${t.buy.no}</text>` : ""}
      </g>`;
    }
    if (t.sell) {
      const sx = x(Number(t.sell.idx));
      const sy = Math.min(bottomEdge - 2, Math.max(topEdge + 2, y(Number(t.sell.price))));
      const pnl = Number(t.sell.pnl_pct);
      const st = sellStyle(t.sell.reason);
      const above = sy - 18 >= topEdge;
      const base = above ? sy - 8 : sy + 8;
      const tip = above ? sy - 17 : sy + 17;
      const labelY = above ? sy - 21 : sy + 29;
      const title = `#${t.sell.no} SAT · ${st.label} · ${fmtTime(t.sell.time)} · ${priceText(t.sell.price)} · K/Z ${pnl >= 0 ? "+" : ""}${fmt(pnl, 2)}%`;
      svg += `<g class="trade-mark"><title>${esc(title)}</title>
        <polygon points="${sx.toFixed(1)},${base.toFixed(1)} ${(sx - 5).toFixed(1)},${tip.toFixed(1)} ${(sx + 5).toFixed(1)},${tip.toFixed(1)}"
          fill="${st.color}" stroke="#060b14" stroke-width="1"/>
        ${showNums ? `<text x="${sx.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" fill="${st.light}" font-size="9">${t.sell.no}</text>` : ""}
      </g>`;
    }
    return svg;
  }).join("");

  // Son mumun kapanışı: sağ kenarda fiyat balonu.
  let lastBadge = "";
  if (showLast) {
    const lastPt = pts[pts.length - 1];
    const ly = Math.min(h - pad.bottom - 1, Math.max(pad.top + 1, y(lastPt.c)));
    const up = lastPt.c >= lastPt.o;
    const col = up ? "#34d399" : "#fb7185";
    lastBadge = `<rect x="${(w - pad.right + 2).toFixed(1)}" y="${(ly - 8).toFixed(1)}" width="64" height="16" rx="3"
        fill="${col}" opacity=".16" stroke="${col}" stroke-width="0.8"/>
      <text x="${(w - pad.right + 6).toFixed(1)}" y="${(ly + 3).toFixed(1)}" font-size="9" fill="${col}"
        style="font-variant-numeric:tabular-nums">${axisLabel(lastPt.c, preciseDecimals)}</text>`;
  }

  const chartId = `tc${++_chartSeq}`;
  _chartGeom.set(chartId, {
    w, h, pad, i0, i1, span, min, max, vspan, pts, x, y,
    step, decimals,
  });
  // Yeniden çizilen/yenilenen grafiklerin eski geometrisi bellekte kalmasın;
  // her kayıt mum listesini ve kapanışları tuttuğu için önemli.
  for (const [key, geom] of _chartGeom) {
    if (key === chartId) continue;
    const node = document.querySelector(`svg.trade-chart[data-chart-id="${key}"]`);
    if (!node) _chartGeom.delete(key);
  }
  if (_chartGeom.size > 40) {
    const oldest = _chartGeom.keys().next().value;
    _chartGeom.delete(oldest);
  }

  return `<svg class="chart-svg trade-chart" data-chart-id="${chartId}"
      viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img"
      style="touch-action:none"
      onwheel="return window.tcWheel(event)"
      onpointerdown="window.tcDown(event)"
      ondblclick="window.tcReset()">
    ${labels}
    ${xTicks}
    ${useCandles ? candlesSvg : `<path d="${line}" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linejoin="round"/>`}
    ${refLines}
    ${tradeLines}
    ${marks}
    ${lastBadge}
    <text x="${pad.left}" y="12" fill="#7f90aa" font-size="10">
      ${shownTrades} işlem · ${pts.length} mum · ${useCandles ? "mum" : "çizgi"} görünümü · tekerlek = yakınlaştır, sürükle = kaydır, çift tıkla = sıfırla
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
  const w = opts.width || 120, h = opts.height || 34, pad = 4;
  // Sıfır tabanlı serilerde (kümülatif K/Z) renk, son değerin işaretine göre;
  // aksi halde trend yönüne göre belirlenir.
  const zero = opts.zeroBased ? 0 : Math.min(...nums, 0);
  const min = Math.min(...nums, zero);
  const max = Math.max(...nums, zero);
  const span = max - min || 1;
  const xAt = (i) => pad + (i / (nums.length - 1)) * (w - pad * 2);
  const yAt = (v) => h - pad - ((v - min) / span) * (h - pad * 2);
  const pts = nums.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ");
  const last = nums[nums.length - 1];
  const first = nums[0];
  const rising = opts.zeroBased ? last >= 0 : last >= first;
  const color = opts.color || (rising ? "#34d399" : "#fb7185");
  const baseY = yAt(zero).toFixed(1);
  const area = `${pad},${baseY} ${pts} ${(w - pad).toFixed(1)},${baseY}`;
  const uid = `spk${Math.abs(Math.round(first * 1e4 + last * 97 + nums.length * 13))}`;
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity=".28"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    <line x1="${pad}" y1="${baseY}" x2="${w - pad}" y2="${baseY}" stroke="currentColor"
      stroke-opacity=".18" stroke-width="1" stroke-dasharray="2 3"/>
    <polygon points="${area}" fill="url(#${uid})" stroke="none"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${xAt(nums.length - 1).toFixed(1)}" cy="${yAt(last).toFixed(1)}" r="2.2" fill="${color}"/>
  </svg>`;
}

/** Saniyeyi "1 yıl 2 ay 3 gün 4 saat 5 dk" biçimine çevirir. */
function uptimeText(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  if (!total) return "—";
  const units = [
    ["yıl", 365 * 86400],
    ["ay", 30 * 86400],
    ["gün", 86400],
    ["saat", 3600],
    ["dk", 60],
  ];
  let rest = total;
  const parts = [];
  for (const [label, size] of units) {
    const count = Math.floor(rest / size);
    if (count > 0) {
      parts.push(`${count} ${label}`);
      rest -= count * size;
    }
    if (parts.length >= 3) break;
  }
  if (!parts.length) parts.push(`${rest} sn`);
  return parts.join(" ");
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
    const err = new Error(detail);
    // Çağıranlar HTTP durumuna göre karar verebilsin (ör. 409 = pozisyon yok).
    err.status = res.status;
    throw err;
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

/* ------------------------------------------------------------------ */
/* Mobil menü (çekmece)                                                */
/* ------------------------------------------------------------------ */
const MOBILE_NAV_QUERY = window.matchMedia("(max-width: 1020px)");

function setNavOpen(open) {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("#nav-backdrop");
  const toggle = $("#nav-toggle");
  if (!sidebar || !backdrop) return;
  const show = !!open && MOBILE_NAV_QUERY.matches;
  sidebar.classList.toggle("open", show);
  backdrop.classList.toggle("hidden", !show);
  document.body.classList.toggle("nav-open", show);
  if (toggle) toggle.setAttribute("aria-expanded", show ? "true" : "false");
}

function closeNav() { setNavOpen(false); }

function setupMobileNav() {
  const toggle = $("#nav-toggle");
  const backdrop = $("#nav-backdrop");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const sidebar = document.querySelector(".sidebar");
      setNavOpen(!(sidebar && sidebar.classList.contains("open")));
    });
  }
  if (backdrop) backdrop.addEventListener("click", closeNav);
  // Menüden bir sayfa seçilince çekmeceyi kapat.
  $$("#nav a").forEach((a) => a.addEventListener("click", closeNav));
  // Masaüstüne dönünce çekmece durumunu temizle.
  const onChange = () => { if (!MOBILE_NAV_QUERY.matches) closeNav(); };
  if (MOBILE_NAV_QUERY.addEventListener) MOBILE_NAV_QUERY.addEventListener("change", onChange);
  else if (MOBILE_NAV_QUERY.addListener) MOBILE_NAV_QUERY.addListener(onChange);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeNav();
  });
}

async function boot() {
  setupMobileNav();
  if (!state.catalog) state.catalog = await api("/strategies/indicators");
  try { state.marketCatalog = await api("/market/symbols"); } catch (e) { state.marketCatalog = null; }
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
  try { state.ai = await api("/ai/models"); } catch (e) { state.ai = []; }
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
  dashboard: "Dashboard", bots: "Botlar", strategies: "Stratejiler", ai: "AI Eğitimi",
  scan: "Tarama",
  lists: "Coin Listeleri", analysis: "Analiz", trades: "İşlem Geçmişi",
  settings: "Ayarlar", system: "Sistem",
};
const VIEW_SUBS = {
  dashboard: "Genel bakış ve performans",
  bots: "Bot oluştur, başlat ve izle",
  strategies: "Görsel kurallarla strateji tasarla",
  ai: "Zaman serisi modeli eğit, test et ve botlara bağla",
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
    ai: renderAI,
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
    const unreal = bots.reduce((sum, b) => sum + (Number(b.state && b.state.position_pnl) || 0), 0);
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
      b.state && b.state.position_pnl]),
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
  const eqPoints = stats.equity || [];
  const eqValues = eqPoints.map((p) => Number(p.value));
  const eqLast = eqValues.length ? eqValues[eqValues.length - 1] : null;
  const eqPct = eqPoints.length ? Number(eqPoints[eqPoints.length - 1].pct) : null;
  const daily = (stats.daily || []).slice(-14).map((d) => ({ label: (d.date || "").slice(5), value: d.pnl }));
  const seriesMap = {};
  (stats.by_bot || []).forEach((b) => { if (b.bot_id) seriesMap[b.bot_id] = b.series; });
  const modes = stats.modes || { paper: 0, live: 0 };
  const totalPnl = bots.reduce((sum, b) => sum + botTotalPnl(b), 0);
  const unrealizedPnl = bots.reduce((sum, b) => sum + (Number(b.state && b.state.position_pnl) || 0), 0);

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
            <p class="muted small">Kapanan işlemlerin net K/Z'si (komisyon dahil, USDT)</p>
          </div>
          <span class="chart-big ${eqLast === null ? "" : eqLast >= 0 ? "pos" : "neg"}">
            ${eqLast === null ? "—" : signedMoney(eqLast)}
          </span>
        </div>
        ${lineChart(eqValues, { height: 230, caption: `${eqValues.length} kapanan işlem${eqPct === null ? "" : ` · ${eqPct >= 0 ? "+" : ""}${fmt(eqPct, 2)}% getiri`}` })}
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

/* ------------------------------------------------------------------ */
/* K/Z kutuları: "bot toplam" ile "pozisyon anlık" ayrımı               */
/* ------------------------------------------------------------------ */
/**
 * İki net sayı üretir: botun toplam K/Z'si ve açık pozisyonun anlık K/Z'si.
 * İkisi de komisyon dahildir; toplam = kapalı işlemler + pozisyon.
 */
function posPnlHtml(bot) {
  const st = (bot && bot.state) || {};
  const total = botTotalPnl(bot);
  const hasPos = !!st.position;
  const coin = hasPos ? st.position.coin : "";
  // Pozisyon: (güncel − alış) × adet → komisyon hariç. Kullanıcı fiyatları
  // kıyasladığında gördüğü sayı budur; net etkisi alt satırda.
  const gross = hasPos ? st.position_pnl_gross : null;
  const grossPct = hasPos ? st.position_pnl_gross_pct : null;
  const net = hasPos ? st.position_pnl : null;
  const totalPct = st.total_pnl_pct;
  const totalGross = st.total_pnl_gross;
  return `
    <div class="pnl-box pnl-main">
      <div class="pnl-label" title="Kapanan işlemler + açık pozisyon, komisyon düşülmüş net">
        Bot toplam K/Z
      </div>
      <div class="pnl-value ${pnlClass(total)}" data-live="total-${esc(bot.id)}">${signedMoney(total)}</div>
      <div class="pnl-hint">${
        totalPct === null || totalPct === undefined
          ? ""
          : `${Number(totalPct) > 0 ? "+" : ""}${fmt(totalPct, 2)}% · `
      }net (komisyon dahil)${
        totalGross === null || totalGross === undefined
          ? ""
          : ` · brüt ${signedMoney(totalGross)}`
      }</div>
    </div>
    <div class="pnl-box">
      <div class="pnl-label" title="Güncel fiyat − alış fiyatı (komisyon hariç)">
        Pozisyon (anlık)
      </div>
      <div class="pnl-value ${hasPos ? pnlClass(gross) : ""}" data-live="pospnl-${esc(bot.id)}">${
        hasPos ? signedMoney(gross) : "—"
      }</div>
      <div class="pnl-hint">${
        hasPos
          ? `${grossPct === null || grossPct === undefined ? "" : `${Number(grossPct) > 0 ? "+" : ""}${fmt(grossPct, 2)}% · `}${esc(coin)}${
              net === null || net === undefined ? "" : ` · satarsan ${signedMoney(net)}`
            }`
          : "açık pozisyon yok"
      }</div>
    </div>`;
}

function botRow(bot, seriesMap = {}) {
  const pos = bot.state && bot.state.position;
  const running = bot.status === "running";
  const series = seriesMap[bot.id] || [];
  const st = bot.state || {};
  const totalPnl = botTotalPnl(bot);
  const chartColor = Number(totalPnl) > 0 ? "#34d399" : Number(totalPnl) < 0 ? "#fb7185" : undefined;
  return `<div class="bot-mini">
    <div class="row between">
      <div class="bot-mini-title">
        <span class="status-dot ${running ? "on" : ""}"></span>
        <strong>${esc(bot.name)}</strong>
        <span class="tag gray">${esc(bot.period)}</span>
        <span class="tag ${bot.mode === "live" ? "amber" : "green"}">${esc(bot.mode)}</span>
      </div>
      <div class="row" style="gap:10px">
        ${sparkline(series, { zeroBased: true, color: chartColor })}
        ${statusTag(bot.status)}
      </div>
    </div>
    <div class="row mt bot-mini-meta">
      <span><span class="muted">Toplam K/Z</span> <b data-live="total-${esc(bot.id)}" class="${pnlClass(totalPnl)}">${signedMoney(totalPnl)}</b></span>
      ${pos ? `<span><span class="muted">Pozisyon</span> <b data-live="pospnl-${esc(bot.id)}" class="${pnlClass(st.position_pnl_gross)}">${signedMoney(st.position_pnl_gross)}</b></span>` : ""}
      <span><span class="muted">İşlem</span> <b>${esc(st.trade_count || 0)}</b></span>
      <span><span class="muted">aktif</span> <b>${esc(uptimeText(st.uptime_seconds))}</b></span>
      ${pos ? `<span class="tag amber">${esc(pos.coin)} @ ${fmt(pos.entry_price, 6)}</span>
        <span><span class="muted">güncel</span> <b data-live="price-${esc(bot.id)}">${fmt(pos.last_price, 8)}</b></span>
        <span><b data-live="rowpnl-${esc(bot.id)}" class="${pnlClass(st.position_pnl_gross_pct)}">${Number(st.position_pnl_gross_pct) > 0 ? "+" : ""}${fmt(st.position_pnl_gross_pct, 2)}%</b></span>
        <button class="ghost small live-watch-btn" type="button" data-live-watch="${esc(bot.id)}"
          title="Canlı mum grafiği: fiyat, alış ve stop seviyeleri (10 sn'de bir güncellenir)">Canlı izle</button>` : '<span class="muted">pozisyon yok</span>'}
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
      b.state && b.state.position_pnl, b.state && b.state.position && b.state.position.last_price]),
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
  trail: ["amber", "takipli stop"], breakeven: ["amber", "breakeven"],
  "profit-exit": ["blue", "kâr koruma"], "kâr-koruma": ["blue", "kâr koruma"],
  "take-profit": ["green", "kâr al"], "take-profit-partial": ["green", "kısmi kâr al"],
  tp: ["green", "kâr al"], end: ["gray", "test sonu"],
  "destek-stop": ["amber", "destek stop"], "dinamik-stop": ["amber", "dinamik stop"],
  "statik-stop": ["amber", "sabit stop"],
  manuel: ["red", "manuel satış"], harici: ["red", "harici işlem"],
};
function tradeReason(reason) {
  const [cls, label] = TRADE_REASONS[reason] || ["gray", reason || "sinyal"];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}

function pendingExitHtml(pending) {
  if (!pending || !pending.reason) return "";
  const attempts = Number(pending.attempts || 0);
  const [cls, label] = TRADE_REASONS[pending.reason] || ["gray", pending.reason];
  return `<div class="row mt" style="gap:6px;align-items:center" title="Satış emri tamamlanamadı; bot birkaç saniyede bir tekrar deniyor">
    <span class="tag red">satış bekliyor</span>
    <span class="tag ${cls}">${esc(label)}</span>
    ${attempts ? `<span class="muted small">${fmt(attempts, 0)} deneme</span>` : ""}
    ${pending.created_at ? `<span class="muted small">· ${esc(fmtIso(pending.created_at))}</span>` : ""}
  </div>`;
}

function exitReasonsHtml(reasons) {
  const entries = Object.entries(reasons || {})
    .map(([k, n]) => [k, Number(n) || 0])
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (!entries.length) return "";
  const chips = entries.map(([key, n]) => {
    const [cls, label] = TRADE_REASONS[key] || ["gray", key];
    return `<span class="tag ${cls}">${esc(label)} ${fmt(n, 0)}</span>`;
  }).join(" ");
  return `<div class="row mt" style="gap:6px;flex-wrap:wrap" title="Kapanan işlemlerin çıkış nedenleri">
    <span class="muted small">çıkışlar:</span>${chips}
  </div>`;
}

function riskSummary(risk) {
  const r = risk || {};
  const parts = [];
  if (r.stop_atr) parts.push(`stop ${fmt(r.stop_atr, 1)}×ATR${r.max_stop_pct ? ` (en çok %${fmt(r.max_stop_pct, 1)})` : ""}`);
  if (r.trail_atr) parts.push(`takipli ${fmt(r.trail_atr, 1)}×ATR${r.trail_after_pct ? ` (kâr>%${fmt(r.trail_after_pct, 1)})` : ""}`);
  if (r.profit_exit_donchian) parts.push(`kâr koruma Donchian(${r.profit_exit_donchian})`);
  if (r.take_profit_atr) parts.push(`kâr al ${fmt(r.take_profit_atr, 1)}×ATR`);
  if (r.take_profit_pct) parts.push(`kâr al %${fmt(r.take_profit_pct, 1)}`);
  if (r.breakeven_pct) parts.push(`breakeven %${fmt(r.breakeven_pct, 1)} kârda`);
  if (r.partial_tp_pct) {
    parts.push(`kısmi kâr %${fmt(r.partial_tp_pct, 1)}'de %${fmt((r.partial_tp_fraction || 0.5) * 100, 0)}`);
  }
  if (r.risk_per_trade_pct) parts.push(`işlem riski %${fmt(r.risk_per_trade_pct, 1)}`);
  if (r.support_stop) parts.push("destek stop");
  if (r.static_stop) parts.push(`sabit stop %${fmt(r.static_stop_pct || 2.5, 1)}`);
  if (r.dynamic_stop) parts.push("dinamik stop (ADX)");
  if (r.cooldown) parts.push(
    r.cooldown_min_loss_pct
      ? `bekleme ${r.cooldown} mum (yalnızca zarar ≥ %${fmt(r.cooldown_min_loss_pct, 1)})`
      : `bekleme ${r.cooldown} mum`
  );
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
  const st = bot.state || {};
  const totalPnl = botTotalPnl(bot);
  const chartColor = Number(totalPnl) > 0 ? "#34d399" : Number(totalPnl) < 0 ? "#fb7185" : undefined;
  return `<div class="card bot-card ${running ? "is-running" : ""} ${live ? "is-live" : ""}">
    <div class="row between">
      <div class="row" style="gap:12px;align-items:flex-start">
        <span class="status-dot big ${running ? "on" : ""}"></span>
        <div>
          <div class="bot-name">${esc(bot.name)}</div>
          <div class="muted bot-sub">${esc(bot.period)} · ${listTag}${esc(coins)} · ${esc(specs || "strateji yok")}</div>
          <div class="muted bot-sub" title="Botun ilk başlatıldığı andan itibaren geçen süre">
            ⏱ aktif ${esc(uptimeText(st.uptime_seconds))}
            ${st.started_at ? `<span class="muted">· başlangıç ${esc(fmtIso(st.started_at))}</span>` : ""}
          </div>
        </div>
      </div>
      <div class="row">
        ${statusTag(bot.status)}
        <button class="mode-pill ${live ? "live" : "paper"}" data-action="mode" data-mode="${live ? "paper" : "live"}"
          data-id="${esc(bot.id)}" ${live || !liveLocked ? "" : "disabled"}
          title="${live ? "Test moduna al" : liveLocked ? "Önce canlı işlem anahtarını aç" : "Canlı moda geç"}">
          <span class="dot"></span>${live ? "CANLI" : "TEST"}
        </button>
        ${sparkline(series, { width: 90, height: 26, zeroBased: true, color: chartColor })}
        ${pos ? `<button class="icon-btn live-watch-btn" data-action="livewatch" data-id="${esc(bot.id)}" type="button"
          title="Canlı izle: açık pozisyonun mum grafiği (10 saniyede bir güncellenir)"
          aria-label="Canlı izle">
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <rect x="3.5" y="8" width="4" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.8"/>
            <line x1="5.5" y1="4" x2="5.5" y2="8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            <line x1="5.5" y1="16" x2="5.5" y2="20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            <rect x="16.5" y="4.5" width="4" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="1.8"/>
            <line x1="18.5" y1="11.5" x2="18.5" y2="20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
        </button>` : ""}
        <button class="icon-btn" data-action="analysis" data-id="${esc(bot.id)}" type="button"
          title="İşlem analizi: ne alındı, ne satıldı, ne kadar tutuldu, ne kadar kâr/zarar"
          aria-label="İşlem analizi">
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6.2" fill="none" stroke="currentColor" stroke-width="2"/>
            <line x1="15.2" y1="15.2" x2="20.2" y2="20.2" stroke="currentColor"
              stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    </div>
    <div class="pnl-row mt">
      ${posPnlHtml(bot)}
      <div class="pnl-box">
        <div class="pnl-label">Portföy değeri</div>
        <div class="pnl-value" data-live="equity-${esc(bot.id)}">${money(st.equity)}</div>
        <div class="pnl-hint">başlangıç ${money(st.initial_cash)}${st.cash !== null && st.cash !== undefined ? ` · nakit ${money(st.cash)}` : ""}</div>
      </div>
      <div class="pnl-box">
        <div class="pnl-label" title="Kapanan işlemlerin net kâr/zararı">Kapalı işlemler</div>
        <div class="pnl-value ${pnlClass(st.total_realized_pnl)}" data-live="realized-${esc(bot.id)}">${signedMoney(st.total_realized_pnl)}</div>
        <div class="pnl-hint">${fmt(st.trade_count, 0)} işlem · net${
          st.commission_total === null || st.commission_total === undefined || Math.abs(st.commission_total) < 0.005
            ? ""
            : ` · komisyon ${money(-Math.abs(st.commission_total))}`
        }</div>
      </div>
    </div>
    <p class="pnl-note">
      <b>Bot toplam</b> komisyon dahil net (gerçek para). <b>Pozisyon</b> güncel fiyat − alış fiyatı
      (komisyon hariç); satarken komisyon düşülür.
    </p>
    ${pos ? `
    <div class="position-strip mt">
      <span class="tag amber">${esc(pos.coin)}</span>
      <span>adet <b>${fmt(pos.quantity, 8)}</b></span>
      <span>giriş <b>${fmt(pos.entry_price, 8)}</b></span>
      <span>güncel <b data-live="price-${esc(bot.id)}">${fmt(pos.last_price, 8)}</b>
        <span class="muted small" title="${pos.price_source === "live" ? "Binance anlık fiyat" : "Canlı fiyat alınamadı; son mum kapanışı kullanılıyor"}">${
          pos.price_source !== "live"
            ? `mum${pos.price_at ? ` · ${esc(fmtTime(pos.price_at))}` : ""}`
            : Number(pos.price_age_seconds) > 30
              ? `canlı · ${fmt(pos.price_age_seconds, 0)} sn önce`
              : "canlı"
        }</span></span>
      <span>maliyet <b>${money(pos.cost)}</b></span>
      <span>şimdi satsan <b>${money(pos.net_value)}</b></span>
      ${pos.stop_price ? `<span>stop <b data-live="stop-${esc(bot.id)}">${fmt(pos.stop_price, 8)}</b>
        <span class="muted small" data-live="stopdist-${esc(bot.id)}">${stopDistanceText(pos.stop_distance_pct)}</span></span>` : ""}
      ${pos.take_profit_price ? `<span>kâr al <b>${fmt(pos.take_profit_price, 8)}</b>
        ${pos.take_profit_distance_pct !== undefined
          ? `<span class="muted small">${pos.take_profit_distance_pct >= 0 ? "+" : ""}${fmt(pos.take_profit_distance_pct, 2)}%</span>`
          : ""}</span>` : ""}
      ${pos.partial_target_price ? `<span>kısmi kâr <b>${fmt(pos.partial_target_price, 8)}</b></span>` : ""}
      ${pos.breakeven_armed ? `<span class="tag amber" title="Kısmi kâr sonrası stop girişe çekildi">breakeven</span>` : ""}
      <span>mum <b>${esc(pos.candles || 0)}</b></span>
    </div>` : '<div class="mt muted small">Açık pozisyon yok.</div>'}
    ${bot.state && bot.state.last_error ? `<div class="error mt">${esc(String(bot.state.last_error).split("\n").slice(-3).join("\n"))}</div>` : ""}
    <div class="muted small mt" title="Canlı motor, backtest ile aynı risk kurallarını uygular">
      Risk: ${esc(riskSummary(cfg.risk) || "yok (yalnızca sinyalle kapanır)")}
    </div>
    ${(cfg.risk_warnings || []).length ? `<div class="mt small" style="color:var(--amber, #fbbf24)">
      <b>Stop güvenliği:</b> ${esc((cfg.risk_warnings || []).join(" · "))}
    </div>` : ""}
    ${exitReasonsHtml(st.exit_reasons)}
    ${pendingExitHtml(st.pending_exit)}
    <div class="row mt">
      <button data-action="start" data-id="${esc(bot.id)}" ${bot.status === "running" ? "disabled" : ""}>Başlat</button>
      <button data-action="stop" data-id="${esc(bot.id)}" ${bot.status !== "running" && bot.status !== "stopping" ? "disabled" : ""}>Durdur</button>
      ${pos ? `<button class="sell-btn" data-action="sell" data-id="${esc(bot.id)}" type="button"
        title="Açık pozisyonu hemen piyasa fiyatından sat">Sat</button>` : ""}
      <button data-action="restart" data-id="${esc(bot.id)}">Yeniden Başlat</button>
      <button data-action="edit" data-id="${esc(bot.id)}" ${bot.status === "running" ? "disabled" : ""}>Düzenle</button>
      <button data-action="duplicate" data-id="${esc(bot.id)}">Kopyala</button>
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
    else if (action === "analysis") { return showBotAnalysis(id); }
    else if (action === "livewatch") { return window.openLiveChart(id); }
    else if (action === "edit") {
      const bot = (state.bots || []).find((b) => b.id === id);
      if (bot) return openBotForm(bot);
      return;
    }
    else if (action === "mode") { return switchBotMode(id, mode); }
    else if (action === "duplicate") {
      const bot = (state.bots || []).find((b) => b.id === id);
      if (!bot) return;
      const name = prompt("Yeni bot adı:", `${bot.name} (kopya)`);
      if (!name || !name.trim()) return;
      const live = bot.mode === "live";
      const ok = await confirmDialog(
        "Botu kopyala",
        `"${bot.name}" botu yeni adla kopyalanacak.\n\n` +
          `• Ad, periyot ve kurallar (strateji, risk, coinler) kopyalanır\n` +
          `• İşlem geçmişi, loglar ve açık pozisyon kopyalanmaz; sıfırdan başlar\n` +
          (live ? `• Kaynak bot CANLI; kopya da canlı olacak\n` : "") +
          `\nDevam edilsin mi?`,
        "Kopyala",
        live,
      );
      if (!ok) return;
      const res = await api(`/bots/${id}/duplicate`, { method: "POST", body: { name: name.trim() } });
      toast(`Kopyalandı: ${res.name}`);
    }
    else if (action === "sell") {
      const bot = (state.bots || []).find((b) => b.id === id) || {};
      const pos = (bot.state || {}).position;
      if (!pos) { toast("Açık pozisyon yok"); return; }
      const live = bot.mode === "live";
      const ok = await confirmDialog(
        "Manuel satış",
        `${pos.coin} pozisyonu hemen satılsın mı?\n\n` +
          `• Adet: ${fmt(pos.quantity, 8)}\n` +
          `• Giriş: ${fmt(pos.entry_price, 8)}\n` +
          `• Güncel: ${fmt(pos.last_price, 8)} (K/Z ${fmt(pos.pnl_gross_pct != null ? pos.pnl_gross_pct : pos.unrealized_pnl_pct, 2)}%)\n` +
          (live
            ? "• CANLI modda gerçek piyasa emri gönderilecek.\n"
            : "• Test modunda sanal satış yapılacak.\n") +
          "\nSatış birkaç saniye içinde uygulanır.",
        live ? "Canlı sat" : "Sat",
        live,
      );
      if (!ok) return;
      const res = await api(`/bots/${id}/sell`, { method: "POST", body: {} });
      toast(res.started ? "Satış istendi; bot satış için başlatıldı" : "Satış istendi, birkaç saniye içinde uygulanacak");
    }
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

const BOT_PERIODS = ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"];
const BOT_COIN_PRESETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT"];
const BOT_ASSET_PRESETS = {
  crypto: BOT_COIN_PRESETS,
  metal: ["XAUUSD", "GAUTRY", "XAGUSD", "GUMUSTRY"],
  forex: ["USDTRY", "EURTRY", "EURUSD", "GBPUSD"],
  stock: ["AAPL", "MSFT", "NVDA", "GARAN.IS", "THYAO.IS", "ASELS.IS"],
  fund: ["TEFAS:AFT", "TEFAS:MAC", "TEFAS:TTE"],
};
/** Sembolden varlık sınıfı tahmini (eski bot kayıtları için). */
function inferAssetClass(coin) {
  const value = String(coin || "").trim().toUpperCase();
  if (!value) return "crypto";
  if (value.startsWith("TEFAS:")) return "fund";
  if (value.endsWith("=X")) return "forex";
  if (value === "GAUTRY" || value === "GUMUSTRY" || value.endsWith("=F")) return "metal";
  if (["USDTRY", "EURTRY", "GBPTRY", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"].includes(value)) return "forex";
  const cryptoQuotes = ["USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "TRY"];
  if (cryptoQuotes.some((q) => value.endsWith(q) && value.length > q.length + 1)) return "crypto";
  if (value.startsWith("XAU") || value.startsWith("XAG")) return "metal";
  return "stock";
}
const RISK_ITEMS = [
  ["dynamic_stop", "Dinamik stop", "ADX'e duyarlı takipli stop. ADX < 20 (yatay piyasa) iken devreye girmez."],
  ["static_stop", "Sabit stop", "Giriş fiyatının belirli bir yüzdesi (aşağıdaki 'Sabit stop yüzdesi') altında çıkar."],
  ["support_stop", "Destek stop", "Destek seviyesi kırılırsa pozisyonu kapatır (son 300 mum)."],
  ["take_profit", "Kâr al", "Sayısal kâr al hedeflerini (ATR / yüzde) uygular. Kapatırsan yalnızca stop ve kâr koruma çalışır."],
];

/*
 * Sayısal risk kuralları. `rec` değerleri kendi backtest ölçümlerimizden
 * gelen başlangıç önerileridir; periyoda göre değişir.
 * unit: giriş kutusunun sağında gösterilir.
 */
const RISK_NUM_FIELDS = [
  {
    key: "stop_atr", label: "Zarar durdur (stop)", unit: "× ATR", step: "0.1",
    help: "Giriş fiyatının kaç ATR aşağısında satılacağı. ATR, coinin son 14 mumdaki ortalama oynaklığıdır. Sağlıklı aralık 1,5–3×ATR; en fazla 6×ATR ve periyot tavanı (15m %4, 1h %6, 4h %8, 1d %12) uygulanır. Çok büyük değer stopu işe yaramaz hale getirir.",
    rec: { "1m": 2, "5m": 2, "15m": 2, "1h": 2, "4h": 2.5, "1d": 3 },
  },
  {
    key: "max_stop_pct", label: "Stop üst sınırı", unit: "%", step: "0.5",
    help: "Stop bu yüzdeden daha uzağa konamaz. Periyot tavanı vardır (15m %4, 1h %6, 4h %8, 1d %12); daha geniş bir değer girilse bile tavan geçerlidir. Kârdan zarara dönmeyi engelleyen asıl sınırdır.",
    rec: { "1m": 2, "5m": 3, "15m": 4, "1h": 6, "4h": 8, "1d": 12 },
  },
  {
    key: "static_stop_pct", label: "Sabit stop yüzdesi", unit: "%", step: "0.5",
    help: "Panelde 'Sabit stop' işaretliyse giriş fiyatının bu yüzde altında satılır. Varsayılan %2,5.",
    rec: { "1m": 2, "5m": 2.5, "15m": 3, "1h": 3.5, "4h": 4.5, "1d": 6 },
  },
  {
    key: "trail_atr", label: "Takipli stop", unit: "× ATR", step: "0.1",
    help: "Fiyat yükseldikçe stop yukarı taşınır. Zirveden kaç ATR aşağıda takip edileceği (en fazla 6×ATR). Kârı kilitler, trend dönünce çıkar.",
    rec: { "1m": 1.5, "5m": 1.5, "15m": 2, "1h": 2, "4h": 2.5, "1d": 3 },
  },
  {
    key: "trail_after_pct", label: "Takipli stop başlangıcı", unit: "% kâr", step: "0.5",
    help: "Kâr bu yüzdeyi geçmeden takipli stop devreye girmez. Erken dalgalanmada pozisyonun kesilmesini önler.",
    rec: { "1m": 1, "5m": 1.5, "15m": 2, "1h": 3, "4h": 5, "1d": 7 },
  },
  {
    key: "take_profit_atr", label: "Kâr al (ATR)", unit: "× ATR", step: "0.1",
    help: "Girişten kaç ATR yukarıda kâr alınacağı. 0 = kapalı; kârı takipli stop ve kâr korumaya bırakır (trend stratejilerinde önerilir).",
    rec: { "1m": 0, "5m": 0, "15m": 0, "1h": 0, "4h": 0, "1d": 0 },
  },
  {
    key: "take_profit_pct", label: "Kâr al (yüzde)", unit: "%", step: "0.5",
    help: "Girişe göre sabit yüzde kâr hedefi. 0 = kapalı. Sabit hedef, güçlü trendlerde erken çıkmanıza yol açar.",
    rec: { "1m": 0, "5m": 0, "15m": 0, "1h": 0, "4h": 0, "1d": 0 },
  },
  {
    key: "breakeven_pct", label: "Breakeven eşiği", unit: "% kâr", step: "0.5",
    help: "Kâr bu yüzdeyi geçince stop en az giriş fiyatına çekilir; artık kaybetme ihtimali kalmaz. 0 = kapalı. Boş bırakılırsa stop mesafesinin ~%60'ı otomatik uygulanır.",
    rec: { "1m": 1, "5m": 1.5, "15m": 2.4, "1h": 3.6, "4h": 4.8, "1d": 7.2 },
  },
  {
    key: "partial_tp_pct", label: "Kısmi kâr hedefi", unit: "%", step: "0.5",
    help: "Kâr bu yüzdeye ulaşınca pozisyonun bir kısmı satılır (aşağıdaki oran), kalan kısım takipli stopla devam eder. 0 = kapalı.",
    rec: { "1m": 0, "5m": 0, "15m": 0, "1h": 0, "4h": 0, "1d": 0 },
  },
  {
    key: "partial_tp_fraction", label: "Kısmi satış oranı", unit: "0–1", step: "0.1",
    help: "Kısmi kâr hedefinde satılacak oran. 0,5 = yarısı satılır, yarısı trend için kalır. Kısmi hedef kapalıysa dikkate alınmaz.",
    rec: { "1m": 0.5, "5m": 0.5, "15m": 0.5, "1h": 0.5, "4h": 0.5, "1d": 0.5 },
  },
  {
    key: "risk_per_trade_pct", label: "İşlem başına risk", unit: "% nakit", step: "0.5",
    help: "Pozisyon büyüklüğü stop mesafesine göre hesaplanır: bu yüzde, stop vurulursa kaybedilecek nakit. Örnek: 1 → 1.000 USDT nakitte stop vurulursa ~10 USDT kayıp. 0 = eski davranış (nakit × pozisyon yüzdesi).",
    rec: { "1m": 1, "5m": 1, "15m": 1, "1h": 1, "4h": 1.5, "1d": 2 },
  },
  {
    key: "profit_exit_donchian", label: "Kâr koruma (Donchian)", unit: "mum", step: "1",
    help: "Pozisyon kârdayken son N mumun dibi kırılırsa çıkar. Trend bozulmasını hızlı yakalar. 0 = kapalı, 10 = yaygın değer.",
    rec: { "1m": 0, "5m": 0, "15m": 10, "1h": 10, "4h": 10, "1d": 10 },
  },
  {
    key: "cooldown", label: "Yeni alım beklemesi (cooldown)", unit: "mum", step: "1",
    help: "Bir satıştan sonra kaç mum boyunca yeni pozisyon açılmayacağı. Aynı sinyalin hemen tekrar girip komisyon erozyonu yaratmasını önler.",
    rec: { "1m": 10, "5m": 8, "15m": 8, "1h": 5, "4h": 3, "1d": 2 },
  },
  {
    key: "cooldown_min_loss_pct", label: "Bekleme yalnızca zarar ≥", unit: "%", step: "0.5",
    help: "0 = her satıştan sonra bekle. 5 = yalnızca %5 veya daha kötü zararla çıkıldıysa bekle; küçük zarar veya kârda bot hemen devam eder.",
    rec: { "1m": 5, "5m": 5, "15m": 5, "1h": 5, "4h": 5, "1d": 5 },
  },
];

function recommendRisk(period) {
  const out = {};
  RISK_NUM_FIELDS.forEach((f) => { out[f.key] = f.rec[period] ?? 0; });
  return out;
}


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
  const ai = (state.ai || [])
    .filter((m) => m.status === "active")
    .map((m) => {
      const t = (m.metrics && m.metrics.test) || {};
      return {
        key: "ai:" + m.id,
        kind: "ai",
        name: "AI · " + m.name,
        version: 1,
        ai: m,
        ret: t.total_return_pct,
        spec: { type: "ai", model_id: m.id },
      };
    });
  return [...ai, ...custom, ...builtin];
}

async function openBotForm(existing = null, options = {}) {
  if (!state.extra || !state.custom) {
    try {
      const [builtin, custom, ai] = await Promise.all([
        api("/strategies/builtin"),
        api("/strategies/custom?include_archived=true"),
        api("/ai/models").catch(() => []),
      ]);
      state.extra = builtin;
      state.custom = custom;
      state.ai = ai;
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
    asset: (cfg && cfg.asset_class) || inferAssetClass((cfg ? (cfg.coins || [])[0] : presetCoins ? presetCoins[0] : "BTCUSDT") || "BTCUSDT"),
    coinListId: cfg && cfg.coin_list ? cfg.coin_list.id : options.coinListId || "",
    strategies: existing
      ? ((cfg && cfg.strategies) || []).map((s) =>
          s.type === "custom" ? "custom:" + s.id
            : s.type === "ai" ? "ai:" + (s.model_id || s.id)
            : "builtin:" + s.name)
      : quick && quickPick ? [quickPick.key] : [],
    risk: Object.assign({ dynamic_stop: false, static_stop: false, support_stop: true, take_profit: true }, (cfg && cfg.risk) || {}),
    filters: Object.assign({ buy_ma_control: false, buy_bb_control: false }, (cfg && cfg.filters) || {}),
    autoRestart: existing ? !!existing.auto_restart : true,
  };
  const pick = (key) => catalog.find((c) => c.key === key);
  const rv = (key) => {
    const v = draft.risk[key];
    return v === undefined || v === null || v === "" ? "" : v;
  };
  const riskNum = (fieldDef) => {
    const rec = fieldDef.rec[draft.period];
    const recText = rec === undefined ? "-" : String(rec);
    return `<div class="risk-num-field">
      <label class="risk-num-label" for="rk-${fieldDef.key}">
        ${esc(fieldDef.label)} <span class="risk-num-unit">${esc(fieldDef.unit)}</span>
      </label>
      <div class="risk-num-input">
        <input id="rk-${fieldDef.key}" type="number" min="0" step="${fieldDef.step}"
          value="${esc(rv(fieldDef.key))}" placeholder="${esc(recText)}">
        <button type="button" class="risk-num-rec" data-rec="${fieldDef.key}"
          title="Bu periyot için önerilen değeri yaz">Önerilen: ${esc(recText)}</button>
      </div>
      <p class="risk-num-help">${esc(fieldDef.help)}</p>
    </div>`;
  };

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
        <div class="row mt">
          <label class="pf"><span>Varlık sınıfı</span>${assetSelectHtml("b-asset", draft.asset)}</label>
          <label class="pf"><span>Zaman dilimi</span><div class="chip-cloud" id="period-chips"></div></label>
        </div>
        <p class="muted small" id="b-asset-hint" style="margin:6px 0 0"></p>
        <div class="row mt">
          <label class="pf"><span>Başlangıç nakdi</span><input id="b-cash" type="number" min="1" step="1" value="${draft.cash}"></label>
          <label class="pf"><span>Maksimum pozisyon (%)</span><input id="b-pos" type="number" min="1" max="100" value="${draft.maxPos}"></label>
        </div>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-head">
        <span class="step">3</span>
        <div><h4>Semboller</h4><p class="muted">Kripto dışı semboller yalnızca test (paper) modunda çalışır.</p></div>
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
          <input id="coin-add" placeholder="Sembol yaz veya ara (XAUUSD, AAPL, TEFAS:AFT…)" style="max-width:300px">
          <button type="button" class="small" id="coin-search-btn">Ara</button>
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
        <div class="risk-num-head">
          <span>Sayısal kurallar</span>
          <span class="muted small">Değerler bu bota özeldir · 0 = kapalı · boş = stratejiden devral</span>
          <button type="button" class="ghost small" id="risk-apply-rec">Önerilen değerleri uygula</button>
        </div>
        <p class="risk-num-intro">
          Aşağıdaki değerler <b id="risk-num-period">${esc(draft.period)}</b> periyodu için önerilen başlangıç değerleridir.
          Kendi backtest sonuçlarınıza göre değiştirebilirsiniz. Her alanın yanındaki
          <b>“Önerilen”</b> düğmesine basarak o değeri tek tıkla yazabilirsiniz.
        </p>
        <div class="risk-num-grid" id="risk-num-grid"></div>
        <div class="risk-num-note">
          <b>Nasıl okunur?</b> ATR, coinin son 14 mumdaki ortalama oynaklığıdır. Stop ve takipli stop
          ATR’nin katı olarak verilir; böylece aynı ayar hem sakin hem oynak coinlerde ölçekli çalışır.
          Cooldown, art arda aynı sinyale girip komisyon ödemeyi engeller.
        </div>
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
    const assetLabel = (ASSET_CLASS_OPTIONS.find((c) => c.id === draft.asset) || {}).label || draft.asset;
    const parts = [
      draft.mode === "live" ? "CANLI" : "Test",
      assetLabel,
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

  /* Periyot: yalnız seçili varlık sınıfının sağlayıcısının ürettiği periyotlar */
  const renderAssetHint = () => {
    const hint = $("#b-asset-hint");
    if (!hint) return;
    const label = (ASSET_CLASS_OPTIONS.find((c) => c.id === draft.asset) || {}).label || draft.asset;
    hint.innerHTML = draft.asset === "crypto"
      ? `<b>${esc(label)}</b> · Binance gerçek zamanlı verisi. Canlı ve test modu kullanılabilir.`
      : `<b>${esc(label)}</b> · Yahoo/TEFAS ücretsiz geçmiş verisi. Bu bot yalnızca <b>test (paper)</b> modunda çalışır.`;
  };
  const renderPeriods = () => {
    const box = $("#period-chips");
    box.innerHTML = "";
    const allowed = periodsForAsset(draft.asset).filter((p) => BOT_PERIODS.includes(p));
    if (!allowed.length) allowed.push("1h");
    if (!allowed.includes(draft.period)) {
      draft.period = allowed.includes("1h") ? "1h" : allowed.includes("1d") ? "1d" : allowed[0];
    }
    allowed.forEach((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (draft.period === p ? " active" : "");
      b.textContent = p;
      b.addEventListener("click", () => {
        draft.period = p;
        renderPeriods();
        collectRiskInputs();
        renderRiskNumbers();
        summary();
      });
      box.appendChild(b);
    });
  };
  renderAssetHint();
  renderPeriods();

  /* Semboller */
  const renderCoins = () => {
    const box = $("#coin-chips");
    box.innerHTML = "";
    const presets = BOT_ASSET_PRESETS[draft.asset] || BOT_COIN_PRESETS;
    const all = Array.from(new Set([...presets, ...draft.coins]));
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
    const values = input.value.split(/[\s,;]+/).map((v) => v.trim().toUpperCase()).filter(Boolean);
    if (!values.length) return;
    let bad = "";
    values.forEach((value) => {
      if (!/^[A-Z0-9:._=/^+-]{2,40}$/.test(value)) { bad = value; return; }
      if (!draft.coins.includes(value)) draft.coins.push(value);
    });
    if (bad) { toast(`Geçersiz sembol: ${bad}`, true); return; }
    input.value = "";
    renderCoins();
    summary();
  };
  $("#coin-add-btn").addEventListener("click", addCoin);
  $("#coin-search-btn").addEventListener("click", () => openSymbolPicker("coin-add", "b-asset", true));
  $("#coin-add").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCoin(); } });

  /* Varlık sınıfı: periyot listesini ve coin önerilerini daraltır. */
  $("#b-asset").addEventListener("change", () => {
    draft.asset = $("#b-asset").value;
    if (draft.asset !== "crypto" && draft.mode === "live") {
      draft.mode = "paper";
      renderMode();
      toast("Canlı işlem yalnızca kripto içindir; bot test moduna alındı.");
    }
    draft.coins = draft.coins.filter((c) => inferAssetClass(c) === draft.asset);
    renderAssetHint();
    renderPeriods();
    renderCoins();
    summary();
  });

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
      } else if (item.kind === "ai") {
        const t = (item.ai && item.ai.metrics && item.ai.metrics.test) || {};
        rules = `<span class="pick-rules muted">Eğitilmiş AI modeli · test getirisi ${fmt(t.total_return_pct, 1)}% · ${fmt(t.trade_count, 0)} işlem</span>`;
      } else {
        rules = `<span class="pick-rules muted">Hazır strateji — mevcut motorla çalışır.</span>`;
      }
      card.innerHTML = `
        <span class="pick-head">
          <strong>${esc(item.name)}</strong>
          <span class="tag ${item.kind === "custom" ? "green" : item.kind === "ai" ? "blue" : "gray"}">${item.kind === "custom" ? "özel v" + item.version : item.kind === "ai" ? "AI" : "hazır"}</span>
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

  /* Sayısal risk kuralları (periyoda göre önerilen değerlerle) */
  const collectRiskInputs = () => {
    RISK_NUM_FIELDS.forEach((f) => {
      const el = $(`#rk-${f.key}`);
      if (!el) return;
      const raw = String(el.value || "").trim().replace(",", ".");
      if (raw === "") { delete draft.risk[f.key]; return; }
      const n = Number(raw);
      if (Number.isFinite(n)) draft.risk[f.key] = Math.max(0, n);
    });
  };
  const renderRiskNumbers = () => {
    const grid = $("#risk-num-grid");
    if (!grid) return;
    const periodLabel = $("#risk-num-period");
    if (periodLabel) periodLabel.textContent = draft.period;
    grid.innerHTML = RISK_NUM_FIELDS.map(riskNum).join("");
    $$("#risk-num-grid [data-rec]").forEach((btn) => btn.addEventListener("click", () => {
      const fieldDef = RISK_NUM_FIELDS.find((f) => f.key === btn.dataset.rec);
      if (!fieldDef) return;
      const value = fieldDef.rec[draft.period];
      const input = $(`#rk-${fieldDef.key}`);
      if (input && value !== undefined) {
        input.value = String(value);
        draft.risk[fieldDef.key] = value;
        input.classList.add("just-set");
        setTimeout(() => input.classList.remove("just-set"), 700);
        summary();
      }
    }));
    $$("#risk-num-grid input[type=number]").forEach((input) => {
      input.addEventListener("input", () => {
        collectRiskInputs();
        summary();
      });
    });
  };
  renderRiskNumbers();

  const applyRecommended = () => {
    collectRiskInputs();
    const rec = recommendRisk(draft.period);
    Object.keys(rec).forEach((key) => {
      draft.risk[key] = rec[key];
      const input = $(`#rk-${key}`);
      if (input) {
        input.value = String(rec[key]);
        input.classList.add("just-set");
        setTimeout(() => input.classList.remove("just-set"), 700);
      }
    });
    summary();
  };
  const applyRecBtn = $("#risk-apply-rec");
  if (applyRecBtn) applyRecBtn.addEventListener("click", applyRecommended);

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
      if (draft.mode === "live" && draft.asset !== "crypto") {
        throw new Error("Hisse/altın/döviz/fon botları yalnızca test (paper) modunda çalışır.");
      }
      const numVal = (key) => {
        const el = $(`#rk-${key}`);
        if (!el) return null;
        const raw = String(el.value || "").trim().replace(",", ".");
        if (raw === "") return null; // boş = stratejiden devral
        const n = Number(raw);
        return Number.isFinite(n) ? Math.max(0, n) : null;
      };
      ["stop_atr", "max_stop_pct", "static_stop_pct", "trail_atr", "trail_after_pct", "take_profit_atr",
       "take_profit_pct", "breakeven_pct", "partial_tp_pct", "partial_tp_fraction",
       "risk_per_trade_pct", "profit_exit_donchian", "cooldown", "cooldown_min_loss_pct"]
        .forEach((key) => { draft.risk[key] = numVal(key); });
      const body = {
        name: $("#b-name").value.trim() || "İsimsiz bot",
        period: draft.period,
        mode: draft.mode,
        asset_class: draft.asset,
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

/** Tutma süresi: "3 sa 12 dk", "2 gün 4 sa", "45 dk". */
function holdText(seconds) {
  const total = Math.floor(Number(seconds));
  if (!Number.isFinite(total) || total < 0) return "—";
  if (total < 60) return `${total} sn`;
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (d > 0) return `${d} gün${h ? ` ${h} sa` : ""}`;
  if (h > 0) return `${h} sa${m ? ` ${m} dk` : ""}`;
  return `${m} dk`;
}

/** Model katman bilgisini güvenli metne çevirir: [64,32] → "64→32", 2 → "2". */
function layersText(value, sep = "→") {
  if (Array.isArray(value)) return value.join(sep);
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number" || typeof value === "string") return String(value);
  return "";
}

/**
 * Mimari özeti. Motor başına farklı alanlar kullanılır:
 * MLP gizli katman listesi, LSTM hücre sayısı, Transformer boyut/blok/başlık.
 * Değerler eksik ya da sayı olduğunda da bozulmadan metin üretir.
 */
function archSummaryText(engine, model, params) {
  const p = params || {};
  const m = model || {};
  const kind = String(engine || p.engine || "mlp");
  if (kind === "gbm") return "gradient boosting";
  if (kind === "transformer") {
    const parts = [];
    if (m.dim) parts.push(`boyut ${m.dim}`);
    const depth = m.depth !== undefined ? m.depth : (typeof m.layers === "number" ? m.layers : null);
    if (depth !== null && depth !== undefined && depth !== "") parts.push(`${depth} blok`);
    if (m.heads) parts.push(`${m.heads} başlık`);
    if (p.seq_window) parts.push(`pencere ${p.seq_window}`);
    return parts.join(" · ") || "-";
  }
  if (kind === "lstm") {
    const parts = [];
    if (m.hidden) parts.push(`${m.hidden} hücre`);
    if (p.seq_window) parts.push(`pencere ${p.seq_window}`);
    if (p.dropout !== undefined && p.dropout !== null) parts.push(`dropout ${fmt(p.dropout, 2)}`);
    return parts.join(" · ") || "-";
  }
  const layers = layersText(m.layers !== undefined && m.layers !== null ? m.layers : p.hidden_layers);
  const act = p.activation ? ` · ${p.activation}` : "";
  const drop = p.dropout !== undefined && p.dropout !== null ? ` · dropout ${fmt(p.dropout, 2)}` : "";
  return `${layers || "-"}${act}${drop}`;
}

async function showBotAnalysis(id) {
  const bot = (state.bots || []).find((b) => b.id === id) || {};
  let data;
  try {
    data = await api(`/trades/bot/${encodeURIComponent(id)}/analysis`);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  const s = data.summary || {};
  const money = (v) => (v === null || v === undefined ? "—" : signedMoney(v));
  const pctText = (v) => (v === null || v === undefined ? "—" : `${Number(v) > 0 ? "+" : ""}${fmt(v, 2)}%`);
  const make = () => {
    const wrap = document.createElement("div");
    const rows = (data.trades || []).map((t, i) => `
      <tr>
        <td class="mono">${(data.trades.length - i)}</td>
        <td>${esc(t.coin)}</td>
        <td class="mono small">${esc(fmtTime(t.entry_time))}</td>
        <td class="mono">${fmt(t.entry_price, 8)}</td>
        <td class="mono small">${esc(fmtTime(t.exit_time))}</td>
        <td class="mono">${fmt(t.exit_price, 8)}</td>
        <td>${fmt(t.quantity, 8)}</td>
        <td>${esc(holdText(t.hold_seconds))}</td>
        <td class="${pnlClass(t.pnl_money)}">${money(t.pnl_money)}</td>
        <td class="${pnlClass(t.pnl_pct)}">${pctText(t.pnl_pct)}</td>
        <td>${tradeReason(t.exit_reason)}</td>
      </tr>`).join("");
    const lots = (data.open_lots || []).map((l) => `
      <tr>
        <td>${esc(l.coin)}</td>
        <td class="mono">${fmt(l.entry_price, 8)}</td>
        <td>${fmt(l.quantity, 8)}</td>
        <td>${money(l.invested)}</td>
        <td class="mono small">${esc(fmtTime(l.entry_time))}</td>
        <td>${esc(holdText(l.age_seconds))}</td>
      </tr>`).join("");
    const coinRows = (data.by_coin || []).map((c) => `
      <tr>
        <td>${esc(c.coin)}</td>
        <td>${fmt(c.trades, 0)}</td>
        <td>${fmt(c.wins, 0)} / ${fmt(c.losses, 0)}</td>
        <td>${c.win_rate === null ? "—" : fmt(c.win_rate, 1) + "%"}</td>
        <td class="${pnlClass(c.pnl_money)}">${money(c.pnl_money)}</td>
        <td class="${pnlClass(c.pnl_pct)}">${pctText(c.pnl_pct)}</td>
        <td>${esc(holdText(c.avg_hold_seconds))}</td>
      </tr>`).join("");
    const reasonRows = (data.by_exit_reason || []).map((r) => `
      <tr>
        <td>${tradeReason(r.reason)}</td>
        <td>${fmt(r.trades, 0)}</td>
        <td class="${pnlClass(r.pnl_money)}">${money(r.pnl_money)}</td>
      </tr>`).join("");
    wrap.innerHTML = `
      <div class="row between" style="align-items:flex-start">
        <div>
          <div class="row" style="gap:8px;align-items:center">
            <b>${esc(bot.name || data.bot_id)}</b>
            <span class="tag ${bot.mode === "live" ? "amber" : "green"}">${esc(bot.mode || "paper")}</span>
            <span class="tag gray">${esc(bot.period || "")}</span>
          </div>
          <div class="muted small" style="margin-top:4px">
            ${fmt(data.orders, 0)} emir · ${fmt(s.buy_orders, 0)} alış / ${fmt(s.sell_orders, 0)} satış ·
            ${fmt(s.closed_trades, 0)} kapanan tur${data.limited ? " (son 2000 emir)" : ""}
          </div>
        </div>
        <a class="chip" href="/api/trades/export.csv?bot_id=${encodeURIComponent(id)}" download>CSV indir</a>
      </div>

      <div class="ana-stats mt">
        <div class="ana-stat">
          <div class="ana-label">Toplam K/Z</div>
          <div class="ana-value ${pnlClass(s.pnl_money)}">${money(s.pnl_money)}</div>
          <div class="ana-hint">${pctText(s.pnl_pct)} · yatırılan ${money(s.invested)}</div>
        </div>
        <div class="ana-stat">
          <div class="ana-label">Kazanan / kaybeden</div>
          <div class="ana-value">${fmt(s.wins, 0)} / ${fmt(s.losses, 0)}</div>
          <div class="ana-hint">${s.win_rate === null || s.win_rate === undefined ? "kapalı işlem yok" : fmt(s.win_rate, 1) + "% kazanma"}</div>
        </div>
        <div class="ana-stat">
          <div class="ana-label">En iyi / en kötü</div>
          <div class="ana-value ${pnlClass(s.best)}">${money(s.best)}</div>
          <div class="ana-hint">en kötü ${money(s.worst)} · ort ${s.avg_pnl_money === null || s.avg_pnl_money === undefined ? "—" : money(s.avg_pnl_money)}</div>
        </div>
        <div class="ana-stat">
          <div class="ana-label">Tutma süresi</div>
          <div class="ana-value">${esc(holdText(s.avg_hold_seconds))}</div>
          <div class="ana-hint">en kısa ${esc(holdText(s.min_hold_seconds))} · en uzun ${esc(holdText(s.max_hold_seconds))}</div>
        </div>
        <div class="ana-stat">
          <div class="ana-label">Kâr faktörü</div>
          <div class="ana-value">${s.profit_factor === null || s.profit_factor === undefined ? "—" : fmt(s.profit_factor, 2)}</div>
          <div class="ana-hint">komisyon ${money(-Math.abs(s.fees || 0))}</div>
        </div>
      </div>

      <div class="row between mt">
        <b class="small">İşlem bazında K/Z</b>
        <span class="muted small">En yeni en üstte · tutma süresi alıştan satışa</span>
      </div>
      <div class="result-scroll mt"><table class="result-table ana-table"><thead><tr>
        <th>#</th><th>Coin</th><th>Alış</th><th>Alış fiyatı</th><th>Satış</th><th>Satış fiyatı</th>
        <th>Adet</th><th>Tutma</th><th>K/Z</th><th>K/Z %</th><th>Çıkış nedeni</th>
      </tr></thead><tbody>${rows || '<tr><td colspan="11" class="muted">Henüz kapanan işlem yok.</td></tr>'}</tbody></table></div>

      ${lots ? `<div class="row between mt"><b class="small">Açık pozisyonlar (henüz satılmadı)</b></div>
      <div class="result-scroll mt"><table class="result-table"><thead><tr>
        <th>Coin</th><th>Alış fiyatı</th><th>Adet</th><th>Yatırılan</th><th>Alış</th><th>Elde</th>
      </tr></thead><tbody>${lots}</tbody></table></div>` : ""}

      <div class="split mt">
        <div>
          <b class="small">Coin bazında</b>
          <div class="result-scroll mt"><table class="result-table"><thead><tr>
            <th>Coin</th><th>Tur</th><th>K/Y</th><th>Kazanma</th><th>K/Z</th><th>K/Z %</th><th>Ort. tutma</th>
          </tr></thead><tbody>${coinRows || '<tr><td colspan="7" class="muted">—</td></tr>'}</tbody></table></div>
        </div>
        <div>
          <b class="small">Çıkış nedeni</b>
          <div class="result-scroll mt"><table class="result-table"><thead><tr>
            <th>Neden</th><th>Tur</th><th>K/Z</th>
          </tr></thead><tbody>${reasonRows || '<tr><td colspan="3" class="muted">—</td></tr>'}</tbody></table></div>
        </div>
      </div>
      <p class="muted small" style="margin-top:12px">
        K/Z, komisyon dahil hesaplanır: alışta ödenen komisyon maliyete eklenir, satışta düşülür.
        Kısmi satışlarda tek alış birden çok tura bölünür.
      </p>`;
    return wrap;
  };
  modal("İşlem analizi", make());
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
          <label class="pf"><span>Varlık</span>${assetSelectHtml("p-asset", "crypto")}</label>
          <label class="pf"><span>Sembol</span>${symbolFieldHtml("p-coin", "BTCUSDT", { asset: "p-asset" })}</label>
          <label class="pf"><span>Periyot</span>${periodFieldHtml("p-period", "1h")}</label>
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
  bindSymbolField("p-coin", "p-asset", "p-period");
  bindPeriodField("p-period");

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
        body: {
          definition: definition(),
          coin: $("#p-coin").value.trim().toUpperCase(),
          period: readPeriod("p-period"),
          source: assetSourceOf($("#p-asset").value),
          asset_class: $("#p-asset").value,
        },
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
  let baseRisk = info.risk && typeof info.risk === "object" ? info.risk : {};
  if (spec && (spec.type === "custom" || spec.kind === "custom")) {
    const custom = (state.custom || []).find((x) => x.id === spec.id);
    if (custom && custom.definition && custom.definition.risk) baseRisk = custom.definition.risk;
  }
  const bRisk = (key) => {
    const v = baseRisk[key];
    return v === undefined || v === null || v === "" ? "" : v;
  };
  const btRisk = (fieldDef) => {
    const rec = fieldDef.rec[selected];
    const recText = rec === undefined ? "-" : String(rec);
    const value = bRisk(fieldDef.key);
    return `<div class="risk-num-field">
      <label class="risk-num-label" for="brk-${fieldDef.key}">
        ${esc(fieldDef.label)} <span class="risk-num-unit">${esc(fieldDef.unit)}</span>
      </label>
      <div class="risk-num-input">
        <input id="brk-${fieldDef.key}" type="number" min="0" step="${fieldDef.step}"
          value="${esc(value)}" placeholder="${esc(recText)}">
        <button type="button" class="risk-num-rec" data-brec="${fieldDef.key}">Önerilen: ${esc(recText)}</button>
      </div>
      <p class="risk-num-help">${esc(fieldDef.help)}</p>
    </div>`;
  };
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="row">
      ${field("Varlık", assetSelectHtml("bt-asset", info.assetClass || "crypto"))}
      ${field("Sembol", symbolFieldHtml("bt-coin", info.coin || "BTCUSDT", { asset: "bt-asset" }))}
      ${field("Periyot", periodFieldHtml("bt-period", selected))}
      ${field("Nakit", `<input id="bt-cash" type="number" value="100">`)}
      ${field("Mum sayısı", `<select id="bt-limit">${limitOptionsHtml(selected, 20000)}</select>`)}
      <button class="primary" id="bt-run">Çalıştır</button>
    </div>
    <div id="bt-estimate" class="muted small" style="margin:8px 0 0"></div>
    ${best ? `<div class="mt small">Ölçülen en iyi zaman dilimi: <b>${esc(best)}</b> ${summary}</div>` : ""}
    <details class="mt">
      <summary class="muted small" style="cursor:pointer">Risk kuralları (stop, kâr al, cooldown) — boş = tanımdan devral</summary>
      <div class="risk-num-grid mt" id="bt-risk-grid">
        ${RISK_NUM_FIELDS.map(btRisk).join("")}
      </div>
    </details>
    <p class="muted small" style="margin:8px 0 0">
      Trend stratejileri uzun geçmişte anlam kazanır. Kısa pencerede al-tut geçildi görünüyorsa
      daha uzun geçmiş seçin; yıllık tablo hangi yıllarda önde olduğunu gösterir.
      Çalıştırdıktan sonra <b>veri raporu</b> gerçekte kaç mum geldiğini, hangi tarih aralığını
      kapsadığını ve verinin temiz olup olmadığını gösterir.
    </p>
    <div id="bt-result" class="mt"></div>`;
  const estimate = () => {
    const lim = Number($("#bt-limit").value || 20000);
    const per = periodValueOf("bt-period") || "1h";
    const el = $("#bt-estimate");
    if (el) el.innerHTML = `${lim.toLocaleString("tr-TR")} mum × ${esc(per)} → <b>${limitSpanLabel(lim, per)}</b>. Gerçek süre çalıştırınca veri raporunda görünür.`;
  };
  modal("Backtest", wrap);
  bindSymbolField("bt-coin", "bt-asset", "bt-period");
  const bindBtRisk = () => {
    $$("[data-brec]").forEach((btn) => btn.addEventListener("click", () => {
      const fieldDef = RISK_NUM_FIELDS.find((f) => f.key === btn.dataset.brec);
      if (!fieldDef) return;
      const period = periodValueOf("bt-period") || "1h";
      const value = fieldDef.rec[period];
      const input = $(`#brk-${fieldDef.key}`);
      if (input && value !== undefined) {
        input.value = String(value);
        input.classList.add("just-set");
        setTimeout(() => input.classList.remove("just-set"), 700);
      }
    }));
  };
  bindBtRisk();
  bindPeriodField("bt-period");
  const onBtPeriod = () => {
    refreshLimitOptions($("#bt-limit"), periodValueOf("bt-period") || "1h");
    const period = periodValueOf("bt-period") || "1h";
    $$("#bt-risk-grid .risk-num-field").forEach((card) => {
      const key = card.querySelector("[data-brec]")?.dataset.brec;
      const fieldDef = RISK_NUM_FIELDS.find((f) => f.key === key);
      if (!fieldDef) return;
      const rec = fieldDef.rec[period];
      const btn = card.querySelector("[data-brec]");
      if (btn) btn.textContent = `Önerilen: ${rec === undefined ? "-" : rec}`;
      const input = card.querySelector("input");
      if (input) input.placeholder = rec === undefined ? "" : String(rec);
    });
    estimate();
  };
  $("#bt-period-preset").addEventListener("period-change", onBtPeriod);
  $("#bt-period").addEventListener("change", onBtPeriod);
  $("#bt-limit").addEventListener("change", estimate);
  $("#bt-asset").addEventListener("change", () => {
    const symbol = $("#bt-coin");
    const known = Object.values(ASSET_DEFAULT_SYMBOL);
    if (!symbol.value.trim() || known.includes(symbol.value.trim().toUpperCase())) {
      symbol.value = ASSET_DEFAULT_SYMBOL[$("#bt-asset").value] || "BTCUSDT";
    }
  });
  estimate();
  $("#bt-run").addEventListener("click", async () => {
    $("#bt-result").innerHTML = '<span class="muted">İş başlatıldı…</span>';
    try {
      const risk = {};
      ["stop_atr", "max_stop_pct", "static_stop_pct", "trail_atr", "trail_after_pct", "take_profit_atr",
       "take_profit_pct", "breakeven_pct", "partial_tp_pct", "partial_tp_fraction",
       "risk_per_trade_pct", "profit_exit_donchian", "cooldown", "cooldown_min_loss_pct"]
        .forEach((key) => {
          const el = $(`#brk-${key}`);
          const raw = el ? String(el.value || "").trim().replace(",", ".") : "";
          if (raw === "") return;
          const n = Number(raw);
          if (Number.isFinite(n)) risk[key] = Math.max(0, n);
        });
      const job = await api("/strategies/backtest", {
        method: "POST",
        body: {
          strategy: spec, coin: $("#bt-coin").value.trim().toUpperCase(),
          period: readPeriod("bt-period"), cash: Number($("#bt-cash").value),
          limit: Number($("#bt-limit").value || 20000),
          source: assetSourceOf($("#bt-asset").value),
          asset_class: $("#bt-asset").value,
          risk,
        },
      });
      pollJob(job.id, (j) => { $("#bt-result").innerHTML = renderBacktest(j); window.tcRedraw(); });
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
  const reasonLabels = { signal: "sinyal", time: "zaman limiti", stop: "stop", "takipli-stop": "takipli stop", trail: "takipli stop", breakeven: "breakeven", "profit-exit": "kâr koruma", "take-profit": "kâr al", "take-profit-partial": "kısmi kâr al", tp: "kâr al", end: "test sonu", manuel: "manuel satış", harici: "harici işlem", "destek-stop": "destek stop", "dinamik-stop": "dinamik stop", "statik-stop": "sabit stop" };
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
            r.risk.cooldown ? `çıkış sonrası ${r.risk.cooldown} mum bekleme${r.risk.cooldown_min_loss_pct ? ` (yalnızca zarar ≥ %${fmt(r.risk.cooldown_min_loss_pct, 1)})` : ""}` : "",
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
        <div id="tc-wrap"><span class="muted small">grafik hazırlanıyor…</span></div>
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
    const sourceLabel = { binance: "Binance", yahoo: "Yahoo Finance", tefas: "TEFAS" }[dr.source] || dr.source || "";
    const sourceBits = [];
    if (sourceLabel) sourceBits.push(`<span class="tag gray">${esc(sourceLabel)}</span>`);
    if (dr.resampled) sourceBits.push(`<span class="tag blue">${esc(dr.base_period || "")} → ${esc(dr.period || "")} yeniden örneklendi</span>`);
    if (dr.cached) sourceBits.push(`<span class="tag amber">yerel önbellek</span>`);
    const sourceNote = dr.has_ohlc === false
      ? `<div class="hint mt">Bu varlıkta yalnızca günlük fiyat (NAV) var. <b>open=high=low=close</b>, hacim 0 kabul edildi; high/low/hacim kullanan stratejilerin sonuçları yanıltıcı olabilir.</div>`
      : dr.intraday_limited
        ? `<div class="hint mt">Kaynak sağlayıcı intraday geçmişi sınırlıyor (Yahoo). Daha uzun geçmiş için günlük ve üstü periyot seçin.</div>`
        : dr.intraday_session
          ? `<div class="hint mt">Hisse/altın intraday serisinde gece, hafta sonu ve tatil araları normaldir; bunlar <b>eksik mum</b> sayılmadı.</div>`
          : "";
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
      ${sourceNote}
      <div class="muted small" style="margin:8px 0 0">${sourceBits.join(" ")}</div>
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
      ${field("Varlık", assetSelectHtml("cmp-asset", "crypto"))}
      ${field("Sembol", symbolFieldHtml("cmp-coin", "BTCUSDT", { asset: "cmp-asset" }))}
      ${field("Periyot", periodFieldHtml("cmp-period", "4h"))}
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
  modal("Tüm Stratejiler - Karşılaştırma", wrap);
  bindSymbolField("cmp-coin", "cmp-asset", "cmp-period");
  const updateEstimate = () => {
    const lim = Number($("#cmp-limit").value || 20000);
    const per = periodValueOf("cmp-period") || "4h";
    const el = $("#cmp-estimate");
    if (el) el.innerHTML = `${lim.toLocaleString("tr-TR")} mum × ${esc(per)} → <b>${limitSpanLabel(lim, per)}</b>. Gerçek aralık sonuç başlığında tarihlerle görünür.`;
  };
  bindPeriodField("cmp-period");
  const onCmpPeriod = () => {
    refreshLimitOptions($("#cmp-limit"), periodValueOf("cmp-period") || "4h");
    updateEstimate();
  };
  $("#cmp-period-preset").addEventListener("period-change", onCmpPeriod);
  $("#cmp-period").addEventListener("change", onCmpPeriod);
  $("#cmp-limit").addEventListener("change", updateEstimate);
  $("#cmp-asset").addEventListener("change", () => {
    const symbol = $("#cmp-coin");
    const known = Object.values(ASSET_DEFAULT_SYMBOL);
    if (!symbol.value.trim() || known.includes(symbol.value.trim().toUpperCase())) {
      symbol.value = ASSET_DEFAULT_SYMBOL[$("#cmp-asset").value] || "BTCUSDT";
    }
  });
  updateEstimate();
  $("#cmp-run").addEventListener("click", async () => {
    const meta = {
      coin: $("#cmp-coin").value.trim().toUpperCase() || "BTCUSDT",
      period: readPeriod("cmp-period"),
      cash: Number($("#cmp-cash").value) || 100,
      limit: Number($("#cmp-limit").value) || 20000,
      source: assetSourceOf($("#cmp-asset").value),
      asset_class: $("#cmp-asset").value,
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
      body: {
        strategy: row.spec, coin: meta.coin, period: meta.period,
        cash: meta.cash, limit: meta.limit,
        source: meta.source || "auto", asset_class: meta.asset_class || "",
      },
    });
    pollJob(job.id, (j) => {
      const el = $("#cmp-detail");
      if (el) el.innerHTML = renderBacktest(j);
      if (el) window.tcRedraw();
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
  const [builtin, custom, lists, aiModels] = await Promise.all([
    api("/strategies/builtin"), api("/strategies/custom"), api("/coin-lists"),
    api("/ai/models").catch(() => []),
  ]);
  const presetId = lists.some((l) => l.id === state.scanListId) ? state.scanListId : "";
  const preset = lists.find((l) => l.id === presetId);
  const opts = [
    ...builtin.filter((b) => !b.archived).map((b) => ({
      id: "builtin:" + b.name, name: b.label || b.name, spec: { type: "builtin", name: b.name },
    })),
    ...custom.filter((c) => c.status === "active").map((c) => ({ id: "custom:" + c.id, name: c.name, spec: { type: "custom", id: c.id, version: c.version } })),
    ...aiModels.filter((m) => m.status === "active").map((m) => ({ id: "ai:" + m.id, name: "AI · " + m.name, spec: { type: "ai", model_id: m.id } })),
  ];
  root.innerHTML = `
    <div class="card">
      <div class="row">
        ${field("Varlık sınıfı", assetSelectHtml("scan-asset", "crypto", true))}
        ${field("Periyot", periodFieldHtml("scan-period", "1h"))}
        ${field("Coin listesi", `<select id="scan-list">
          <option value="">— Tüm liste (coin_list.txt) —</option>
          ${lists.map((l) => `<option value="${esc(l.id)}" ${l.id === presetId ? "selected" : ""}>${esc(l.name)} (${l.count})</option>`).join("")}
        </select>`)}
        ${field("Semboller (boş = tüm liste)", symbolMultiFieldHtml("scan-coins", preset ? preset.coins.join(", ") : "", { asset: "scan-asset", placeholder: "BTCUSDT, XAUUSD, AAPL, TEFAS:AFT" }))}
        <button class="primary" id="scan-run">Taramayı Başlat</button>
      </div>
      <p class="muted small" id="scan-list-hint" style="margin:8px 0 0"></p>
      <div class="card mt" style="padding:10px"><div class="muted">Stratejiler</div>
        ${opts.map((o) => `<label class="check"><input type="checkbox" class="scan-strategy" value="${o.id}" checked> ${esc(o.name)}</label>`).join("")}
      </div>
    </div>
    <div id="scan-result" class="mt"></div>`;
  bindPeriodField("scan-period");
  bindAssetPeriods("scan-asset", "scan-period");
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
          period: readPeriod("scan-period"),
          strategies: specs,
          coins: $("#scan-coins").value.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean),
          list_id: $("#scan-list").value || null,
          source: assetSourceOf($("#scan-asset").value),
          asset_class: $("#scan-asset").value === "auto" ? "" : $("#scan-asset").value,
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
          ${field("Varlık", assetSelectHtml("an-asset", "crypto"))}
          ${field("Sembol", symbolFieldHtml("an-coin", "BTCUSDT", { asset: "an-asset" }))}
          ${field("Periyot", periodFieldHtml("an-period", "1h"))}
          ${field("Adet", `<input id="an-count" type="number" value="20" min="1" max="500">`)}
        </div>`,
        "Getir", "indicator_values")}
      ${tool(
        "M12 2 2 7l10 5 10-5-10-5Zm0 7.2L4.4 5.4 12 9.1l7.6-3.7L12 9.2ZM2 12l10 5 10-5v5l-10 5-10-5v-5Z",
        "Destek / Direnç",
        "Fiyatın altındaki destek ve üstündeki direnç seviyeleri.",
        `<div class="tool-fields">
          ${field("Varlık", assetSelectHtml("sr-asset", "crypto"))}
          ${field("Sembol", symbolFieldHtml("sr-coin", "BTCUSDT", { asset: "sr-asset" }))}
          ${field("Periyot", periodFieldHtml("sr-period", "1h"))}
          ${field("Fiyat (boş = son)", `<input id="sr-price" type="number" step="any">`)}
        </div>`,
        "Hesapla", "support_resistance")}
      ${tool(
        "M7 2h10a2 2 0 0 1 2 2v18l-4-2-3 2-3-2-4 2V4a2 2 0 0 1 2-2Zm1 5v2h8V7H8Zm0 4v2h8v-2H8Z",
        "Aylık sonuç",
        "Coin'in ay bazında toplam getirisi ve yükseliş/düşüş günleri.",
        `<div class="tool-fields">
          ${field("Varlık", assetSelectHtml("mo-asset", "crypto"))}
          ${field("Sembol", symbolFieldHtml("mo-coin", "BTCUSDT", { asset: "mo-asset" }))}
          ${field("Periyot", periodFieldHtml("mo-period", "1d"))}
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
          ${field("Varlık sınıfı", assetSelectHtml("mk-asset", "crypto", true))}
          ${field("Periyot", periodFieldHtml("mk-period", "1h"))}
          ${field("Semboller (boş = coin listesi)", symbolMultiFieldHtml("mk-coins", "", { asset: "mk-asset", placeholder: "BTCUSDT, XAUUSD, AAPL, TEFAS:AFT" }))}
          ${field("Maks coin", `<input id="mk-max" type="number" value="30" min="1">`)}
        </div>
        <div class="tool-checks">${opts.slice(0, 12).map((o) => `<label class="check"><input type="checkbox" class="mk-strategy" value="${o.id}"> ${esc(o.name)}</label>`).join("")}</div>`,
        "Analiz et", "market")}
      ${tool(
        "M4 4h16v2H4V4Zm0 5h16v2H4V9Zm0 5h10v2H4v-2Zm0 5h10v2H4v-2Z",
        "Coin listesi",
        "Borsadaki işlem gören coinleri listeler ve kaydeder.",
        `<div class="tool-fields">
          ${field("Periyot", periodFieldHtml("cl-period", "1h"))}
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
        "Model eğitimi, backtest ve bot entegrasyonu artık kendi sekmesinde.",
        `<div class="tool-note">Zaman serisi protokolü, walk-forward raporu ve model onayı için <b>AI Eğitimi</b> sekmesini kullanın.</div>`,
        "AI Eğitimi'ne git", "__goto_ai")}
    </div>

    <div id="analysis-result" class="mt"></div>`;
  bindSymbolField("an-coin", "an-asset", "an-period");
  bindSymbolField("sr-coin", "sr-asset", "sr-period");
  bindSymbolField("mo-coin", "mo-asset", "mo-period");
  ["an-period", "sr-period", "mo-period", "mk-period", "cl-period"].forEach(bindPeriodField);
  bindAssetPeriods("mk-asset", "mk-period");
  $$("[data-job]").forEach((btn) => btn.addEventListener("click", () => {
    if (btn.dataset.job === "__goto_ai") { location.hash = "#ai"; return; }
    runAnalysisJob(btn.dataset.job, opts, btn);
  }));
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
    body.coin = $("#an-coin").value.trim().toUpperCase(); body.period = readPeriod("an-period"); if (!body.period) return;
    body.count = Number($("#an-count").value);
    body.asset_class = $("#an-asset").value; body.source = assetSourceOf($("#an-asset").value);
  } else if (type === "support_resistance") {
    body.coin = $("#sr-coin").value.trim().toUpperCase(); body.period = readPeriod("sr-period"); if (!body.period) return;
    body.asset_class = $("#sr-asset").value; body.source = assetSourceOf($("#sr-asset").value);
    const price = $("#sr-price").value;
    body.price = price ? Number(price) : null;
  } else if (type === "market") {
    body.period = readPeriod("mk-period"); if (!body.period) return; body.max_coins = Number($("#mk-max").value);
    body.asset_class = $("#mk-asset").value === "auto" ? "" : $("#mk-asset").value;
    body.source = assetSourceOf($("#mk-asset").value);
    body.coins = String($("#mk-coins").value || "").split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    body.strategies = $$(".mk-strategy:checked")
      .map((cb) => (opts.find((o) => o.id === cb.value) || {}).spec)
      .filter(Boolean);
    if (!body.strategies.length) return toast("En az bir strateji seçin", true);
  } else if (type === "monthly") {
    body.coin = $("#mo-coin").value.trim().toUpperCase(); body.period = readPeriod("mo-period"); if (!body.period) return;
    body.asset_class = $("#mo-asset").value; body.source = assetSourceOf($("#mo-asset").value);
  } else if (type === "coinlist") {
    body.period = readPeriod("cl-period"); if (!body.period) return; body.sort = $("#cl-sort").checked;
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
function _toMs(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (Number.isFinite(n)) return n > 1e11 ? n : n * 1000;
  const t = new Date(String(value).replace(" ", "T")).getTime();
  return Number.isFinite(t) ? t : null;
}

/* İşlem satırına tıklanınca: bot nereden aldı, nereden sattı? */
window.tradeChart = async (tradeId) => {
  try {
    modal("İşlem grafiği", `<p class="muted">Grafik yükleniyor…</p>`);
    const d = await api(`/trades/${encodeURIComponent(tradeId)}/chart`);
    const candles = d.candles || [];
    const prices = candles.map((c, i) => ({
      idx: i, t: Number(c.time), o: Number(c.open), h: Number(c.high),
      l: Number(c.low), c: Number(c.close), v: Number(c.volume) || 0,
    }));
    const candleIdx = (ms) => {
      if (!candles.length || ms === null) return null;
      let best = 0;
      for (let i = 0; i < candles.length; i += 1) {
        if (Number(candles[i].time) <= ms) best = i;
        else break;
      }
      return best;
    };
    const marks = [];
    const entry = d.entry || null;
    const exit = d.exit || null;
    if (entry) {
      marks.push({
        idx: candleIdx(_toMs(entry.time)), t: _toMs(entry.time), no: 1,
        price: Number(entry.price), side: "buy", time: entry.time,
      });
    }
    if (exit) {
      marks.push({
        idx: candleIdx(_toMs(exit.time)), t: _toMs(exit.time), no: 1,
        price: Number(exit.price), side: "sell", time: exit.time,
        reason: exit.reason, pnl_pct: d.pnl_pct,
      });
    }
    const validMarks = marks.filter((m) => m.idx !== null && Number.isFinite(m.price));
    // Modal grafiği de yakınlaştırma/kaydırma kullanabilsin diye aynı
    // veri yuvasına yazılır (tcRedraw "tc-wrap" kapsayıcısını çizer).
    const fullLo = prices.length ? Number(prices[0].idx) : 0;
    const fullHi = prices.length ? Number(prices[prices.length - 1].idx) : 0;
    window.__btData = {
      markers: validMarks, price: prices, fullLo, fullHi, lo: fullLo, hi: fullHi,
      height: 400,
      entryPrice: entry ? Number(entry.price) : null,
      exitPrice: exit ? Number(exit.price) : null,
      label: `${d.coin || ""} ${d.period || ""}`.trim(),
    };
    const qty = Number((d.trade || {}).quantity) || 0;
    const pnlMoney = entry && exit ? (Number(exit.price) - Number(entry.price)) * qty : null;
    const pnlPct = d.pnl_pct;
    const hold = entry && exit ? (_toMs(exit.time) - _toMs(entry.time)) / 1000 : null;
    const after = d.after_exit || {};
    const afterText = exit && after.bars
      ? `<span>satış sonrası ${Number(after.bars)} mum · en yüksek <b class="${pnlClass(after.high_pct)}">${after.high_pct === null ? "—" : `${Number(after.high_pct) > 0 ? "+" : ""}${fmt(after.high_pct, 2)}%`}</b> · en düşük <b class="${pnlClass(after.low_pct)}">${after.low_pct === null ? "—" : `${Number(after.low_pct) > 0 ? "+" : ""}${fmt(after.low_pct, 2)}%`}</b></span>`
      : "";
    const entryTag = entry
      ? `<span class="tag green">AL</span> <b>${fmt(entry.price, 8)}</b> <span class="muted small">${esc(fmtTime(entry.time))}</span>`
      : `<span class="tag amber">eşleşen alış bulunamadı</span>`;
    const exitTag = exit
      ? `<span class="tag red">SAT</span> <b>${fmt(exit.price, 8)}</b> <span class="muted small">${esc(fmtTime(exit.time))}</span>`
      : `<span class="tag gray">henüz satılmadı</span>`;
    const body = `
      <div class="row between">
        <div>
          <h3 style="margin:0">${esc(d.coin)} · ${esc(d.period)}</h3>
          <p class="muted small" style="margin:4px 0 0">${candles.length} mum · yeşil üçgen alış, kırmızı üçgen satış</p>
        </div>
        <div class="pnl-value ${pnlClass(pnlPct)}" style="font-size:22px">
          ${pnlPct === null || pnlPct === undefined ? "—" : `${Number(pnlPct) > 0 ? "+" : ""}${fmt(pnlPct, 2)}%`}
        </div>
      </div>
      <div class="position-strip mt">
        <span>${entryTag}</span>
        <span>${exitTag}</span>
        <span>adet <b>${fmt(qty, 8)}</b></span>
        ${pnlMoney === null ? "" : `<span>K/Z <b class="${pnlClass(pnlMoney)}">${signedMoney(pnlMoney)}</b></span>`}
        ${hold === null ? "" : `<span>süre <b>${esc(uptimeText(hold))}</b></span>`}
        ${afterText}
        ${exit && exit.reason ? `<span>neden ${tradeReason(exit.reason)}</span>` : ""}
      </div>
      ${d.error ? `<p class="muted small mt">Grafik verisi alınamadı: ${esc(d.error)}</p>` : ""}
      ${d.price_consistent === false ? `<p class="mt"><span class="tag amber">mum verisi işlem fiyatlarıyla uyuşmuyor</span>
        <span class="muted small">Bu kayıt farklı bir sembol/eski fiyatla oluşmuş olabilir; grafik çizilmedi, işlem bilgileri yukarıda.</span></p>` : ""}
      <div class="row between mt" style="gap:8px;flex-wrap:wrap">
        <span class="muted small">tekerlek = yakınlaştır, sürükle = kaydır, fareyle üzerine gel = mum değerleri</span>
        <span class="row small" style="gap:8px">
          <button type="button" class="small ghost" onclick="window.tcZoom(1/1.7)" title="Yakınlaş">＋</button>
          <button type="button" class="small ghost" onclick="window.tcZoom(1.7)" title="Uzaklaş">−</button>
          <button type="button" class="small ghost" onclick="window.tcReset()" title="Tüm görünüm">Sıfırla</button>
        </span>
      </div>
      <div id="tc-wrap"></div>
      <p class="muted small mt">
        Yeşil kesikli çizgi alış, kırmızı kesikli çizgi satış seviyesidir; sağdaki balon son mumun kapanışıdır.
        Mumların üzerine fareyle gelince açılış/yüksek/düşük/kapanış değerleri görünür.
      </p>`;
    modal(`${d.coin} · ${(d.trade || {}).side === "BUY" ? "alış" : "satış"} işlemi`, body);
    // Grafik, modal yerleştikten sonra kapsayıcının gerçek genişliğiyle
    // çizilir; böylece viewBox oranı kutuyu tam doldurur ve imleç kaymaz.
    const wrap = document.getElementById("tc-wrap");
    renderTradeChart(wrap, prices, validMarks, {
      height: 400, lo: fullLo, hi: fullHi,
      extraPrices: validMarks.map((m) => Number(m.price)),
      entryPrice: entry ? Number(entry.price) : null,
      exitPrice: exit ? Number(exit.price) : null,
      hover: true,
    });
    const svg = wrap && wrap.querySelector("svg.trade-chart");
    if (svg && svg.dataset.chartId) {
      const geom = _chartGeom.get(svg.dataset.chartId);
      if (geom) window.__btData.chartWidth = geom.w;
    }
  } catch (err) {
    toast(err.message || "İşlem grafiği yüklenemedi", true);
  }
};

/* ------------------------------------------------------------------ */
/* Canlı izleme: açık pozisyon grafiği (10 saniyede bir)               */
/* ------------------------------------------------------------------ */
const LIVE_WATCH_MS = 10000;

function stopLiveWatch() {
  const current = window.__liveWatch;
  if (current && current.timer) clearInterval(current.timer);
  window.__liveWatch = null;
}

/** Canlı veriyi grafiğe uygular: mumlar + alış/stop/kâr al seviyeleri. */
function _applyLiveChart(data, initial) {
  const rows = Array.isArray(data.candles) ? data.candles : [];
  const prices = rows
    .map((c) => ({
      idx: Number(c.time), t: Number(c.time),
      o: Number(c.open), h: Number(c.high), l: Number(c.low), c: Number(c.close),
      v: Number(c.volume) || 0,
    }))
    .filter((p) => Number.isFinite(p.idx) && Number.isFinite(p.c) && p.c > 0);
  if (!prices.length) throw new Error("Mum verisi boş");

  const pos = data.position || {};
  const live = Number(data.live_price);
  // Son (devam eden) mumu canlı fiyatla güncelle: grafik 10 sn'de bir
  // "canlı" hissi versin, yeni bir mum gelene kadar kapanış takip etsin.
  const last = prices[prices.length - 1];
  if (Number.isFinite(live) && live > 0) {
    last.c = live;
    if (live > last.h) last.h = live;
    if (live < last.l) last.l = live;
    last.live = true;
  }

  const fullLo = Number(prices[0].idx);
  const fullHi = Number(prices[prices.length - 1].idx);

  // Alış anını ilgili muma yerleştir (mum verisi alıştan öncesini kapsar).
  const markers = [];
  const entryPrice = Number(pos.entry_price);
  const openedMs = _toMs(pos.opened_at);
  if (Number.isFinite(entryPrice) && entryPrice > 0) {
    let idx = fullHi;
    if (openedMs !== null) {
      idx = fullLo;
      for (const p of prices) {
        if (p.idx <= openedMs) idx = p.idx;
        else break;
      }
    }
    markers.push({
      idx, t: openedMs, no: 1, price: entryPrice, side: "buy",
      time: pos.opened_at,
    });
  }

  const refs = [];
  if (Number.isFinite(entryPrice) && entryPrice > 0) {
    refs.push({ value: entryPrice, color: "#34d399", label: "alış" });
  }
  const stop = Number(pos.stop_price);
  if (Number.isFinite(stop) && stop > 0) {
    refs.push({ value: stop, color: "#fb7185", label: "stop", band: "strong" });
  }
  const tp = Number(pos.take_profit_price);
  if (Number.isFinite(tp) && tp > 0) {
    refs.push({ value: tp, color: "#38bdf8", label: "kâr al" });
  }
  const partial = Number(pos.partial_target_price);
  if (Number.isFinite(partial) && partial > 0) {
    refs.push({ value: partial, color: "#fbbf24", label: "kısmi kâr" });
  }
  if (Number.isFinite(live) && live > 0) {
    refs.push({ value: live, color: "#e2e8f0", label: "canlı", band: "strong" });
  }

  // Yakınlaştırmada en az iki mum görünsün (ms tabanlı indekste "4" anlamsız).
  const steps = [];
  for (let i = 1; i < prices.length; i += 1) steps.push(prices[i].idx - prices[i - 1].idx);
  steps.sort((a, b) => a - b);
  const medianStep = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
  const minSpan = medianStep > 0 ? medianStep * 2 : undefined;

  const prev = window.__btData;
  const follow = initial || !prev || Number(prev.hi) >= Number(prev.fullHi) - 1;
  window.__btData = {
    markers,
    price: prices,
    fullLo,
    fullHi,
    lo: follow ? fullLo : Math.max(fullLo, Number(prev.lo)),
    hi: follow ? fullHi : Math.min(fullHi, Number(prev.hi)),
    minSpan,
    height: 400,
    refs,
    label: `${data.coin || ""} ${data.period || ""}`.trim(),
  };
}

function _liveWatchStrip(data) {
  const pos = data.position || {};
  const live = Number(data.live_price);
  const entry = Number(pos.entry_price);
  const stop = Number(pos.stop_price);
  const pct = Number(pos.pnl_gross_pct);
  const source = data.price_source === "live"
    ? (Number(data.price_age_seconds) > 30 ? `canlı · ${fmt(data.price_age_seconds, 0)} sn önce` : "canlı")
    : "mum kapanışı";
  const be = pos.breakeven_armed
    ? '<span class="tag amber" title="Kısmi kâr sonrası stop girişe çekildi">breakeven</span>'
    : "";
  const dist = stop > 0 && live > 0 ? ` (${fmt((live / stop - 1) * 100, 2)}% uzak)` : "";
  return `<div class="position-strip mt">
    <span class="tag amber">${esc(data.coin)}</span>
    <span>güncel <b class="${pnlClass(pct)}">${priceText(live)}</b>
      <span class="muted small">${esc(source)}</span></span>
    <span>alış <b>${priceText(entry)}</b></span>
    ${stop > 0 ? `<span>stop <b class="neg">${priceText(stop)}</b><span class="muted small">${esc(dist)}</span></span>` : ""}
    ${Number(pos.take_profit_price) > 0 ? `<span>kâr al <b>${priceText(pos.take_profit_price)}</b></span>` : ""}
    <span>K/Z <b class="${pnlClass(pct)}">${Number.isFinite(pct) ? `${pct > 0 ? "+" : ""}${fmt(pct, 2)}%` : "—"}</b></span>
    <span>adet <b>${fmt(pos.quantity, 8)}</b></span>
    ${be}
  </div>`;
}

/** Açık pozisyonu canlı izle: mum grafiği + alış/stop seviyeleri. */
window.openLiveChart = async (botId) => {
  stopLiveWatch();
  const bot = (state.bots || []).find((b) => b.id === botId) || {};
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="row between" style="flex-wrap:wrap;gap:10px">
      <div>
        <h3 style="margin:0" id="live-title">${esc(bot.name || botId)}</h3>
        <p class="muted small" style="margin:4px 0 0" id="live-sub">Grafik yükleniyor…</p>
      </div>
      <div class="row" style="gap:8px;align-items:center">
        <span class="status-dot on" title="Canlı izleme açık"></span>
        <span class="muted small" id="live-ago">—</span>
      </div>
    </div>
    <div id="live-strip"></div>
    <div class="row between mt" style="gap:8px;flex-wrap:wrap">
      <span class="muted small">tekerlek = yakınlaştır · sürükle = kaydır · Shift+tekerlek = yana kaydır · çift tıkla = sıfırla</span>
      <span class="row small" style="gap:8px">
        <button type="button" class="small ghost" onclick="window.tcZoom(1/1.7)" title="Yakınlaş">＋</button>
        <button type="button" class="small ghost" onclick="window.tcZoom(1.7)" title="Uzaklaş">−</button>
        <button type="button" class="small ghost" onclick="window.tcReset()" title="Tüm görünüm (çift tıklama)">Sıfırla</button>
        <button type="button" class="small ghost" id="live-more" title="Daha eski mumları yükle">Daha fazla geçmiş</button>
      </span>
    </div>
    <div id="tc-wrap"></div>
    <p class="muted small mt">
      Yeşil kesikli çizgi <b>alış</b>, kırmızı düz çizgi <b>stop</b>, mavi çizgi <b>kâr al</b>,
      açık çizgi <b>canlı fiyat</b>. Grafik <b>10 saniyede bir</b> kendini günceller.
    </p>`;
  modal(`Canlı izle · ${bot.name || botId}`, wrap);

  const watch = { timer: null, data: null, botId, failures: 0, limit: 150 };
  window.__liveWatch = watch;

  const drawNow = (initial) => {
    const data = watch.data;
    if (!data) return;
    _applyLiveChart(data, initial);
    const chartWrap = document.getElementById("tc-wrap");
    if (!chartWrap) return;
    // Görünür aralık, yakınlaştırma ve referans çizgileri tcRedraw'da uygulanır.
    tcRedraw();
    const svg = chartWrap.querySelector("svg.trade-chart");
    if (svg && svg.dataset.chartId) {
      const geom = _chartGeom.get(svg.dataset.chartId);
      if (geom) window.__btData.chartWidth = geom.w;
    }
    const strip = document.getElementById("live-strip");
    if (strip) strip.innerHTML = _liveWatchStrip(data);
    const sub = document.getElementById("live-sub");
    if (sub) {
      const d = window.__btData || {};
      sub.textContent = `${data.coin} · ${data.period} · ${(d.price || []).length} mum · ${data.provider || "—"}`
        + `${data.mode ? ` · ${data.mode === "live" ? "CANLI" : "test"}` : ""}`;
    }
  };

  const load = async (initial, opts = {}) => {
    try {
      // "Daha fazla geçmiş": sağ kenar korunur, sola doğru genişletilir.
      const prevHi = window.__btData ? Number(window.__btData.hi) : null;
      const data = await api(
        `/bots/${encodeURIComponent(botId)}/live-chart?candles=${watch.limit}`
      );
      watch.data = data;
      watch.failures = 0;
      drawNow(initial);
      if (opts.expandToLeft && prevHi !== null && window.__btData) {
        const d = window.__btData;
        d.hi = Math.min(prevHi, d.fullHi);
        d.lo = d.fullLo;
        tcRedraw();
      }
      const ago = document.getElementById("live-ago");
      if (ago) {
        const now = new Date();
        ago.textContent = `son güncelleme ${now.toLocaleTimeString("tr-TR")}`;
      }
    } catch (err) {
      // Pozisyon kapandıysa izlemeyi bitir (sunucu 409 döner).
      if (err && err.status === 409) {
        stopLiveWatch();
        const ago = document.getElementById("live-ago");
        if (ago) ago.innerHTML = '<span class="tag gray">pozisyon kapandı</span>';
        const sub = document.getElementById("live-sub");
        if (sub) sub.textContent = "Bu botta açık pozisyon kalmadı; canlı izleme durduruldu.";
        if (!watch.data) {
          const chartWrap = document.getElementById("tc-wrap");
          if (chartWrap) chartWrap.innerHTML = chartEmpty(320, "Açık pozisyon yok");
        }
        return;
      }
      watch.failures += 1;
      const ago = document.getElementById("live-ago");
      if (ago) {
        ago.innerHTML = `<span class="neg">güncellenemedi (${watch.failures})</span>`;
      }
      if (initial) {
        const sub = document.getElementById("live-sub");
        if (sub) sub.innerHTML = `<span class="neg">${esc(err.message || "veri alınamadı")}</span>`;
        const strip = document.getElementById("live-strip");
        if (strip) strip.innerHTML = "";
        const chartWrap = document.getElementById("tc-wrap");
        if (chartWrap) chartWrap.innerHTML = chartEmpty(320, "Grafik verisi alınamadı");
      }
      // Sonraki turlarda eski grafik korunur; kullanıcı kesintiyi görür.
    }
  };

  await load(true);

  // Daha fazla geçmiş: mum sayısını artır, sağ kenarı koruyarak sola genişlet.
  const moreBtn = document.getElementById("live-more");
  if (moreBtn) {
    moreBtn.addEventListener("click", async () => {
      if (watch.limit >= 400) return;
      moreBtn.disabled = true;
      watch.limit = Math.min(400, watch.limit + 250);
      await load(false, { expandToLeft: true });
      moreBtn.disabled = false;
      if (watch.limit >= 400) {
        moreBtn.textContent = "Tüm geçmiş yüklendi";
        moreBtn.disabled = true;
      }
    });
  }

  if (!window.__liveWatch) return;
  watch.timer = setInterval(() => {
    // Modal kapandıysa veya başka bir grafik açıldıysa dur.
    if (window.__liveWatch !== watch || !document.getElementById("tc-wrap")) {
      stopLiveWatch();
      return;
    }
    load(false);
  }, LIVE_WATCH_MS);
};

async function renderTrades(root) {
  const [trades, history, summary, positions, stats, bots] = await Promise.all([
    api("/trades?limit=200"),
    // Tur eşleştirmesi başarısız olsa da sayfa açılsın (ham emirler görünür).
    api("/trades/history?limit=2000").catch(() => ({ trades: [], open: [] })),
    api("/summary"), api("/positions?status=open"), api("/stats"), api("/bots"),
  ]);
  const historyTours = history.trades || [];
  const historyOpen = history.open || [];
  const historyLimited = !!history.limited;
  const historyOrders = Number(history.orders || 0);
  const total = summary.total || {};
  const t = stats.totals || {};
  const eqPoints = stats.equity || [];
  const eq = eqPoints.map((p) => Number(p.value));
  const eqLast = eq.length ? eq[eq.length - 1] : null;
  const eqPct = eqPoints.length ? Number(eqPoints[eqPoints.length - 1].pct) : null;
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
          <div><h3>Kümülatif K/Z</h3><p class="muted small">Kapanan işlemlerin net K/Z'si (komisyon dahil, USDT)</p></div>
          <span class="chart-big ${eqLast === null ? "" : eqLast >= 0 ? "pos" : "neg"}">${eqLast === null ? "—" : signedMoney(eqLast)}</span>
        </div>
        ${lineChart(eq, { height: 220, caption: `${eq.length} kapanan işlem${eqPct === null ? "" : ` · ${eqPct >= 0 ? "+" : ""}${fmt(eqPct, 2)}% getiri`}` })}
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
        <div class="row between"><h3>Coin bazında K/Z</h3><span class="tag gray">net USDT</span></div>
        ${barChart(coinItems, { height: 190 })}
      </div>
      <div class="card chart-card">
        <div class="row between"><h3>Günlük K/Z</h3><span class="tag gray">son 14 gün</span></div>
        ${barChart(daily, { height: 190 })}
      </div>
    </div>

    <div class="card mt">
      <div class="row between" style="flex-wrap:wrap;gap:10px">
        <div>
          <h3 style="margin:0">İşlemler</h3>
          <p class="muted small" style="margin:3px 0 0">
            Her satır bir alım–satım turudur; alış ve satış fiyatı ayrı gösterilir.
            Satıra tıkla → grafikte nereden alınıp nereden satıldığını gör.
          </p>
        </div>
        <div class="row small" style="gap:8px;align-items:center">
          <button type="button" class="small" id="tr-mode-tours">Turlar</button>
          <button type="button" class="small ghost" id="tr-mode-orders">Ham emirler</button>
          <a class="small" href="/api/export.csv" target="_blank">CSV indir</a>
        </div>
      </div>
      <div id="tr-view-tours" class="mt">
        <div style="overflow:auto"><table class="tr-table"><thead><tr>
          <th>Giriş / Kapanış</th><th>Bot</th><th>Coin</th><th>Adet</th>
          <th>Alış fiyatı</th><th>Satış fiyatı</th><th>K/Z</th><th>Neden</th>
        </tr></thead><tbody>
        ${historyTours.map((tr) => `<tr class="trade-row clickable" onclick="window.tradeChart(${Number(tr.exit_id)})"
            title="Giriş: ${tr.entry_price == null ? "eşleşmedi" : `${esc(fmtTime(tr.entry_time))} · ${priceText(tr.entry_price)}`} → Çıkış: ${esc(fmtTime(tr.exit_time))} · ${priceText(tr.exit_price)}">
          <td class="mono small">${tr.entry_time ? esc(shortStamp(tr.entry_time)) : "—"}
            <span class="muted">→</span> ${esc(shortStamp(tr.exit_time))}
            ${tr.hold_seconds ? `<br><span class="muted">${esc(uptimeText(tr.hold_seconds))}</span>` : ""}</td>          <td>${esc(tr.bot_name || tr.bot_id || "—")}</td>
          <td>${esc(tr.coin)}
            ${tr.mode === "live" ? '<span class="tag amber tiny">canlı</span>' : '<span class="tag gray tiny">test</span>'}
            ${tr.partial ? '<span class="tag amber tiny" title="Pozisyonun bir kısmı satıldı">kısmi</span>' : ""}</td>
          <td class="mono">${priceText(tr.quantity)}</td>
          <td class="mono px-buy"${tr.unmatched ? ' title="Bu satışın alışı görünen kayıtlarda yok"' : ""}>${tr.entry_price == null ? "—" : priceText(tr.entry_price)}</td>
          <td class="mono px-sell">${priceText(tr.exit_price)}</td>
          <td>${tr.pnl_pct == null ? '<span class="muted">—</span>' : `${pct(tr.pnl_pct)}<br><span class="muted small ${pnlClass(tr.pnl_money)}">${signedMoney(tr.pnl_money)}</span>`}</td>
          <td>${tradeReason(tr.exit_reason)}</td>
        </tr>`).join("") || '<tr><td colspan="8" class="muted">Henüz kapanan işlem yok.</td></tr>'}
        </tbody></table></div>
        ${historyOpen.length ? `
        <h4 class="mt">Açık pozisyonlar</h4>
        <div style="overflow:auto"><table class="tr-table"><thead><tr>
          <th>Giriş</th><th>Bot</th><th>Coin</th><th>Adet</th><th>Alış fiyatı</th><th>Yatırılan</th>
        </tr></thead><tbody>
        ${historyOpen.map((tr) => `<tr>
          <td class="mono">${esc(fmtIso(tr.entry_time))}</td>
          <td>${esc(tr.bot_name || tr.bot_id || "—")}</td>
          <td>${esc(tr.coin)}</td>
          <td class="mono">${priceText(tr.quantity)}</td>
          <td class="mono px-buy">${priceText(tr.entry_price)}</td>
          <td class="mono">${money(tr.invested)}</td>
        </tr>`).join("")}
        </tbody></table></div>` : ""}
        ${historyLimited ? `<p class="muted small mt">Yalnızca son ${fmt(historyOrders, 0)} emir eşleştirildi.</p>` : ""}
      </div>
      <div id="tr-view-orders" class="mt hidden">
        <div style="overflow:auto"><table class="tr-table"><thead><tr>
          <th>Zaman</th><th>Bot</th><th>Coin</th><th>Yön</th><th>Adet</th><th>Fiyat</th><th>K/Z</th><th>Neden</th>
        </tr></thead><tbody>
        ${trades.map((tr) => `<tr class="trade-row clickable" onclick="window.tradeChart(${Number(tr.id)})" title="Grafikte alış/satışı gör">
          <td class="mono">${esc(fmtIso(tr.created_at))}</td>
          <td>${esc(tr.bot_name || tr.bot_id || "—")}</td><td>${esc(tr.coin)}
            ${tr.mode === "live" ? '<span class="tag amber tiny">canlı</span>' : '<span class="tag gray tiny">test</span>'}</td>
          <td>${tr.side === "BUY" ? '<span class="tag green">AL</span>' : '<span class="tag red">SAT</span>'}</td>
          <td class="mono">${priceText(tr.quantity)}</td>
          <td class="mono ${tr.side === "BUY" ? "px-buy" : "px-sell"}">${priceText(tr.price)}</td>
          <td>${tr.pnl_pct == null ? "—" : pct(tr.pnl_pct)}</td><td>${tradeReason(tr.reason)}</td></tr>`).join("") || '<tr><td colspan="8" class="muted">Henüz işlem yok.</td></tr>'}
        </tbody></table></div>
      </div>
    </div>

    <div class="card danger-card mt">
      <h3 style="margin:0">İstatistikleri sıfırla</h3>
      <p class="muted small" style="margin:4px 0 0">
        İşlem geçmişi, K/Z grafikleri, sinyal/olay kayıtları, kapanmış pozisyonlar ve bitmiş iş
        kayıtları silinir; botların birikmiş K/Z sayacı sıfırlanır.
        <b>Açık pozisyonlar ve nakit korunur</b>; botlar durdurulur (sonra Botlar sayfasından başlatılır).
      </p>
      <div class="row mt">
        ${field("Bot", `<select id="tr-reset-bot">
          <option value="">Tüm botlar</option>
          ${(bots || []).map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("")}
        </select>`)}
        ${field("Şifre", `<input id="tr-reset-pass" type="password">`)}
        ${field("Onay metni", `<input id="tr-reset-confirm" placeholder="SIFIRLA">`)}
        <button class="danger" id="tr-reset-btn" type="button">İstatistikleri sıfırla</button>
      </div>
    </div>`;

  $("#tr-mode-tours").addEventListener("click", () => {
    $("#tr-view-tours").classList.remove("hidden");
    $("#tr-view-orders").classList.add("hidden");
    $("#tr-mode-tours").classList.remove("ghost");
    $("#tr-mode-orders").classList.add("ghost");
  });
  $("#tr-mode-orders").addEventListener("click", () => {
    $("#tr-view-orders").classList.remove("hidden");
    $("#tr-view-tours").classList.add("hidden");
    $("#tr-mode-orders").classList.remove("ghost");
    $("#tr-mode-tours").classList.add("ghost");
  });

  $("#tr-reset-btn").addEventListener("click", async () => {
    const confirmText = $("#tr-reset-confirm").value.trim();
    if (confirmText.toUpperCase() !== "SIFIRLA") { toast("Onay metni 'SIFIRLA' olmalı", true); return; }
    const botId = $("#tr-reset-bot").value;
    const ok = await confirmDialog(
      "İstatistikleri sıfırla",
      `İstatistikler silinecek (${botId ? "seçili bot" : "tüm botlar"}). Açık pozisyonlar ve nakit korunur; botlar durdurulur. Emin misin?`,
      "Sıfırla",
      true,
    );
    if (!ok) return;
    try {
      const body = { password: $("#tr-reset-pass").value, confirm: confirmText };
      if (botId) body.bot_id = botId;
      const res = await api("/settings/danger/reset-stats", { method: "POST", body });
      const d = res.deleted || {};
      toast(`Sıfırlandı (${res.scope === "all" ? "tüm botlar" : res.scope}): ` +
        Object.entries(d).map(([k, v]) => `${k} ${v}`).join(", "));
      route();
    } catch (e) { toast(e.message, true); }
  });
}

/* ------------------------------------------------------------------ */
/* Ayarlar                                                             */
/* ------------------------------------------------------------------ */
/* ------------------------------------------------------------------ */
/* AI eğitimi                                                          */
/* ------------------------------------------------------------------ */
function aiStatusTag(status) {
  const map = { active: ["green", "aktif"], candidate: ["blue", "aday"], archived: ["gray", "arşiv"] };
  const [cls, text] = map[status] || ["gray", status || "-"];
  return `<span class="tag ${cls}">${esc(text)}</span>`;
}

function aiTrainingReport(report) {
  if (!report || !report.test) return '<span class="muted">Rapor yok.</span>';
  const test = (report.test && report.test.trading) || {};
  const ref = report.refinement || {};
  const timing = ref.timing || {};
  const mdl = report.model || {};
  const spec = report.spec || {};
  const heads = mdl.models || [];
  const first = heads[0] || {};
  const curve = first.curve || [];
  const trainCurve = curve.map((c) => Number(c.train_loss));
  const valCurve = curve.map((c) => Number(c.val_loss));
  const scores = (ref.history || []).map((h) => Number(h.score));
  const groups = (spec.feature_groups || []).length;
  const arch = archSummaryText(spec.engine, first, spec);
  const mode = spec.output_mode === "ternary" ? "nötr / dip / zirve"
    : spec.output_mode === "regression" ? "gelecek getiri" : 'AL + SAT';
  return `
    <div class="stat-grid">
      <div class="stat"><span>Test getirisi</span><b class="${pnlClass(test.total_return_pct)}">${fmt(test.total_return_pct, 1)}%</b><small>al-tut ${fmt(test.buy_hold_pct, 1)}%</small></div>
      <div class="stat"><span>Edge</span><b class="${pnlClass(test.edge_pct)}">${fmt(test.edge_pct, 1)}%</b><small>${fmt(test.trade_count, 0)} işlem</small></div>
      <div class="stat"><span>Kazanma</span><b>${fmt(test.win_rate, 1)}%</b><small>maks. düşüş ${fmt(test.max_drawdown_pct, 1)}%</small></div>
      <div class="stat"><span>Model</span><b class="small">${fmt(mdl.params, 0)}</b><small>parametre · ${groups} grup</small></div>
    </div>
    <div class="row small muted" style="gap:8px;flex-wrap:wrap;margin-top:8px">
      <span class="tag blue">${esc(spec.engine || "mlp")} · ${esc(arch)}</span>
      <span class="tag blue">${esc(mode)}</span>
      ${first.epochs_run ? `<span class="tag ${first.stopped_early ? "green" : "gray"}">${fmt(first.epochs_run, 0)} epoch · en iyi ${fmt(first.best_epoch, 0)}${first.stopped_early ? " (erken durdu)" : ""}</span>` : ""}
      ${ref.iterations_run ? `<span class="tag blue">${ref.iterations_run} iyileştirme turu · en iyi tur ${ref.best_iteration}</span>` : ""}
      ${report.threshold_adjustment && report.threshold_adjustment.reason ? `<span class="tag gray">${esc(report.threshold_adjustment.reason)}</span>` : ""}
    </div>
    ${timing.trades ? `<div class="row small" style="gap:8px;flex-wrap:wrap;margin-top:8px">
      <span class="tag gray">Giriş: erken ${timing.entry ? timing.entry.erken : 0} · geç ${timing.entry ? timing.entry["geç"] : 0} · zamanında ${timing.entry ? timing.entry["zamanında"] : 0}</span>
      <span class="tag gray">Çıkış: erken ${timing.exit ? timing.exit.erken : 0} · geç ${timing.exit ? timing.exit["geç"] : 0} · zamanında ${timing.exit ? timing.exit["zamanında"] : 0}</span>
      <span class="tag gray">ort. giriş hatası ${fmt(timing.avg_entry_error_pct, 2)}% · çıkış ${fmt(timing.avg_exit_error_pct, 2)}%</span>
    </div>` : ""}
    ${curve.length ? `<div class="split mt">
      <div><div class="muted small">Eğitim kaybı</div>${sparkline(trainCurve, { width: 260, height: 46 })}</div>
      <div><div class="muted small">Doğrulama kaybı</div>${sparkline(valCurve, { width: 260, height: 46 })}</div>
      ${scores.length > 1 ? `<div><div class="muted small">Tur skorları (validation)</div>${sparkline(scores, { width: 260, height: 46 })}</div>` : ""}
    </div>` : ""}
    ${(first.top_features || []).length ? `<div class="muted small" style="margin-top:8px">En etkili özellikler: ${(first.top_features || []).slice(0, 8).map((f) => `<span class="mono">${esc(f.feature)}</span> (${fmt(f.weight * 100, 1)}%)`).join(" · ")}</div>` : ""}
  `;
}

function aiMetricsHtml(m) {
  const test = (m.metrics && m.metrics.test) || {};
  const buy = (m.metrics && m.metrics.buy) || {};
  const sell = (m.metrics && m.metrics.sell) || {};
  const wf = (m.metrics && m.metrics.walk_forward) || {};
  const ref = (m.metrics && m.metrics.refinement) || {};
  const mdl = (m.metrics && m.metrics.model) || {};
  const lineage = (m.metrics && m.metrics.lineage) || {};
  const agrTest = ((m.metrics || {}).agreement || {}).test || {};
  const timing = ref.timing || {};
  const params = m.params || {};
  const ret = Number(test.total_return_pct || 0);
  const edge = Number(test.edge_pct || 0);
  const groups = params.feature_groups || [];
  const archText = archSummaryText(params.engine, mdl, params);
  const modeText = params.output_mode === "ternary" ? "nötr/dip/zirve"
    : params.output_mode === "regression" ? "gelecek getiri" : 'AL + SAT';
  const top = (mdl.top_features || []).slice(0, 6);
  const timingChips = timing && timing.trades
    ? `<span class="tag gray" title="Giriş zamanlaması">Giriş: erken ${timing.entry ? timing.entry.erken : 0} · geç ${timing.entry ? timing.entry["geç"] : 0} · zamanında ${timing.entry ? timing.entry["zamanında"] : 0}</span>
       <span class="tag gray" title="Çıkış zamanlaması">Çıkış: erken ${timing.exit ? timing.exit.erken : 0} · geç ${timing.exit ? timing.exit["geç"] : 0} · zamanında ${timing.exit ? timing.exit["zamanında"] : 0}</span>`
    : "";
  return `<div class="stat-grid">
    <div class="stat"><span>Test getirisi</span><b class="${pnlClass(ret)}">${fmt(ret, 1)}%</b><small>al-tut: ${fmt(test.buy_hold_pct, 1)}%</small></div>
    <div class="stat"><span>Fark (edge)</span><b class="${pnlClass(edge)}">${fmt(edge, 1)}%</b><small>al-tut'a karşı</small></div>
    <div class="stat"><span>İşlem / kazanma</span><b>${fmt(test.trade_count, 0)}</b><small>${fmt(test.win_rate, 1)}% kazanan</small></div>
    <div class="stat"><span>Maks. düşüş</span><b class="neg">${fmt(test.max_drawdown_pct, 1)}%</b><small>${test.avg_candles ? `ort. ${fmt(test.avg_candles, 1)} mum / işlem` : "test dönemi"}</small></div>
  </div>
  <div class="row small muted" style="gap:8px;flex-wrap:wrap;margin-top:6px">
    ${(() => { const q = ((m.metrics || {}).quality || {}).robust || {}; return q.score === undefined ? "" : `<span class="tag ${Number(q.score) > 0 ? "green" : "amber"}" title="3 pencereli işlem kalitesi">Kalite ${fmt(q.score, 1)} · ${fmt(q.positive_windows, 0)}/${fmt(q.windows, 0)} pencere</span>`; })()}
    ${agrTest.f1 !== undefined ? `<span class="tag ${Number(agrTest.f1) > 0.25 ? "green" : "amber"}">Local_Min_Max uyumu ${fmt(Number(agrTest.f1) * 100, 1)}%</span>` : ""}
    ${(agrTest.robust || {}).f1 != null ? `<span class="tag blue" title="Öğrenme bölgesinin 3 ayrı penceresi; test kullanılmaz">Genelleme (3 pencere) ${fmt(Number(agrTest.robust.f1) * 100, 1)}%</span>` : ""}
    ${agrTest.buy ? `<span class="tag gray">AL isabet ${fmt(agrTest.buy.precision, 2)} · yakalama ${fmt(agrTest.buy.recall, 2)}</span>` : ""}
    ${agrTest.sell ? `<span class="tag gray">SAT isabet ${fmt(agrTest.sell.precision, 2)} · yakalama ${fmt(agrTest.sell.recall, 2)}</span>` : ""}
    <span class="tag blue">${esc(params.engine || "mlp")} · ${esc(archText)}</span>
    <span class="tag blue">${esc(modeText)}</span>
    <span class="tag gray">${groups.length} özellik grubu · ${fmt(mdl.params, 0)} parametre</span>
    ${mdl.epochs ? `<span class="tag ${mdl.stopped_early ? "green" : "gray"}">${fmt(mdl.epochs, 0)} epoch · en iyi ${fmt(mdl.best_epoch, 0)}${mdl.stopped_early ? " (erken durdu)" : ""}</span>` : ""}
    <span class="tag gray">AL precision ${fmt(buy.precision, 2)} · recall ${fmt(buy.recall, 2)}</span>
    <span class="tag gray">SAT precision ${fmt(sell.precision, 2)} · recall ${fmt(sell.recall, 2)}</span>
    <span class="tag gray">eşik AL ${fmt(m.thresholds && m.thresholds.buy, 2)} / SAT ${fmt(m.thresholds && m.thresholds.sell, 2)}</span>
    ${ref.iterations_run ? `<span class="tag blue">iyileştirme ${ref.iterations_run} tur · en iyi tur ${ref.best_iteration}</span>` : ""}
    ${lineage.generation ? `<span class="tag ${lineage.warm_start_used ? "green" : "gray"}">nesil ${fmt(lineage.generation, 0)}${lineage.warm_start_used ? " · öncekinden devam" : " · sıfırdan"}</span>` : ""}
    ${wf.folds ? `<span class="tag ${Number(wf.avg_edge_pct) > 0 ? "green" : "gray"}">WF ${wf.folds} kat · ort. edge ${fmt(wf.avg_edge_pct, 1)}% · ${wf.positive_folds}/${wf.folds} pozitif</span>` : ""}
    ${timingChips}
  </div>
  ${top.length ? `<div class="muted small" style="margin-top:6px">En etkili özellikler: ${top.map((f) => `<span class="mono">${esc(f.feature)}</span> (${fmt(f.weight * 100, 1)}%)`).join(" · ")}</div>` : ""}`;
}

async function renderAI(root) {
  const [status, models, auto, arch, ds, profile] = await Promise.all([
    api("/ai/status"),
    api("/ai/models?include_archived=true"),
    api("/ai/autopilot"),
    api("/ai/architecture"),
    api("/ai/datasets").catch(() => ({ items: [] })),
    api("/ai/profile").catch(() => ({ profile: {}, last: {} })),
  ]);
  const prof = profile.profile || {};
  const lastAuto = profile.last || {};
  // Uğraşma düzeyleri yanıtın kökünde gelir; profilde yoksa güvenli varsayılan.
  const effortLevels = (profile.effortLevels && Object.keys(profile.effortLevels).length)
    ? profile.effortLevels
    : {
        quick: { label: "Hızlı", desc: "Tek mimari, az tur. Birkaç dakikada sonuç." },
        balanced: { label: "Dengeli", desc: "Önerilen. Birkaç mimari dener, hatalardan ders alır." },
        thorough: { label: "Titiz", desc: "En çok mimari ve tur. En uzun süre." },
      };
  const effort = prof.effort && effortLevels[prof.effort] ? prof.effort : "balanced";
  const cfg = auto.settings || {};
  const presets = auto.presets || [];
  const spec = auto.spec || arch.defaults;
  const groups = arch.feature_groups || [];
  const engines = arch.engines || [];
  const modes = arch.output_modes || [];
  const activations = arch.activations || [];
  const specGroups = spec.feature_groups || [];
  const datasetList = ds.items || [];
  const pinnedId = String(cfg.dataset_id || "");
  const pinned = datasetList.find((d) => d.id === pinnedId) || null;
  const dsName = (d) => `${d.coin} · ${d.period} · ${fmt(d.rows, 0)} mum`;
  const dsRow = (d) => {
    const isPinned = d.id === pinnedId;
    const size = d.size_bytes ? `${fmt(Number(d.size_bytes) / 1024, 0)} KB` : "";
    const when = String(d.created_at || "").slice(0, 16).replace("T", " ");
    return `<div class="ds-row ${isPinned ? "is-pinned" : ""}">
      <div class="ds-main">
        <b>${esc(d.coin)} · ${esc(d.period)}</b>
        <span class="muted small">${fmt(d.rows, 0)} mum · ${esc(when)}${size ? " · " + esc(size) : ""}</span>
      </div>
      <div class="row" style="gap:6px">
        ${isPinned
          ? '<span class="tag green">sabit</span>'
          : `<button class="small" data-ds-pin="${esc(d.id)}" type="button">Sabitle</button>`}
        <button class="ghost small" data-ds-del="${esc(d.id)}" type="button">Sil</button>
      </div>
    </div>`;
  };

  /* Yardımcı: açıklamalı + "önerilen" düğmeli alan */
  const pfField = (label, inputHtml, help, recValue, recText) => `
    <div class="pf-field">
      <label class="pf-label">${esc(label)}${inputHtml}</label>
      <p class="pf-help">${help}</p>
      ${recValue === undefined || recValue === null ? "" : `<button type="button" class="pf-rec" data-pfrec="${esc(String(recValue))}" data-pftarget="${esc(label)}">Önerilen: ${esc(recText ?? recValue)}</button>`}
    </div>`;

  const recFor = (period) => {
    const map = {
      "15m": { horizon: 24, target: 1.0, stop: 1.0 },
      "1h": { horizon: 12, target: 1.0, stop: 1.0 },
      "4h": { horizon: 6, target: 1.5, stop: 1.5 },
      "1d": { horizon: 3, target: 2.5, stop: 2.0 },
    };
    return map[period] || map["1h"];
  };
  const rec = recFor(prof.period || "1h");

  const masterCard = `<div class="card mt ai-master-card">
    <div class="row between" style="align-items:flex-start">
      <div>
        <div class="row" style="gap:10px;align-items:center">
          <h3 style="margin:0">Modeli eğit</h3>
          <span class="tag green">LSTM · Transformer · kâr odaklı</span>
        </div>
        <p class="muted small" style="margin:6px 0 0;max-width:760px">
          Model son <b>24 mumun gidişatını</b> okur (LSTM / Transformer). Hedef: <b>genel trend
          yukarıyken dibe yakın almak, tepeye yakın satmak</b> ve al-tut'u geçmek. İşlemler az
          ve seçicidir: trend kırılınca veya takipli stop devreye girince çıkar. Bu yüzden
          yükselişte al-tut'un bir miktar gerisinde kalabilir; asıl farkı <b>düşüşlerde sermayeyi
          koruyarak</b> yaratır. Sıra modelleri birkaç dakika eğitilir; ilerleme altta görünür.
        </p>
      </div>
      <button class="primary" id="master-train" type="button" style="min-width:170px"
        ${status.enabled ? "" : "disabled"}>Modeli eğit</button>
    </div>

    <div class="pf-simple">
      <div class="pf-field">
        <label class="pf-label">Coin <input id="pf-coin" value="${esc(prof.coin || "BTCUSDT")}"></label>
        <p class="pf-help">Modelin öğreneceği parite.</p>
      </div>
      <div class="pf-field">
        <label class="pf-label">Periyot ${periodFieldHtml("pf-period", prof.period || "1h")}</label>
        <p class="pf-help">1h iyi bir başlangıç. 15m daha sık işlem, 4h/1d daha az gürültü.</p>
      </div>
      <div class="pf-field">
        <label class="pf-label">Geçmiş mum <select id="pf-limit">${[5000,10000,20000,30000,50000].map((n) => `<option value="${n}" ${Number(prof.limit) === n ? "selected" : ""}>${n.toLocaleString("tr-TR")}</option>`).join("")}</select></label>
        <p class="pf-help">Ne kadar geçmişi öğreneceği. 20.000 mum (1h'de ~2 yıl) iyi bir denge.</p>
      </div>
      <div class="pf-field">
        <label class="pf-label">Fiyat verisi <select id="pf-dataset">
          <option value="" ${prof.dataset_id ? "" : "selected"}>Sabit / otomatik</option>
          ${datasetList.map((d) => `<option value="${esc(d.id)}" ${d.id === String(prof.dataset_id || "") ? "selected" : ""}>${esc(d.coin)} ${esc(d.period)} · ${fmt(d.rows, 0)} mum</option>`).join("")}
        </select></label>
        <p class="pf-help">Bir kez çekilip sabitlenen veri. Boş bırakırsan ilk eğitimde otomatik sabitlenir.</p>
      </div>
      <div class="pf-field">
        <label class="pf-label">Hedef <select id="pf-objective">
          <option value="profit" ${(prof.objective || "profit") === "profit" ? "selected" : ""}>Kâr odaklı (önerilen)</option>
          <option value="local_min_max" ${prof.objective === "local_min_max" ? "selected" : ""}>Local_Min_Max taklidi</option>
        </select></label>
        <p class="pf-help">Kâr odaklı: trend + dip/tepe. LMM taklidi: dip/zirve uyumu (F1) öncelikli.</p>
      </div>
      <div class="pf-field">
        <label class="pf-label">Uğraşma düzeyi <select id="pf-effort">${Object.entries(effortLevels).map(([id, level]) => `<option value="${esc(id)}" ${id === effort ? "selected" : ""}>${esc(level.label)} — ${esc(level.desc || "")}</option>`).join("")}</select></label>
        <p class="pf-help">Hızlı: birkaç dakika, tek mimari. Dengeli: önerilen. Titiz: en çok deneme, en uzun süre.</p>
      </div>
    </div>

    <div class="pf-objective mt">
      <b>Başarı ölçütü:</b> doğrulamanın <b>3 ayrı penceresinde</b> işlem kalitesi — al-tut farkı,
      getiri, kâr faktörü ve düşüş. Aşırı işlem yapan modeller cezalandırılır. Test verisi
      seçime hiç katılmaz. Model kabul edilmezse mevcut model korunur; bu bir hata değildir.
    </div>

    <details class="pf-advanced">
      <summary><b>Uzman ayarları</b> <span class="muted small">— genelde dokunma gerekmez</span></summary>

      <div class="pf-section-title">Local_Min_Max hedefi</div>
      <div class="pf-grid">
        ${pfField("Pivot penceresi (mum)", `<input id="pf-window" type="number" min="0" max="100" value="${esc(prof.extreme_window || 0)}">`,
          "Local_Min_Max'ın dip/zirve saymak için iki yanına baktığı mum sayısı. 0 = periyoda göre otomatik (15m:10, 1h:13, 4h:10, 1d:7).", 0, "otomatik")}
        ${pfField("Dip/zirve bandı (%)", `<input id="pf-band" type="number" min="0" max="5" step="0.05" value="${esc((Number(prof.proximity_band || 0.001) * 100).toFixed(2))}">`,
          "Fiyatın yerel dibe ne kadar yakınken 'dip bölgesi' sayılacağı. Küçük = sadece tam dip (az ama isabetli sinyal), büyük = geniş bölge (çok ama gürültülü). 0,1 önerilir.", 0.1, "%0,10")}
        ${pfField("Kayma toleransı (mum)", `<input id="pf-agree-tol" type="number" min="0" max="20" value="${esc(prof.agree_tolerance ?? 2)}">`,
          "Model sinyali gerçek pivottan kaç mum kayarsa yine 'tuttu' sayılsın. 2 makul.", 2, "2")}
        ${pfField("Asgari isabet", `<input id="pf-minprec" type="number" min="0.05" max="0.95" step="0.05" value="${esc(prof.min_precision ?? 0.35)}">`,
          "Sinyallerin en az kaçta kaçı gerçek pivot olmalı. 0,35 = üçte biri. Yükseltirsen daha az ama daha isabetli işlem.", 0.35, "0,35")}
      </div>

      <div class="pf-section-title">İşlem disiplini</div>
      <div class="pf-grid">
        ${pfField("Giriş seçiciliği (%)", `<input id="pf-entryrate" type="number" min="0.2" max="20" step="0.5" value="${esc((Number(prof.entry_rate || 0.02) * 100).toFixed(1))}">`,
          "Doğrulamada en yüksek olasılıklı mumların yüzde kaçında alım yapılabilsin. Küçük = az ama seçici işlem. 2 iyi bir denge.", 2, "%2")}
        ${pfField("Asgari tutma (mum)", `<input id="pf-minhold" type="number" min="0" max="500" value="${esc(prof.min_hold ?? 24)}">`,
          "Pozisyon en az kaç mum tutulur; sinyalle hemen kapanmaz. 24 = 1 gün (1h).", 24, "24")}
        ${pfField("Bekleme (mum)", `<input id="pf-cooldown" type="number" min="0" max="500" value="${esc(prof.cooldown ?? 24)}">`,
          "Çıkıştan sonra kaç mum yeni alım yapılmaz. Testere işlemleri ve maliyeti azaltır.", 24, "24")}
        ${pfField("Takipli stop (%)", `<input id="pf-trail" type="number" min="0" max="50" step="0.5" value="${esc((Number(prof.trailing_stop || 0.08) * 100).toFixed(1))}">`,
          "En yüksek fiyattan bu kadar geri çekilmede kâr korunur. Trendi yakalamak için 8 önerilir; 0 = kapalı.", 8, "%8")}
        ${pfField("Rejim bandı (%)", `<input id="pf-regime" type="number" min="0" max="20" step="0.5" value="${esc((Number(prof.regime_band || 0.02) * 100).toFixed(1))}">`,
          "EMA200 üstünde kalma bandı. Fiyat bandın üstüne çıkınca trend açık sayılır, altına inince kapanır. Testere sinyallerini engeller.", 2, "%2")}
      </div>

      <div class="pf-section-title">Model yapısı</div>
      <div class="pf-grid">
        ${pfField("Motor", `<select id="pf-engine"><option value="auto" ${prof.engine === "auto" ? "selected" : ""}>Sistem seçsin</option>${engines.map((e) => `<option value="${esc(e.id)}" ${e.id === prof.engine ? "selected" : ""}>${esc(e.label)}</option>`).join("")}</select>`,
          "Hangi algoritma. 'Sistem seçsin' en güvenlisi.", "auto", "sistem")}
        ${pfField("Çıktı biçimi", `<select id="pf-mode">${modes.map((m) => `<option value="${esc(m.id)}" ${m.id === prof.output_mode ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select>`,
          "Model neyi tahmin etsin. 'AL + SAT' en anlaşılır.", "dual_binary", 'AL + SAT')}
        ${pfField("Katmanlar", `<input id="pf-layers" value="${esc(layersText(prof.hidden_layers, ", "))}" placeholder="otomatik">`,
          "Sadece sinir ağı için. Boş = sistem dener.", "", "boş bırak")}
        ${pfField("Sıra penceresi (mum)", `<input id="pf-seqwindow" type="number" min="4" max="96" value="${esc(prof.seq_window || 24)}">`,
          "LSTM/Transformer kaç mumluk geçmişe baksın. 24 = 1 gün (1h). Uzun pencere daha geniş bağlam, daha yavaş eğitim.", 24, "24")}
        ${pfField("Aktivasyon", `<select id="pf-act"><option value="auto" ${prof.activation === "auto" ? "selected" : ""}>Sistem seçsin</option>${activations.map((a) => `<option value="${esc(a.id)}" ${a.id === prof.activation ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</select>`,
          "'Sistem seçsin' yeterli.", "auto", "sistem")}
      </div>

      <div class="pf-section-title">Hangi bilgileri görsün?</div>
      <p class="muted small" style="margin:0 0 8px">Hiçbiri seçilmezse sistem en iyi kombinasyonu arar.</p>
      <div class="arch-group-grid" id="pf-groups">
        ${groups.map((g) => `<label class="check arch-group">
          <input type="checkbox" class="pf-group-cb" value="${esc(g.id)}" ${(prof.feature_groups || []).includes(g.id) ? "checked" : ""}>
          <span><b>${esc(g.label)}</b> <span class="tag gray">${g.column_count}</span><br><small class="muted">${esc(g.desc)}</small></span>
        </label>`).join("")}
      </div>

      <div class="pf-section-title">Doğrulama</div>
      <div class="row" style="flex-wrap:wrap;gap:14px">
        <label class="check"><input type="checkbox" id="pf-wf" ${prof.walk_forward ? "checked" : ""}> Walk-forward doğrulaması</label>
        <label class="check"><input type="checkbox" id="pf-feedback" ${prof.use_feedback ? "checked" : ""}> Kapanan işlemlerden öğren</label>
      </div>
    </details>

    <div class="row mt" style="align-items:center;flex-wrap:wrap;gap:10px">
      <span class="muted small">${lastAuto.at ? `Son eğitim: ${esc(String(lastAuto.at).slice(0, 16).replace("T", " "))} · ${esc(lastAuto.reason || lastAuto.decision || "")}` : "Bu model için henüz eğitim yapılmadı"}</span>
    </div>
    <div id="master-result" class="mt"></div>
  </div>`;


  const datasetCard = `<div class="card mt ds-card">
    <div class="row between" style="align-items:flex-start">
      <div>
        <div class="row" style="gap:10px;align-items:center">
          <h3 style="margin:0">Fiyat verisi</h3>
          <span class="tag ${pinned ? "green" : "amber"}">${pinned ? "sabitlenmiş" : "canlı / otomatik"}</span>
        </div>
        <p class="muted small" style="margin:6px 0 0;max-width:680px">
          ${pinned
            ? `Eğitimler <b>${esc(dsName(pinned))}</b> sabit kopyasından okunur; ağa çıkılmaz. İndikatörler bu veriden yeniden hesaplanır.`
            : "İlk eğitimde veri bir kez çekilip diske sabitlenir; sonraki eğitimler aynı kopyayı kullanır. Yeni veri istediğinde yeni bir kopya oluştur."}
        </p>
      </div>
      <button class="primary small" id="ds-create" type="button">Yeni veri kopyası al</button>
    </div>
    <div class="row mt" style="flex-wrap:wrap;align-items:flex-end">
      ${field("Varlık", assetSelectHtml("ds-asset", "crypto"))}
      ${field("Sembol", symbolFieldHtml("ds-coin", cfg.coin || "BTCUSDT", { asset: "ds-asset" }))}
      ${field("Periyot", periodFieldHtml("ds-period", cfg.period || "1h"))}
      ${field("Mum sayısı", `<select id="ds-limit">${[5000,10000,20000,30000,50000].map((n) => `<option value="${n}" ${n === 20000 ? "selected" : ""}>${n.toLocaleString("tr-TR")}</option>`).join("")}</select>`)}
      <button class="ghost" id="ds-refresh" type="button" ${pinned ? "" : "disabled"} title="Sabit veriyi güncel fiyatlarla yenile">Sabit veriyi yenile</button>
      ${pinned ? `<button class="ghost" id="ds-unpin" type="button">Sabitlemeyi kaldır</button>` : ""}
    </div>
    <div class="ds-list mt">
      ${datasetList.length
        ? datasetList.slice(0, 12).map(dsRow).join("")
        : '<div class="empty-state small">Henüz sabit veri yok. İlk eğitimde otomatik oluşur veya yukarıdan elle al.</div>'}
    </div>
    <div class="tool-note mt">
      <b>Neden?</b> Her eğitimde borsaya istek atmak hem yavaş hem de sonuçları değişken yapar.
      Sabit kopya sayesinde aynı veride tekrar tekrar eğitim yapabilir, modelleri adil karşılaştırabilirsin.
      Yeni bir kopya aldığında eski kopya silinmez; geçmiş karşılaştırmalar bozulmaz.
    </div>
  </div>`;
  const active = models.filter((m) => m.status === "active");
  const candidates = models.filter((m) => m.status === "candidate");
  const archived = models.filter((m) => m.status === "archived");
  const running = models.filter((m) => m.status === "active" && (m.params || {}).coin === cfg.coin);
  const last = (auto.history || [])[0];
  const decisionText = {
    promoted: ["green", "terfi etti"],
    kept: ["amber", "mevcut model korundu"],
    rejected: ["red", "reddedildi"],
    error: ["red", "hata"],
  };

  const modelCard = (m) => {
    const p = m.params || {};
    const d = m.data || {};
    return `<div class="card" style="margin-bottom:10px">
      <div class="row between" style="align-items:flex-start">
        <div>
          <div class="row" style="gap:8px;align-items:center">
            <h3 style="margin:0">${esc(m.name)}</h3>
            <span class="tag blue">v${fmt(m.version || 1, 0)}</span>
            ${aiStatusTag(m.status)}
          </div>
          <div class="muted small" style="margin-top:4px">
            ${esc(p.coin || "-")} · ${esc(p.period || "-")} · ${fmt(d.rows, 0)} mum · v${fmt(m.version || 1, 0)} · ${esc((m.updated_at || m.created_at || "").slice(0, 16).replace("T", " "))}
          </div>
        </div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          ${m.status !== "active" ? `<button class="small" data-ai-promote="${esc(m.id)}" type="button">Aktifleştir</button>` : ""}
          <button class="small" data-ai-retrain="${esc(m.id)}" type="button" title="Aynı modeli tekrar eğit; sürüm artar">Tekrar eğit</button>
          <button class="small" data-ai-backtest="${esc(m.id)}" type="button">Backtest</button>
          <button class="ghost small" data-ai-detail="${esc(m.id)}" type="button">Detay</button>
          ${m.status !== "archived" ? `<button class="ghost small" data-ai-archive="${esc(m.id)}" type="button">Arşivle</button>` : ""}
          <button class="ghost small" data-ai-delete="${esc(m.id)}" type="button">Sil</button>
        </div>
      </div>
      <div class="mt">${aiMetricsHtml(m)}</div>
    </div>`;
  };

  root.innerHTML = `
    <div class="card ${status.enabled ? "" : "warn-card"}">
      <div class="row between">
        <div>
          <h3 style="margin:0">Yapay zekâ durumu</h3>
          <p class="muted small" style="margin:6px 0 0">${esc(status.note)}</p>
        </div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          <span class="tag ${status.enabled ? "green" : "gray"}">AI ${status.enabled ? "açık" : "kapalı"}</span>
          <span class="tag ${status.sklearn ? "green" : "gray"}">${status.sklearn ? "scikit-learn hazır" : "NumPy yedek model"}</span>
          <span class="tag blue">${status.models} model</span>
          <span class="tag blue">${status.experiences} işlem deneyimi</span>
        </div>
      </div>
    </div>

    ${masterCard}

    <details class="mt">
      <summary class="ghost" style="cursor:pointer;padding:10px 14px;border-radius:10px;background:rgba(148,163,184,.08)">
        <b>Gelişmiş ayarlar</b> <span class="muted small">— fiyat verisi, otomatik öğrenme, mimari, veri setleri</span>
      </summary>

    ${datasetCard}

    <div class="card mt ai-auto-card">
      <div class="row between" style="align-items:flex-start">
        <div>
          <div class="row" style="gap:10px;align-items:center">
            <h3 style="margin:0">Otomatik öğrenme</h3>
            <span class="tag ${cfg.enabled ? "green" : "gray"}">${cfg.enabled ? "açık" : "kapalı"}</span>
          </div>
          <p class="muted small" style="margin:6px 0 0;max-width:640px">
            Tek anahtar: model belirli aralıkla kendi kendini eğitir, sonucu test eder.
            Yeni model mevcut modelden belirgin biçimde iyiyse otomatik devreye girer; değilse korunur.
            Kapanan işlemler bir sonraki turda ders olarak kullanılır.
          </p>
        </div>
        <button class="toggle-row slim ${cfg.enabled ? "on" : ""}" id="auto-toggle" type="button" style="min-width:150px">
          <span class="switch"></span><span class="toggle-text"><strong>${cfg.enabled ? "Açık" : "Kapalı"}</strong><small>dokun ve değiştir</small></span>
        </button>
      </div>

      <div class="row mt" style="flex-wrap:wrap;align-items:flex-end">
        ${field("Coin", `<input id="auto-coin" value="${esc(cfg.coin || "BTCUSDT")}">`)}
        ${field("Periyot", periodFieldHtml("auto-period", cfg.period || "1h"))}
        ${field("Öğrenme tarzı", `<select id="auto-preset">${presets.map((p) => `<option value="${esc(p.id)}" ${p.id === cfg.preset ? "selected" : ""}>${esc(p.label)} — ${esc(p.desc)}</option>`).join("")}</select>`)}
        ${field("Kaç saatte bir", `<select id="auto-interval">${[6,12,24,48,72,168].map((h) => `<option value="${h}" ${Number(cfg.interval_hours) === h ? "selected" : ""}>${h < 24 ? h + " saat" : h / 24 + " gün"}</option>`).join("")}</select>`)}
        ${field("Geçmiş (mum)", `<select id="auto-limit">${[10000,20000,30000,50000].map((n) => `<option value="${n}" ${Number(cfg.limit) === n ? "selected" : ""}>${n.toLocaleString("tr-TR")}</option>`).join("")}</select>`)}
        ${field("Veri seti", `<select id="auto-dataset">
          <option value="" ${pinnedId ? "" : "selected"}>Canlı (otomatik sabitlenir)</option>
          ${datasetList.map((d) => `<option value="${esc(d.id)}" ${d.id === pinnedId ? "selected" : ""}>${esc(d.coin)} ${esc(d.period)} · ${fmt(d.rows, 0)} mum</option>`).join("")}
        </select>`)}
      </div>
      <div class="row mt" style="flex-wrap:wrap;gap:10px;align-items:center">
        <button class="primary" id="auto-save" type="button">Ayarları kaydet</button>
        <button class="ghost" id="auto-run" type="button" ${status.enabled ? "" : "disabled"}>Şimdi öğren</button>
        ${field("Nesil sayısı", `<select id="auto-generations">${[2,3,4,5,6].map((n) => `<option value="${n}" ${n === 3 ? "selected" : ""}>${n} nesil</option>`).join("")}</select>`)}
        <button class="ghost" id="auto-evolve" type="button" ${status.enabled ? "" : "disabled"}>Nesiller boyu eğit</button>
        <span class="muted small">${cfg.enabled && auto.next_run_at ? `Sıradaki tur: ${esc(fmtIso(auto.next_run_at))}` : "Otomatik öğrenme kapalı"}</span>
      </div>
      <div id="auto-result" class="mt"></div>

      <div class="ai-auto-status mt">
        <div class="ai-auto-item">
          <span>Aktif model</span>
          <b>${running.length ? esc(running[0].name) : "yok"}</b>
          <small>${running.length ? "bot sihirbazında AI olarak seçilebilir" : "ilk başarılı eğitimde otomatik aktifleşir"}</small>
        </div>
        <div class="ai-auto-item">
          <span>Son tur</span>
          <b>${last ? esc((last.created_at || "").slice(0, 16).replace("T", " ")) : "-"}</b>
          <small>${last ? `<span class="tag ${(decisionText[last.status] || ["gray"])[0]}">${esc((decisionText[last.status] || ["gray", last.status])[1])}</span>` : "henüz çalışmadı"}</small>
        </div>
        <div class="ai-auto-item">
          <span>Üst üste hata</span>
          <b>${fmt(cfg.consecutive_failures, 0)}</b>
          <small>${Number(cfg.consecutive_failures) > 0 ? "tekrar deneme aralığı otomatik uzar" : "sorun yok"}</small>
        </div>
      </div>
      ${last && last.reason ? `<div class="tool-note mt">Son karar: ${esc(last.reason)}</div>` : ""}
    </div>

    <div class="card mt ai-arch-card">
      <div class="row between" style="align-items:flex-start">
        <div>
          <div class="row" style="gap:10px;align-items:center">
            <h3 style="margin:0">Model mimarisi</h3>
            <span class="tag blue">sen seç</span>
          </div>
          <p class="muted small" style="margin:6px 0 0;max-width:700px">
            Hangi bilgiyi göreceğini, ağın kaç katman olacağını ve neyi tahmin edeceğini burada belirliyorsun.
            Aynı mimari hem otomatik öğrenmede hem elle eğitimde kullanılır.
          </p>
        </div>
        <button class="primary small" id="arch-save" type="button">Mimariyi kaydet</button>
      </div>

      <div class="row mt" style="flex-wrap:wrap;align-items:flex-end">
        ${field("Motor", `<select id="arch-engine">${engines.map((e) => `<option value="${esc(e.id)}" ${e.id === spec.engine ? "selected" : ""}>${esc(e.label)}</option>`).join("")}</select>`)}
        ${field("Çıktı biçimi", `<select id="arch-mode">${modes.map((m) => `<option value="${esc(m.id)}" ${m.id === spec.output_mode ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select>`)}
        ${field("Gizli katmanlar (virgülle)", `<input id="arch-layers" value="${esc(layersText(spec.hidden_layers, ", "))}" placeholder="64, 32">`)}
        ${field("Aktivasyon", `<select id="arch-act">${activations.map((a) => `<option value="${esc(a.id)}" ${a.id === spec.activation ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</select>`)}
      </div>
      <div class="row" style="flex-wrap:wrap;align-items:flex-end">
        ${field("Dropout", `<input id="arch-dropout" type="number" min="0" max="0.8" step="0.05" value="${esc(spec.dropout)}">`)}
        ${field("Öğrenme oranı", `<input id="arch-lr" type="number" min="0.00001" max="0.5" step="0.0005" value="${esc(spec.learning_rate)}">`)}
        ${field("Epoch", `<input id="arch-epochs" type="number" min="5" max="2000" step="5" value="${esc(spec.epochs)}">`)}
        ${field("Batch", `<input id="arch-batch" type="number" min="16" max="8192" step="16" value="${esc(spec.batch_size)}">`)}
        ${field("L2 ceza", `<input id="arch-l2" type="number" min="0" max="0.1" step="0.0001" value="${esc(spec.l2)}">`)}
        ${field("Sabır (epoch)", `<input id="arch-patience" type="number" min="1" max="200" step="1" value="${esc(spec.patience)}">`)}
      </div>
      <div class="arch-groups">
        <div class="row between" style="align-items:baseline">
          <b class="small">Özellik grupları</b>
          <span class="muted small">Seçilmeyen grup modele hiç girmez</span>
        </div>
        <div class="arch-group-grid">
          ${groups.map((g) => `<label class="check arch-group">
            <input type="checkbox" class="arch-group-cb" value="${esc(g.id)}" ${specGroups.includes(g.id) ? "checked" : ""}>
            <span><b>${esc(g.label)}</b> <span class="tag gray">${g.column_count}</span><br><small class="muted">${esc(g.desc)}</small></span>
          </label>`).join("")}
        </div>
      </div>
      <div class="tool-note mt" id="arch-summary"></div>
    </div>
    </details>

    <div class="card mt">
      <div class="row between">
        <h3 style="margin:0">Aktif modeller <span class="tag green">${active.length}</span></h3>
        <button class="ghost small" id="ai-refresh" type="button">Yenile</button>
      </div>
      <p class="muted small">Aktif model bot oluşturma ekranında AI stratejisi olarak seçilir ve panelden değiştirilene kadar sabit kalır.</p>
      ${active.length ? active.map(modelCard).join("") : '<div class="empty-state">Henüz aktif model yok. Yukarıdan “Modeli eğit” ile ilk modeli üret.</div>'}
    </div>

    <div class="card mt">
      <div class="row between">
        <h3 style="margin:0">Aday modeller <span class="tag blue">${candidates.length}</span></h3>
        ${candidates.length ? `<button class="ghost small" data-ai-purge="candidate" type="button">Tümünü sil</button>` : ""}
      </div>
      <p class="muted small">Kalite kapısını geçmiş ama mevcut modelden belirgin üstün olmadığı için terfi ettirilmemiş modeller.</p>
      ${candidates.length ? candidates.map(modelCard).join("") : '<div class="empty-state">Aday model yok.</div>'}
    </div>

    ${archived.length ? `<div class="card mt"><div class="row between"><h3 style="margin:0">Arşiv <span class="tag gray">${archived.length}</span></h3><button class="ghost small" data-ai-purge="archived" type="button">Tümünü sil</button></div>${archived.map(modelCard).join("")}</div>` : ""}

    ${(candidates.length + archived.length) ? `<div class="row mt" style="justify-content:flex-end">
      <button class="ghost small" data-ai-purge="candidate,archived" type="button">Aday ve arşivi birlikte sil (${candidates.length + archived.length})</button>
    </div>` : ""}

    <details class="card mt">
      <summary style="cursor:pointer"><b>Gelişmiş: elle eğitim</b> <span class="muted small">— genelde gerekmez</span></summary>
      <p class="muted small" style="margin:10px 0 0">Otomatik öğrenme yeterli değilse ince ayar burada. Aynı zaman serisi protokolü uygulanır: kronolojik bölme, embargo, yalnızca validation'da eşik, testin tek kullanımı.</p>
      <div class="row mt" style="flex-wrap:wrap">
        ${field("Model adı", `<input id="ai-name" placeholder="BTC 1h dip-zirve">`)}
        ${field("Varlık", assetSelectHtml("ai-asset", "crypto"))}
        ${field("Sembol", symbolFieldHtml("ai-coin", "BTCUSDT", { asset: "ai-asset" }))}
        ${field("Periyot", periodFieldHtml("ai-period", "1h"))}
        ${field("Mum sayısı", `<input id="ai-limit" type="number" value="20000" min="1000" max="250000" step="1000">`)}
      </div>
      <div class="row" style="flex-wrap:wrap">
        ${field("Veri kaynağı", `<select id="ai-source"><option value="auto">Otomatik</option><option value="binance">Binance</option><option value="yahoo">Yahoo Finance</option><option value="tefas">TEFAS</option><option value="csv">Yerel CSV (Data/)</option></select>`)}
        ${field("CSV yolu", `<input id="ai-csv" placeholder="btcusd_1-min_data.csv">`)}
        ${field("Etiket türü", `<select id="ai-label-kind"><option value="forward">İleri getiri (önerilen)</option><option value="local_extreme">Yerel dip/zirve (deney)</option></select>`)}
        ${field("Ufuk (mum)", `<input id="ai-horizon" type="number" value="12" min="2" max="500">`)}
      </div>
      <div class="row" style="flex-wrap:wrap">
        ${field("Hedef hareket %", `<input id="ai-target" type="number" value="1.0" min="0.05" max="50" step="0.1">`)}
        ${field("Stop mesafesi %", `<input id="ai-stop" type="number" value="1.0" min="0.05" max="50" step="0.1">`)}
        ${field("Min. precision", `<input id="ai-min-precision" type="number" value="0.35" min="0.05" max="0.95" step="0.05">`)}
        ${field("Walk-forward kat", `<input id="ai-folds" type="number" value="3" min="0" max="6">`)}
        ${field("İyileştirme turu", `<input id="ai-iterations" type="number" value="5" min="1" max="12">`)}
        ${field("Sabır (tur)", `<input id="ai-patience" type="number" value="2" min="1" max="6">`)}
        ${field("Zamanlama toleransı %", `<input id="ai-timing-tol" type="number" value="0.4" min="0.05" max="5" step="0.05">`)}
      </div>
      <div class="row" style="flex-wrap:wrap;gap:14px;margin-top:6px">
        <label class="check"><input type="checkbox" id="ai-refine" checked> Zamanlama hatalarından öğren (tur tur iyileştir)</label>
        <label class="check"><input type="checkbox" id="ai-wf" checked> Walk-forward raporu</label>
        <label class="check"><input type="checkbox" id="ai-feedback" checked> Kapanan AI işlemlerinden öğren</label>
        ${field("Geri bildirim ağırlığı", `<input id="ai-feedback-weight" type="number" value="0.5" min="0" max="2" step="0.1">`)}
      </div>
      <div class="row" style="margin-top:12px">
        <button class="primary" id="ai-train" type="button" ${status.enabled ? "" : "disabled"}>Eğitimi başlat</button>
      </div>
      <div id="ai-train-result" class="mt"></div>
    </details>
  `;

  const collectArch = () => {
    const layers = String($("#arch-layers").value || "")
      .split(/[\s,;x]+/).map((v) => v.trim()).filter(Boolean).map(Number).filter((n) => n > 0);
    const selected = $$(".arch-group-cb").filter((cb) => cb.checked).map((cb) => cb.value);
    return {
      engine: $("#arch-engine").value,
      output_mode: $("#arch-mode").value,
      hidden_layers: layers,
      activation: $("#arch-act").value,
      dropout: Number($("#arch-dropout").value || 0),
      learning_rate: Number($("#arch-lr").value || 0.003),
      epochs: Number($("#arch-epochs").value || 120),
      batch_size: Number($("#arch-batch").value || 256),
      l2: Number($("#arch-l2").value || 0),
      patience: Number($("#arch-patience").value || 15),
      feature_groups: selected,
    };
  };
  const archSummary = () => {
    const s = collectArch();
    const groupCols = groups
      .filter((g) => s.feature_groups.includes(g.id))
      .reduce((sum, g) => sum + Number(g.column_count || 0), 0);
    const modeLabel = (modes.find((m) => m.id === s.output_mode) || {}).label || s.output_mode;
    const engineLabel = (engines.find((e) => e.id === s.engine) || {}).label || s.engine;
    const archText = archSummaryText(s.engine, s, s);
    $("#arch-summary").innerHTML = `<b>Özet:</b> ${esc(engineLabel)} · ${esc(archText)} · ${esc(modeLabel)} · ` +
      `${s.feature_groups.length} grup / ${groupCols} özellik`;
  };

  const saveCfg = async (extra = {}) => {
    const body = {
      coin: $("#auto-coin").value.trim().toUpperCase(),
      period: readPeriod("auto-period"),
      preset: $("#auto-preset").value,
      interval_hours: Number($("#auto-interval").value || 24),
      limit: Number($("#auto-limit").value || 25000),
      dataset_id: $("#auto-dataset").value || "",
      spec: collectArch(),
      ...extra,
    };
    return api("/ai/autopilot", { method: "PUT", body });
  };

  /* Tek düğme: Modeli eğit */
  const collectProfile = () => {
    const layers = String($("#pf-layers").value || "")
      .split(/[\s,;x]+/).map((v) => v.trim()).filter(Boolean).map(Number).filter((n) => n > 0);
    const selected = $$(".pf-group-cb").filter((cb) => cb.checked).map((cb) => cb.value);
    return {
      coin: $("#pf-coin").value.trim().toUpperCase(),
      period: readPeriod("pf-period"),
      limit: Number($("#pf-limit").value || 20000),
      dataset_id: $("#pf-dataset").value || "",
      effort: ($("#pf-effort") || {}).value || effort,
      objective: ($("#pf-objective") || {}).value || "profit",
      extreme_window: Number(($("#pf-window") || {}).value || 0),
      proximity_band: Number((($("#pf-band") || {}).value || 0.1)) / 100,
      agree_tolerance: Number(($("#pf-agree-tol") || {}).value || 2),
      min_precision: Number(($("#pf-minprec") || {}).value || 0.35),
      entry_rate: Number(($("#pf-entryrate") || {}).value || 2) / 100,
      min_hold: Number(($("#pf-minhold") || {}).value || 24),
      cooldown: Number(($("#pf-cooldown") || {}).value || 24),
      trailing_stop: Number(($("#pf-trail") || {}).value || 8) / 100,
      regime_band: Number(($("#pf-regime") || {}).value || 2) / 100,
      seq_window: Number(($("#pf-seqwindow") || {}).value || 24),
      engine: $("#pf-engine").value,
      output_mode: $("#pf-mode").value,
      hidden_layers: layers,
      activation: $("#pf-act").value,
      feature_groups: selected,
      walk_forward: $("#pf-wf").checked,
      use_feedback: $("#pf-feedback").checked,
    };
  };

  /* "Önerilen" düğmeleri: alanı etiket adıyla eşleştirip değeri yazar. */
  $$("[data-pfrec]").forEach((b) => b.addEventListener("click", () => {
    const label = b.dataset.pftarget || "";
    const map = {
      "Pivot penceresi (mum)": "#pf-window",
      "Giriş seçiciliği (%)": "#pf-entryrate",
      "Asgari tutma (mum)": "#pf-minhold",
      "Bekleme (mum)": "#pf-cooldown",
      "Takipli stop (%)": "#pf-trail",
      "Rejim bandı (%)": "#pf-regime",
      "Sıra penceresi (mum)": "#pf-seqwindow",
      "Dip/zirve bandı (%)": "#pf-band",
      "Kayma toleransı (mum)": "#pf-agree-tol",
      "Asgari isabet": "#pf-minprec",
      "Motor": "#pf-engine",
      "Çıktı biçimi": "#pf-mode",
      "Aktivasyon": "#pf-act",
    };
    const target = map[label];
    if (!target) return;
    const el = $(target);
    if (!el) return;
    el.value = b.dataset.pfrec;
    el.classList.add("just-set");
    setTimeout(() => el.classList.remove("just-set"), 700);
  }));

  $("#master-train").addEventListener("click", async () => {
    const btn = $("#master-train");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Eğitiliyor…";
    const box = $("#master-result");
    box.innerHTML = '<span class="muted">Model eğitimi başlatılıyor…</span>';
    try {
      const job = await api("/ai/auto", { method: "POST", body: collectProfile() });
      pollJob(job.id, (j) => {
        if (j.status === "error") {
          box.innerHTML = `<div class="error">${esc(j.error || "Eğitim hatası")}</div>`;
          btn.disabled = false;
          btn.textContent = label;
          return;
        }
        if (j.status !== "done") {
          box.innerHTML = `<div class="muted">${esc(j.message || j.status)} · %${fmt(j.progress, 0)}</div>`;
          return;
        }
        const r = j.result || {};
        const labels = {
          created: ["green", "ilk model oluşturuldu"],
          updated: ["green", "model güncellendi"],
          kept: ["amber", "mevcut model korundu"],
        };
        const [cls, text] = labels[r.decision] || ["gray", r.decision || "-"];
        const rows = (r.attempts || []).map((a, i) => {
          const v = a.validation || {};
          const spec = a.spec || {};
          const arch = spec.engine === "gbm" ? "GBM" : layersText(spec.hidden_layers);
          const av = a.agreement || {};
          return `<tr>
            <td>${i + 1}</td>
            <td class="mono small">${esc(arch)} · ${esc(spec.activation || "")}</td>
            <td>${(spec.feature_groups || []).length} grup</td>
            <td>${av.f1 === undefined ? "-" : fmt(av.f1 * 100, 1) + "%"}</td>
            <td class="${pnlClass(v.edge_pct)}">${fmt(v.edge_pct, 2)}%</td>
            <td>${fmt(a.score, 2)}${a.error ? ` <span class="tag red">hata</span>` : ""}</td>
          </tr>`;
        }).join("");
        const rep = r.report || {};
        const trd = rep.test ? (rep.test.trading || {}) : (rep.validation ? (rep.validation.trading || {}) : {});
        const qual = ((rep.quality || {}).robust) || {};
        box.innerHTML = `<div class="card" style="padding:12px">
          <div class="row between"><b>Eğitim tamamlandı</b><span class="tag ${cls}">${esc(text)}</span></div>
          <div class="muted small" style="margin:6px 0">${esc(r.reason || "")}</div>
          <div class="stat-grid">
            <div class="stat"><span>İşlem kalitesi</span><b class="${Number(qual.score || 0) > 0 ? "pos" : "neg"}">${qual.score === undefined ? "-" : fmt(qual.score, 1)}</b><small>${fmt(qual.positive_windows, 0)}/${fmt(qual.windows, 0)} pencerede al-tut geçildi</small></div>
            <div class="stat"><span>Al-tut farkı</span><b class="${pnlClass(trd.edge_pct)}">${fmt(trd.edge_pct, 1)}%</b><small>getiri ${fmt(trd.total_return_pct, 1)}% · al-tut ${fmt(trd.buy_hold_pct, 1)}%</small></div>
            <div class="stat"><span>İşlem / kazanma</span><b>${fmt(trd.trade_count, 0)}</b><small>${fmt(trd.win_rate, 1)}% kazanan · pf ${fmt(trd.profit_factor, 2)}</small></div>
            <div class="stat"><span>Karar</span><b class="small">${esc(text)}</b><small>${(r.attempts || []).length} mimari denendi</small></div>
          </div>
          <div class="result-scroll mt"><table class="result-table"><thead><tr>
            <th>#</th><th>Mimari</th><th>Özellik</th><th>Uyum (F1)</th><th>Al-tut farkı</th><th>Skor</th>
          </tr></thead><tbody>${rows}</tbody></table></div>
          ${r.report ? aiTrainingReport(r.report) : ""}
          <div class="row mt"><button class="small" id="master-after" type="button">Listeyi yenile</button></div>
        </div>`;
        btn.disabled = false;
        btn.textContent = label;
        const after = $("#master-after");
        if (after) after.addEventListener("click", () => route());
      });
    } catch (e) {
      box.innerHTML = `<div class="error">${esc(e.message)}</div>`;
      btn.disabled = false;
      btn.textContent = label;
    }
  });

  /* Fiyat verisi (sabit kopya) */
  const datasetAction = async (fn, okText) => {
    try {
      await fn();
      toast(okText);
      route();
    } catch (e) { toast(e.message, true); }
  };
  const createSnapshot = (coin, period, limit, okText, assetClass = "crypto", source = "") =>
    datasetAction(async () => {
      await api("/ai/datasets", {
        method: "POST",
        body: {
          coin: coin.trim().toUpperCase(), period: period.trim(), limit: Number(limit),
          asset_class: assetClass, source: source || assetSourceOf(assetClass),
        },
      });
    }, okText);

  $("#ds-create").addEventListener("click", () => {
    createSnapshot($("#ds-coin").value, readPeriod("ds-period"), $("#ds-limit").value,
      "Veri kopyası alındı ve sabitlendi", $("#ds-asset").value);
  });
  bindSymbolField("ds-coin", "ds-asset", "ds-period");
  bindPeriodField("ds-period");
  const refreshBtn = $("#ds-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", () => {
    if (!pinned) return;
    createSnapshot(
      pinned.coin, pinned.period, pinned.rows, "Sabit veri yenilendi",
      pinned.asset_class || "crypto", pinned.source || "",
    );
  });
  const unpinBtn = $("#ds-unpin");
  if (unpinBtn) unpinBtn.addEventListener("click", async () => {
    await datasetAction(() => api("/ai/autopilot", { method: "PUT", body: { dataset_id: "" } }),
      "Sabitleme kaldırıldı");
  });
  $$("[data-ds-pin]").forEach((b) => b.addEventListener("click", async () => {
    await datasetAction(() => api("/ai/autopilot", { method: "PUT", body: { dataset_id: b.dataset.dsPin } }),
      "Veri seti sabitlendi");
  }));
  $$("[data-ds-del]").forEach((b) => b.addEventListener("click", async () => {
    const ok = await confirmDialog("Veri setini sil", "Sabit fiyat kopyası silinecek. Devam edilsin mi?", "Sil", true);
    if (!ok) return;
    await datasetAction(() => api(`/ai/datasets/${encodeURIComponent(b.dataset.dsDel)}`, { method: "DELETE" }),
      "Veri seti silindi");
  }));

  ["#arch-engine", "#arch-mode", "#arch-layers", "#arch-act", "#arch-dropout",
   "#arch-lr", "#arch-epochs", "#arch-batch", "#arch-l2", "#arch-patience"]
    .forEach((sel) => {
      const el = $(sel);
      if (el) el.addEventListener("input", archSummary);
      if (el) el.addEventListener("change", archSummary);
    });
  $$(".arch-group-cb").forEach((cb) => cb.addEventListener("change", archSummary));
  archSummary();
  $("#arch-save").addEventListener("click", async () => {
    const btn = $("#arch-save");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Kaydediliyor…";
    try {
      const res = await api("/ai/autopilot", { method: "PUT", body: { spec: collectArch() } });
      toast(`Model mimarisi kaydedildi (${layersText(res.spec.hidden_layers) || "ağaç"}, ${res.spec.feature_groups.length} grup)`);
      route();
    } catch (e) {
      toast(`Kaydedilemedi: ${e.message}`, true);
      btn.disabled = false;
      btn.textContent = label;
    }
  });

  $("#auto-toggle").addEventListener("click", async () => {
    if (!cfg.enabled && !status.enabled) { toast("Önce AI özelliklerini açın: Ayarlar > Sistem", true); return; }
    try {
      await saveCfg({ enabled: !cfg.enabled });
      toast(cfg.enabled ? "Otomatik öğrenme kapatıldı" : "Otomatik öğrenme açıldı");
      route();
    } catch (e) { toast(e.message, true); }
  });
  $("#auto-save").addEventListener("click", async () => {
    try { await saveCfg(); toast("Otomatik öğrenme ayarları kaydedildi"); route(); }
    catch (e) { toast(e.message, true); }
  });
  $("#auto-run").addEventListener("click", async () => {
    const btn = $("#auto-run");
    btn.disabled = true;
    const box = $("#auto-result");
    box.innerHTML = '<span class="muted">Öğrenme turu kuyruğa alınıyor…</span>';
    try {
      await saveCfg();
      const job = await api("/ai/autopilot/run", { method: "POST" });
      pollJob(job.id, (j) => {
        if (j.status === "error") {
          box.innerHTML = `<div class="error">${esc(j.error || "Öğrenme hatası")}</div>`;
          btn.disabled = false;
          return;
        }
        if (j.status !== "done") {
          box.innerHTML = `<div class="muted">${esc(j.message || j.status)} · %${fmt(j.progress, 0)}</div>`;
          return;
        }
        const r = j.result || {};
        const gate = r.gate || {};
        const t = (gate.metrics && gate.metrics.test) || {};
        const [cls, text] = decisionText[r.decision] || ["gray", r.decision || "-"];
        box.innerHTML = `<div class="card" style="padding:12px">
          <div class="row between"><b>Tur tamamlandı</b><span class="tag ${cls}">${esc(text)}</span></div>
          <div class="muted small" style="margin:6px 0">${esc(r.reason || "")}</div>
          <div class="stat-grid">
            <div class="stat"><span>Test getirisi</span><b class="${pnlClass(t.total_return_pct)}">${fmt(t.total_return_pct, 1)}%</b><small>al-tut ${fmt(t.buy_hold_pct, 1)}%</small></div>
            <div class="stat"><span>Edge</span><b class="${pnlClass(t.edge_pct)}">${fmt(t.edge_pct, 1)}%</b><small>${fmt(t.trade_count, 0)} işlem</small></div>
            <div class="stat"><span>Kazanma</span><b>${fmt(t.win_rate, 1)}%</b><small>maks. düşüş ${fmt(t.max_drawdown_pct, 1)}%</small></div>
          </div>
          ${(gate.reasons || []).length ? `<div class="error small mt">${gate.reasons.map((x) => esc(x)).join("<br>")}</div>` : ""}
          ${(gate.warnings || []).length ? `<div class="muted small mt">${gate.warnings.map((x) => esc(x)).join("<br>")}</div>` : ""}
          ${r.report ? aiTrainingReport(r.report) : ""}
          <div class="row mt"><button class="small" id="auto-after" type="button">Listeyi yenile</button></div>
        </div>`;
        btn.disabled = false;
        const after = $("#auto-after");
        if (after) after.addEventListener("click", () => route());
      });
    } catch (e) {
      box.innerHTML = `<div class="error">${esc(e.message)}</div>`;
      btn.disabled = false;
    }
  });

  $("#auto-evolve").addEventListener("click", async () => {
    const btn = $("#auto-evolve");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Nesiller eğitiliyor…";
    const box = $("#auto-result");
    const generations = Number($("#auto-generations").value || 3);
    box.innerHTML = `<div class="muted">${generations} nesil eğitim kuyruğa alınıyor… (her nesil öncekinden devam eder)</div>`;
    try {
      await saveCfg();
      const job = await api("/ai/evolve", {
        method: "POST",
        body: {
          coin: $("#auto-coin").value.trim().toUpperCase(),
          period: readPeriod("auto-period"),
          limit: Number($("#auto-limit").value || 25000),
          generations,
          dataset_id: pinnedId,
          auto_snapshot: !pinnedId,
          spec: collectArch(),
        },
      });
      pollJob(job.id, (j) => {
        if (j.status === "error") {
          box.innerHTML = `<div class="error">${esc(j.error || "Nesil eğitimi hatası")}</div>`;
          btn.disabled = false;
          btn.textContent = label;
          return;
        }
        if (j.status !== "done") {
          box.innerHTML = `<div class="muted">${esc(j.message || j.status)} · %${fmt(j.progress, 0)}</div>`;
          return;
        }
        const r = j.result || {};
        const [cls, text] = decisionText[r.decision] || ["gray", r.decision || "-"];
        const rows = (r.history || []).map((h) => {
          const val = h.validation || {};
          const test = h.test || {};
          return `<tr class="${h.final_audit ? "muted" : ""}">
            <td>${fmt(h.generation, 0)}${h.final_audit ? ' <span class="tag gray">denetim</span>' : ""}</td>
            <td>${h.warm_start_used ? '<span class="tag green">devam</span>' : '<span class="tag gray">sıfırdan</span>'}</td>
            <td class="${pnlClass(val.edge_pct)}">${fmt(val.edge_pct, 2)}%</td>
            <td>${fmt(val.total_return_pct, 2)}% / ${fmt(val.trade_count, 0)} işlem</td>
            <td class="${pnlClass(test.total_return_pct)}">${h.test ? fmt(test.total_return_pct, 2) + "%" : "-"}</td>
            <td>${h.improved ? '<span class="tag green">iyileşti</span>' : '<span class="tag amber">geriledi</span>'}</td>
          </tr>`;
        }).join("");
        box.innerHTML = `<div class="card" style="padding:12px">
          <div class="row between"><b>${fmt(r.best_generation, 0)}. nesil seçildi</b><span class="tag ${cls}">${esc(text)}</span></div>
          <div class="muted small" style="margin:6px 0">${esc(r.reason || "")}</div>
          <div class="stat-grid">
            <div class="stat"><span>Seçim skoru (validation)</span><b>${fmt(r.best_score, 2)}</b><small>nesil seçimi teste bakmaz</small></div>
            <div class="stat"><span>Nihai skor</span><b>${fmt(r.final_score, 2)}</b><small>audit modeli</small></div>
            <div class="stat"><span>Nesil</span><b>${fmt(r.history.length, 0)}</b><small>${fmt(r.best_generation, 0)}. seçildi</small></div>
          </div>
          <div class="result-scroll mt"><table class="result-table"><thead><tr>
            <th>Nesil</th><th>Başlangıç</th><th>Validation edge</th><th>Validation getiri / işlem</th><th>Test getiri</th><th>Sonuç</th>
          </tr></thead><tbody>${rows}</tbody></table></div>
          ${r.report ? aiTrainingReport(r.report) : ""}
          <div class="row mt"><button class="small" id="evo-after" type="button">Listeyi yenile</button></div>
        </div>`;
        btn.disabled = false;
        btn.textContent = label;
        const after = $("#evo-after");
        if (after) after.addEventListener("click", () => route());
      });
    } catch (e) {
      box.innerHTML = `<div class="error">${esc(e.message)}</div>`;
      btn.disabled = false;
      btn.textContent = label;
    }
  });

  $("#ai-refresh").addEventListener("click", () => route());

  $("#ai-source").addEventListener("change", () => {
    $("#ai-csv").closest("label").style.display = $("#ai-source").value === "csv" ? "" : "none";
  });
  $("#ai-source").dispatchEvent(new Event("change"));
  bindSymbolField("ai-coin", "ai-asset", "ai-period");
  bindPeriodField("ai-period");
  ["pf-period", "auto-period"].forEach(bindPeriodField);
  $("#ai-asset").addEventListener("change", () => {
    const source = $("#ai-source");
    if (source.value !== "csv") source.value = assetSourceOf($("#ai-asset").value);
    const symbol = $("#ai-coin");
    const known = Object.values(ASSET_DEFAULT_SYMBOL);
    if (!symbol.value.trim() || known.includes(symbol.value.trim().toUpperCase())) {
      symbol.value = ASSET_DEFAULT_SYMBOL[$("#ai-asset").value] || "BTCUSDT";
    }
  });

  $("#ai-train").addEventListener("click", async () => {
    const btn = $("#ai-train");
    btn.disabled = true;
    const box = $("#ai-train-result");
    box.innerHTML = '<span class="muted">Eğitim kuyruğa alınıyor…</span>';
    try {
      const body = {
        name: $("#ai-name").value.trim(),
        coin: $("#ai-coin").value.trim().toUpperCase(),
        period: readPeriod("ai-period"),
        limit: Number($("#ai-limit").value || 20000),
        source: $("#ai-source").value,
        asset_class: $("#ai-asset").value,
        csv_path: $("#ai-csv").value.trim(),
        label_kind: $("#ai-label-kind").value,
        horizon: Number($("#ai-horizon").value || 12),
        target_move: Number($("#ai-target").value || 1) / 100,
        stop_move: Number($("#ai-stop").value || 1) / 100,
        min_precision: Number($("#ai-min-precision").value || 0.35),
        refine: $("#ai-refine").checked,
        iterations: Number($("#ai-iterations").value || 5),
        patience: Number($("#ai-patience").value || 2),
        timing_tolerance: Number($("#ai-timing-tol").value || 0.4) / 100,
        walk_forward: $("#ai-wf").checked,
        folds: Number($("#ai-folds").value || 0),
        use_feedback: $("#ai-feedback").checked,
        feedback_weight: Number($("#ai-feedback-weight").value || 0.5),
        dataset_id: pinnedId,
        auto_snapshot: !pinnedId && $("#ai-source").value !== "csv",
        spec: collectArch(),
      };
      const job = await api("/ai/train", { method: "POST", body });
      box.innerHTML = `<div class="muted">İş <span class="mono">${esc(job.id)}</span> kuyruğa alındı.</div>`;
      pollJob(job.id, (j) => {
        if (j.status === "error") {
          box.innerHTML = `<div class="error">${esc(j.error || "Eğitim hatası")}</div>`;
          btn.disabled = false;
          return;
        }
        if (j.status !== "done") {
          box.innerHTML = `<div class="muted">${esc(j.message || j.status)} · %${fmt(j.progress, 0)}</div>`;
          return;
        }
        const r = j.result || {};
        const report = r.report || {};
        box.innerHTML = `<div class="card" style="padding:12px">
          <div class="row between"><b>Eğitim tamamlandı</b><button class="small" id="ai-goto-models" type="button">Modeli gör</button></div>
          <div class="muted small" style="margin:6px 0">Model: <span class="mono">${esc(r.model_id || "-")}</span></div>
          ${aiTrainingReport(report)}
        </div>`;
        btn.disabled = false;
        const after = $("#ai-goto-models");
        if (after) after.addEventListener("click", () => route());
      });
    } catch (e) {
      box.innerHTML = `<div class="error">${esc(e.message)}</div>`;
      btn.disabled = false;
    }
  });

  $$("[data-ai-detail]").forEach((b) => b.addEventListener("click", async () => {
    try {
      const d = await api(`/ai/models/${encodeURIComponent(b.dataset.aiDetail)}`);
      modal("AI model detayı", `<pre style="white-space:pre-wrap;max-height:60vh;overflow:auto">${esc(JSON.stringify({ model: d.model, report: d.report, experiences: d.experiences }, null, 2))}</pre>`);
    } catch (e) { toast(e.message, true); }
  }));
  $$("[data-ai-promote]").forEach((b) => b.addEventListener("click", async () => {
    const ok = await confirmDialog("Modeli aktifleştir", "Bu model bot sihirbazında AI stratejisi olarak görünecek. Devam edilsin mi?");
    if (!ok) return;
    try { await api(`/ai/models/${encodeURIComponent(b.dataset.aiPromote)}/promote`, { method: "POST" }); toast("Model aktifleştirildi"); route(); }
    catch (e) { toast(e.message, true); }
  }));
  $$("[data-ai-archive]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/ai/models/${encodeURIComponent(b.dataset.aiArchive)}/archive`, { method: "POST" }); toast("Model arşivlendi"); route(); }
    catch (e) { toast(e.message, true); }
  }));
  $$("[data-ai-delete]").forEach((b) => b.addEventListener("click", async () => {
    const ok = await confirmDialog("Modeli sil", "Model dosyaları kalıcı olarak silinecek. Devam edilsin mi?", "Sil", true);
    if (!ok) return;
    try { await api(`/ai/models/${encodeURIComponent(b.dataset.aiDelete)}`, { method: "DELETE" }); toast("Model silindi"); route(); }
    catch (e) { toast(e.message, true); }
  }));
  $$("[data-ai-purge]").forEach((b) => b.addEventListener("click", async () => {
    const statuses = String(b.dataset.aiPurge || "").split(",").filter(Boolean);
    const n = statuses.reduce((acc, s) => acc + (s === "candidate" ? candidates.length : s === "archived" ? archived.length : 0), 0);
    if (!n) { toast("Silinecek model yok"); return; }
    const label = statuses.length > 1 ? `${n} aday/arşiv model` : (statuses[0] === "candidate" ? `${n} aday model` : `${n} arşiv model`);
    const ok = await confirmDialog(
      "Toplu sil",
      `${label} kalıcı olarak silinecek. Aktif modeller korunur. Devam edilsin mi?`,
      "Hepsini sil",
      true,
    );
    if (!ok) return;
    b.disabled = true;
    try {
      const r = await api("/ai/models/bulk-delete", { method: "POST", body: { statuses } });
      toast(`${fmt(r.deleted, 0)} model silindi`);
      if ((r.failed || []).length) toast(`${r.failed.length} model silinemedi`, true);
      route();
    } catch (e) {
      toast(e.message, true);
      b.disabled = false;
    }
  }));
  $$("[data-ai-retrain]").forEach((b) => b.addEventListener("click", async () => {
    const model = models.find((x) => x.id === b.dataset.aiRetrain) || {};
    const version = Number(model.version || 1);
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <p class="muted small">Aynı model kimliği korunur; sürüm numarası artar.
      Bir tur mevcut sürümden daha iyi değilse <b>mevcut sürüm korunur</b>, gerileme kabul edilmez.</p>
      <div class="tool-note">Model: <b>${esc(model.name || b.dataset.aiRetrain)}</b> · mevcut sürüm v${fmt(version, 0)}</div>
      <p class="muted small" style="margin:8px 0 0">
        <b>Veri sabit kalır.</b> Turlar dönüşümlü ilerler: bir tur önceki ağırlıklardan ince ayar,
        sonraki tur <b>sıfırdan</b> eğitim (yerel optimuma takılmamak için). Eğitim uzun bütçeli
        (200 epoch'a kadar, sabırlı erken durma) ve son model birkaç tohumun ortalamasıdır.
        Terfi kararı test görmeden, <b>3 ayrı validation penceresinin</b> uyumuna göre verilir.
      </p>
      <div class="row mt" style="flex-wrap:wrap;align-items:flex-end">
        ${field("Kaç tur", `<select id="rt-repeats">${[1,2,3,5,8,10].map((n) => `<option value="${n}" ${n === 3 ? "selected" : ""}>${n} tur</option>`).join("")}</select>`)}
        ${field("Asgari kazanç (puan)", `<input id="rt-gain" type="number" value="0" min="0" max="5" step="0.05">`)}
        ${field("Veri", `<select id="rt-dataset">
          <option value="">Sabit / otomatik veri</option>
          ${datasetList.map((d) => `<option value="${esc(d.id)}" ${d.id === String((model.params || {}).dataset_id || "") ? "selected" : ""}>${esc(d.coin)} ${esc(d.period)} · ${fmt(d.rows, 0)} mum</option>`).join("")}
        </select>`)}
      </div>
      <div class="row end mt">
        <button class="ghost" id="rt-cancel" type="button">Vazgeç</button>
        <button class="primary" id="rt-start" type="button">Tekrar eğit</button>
      </div>
      <div id="rt-result" class="mt"></div>`;
    modal("Aynı modeli tekrar eğit", wrap);
    $("#rt-cancel").addEventListener("click", closeModal);
    $("#rt-start").addEventListener("click", async () => {
      const btn = $("#rt-start");
      btn.disabled = true;
      const box = $("#rt-result");
      box.innerHTML = '<span class="muted">Turlar kuyruğa alınıyor…</span>';
      try {
        const dsId = $("#rt-dataset").value;
        const job = await api(`/ai/models/${encodeURIComponent(b.dataset.aiRetrain)}/retrain`, {
          method: "POST",
          body: {
            repeats: Number($("#rt-repeats").value || 1),
            min_gain: Number($("#rt-gain").value || 0),
            dataset_id: dsId || null,
            auto_snapshot: !dsId,
          },
        });
        pollJob(job.id, (j) => {
          if (j.status === "error") {
            box.innerHTML = `<div class="error">${esc(j.error || "Tekrar eğitim hatası")}</div>`;
            btn.disabled = false;
            return;
          }
          if (j.status !== "done") {
            box.innerHTML = `<div class="muted">${esc(j.message || j.status)} · %${fmt(j.progress, 0)}</div>`;
            return;
          }
          const r = j.result || {};
          const rows = (r.attempts || []).map((a) => `
            <tr>
              <td>${fmt(a.step, 0)}</td>
              <td>v${fmt(a.parent_version, 0)}</td>
              <td>${fmt(a.previous_score, 2)}</td>
              <td>${fmt(a.candidate_score, 2)}</td>
              <td>${a.previous_robust_f1 == null ? "-" : fmt(a.previous_robust_f1 * 100, 1) + "% → " + fmt(a.candidate_robust_f1 * 100, 1) + "%"}</td>
              <td>${fmt(a.focus, 2)}</td>
              <td>${a.improved ? '<span class="tag green">kabul</span>' : '<span class="tag amber">korundu</span>'}</td>
              <td class="${pnlClass((a.test || {}).total_return_pct)}">${fmt((a.test || {}).total_return_pct, 2)}%</td>
            </tr>`).join("");
          box.innerHTML = `<div class="card" style="padding:12px">
            <div class="row between"><b>Sonuç: v${fmt(r.version, 0)}</b>
              <span class="tag ${r.promoted ? "green" : "gray"}">${fmt(r.promoted, 0)}/${fmt(r.repeats, 0)} tur kabul</span></div>
            <div class="muted small" style="margin:6px 0">Kimlik: <span class="mono">${esc(r.model_id || "")}</span> · skor ${fmt(r.score, 2)}</div>
            <p class="muted small" style="margin:0 0 8px">Uyum = Local_Min_Max eşleşmesi (validation F1). Odak = önceki neslin hatalarına verilen ek ağırlık.</p>
            <div class="result-scroll mt"><table class="result-table"><thead><tr>
              <th>Tur</th><th>Önceki sürüm</th><th>Önceki skor</th><th>Aday skor</th><th>Uyum (3 pencere)</th><th>Odak</th><th>Karar</th><th>Test getiri</th>
            </tr></thead><tbody>${rows}</tbody></table></div>
            <div class="row mt"><button class="small" id="rt-after" type="button">Kapat ve yenile</button></div>
          </div>`;
          btn.disabled = false;
          const after = $("#rt-after");
          if (after) after.addEventListener("click", () => { closeModal(); route(); });
        });
      } catch (e) {
        box.innerHTML = `<div class="error">${esc(e.message)}</div>`;
        btn.disabled = false;
      }
    });
  }));
  $$("[data-ai-backtest]").forEach((b) => b.addEventListener("click", () => {
    const m = models.find((x) => x.id === b.dataset.aiBacktest);
    openBacktest({ type: "ai", model_id: b.dataset.aiBacktest }, {
      coin: (m && m.params && m.params.coin) || "BTCUSDT",
      bestTimeframe: (m && m.params && m.params.period) || "1h",
    });
  }));
}


async function renderSettings(root) {
  const [settings, coinlist, bots] = await Promise.all([api("/settings"), api("/settings/coinlist"), api("/bots")]);
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
            ${field("Onay metni", `<input id="dg-confirm" placeholder="KAPAT / NAKIT / SIFIRLA">`)}
            <div class="row">
              <button class="danger" data-danger="close-all" type="button">Tüm pozisyonları kapat</button>
              <button class="danger" data-danger="full-cash" type="button">Full nakite geç</button>
            </div>
            <hr class="sep">
            <h3>İstatistikleri sıfırla</h3>
            <p class="muted small">
              İşlem geçmişi, K/Z grafikleri, sinyal ve olay kayıtları, kapanmış pozisyonlar ve
              bitmiş iş kayıtları silinir; botların birikmiş K/Z sayacı sıfırlanır.
              <b>Açık pozisyonlar ve nakit korunur.</b> Botlar durdurulur, sonra Botlar sayfasından başlatılır.
            </p>
            ${field("Bot", `<select id="dg-bot">
              <option value="">Tüm botlar</option>
              ${(bots || []).map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("")}
            </select>`)}
            <button class="danger mt" data-danger="reset-stats" type="button">İstatistikleri sıfırla</button>
          </div>
        </div>`;
      $("#pw-save").addEventListener("click", async () => {
        try {
          await api("/auth/change-password", { method: "POST", body: { current_password: $("#pw-old").value, new_password: $("#pw-new").value } });
          toast("Şifre değiştirildi"); $("#pw-old").value = ""; $("#pw-new").value = "";
        } catch (e) { toast(e.message, true); }
      });
      const DANGER_CONFIRM = { "close-all": "KAPAT", "full-cash": "NAKIT", "reset-stats": "SIFIRLA" };
      $$("[data-danger]").forEach((btn) => btn.addEventListener("click", async () => {
        const action = btn.dataset.danger;
        const isReset = action === "reset-stats";
        const expected = DANGER_CONFIRM[action] || "KAPAT";
        const confirmText = prompt(`Onay metnini yazın (${expected}):`, isReset ? "SIFIRLA" : "");
        if (!confirmText) return;
        const ok = await confirmDialog(
          isReset ? "İstatistikleri sıfırla" : "Gerçek emir gönderilecek",
          isReset
            ? "İşlem geçmişi ve tüm K/Z istatistikleri silinecek. Açık pozisyonlar ve nakit korunur; botlar durdurulur. Emin misin?"
            : "Bu işlem gerçek hesapta emir gönderir. Emin misin?",
          isReset ? "Sıfırla" : "Gönder",
          true,
        );
        if (!ok) return;
        try {
          const body = { password: $("#dg-pass").value, confirm: confirmText };
          const botSelect = $("#dg-bot");
          if (isReset && botSelect && botSelect.value) body.bot_id = botSelect.value;
          const res = await api(`/settings/danger/${action}`, { method: "POST", body });
          if (isReset) {
            const d = res.deleted || {};
            toast(`Sıfırlandı (${res.scope === "all" ? "tüm botlar" : res.scope}): ` +
              Object.entries(d).map(([k, v]) => `${k} ${v}`).join(", "));
            route();
          } else {
            toast(`${res.results.length} işlem sonucu alındı`);
          }
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
        ${field("Periyot", periodFieldHtml("snap-period", "15m"))}
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

  bindPeriodField("snap-period");

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
          period: readPeriod("snap-period"),
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
