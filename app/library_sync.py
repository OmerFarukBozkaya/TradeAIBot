"""Strateji ve coin listelerini Git dostu JSON dosyalarına aktarır.

Veritabanının tamamını yedeklemek yerine yalnızca **kullanıcı stratejileri**
ve **coin listeleri** dışa/içe aktarılır. Dosyalar ``library/`` altında
tutulur ve doğrudan repoya commit edilebilir.

Tasarım:
  * Dosya adı ``<isim>--<kimlik>.json``; kimlik korunur, böylece botların
    strateji referansları içe aktarmadan sonra da çalışır.
  * Dışa aktarma sırasında aynı kimliğin eski dosyaları silinir (isim
    değişince mükerrer dosya kalmaz).
  * İçe aktarma önce **plan** üretir; ``--apply`` verilmeden hiçbir şey
    yazılmaz. Aynı tanım tekrar içe aktarılırsa sürüm artmaz (idempotent).
  * Hazır (builtin) stratejiler kodda tanımlıdır; hazır coin listeleri de
    kodda olduğu için varsayılan olarak dışa aktarılmaz.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app import coin_lists, db
from app.strategies import service
from app.strategies.compiler import validate_definition

SCHEMA = 1
_TR_MAP = str.maketrans(
    "çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu"
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "kayit", max_len: int = 60) -> str:
    """Dosya adı için güvenli, okunabilir anahtar üretir."""
    clean = (text or "").translate(_TR_MAP).lower()
    clean = _SLUG_RE.sub("-", clean).strip("-")
    if not clean:
        clean = fallback
    return clean[:max_len].strip("-") or fallback


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=False
    )


def _strategy_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "strategy",
        "schema": SCHEMA,
        "id": item["id"],
        "name": item["name"],
        "version": item.get("version"),
        "status": item.get("status") or "active",
        "definition": item["definition"],
    }


def _coinlist_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "coinlist",
        "schema": SCHEMA,
        "id": item["id"],
        "name": item["name"],
        "coins": list(item["coins"]),
    }


def export_library(
    directory: str | Path,
    *,
    include_archived: bool = True,
    include_builtin_lists: bool = False,
    prune: bool = False,
) -> Dict[str, Any]:
    """Stratejileri ve coin listelerini ``directory`` altına yazar."""
    root = Path(directory)
    strat_dir = root / "strategies"
    list_dir = root / "coinlists"
    strat_dir.mkdir(parents=True, exist_ok=True)
    list_dir.mkdir(parents=True, exist_ok=True)

    written: set[Path] = set()

    strategies = service.list_custom(include_archived=include_archived)
    for item in strategies:
        payload = _strategy_payload(item)
        path = strat_dir / f"{slugify(item['name'])}--{item['id']}.json"
        # İsim değişmişse eski dosyayı bırakma.
        for old in strat_dir.glob(f"*--{item['id']}.json"):
            if old != path:
                old.unlink()
        _write_json(path, payload)
        written.add(path)

    lists = coin_lists.list_lists()
    for item in lists:
        if item.get("builtin") and not include_builtin_lists:
            continue
        payload = _coinlist_payload(item)
        path = list_dir / f"{slugify(item['name'])}--{item['id']}.json"
        for old in list_dir.glob(f"*--{item['id']}.json"):
            if old != path:
                old.unlink()
        _write_json(path, payload)
        written.add(path)

    removed = 0
    if prune:
        for folder in (strat_dir, list_dir):
            for path in folder.glob("*.json"):
                if path not in written:
                    path.unlink()
                    removed += 1

    return {
        "directory": str(root),
        "strategies": len(strategies),
        "coinlists": len(written) - len(strategies),
        "removed": removed,
    }


# ---------------------------------------------------------------------------
# İçe aktarma
# ---------------------------------------------------------------------------
def _iter_payloads(
    folder: Path, kind: str
) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            yield path, {"_error": f"okunamadı: {exc}"}
            continue
        if not isinstance(data, dict):
            yield path, {"_error": "JSON nesnesi değil"}
            continue
        if data.get("kind") != kind:
            yield path, {"_error": f"tür uyuşmuyor (beklenen: {kind})"}
            continue
        yield path, data


def _unique_name(name: str, *, strategy: bool) -> str:
    """Hazır kayıtla çakışınca kullanılacak boş bir ad üretir."""
    candidate = f"{name} (içe aktarma)"
    index = 2
    while True:
        if strategy:
            taken = db.row(
                "SELECT id FROM strategies WHERE lower(name)=lower(?)", (candidate,)
            )
        else:
            taken = db.row(
                "SELECT id FROM coin_lists WHERE lower(name)=lower(?)", (candidate,)
            )
        if not taken:
            return candidate
        candidate = f"{name} (içe aktarma {index})"
        index += 1


def _plan_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("_error"):
        raise ValueError(payload["_error"])
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        raise ValueError("definition eksik veya nesne değil")
    sid = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or definition.get("name") or sid).strip()
    if not name:
        raise ValueError("strateji adı yok")
    definition = dict(definition)
    definition["name"] = name
    errors = validate_definition(definition)
    if errors:
        raise ValueError("; ".join(errors))

    current = service.get_custom(sid) if sid else None
    target_id = sid
    if current:
        action = "skip" if _same(definition, current["definition"]) else "update"
        matched = "id"
    else:
        by_name = db.row(
            "SELECT id FROM strategies WHERE lower(name)=lower(?)", (name,)
        )
        if by_name:
            target_id = by_name["id"]
            current = service.get_custom(target_id)
            action = (
                "skip"
                if current and _same(definition, current["definition"])
                else "update"
            )
            matched = "isim"
        else:
            free = sid and not db.row("SELECT id FROM strategies WHERE id=?", (sid,))
            target_id = sid if free else None
            action = "create"
            matched = "-"

    return {
        "kind": "strategy",
        "file": payload.get("_file"),
        "id": target_id,
        "name": name,
        "version": payload.get("version"),
        "action": action,
        "matched": matched,
        "definition": definition,
    }


def _plan_coinlist(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("_error"):
        raise ValueError(payload["_error"])
    lid = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("liste adı yok")
    coins = coin_lists.normalize_coins(payload.get("coins") or [])
    if not coins:
        raise ValueError("liste boş")

    current = coin_lists.get_list(lid) if lid else None
    target_id = lid
    if current:
        if current.get("builtin"):
            # Hazır liste değiştirilemez: kullanıcı kopyası oluştur.
            name = _unique_name(name, strategy=False)
            target_id = None
            action = "create"
            matched = "hazır-liste"
        elif current["name"] == name and current["coins"] == coins:
            action = "skip"
            matched = "id"
        else:
            action = "update"
            matched = "id"
    else:
        by_name = db.row(
            "SELECT * FROM coin_lists WHERE lower(name)=lower(?)", (name,)
        )
        if by_name:
            existing = coin_lists.get_list(by_name["id"])
            if existing and existing.get("builtin"):
                name = _unique_name(name, strategy=False)
                target_id = None
                action = "create"
                matched = "hazır-liste"
            elif existing and existing["coins"] == coins:
                target_id = existing["id"]
                action = "skip"
                matched = "isim"
            else:
                target_id = existing["id"] if existing else None
                action = "update"
                matched = "isim"
        else:
            free = lid and not db.row("SELECT id FROM coin_lists WHERE id=?", (lid,))
            target_id = lid if free else None
            action = "create"
            matched = "-"

    return {
        "kind": "coinlist",
        "file": payload.get("_file"),
        "id": target_id,
        "name": name,
        "coins": coins,
        "action": action,
        "matched": matched,
    }


def _apply_strategy(entry: Dict[str, Any]) -> Dict[str, Any]:
    if entry["action"] == "create":
        item = service.create_custom(entry["definition"], strategy_id=entry["id"])
    else:
        item = service.update_custom(entry["id"], entry["definition"])
    entry["id"] = item["id"]
    return {"id": item["id"], "name": item["name"], "version": item["version"]}


def _apply_coinlist(entry: Dict[str, Any]) -> Dict[str, Any]:
    if entry["action"] == "create":
        item = coin_lists.create_list(
            entry["name"], entry["coins"], list_id=entry["id"]
        )
    else:
        item = coin_lists.update_list(entry["id"], entry["name"], entry["coins"])
    entry["id"] = item["id"]
    return {"id": item["id"], "name": item["name"], "coins": len(item["coins"])}


def import_library(
    directory: str | Path,
    *,
    apply: bool = False,
    only_missing: bool = False,
) -> Dict[str, Any]:
    """``library/`` altındaki dosyaları veritabanına uygular (idempotent).

    ``only_missing=True`` ise yalnızca **olmayan** kayıtlar eklenir; var olan
    bir strateji/liste dosyayla farklı olsa bile **güncellenmez**. Uygulama
    açılışında kullanılan güvenli mod budur: kullanıcının panelden yaptığı
    düzenlemeleri sessizce geri almaz.
    """
    root = Path(directory)
    report: Dict[str, Any] = {
        "directory": str(root),
        "apply": bool(apply),
        "only_missing": bool(only_missing),
        "strategies": [],
        "coinlists": [],
        "errors": [],
    }

    for path, payload in _iter_payloads(root / "strategies", "strategy"):
        payload["_file"] = path.name
        try:
            entry = _plan_strategy(payload)
            if only_missing and entry["action"] == "update":
                entry["action"] = "skip"
            if apply and entry["action"] in {"create", "update"}:
                entry["result"] = _apply_strategy(entry)
        except Exception as exc:  # noqa: BLE001 - dosya bazında raporlanır
            report["errors"].append({"file": path.name, "error": str(exc)})
            continue
        report["strategies"].append(entry)

    for path, payload in _iter_payloads(root / "coinlists", "coinlist"):
        payload["_file"] = path.name
        try:
            entry = _plan_coinlist(payload)
            if only_missing and entry["action"] == "update":
                entry["action"] = "skip"
            if apply and entry["action"] in {"create", "update"}:
                entry["result"] = _apply_coinlist(entry)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"file": path.name, "error": str(exc)})
            continue
        report["coinlists"].append(entry)

    return report


def summarize(report: Dict[str, Any]) -> List[str]:
    """İnsan okunur rapor satırları (CLI ve log için)."""
    lines: List[str] = []
    labels = {"create": "ekle", "update": "güncelle", "skip": "değişmedi"}
    for kind, key in (("Strateji", "strategies"), ("Coin listesi", "coinlists")):
        for entry in report.get(key) or []:
            label = labels.get(entry["action"], entry["action"])
            detail = (
                f"v{entry['result']['version']}"
                if entry.get("result") and "version" in entry["result"]
                else ""
            )
            match = entry.get("matched")
            extra = f" [{match} eşleşti]" if match not in (None, "-", "id") else ""
            lines.append(
                f"  {label:9} {kind}: {entry['name']}{extra} {detail}".rstrip()
            )
    for err in report.get("errors") or []:
        lines.append(f"  HATA      {err['file']}: {err['error']}")
    return lines
