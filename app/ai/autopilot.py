"""Otomatik (sürekli) AI eğitimi ve şampiyon/yarışmacı yönetimi.

Kullanıcı tek bir anahtar açar: bot periyodik olarak kendi kendini eğitir.
Amaç, ayar kalabalığı olmadan "iyi alım/satım" öğrenmek ve hatalardan ders
almaktır. Aşırı öğrenmeye karşı korumalar burada uygulanır:

- Walk-forward katları ve test sonucu birlikte değerlendirilir.
- Eğitim (in-sample) getirisi test getirisinden aşırı yüksekse model reddedilir.
- Yeterli işlem yoksa, test getirisi/al-tut farkı (edge) negatifse reddedilir.
- Mevcut aktif modelden belirgin biçimde iyi değilse terfi ettirilmez.
- Kapanan işlem deneyimleri yalnızca sınırlı oranda eğitime katılır.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app import db
from app.ai.features import GROUPS
from app.ai.spec import normalize_spec, validate_spec

SETTINGS_KEY = "ai_autopilot"
MAX_FAILURES_BACKOFF = 6

PRESETS: Dict[str, Dict[str, Any]] = {
    "cautious": {
        "label": "Temkinli",
        "desc": "Az ama yüksek olasılıklı işlem. Daha uzun ufuk, yüksek eşik.",
        "horizon": 24,
        "target_move": 0.015,
        "stop_move": 0.01,
        "min_precision": 0.50,
        "walk_forward": True,
        "folds": 4,
        "feedback_weight": 0.30,
        "limit": 30000,
        "min_trades": 12,
        "max_overfit_ratio": 0.30,
        "min_positive_fold_ratio": 0.60,
        "iterations": 5,
        "patience": 2,
    },
    "balanced": {
        "label": "Dengeli",
        "desc": "Orta sıklıkta işlem. Önerilen başlangıç.",
        "horizon": 12,
        "target_move": 0.01,
        "stop_move": 0.01,
        "min_precision": 0.40,
        "walk_forward": True,
        "folds": 3,
        "feedback_weight": 0.50,
        "limit": 25000,
        "min_trades": 10,
        "max_overfit_ratio": 0.25,
        "min_positive_fold_ratio": 0.50,
        "iterations": 6,
        "patience": 2,
    },
    "aggressive": {
        "label": "Agresif",
        "desc": "Sık işlem, kısa ufuk. Daha fazla sinyal, daha fazla gürültü.",
        "horizon": 6,
        "target_move": 0.006,
        "stop_move": 0.012,
        "min_precision": 0.32,
        "walk_forward": True,
        "folds": 3,
        "feedback_weight": 0.70,
        "limit": 20000,
        "min_trades": 8,
        "max_overfit_ratio": 0.20,
        "min_positive_fold_ratio": 0.40,
        "iterations": 4,
        "patience": 2,
    },
}

DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "coin": "BTCUSDT",
    "period": "1h",
    "preset": "balanced",
    "interval_hours": 24,
    "limit": 25000,
    "dataset_id": "",
    "auto_snapshot": True,
    "spec": None,
    "last_run_at": None,
    "last_model_id": None,
    "last_status": None,
    "last_reason": None,
    "consecutive_failures": 0,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def load_settings() -> Dict[str, Any]:
    raw = db.get_setting(SETTINGS_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = {**DEFAULTS, **raw}
    preset = str(merged.get("preset") or "balanced")
    if preset not in PRESETS:
        merged["preset"] = "balanced"
    return merged


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    current = load_settings()
    allowed = {
        "enabled", "coin", "period", "preset", "interval_hours", "limit", "spec",
        "dataset_id", "auto_snapshot",
    }
    for key in allowed:
        if key not in values:
            continue
        value = values[key]
        if key == "dataset_id":
            text = str(value or "").strip()
            if text:
                from app.ai import datasets

                meta = datasets.manifest(text)
                if not meta:
                    raise ValueError("Veri seti bulunamadı")
                current["dataset_id"] = text
                current["coin"] = str(meta.get("coin") or current.get("coin"))
                current["period"] = str(meta.get("period") or current.get("period"))
            else:
                current["dataset_id"] = ""
            continue
        if key == "auto_snapshot":
            current["auto_snapshot"] = bool(value)
            continue
        if key == "spec":
            # Sessizce varsayılana düşmek yerine açık hata ver: kullanıcı
            # yanlış grup seçtiğini görsün.
            if isinstance(value, dict):
                raw_groups = value.get("feature_groups")
                if raw_groups is not None:
                    if not raw_groups:
                        raise ValueError("En az bir özellik grubu seçilmeli")
                    unknown = [str(g) for g in raw_groups if str(g) not in GROUPS]
                    if unknown:
                        raise ValueError(f"Bilinmeyen özellik grubu: {', '.join(unknown)}")
            spec = normalize_spec(value)
            errors = validate_spec(spec)
            if errors:
                raise ValueError("; ".join(errors))
            current["spec"] = spec
            continue
        if key == "enabled":
            current[key] = bool(value)
        elif key == "interval_hours":
            try:
                current[key] = max(1, min(int(value), 24 * 30))
            except (TypeError, ValueError):
                pass
        elif key == "limit":
            try:
                current[key] = max(2000, min(int(value), 250_000))
            except (TypeError, ValueError):
                pass
        elif key == "period":
            from app.market_data.periods import parse_period

            try:
                current[key] = parse_period(str(value or "1h")).text
            except ValueError:
                current[key] = "1h"
        elif key == "preset":
            text = str(value or "balanced")
            current[key] = text if text in PRESETS else "balanced"
        elif key == "coin":
            text = str(value or "BTCUSDT").strip().upper()
            current[key] = text or "BTCUSDT"
    db.set_setting(SETTINGS_KEY, current)
    return current


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment
    except (TypeError, ValueError):
        return None


def next_run_at(cfg: Optional[Dict[str, Any]] = None) -> Optional[datetime]:
    cfg = cfg or load_settings()
    if not cfg.get("enabled"):
        return None
    last = _parse_iso(cfg.get("last_run_at"))
    if last is None:
        return _now()
    hours = float(cfg.get("interval_hours") or 24)
    failures = int(cfg.get("consecutive_failures") or 0)
    if failures:
        # Başarısız denemelerde üstel geri çekilme; en fazla ayarlanan aralık.
        hours = min(hours, 0.5 * (2 ** min(failures, MAX_FAILURES_BACKOFF)))
    return last + timedelta(hours=hours)


def _score(metrics: Dict[str, Any]) -> float:
    """Modeli tek sayıya indirger: test edge + walk-forward edge."""
    test = metrics.get("test") or {}
    wf = metrics.get("walk_forward") or {}
    test_edge = float(test.get("edge_pct") or 0.0)
    wf_edge = float(wf.get("avg_edge_pct") or 0.0) if wf.get("folds") else test_edge
    return round(0.6 * test_edge + 0.4 * wf_edge, 2)


def _active_champion(coin: str, period: str) -> Optional[Dict[str, Any]]:
    for model in _models():
        params = model.get("params") or {}
        if model.get("status") != "active":
            continue
        if str(params.get("coin") or "").upper() != coin.upper():
            continue
        if str(params.get("period") or "") != period:
            continue
        return model
    return None


def _models() -> List[Dict[str, Any]]:
    from app.ai import artifacts

    try:
        return artifacts.list_models(include_archived=False)
    except Exception:
        return []


def evaluate_gate(report: Dict[str, Any], preset_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Eğitim raporunu aşırı öğrenme ve kalite kapısından geçirir."""
    test = (report.get("test") or {}).get("trading") or {}
    train = (report.get("train") or {}).get("trading") or {}
    wf = report.get("walk_forward") or []
    folds = [f for f in wf if isinstance(f, dict) and f.get("trading")]

    reasons: List[str] = []
    warnings: List[str] = []

    trades = int(test.get("trade_count") or 0)
    edge = float(test.get("edge_pct") or 0.0)
    ret = float(test.get("total_return_pct") or 0.0)
    min_trades = int(preset_cfg.get("min_trades") or 10)

    if trades < min_trades:
        reasons.append(f"Test işlem sayısı yetersiz ({trades} < {min_trades})")
    if edge <= 0:
        reasons.append(f"Test edge negatif ({edge:+.2f}%)")
    if ret <= 0:
        reasons.append(f"Test getirisi negatif ({ret:+.2f}%)")

    # Aşırı öğrenme: örnek içi getiri teste göre aşırı iyimser.
    train_ret = float(train.get("total_return_pct") or 0.0)
    max_ratio = float(preset_cfg.get("max_overfit_ratio") or 0.25)
    overfit_ratio = None
    if train_ret > 0 and ret > 0:
        overfit_ratio = ret / train_ret
        if overfit_ratio < max_ratio:
            reasons.append(
                f"Aşırı öğrenme şüphesi: test getirisi eğitimin yalnızca "
                f"%{overfit_ratio * 100:.0f}'i"
            )

    # Walk-forward: modelin zaman içinde tutarlı olması.
    positive = sum(1 for f in folds if float((f.get("trading") or {}).get("total_return_pct") or 0) > 0)
    ratio = (positive / len(folds)) if folds else 0.0
    min_ratio = float(preset_cfg.get("min_positive_fold_ratio") or 0.5)
    wf_edge = None
    if folds:
        wf_edge = sum(float((f.get("trading") or {}).get("edge_pct") or 0) for f in folds) / len(folds)
        if ratio < min_ratio:
            reasons.append(
                f"Walk-forward tutarsız: {positive}/{len(folds)} kat pozitif "
                f"(en az %{min_ratio * 100:.0f} gerekli)"
            )
        if wf_edge <= 0:
            reasons.append(f"Walk-forward edge negatif ({wf_edge:+.2f}%)")
    else:
        warnings.append("Walk-forward raporu yok; tek test sonucuna güveniliyor")

    # Aşırı işlem/komisyon erozyonu uyarısı
    if trades > 2000:
        warnings.append("Çok yüksek işlem sayısı; komisyon etkisini kontrol edin")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "score": _score({"test": test, "walk_forward": report.get("walk_forward_summary") or {}}),
        "metrics": {
            "test": test,
            "train": train,
            "trades": trades,
            "edge_pct": edge,
            "overfit_ratio": None if overfit_ratio is None else round(overfit_ratio, 3),
            "wf_positive_ratio": round(ratio, 3) if folds else None,
            "wf_edge_pct": None if wf_edge is None else round(wf_edge, 2),
        },
    }


