"""Zaman serisi AI eğitimi ve model yönetimi.

Bu paket, ``Local_Min_Max`` stratejisinin "ütopik" hedeflerine yaklaşmak için
geçmiş mumlardan *geleceğe bakmadan* öğrenen modeller üretir.

Temel ilkeler:
- Özellikler yalnızca karar anına kadar olan (kapanmış) mumlardan üretilir.
- Etiketler gelecekteki fiyat hareketinden türetilir; eğitim/test ayrımında
  etiket ufku kadar "embargo" bırakılır. Böylece test satırının etiketi eğitim
  penceresine sızmaz.
- Veri asla karıştırılmaz (shuffle yok). Train < validation < test sırası korunur.
- Ölçekleme/doldurma yalnızca eğitim kümesinden öğrenilir.
"""

from __future__ import annotations

__all__ = ["features", "labels", "artifacts", "trainer", "strategy"]
