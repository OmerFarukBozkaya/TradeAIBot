from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from app import db
from app.strategies.builtin import BuiltinStrategy, builtin_names
from app.strategies.compiler import (
    StrategyValidationError,
    compile_strategy,
    validate_definition,
)
from app.strategies.registry import catalog


def _timeframe_meta() -> Dict[str, Dict[str, Any]]:
    """Ölçülmüş 'en iyi zaman dilimi' bilgisi (settings tablosunda saklanır)."""
    raw = db.get_setting("strategy_timeframes", {}) or {}
    return raw if isinstance(raw, dict) else {}


def attach_timeframes(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Her öğeye `best_timeframe`, `timeframe_edge`, `timeframe_note` ve
    `timeframe_periods` alanlarını ekler."""
    meta = _timeframe_meta()
    for item in items:
        info = meta.get(item.get("id")) or {}
        periods = info.get("periods") or {}
        best = info.get("best")
        reliable = info.get("reliable", True)
        item["best_timeframe"] = best if reliable else None
        item["timeframe_edge"] = info.get("edge") if reliable else None
        item["timeframe_reliable"] = bool(reliable)
        item["timeframe_periods"] = {
            p: {
                "return_pct": m.get("ret"),
                "buy_hold_pct": m.get("bh"),
                "diff": m.get("ex"),
                "drawdown_pct": m.get("dd"),
                "trades": m.get("trades"),
            }
            for p, m in periods.items()
            if m
        }
    return items


def list_custom(include_archived: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM strategies"
    if not include_archived:
        sql += " WHERE status != 'archived'"
    sql += " ORDER BY updated_at DESC"
    items = db.rows(sql)
    for item in items:
        item["definition"] = json.loads(item.pop("definition_json"))
    return attach_timeframes(items)


def get_custom(strategy_id: str) -> Optional[Dict[str, Any]]:
    item = db.row("SELECT * FROM strategies WHERE id=?", (strategy_id,))
    if not item:
        return None
    item["definition"] = json.loads(item.pop("definition_json"))
    return attach_timeframes([item])[0]


def get_version(strategy_id: str, version: int) -> Optional[Dict[str, Any]]:
    item = db.row(
        "SELECT * FROM strategy_versions WHERE strategy_id=? AND version=?",
        (strategy_id, version),
    )
    return json.loads(item["definition_json"]) if item else None


def create_custom(definition: Dict[str, Any], strategy_id: Optional[str] = None) -> Dict[str, Any]:
    errors = validate_definition(definition)
    if errors:
        raise StrategyValidationError("; ".join(errors))
    strategy_id = strategy_id or f"custom_{uuid.uuid4().hex[:10]}"
    if db.row("SELECT id FROM strategies WHERE id=?", (strategy_id,)):
        raise StrategyValidationError("Bu kimlikle bir strateji zaten var")
    now = db.utcnow()
    payload = json.dumps(definition, ensure_ascii=False)
    db.execute(
        "INSERT INTO strategies(id,name,definition_json,version,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (strategy_id, definition.get("name", strategy_id), payload, 1, "active", now, now),
    )
    db.execute(
        "INSERT INTO strategy_versions(strategy_id,version,definition_json,created_at) VALUES(?,?,?,?)",
        (strategy_id, 1, payload, now),
    )
    return get_custom(strategy_id)  # type: ignore


def update_custom(strategy_id: str, definition: Dict[str, Any]) -> Dict[str, Any]:
    current = get_custom(strategy_id)
    if not current:
        raise StrategyValidationError("Strateji bulunamadı")
    errors = validate_definition(definition)
    if errors:
        raise StrategyValidationError("; ".join(errors))
    new_version = int(current["version"]) + 1
    now = db.utcnow()
    payload = json.dumps(definition, ensure_ascii=False)
    db.execute(
        "UPDATE strategies SET name=?, definition_json=?, version=?, updated_at=? WHERE id=?",
        (definition.get("name", strategy_id), payload, new_version, now, strategy_id),
    )
    db.execute(
        "INSERT INTO strategy_versions(strategy_id,version,definition_json,created_at) VALUES(?,?,?,?)",
        (strategy_id, new_version, payload, now),
    )
    return get_custom(strategy_id)  # type: ignore


def duplicate_custom(strategy_id: str) -> Dict[str, Any]:
    item = get_custom(strategy_id)
    if not item:
        raise StrategyValidationError("Strateji bulunamadı")
    definition = dict(item["definition"])
    definition["name"] = f"{definition.get('name')} (kopya)"
    return create_custom(definition)


def bots_using(strategy_id: str) -> List[Dict[str, Any]]:
    """Bu stratejiyi kullanan botları döndürür (bot.config_json içindeki referans)."""
    used: List[Dict[str, Any]] = []
    for bot in db.rows("SELECT id,name,status,config_json FROM bots"):
        try:
            config = json.loads(bot.get("config_json") or "{}")
        except (TypeError, ValueError):
            continue
        for spec in config.get("strategies") or []:
            if isinstance(spec, dict) and spec.get("type") == "custom" and spec.get("id") == strategy_id:
                used.append({"id": bot["id"], "name": bot["name"], "status": bot["status"]})
                break
    return used


def delete_custom(strategy_id: str, force: bool = False) -> Dict[str, Any]:
    """Kullanıcı stratejisini kalıcı olarak siler.

    Stratejiyi kullanan bot varsa ve `force` değilse hata verir; böylece
    çalışan bir botun referansı sessizce bozulmaz. `force=True` ile bot
    referanslarına rağmen silinir (bot başlatılırken strateji bulunamaz).
    """
    item = get_custom(strategy_id)
    if not item:
        raise StrategyValidationError("Strateji bulunamadı")

    used = bots_using(strategy_id)
    if used and not force:
        names = ", ".join(b["name"] for b in used[:5])
        more = "" if len(used) <= 5 else f" ve {len(used) - 5} bot daha"
        raise StrategyValidationError(
            f"Bu strateji {len(used)} bot tarafından kullanılıyor: {names}{more}. "
            "Önce o botları silin veya stratejiyi zorla silin."
        )

    db.execute("DELETE FROM strategy_versions WHERE strategy_id=?", (strategy_id,))
    db.execute("DELETE FROM strategy_backtests WHERE strategy_id=?", (strategy_id,))
    db.execute("DELETE FROM strategies WHERE id=?", (strategy_id,))
    return {"ok": True, "id": strategy_id, "bots": used}


def set_status(strategy_id: str, status: str) -> None:
    if status not in {"active", "draft", "archived"}:
        raise StrategyValidationError("Geçersiz durum")
    db.execute(
        "UPDATE strategies SET status=?, updated_at=? WHERE id=?",
        (status, db.utcnow(), strategy_id),
    )


# ---------------------------------------------------------------------------
# Hazır (kod tabanlı) stratejiler: görünen ad ve arşiv durumu
# ---------------------------------------------------------------------------
def _builtin_meta() -> Dict[str, Dict[str, Any]]:
    raw = db.get_setting("builtin_strategy_meta", {}) or {}
    return raw if isinstance(raw, dict) else {}


def _save_builtin_meta(meta: Dict[str, Dict[str, Any]]) -> None:
    db.set_setting("builtin_strategy_meta", meta)


def list_builtin(include_archived: bool = False) -> List[Dict[str, Any]]:
    from app.config import settings

    meta = _builtin_meta()
    items: List[Dict[str, Any]] = []
    for name in builtin_names(include_ai=settings.AI_ENABLED):
        info = meta.get(name) or {}
        archived = bool(info.get("archived"))
        if archived and not include_archived:
            continue
        items.append(
            {
                "id": name,
                "name": name,
                "label": info.get("label") or name,
                "archived": archived,
                "kind": "builtin",
                "status": "archived" if archived else "active",
            }
        )
    return attach_timeframes(items)


def rename_builtin(name: str, label: str) -> Dict[str, Any]:
    from app.config import settings

    if name not in builtin_names(include_ai=settings.AI_ENABLED):
        raise StrategyValidationError("Hazır strateji bulunamadı")
    clean = (label or "").strip()[:80]
    meta = _builtin_meta()
    entry = dict(meta.get(name) or {})
    entry["label"] = clean or name
    meta[name] = entry
    _save_builtin_meta(meta)
    return {"ok": True, "name": name, "label": entry["label"]}


def set_builtin_archived(name: str, archived: bool) -> Dict[str, Any]:
    from app.config import settings

    if name not in builtin_names(include_ai=settings.AI_ENABLED):
        raise StrategyValidationError("Hazır strateji bulunamadı")
    meta = _builtin_meta()
    entry = dict(meta.get(name) or {})
    entry["archived"] = bool(archived)
    meta[name] = entry
    _save_builtin_meta(meta)
    return {"ok": True, "name": name, "archived": bool(archived)}


def duplicate_builtin(name: str) -> Dict[str, Any]:
    """Hazır stratejiyi düzenlenebilir bir kayıt olarak kopyalar.

    Kopya, hazır motoru referans alır; böylece kullanıcı listesinde görünür,
    arşivlenebilir ve backtest edilebilir.
    """
    from app.config import settings

    if name not in builtin_names(include_ai=settings.AI_ENABLED):
        raise StrategyValidationError("Hazır strateji bulunamadı")
    meta = _builtin_meta()
    label = (meta.get(name) or {}).get("label") or name
    definition = {
        "name": f"{label} (kopya)",
        "builtin": name,
    }
    return create_custom(definition)


def catalog_payload() -> Dict[str, Any]:
    custom = list_custom()
    from app.config import settings

    return {
        "indicators": catalog(),
        "builtin": [
            {"id": name, "name": name, "kind": "builtin"}
            for name in builtin_names(include_ai=settings.AI_ENABLED)
        ],
        "custom": [
            {
                "id": item["id"],
                "name": item["name"],
                "version": item["version"],
                "status": item["status"],
                "definition": item["definition"],
                "kind": "custom",
            }
            for item in custom
        ],
    }


def build_evaluator(spec: Dict[str, Any]):
    """Bot konfigürasyonundaki strateji referansını çalıştırılabilir motora çevirir."""
    if isinstance(spec, str):
        return BuiltinStrategy(spec)
    kind = spec.get("type") or spec.get("kind")
    if kind == "builtin":
        return BuiltinStrategy(spec["name"])
    if kind == "custom":
        version = spec.get("version")
        item = get_custom(spec["id"])
        if not item:
            raise ValueError(f"Strateji bulunamadı: {spec['id']}")
        definition = item["definition"]
        # Hazır motordan türetilmiş kopya
        if isinstance(definition, dict) and definition.get("builtin"):
            return BuiltinStrategy(definition["builtin"])
        if version and int(version) != int(item["version"]):
            definition = get_version(spec["id"], int(version))
            if not definition:
                raise ValueError(f"Strateji sürümü bulunamadı: {spec['id']} v{version}")
            return compile_strategy(definition, spec["id"], int(version))
        return compile_strategy(item["definition"], item["id"], int(item["version"]))
    raise ValueError(f"Geçersiz strateji referansı: {spec}")


def normalize_specs(raw: Any) -> List[Dict[str, Any]]:
    """Eski string listesi ve yeni nesne listesini tek forma indirger."""
    result: List[Dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            result.append({"type": "builtin", "name": item})
        elif isinstance(item, dict):
            if item.get("type") or item.get("kind"):
                result.append(item)
            elif item.get("name"):
                result.append({"type": "builtin", "name": item["name"]})
    return result
