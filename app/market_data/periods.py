"""Serbest periyot ayrıştırma ve kaynak periyodu seçimi.

Desteklenen biçim: ``<sayı><birim>``
  - m: dakika
  - h: saat
  - d: gün
  - w: hafta
  - M: ay (büyük M)
  - y: yıl

Örnekler: ``15m``, ``45m``, ``2h``, ``3d``, ``1w``, ``1M``, ``1y``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

_PERIOD_RE = re.compile(r"^\s*(\d{1,4})\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)?\s*$")

_UNIT_MS = {
    "m": 60_000.0,
    "h": 3_600_000.0,
    "d": 86_400_000.0,
    "w": 604_800_000.0,
    "M": 2_592_000_000.0,   # 30 gün (takvim ayı için yaklaşık)
    "y": 31_536_000_000.0,  # 365 gün
}

_UNIT_LABEL = {
    "m": "dakika",
    "h": "saat",
    "d": "gün",
    "w": "hafta",
    "M": "ay",
    "y": "yıl",
}

# Kullanıcı yazımını kanonik birime çevirir. Büyük/küçük harf ve Türkçe
# kısaltmalar (gün, hafta, ay, yıl, saat, dk) kabul edilir.
_UNIT_ALIASES = {
    "m": "m", "min": "m", "mins": "m", "dk": "m", "dakika": "m",
    "h": "h", "hr": "h", "hrs": "h", "saat": "h", "st": "h",
    "d": "d", "day": "d", "days": "d", "g": "d", "gun": "d",
    "gün": "d",
    "w": "w", "wk": "w", "week": "w", "hf": "w", "hafta": "w",
    "ay": "M", "mo": "M", "month": "M",
    "y": "y", "yr": "y", "year": "y", "yil": "y", "yıl": "y",
}


def _normalise_unit(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    # Tek harf: m/h/d/w/M/y — M büyükse ay, diğerleri küçük harfe düşer.
    if len(raw) == 1:
        if raw == "M":
            return "M"
        lowered = raw.lower()
        if lowered in _UNIT_MS:
            return lowered
        # Türkçe tek harf kısaltması: G (gün)
        return {"g": "d"}.get(lowered, "")
    low = raw.replace("İ", "i").replace("I", "ı").lower()
    return _UNIT_ALIASES.get(low, "")


def parse_period(value: str) -> Period:
    text = str(value or "").strip()
    match = _PERIOD_RE.match(text)
    if not match or not match.group(2):
        raise ValueError(
            f"Geçersiz periyot: {value!r}. Örnek: 15m, 45m, 2h, 4h, 1d, 3d, 1w, 1M, 1y"
        )
    count = int(match.group(1))
    unit = _normalise_unit(match.group(2))
    if not unit:
        raise ValueError(
            f"Geçersiz periyot birimi: {value!r}. Kullanılabilir: m, h, d, w, M, y"
        )
    if count < 1:
        raise ValueError("Periyot sayısı en az 1 olmalı")
    if count > 1000:
        raise ValueError("Periyot sayısı çok büyük (en fazla 1000)")
    canonical = f"{count}{unit}"
    return Period(text=canonical, count=count, unit=unit, ms=count * _UNIT_MS[unit])


@dataclass(frozen=True)
class Period:
    text: str
    count: int
    unit: str
    ms: float

    @property
    def pandas_rule(self) -> str:
        """pandas resample kuralı (sol etiketli, UTC)."""
        n = self.count
        if self.unit == "m":
            return f"{n}min"
        if self.unit == "h":
            return f"{n}h"
        if self.unit == "d":
            return f"{n}D"
        if self.unit == "w":
            return f"{n}W-MON"
        if self.unit == "M":
            return f"{n}MS"
        return f"{n}YS"

    @property
    def fixed(self) -> bool:
        """Takvimden bağımsız (sabit milisaniye) periyot mu?"""
        return self.unit in {"m", "h", "d", "w"}

    @property
    def label(self) -> str:
        return f"{self.count} {_UNIT_LABEL[self.unit]}"


def period_ms(value: str) -> Optional[float]:
    try:
        return parse_period(value).ms
    except ValueError:
        return None


def choose_base_period(target: str | Period, available: Iterable[str]) -> Optional[str]:
    """İstenen periyodu üretmek için kullanılacak en büyük kaynak periyodu seçer.

    - Sabit periyotlarda (m/h/d/w) hedef, kaynak periyodun tam katı olmalıdır.
      Böylece 45m istenirse 30m değil 15m kaynağı seçilir.
    - Ay/yıl gibi takvim periyotlarında daha küçük herhangi bir kaynak uygundur.
    """
    want = target if isinstance(target, Period) else parse_period(target)
    candidates: List[Period] = []
    for item in available:
        try:
            parsed = parse_period(item)
        except ValueError:
            continue
        if parsed.text == want.text:
            return parsed.text
        if parsed.ms >= want.ms:
            continue
        if want.fixed and (want.ms % parsed.ms) != 0:
            continue
        candidates.append(parsed)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.ms, reverse=True)
    return candidates[0].text
