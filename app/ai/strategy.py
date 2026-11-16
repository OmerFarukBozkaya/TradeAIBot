"""Eğitilmiş AI modelini bot/backtest motoruna bağlayan strateji adaptörü.

Canlıda ve backtestte **aynı** çıkarım yolu kullanılır. Karar daima kapanmış
mum üzerinden verilir; model yalnızca o ana kadarki özellikleri görür.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from app.ai import artifacts
from app.ai.features import build_features
from app.ai.model import predict_positive


class AIModelStrategy:
    def __init__(self, model_id: str, version: Optional[int] = None, allow_archived: bool = False):
        self.model_id = str(model_id)
        self.manifest = artifacts.load_manifest(self.model_id)
        if not self.manifest:
            raise ValueError(f"AI modeli bulunamadı: {self.model_id}")
        # Arşiv modeli canlı bota eklenemez; ancak backtest/teşhis için
        # geçmiş performansını yeniden görmek isteyebilirsin.
        if str(self.manifest.get("status") or "candidate") == "archived" and not allow_archived:
            raise ValueError(f"AI modeli arşivlenmiş: {self.model_id}")
        self.bundle = artifacts.load_bundle(self.model_id)
        self.feature_names = list(
            self.bundle.get("feature_names") or self.manifest.get("feature_names") or []
        )
        self.fill_values = np.asarray(
            self.bundle.get("fill_values") or [0.0] * len(self.feature_names), dtype=float
        )
        thresholds = self.bundle.get("thresholds") or self.manifest.get("thresholds") or {}
        self.buy_threshold = float(thresholds.get("buy") or 0.6)
        self.sell_threshold = float(thresholds.get("sell") or 0.6)
        self.horizon = int(self.bundle.get("horizon") or self.manifest.get("params", {}).get("horizon") or 12)
        self.id = self.model_id
        self.name = self.manifest.get("name") or self.model_id
        self.version = int(version or self.manifest.get("version") or 1)
        self.warmup = 210
        self.definition = {
            "ai_model": self.model_id,
            "thresholds": {
                "buy": self.buy_threshold,
                "sell": self.sell_threshold,
            },
        }
        self._prepared: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Çıkarım
    # ------------------------------------------------------------------
    def _predict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        feature = build_features(data)
        X = feature["X"]
        if X.size and self.fill_values.size == X.shape[1]:
            X = np.where(np.isfinite(X), X, self.fill_values)
        buy = predict_positive(self.bundle["buy_model"], X) if len(X) else np.array([])
        sell = predict_positive(self.bundle["sell_model"], X) if len(X) else np.array([])
        return {
            "length": len(feature["close"]),
            "feature_names": feature["feature_names"],
            "frame": feature["frame"],
            "buy_prob": buy,
            "sell_prob": sell,
            "close": feature["close"],
            "warmup": max(self.warmup, int(feature.get("warmup") or 0)),
        }

    def prepare(self, data: Dict[str, Any]) -> None:
        self._prepared = self._predict(data)

    def _ensure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        n = len(data.get("close") or [])
        if self._prepared is None or self._prepared.get("length") != n:
            self.prepare(data)
        return self._prepared  # type: ignore

    def evaluate_at(self, data: Dict[str, Any], idx: int) -> Dict[str, Any]:
        prepared = self._ensure(data)
        n = len(data.get("close") or [])
        warmup = int(prepared.get("warmup") or 0)
        result = {
            "strategy_id": self.id,
            "version": self.version,
            "candle_index": idx,
            "candle_time": (data.get("opendate") or [None] * n)[idx] if 0 <= idx < n else None,
            "buy": False,
            "sell": False,
            "buy_detail": None,
            "sell_detail": None,
            "warmup_ok": n >= warmup and idx >= warmup and idx < n,
        }
        if not result["warmup_ok"]:
            return result
        buy_p = float(prepared["buy_prob"][idx])
        sell_p = float(prepared["sell_prob"][idx])
        if not np.isfinite(buy_p):
            buy_p = 0.0
        if not np.isfinite(sell_p):
            sell_p = 0.0
        buy = buy_p >= self.buy_threshold and sell_p < self.sell_threshold
        sell = sell_p >= self.sell_threshold
        feature_snapshot = {}
        try:
            row = prepared["frame"].iloc[idx]
            feature_snapshot = {
                str(k): (None if row[k] != row[k] else float(row[k]))
                for k in prepared["feature_names"]
            }
        except Exception:
            feature_snapshot = {}
        detail = {
            "source": "ai",
            "model_id": self.model_id,
            "buy_probability": round(buy_p, 6),
            "sell_probability": round(sell_p, 6),
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "features": feature_snapshot,
        }
        result["buy"] = bool(buy)
        result["sell"] = bool(sell)
        result["buy_detail"] = {**detail, "result": bool(buy)}
        result["sell_detail"] = {**detail, "result": bool(sell)}
        return result

    def evaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        n = len(data.get("close") or [])
        return self.evaluate_at(data, n - 2)

    def buy_signal(self, data: Dict[str, Any]) -> bool:
        return bool(self.evaluate(data).get("buy"))

    def sell_signal(self, data: Dict[str, Any]) -> bool:
        return bool(self.evaluate(data).get("sell"))


def ai_model_specs(include_candidate: bool = True) -> list[Dict[str, Any]]:
    """Panel/bot seçimi için AI modellerini strateji biçiminde döndürür."""
    items = []
    try:
        models = artifacts.list_models(include_archived=False)
    except Exception:
        models = []
    for model in models:
        status = str(model.get("status") or "candidate")
        if not include_candidate and status != "active":
            continue
        if status == "archived":
            continue
        test = ((model.get("metrics") or {}).get("test") or {})
        items.append(
            {
                "id": model["id"],
                "name": f"AI · {model['name']}",
                "kind": "ai",
                "status": status,
                "model_id": model["id"],
                "metrics": test,
                "spec": {"type": "ai", "model_id": model["id"]},
            }
        )
    return items
