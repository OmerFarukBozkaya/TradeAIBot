from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import db
from app.config import BASE_DIR, LOG_DIR, settings

# Dashboard'da gösterilen okunur iş adları
JOB_LABELS = {
    "scan": "Tarama",
    "backtest": "Backtest",
    "backtest_all": "Strateji karşılaştırma",
    "indicator_values": "İndikatör değerleri",
    "strategy_values": "Strateji değerleri",
    "support_resistance": "Destek / direnç",
    "market": "Piyasa analizi",
    "monthly": "Aylık sonuç",
    "coinlist": "Coin listesi",
    "buy_result": "Alım sonucu",
    "dataset": "Veri seti",
    "strategy_results": "Strateji sonuçları",
    "strategy_analyze_save": "Strateji analizi",
    "ai_train": "AI eğitimi",
    "snapshot_record": "Snapshot kaydı",
    "snapshot_verify": "Snapshot doğrulama",
}

ACTIVE_STATUSES = ("queued", "running")


def job_label(job_type: str) -> str:
    return JOB_LABELS.get(job_type, job_type)


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return os.name == "nt"  # Windows'ta os.kill(pid, 0) güvenilir değil


def _reap_stale() -> int:
    """Çökmüş / takılı kalmış işleri temizler.

    Alt süreç açılamazsa iş sonsuza kadar 'queued' kalıp eşzamanlılık
    limitini kilitliyordu. Bu fonksiyon onları hata olarak işaretler.
    """
    now = datetime.now(timezone.utc)
    reaped = 0
    for item in db.rows("SELECT * FROM jobs WHERE status IN ('queued','running')"):
        stamp = item.get("started_at") or item.get("created_at")
        age = 0.0
        if stamp:
            try:
                began = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if began.tzinfo is None:
                    began = began.replace(tzinfo=timezone.utc)
                age = (now - began).total_seconds()
            except (ValueError, TypeError):
                age = 0.0
        stale = False
        if item["status"] == "queued" and age > 90:
            stale = True
        elif item["status"] == "running":
            if age > 3600:
                stale = True
            elif item.get("pid") and not _pid_alive(item["pid"]):
                stale = True
        if stale:
            db.execute(
                "UPDATE jobs SET status='error', message=?, error=?, finished_at=? WHERE id=?",
                (
                    "İş yanıt vermedi (zaman aşımı)",
                    "İş süreci başlamadı veya yanıt vermedi. Lütfen tekrar deneyin.",
                    db.utcnow(),
                    item["id"],
                ),
            )
            reaped += 1
    return reaped


def create_job(job_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    _reap_stale()
    job_id = uuid.uuid4().hex[:12]
    db.execute(
        "INSERT INTO jobs(id,type,params_json,status,progress,message,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            job_id,
            job_type,
            json.dumps(params, ensure_ascii=False),
            "queued",
            0,
            "Sırada bekliyor",
            db.utcnow(),
        ),
    )
    running = db.row("SELECT COUNT(*) AS c FROM jobs WHERE status IN ('queued','running')")
    # Basit eşzamanlılık sınırı
    if running and int(running["c"]) > settings.MAX_JOBS:
        db.execute(
            "UPDATE jobs SET status='error', error=?, message=?, finished_at=? WHERE id=?",
            (
                f"Eşzamanlı iş limiti aşıldı ({settings.MAX_JOBS}). Biraz bekleyip tekrar deneyin.",
                "İş kuyruğu dolu",
                db.utcnow(),
                job_id,
            ),
        )
        return get_job(job_id)  # type: ignore

    log_path = LOG_DIR / "jobs" / f"{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # AI işleri ayrı profil container'ındaki ai_worker tarafından alınır.
    if job_type.startswith("ai_"):
        return get_job(job_id)  # type: ignore
    handle = open(log_path, "a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "app.job_runner", "--job-id", job_id],
        cwd=str(BASE_DIR),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=(os.name != "nt"),
    )
    db.execute("UPDATE jobs SET pid=? WHERE id=?", (process.pid, job_id))
    return get_job(job_id)  # type: ignore


