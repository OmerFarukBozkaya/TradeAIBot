"""Eğitilmiş AI modelini bot/backtest motoruna bağlayan strateji adaptörü.

Canlıda ve backtestte **aynı** çıkarım yolu kullanılır. Karar daima kapanmış
mum üzerinden verilir; model yalnızca o ana kadarki özellikleri görür.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from app.ai import artifacts
from app.ai.features import build_features, warmup_for
from app.ai.model import predict_sequence, predict_signals
from app.ai.sequence import SequenceData


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
        fill_raw = self.bundle.get("fill_values")
        if fill_raw is None:
            fill_raw = [0.0] * len(self.feature_names)
        self.fill_values = np.asarray(fill_raw, dtype=float)
        thresholds = self.bundle.get("thresholds") or self.manifest.get("thresholds") or {}
        self.buy_threshold = float(thresholds.get("buy") or 0.6)
        self.sell_threshold = float(thresholds.get("sell") or 0.6)
        self.horizon = int(self.bundle.get("horizon") or self.manifest.get("params", {}).get("horizon") or 12)
        self.feature_groups = self.bundle.get("feature_groups") or []
        self.output_mode = str(self.bundle.get("output_mode") or "dual_binary")
        self.is_sequence = self.bundle.get("sequence_model") is not None
        self.seq_window = int(self.bundle.get("seq_window") or 24)
        self.trend_filter = bool(self.bundle.get("trend_filter", False))
        self.spec = self.bundle.get("spec") or self.manifest.get("params") or {}
        self.id = self.model_id
        self.name = self.manifest.get("name") or self.model_id
        self.version = int(version or self.manifest.get("version") or 1)
        base_warmup = warmup_for(self.feature_groups) if self.feature_groups else 210
        self.warmup = max(base_warmup, self.seq_window + 1) if self.is_sequence else base_warmup
        self.definition = {
            "ai_model": self.model_id,
            "output_mode": self.output_mode,
            "feature_groups": self.feature_groups,
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
        feature = build_features(data, self.feature_groups)
        frame = feature["frame"]
        X = feature["X"]
        # Model kendi eğitildiği kolon şemasını bekler. Yeni sürümde özellik
        # seti değişmiş olabilir; eksik kolonlar NaN, fazlalar atılır.
        if self.feature_names and list(frame.columns) != list(self.feature_names):
            frame = frame.reindex(columns=self.feature_names)
            X = frame.to_numpy(dtype=float)
        n = len(feature["close"])
        if self.is_sequence:
            buy = np.full(n, np.nan)
            sell = np.full(n, np.nan)
            if n > self.seq_window:
                try:
                    seq = SequenceData.from_bundle(X, self.bundle)
                    pos = np.arange(self.seq_window - 1, n)
                    p_buy, p_sell = predict_sequence(self.bundle, seq, pos)
                    buy[pos] = p_buy
                    sell[pos] = p_sell
                except Exception:
                    buy = np.full(n, 0.0)
                    sell = np.full(n, 0.0)
        else:
            if X.size and self.fill_values.size == X.shape[1]:
                X = np.where(np.isfinite(X), X, self.fill_values)
            buy, sell = predict_signals(self.bundle, X) if len(X) else (np.array([]), np.array([]))
        trend_ok = np.ones(n, dtype=bool)
        if self.trend_filter:
            from app.ai.labels import _ema

            close = np.asarray(feature["close"], dtype=float)
            trend_ok = (_ema(close, 20) > _ema(close, 50)) & (_ema(close, 50) > _ema(close, 200))
        return {
            "length": n,
            "feature_names": self.feature_names or feature["feature_names"],
            "frame": frame,
            "buy_prob": buy,
            "sell_prob": sell,
            "trend_ok": trend_ok,
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
        gate = True
        if self.trend_filter:
            # ``trend_ok`` bir numpy dizisidir; ``or`` ile varsayılan vermek
            # dizinin tamamını bool'a çevirmeye çalışıp hata verir.
            trend = prepared.get("trend_ok")
            if trend is not None and 0 <= idx < len(trend):
                gate = bool(trend[idx])
        buy = buy_p >= self.buy_threshold and sell_p < self.sell_threshold and gate
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
            "trend_ok": gate,
            "engine": "sequence" if self.is_sequence else "tabular",
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
