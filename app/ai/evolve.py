"""Nesiller boyu eğitim (evolve).

Kullanıcı "her eğittiğimde biraz daha iyi olsun" dediğinde tek bir eğitim
yeterli olmaz. Bu modül, önceki modelden **sıcak başlangıç** alarak art arda
nesiller üretir:

1. 1. nesil mevcut şampiyondan (yoksa sıfırdan) başlar.
2. Her nesil yalnızca eğitim kümesinde eğitilir, eşiği validation'da seçilir.
3. Neslin skoru **validation** ile ölçülür; test bu aşamada hiç kullanılmaz.
4. Skor iyileşmezse erken durulur (sabır).
5. En iyi nesil seçilir ve **test yalnızca bir kez** onun için çalıştırılır.
6. Kalite kapısı ve şampiyon karşılaştırması sonucu terfi kararı verilir.

Böylece her tur bir öncekinin bilgisini taşır; kabul edilen model asla
gerilemez.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app import db
from app.ai.autopilot import (
    PRESETS,
    _active_champion,
    _record_run,
    _score,
    evaluate_gate,
    load_settings,
)
from app.ai.trainer import train_model


def _val_score(report: Dict[str, Any], min_trades: int) -> float:
    ref = report.get("refinement") or {}
    if ref.get("best_score") is not None:
        return float(ref["best_score"])
    from app.ai.trainer import _validation_score

    trading = ((report.get("validation") or {}).get("trading") or {})
    return _validation_score(trading, min_trades)


def evolve(params: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_settings()
    preset_name = str(params.get("preset") or cfg.get("preset") or "balanced")
    preset = PRESETS.get(preset_name, PRESETS["balanced"])
    generations = max(2, min(int(params.get("generations") or 3), 8))
    patience = max(1, min(int(params.get("evolve_patience") or 1), 3))
    min_delta = max(0.0, float(params.get("min_delta") or 0.02))
    min_trades = int(params.get("min_trades") or preset.get("min_trades") or 10)
    coin = str(params.get("coin") or cfg.get("coin") or "BTCUSDT").upper()
    period = str(params.get("period") or cfg.get("period") or "1h")

    champion = _active_champion(coin, period)
    parent_id = str(params.get("parent_model_id") or (champion or {}).get("id") or "") or None
    base_params = {k: v for k, v in params.items() if k not in {"generations", "evolve_patience", "_job_id"}}
    base_params.update({"coin": coin, "period": period, "min_trades": min_trades, "warm_start": True})

    history: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    final_result: Optional[Dict[str, Any]] = None
    no_improve = 0
    run_parent = parent_id

    for generation in range(1, generations + 1):
        # İlerleyen nesillerde eğitim bütçesi biraz artırılır; sıcak başlangıç
        # zaten iyi bir noktadan başladığı için model daha ince ayrıntı öğrenir.
        gen_spec = dict(base_params.get("spec") or {})
        try:
            base_epochs = int(gen_spec.get("epochs") or 120)
        except (TypeError, ValueError):
            base_epochs = 120
        gen_spec["epochs"] = int(min(base_epochs * (1 + 0.25 * (generation - 1)), base_epochs * 2))
        gen_params = {**base_params, "spec": gen_spec}

        # Ara nesillerde test değerlendirilmez (test sızıntısı olmasın).
        result = train_model(
            {
                **gen_params,
                "parent_model_id": run_parent,
                "generation": generation,
                "skip_test": generation < generations,
            }
        )
        report = result["report"]
        model_id = result["model"]["id"]
        score = _val_score(report, min_trades)
        lineage = report.get("lineage") or {}
        entry = {
            "generation": generation,
            "model_id": model_id,
            "parent_id": run_parent,
            "warm_start_used": bool(lineage.get("warm_start_used")),
            "warm_start_note": lineage.get("warm_start_note"),
            "epochs": gen_spec.get("epochs"),
            "score": round(score, 4),
            "validation": (report.get("validation") or {}).get("trading") or {},
            "test": (report.get("test") or {}).get("trading") if not report.get("skip_test") else None,
            "improved": bool(best is None or score > float(best["score"]) + min_delta),
        }
        history.append(entry)

        if best is None or score > float(best["score"]) + min_delta:
            best = entry
            no_improve = 0
        else:
            no_improve += 1
        # Sıcak başlangıç her zaman en son nesilden devam eder; en iyi nesil
        # seçimi ayrıca yapılır.
        run_parent = model_id
        if no_improve >= patience:
            break

    if best is None:
        raise RuntimeError("Hiçbir nesil eğitilemedi")

    # En iyi nesil zaten son nesil değilse testi onun için bir kez çalıştır.
    # Bu, seçimi değiştirmez; yalnızca nihai denetim (audit) içindir.
    selection_score = float(best["score"])
    if best["generation"] < generations and best.get("test") is None:
        parent_of_best = best["model_id"]
        final = train_model(
            {
                **base_params,
                "parent_model_id": parent_of_best,
                "generation": best["generation"],
                "skip_test": False,
                "name": f"{coin} {period} nesil-{best['generation']}",
            }
        )
        report = final["report"]
        model_id = final["model"]["id"]
        best = {
            **best,
            "model_id": model_id,
            "selection_score": selection_score,
            "final_score": _val_score(report, min_trades),
            "validation": (report.get("validation") or {}).get("trading") or {},
            "test": (report.get("test") or {}).get("trading") or {},
        }
        history.append(
            {
                "generation": best["generation"],
                "model_id": model_id,
                "parent_id": parent_of_best,
                "warm_start_used": bool((report.get("lineage") or {}).get("warm_start_used")),
                "score": best["final_score"],
                "selection_score": selection_score,
                "validation": best["validation"],
                "test": best["test"],
                "final_audit": True,
                "improved": True,
            }
        )
        final_result = final
    else:
        final_result = None

    # Eğer son nesil en iyiyse onun raporu elimizde; testi eksikse çalıştır.
    if best.get("test") is None:
        final = train_model(
            {
                **base_params,
                "parent_model_id": best["model_id"],
                "generation": best["generation"],
                "skip_test": False,
            }
        )
        report = final["report"]
        best["model_id"] = final["model"]["id"]
        best["test"] = (report.get("test") or {}).get("trading") or {}
        best["selection_score"] = selection_score
        best["final_score"] = _val_score(report, min_trades)
        final_result = final
    else:
        report = (final_result or {}).get("report") or {}

    if not report:
        try:
            from app.ai import artifacts

            report = artifacts.read_report(best["model_id"]) or {}
        except Exception:
            report = {}

    gate = evaluate_gate(report, preset)
    champion_score = _score(champion.get("metrics") or {}) if champion else None
    decision = "candidate"
    reason = ""
    if not gate["passed"]:
        decision = "rejected"
        reason = "; ".join(gate["reasons"])
    elif champion and gate["score"] < champion_score + 0.5:
        decision = "kept"
        reason = (
            f"Mevcut model daha iyi/eşit: şampiyon {champion_score:+.2f} "
            f"vs en iyi nesil {gate['score']:+.2f}"
        )
    else:
        decision = "promoted"
        reason = (
            f"En iyi nesil terfi etti: {gate['score']:+.2f}"
            + (f" > şampiyon {champion_score:+.2f}" if champion else " (ilk model)")
        )

    from app.ai import artifacts

    if decision == "promoted":
        if champion:
            artifacts.set_status(champion["id"], "candidate")
        artifacts.set_status(best["model_id"], "active")
    elif decision == "rejected":
        # Reddedilen nesil diske bırakılmaz; arşiv listesi şişmesin.
        try:
            artifacts.delete_model(best["model_id"])
        except Exception:
            pass

    summary = {
        "decision": decision,
        "reason": reason,
        "generations_requested": generations,
        "generations_run": len({h["generation"] for h in history}),
        "best_generation": best["generation"],
        "best_model_id": best["model_id"],
        "best_score": round(selection_score, 4),
        "final_score": round(float(best.get("final_score") or selection_score), 4),
        "champion_id": (champion or {}).get("id"),
        "champion_score": champion_score,
        "history": history,
        "gate": gate,
    }
    try:
        artifacts.write_report(best["model_id"], {**report, "evolve": summary})
    except Exception:
        pass
    _record_run(
        best["model_id"],
        decision,
        reason,
        {
            "generations": len(history),
            "best_generation": best["generation"],
            "champion_id": (champion or {}).get("id"),
            "history": [
                {"generation": h["generation"], "score": h["score"], "improved": h.get("improved")}
                for h in history
            ],
        },
    )
    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "model_id": best["model_id"],
        "best_generation": best["generation"],
        "best_score": round(selection_score, 4),
        "final_score": round(float(best.get("final_score") or selection_score), 4),
        "history": history,
        "gate": gate,
        "report": report,
    }