def build_params(cfg: Dict[str, Any], trigger: str = "auto") -> Dict[str, Any]:
    preset_name = str(cfg.get("preset") or "balanced")
    preset = PRESETS[preset_name]
    coin = str(cfg.get("coin") or "BTCUSDT").upper()
    period = str(cfg.get("period") or "1h")
    limit = int(cfg.get("limit") or preset["limit"])
    return {
        "name": f"{coin} {period} oto-{preset_name}",
        "coin": coin,
        "period": period,
        "limit": limit,
        "source": "binance",
        "label_kind": "forward",
        "horizon": preset["horizon"],
        "target_move": preset["target_move"],
        "stop_move": preset["stop_move"],
        "min_precision": preset["min_precision"],
        "walk_forward": preset["walk_forward"],
        "folds": preset["folds"],
        "use_feedback": True,
        "feedback_weight": preset["feedback_weight"],
        "fee": 0.001,
        "slippage": 0.0005,
        "refine": True,
        "iterations": preset.get("iterations", 5),
        "patience": preset.get("patience", 2),
        "min_trades": preset.get("min_trades", 10),
        "spec": normalize_spec(cfg.get("spec")),
        "dataset_id": str(cfg.get("dataset_id") or ""),
        "auto_snapshot": bool(cfg.get("auto_snapshot", True)),
        "refresh_data": bool(cfg.get("refresh_data", False)),
        "notes": f"Otomatik öğrenme ({preset['label']}) · tetik: {trigger}",
        "_preset": preset_name,
        "_trigger": trigger,
    }


