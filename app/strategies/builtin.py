"""Mevcut `Stratejiler.py` fonksiyonlarını yeni sinyal arayüzüne sarar.

Bu sarmalayıcı, `Trade.py` içindeki alım/satım sinyali mantığını birebir korur:
- Alım: kapanmış mumda ([-2]) BUY var ve son SELL'den sonra başka BUY yok.
- Satım: kapanmış mumda ([-2]) SELL var.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core import Stratejiler

EXCLUDED = {"dinamik_stop_lose", "static_stop_lose", "destek_stop_lose", "take_profit"}


def builtin_names(include_ai: bool = False) -> List[str]:
    names = []
    for name in dir(Stratejiler):
        if name.startswith("_"):
            continue
        if name == "AI" and not include_ai:
            continue
        attr = getattr(Stratejiler, name)
        if callable(attr) and name not in EXCLUDED:
            names.append(name)
    return sorted(names)


class BuiltinStrategy:
    def __init__(self, name: str):
        fn = getattr(Stratejiler, name, None)
        if not callable(fn):
            raise ValueError(f"Bilinmeyen hazır strateji: {name}")
        self.id = name
        self.name = name
        self.version = 1
        self.warmup = 60

    def _run(self, data: Dict[str, List[float]]) -> List[Any]:
        fn = getattr(Stratejiler, self.id)
        if self.id == "Alpha_Trend":
            return fn(data["high"], data["low"], data["close"], data["volume_usdt"])
        return fn(data["high"], data["low"], data["close"])

    def prepare(self, data: Dict[str, List[float]]) -> None:
        """Backtest için tüm seriyi bir kez hesaplar."""
        self._prepared = self._run(data)

    def evaluate_at(self, data: Dict[str, List[float]], idx: int) -> Dict[str, Any]:
        n = len(data.get("close") or [])
        result = {
            "strategy_id": self.id,
            "version": self.version,
            "candle_index": idx,
            "candle_time": (data.get("opendate") or [None] * n)[idx] if 0 <= idx < n else None,
            "buy": False,
            "sell": False,
            "buy_detail": None,
            "sell_detail": None,
            "warmup_ok": n >= self.warmup and idx >= 1,
        }
        if not result["warmup_ok"]:
            return result
        signals = getattr(self, "_prepared", None)
        if signals is None:
            signals = self._run(data)
        if self.id == "AI":
            decision = signals if isinstance(signals, str) else str(signals)
            result["buy"] = decision == "BUY"
            result["sell"] = decision == "SELL"
            result["buy_detail"] = {"source": "ai", "decision": decision, "result": result["buy"]}
            result["sell_detail"] = {"source": "ai", "decision": decision, "result": result["sell"]}
            return result
        if not signals or len(signals) < 2:
            return result
        last_sell = 0
        for i in range(idx, -1, -1):
            if signals[i] == "SELL":
                last_sell = i
                break
        buy = signals[idx] == "BUY" and "BUY" not in signals[last_sell:idx]
        sell = signals[idx] == "SELL"
        result["buy"] = bool(buy)
        result["sell"] = bool(sell)
        result["buy_detail"] = {
            "source": "builtin",
            "closed_candle_signal": signals[idx],
            "last_sell_index": last_sell,
            "result": bool(buy),
        }
        result["sell_detail"] = {
            "source": "builtin",
            "closed_candle_signal": signals[idx],
            "result": bool(sell),
        }
        return result

    def evaluate(self, data: Dict[str, List[float]]) -> Dict[str, Any]:
        n = len(data.get("close") or [])
        return self.evaluate_at(data, n - 2)

    def buy_signal(self, data) -> bool:
        return self.evaluate(data)["buy"]

    def sell_signal(self, data) -> bool:
        return self.evaluate(data)["sell"]
