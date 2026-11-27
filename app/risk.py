"""Ortak risk kuralları: stop, takipli stop, kâr al, breakeven, boyut.

Canlı/paper motor (`app.engine`) ve backtest (`app.job_runner`) **aynı**
fonksiyonları kullanır. Böylece panelde girilen bir ayar iki tarafta da aynı
sonucu verir; daha önce kâr al (ATR/yüzde) yalnızca backtest'te uygulanıyor,
destek/sabit/dinamik stop ise yalnızca canlıda çalışıyordu.

Kural önceliği (aynı mumda birden fazlası vurulursa kötümser olan kazanır):
    stop / takipli stop / breakeven  >  kâr al  >  sinyal
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DEFAULT_STATIC_STOP_PCT = 2.5
DEFAULT_SUPPORT_LOOKBACK = 300
DEFAULT_PARTIAL_FRACTION = 0.5

# ----------------------------------------------------------------------
# Güvenli stop sınırları
# ----------------------------------------------------------------------
# ATR çarpanı olarak verilen stop, bu değerin üzerine çıkamaz. 6×ATR'den
# uzak bir stop pratikte hiç tetiklenmez; pozisyon kârdan zarara döner.
MAX_STOP_ATR = 6.0
MAX_TRAIL_ATR = 6.0
MAX_TAKE_PROFIT_ATR = 8.0
DEFAULT_STOP_ATR = 2.0

# Her durumda geçerli mutlak tavan (yüzde).
ABSOLUTE_STOP_CAP = 20.0

# Periyoda göre stop tavanı (yüzde). ATR çarpanı bu mesafeyi aşamaz.
# Kısa periyotta stop yakın olmalı; yoksa zarar birikmeden çıkılmıyor.
PERIOD_STOP_CAP: Dict[str, float] = {
    "1m": 2.0, "3m": 2.5, "5m": 3.0, "15m": 4.0, "30m": 5.0,
    "45m": 5.5, "1h": 6.0, "2h": 7.0, "4h": 8.0, "6h": 9.0,
    "8h": 10.0, "12h": 10.0, "1d": 12.0, "3d": 14.0, "1w": 16.0,
    "1M": 18.0,
}

# Hiç stop kuralı tanımlanmadıysa kullanılacak varsayılan stop mesafesi (yüzde).
# Stratejide risk bloğu boş olan botlarda bile stop bulunmasını sağlar.
PERIOD_STOP_PCT: Dict[str, float] = {
    "1m": 1.0, "3m": 1.2, "5m": 1.5, "15m": 2.0, "30m": 2.5,
    "45m": 2.8, "1h": 3.0, "2h": 3.5, "4h": 4.5, "6h": 5.0,
    "8h": 5.5, "12h": 6.0, "1d": 7.0, "3d": 8.0, "1w": 10.0,
    "1M": 12.0,
}

DEFAULT_STOP_CAP = 12.0
DEFAULT_STOP_PCT = 5.0


def period_key(period: Any) -> str:
    """Periyot metnini kanonik anahtara çevirir (``2H`` → ``2h``, ``1Gun`` → ``1d``)."""
    text = str(period or "").strip()
    if not text:
        return ""
    try:
        from app.market_data.periods import parse_period

        return parse_period(text).text
    except Exception:  # noqa: BLE001 - bilinmeyen periyot: ham metin
        return text


def period_stop_cap(period: Any) -> float:
    """Periyodun izin verdiği en uzak stop mesafesi (yüzde)."""
    key = period_key(period)
    base = PERIOD_STOP_CAP.get(key)
    if base:
        return base
    # Bilinmeyen periyot: adım sayısından kaba tahmin (1m → 2, 1d → 12).
    if key:
        try:
            from app.market_data.periods import parse_period

            ms = parse_period(key).ms
            if ms <= 300_000:
                return 3.0
            if ms <= 3_600_000:
                return 5.0
            if ms <= 21_600_000:
                return 8.0
            if ms <= 86_400_000:
                return 12.0
            return 16.0
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_STOP_CAP


def period_default_stop_pct(period: Any) -> float:
    """Stop kuralı yoksa kullanılacak varsayılan mesafe (yüzde)."""
    key = period_key(period)
    if key in PERIOD_STOP_PCT:
        return PERIOD_STOP_PCT[key]
    return DEFAULT_STOP_PCT


def stop_cap_pct(period: Any, risk: Optional[Dict[str, Any]]) -> float:
    """Etkin stop tavanı (yüzde).

    Kullanıcı daha **sıkı** bir ``max_stop_pct`` verdiyse o kullanılır; daha
    geniş bir değer verirse periyot tavanı geçerli olur. Böylece 15m bir botta
    "%35 stop" gibi işe yaramaz ayarlar sessizce kabul edilmez.
    """
    cap = period_stop_cap(period)
    user = _f(risk, "max_stop_pct")
    if 0 < user < cap:
        cap = user
    return max(0.2, min(cap, ABSOLUTE_STOP_CAP))


def _f(risk: Optional[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    """Risk sözlüğünden güvenli sayı okur (boş/bozuk değer → varsayılan)."""
    try:
        value = (risk or {}).get(key)
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_risk_multipliers(risk: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Strateji tanımındaki ATR çarpanlarını güvenli sınıra çeker.

    Periyot bilinmediği için yalnızca **periyottan bağımsız** sınırlar uygulanır
    (``MAX_STOP_ATR``, ``MAX_TRAIL_ATR``, ``ABSOLUTE_STOP_CAP``). Periyoda özel
    tavan ve varsayılanlar bot oluşturulurken ``normalize_risk`` ile eklenir.
    """
    clean: Dict[str, Any] = dict(risk or {})
    warnings: List[str] = []
    for key, limit in (
        ("stop_atr", MAX_STOP_ATR),
        ("trail_atr", MAX_TRAIL_ATR),
        ("take_profit_atr", MAX_TAKE_PROFIT_ATR),
        ("partial_tp_atr", MAX_TAKE_PROFIT_ATR),
    ):
        value = _f(clean, key)
        if value > limit:
            clean[key] = limit
            warnings.append(f"{key} {value:g} → {limit:g}")
    cap = _f(clean, "max_stop_pct")
    if cap > ABSOLUTE_STOP_CAP:
        clean["max_stop_pct"] = ABSOLUTE_STOP_CAP
        warnings.append(f"max_stop_pct %{cap:g} → %{ABSOLUTE_STOP_CAP:g}")
    for key in ("static_stop_pct",):
        value = _f(clean, key)
        if value > ABSOLUTE_STOP_CAP:
            clean[key] = ABSOLUTE_STOP_CAP
            warnings.append(f"{key} %{value:g} → %{ABSOLUTE_STOP_CAP:g}")
    return clean, warnings


