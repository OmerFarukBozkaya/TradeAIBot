"""AI model kataloğu ve canlı işlem deneyimi deposu."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import db
from app.paths import paths

try:
    import joblib  # type: ignore
except Exception:  # pragma: no cover
    joblib = None  # type: ignore

MODEL_ROOT = paths.data / "Model" / "ai"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(model_id: str) -> str:
    value = str(model_id or "").strip()
    if not _SAFE_ID.match(value):
        raise ValueError("Geçersiz model kimliği")
    return value


def model_dir(model_id: str) -> Path:
    return MODEL_ROOT / _safe_id(model_id)


def _dump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        if joblib is not None:
            joblib.dump(obj, handle)
        else:
            pickle.dump(obj, handle)
    os.replace(tmp, path)


def _load_model_file(path: Path) -> Any:
    with open(path, "rb") as handle:
        if joblib is not None:
            return joblib.load(handle)
        return pickle.load(handle)


def data_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def save_model(
    *,
    name: str,
    bundle: Dict[str, Any],
    params: Dict[str, Any],
    metrics: Dict[str, Any],
    data_meta: Dict[str, Any],
    feature_names: List[str],
    thresholds: Dict[str, float],
    notes: str = "",
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Modeli diske ve SQLite kataloğuna yazar.

    ``model_id`` verilirse **aynı model** güncellenir: dosya yerinde kalır,
    sürüm numarası artar ve önceki denemeler `history` altında saklanır.
    Böylece aynı modeli tekrar tekrar eğitmek mümkündür.
    """
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    existing: Optional[Dict[str, Any]] = None
    if model_id:
        model_id = _safe_id(model_id)
        existing = load_manifest(model_id)
        if not existing:
            raise ValueError(f"Model bulunamadı: {model_id}")
        folder = model_dir(model_id)
        folder.mkdir(parents=True, exist_ok=True)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^A-Za-z0-9]+", "_", str(name or "model")).strip("_")[:28] or "model"
        model_id = f"ai_{stamp}_{slug}_{data_hash(params)[:6]}"
        folder = model_dir(model_id)
        suffix = 1
        while folder.exists():
            model_id = f"ai_{stamp}_{slug}_{data_hash(params)[:6]}_{suffix}"
            folder = model_dir(model_id)
            suffix += 1
        folder.mkdir(parents=True, exist_ok=False)

    _dump(bundle, folder / "model.pkl")
    version = int((existing or {}).get("version") or 0) + 1
    history = list((existing or {}).get("history") or [])
    if existing:
        history.append(
            {
                "version": int(existing.get("version") or 1),
                "created_at": existing.get("created_at"),
                "metrics": (existing.get("metrics") or {}).get("test"),
                "validation": (existing.get("metrics") or {}).get("validation"),
                "thresholds": existing.get("thresholds"),
            }
        )
        history = history[-20:]
    manifest = {
        "id": model_id,
        "name": name or (existing or {}).get("name") or model_id,
        "created_at": (existing or {}).get("created_at") or _now(),
        "updated_at": _now(),
        "status": (existing or {}).get("status") or "candidate",
        "version": version,
        "trained_versions": version,
        "params": params,
        "feature_names": feature_names,
        "thresholds": thresholds,
        "metrics": metrics,
        "data": data_meta,
        "notes": notes,
        "history": history,
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    db.execute(
        "INSERT OR REPLACE INTO ai_models(id,name,status,manifest_json,metrics_json,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            model_id,
            manifest["name"],
            manifest["status"],
            json.dumps(manifest, ensure_ascii=False, default=str),
            json.dumps(metrics, ensure_ascii=False, default=str),
            manifest["created_at"],
            manifest["updated_at"],
        ),
    )
    return manifest


def load_manifest(model_id: str) -> Optional[Dict[str, Any]]:
    folder = model_dir(model_id)
    path = folder / "manifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    row = db.row("SELECT manifest_json FROM ai_models WHERE id=?", (model_id,))
    if row and row.get("manifest_json"):
        try:
            return json.loads(row["manifest_json"])
        except ValueError:
            return None
    return None


def load_bundle(model_id: str) -> Dict[str, Any]:
    path = model_dir(model_id) / "model.pkl"
    if not path.exists():
        raise FileNotFoundError(f"Model dosyası yok: {model_id}")
    return _load_model_file(path)