def _parse(item: Dict[str, Any]) -> Dict[str, Any]:
    item["params"] = json.loads(item.pop("params_json") or "{}")
    item["result"] = json.loads(item["result_json"]) if item.get("result_json") else None
    item.pop("result_json", None)
    return item


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    item = db.row("SELECT * FROM jobs WHERE id=?", (job_id,))
    return _parse(item) if item else None


def list_jobs(job_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    if job_type:
        items = db.rows(
            "SELECT * FROM jobs WHERE type=? ORDER BY created_at DESC LIMIT ?", (job_type, limit)
        )
    else:
        items = db.rows("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_parse(item) for item in items]


# ---------------------------------------------------------------------------
# Dashboard: aktif işler
# ---------------------------------------------------------------------------
def _elapsed_seconds(started: Optional[str], created: Optional[str]) -> int:
    stamp = started or created
    if not stamp:
        return 0
    try:
        began = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if began.tzinfo is None:
            began = began.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - began).total_seconds()))
    except (ValueError, TypeError):
        return 0


def _summary_params(job_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if params.get("period"):
        summary["period"] = params["period"]
    coins = params.get("coins") or []
    if not coins and params.get("list_id"):
        from app.coin_lists import list_coins

        coins = list_coins(params["list_id"]) or []
    if coins:
        summary["coins"] = len(coins)
        summary["coin_preview"] = ", ".join(str(c) for c in coins[:3])
    if params.get("coin"):
        summary["coin"] = params["coin"]
    strategies = params.get("strategies") or []
    if strategies:
        summary["strategies"] = len(strategies)
    if job_type == "scan":
        summary["scope"] = "Tüm coin listesi" if not coins else f"{len(coins)} coin"
    if job_type == "backtest_all":
        summary["scope"] = "Tüm stratejiler"
    return summary


def active_jobs(recent_seconds: int = 120, limit: int = 8) -> Dict[str, Any]:
    """Devam eden işler + kısa süre önce bitenler (dashboard kartı için)."""
    _reap_stale()
    active = [_parse(r) for r in db.rows(
        "SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created_at ASC LIMIT ?",
        (limit,),
    )]
    recent = [_parse(r) for r in db.rows(
        "SELECT * FROM jobs WHERE status NOT IN ('queued','running') "
        "ORDER BY COALESCE(finished_at, created_at) DESC LIMIT 6"
    )]

    def build(item: Dict[str, Any], running: bool) -> Dict[str, Any]:
        params = item.get("params") or {}
        return {
            "id": item["id"],
            "type": item["type"],
            "label": job_label(item["type"]),
            "status": item["status"],
            "progress": int(item.get("progress") or 0),
            "message": item.get("message") or "",
            "period": params.get("period"),
            "summary": _summary_params(item["type"], params),
            "created_at": item["created_at"],
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "elapsed": _elapsed_seconds(item.get("started_at"), item["created_at"]),
            "error": (item.get("error") or "").split("\n")[0][:200] or None,
        }

    return {
        "active": [build(i, True) for i in active],
        "recent": [build(i, False) for i in recent],
        "limit": settings.MAX_JOBS,
    }


# ---------------------------------------------------------------------------
# Dashboard: tarama sonuçları
# ---------------------------------------------------------------------------
def _strategy_names(params: Dict[str, Any]) -> Dict[str, str]:
    """Sonuç anahtarlarını (builtin adı / custom id) okunur isme çevirir."""
    from app.strategies.service import get_custom

    mapping: Dict[str, str] = {}
    for spec in params.get("strategies") or []:
        if isinstance(spec, str):
            mapping[spec] = spec
            continue
        kind = spec.get("type") or spec.get("kind")
        if kind == "builtin" or not kind:
            name = spec.get("name") or spec.get("id") or ""
            mapping[str(name)] = str(name)
        else:
            sid = str(spec.get("id") or "")
            name = sid
            try:
                item = get_custom(sid)
                if item:
                    name = item["name"]
            except Exception:
                pass
            mapping[sid] = name
    return mapping


def scan_results(limit: int = 5) -> List[Dict[str, Any]]:
    """Biten taramaların sonuçlarını dashboard için özetler."""
    rows = db.rows(
        "SELECT * FROM jobs WHERE type='scan' AND status IN ('done','error') "
        "ORDER BY COALESCE(finished_at, created_at) DESC LIMIT ?",
        (max(1, min(20, limit)),),
    )
    items: List[Dict[str, Any]] = []
    for raw in rows:
        item = _parse(raw)
        params = item.get("params") or {}
        result = item.get("result") or {}
        names = _strategy_names(params)
        raw_results = result.get("results") or {}

        strategies = []
        signals = []
        buy_total = sell_total = 0
        for key, sides in raw_results.items():
            name = names.get(key, key)
            buys = [str(c) for c in (sides.get("BUY") or [])]
            sells = [str(c) for c in (sides.get("SELL") or [])]
            buy_total += len(buys)
            sell_total += len(sells)
            strategies.append(
                {
                    "id": key,
                    "name": name,
                    "buy": buys[:60],
                    "sell": sells[:60],
                    "buy_count": len(buys),
                    "sell_count": len(sells),
                }
            )
            for coin in buys:
                signals.append({"coin": coin, "side": "BUY", "strategy": name})
            for coin in sells:
                signals.append({"coin": coin, "side": "SELL", "strategy": name})

        unique_buy = sorted({s["coin"] for s in signals if s["side"] == "BUY"})
        unique_sell = sorted({s["coin"] for s in signals if s["side"] == "SELL"})

        # Coin merkezli detay: her coin için hangi stratejiler AL/SAT verdi.
        coin_map: Dict[str, Dict[str, Any]] = {}
        for key, sides in raw_results.items():
            name = names.get(key, key)
            for side in ("BUY", "SELL"):
                for coin in (sides.get(side) or []):
                    coin = str(coin)
                    entry = coin_map.setdefault(
                        coin,
                        {"coin": coin, "buy": [], "sell": [], "buy_count": 0, "sell_count": 0},
                    )
                    if name not in entry[side.lower()]:
                        entry[side.lower()].append(name)
                    if side == "BUY":
                        entry["buy_count"] += 1
                    else:
                        entry["sell_count"] += 1
        coins = sorted(
            coin_map.values(),
            key=lambda c: (-(c["buy_count"] + c["sell_count"]), c["coin"]),
        )

        items.append(
            {
                "id": item["id"],
                "status": item["status"],
                "period": params.get("period", ""),
                "scanned": result.get("scanned", 0),
                "created_at": item["created_at"],
                "finished_at": item.get("finished_at"),
                "error": (item.get("error") or "").split("\n")[0][:200] or None,
                "errors": (result.get("errors") or [])[:5],
                "strategies": strategies,
                "signals": signals[:400],
                "coins": coins,
                "buy_total": buy_total,
                "sell_total": sell_total,
                "buy_coins": unique_buy,
                "sell_coins": unique_sell,
            }
        )
    return items


def cancel_job(job_id: str) -> Dict[str, Any]:
    item = db.row("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not item:
        raise LookupError("İş bulunamadı")
    if item["status"] not in ACTIVE_STATUSES:
        raise ValueError("Bu iş zaten bitmiş")
    db.execute(
        "UPDATE jobs SET status='cancelled', message=?, finished_at=? WHERE id=?",
        ("Kullanıcı iptal etti", db.utcnow(), job_id),
    )
    pid = item.get("pid")
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            else:
                os.kill(int(pid), 15)
        except Exception:
            pass
    db.log_event(None, f"İş iptal edildi: {job_label(item['type'])}", "warning")
    return {"ok": True, "id": job_id}
