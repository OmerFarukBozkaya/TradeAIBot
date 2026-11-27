"""Piyasa rejimi yardımcıları.

Tek coinin trendi ile **piyasanın** trendi aynı şey değildir. Altcoinlerin
büyük kısmı BTC'nin yönüne yüksek korelasyonla bağlıdır; BTC 200 periyotluk
ortalamasının altındayken alım açmak, strateji doğru olsa bile art arda stop
olmaya yol açar. Bu modül, botlarda ve backtest'te kullanılan **risk-on /
risk-off** filtresini üretir.

Kural bilinçli olarak basittir ve parametre içermez:

    rejim = kapanış > EMA(200)

EMA yeterli geçmiş yoksa filtre uygulanmaz (``True``); böylece yeni listelenen
bir sembol yanlışlıkla bloke edilmez.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def ema(values: Iterable[float], length: int) -> List[Optional[float]]:
    """``None`` toleranslı EMA (Pine ile aynı özyineleme).

    İlk geçerli değer tohum olarak kullanılır. ``None`` gelen mumda önceki
    değer korunur.
    """
    length = int(length)
    if length <= 0:
        return [None for _ in values]
    k = 2.0 / (length + 1.0)
    out: List[Optional[float]] = []
    prev: Optional[float] = None
    for value in values:
        if value is None:
            out.append(prev)
            continue
        current = float(value)
        prev = current if prev is None else prev + k * (current - prev)
        out.append(prev)
    return out


def regime_flags(closes: Iterable[float], length: int = 200) -> List[bool]:
    """Her mum için ``kapanış > EMA(length)`` sonucu.

    İlk ``length`` mumda yeterli geçmiş olmadığı için filtre uygulanmaz
    (``True`` döner). Veri boşsa boş liste döner.
    """
    values = [None if v is None else float(v) for v in closes]
    n = len(values)
    length = max(1, int(length))
    if n == 0:
        return []
    averages = ema(values, length)
    flags: List[bool] = []
    for index, (close, average) in enumerate(zip(values, averages)):
        if index < length or close is None or average is None:
            flags.append(True)
        else:
            flags.append(close > average)
    return flags


def regime_map(data: Dict[str, Any], length: int = 200) -> Dict[int, bool]:
    """``opendate`` → rejim eşlemesi (backtest'te hızlı arama için).

    Zaman damgası yoksa boş sözlük döner; çağıran taraf filtreyi atlar.
    """
    times = data.get("opendate") or []
    closes = data.get("close") or []
    if not times or not closes:
        return {}
    flags = regime_flags(closes, length)
    return {int(t): bool(flag) for t, flag in zip(times, flags)}


def last_regime(closes: Iterable[float], length: int = 200) -> bool:
    """Son mumun rejimi. Yeterli veri yoksa ``True`` (filtre uygulanmaz)."""
    flags = regime_flags(closes, length)
    return bool(flags[-1]) if flags else True