def list_models(include_archived: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM ai_models"
    if not include_archived:
        sql += " WHERE status != 'archived'"
    sql += " ORDER BY created_at DESC"
    rows = db.rows(sql)
    items: List[Dict[str, Any]] = []
    for row in rows:
        try:
            manifest = json.loads(row.get("manifest_json") or "{}")
        except ValueError:
            manifest = {}
        if not manifest:
            continue
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row.get("updated_at"),
                "params": manifest.get("params") or {},
                "metrics": manifest.get("metrics") or {},
                "thresholds": manifest.get("thresholds") or {},
                "data": manifest.get("data") or {},
                "version": int(manifest.get("version") or 1),
                "updated_at": manifest.get("updated_at") or row.get("updated_at"),
                "history": manifest.get("history") or [],
                "feature_count": len(manifest.get("feature_names") or []),
                "notes": manifest.get("notes") or "",
            }
        )
    return items


def set_status(model_id: str, status: str) -> Dict[str, Any]:
    if status not in {"candidate", "active", "archived"}:
        raise ValueError("Geçersiz durum")
    manifest = load_manifest(model_id)
    if not manifest:
        raise ValueError("Model bulunamadı")
    manifest["status"] = status
    folder = model_dir(model_id)
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    db.execute(
        "UPDATE ai_models SET status=?, manifest_json=?, updated_at=? WHERE id=?",
        (status, json.dumps(manifest, ensure_ascii=False, default=str), _now(), model_id),
    )
    return manifest


def delete_model(model_id: str) -> Dict[str, Any]:
    manifest = load_manifest(model_id)
    if not manifest:
        raise ValueError("Model bulunamadı")
    folder = model_dir(model_id)
    if folder.exists():
        shutil.rmtree(folder)
    db.execute("DELETE FROM ai_models WHERE id=?", (model_id,))
    return {"ok": True, "id": model_id}


def bulk_delete(statuses: Optional[List[str]] = None) -> Dict[str, Any]:
    """Aday ve/veya arşiv modellerini toplu siler.

    ``active`` modeller asla silinmez; yanlış çağrıda ana modeli kaybetmemek
    için durum listesi ``candidate`` ve ``archived`` ile sınırlanır.
    """
    allowed = {"candidate", "archived"}
    wanted = {str(s) for s in (statuses or sorted(allowed)) if str(s) in allowed}
    if not wanted:
        raise ValueError("Silinecek durum seçilmedi (candidate / archived)")
    deleted: List[str] = []
    failed: List[Dict[str, str]] = []
    for item in list_models(include_archived=True):
        if item.get("status") not in wanted:
            continue
        try:
            delete_model(item["id"])
            deleted.append(item["id"])
        except Exception as exc:  # noqa: BLE001 - tek model hatası toplu silmeyi durdurmaz
            failed.append({"id": item["id"], "error": str(exc)[:200]})
    return {
        "ok": True,
        "deleted": len(deleted),
        "ids": deleted,
        "failed": failed,
        "statuses": sorted(wanted),
    }


def write_report(model_id: str, report: Dict[str, Any]) -> None:
    folder = model_dir(model_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def read_report(model_id: str) -> Optional[Dict[str, Any]]:
    path = model_dir(model_id) / "report.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# Canlı işlem deneyimleri ("işlemlerden öğrenme")
# ---------------------------------------------------------------------------
def record_experience(payload: Dict[str, Any]) -> None:
    """Kapanan AI işlemini deneyim tablosuna yazar.

    Hata botu durdurmamalıdır; bu yüzden çağıran taraf try/except kullanır.
    """
    db.execute(
        "INSERT INTO ai_experiences(model_id,bot_id,coin,period,side,features_json,"
        "entry_price,exit_price,pnl_pct,candles,reason,mode,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            payload.get("model_id"),
            payload.get("bot_id"),
            payload.get("coin"),
            payload.get("period"),
            payload.get("side") or "BUY",
            json.dumps(payload.get("features") or {}, ensure_ascii=False, default=str),
            payload.get("entry_price"),
            payload.get("exit_price"),
            payload.get("pnl_pct"),
            payload.get("candles"),
            payload.get("reason"),
            payload.get("mode"),
            _now(),
        ),
    )


def list_experiences(model_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    if model_id:
        rows = db.rows(
            "SELECT * FROM ai_experiences WHERE model_id=? ORDER BY created_at DESC LIMIT ?",
            (model_id, limit),
        )
    else:
        rows = db.rows("SELECT * FROM ai_experiences ORDER BY created_at DESC LIMIT ?", (limit,))
    for row in rows:
        try:
            row["features"] = json.loads(row.pop("features_json") or "{}")
        except ValueError:
            row["features"] = {}
    return rows


def experience_count(model_id: Optional[str] = None) -> int:
    if model_id:
        row = db.row("SELECT COUNT(*) AS c FROM ai_experiences WHERE model_id=?", (model_id,))
    else:
        row = db.row("SELECT COUNT(*) AS c FROM ai_experiences")
    return int((row or {}).get("c") or 0)
