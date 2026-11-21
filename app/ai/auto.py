"""Tek düğme ile otomatik model eğitimi.

Kullanıcı yalnızca "eğit" der. Bu modül sırayla:

1. Fiyat verisini hazırlar (sabit veri seti varsa ağa çıkmaz).
2. Mevcut şampiyonu yükler (varsa ondan sıcak başlangıç yapar).
3. Küçük bir mimari/hiperparametre ızgarasını **validation** ile dener.
4. En iyi adayı, tam iyileştirme turuyla yeniden eğitir.
5. **Testi yalnızca kazanan için bir kez** çalıştırır.
6. Şampiyondan daha iyiyse terfi ettirir; değilse şampiyonu korur.

Hiçbir aday "reddedildi" diye kullanıcıya hata dönmez: ya yeni model
aktifleşir ya da mevcut model korunur (`decision = kept`).

Tüm ayarlar tek bir profil kaydında (`ai_profile`) tutulur; kullanıcı isterse
yalnızca 1-2 alanı değiştirir, gerisini sistem yönetir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app import db
from app.ai import artifacts
from app.ai.autopilot import PRESETS, _active_champion, _score
from app.ai.spec import normalize_spec, validate_spec
from app.ai.trainer import train_model

PROFILE_KEY = "ai_profile"
# Profil şema sürümü: eski kayıtlarda hedef "local_min_max" idi. Yeni kâr
# odaklı hataya geçişte bir kez taşınır; kullanıcı sonra elle değiştirebilir.
PROFILE_VERSION = 2

DEFAULTS: Dict[str, Any] = {
    # Veri
    "coin": "BTCUSDT",
    "period": "1h",
    "limit": 20000,
    "dataset_id": "",
    "auto_snapshot": True,
    # Hedef: kâr odaklı (trende uygun dip alımı / tepe satışı) — varsayılan
    "objective": "profit",
    "excess_quantile": 0.60,
    "trend_gate": True,
    "dip_gate": True,
    "top_gate": True,
    "trend_filter": True,
    "proximity_band": 0.001,
    "extreme_window": 0,
    "agree_tolerance": 2,
    # Etiket (yalnızca forward hedefi seçilirse kullanılır)
    "horizon": 24,
    "target_move": 0.0,   # 0 = ATR'den türet
    "stop_move": 0.0,     # 0 = ATR'den türet
    # Uğraşma düzeyi
    "effort": "balanced",  # quick | balanced | thorough
    "search_budget": 3,
    "refine_iterations": 5,
    "refine_patience": 2,
    "min_gain": 0.0,
    "walk_forward": True,
    "folds": 3,
    "use_feedback": True,
    "feedback_weight": 0.5,
    "min_trades": 6,
    "min_precision": 0.35,
    "threshold_adjust": True,
    # Mimari (boş = sistem seçer)
    "engine": "auto",
    "output_mode": "dual_binary",
    "feature_groups": [],          # boş = sistem seçer
    "hidden_layers": [],           # boş = sistem seçer
    "activation": "auto",
    "advanced": {},                # elle verilen spec alanları (kazanır)
    "preset": "balanced",
    "version": PROFILE_VERSION,
    # Sıra modelleri
    "seq_window": 24,
    "lstm_hidden": 28,
    "trans_dim": 28,
    "trans_heads": 2,
    "trans_layers": 1,
    "seq_max_samples": 3500,
    "class_balance": 0.6,
    "ensemble": 2,
    # İşlem disiplini: trendi yakala, gürültüde atılma
    "trailing_stop": 0.08,
    "min_hold": 24,
    "cooldown": 24,
    "regime_band": 0.02,
    "entry_rate": 0.02,
}

EFFORT_LEVELS: Dict[str, Dict[str, Any]] = {
    "quick": {
        "label": "Hızlı",
        "desc": "Tek mimari, az tur. Birkaç dakikada sonuç.",
        "search_budget": 1,
        "refine_iterations": 2,
        "refine_patience": 1,
        "folds": 0,
        "walk_forward": False,
    },
    "balanced": {
        "label": "Dengeli",
        "desc": "Önerilen. Birkaç mimari dener, hatalardan ders alır.",
        "search_budget": 3,
        "refine_iterations": 5,
        "refine_patience": 2,
        "folds": 3,
        "walk_forward": True,
    },
    "thorough": {
        "label": "Titiz",
        "desc": "En çok mimari ve tur. En uzun süre, en iyi sonuç arayışı.",
        "search_budget": 6,
        "refine_iterations": 8,
        "refine_patience": 3,
        "folds": 4,
        "walk_forward": True,
    },
}

# Sistemin deneyeceği mimariler (ucuzdan pahalıya).
LAYER_CHOICES = ([32, 16], [64, 32], [64, 32, 16], [128, 64, 32])
ACTIVATION_CHOICES = ("relu", "gelu")

# Sistemin deneyeceği özellik grupları.
LEAN_GROUPS = [
    "returns", "range_position", "rsi_macd", "volatility", "volume", "local_extremes",
]
FULL_GROUPS = [
    "returns", "range_position", "ema", "rsi_macd", "bollinger", "volatility",
    "volume", "candle", "donchian", "stochastic", "local_extremes",
    "trend", "atr_position", "regime", "htf_trend",
]

# Sıra modelleri için yalın set: en çok bilgi taşıyan gruplar. Özellik sayısı
# düştükçe hem hız artar hem aşırı öğrenme azalır.
SEQ_GROUPS = [
    "returns", "range_position", "ema", "rsi_macd", "bollinger", "volatility",
    "volume", "candle", "local_extremes", "trend", "atr_position", "htf_trend",
]


def load_profile() -> Dict[str, Any]:
    raw = db.get_setting(PROFILE_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = {**DEFAULTS, **raw}
    if not isinstance(merged.get("advanced"), dict):
        merged["advanced"] = {}
    # Tek seferlik geçiş: eski profil kâr odaklı hedefe taşınır.
    if int(raw.get("version") or 0) < PROFILE_VERSION:
        merged["objective"] = "profit"
        merged["label_kind"] = "excess_return"
        merged["horizon"] = max(24, int(merged.get("horizon") or 24))
        merged["version"] = PROFILE_VERSION
        try:
            db.set_setting(PROFILE_KEY, merged)
        except Exception:  # noqa: BLE001 - kayıt başarısızsa eğitim yine çalışır
            pass
    return merged


def save_profile(values: Dict[str, Any]) -> Dict[str, Any]:
    current = load_profile()
    # Uğraşma düzeyi önce uygulanır; açıkça verilen alanlar onu ezer.
    if values.get("effort") in EFFORT_LEVELS:
        level = EFFORT_LEVELS[values["effort"]]
        current["effort"] = values["effort"]
        for key in ("search_budget", "refine_iterations", "refine_patience", "folds", "walk_forward"):
            current[key] = level[key]
    numbers = {
        "limit": (2000, 250_000),
        "horizon": (2, 500),
        "extreme_window": (0, 100),
        "agree_tolerance": (0, 20),
        "search_budget": (1, 8),
        "refine_iterations": (1, 12),
        "refine_patience": (1, 6),
        "folds": (0, 6),
        "min_trades": (1, 5000),
    }
    floats = {
        "target_move": (0.0, 0.5),
        "stop_move": (0.0, 0.5),
        "proximity_band": (0.0, 0.05),
        "min_precision": (0.05, 0.95),
        "min_gain": (0.0, 10.0),
        "feedback_weight": (0.0, 2.0),
    }
    for key, (low, high) in numbers.items():
        if key in values and values[key] is not None:
            try:
                current[key] = max(low, min(int(values[key]), high))
            except (TypeError, ValueError):
                pass
    for key, (low, high) in floats.items():
        if key in values and values[key] is not None:
            try:
                current[key] = max(low, min(float(values[key]), high))
            except (TypeError, ValueError):
                pass

    if values.get("coin"):
        current["coin"] = str(values["coin"]).strip().upper()[:20]
    if values.get("period"):
        from app.market_data.periods import parse_period

        try:
            current["period"] = parse_period(str(values["period"])).text
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if values.get("preset") in PRESETS:
        current["preset"] = values["preset"]
    for key in ("auto_snapshot", "walk_forward", "use_feedback", "threshold_adjust"):
        if key in values and values[key] is not None:
            current[key] = bool(values[key])
    if "dataset_id" in values:
        text = str(values.get("dataset_id") or "").strip()
        if text:
            from app.ai import datasets

            meta = datasets.manifest(text)
            if not meta:
                raise ValueError("Veri seti bulunamadı")
            current["dataset_id"] = text
            current["coin"] = str(meta.get("coin") or current["coin"])
            current["period"] = str(meta.get("period") or current["period"])
        else:
            current["dataset_id"] = ""
    if values.get("objective") in {"local_min_max", "forward"}:
        current["objective"] = values["objective"]
    if values.get("engine") in {"auto", "mlp", "gbm"}:
        current["engine"] = values["engine"]
    if values.get("activation") in {"auto", "relu", "leaky_relu", "tanh", "gelu", "sigmoid"}:
        current["activation"] = values["activation"]
    if values.get("output_mode") in {"dual_binary", "ternary", "regression"}:
        current["output_mode"] = values["output_mode"]
    if "feature_groups" in values and isinstance(values["feature_groups"], list):
        from app.ai.features import GROUPS

        groups = [str(g) for g in values["feature_groups"] if str(g) in GROUPS]
        current["feature_groups"] = groups
    if "hidden_layers" in values and isinstance(values["hidden_layers"], list):
        layers = []
        for item in values["hidden_layers"]:
            try:
                size = int(item)
            except (TypeError, ValueError):
                continue
            if 0 < size <= 1024:
                layers.append(size)
        current["hidden_layers"] = layers[:6]
    if isinstance(values.get("advanced"), dict):
        current["advanced"] = {**current.get("advanced", {}), **values["advanced"]}

    db.set_setting(PROFILE_KEY, current)
    return current


def _spec_from_profile(profile: Dict[str, Any], *, layers, activation, groups, engine) -> Dict[str, Any]:
    spec = normalize_spec(
        {
            "engine": engine,
            "output_mode": profile.get("output_mode") or "dual_binary",
            "hidden_layers": layers,
            "activation": activation,
            "dropout": profile.get("dropout", 0.15),
            "learning_rate": profile.get("learning_rate", 0.003),
            "epochs": profile.get("epochs", 120),
            "batch_size": profile.get("batch_size", 256),
            "l2": profile.get("l2", 0.0005),
            "patience": profile.get("patience", 15),
            "feature_groups": groups,
            **(profile.get("advanced") or {}),
        }
    )
    return spec


def candidate_specs(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Denenecek mimari adayları (ucuzdan pahalıya doğru sıralı).

    Varsayılan sıra: **LSTM → Transformer → MLP** (gerekirse GBM). Sıra
    modelleri son N mumun gidişatını gördüğü için ana adaylardır; MLP tek
    mumla yetinir, GBM ise hızlı bir referanstır.
    """
    engine_pref = str(profile.get("engine") or "auto")
    group_pref = [str(g) for g in (profile.get("feature_groups") or [])]
    groups = group_pref or SEQ_GROUPS
    window = int(profile.get("seq_window") or 24)
    hidden = int(profile.get("lstm_hidden") or 28)
    dim = int(profile.get("trans_dim") or 28)
    budget = max(1, int(profile.get("search_budget") or 3))

    def base(engine: str, **extra: Any) -> Dict[str, Any]:
        spec = _spec_from_profile(profile, layers=[64, 32], activation="relu", groups=groups, engine=engine)
        spec.update({k: v for k, v in extra.items() if v is not None})
        return spec

    # Arama ucuz olsun: kısa eğitim, kazanan tam bütçeyle yeniden eğitilir.
    plans: List[Dict[str, Any]] = []
    if engine_pref == "lstm":
        plans = [
            base("lstm", lstm_hidden=hidden, seq_window=window),
            base("lstm", lstm_hidden=hidden * 2, seq_window=window),
        ]
    elif engine_pref == "transformer":
        plans = [
            base("transformer", trans_dim=dim, seq_window=window, trans_layers=1),
            base("transformer", trans_dim=dim, seq_window=window, trans_layers=2),
        ]
    elif engine_pref == "mlp":
        plans = [base("mlp", hidden_layers=[64, 32]), base("mlp", hidden_layers=[128, 64])]
    elif engine_pref == "gbm":
        plans = [base("gbm")]
    else:
        # Varsayılan arama ucuzdan pahalıya: kısa pencere sıra modelleri önce.
        plans = [
            base("lstm", lstm_hidden=hidden, seq_window=window),
            base("transformer", trans_dim=dim, seq_window=window, trans_layers=1),
            base("mlp", hidden_layers=[64, 32]),
        ]
        if budget >= 4:
            plans.append(base("transformer", trans_dim=dim * 2, seq_window=window, trans_layers=2))
        try:
            from app.ai.model import SKLEARN_AVAILABLE

            if SKLEARN_AVAILABLE and budget >= 5:
                plans.append(base("gbm"))
        except Exception:
            pass

    specs: List[Dict[str, Any]] = []
    for spec in plans:
        # Arama aşamasında daha kısa eğitim: aday sayısı × süre sınırlı kalsın.
        spec["epochs"] = min(int(spec.get("epochs") or 20), 10 if spec.get("engine") == "transformer" else 14)
        spec["patience"] = min(int(spec.get("patience") or 8), 6)
        if not validate_spec(spec):
            specs.append(spec)
        if len(specs) >= max(6, budget):
            break
    return specs[:budget]