def normalize_risk(
    risk: Optional[Dict[str, Any]], period: Any = ""
) -> Tuple[Dict[str, Any], List[str]]:
    """Risk ayarlarını güvenli aralığa çeker ve **stop garantiler**.

    Sorun: strateji tanımlarında ``stop_atr`` çoğu zaman yüzde sanılarak
    20–35 yazılmıştı. Kod bunu ATR çarpanı olarak kullandığı için 1h'de %50,
    15m'de %36 uzaklıkta stoplar oluşuyordu; bunlar hiç tetiklenmiyor,
    pozisyon kârdan zarara dönüyordu. ``risk`` bloğu boş olan botlarda ise
    hiç stop yoktu (yalnızca çok uzak destek stop).

    Bu fonksiyon:
      - ATR çarpanlarını ``MAX_*`` sınırına çeker,
      - ``max_stop_pct`` değerini periyot tavanına indirir (her zaman yazar),
      - breakeven tanımlı değilse kâr koruması ekler,
      - hiç sert stop yoksa ``DEFAULT_STOP_ATR`` ekler.

    Döndürür: ``(temiz_risk, uyarilar)``. Uyarılar bot/log kaydına yazılır.
    """
    clean: Dict[str, Any] = dict(risk or {})
    warnings: List[str] = []

    for key, limit in (
        ("stop_atr", MAX_STOP_ATR),
        ("trail_atr", MAX_TRAIL_ATR),
        ("take_profit_atr", MAX_TAKE_PROFIT_ATR),
        ("partial_tp_atr", MAX_TAKE_PROFIT_ATR),
    ):
        value = _f(clean, key)
        if value > limit:
            clean[key] = limit
            warnings.append(f"{key} {value:g} → {limit:g} (güvenli üst sınır)")

    cap = period_stop_cap(period)
    user_cap = _f(clean, "max_stop_pct")
    if user_cap <= 0:
        clean["max_stop_pct"] = cap
    elif user_cap > cap:
        clean["max_stop_pct"] = cap
        warnings.append(
            f"max_stop_pct %{user_cap:g} → %{cap:g} ({period_key(period) or 'periyot'} tavanı)"
        )

    static_pct = _f(clean, "static_stop_pct")
    if static_pct > cap:
        clean["static_stop_pct"] = cap
        warnings.append(f"static_stop_pct %{static_pct:g} → %{cap:g} (tavan)")

    # Sert stop var mı? (breakeven tek başına sert stop değildir: kâr
    # eşiğine ulaşmadan hiçbir seviye üretmez.)
    hard_stop = (
        _f(clean, "stop_atr") > 0
        or _f(clean, "trail_atr") > 0
        or bool(clean.get("static_stop"))
        or bool(clean.get("dynamic_stop"))
    )
    if not hard_stop:
        clean["stop_atr"] = DEFAULT_STOP_ATR
        warnings.append(
            f"tanımlı stop yoktu → {DEFAULT_STOP_ATR:g}×ATR eklendi "
            f"(en çok %{cap:g})"
        )

    # Kâr koruması: breakeven tanımlı değilse stop mesafesinin ~%60'ı kadar
    # kârda stop girişe çekilir. "Kârdayken zarara dönme" şikâyetini çözer;
    # açıkça 0 yazıldıysa (kullanıcı kapattıysa) dokunulmaz.
    raw_be = clean.get("breakeven_pct")
    if raw_be is None or raw_be == "":
        clean["breakeven_pct"] = max(0.5, round(cap * 0.6, 1))
        warnings.append(
            f"breakeven eklendi (%{clean['breakeven_pct']:g} kârda stop girişe)"
        )

    return clean, warnings