def run_once(trigger: str = "manual") -> Dict[str, Any]:
    """Tek bir otomatik eğitim döngüsü: eğit, değerlendir, gerekirse terfi ettir.

    Bu fonksiyon iş sürecinde çalışır (job_runner). Hata durumunda ayarlar
    korunur; sonraki zamanlanmış deneme tekrar dener.
    """
    from app.ai import artifacts
    from app.ai.trainer import train_model

    cfg = load_settings()
    params = build_params(cfg, trigger)
    preset_name = params.pop("_preset")
    params.pop("_trigger", None)
    preset = PRESETS[preset_name]

    # Her zamanlanmış tur, mevcut şampiyonun bilgisinden başlar. Böylece
    # tekrar tekrar eğitim sıfırdan başlamaz, birikimli ilerler.
    champion = _active_champion(params["coin"], params["period"])
    if champion:
        params["parent_model_id"] = champion["id"]
        params["warm_start"] = True

    try:
        result = train_model(params)
    except Exception as exc:
        cfg["last_run_at"] = _iso(_now())
        cfg["last_status"] = "error"
        cfg["last_reason"] = str(exc)[:400]
        cfg["consecutive_failures"] = int(cfg.get("consecutive_failures") or 0) + 1
        db.set_setting(SETTINGS_KEY, cfg)
        _record_run(None, "error", str(exc), {})
        raise

    manifest = result["model"]
    report = result["report"]
    model_id = manifest["id"]
    gate = evaluate_gate(report, preset)

    champion_score = None
    decision = "candidate"
    reason = ""

    if not gate["passed"]:
        decision = "rejected"
        reason = "; ".join(gate["reasons"])
    else:
        challenger_score = gate["score"]
        if champion:
            champion_score = _score(champion.get("metrics") or {})
            # Terfi için belirgin üstünlük isteriz; gürültüyle yer değiştirmesin.
            if challenger_score < champion_score + 0.5:
                decision = "kept"
                reason = (
                    f"Mevcut model daha iyi/eşit: şampiyon {champion_score:+.2f} "
                    f"vs yeni {challenger_score:+.2f}"
                )
            else:
                decision = "promoted"
                reason = (
                    f"Yeni model üstün: {challenger_score:+.2f} > "
                    f"{champion_score:+.2f} (+0.5 eşik)"
                )
        else:
            decision = "promoted"
            reason = "Bu coin/periyot için aktif model yok; ilk model aktifleştirildi"

    if decision == "promoted":
        if champion:
            artifacts.set_status(champion["id"], "candidate")
        artifacts.set_status(model_id, "active")
    else:
        # "rejected" veya "kept": yeni model diske bırakılmaz, liste şişmesin.
        # Rapor ai_last_auto ayarında ve günlükte kalır.
        try:
            artifacts.delete_model(model_id)
        except Exception:
            pass

    cfg["last_run_at"] = _iso(_now())
    cfg["last_model_id"] = model_id
    cfg["last_status"] = decision
    cfg["last_reason"] = reason
    cfg["consecutive_failures"] = 0
    db.set_setting(SETTINGS_KEY, cfg)

    summary = {
        "decision": decision,
        "reason": reason,
        "gate": gate,
        "champion_id": (champion or {}).get("id"),
        "champion_score": champion_score,
        "preset": preset_name,
        "coin": params["coin"],
        "period": params["period"],
    }
    artifacts.write_report(model_id, {**report, "autopilot": summary})
    _record_run(model_id, decision, reason, {
        "gate": gate,
        "champion_id": (champion or {}).get("id"),
        "champion_score": champion_score,
    })
    return {"ok": True, "model_id": model_id, "decision": decision, "reason": reason, "gate": gate, "report": report}


