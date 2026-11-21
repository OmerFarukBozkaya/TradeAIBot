"""Model mimarisi tanımı ve doğrulaması.

Panelden seçilebilen her şey burada tanımlanır: motor, katmanlar,
aktivasyon, düzenlileştirme, çıktı biçimi ve özellik grupları.

Varsayılanlar, "makul bir başlangıç" olarak seçildi; kullanıcı isterse
tamamen değiştirebilir. Doğrulama, eğitim başlamadan hatalı yapılandırmayı
yakalar.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.ai.features import DEFAULT_GROUPS, GROUPS, normalize_groups

ENGINES: Dict[str, Dict[str, str]] = {
    "lstm": {"label": "LSTM (sıra)", "desc": "Son N mumun gidişatını hafızayla öğrenir"},
    "transformer": {"label": "Transformer (sıra)", "desc": "Dikkat (attention) ile pencereyi bir bütün olarak okur"},
    "mlp": {"label": "Sinir ağı (MLP)", "desc": "Tek mumun özelliklerine bakar; hızlı ve hafif"},
    "gbm": {"label": "Gradient boosting", "desc": "Ağaç tabanlı; hızlı başlangıç, sıra belleği yok"},
}

OUTPUT_MODES: Dict[str, Dict[str, str]] = {
    "dual_binary": {
        "label": "İki ayrı sinyal (AL / SAT)",
        "desc": "Bir model alım olasılığı, bir model satım olasılığı üretir",
    },
    "ternary": {
        "label": "Tek model: nötr / dip / zirve",
        "desc": "Üç sınıflı model; dip olasılığı AL, zirve olasılığı SAT olur",
    },
    "regression": {
        "label": "Gelecek getiri (regresyon)",
        "desc": "Ufuk sonundaki yüzde getiriyi tahmin eder; işaretine göre AL/SAT",
    },
}

ACTIVATIONS = {
    "relu": "ReLU (önerilen)",
    "leaky_relu": "Leaky ReLU",
    "tanh": "Tanh",
    "gelu": "GELU",
    "sigmoid": "Sigmoid",
}

DEFAULT_SPEC: Dict[str, Any] = {
    "engine": "mlp",
    "output_mode": "dual_binary",
    "hidden_layers": [64, 32],
    "activation": "relu",
    "dropout": 0.15,
    "learning_rate": 0.003,
    "epochs": 120,
    "batch_size": 256,
    "l2": 0.0005,
    "patience": 15,
    "es_min_delta": 1e-4,
    "grad_clip": 5.0,
    "lr_decay": True,
    # Sıra modelleri
    "seq_window": 24,
    "seq_batch": 0,  # 0 = motora göre otomatik (LSTM 64, Transformer 256)
    "lstm_hidden": 28,
    "trans_dim": 28,
    "trans_heads": 2,
    "trans_layers": 1,
    "ffn_activation": "relu",
    "feature_groups": list(DEFAULT_GROUPS),
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def normalize_spec(raw: Any) -> Dict[str, Any]:
    """Gelen ham mimari tanımını güvenli ve tutarlı biçime getirir."""
    data = raw if isinstance(raw, dict) else {}
    spec = dict(DEFAULT_SPEC)

    engine = str(data.get("engine") or spec["engine"])
    spec["engine"] = engine if engine in ENGINES else "mlp"

    mode = str(data.get("output_mode") or spec["output_mode"])
    spec["output_mode"] = mode if mode in OUTPUT_MODES else "dual_binary"

    layers_raw = data.get("hidden_layers", spec["hidden_layers"])
    if isinstance(layers_raw, str):
        layers_raw = [p for p in layers_raw.replace("x", ",").split(",") if p.strip()]
    layers: List[int] = []
    for item in layers_raw or []:
        try:
            size = int(item)
        except (TypeError, ValueError):
            continue
        if 0 < size <= 1024:
            layers.append(size)
    spec["hidden_layers"] = layers[:6] or list(DEFAULT_SPEC["hidden_layers"])

    activation = str(data.get("activation") or spec["activation"])
    spec["activation"] = activation if activation in ACTIVATIONS else "relu"

    spec["dropout"] = round(_clamp(data.get("dropout", spec["dropout"]), 0.0, 0.8), 3)
    spec["learning_rate"] = round(_clamp(data.get("learning_rate", spec["learning_rate"]), 1e-5, 0.5), 6)
    spec["epochs"] = int(_clamp(data.get("epochs", spec["epochs"]), 5, 2000))
    spec["batch_size"] = int(_clamp(data.get("batch_size", spec["batch_size"]), 16, 8192))
    spec["l2"] = round(_clamp(data.get("l2", spec["l2"]), 0.0, 0.1), 6)
    spec["patience"] = int(_clamp(data.get("patience", spec["patience"]), 1, 200))
    spec["es_min_delta"] = round(_clamp(data.get("es_min_delta", spec["es_min_delta"]), 0.0, 0.5), 6)
    spec["grad_clip"] = round(_clamp(data.get("grad_clip", spec["grad_clip"]), 0.0, 100.0), 3)
    spec["lr_decay"] = bool(data.get("lr_decay", spec["lr_decay"]))
    spec["seq_window"] = int(_clamp(data.get("seq_window", spec["seq_window"]), 4, 96))
    spec["seq_batch"] = int(_clamp(data.get("seq_batch", spec["seq_batch"]), 0, 1024))
    spec["lstm_hidden"] = int(_clamp(data.get("lstm_hidden", spec["lstm_hidden"]), 4, 128))
    spec["trans_dim"] = int(_clamp(data.get("trans_dim", spec["trans_dim"]), 8, 128))
    spec["trans_heads"] = int(_clamp(data.get("trans_heads", spec["trans_heads"]), 1, 8))
    spec["trans_layers"] = int(_clamp(data.get("trans_layers", spec["trans_layers"]), 1, 4))
    ffn = str(data.get("ffn_activation", spec["ffn_activation"]))
    spec["ffn_activation"] = ffn if ffn in {"relu", "gelu"} else "relu"

    groups = data.get("feature_groups", spec["feature_groups"])
    spec["feature_groups"] = normalize_groups(list(groups or []))
    return spec


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if spec.get("engine") not in ENGINES:
        errors.append("Bilinmeyen motor")
    if spec.get("output_mode") not in OUTPUT_MODES:
        errors.append("Bilinmeyen çıktı biçimi")
    if spec.get("activation") not in ACTIVATIONS:
        errors.append("Bilinmeyen aktivasyon")
    if spec.get("engine") == "mlp" and not spec.get("hidden_layers"):
        errors.append("Sinir ağı için en az bir gizli katman gerekli")
    if spec.get("engine") == "mlp" and int(spec.get("epochs") or 0) < 5:
        errors.append("Epoch sayısı çok küçük")
    if int(spec.get("epochs") or 0) < 5:
        errors.append("Epoch sayısı çok küçük (en az 5)")
    groups = spec.get("feature_groups") or []
    unknown = [g for g in groups if g not in GROUPS]
    if unknown:
        errors.append(f"Bilinmeyen özellik grubu: {', '.join(unknown)}")
    if not groups:
        errors.append("En az bir özellik grubu seçilmeli")
    return errors


def describe_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Panelde tek satırda göstermek için özet."""
    engine = ENGINES.get(spec.get("engine", ""), {}).get("label", spec.get("engine"))
    mode = OUTPUT_MODES.get(spec.get("output_mode", ""), {}).get("label", spec.get("output_mode"))
    layers = spec.get("hidden_layers") or []
    groups = spec.get("feature_groups") or []
    if spec.get("engine") == "mlp":
        arch = " → ".join([str(x) for x in layers])
        detail = f"{arch} · {spec.get('activation')} · dropout {spec.get('dropout')}"
    else:
        detail = "ağaç topluluğu"
    return {
        "engine": engine,
        "output_mode": mode,
        "architecture": detail,
        "features": len(groups),
        "feature_groups": groups,
        "summary": f"{engine} · {detail} · {mode} · {len(groups)} özellik grubu",
    }


