"""Eğitim verisi yükleme (Binance veya yerel CSV)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from app.paths import paths


def _normalise_market(data: Dict[str, Any]) -> Dict[str, Any]:
    """Listeleri float'a çevirir, zaman damgasını ms'e normalize eder."""
    out: Dict[str, Any] = {}
    for key in (
        "open", "high", "low", "close", "volume_coin", "volume_usdt",
        "trade_number", "buy_coin_volume", "buy_usdt_volume",
    ):
        out[key] = [float(v) for v in (data.get(key) or [])]
    ts = [float(v) for v in (data.get("opendate") or [])]
    if ts and max(ts) < 10_000_000_000:  # saniye ise ms'e çevir
        ts = [v * 1000.0 for v in ts]
    out["opendate"] = ts
    return out


def load_csv(path_text: str, limit: int) -> Dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = (paths.data / path_text).resolve()
    base = paths.data.resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise ValueError("CSV yalnızca Data/ klasöründen okunabilir")
    if not path.exists():
        raise FileNotFoundError(f"CSV bulunamadı: {path_text}")
    # Büyük CSV'lerde (ör. GB'lık 1m veri) tüm dosyayı belleğe almamak için
    # parça parça okuyup yalnızca son ``limit`` satırı tut.
    parts = []
    kept = 0
    for chunk in pd.read_csv(path, chunksize=200_000):
        parts.append(chunk)
        kept += len(chunk)
        if kept > max(limit * 2, 400_000):
            merged = pd.concat(parts, ignore_index=True).tail(limit)
            parts = [merged]
            kept = len(merged)
    if not parts:
        raise ValueError("CSV boş")
    frame = pd.concat(parts, ignore_index=True).tail(limit).reset_index(drop=True)
    cols = {str(c).strip().lower(): c for c in frame.columns}
    # Timestamp / opendate
    ts_col = cols.get("timestamp") or cols.get("opendate") or cols.get("time") or cols.get("date")
    if ts_col:
        raw = pd.to_numeric(frame[ts_col], errors="coerce")
        if raw.notna().sum() and raw.dropna().iloc[0] < 10_000_000_000:
            raw = raw * 1000.0
        ts = raw.to_numpy(dtype=float)
    else:
        ts = np.arange(len(frame), dtype=float) * 60_000.0
    mapping = {
        "open": cols.get("open"),
        "high": cols.get("high"),
        "low": cols.get("low"),
        "close": cols.get("close"),
        "volume_coin": cols.get("volume") or cols.get("volume_coin"),
        "volume_usdt": cols.get("volume_usdt") or cols.get("quote_volume"),
    }
    for key in ("open", "high", "low", "close"):
        if not mapping.get(key):
            raise ValueError(f"CSV'de {key} sütunu yok")
    payload: Dict[str, Any] = {"opendate": ts.tolist()}
    for key, col in mapping.items():
        if col:
            payload[key] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0).to_numpy(dtype=float).tolist()
    if not payload.get("volume_usdt") and not payload.get("volume_coin"):
        payload["volume_usdt"] = [0.0] * len(frame)
    data = _normalise_market(payload)
    n = len(data["close"])
    take = min(int(limit), n)
    for key in list(data.keys()):
        data[key] = data[key][-take:]
    return data


def load_market_data(
    coin: str = "BTCUSDT",
    period: str = "1h",
    limit: int = 20000,
    source: str = "binance",
    csv_path: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Veriyi kronolojik sırayla döndürür. Meta bilgisi rapora girer."""
    limit = max(500, min(int(limit), 250_000))
    if source == "csv" and csv_path:
        data = load_csv(csv_path, limit)
        meta = {"source": "csv", "path": csv_path, "requested": limit}
    else:
        from app.job_runner import _history
        from core import Binance

        client = Binance()
        data, history_meta = _history(client, coin.upper(), period, limit)
        data = _normalise_market(data)
        meta = {**dict(history_meta or {}), "source": "binance"}

    if not data.get("close"):
        raise RuntimeError("Veri boş döndü")
    # Tekrarları ve sırasızlığı temizle (kronolojik, tekil).
    ts = data["opendate"]
    if ts:
        order = np.argsort(np.asarray(ts, dtype=float))
        for key in list(data.keys()):
            data[key] = [data[key][i] for i in order]
        seen = set()
        keep = []
        for i, t in enumerate(data["opendate"]):
            if t in seen:
                continue
            seen.add(t)
            keep.append(i)
        if len(keep) != len(data["opendate"]):
            for key in list(data.keys()):
                data[key] = [data[key][i] for i in keep]

    n = len(data["close"])
    if n < 300:
        raise RuntimeError(f"Yetersiz veri: {n} mum (en az 300 gerekli)")
    meta.update(
        {
            "rows": n,
            "coin": coin.upper(),
            "period": period,
            "start": data["opendate"][0] if data.get("opendate") else None,
            "end": data["opendate"][-1] if data.get("opendate") else None,
        }
    )
    return data, meta
