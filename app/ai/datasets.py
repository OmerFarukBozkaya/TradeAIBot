"""Sabit (dondurulmuş) fiyat veri setleri.

Amaç: her eğitimde Binance'e tekrar tekrar istek atmamak. Fiyat verisi bir kez
çekilir, diske yazılır ve sonraki eğitimler bu sabit kopyadan okunur.

- Bir veri seti coin + periyot + zaman aralığı ile tanımlıdır.
- Aynı coin/periyot için yeni snapshot oluşturulursa en yenisi kullanılır.
- İndikatörler veri setinden **yeniden hesaplanır**; sadece ham OHLCV saklanır.
  Böylece indikatör tanımı değişince veri yeniden çekmek gerekmez.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.paths import paths

DATASET_ROOT = paths.data / "AI" / "datasets"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]{3,120}$")
_FIELDS = ("opendate", "open", "high", "low", "close", "volume_usdt", "volume_coin")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(dataset_id: str) -> str:
    value = str(dataset_id or "").strip()
    if not _SAFE.match(value):
        raise ValueError("Geçersiz veri seti kimliği")
    return value


def folder(dataset_id: str):
    return DATASET_ROOT / _safe_id(dataset_id)


_COIN_RE = re.compile(r"^[A-Z0-9:._=/+-]{2,40}$")
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _slug(value: str) -> str:
    text = _SLUG_RE.sub("_", str(value or "").strip()).strip("._")
    return text[:40] or "sym"


def _check(coin: str, period: str) -> Tuple[str, str]:
    from app.market_data.periods import parse_period

    coin = str(coin or "").strip().upper()
    period = str(period or "").strip()
    if not _COIN_RE.match(coin):
        raise ValueError("Geçersiz sembol")
    try:
        period = parse_period(period).text
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    return coin, period


def _fingerprint(coin: str, period: str, rows: int) -> str:
    text = f"{coin}|{period}|{rows}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def save(
    data: Dict[str, Any],
    *,
    coin: str,
    period: str,
    source: str = "binance",
    name: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ham OHLCV verisini diske yazar ve manifest döndürür."""
    coin, period = _check(coin, period)
    close = list(data.get("close") or [])
    if len(close) < 300:
        raise ValueError(f"Veri seti çok küçük: {len(close)} mum (en az 300)")
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    code = _slug(coin)
    dataset_id = f"ds_{stamp}_{code}_{period}_{_fingerprint(coin, period, len(close))}"
    target = folder(dataset_id)
    suffix = 1
    while target.exists():
        dataset_id = f"ds_{stamp}_{code}_{period}_{_fingerprint(coin, period, len(close))}_{suffix}"
        target = folder(dataset_id)
        suffix += 1
    target.mkdir(parents=True, exist_ok=False)

    arrays = {}
    for key in _FIELDS:
        values = data.get(key)
        arrays[key] = np.asarray(values if values is not None else [0.0] * len(close), dtype=np.float64)
    tmp = target / "data.tmp.npz"
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, target / "data.npz")

    manifest = {
        "id": dataset_id,
        "name": name or f"{coin} {period}",
        "coin": coin,
        "period": period,
        "rows": int(len(close)),
        "source": source,
        "created_at": _now(),
        "start": float(arrays["opendate"][0]) if len(close) else None,
        "end": float(arrays["opendate"][-1]) if len(close) else None,
        "size_bytes": int((target / "data.npz").stat().st_size),
        "fields": list(_FIELDS),
        **(extra or {}),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _update_index(manifest)
    return manifest


def load(dataset_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Kayıtlı veri setini okur. Ağ erişimi yoktur."""
    target = folder(dataset_id)
    data_path = target / "data.npz"
    manifest_path = target / "manifest.json"
    if not data_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(f"Veri seti bulunamadı: {dataset_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with np.load(data_path, allow_pickle=False) as npz:
        data = {key: npz[key].astype(float).tolist() for key in npz.files}
    return data, manifest


def manifest(dataset_id: str) -> Optional[Dict[str, Any]]:
    path = folder(dataset_id) / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _update_index(item: Dict[str, Any]) -> None:
    """Aynı coin/periyot için hızlı arama indeksi."""
    index_path = DATASET_ROOT / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        if not isinstance(index, dict):
            index = {}
    except (ValueError, OSError):
        index = {}
    index[item["id"]] = {
        "id": item["id"],
        "coin": item["coin"],
        "period": item["period"],
        "rows": item["rows"],
        "created_at": item["created_at"],
        "start": item.get("start"),
        "end": item.get("end"),
        "size_bytes": item.get("size_bytes"),
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def list_datasets() -> List[Dict[str, Any]]:
    if not DATASET_ROOT.exists():
        return []
    items: List[Dict[str, Any]] = []
    for child in DATASET_ROOT.iterdir():
        if not child.is_dir():
            continue
        meta = manifest(child.name)
        if meta:
            items.append(meta)
    items.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    return items


def latest(coin: str, period: str) -> Optional[Dict[str, Any]]:
    coin, period = _check(coin, period)
    for meta in list_datasets():  # newest first
        if str(meta.get("coin")) == coin and str(meta.get("period")) == period:
            return meta
    return None


def delete(dataset_id: str) -> Dict[str, Any]:
    target = folder(dataset_id)
    if not target.exists():
        raise ValueError("Veri seti bulunamadı")
    shutil.rmtree(target)
    index_path = DATASET_ROOT / "index.json"
    try:
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8")) or {}
            if isinstance(index, dict):
                index.pop(dataset_id, None)
                index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except (ValueError, OSError):
        pass
    return {"ok": True, "id": dataset_id}


def resolve(
    coin: str,
    period: str,
    limit: int,
    *,
    dataset_id: str = "",
    refresh: bool = False,
    auto_snapshot: bool = True,
    source: str = "auto",
    asset_class: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Eğitim için veriyi döndürür; mümkünse ağa çıkmadan.

    Öncelik:
    1. Açıkça seçilmiş ``dataset_id``
    2. ``auto_snapshot`` açıksa aynı coin/periyot için en yeni snapshot
    3. Canlı çekim (ve ``auto_snapshot`` açıksa diske kaydet)
    """
    from app.ai.data import load_market_data as live_load

    coin, period = _check(coin, period)
    limit = max(500, min(int(limit), 250_000))

    if dataset_id:
        data, meta = load(dataset_id)
        n = len(data.get("close") or [])
        if n > limit:
            for key in list(data.keys()):
                data[key] = data[key][-limit:]
            n = limit
        meta = {
            **meta,
            "rows": n,
            "dataset_id": meta.get("id"),
            "reused": True,
            "pinned": True,
            "requested": limit,
        }
        return data, meta

    if auto_snapshot and not refresh:
        found = latest(coin, period)
        if found and int(found.get("rows") or 0) >= min(500, limit):
            data, meta = load(found["id"])
            n = len(data.get("close") or [])
            if n > limit:
                for key in list(data.keys()):
                    data[key] = data[key][-limit:]
                n = limit
            meta = {
                **meta,
                "rows": n,
                "dataset_id": meta.get("id"),
                "reused": True,
                "pinned": False,
                "requested": limit,
            }
            return data, meta

    if asset_class:
        data, meta = live_load(coin, period, limit, source, "", asset_class=asset_class)
    else:
        data, meta = live_load(coin, period, limit, source, "")
    meta = dict(meta)
    meta["dataset_id"] = None
    meta["reused"] = False
    meta["pinned"] = False
    if auto_snapshot:
        try:
            saved = save(
                data, coin=coin, period=period, source=str(meta.get("source") or source),
                extra={"limit": limit, "asset_class": asset_class},
            )
            meta["dataset_id"] = saved["id"]
            meta["saved_snapshot"] = True
        except Exception as exc:  # noqa: BLE001 - snapshot başarısızsa eğitim devam eder
            meta["saved_snapshot"] = False
            meta["snapshot_error"] = str(exc)[:200]
    return data, meta
