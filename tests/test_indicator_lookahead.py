"""Pivot indikatörü nedensel mi? (lookahead bias regresyonu)

Eski `local_min_max`, pivotu kendi mumunda döndürüyordu → gelecekteki barları
kullanıyordu. Backtest'te Local_Min_Max stratejisi bu yüzden gerçekdışı getiri
gösteriyordu; canlıda ise sinyal gecikmeli/anlamsız oluyordu.
"""

from __future__ import annotations

from Indikator import Indikator


def _series(n=120):
    high, low = [], []
    price = 100.0
    for i in range(n):
        price += 1.0 if (i // 6) % 2 == 0 else -1.0
        high.append(price + 0.5)
        low.append(price - 0.5)
    return high, low


def test_pivot_has_no_lookahead():
    high, low = _series()
    full = Indikator.local_min_max(high, low, length=3)
    # Seriyi kısalt: geçmiş değerler değişmemeli.
    cut = 80
    part = Indikator.local_min_max(high[:cut], low[:cut], length=3)
    assert full[:cut] == part[:cut], "gelecekteki barlar geçmiş değerleri değiştiriyor"


def test_pivot_is_delayed_by_length():
    """Pivot, kendi mumunda değil ``length`` mum sonra görünür."""
    high, low = _series()
    length = 3
    values = Indikator.local_min_max(high, low, length=length)
    # İlk doğrulanabilir pivot en erken length*2. indekste yayınlanır.
    first = next((i for i, v in enumerate(values) if v is not None), None)
    assert first is not None
    assert first >= length * 2 - 1


def test_pivot_returns_same_length():
    high, low = _series(50)
    out = Indikator.local_min_max(high, low, length=3)
    assert len(out) == 50
