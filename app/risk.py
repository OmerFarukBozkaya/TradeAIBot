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


def _f(risk: Optional[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    """Risk sözlüğünden güvenli sayı okur (boş/bozuk değer → varsayılan)."""
    try:
        value = (risk or {}).get(key)
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------
# Seviyeler
# ----------------------------------------------------------------------
def effective_stop(
    entry: float,
    atr: float,
    highest: float,
    risk: Optional[Dict[str, Any]],
    floor: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """Etkin stop seviyesi ve türü.

    - ATR stop: ``giriş − stop_atr × ATR``, ``max_stop_pct`` ile tavanlanır.
    - Takipli stop: kâr ``trail_after_pct`` eşiğini geçince ``zirve − trail_atr × ATR``.
    - Breakeven: kâr ``breakeven_pct`` eşiğini geçince stop en az girişe çekilir.
    - ``floor``: kısmi kâr sonrası zorunlu taban (genelde giriş fiyatı).

    Döndürür: ``(fiyat, tür)``; tür ``stop`` / ``takipli-stop`` / ``breakeven``.
    """
    entry = float(entry)
    highest = float(highest or entry)
    atr = float(atr or 0.0)
    stop: Optional[float] = None
    kind = "stop"

    stop_atr = _f(risk, "stop_atr")
    if atr > 0 and stop_atr > 0:
        stop = entry - stop_atr * atr
        max_stop_pct = _f(risk, "max_stop_pct")
        if max_stop_pct > 0:
            stop = max(stop, entry * (1 - max_stop_pct / 100))

    trail_atr = _f(risk, "trail_atr")
    trail_after = _f(risk, "trail_after_pct")
    if atr > 0 and trail_atr > 0:
        armed = trail_after <= 0 or highest >= entry * (1 + trail_after / 100)
        if armed:
            trail = highest - trail_atr * atr
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

    return stop, kind


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