def _score_of(manifest: Dict[str, Any]) -> float:
    """Aday sıralaması: 3 pencereli işlem kalitesi (kâr) ana ölçüt."""
    metrics = manifest.get("metrics") or {}
    quality = (metrics.get("quality") or {}).get("robust") or {}
    if quality.get("score") is not None:
        return float(quality["score"])
    ref = metrics.get("refinement") or {}
    agr = metrics.get("agreement") or {}
    val_agr = agr.get("validation") or {}
    f1 = val_agr.get("f1")
    if f1 is None:
        return float(ref.get("best_score") or _score(metrics))
    val = metrics.get("validation") or {}
    edge = float(val.get("edge_pct") or 0.0)
    ret = float(val.get("total_return_pct") or 0.0)
    trades = int(val.get("trade_count") or 0)
    score = float(f1) * 100.0
    score += max(-15.0, min(edge, 30.0)) * 0.2
    score += max(-10.0, min(ret, 30.0)) * 0.1
    if edge < -15.0:
        score -= min(8.0, (-15.0 - edge) * 0.25)
    if trades < 3:
        score -= 20.0
    return round(score, 4)


def _validation(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return ((manifest.get("metrics") or {}).get("validation") or {})


def auto_train(params: Optional[Dict[str, Any]] = None, job_id: Optional[str] = None) -> Dict[str, Any]:
    """Tek düğme: ayarları profilden alır, aramayı yapar, en iyiyi uygular."""
    overrides = dict(params or {})
    if overrides:
        # Gönderilen alanlar profil üzerine yazılır (kalıcı olarak).
        save_profile({k: v for k, v in overrides.items() if k not in {"_job_id", "retrain_model_id"}})
    profile = load_profile()
    coin = str(profile.get("coin") or "BTCUSDT").upper()
    period = str(profile.get("period") or "1h")
    preset = PRESETS.get(str(profile.get("preset") or "balanced"), PRESETS["balanced"])
    champion = _active_champion(coin, period)
    champion_score = _score_of(champion) if champion else None

    def progress(pct: int, message: str) -> None:
        if not job_id:
            return
        from app.job_runner import _progress

        _progress(job_id, pct, message)

    # Hedef türü: "profit" → kâr odaklı excess_return; aksi halde LMM taklidi.
    label_kind = "excess_return" if str(profile.get("objective") or "profit") != "local_min_max" else "local_min_max"
    specs = candidate_specs(profile)
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    # 1) Arama: her aday yalnızca eğitim + validation ile ölçülür, test kapalı.
    for index, spec in enumerate(specs, start=1):
        progress(5 + int((index - 1) / max(len(specs), 1) * 55), f"Aday {index}/{len(specs)} eğitiliyor")
        train_params: Dict[str, Any] = {
            "name": f"{coin} {period} auto",
            "coin": coin,
            "period": period,
            "limit": int(profile.get("limit") or 20000),
            "label_kind": label_kind,
            "proximity_band": float(profile.get("proximity_band") or 0.001),
            "extreme_window": int(profile.get("extreme_window") or 0),
            "agree_tolerance": int(profile.get("agree_tolerance") or 2),
            "min_precision": float(profile.get("min_precision") or 0.35),
            "excess_quantile": float(profile.get("excess_quantile") or 0.65),
            "trend_gate": bool(profile.get("trend_gate", True)),
            "dip_gate": bool(profile.get("dip_gate", True)),
            "top_gate": bool(profile.get("top_gate", True)),
            "trend_filter": bool(profile.get("trend_filter", True)),
            "trailing_stop": float(profile.get("trailing_stop") or 0.0),
            "min_hold": int(profile.get("min_hold") or 0),
            "cooldown": int(profile.get("cooldown") or 0),
            "regime_band": float(profile.get("regime_band") or 0.02),
            "class_balance": float(profile.get("class_balance", 0.6)),
            "seq_max_samples": int(profile.get("seq_max_samples") or 3500),
            "horizon": int(profile.get("horizon") or 24),
            "target_move": float(profile.get("target_move") or 0.0),
            "stop_move": float(profile.get("stop_move") or 0.0),
            "walk_forward": False,  # aramada pahalı; kazanan için çalıştırılır
            "folds": int(profile.get("folds") or 3),
            "use_feedback": bool(profile.get("use_feedback", True)),
            "feedback_weight": float(profile.get("feedback_weight") or 0.5),
            "min_trades": int(profile.get("min_trades") or 6),
            "threshold_adjust": bool(profile.get("threshold_adjust", True)),
            "refine": True,
            "iterations": 1,  # arama aşamasında tek tur yeterli
            "patience": int(profile.get("refine_patience") or 2),
            "skip_test": True,
            "dataset_id": str(profile.get("dataset_id") or ""),
            "auto_snapshot": bool(profile.get("auto_snapshot", True)),
            "spec": spec,
        }
        if champion:
            train_params["parent_model_id"] = champion["id"]
            train_params["warm_start"] = True
        try:
            result = train_model(train_params)
        except Exception as exc:  # noqa: BLE001 - aday hatası aramayı durdurmaz
            attempts.append(
                {"spec": spec, "error": str(exc)[:300], "score": None, "model_id": None}
            )
            continue
        manifest = result["model"]
        score = _score_of(manifest)
        # Performans eşitse zamanı modelleyen mimari tercih edilir (kullanıcı
        # isteği: LSTM/Transformer). Fark büyükse skor yine belirleyicidir.
        engine = str(spec.get("engine") or "mlp")
        rank = score + (3.0 if engine in {"lstm", "transformer"} else 0.0)
        attempts.append(
            {
                "spec": spec,
                "model_id": manifest["id"],
                "score": round(score, 4),
                "rank": round(rank, 4),
                "validation": _validation(manifest),
                "params": manifest.get("params") or {},
                "warm_start_used": bool((result["report"].get("lineage") or {}).get("warm_start_used")),
            }
        )
        if best is None or rank > float(best.get("rank", best["score"])):
            best = attempts[-1]

    if best is None:
        # Hiçbir aday eğitilemediyse mevcut şampiyonla devam et (kullanıcıya hata değil).
        if champion:
            return {
                "ok": True,
                "decision": "kept",
                "reason": "Adaylar eğitilemedi; mevcut model korundu.",
                "model_id": champion["id"],
                "active_model_id": champion["id"],
                "best_score": round(champion_score or 0.0, 4),
                "champion_score": round(champion_score or 0.0, 4),
                "attempts": attempts,
                "profile": profile,
                "report": artifacts.read_report(champion["id"]) or {},
            }
        raise RuntimeError("Hiçbir aday eğitilemedi: " + "; ".join(a.get("error", "") for a in attempts[:2]))

    # 2) Kazanan adayı tam eğitimle (walk-forward + tam iyileştirme) yeniden üret.
    progress(70, "En iyi aday tam eğitimle doğrulanıyor")
    final_params: Dict[str, Any] = {
        "name": f"{coin} {period} model",
        "coin": coin,
        "period": period,
        "limit": int(profile.get("limit") or 20000),
        "label_kind": label_kind,
        "proximity_band": float(profile.get("proximity_band") or 0.001),
        "extreme_window": int(profile.get("extreme_window") or 0),
        "agree_tolerance": int(profile.get("agree_tolerance") or 2),
        "min_precision": float(profile.get("min_precision") or 0.35),
        "excess_quantile": float(profile.get("excess_quantile") or 0.65),
        "trend_gate": bool(profile.get("trend_gate", True)),
        "dip_gate": bool(profile.get("dip_gate", True)),
        "top_gate": bool(profile.get("top_gate", True)),
        "trend_filter": bool(profile.get("trend_filter", True)),
        "trailing_stop": float(profile.get("trailing_stop") or 0.0),
        "min_hold": int(profile.get("min_hold") or 0),
        "cooldown": int(profile.get("cooldown") or 0),
        "regime_band": float(profile.get("regime_band") or 0.02),
        "class_balance": float(profile.get("class_balance", 0.6)),
        "seq_max_samples": int(profile.get("seq_max_samples") or 3500),
        "horizon": int(profile.get("horizon") or 24),
        "target_move": float(profile.get("target_move") or 0.0),
        "stop_move": float(profile.get("stop_move") or 0.0),
        "walk_forward": bool(profile.get("walk_forward", True)),
        "folds": int(profile.get("folds") or preset.get("folds", 3)),
        "use_feedback": bool(profile.get("use_feedback", True)),
        "feedback_weight": float(profile.get("feedback_weight") or 0.5),
        "min_trades": int(profile.get("min_trades") or 6),
        "threshold_adjust": bool(profile.get("threshold_adjust", True)),
        "refine": True,
        "iterations": int(profile.get("refine_iterations") or 5),
        "patience": int(profile.get("refine_patience") or 2),
        "skip_test": False,
        "dataset_id": str(profile.get("dataset_id") or ""),
        "auto_snapshot": bool(profile.get("auto_snapshot", True)),
        # Kazanan aday tam bütçeyle eğitilir. Sıra modelleri epoch başına
        # pahalıdır; 32 epoch + sabırlı erken durma yeter. Üst düzey alanlar
        # spec'i ezer.
        "epochs": int(
            (16 if str(best["spec"].get("engine")) == "transformer" else 22)
            if str(best["spec"].get("engine")) in {"lstm", "transformer"}
            else max(150, min(int(best["spec"].get("epochs") or 120), 250))
        ),
        "patience": int(
            8 if str(best["spec"].get("engine")) in {"lstm", "transformer"}
            else max(18, int(best["spec"].get("patience") or 15))
        ),
        "class_balance": float(profile.get("class_balance") or 0.6),
        "ensemble": int(max(1, min(int(profile.get("ensemble") or 2), 4))),
        "spec": best["spec"],
    }
    parent_id = (best.get("params") or {}).get("parent_id") or ""
    if parent_id:
        final_params["parent_model_id"] = parent_id
        final_params["warm_start"] = True
    final = train_model(final_params)
    final_manifest = final["model"]
    final_report = final["report"]
    final_score = _score_of(final_manifest)

    progress(92, "Karar veriliyor")
    # 3) Mevcut modelle karşılaştır.
    min_gain = float(profile.get("min_gain") or 0.0)
    # Eski modeller farklı bir skorla üretilmiş olabilir; o zaman kıyaslama
    # elmayla armut olur. Yeni ölçüt (3 pencereli işlem kalitesi) yoksa yeni
    # adayı, makul bir işlem sayısı şartıyla şampiyon kabul ederiz.
    champ_quality = ((champion or {}).get("metrics") or {}).get("quality") or {}
    champ_robust = champ_quality.get("robust") or {}
    comparable = bool(champion) and champ_robust.get("score") is not None
    final_trades = int((((final_manifest.get("metrics") or {}).get("validation") or {}).get("trade_count")) or 0)
    if not comparable:
        improved = final_score > -40.0 and final_trades >= 3
    else:
        improved = final_score >= (champion_score or 0.0) + min_gain
    # "kept" kararında geçici aday model sonunda silinir; liste şişmez.
    discard_final = False

    if improved and champion:
        # Aynı modeli yerinde güncelle: kimlik korunur, sürüm artar.
        bundle = artifacts.load_bundle(final_manifest["id"])
        merged = artifacts.save_model(
            name=champion.get("name") or f"{coin} {period} model",
            bundle=bundle,
            model_id=champion["id"],
            params={**(champion.get("params") or {}), **(final_manifest.get("params") or {})},
            metrics=final_manifest.get("metrics") or {},
            data_meta=final_manifest.get("data") or {},
            feature_names=final_manifest.get("feature_names") or [],
            thresholds=final_manifest.get("thresholds") or {},
            notes=str((champion.get("notes") or ""))[:200],
        )
        artifacts.write_report(champion["id"], {**final_report, "auto": {"decision": "updated"}})
        try:
            artifacts.delete_model(final_manifest["id"])
        except Exception:
            pass
        active = merged
        decision = "updated"
        reason = (
            f"Mevcut model güncellendi: v{merged.get('version')} · "
            f"{final_score:+.2f} ≥ {champion_score:+.2f}"
        )
    elif improved:
        artifacts.set_status(final_manifest["id"], "active")
        active = final_manifest
        decision = "created"
        reason = f"İlk model aktifleştirildi: {final_score:+.2f}"
    else:
        # Gerileme yok: şampiyon korunur. Aday model diske kaydedilmez;
        # aday/arşiv listesi gereksiz şişmesin.
        artifacts.set_status(final_manifest["id"], "candidate")
        active = champion
        discard_final = True
        decision = "kept"
        reason = (
            f"Mevcut model korundu: şampiyon {champion_score:+.2f} ≥ "
            f"yeni {final_score:+.2f}"
        )

    # Arama adaylarını arşivle: model listesi şişmesin. Kazanan zaten
    # şampiyona taşındı veya aktifleştirildi.
    keep_ids = {str((active or {}).get("id") or ""), str(final_manifest["id"])}
    for attempt in attempts:
        candidate_id = attempt.get("model_id")
        if not candidate_id or candidate_id in keep_ids:
            continue
        try:
            artifacts.delete_model(candidate_id)
        except Exception:
            pass
    summary = {
        "decision": decision,
        "reason": reason,
        "best_score": round(final_score, 4),
        "champion_score": None if champion_score is None else round(champion_score, 4),
        "active_model_id": active["id"] if active else final_manifest["id"],
        "attempts": [
            {k: v for k, v in a.items() if k != "params"} for a in attempts
        ],
        "spec": best["spec"],
    }
    try:
        artifacts.write_report(
            str((active or {}).get("id") or final_manifest["id"]),
            {**final_report, "auto": summary},
        )
    except Exception:
        pass
    # "kept" kararında geçici aday diske bırakılmaz: aday/arşiv listesi şişmesin.
    if discard_final:
        try:
            artifacts.delete_model(final_manifest["id"])
        except Exception:
            pass
    db.set_setting(
        "ai_last_auto",
        {
            **summary,
            "at": db.utcnow(),
            "coin": coin,
            "period": period,
        },
    )
    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "model_id": active["id"] if discard_final else final_manifest["id"],
        "active_model_id": active["id"] if active else final_manifest["id"],
        "best_score": round(final_score, 4),
        "champion_score": None if champion_score is None else round(champion_score, 4),
        "attempts": attempts,
        "spec": best["spec"],
        "profile": profile,
        "report": final_report,
    }