# ----------------------------------------------------------------------
# Seviyeler
# ----------------------------------------------------------------------
def effective_stop(
    entry: float,
    atr: float,
    highest: float,
    risk: Optional[Dict[str, Any]],
    floor: Optional[float] = None,
    period: Any = "",
    atr_now: Optional[float] = None,
    previous_stop: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """Etkin stop seviyesi ve türü.

    - ATR stop: ``giriş − stop_atr × ATR``, periyot tavanı ile sınırlanır.
      Bu **girişteki** ATR ile sabitlenir (pozisyonun ilk koruması).
    - Takipli stop: kâr ``trail_after_pct`` eşiğini geçince
      ``zirve − trail_atr × ATR(şimdi)``. Güncel ATR kullanılır; böylece
      oynaklık artınca stop sıkışıp trendi erken kesmez.
    - Breakeven: kâr ``breakeven_pct`` eşiğini geçince stop en az girişe çekilir.
    - ``floor``: kısmi kâr sonrası zorunlu taban (genelde giriş fiyatı).

    **Stop asla geri gitmez (ratchet).** ``previous_stop`` verilirse dönen
    seviye ondan aşağı olamaz. Aksi halde oynaklık artışı veya zirvenin
    gerilemesi takipli stopu gevşetir; trend takibinde bu istenmeyen
    davranıştır (kâr geri verilir).

    **Stop garantisi:** hiçbir kural stop üretmiyorsa periyodun varsayılan
    yüzdesi kullanılır. Ayrıca hiçbir stop periyot tavanından (``max_stop_pct``
    veya ``PERIOD_STOP_CAP``) daha uzağa konamaz.

    Döndürür: ``(fiyat, tür)``; tür ``stop`` / ``takipli-stop`` / ``breakeven``.
    """
    entry = float(entry)
    highest = float(highest or entry)
    atr = float(atr or 0.0)
    # Güncel ATR: takipli stop için. Verilmezse giriş ATR'si.
    try:
        trail_atr_base = float(atr_now) if atr_now else 0.0
    except (TypeError, ValueError):
        trail_atr_base = 0.0
    if trail_atr_base <= 0:
        trail_atr_base = atr
    stop: Optional[float] = None
    kind = "stop"

    cap_pct = stop_cap_pct(period, risk)
    cap_price = entry * (1 - cap_pct / 100.0)

    stop_atr = _f(risk, "stop_atr")
    if stop_atr > 0:
        stop_atr = min(stop_atr, MAX_STOP_ATR)
        if atr > 0:
            stop = entry - stop_atr * atr
        else:
            # ATR hesaplanamadıysa çarpanı anlamsız; varsayılan yüzdeyi kullan.
            stop = entry * (1 - period_default_stop_pct(period) / 100.0)

    trail_atr = _f(risk, "trail_atr")
    trail_after = _f(risk, "trail_after_pct")
    if trail_atr > 0:
        trail_atr = min(trail_atr, MAX_TRAIL_ATR)
        armed = trail_after <= 0 or highest >= entry * (1 + trail_after / 100)
        if armed and trail_atr_base > 0:
            trail = highest - trail_atr * trail_atr_base
            if stop is None or trail > stop:
                stop = trail
                kind = "takipli-stop"

    breakeven_pct = _f(risk, "breakeven_pct")
    if breakeven_pct > 0 and highest >= entry * (1 + breakeven_pct / 100):
        if stop is None or entry > stop:
            stop = entry
            kind = "breakeven"

    floor_price = None
    if floor is not None:
        try:
            floor_price = float(floor)
        except (TypeError, ValueError):
            floor_price = None
    if floor_price is not None and (stop is None or floor_price > stop):
        stop = floor_price
        kind = "breakeven"

    if stop is None:
        # Hiç kural yok: varsayılan yüzde stop (periyoda göre).
        stop = entry * (1 - period_default_stop_pct(period) / 100.0)
        kind = "stop"

    # Tavan: periyot/kullanıcı sınırından daha uzak stop yok.
    if stop < cap_price:
        stop = cap_price

    # Ratchet: stop asla geri gitmez. Aksi halde oynaklık artışı ya da zirvenin
    # gerilemesi takipli stopu gevşetir; trend takibinde kâr geri verilir.
    prev = None
    if previous_stop is not None:
        try:
            prev = float(previous_stop)
        except (TypeError, ValueError):
            prev = None
    if prev is not None and prev > 0 and prev > stop:
        stop = prev
        if kind == "stop" and trail_atr > 0:
            kind = "takipli-stop"

    return stop, kind


def stop_distance_pct(entry: float, stop: Optional[float]) -> Optional[float]:
    """Stop mesafesi (yüzde, pozitif = girişin altında)."""
    try:
        entry = float(entry)
        stop = float(stop)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if entry <= 0 or stop <= 0:
        return None
    return (entry - stop) / entry * 100.0


def target_price(
    entry: float, atr: float, risk: Optional[Dict[str, Any]]
) -> Optional[float]:
    """Kâr al hedefi: ATR ve/veya yüzde. İkisi de açıksa **yakın** olan seçilir."""
    entry = float(entry)
    atr = float(atr or 0.0)
    # Panelde "Kâr al" kutusu kapatıldıysa sayısal hedefler uygulanmaz.
    if risk is not None and risk.get("take_profit") is False:
        return None
    targets: List[float] = []
    tp_pct = _f(risk, "take_profit_pct")
    if tp_pct > 0:
        targets.append(entry * (1 + tp_pct / 100))
    tp_atr = _f(risk, "take_profit_atr")
    if tp_atr > 0 and atr > 0:
        targets.append(entry + tp_atr * atr)
    return min(targets) if targets else None


def partial_target_price(
    entry: float, atr: float, risk: Optional[Dict[str, Any]]
) -> Optional[float]:
    """Kısmi kâr hedefi (pozisyonun bir kısmını sat). Kapalıysa ``None``."""
    entry = float(entry)
    atr = float(atr or 0.0)
    fraction = partial_fraction(risk)
    if fraction <= 0:
        return None
    if risk is not None and risk.get("take_profit") is False:
        return None
    targets: List[float] = []
    p_pct = _f(risk, "partial_tp_pct")
    if p_pct > 0:
        targets.append(entry * (1 + p_pct / 100))
    p_atr = _f(risk, "partial_tp_atr")
    if p_atr > 0 and atr > 0:
        targets.append(entry + p_atr * atr)
    return min(targets) if targets else None


def partial_fraction(risk: Optional[Dict[str, Any]]) -> float:
    """Kısmi satışta satılacak oran (0 = kapalı). 0,05–1 aralığına kırpılır."""
    raw = _f(risk, "partial_tp_fraction", DEFAULT_PARTIAL_FRACTION)
    if raw <= 0:
        return 0.0
    return max(0.05, min(raw, 1.0))


def static_stop_price(entry: float, risk: Optional[Dict[str, Any]]) -> Optional[float]:
    """Sabit yüzde stop (eski ``static_stop`` kutusu)."""
    pct = _f(risk, "static_stop_pct", DEFAULT_STATIC_STOP_PCT)
    if pct <= 0:
        pct = DEFAULT_STATIC_STOP_PCT
    return float(entry) * (1 - pct / 100)


def dynamic_stop_level(
    highest: float, atr: float, adx: Optional[float], risk: Optional[Dict[str, Any]]
) -> Optional[float]:
    """ADX'e duyarlı takipli stop (eski ``dynamic_stop`` kutusu).

    ADX < 20 (yatay piyasa) ise stop kapalıdır — bu bilinçli bir tercih değil,
    eski davranışın korunmasıdır; panelde uyarı olarak gösterilir.
    """
    atr = float(atr or 0.0)
    if atr <= 0 or adx is None:
        return None
    try:
        adx = float(adx)
    except (TypeError, ValueError):
        return None
    if adx < 20:
        return None
    factor = 2.0 if adx > 30 else 1.2
    return float(highest) - factor * atr


def dynamic_stop_hit(
    close: float, level: Optional[float], risk: Optional[Dict[str, Any]]
) -> bool:
    if level is None:
        return False
    tolerance = _f(risk, "dynamic_stop_tolerance_pct", 1.0)
    return float(close) < float(level) * (1 - tolerance / 100)


def support_break(
    close: float, destek: Optional[float], risk: Optional[Dict[str, Any]] = None
) -> bool:
    """Saklanan destek seviyesi kırıldı mı? (seviye yeniden hesabı gerektirmez)"""
    if destek is None:
        return False
    tolerance = _f(risk, "support_tolerance_pct", 1.0)
    return float(close) < float(destek) * (1 - tolerance / 100)


def support_refresh(risk: Optional[Dict[str, Any]]) -> int:
    """Destek/direnç seviyelerinin kaç mumda bir yeniden hesaplanacağı."""
    step = int(_f(risk, "support_refresh", 10) or 10)
    return max(1, min(step, 500))


# ----------------------------------------------------------------------
# Destek stop (eski kural, performans için son N mumla sınırlı)
# ----------------------------------------------------------------------
def support_stop(
    buy_price: float,
    destek: Optional[float],
    direnc: Optional[float],
    close: List[float],
    low: List[float],
    risk: Optional[Dict[str, Any]] = None,
    end: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Destek/direnç seviyelerini ve stop sinyalini döndürür.

    Eski kod her turda tüm geçmişi tarıyordu (O(n) + sıralama). Burada yalnızca
    son ``support_lookback`` mum (varsayılan 300) incelenir. ``end`` verilirse
    pencere o indekste biter (backtest için); verilmezse son mum esas alınır.
    """
    from core import Stratejiler

    lookback = int(_f(risk, "support_lookback", DEFAULT_SUPPORT_LOOKBACK) or DEFAULT_SUPPORT_LOOKBACK)
    lookback = max(50, min(lookback, 2000))
    if end is None:
        end = len(close)
    start = max(0, end - lookback)
    window_close = list(close[start:end])
    window_low = list(low[start:end])
    if len(window_low) < 10:
        return destek, direnc, None
    result = Stratejiler.destek_stop_lose(
        buy_price, destek, direnc, window_close, window_low
    )
    if not result:
        return destek, direnc, None
    return result


# ----------------------------------------------------------------------
# Pozisyon boyutu
# ----------------------------------------------------------------------
def daily_loss_exceeded(
    start_equity: float, current_equity: float, limit_pct: float
) -> bool:
    """Günlük zarar limiti aşıldı mı?

    ``limit_pct`` 0 veya negatifse koruma kapalıdır. Gün başındaki özkaynak
    bilinmiyorsa (0) da engelleme yapılmaz; aksi halde bot hiç işlem açamaz.
    """
    try:
        limit = float(limit_pct or 0.0)
        start = float(start_equity or 0.0)
        current = float(current_equity or 0.0)
    except (TypeError, ValueError):
        return False
    if limit <= 0 or start <= 0:
        return False
    return (current / start - 1.0) * 100.0 <= -limit


def position_budget(
    cash: float,
    entry: float,
    stop_price: Optional[float],
    risk: Optional[Dict[str, Any]],
    max_position_pct: float,
) -> float:
    """İşlem için ayrılacak USDT.

    ``risk_per_trade_pct`` > 0 ve stop biliniyorsa boyut, **stop mesafesine**
    göre hesaplanır: her işlemde kaybedilecek tutar sabit kalır.

        bütçe = (nakit × risk_%) / (stop mesafesi)

    Stop yoksa eski davranış: ``nakit × max_position_pct``.
    """
    cash = max(0.0, float(cash or 0.0))
    entry = float(entry or 0.0)
    max_pct = max(0.0, min(float(max_position_pct or 0.0), 1.0))
    cap = cash * max_pct
    risk_pct = _f(risk, "risk_per_trade_pct")
    if risk_pct <= 0 or entry <= 0 or stop_price is None:
        return cap
    try:
        stop_price = float(stop_price)
    except (TypeError, ValueError):
        return cap
    distance = (entry - stop_price) / entry
    if distance <= 0:
        return cap
    risk_amount = cash * risk_pct / 100
    budget = risk_amount / distance
    return max(0.0, min(budget, cap))


# ----------------------------------------------------------------------
# Kapanış nedeni etiketleri (panel ve raporlar için ortak)
# ----------------------------------------------------------------------
EXIT_REASON_LABELS = {
    "signal": "sinyal",
    "stop": "stop",
    "takipli-stop": "takipli stop",
    "breakeven": "breakeven",
    "take-profit": "kâr al",
    "take-profit-partial": "kısmi kâr al",
    "profit-exit": "kâr koruma",
    "destek-stop": "destek stop",
    "dinamik-stop": "dinamik stop",
    "statik-stop": "sabit stop",
    "manuel": "manuel satış",
    "harici": "harici işlem",
}