def _record_run(model_id: Optional[str], status: str, reason: str, metrics: Dict[str, Any]) -> None:
    try:
        db.execute(
            "INSERT INTO ai_training_runs(model_id,status,reason,metrics_json,created_at) VALUES(?,?,?,?,?)",
            (
                model_id,
                status,
                (reason or "")[:600],
                db.json.dumps(metrics, ensure_ascii=False, default=str),
                db.utcnow(),
            ),
        )
    except Exception:
        pass


def history(limit: int = 20) -> List[Dict[str, Any]]:
    rows = db.rows(
        "SELECT * FROM ai_training_runs ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)
    )
    for row in rows:
        try:
            row["metrics"] = db.json.loads(row.pop("metrics_json") or "{}")
        except Exception:
            row["metrics"] = {}
    return rows


# ---------------------------------------------------------------------------
# Zamanlayıcı (web süreci tek örnek)
# ---------------------------------------------------------------------------
class AutoPilot:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopping = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True

    def _loop(self) -> None:
        # Açılışta acele etmemek için kısa bekleme.
        time.sleep(20)
        while not self._stopping:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - zamanlayıcı durmamalı
                db.log_event(None, f"AI otomatik öğrenme hatası: {exc}", "warning")
            time.sleep(120)

    def tick(self) -> None:
        from app.config import settings

        if not settings.AI_ENABLED:
            return
        cfg = load_settings()
        if not cfg.get("enabled"):
            return
        due = next_run_at(cfg)
        if due is None or _now() < due:
            return
        # Aynı anda ikinci bir AI işi başlatma.
        active = db.row(
            "SELECT COUNT(*) AS c FROM jobs WHERE status IN ('starting','queued','running') "
            "AND type LIKE 'ai_%'"
        )
        if active and int(active["c"] or 0) > 0:
            return
        from app.jobs import create_job

        create_job("ai_auto", {"trigger": "schedule"})


autopilot = AutoPilot()