def architecture_catalog() -> Dict[str, Any]:
    """Panelin mimari seçim ekranını besleyen katalog."""
    from app.ai.features import group_catalog

    return {
        "engines": [{"id": k, **v} for k, v in ENGINES.items()],
        "output_modes": [{"id": k, **v} for k, v in OUTPUT_MODES.items()],
        "activations": [{"id": k, "label": v} for k, v in ACTIVATIONS.items()],
        "feature_groups": group_catalog(),
        "defaults": DEFAULT_SPEC,
        "limits": {
            "layers": {"max_count": 6, "min_size": 1, "max_size": 1024},
            "dropout": {"min": 0.0, "max": 0.8},
            "learning_rate": {"min": 0.00001, "max": 0.5},
            "epochs": {"min": 5, "max": 2000},
            "batch_size": {"min": 16, "max": 8192},
        },
    }


def spec_from_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Eğitim parametrelerinden mimariyi çıkarır (yalın alanlar da kabul)."""
    raw = params.get("spec")
    if isinstance(raw, dict):
        merged = dict(raw)
    else:
        merged = {}
    # Üst seviyede verilen alanlar spec'i ezer (geriye uyumluluk).
    for key in (
        "engine", "output_mode", "hidden_layers", "activation", "dropout",
        "learning_rate", "epochs", "batch_size", "l2", "patience",
        "es_min_delta", "grad_clip", "lr_decay", "feature_groups",
        "seq_window", "seq_batch", "lstm_hidden", "trans_dim", "trans_heads", "trans_layers",
        "ffn_activation",
    ):
        if key in params and params[key] not in (None, ""):
            merged[key] = params[key]
    return normalize_spec(merged)


def feature_frame_groups(spec: Dict[str, Any]) -> Sequence[str]:
    return list(spec.get("feature_groups") or DEFAULT_GROUPS)
