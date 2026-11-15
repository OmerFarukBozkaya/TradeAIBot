"""Regresyon testi (snapshot) sistemi.

Belirli bir coin/periyot için **fiyat geçmişini**, o veriden üretilen
**indikatör değerlerini** ve **strateji sinyallerini** diske kaydeder. Daha
sonra kodda bir değişiklik yapıldığında aynı fiyatlar kullanılarak çıktılar
yeniden üretilir ve kayıtla **birebir** karşılaştırılır. Fark varsa hangi
indikatörün/stratejinin hangi mumda saptığı raporlanır.

Tasarım notları:
  * Fiyatlar ve indikatör değerleri JSON'a yazılır (float'lar Python'un
    round-trip gösterimiyle saklanır; kayıp yok). Dosya gzip'lenir.
  * Strateji sinyalleri mum başına "0"/"1" dizisi olarak tutulur: küçük,
    okunur ve ilk farkın **mum indeksini** doğrudan verir.
  * Karşılaştırma toleransı `DEFAULT_TOL` (1e-12). Bu, float ilişkilendirme
    farklarını yok sayar ama gerçek formül hatasını yakalar.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app import job_runner as jr
from app.paths import paths
from app.strategies.builtin import builtin_names
from app.strategies.compiler import CompiledStrategy
from app.strategies.registry import INDICATORS, IndicatorCache
from app.strategies.service import get_custom, list_custom, normalize_specs

SNAPSHOT_DIR = paths.base / "Data" / "snapshots"
DEFAULT_TOL = 1e-12
SUPPORTED_PERIODS = ("15m", "1h", "4h", "1d")
MAX_CANDLES = 50000


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOT_DIR


def _path(snapshot_id: str):
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id:
        raise ValueError("Geçersiz snapshot kimliği")
    return _dir() / f"{snapshot_id}.json.gz"


def _dump(path, payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wb", compresslevel=6) as fh:
        fh.write(raw)
    tmp.replace(path)


def _load(path) -> Dict[str, Any]:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _versions() -> Dict[str, str]:
    out = {"python": platform.python_version()}
    try:
        import numpy

        out["numpy"] = numpy.__version__
    except Exception:
        out["numpy"] = "?"
    try:
        import pandas

        out["pandas"] = pandas.__version__
    except Exception:
        out["pandas"] = "?"
    return out


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
def _default_outputs() -> Iterable[tuple]:
    """Her indikatör için varsayılan parametrelerle hesaplanacak çıktılar."""
    for key, spec in INDICATORS.items():
        defaults = {p["name"]: p["default"] for p in spec["params"]}
        for output in spec["outputs"]:
            yield key, defaults, output


def _indicator_key(name: str, params: Dict[str, Any], output: str) -> str:
    parts = ",".join(f"{k}={params[k]}" for k in sorted(params))
    first = INDICATORS[name]["outputs"][0]
    suffix = "" if output == first else f".{output}"
    return f"{name}({parts}){suffix}"


def _strategy_specs() -> List[Dict[str, Any]]:
    """Kaydedilecek stratejiler: tüm özel (arşiv dahil) + hazır motorlar."""
    specs: List[Dict[str, Any]] = []
    for item in list_custom(include_archived=True):
        specs.append(
            {
                "key": f"custom:{item['id']}:v{item['version']}",
                "name": item["name"],
                "kind": "custom",
                "spec": {"type": "custom", "id": item["id"], "version": item["version"]},
            }
        )
    for name in builtin_names(include_ai=False):
        specs.append(
            {
                "key": f"builtin:{name}",
                "name": name,
                "kind": "builtin",
                "spec": {"type": "builtin", "name": name},
            }
        )
    return specs


def _signals(evaluator, data: Dict[str, Any], start: int) -> Dict[str, str]:
    """Sinyalleri mum başına '0'/'1' dizisine çevirir."""
    n = len(data["close"])
    cache = IndicatorCache(data) if isinstance(evaluator, CompiledStrategy) else None
    buy = ["0"] * n
    sell = ["0"] * n
    for idx in range(max(0, start), n - 1):
        if isinstance(evaluator, CompiledStrategy):
            result = evaluator.evaluate_at(data, cache, idx, detail=False)
        else:
            result = evaluator.evaluate_at(data, idx)
        if not result.get("warmup_ok", True):
            continue
        if result.get("buy"):
            buy[idx] = "1"
        if result.get("sell"):
            sell[idx] = "1"
    return {"buy": "".join(buy), "sell": "".join(sell)}


def record(
    coin: str = "BTCUSDT",
    period: str = "15m",
    candles: int = 20000,
    note: str = "",
    progress=None,
) -> Dict[str, Any]:
    """Snapshot oluşturur ve meta bilgisini döndürür."""
    coin = (coin or "BTCUSDT").strip().upper()
    period = (period or "15m").strip()
    if period not in SUPPORTED_PERIODS:
        raise ValueError(f"Desteklenmeyen periyot: {period}")
    candles = max(200, min(int(candles), MAX_CANDLES))

    def report(pct: int, message: str = "") -> None:
        if progress:
            progress(pct, message)

    report(5, f"{coin} {period} · {candles} mum veri çekiliyor")
    client = jr._client()
    data, history_meta = jr._history(client, coin, period, candles)
    n = len(data["close"])
    if n < 200:
        raise ValueError(f"Yeterli mum alınamadı ({n})")

    cache = IndicatorCache(data)
    indicators: Dict[str, List[Any]] = {}
    indicator_errors: List[Dict[str, str]] = []
    outputs = list(_default_outputs())
    for i, (name, params, output) in enumerate(outputs, start=1):
        try:
            indicators[_indicator_key(name, params, output)] = cache.compute(name, params, output)
        except Exception as exc:  # noqa: BLE001
            indicator_errors.append({"indicator": name, "error": str(exc)[:120]})
        if i % 5 == 0 or i == len(outputs):
            report(20 + int(i / max(1, len(outputs)) * 45), f"indikatörler {i}/{len(outputs)}")

    strategies: Dict[str, Any] = {}
    strategy_errors: List[Dict[str, str]] = []
    specs = _strategy_specs()
    for i, item in enumerate(specs, start=1):
        try:
            evaluator = jr.build_evaluator(item["spec"])
            if hasattr(evaluator, "prepare"):
                evaluator.prepare(data)
            sig = _signals(evaluator, data, int(getattr(evaluator, "warmup", 60)))
            strategies[item["key"]] = {
                "name": item["name"],
                "kind": item["kind"],
                "warmup": int(getattr(evaluator, "warmup", 0)),
                "buy": sig["buy"],
                "sell": sig["sell"],
                "buy_count": sig["buy"].count("1"),
                "sell_count": sig["sell"].count("1"),
            }
        except Exception as exc:  # noqa: BLE001
            strategy_errors.append({"strategy": item["key"], "error": str(exc)[:120]})
        report(65 + int(i / max(1, len(specs)) * 30), f"stratejiler {i}/{len(specs)}")

    snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    price_payload = {
        key: data[key] for key in ("open", "high", "low", "close", "volume_coin", "volume_usdt", "opendate")
    }
    meta = {
        "id": snapshot_id,
        "coin": coin,
        "period": period,
        "candles": n,
        "requested": candles,
        "note": note[:200],
        "created_at": _now(),
        "versions": _versions(),
        "price_sha256": _sha(price_payload),
        "indicator_count": len(indicators),
        "strategy_count": len(strategies),
        "indicator_errors": indicator_errors,
        "strategy_errors": strategy_errors,
        "history": {
            k: v for k, v in (history_meta or {}).items() if k in ("requested", "raw_rows", "pages")
        },
    }
    payload = {"meta": meta, "data": price_payload, "indicators": indicators, "strategies": strategies}
    path = _path(snapshot_id)
    _dump(path, payload)

    info = dict(meta)
    info["size_mb"] = round(path.stat().st_size / 1048576, 2)
    return info


# ---------------------------------------------------------------------------
# Listeleme / silme
# ---------------------------------------------------------------------------
def list_snapshots() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for path in sorted(_dir().glob("snap_*.json.gz"), reverse=True):
        try:
            payload = _load(path)
            meta = dict(payload.get("meta") or {})
        except Exception:  # bozuk dosya: yine de göster
            meta = {"id": path.stem.replace(".json", ""), "error": "okunamadı"}
        meta["size_mb"] = round(path.stat().st_size / 1048576, 2)
        items.append(meta)
    return items


def get_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    path = _path(snapshot_id)
    if not path.exists():
        return None
    return _load(path)


def delete_snapshot(snapshot_id: str) -> bool:
    path = _path(snapshot_id)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def _compare_series(expected: List[Any], actual: List[Any], tol: float) -> Dict[str, Any]:
    if len(expected) != len(actual):
        return {
            "diffs": abs(len(expected) - len(actual)),
            "first_index": min(len(expected), len(actual)),
            "expected": f"uzunluk {len(expected)}",
            "actual": f"uzunluk {len(actual)}",
        }
    diffs = 0
    first = None
    exp_v = act_v = None
    for i, (e, a) in enumerate(zip(expected, actual)):
        if e is None and a is None:
            continue
        if e is None or a is None:
            diffs += 1
            if first is None:
                first, exp_v, act_v = i, e, a
            continue
        try:
            if abs(float(e) - float(a)) > tol:
                diffs += 1
                if first is None:
                    first, exp_v, act_v = i, e, a
        except (TypeError, ValueError):
            if e != a:
                diffs += 1
                if first is None:
                    first, exp_v, act_v = i, e, a
    return {"diffs": diffs, "first_index": first, "expected": exp_v, "actual": act_v}


def _compare_signals(expected: str, actual: str) -> Dict[str, Any]:
    if len(expected) != len(actual):
        return {
            "diffs": abs(len(expected) - len(actual)),
            "first_index": min(len(expected), len(actual)),
            "expected": f"uzunluk {len(expected)}",
            "actual": f"uzunluk {len(actual)}",
        }
    diffs = 0
    first = None
    for i, (e, a) in enumerate(zip(expected, actual)):
        if e != a:
            diffs += 1
            if first is None:
                first = i
    return {"diffs": diffs, "first_index": first, "expected": None, "actual": None}


def verify(snapshot_id: str, tol: float = DEFAULT_TOL, progress=None) -> Dict[str, Any]:
    """Snapshot'ı mevcut kodla yeniden üretip karşılaştırır."""
    payload = get_snapshot(snapshot_id)
    if not payload:
        raise LookupError("Snapshot bulunamadı")

    def report(pct: int, message: str = "") -> None:
        if progress:
            progress(pct, message)

    report(5, "snapshot okunuyor")
    meta = payload.get("meta") or {}
    data = payload.get("data") or {}
    if not data.get("close"):
        raise ValueError("Snapshot fiyat verisi eksik")

    n = len(data["close"])
    failures: List[Dict[str, Any]] = []
    checked_indicators = 0
    checked_strategies = 0

    # 1) Fiyat verisi bozulmamış mı?
    price_sha = _sha({k: data.get(k) for k in (
        "open", "high", "low", "close", "volume_coin", "volume_usdt", "opendate")})
    if meta.get("price_sha256") and price_sha != meta["price_sha256"]:
        failures.append({
            "type": "data",
            "name": "fiyat geçmişi",
            "message": "Snapshot dosyasındaki fiyat verisi kayıt anındakiyle aynı değil",
            "diffs": None,
        })

    cache = IndicatorCache(data)
    version_warnings: List[str] = []
    now_versions = _versions()
    for key, old in now_versions.items():
        saved = (meta.get("versions") or {}).get(key)
        if saved and saved != old and saved != "?":
            version_warnings.append(f"{key}: kayıt {saved} → şimdi {old}")

    # 2) İndikatörler
    outputs = list(_default_outputs())
    for i, (name, params, output) in enumerate(outputs, start=1):
        key = _indicator_key(name, params, output)
        expected = (payload.get("indicators") or {}).get(key)
        if expected is None:
            continue
        checked_indicators += 1
        try:
            actual = cache.compute(name, params, output)
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "type": "indicator", "name": key, "message": f"hesaplanamadı: {exc}"[:200],
                "diffs": None,
            })
            continue
        diff = _compare_series(expected, actual, tol)
        if diff["diffs"]:
            failures.append({"type": "indicator", "name": key, **diff})
        if i % 5 == 0:
            report(10 + int(i / max(1, len(outputs)) * 50), f"indikatörler {i}/{len(outputs)}")

    # 3) Stratejiler
    saved_strategies = payload.get("strategies") or {}
    total_strategies = max(1, len(saved_strategies))
    for i, (key, saved) in enumerate(saved_strategies.items(), start=1):
        checked_strategies += 1
        kind, _, rest = key.partition(":")
        try:
            if kind == "custom":
                sid, _, ver = rest.rpartition(":v")
                evaluator = jr.build_evaluator(
                    {"type": "custom", "id": sid, "version": int(ver)}
                )
            else:
                evaluator = jr.build_evaluator({"type": "builtin", "name": rest})
            if hasattr(evaluator, "prepare"):
                evaluator.prepare(data)
            sig = _signals(evaluator, data, int(saved.get("warmup") or getattr(evaluator, "warmup", 60)))
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "type": "strategy", "name": saved.get("name") or key,
                "message": f"hesaplanamadı: {exc}"[:200], "diffs": None,
            })
            continue
        for side in ("buy", "sell"):
            if saved.get(side) is None:
                continue
            diff = _compare_signals(saved.get(side) or "", sig[side])
            if diff["diffs"]:
                failures.append({
                    "type": "strategy",
                    "name": saved.get("name") or key,
                    "key": key,
                    "side": "AL" if side == "buy" else "SAT",
                    **diff,
                })
        report(60 + int(i / total_strategies * 38), f"stratejiler {i}/{total_strategies}")

    by_type: Dict[str, int] = {}
    for item in failures:
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1

    return {
        "snapshot": {
            "id": meta.get("id"),
            "coin": meta.get("coin"),
            "period": meta.get("period"),
            "candles": n,
            "created_at": meta.get("created_at"),
        },
        "ok": not failures,
        "tolerance": tol,
        "checked": {"indicators": checked_indicators, "strategies": checked_strategies},
        "failure_count": len(failures),
        "by_type": by_type,
        "failures": failures[:50],
        "truncated": len(failures) > 50,
        "version_warnings": version_warnings,
        "checked_at": _now(),
    }
