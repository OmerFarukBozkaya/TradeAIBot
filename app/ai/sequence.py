"""Sıra (sequence) tabanlı modeller için ortak veri hattı.

LSTM ve Transformer, tek bir mumun özelliklerini değil **son N mumun
gidişatını** görür. Bu modül:

- ``SequenceData``: tam özellik matrisini tutar (n × F), ölçekler ve istenen
  konumlar için (N, T, F) pencereleri üretir.
- Ölçekleyici (mean/scale) yalnızca **eğitim satırlarından** öğrenilir; canlı
  çıkarımda aynı değerler paketten okunur. Böylece sızıntı olmaz.

Bellek dostudur: tüm pencereler önceden kopyalanmaz, yalnızca batch kadar
pencere üretilir.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

import numpy as np

CLIP = 8.0


def _fill_non_finite(values: np.ndarray, fill: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(values), values, fill)


class SequenceData:
    """Zaman serisi pencereleri üretir ve ölçekler."""

    def __init__(self, X: np.ndarray, window: int = 32):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim != 2:
            raise ValueError("X iki boyutlu olmalı (satır × özellik)")
        self.raw = X
        self.window = max(2, int(window))
        self.n, self.features = X.shape
        self.mean: Optional[np.ndarray] = None
        self.scale: Optional[np.ndarray] = None
        self.Z: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    def fit_scaler(self, positions: Sequence[int]) -> None:
        """Ölçekleyiciyi yalnızca verilen (eğitim) satırlardan öğrenir."""
        pos = np.asarray(positions, dtype=int)
        pos = pos[(pos >= 0) & (pos < self.n)]
        sub = self.raw[pos] if len(pos) else self.raw
        with np.errstate(invalid="ignore"):
            mean = np.nanmean(sub, axis=0)
            scale = np.nanstd(sub, axis=0)
        mean = np.where(np.isfinite(mean), mean, 0.0)
        scale = np.where(np.isfinite(scale) & (scale > 1e-9), scale, 1.0)
        self.mean = mean
        self.scale = scale
        self._build()

    def _build(self) -> None:
        if self.mean is None or self.scale is None:
            raise RuntimeError("Önce fit_scaler çağrılmalı")
        Z = (self.raw - self.mean) / self.scale
        Z = np.clip(Z, -CLIP, CLIP)
        Z = np.where(np.isfinite(Z), Z, 0.0)
        self.Z = Z.astype(np.float32)

    @classmethod
    def from_bundle(cls, X: np.ndarray, bundle: Dict[str, Any]) -> "SequenceData":
        """Eğitilmiş modelin ölçekleyicisiyle (canlı çıkarım) hazırlar."""
        window = int(bundle.get("seq_window") or 32)
        data = cls(X, window=window)
        scaler = bundle.get("seq_scaler") or {}
        mean = scaler.get("mean")
        scale = scaler.get("scale")
        if mean is None or scale is None:
            raise ValueError("Modelde sıra ölçekleyicisi yok")
        data.mean = np.asarray(mean, dtype=float)
        data.scale = np.asarray(scale, dtype=float)
        if data.mean.shape[0] != X.shape[1]:
            raise ValueError("Özellik şeması modelle uyuşmuyor")
        data._build()
        return data

    # ------------------------------------------------------------------
    def scalar(self) -> Dict[str, Any]:
        return {
            "mean": None if self.mean is None else self.mean.tolist(),
            "scale": None if self.scale is None else self.scale.tolist(),
        }

    def windows(self, positions: Sequence[int]) -> np.ndarray:
        """Verilen mutlak konumlar için (N, T, F) pencere yığını."""
        if self.Z is None:
            raise RuntimeError("Önce fit_scaler çağrılmalı")
        pos = np.asarray(positions, dtype=int)
        w = self.window
        if len(pos) == 0:
            return np.empty((0, w, self.features), dtype=np.float32)
        if pos.min() < w - 1:
            raise ValueError("Pencere için yeterli geçmiş yok")
        out = np.empty((len(pos), w, self.features), dtype=np.float32)
        for k, p in enumerate(pos):
            out[k] = self.Z[p - w + 1 : p + 1]
        return out

    def windows_batched(
        self,
        positions: Sequence[int],
        batch_size: int = 2048,
    ) -> Iterable[tuple[int, np.ndarray]]:
        pos = np.asarray(positions, dtype=int)
        for start in range(0, len(pos), batch_size):
            chunk = pos[start : start + batch_size]
            yield start, self.windows(chunk)

    def last_window(self) -> np.ndarray:
        """En son mum için tek pencere (canlı çıkarım)."""
        return self.windows([self.n - 1])


def subsample(positions: Sequence[int], max_items: int, stride: int = 1) -> np.ndarray:
    """Eğitim örneklerini seyreltir (maliyet kontrolü)."""
    pos = np.asarray(positions, dtype=int)
    if stride > 1:
        pos = pos[:: stride]
    if max_items > 0 and len(pos) > max_items:
        # Rastgele değil, eşit aralıklı: zaman dağılımı korunur.
        pick = np.linspace(0, len(pos) - 1, max_items).astype(int)
        pos = pos[pick]
    return pos
