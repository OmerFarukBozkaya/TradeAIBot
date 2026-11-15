"""Görsel strateji tanımını çalıştırılabilir sinyal motoruna derler.

Güvenlik: `eval` kullanılmaz. Sadece whitelist operatörler ve operand türleri.
Değerlendirme her zaman kapanmış mum üzerinde yapılır (n-2), mevcut bot ile aynı.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.strategies.registry import IndicatorCache, INDICATORS, warmup_of

OPERATORS = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "==",
    "neq": "!=",
    "crosses_above": "yukarı kesti",
    "crosses_below": "aşağı kesti",
    "rising": "yükseliyor",
    "falling": "düşüyor",
    "rising_for_n": "N mumdur yükseliyor",
    "falling_for_n": "N mumdur düşüyor",
    "between": "arasında",
    "outside": "dışında",
    "pct_change_gt": "% değişim >",
    "pct_change_lt": "% değişim <",
}


class StrategyValidationError(ValueError):
    pass


def _value(series: List[Any], idx: int) -> Optional[float]:
    if idx < 0 or idx >= len(series):
        return None
    value = series[idx]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_operand(
    operand: Dict[str, Any], data: Dict[str, List[float]], cache: IndicatorCache
) -> List[Any]:
    """Operandı seriye çevirir.

    Sonuç `IndicatorCache` üzerinde önbelleğe alınır. Backtest her mum için
    `evaluate_at` çağırdığından, bu olmadan aynı seri binlerce kez yeniden
    kurulur (O(n²)). Anahtar operand tanımı + veri uzunluğudur; cache zaten
    tek bir veri anlık görüntüsüne bağlıdır.
    """
    memo = cache.__dict__.get("_operand_memo")
    n = cache.__dict__.get("_n") or len(data.get("close") or [])
    key = None
    if memo is not None:
        # Anahtar olarak `id(operand)` kullanılır: operand sözlükleri strateji
        # tanımının parçasıdır ve çalışma boyunca yaşar (id'leri sabit).
        # Önceden her çağrıda `json.dumps` ile anahtar üretiliyordu; bu tek
        # başına 250k mumluk backtest'te ~35 saniye harcıyordu.
        key = (n, id(operand))
        cached = memo.get(key)
        if cached is not None:
            return cached
    series = _resolve_operand_uncached(operand, data, cache, n)
    if memo is not None and key is not None:
        memo[key] = series
    return series


def _resolve_operand_uncached(
    operand: Dict[str, Any], data: Dict[str, List[float]], cache: IndicatorCache, n: int
) -> List[Any]:
    kind = operand.get("type")
    if kind == "constant":
        return [operand.get("value")] * n
    if kind == "price":
        field = operand.get("field", "close")
        if field == "hl2":
            return [(data["high"][i] + data["low"][i]) / 2 for i in range(n)]
        if field == "hlc3":
            return [
                (data["high"][i] + data["low"][i] + data["close"][i]) / 3
                for i in range(n)
            ]
        if field == "ohlc4":
            return [
                (data["open"][i] + data["high"][i] + data["low"][i] + data["close"][i]) / 4
                for i in range(n)
            ]
        if field not in data:
            raise StrategyValidationError(f"Geçersiz fiyat alanı: {field}")
        return list(data[field])
    if kind == "volume":
        field = operand.get("field", "volume_coin")
        if field not in data:
            raise StrategyValidationError(f"Geçersiz hacim alanı: {field}")
        return list(data[field])
    if kind == "indicator":
        return cache.compute(
            operand.get("id", ""), operand.get("params") or {}, operand.get("output", "value")
        )
    if kind == "offset":
        inner = _resolve_operand(operand.get("operand") or {}, data, cache)
        shift = int(operand.get("shift", 1))
        return [None] * shift + inner[:-shift] if shift > 0 else inner
    if kind == "math":
        left = _resolve_operand(operand.get("left") or {}, data, cache)
        right = _resolve_operand(operand.get("right") or {}, data, cache)
        op = operand.get("op", "sub")
        out: List[Any] = []
        for i in range(n):
            a, b = _value(left, i), _value(right, i)
            if a is None or b is None:
                out.append(None)
                continue
            if op == "add":
                out.append(a + b)
            elif op == "sub":
                out.append(a - b)
            elif op == "mul":
                out.append(a * b)
            elif op == "div":
                out.append(None if b == 0 else a / b)
            elif op == "pct_diff":
                out.append(None if b == 0 else (a - b) / b * 100)
            else:
                raise StrategyValidationError(f"Geçersiz matematik operatörü: {op}")
        return out
    raise StrategyValidationError(f"Geçersiz operand türü: {kind}")


def _compare(op: str, a: Optional[float], b: Optional[float]) -> Optional[bool]:
    if a is None or b is None:
        return None
    if op == "gt":
        return a > b
    if op == "gte":
        return a >= b
    if op == "lt":
        return a < b
    if op == "lte":
        return a <= b
    if op == "eq":
        return a == b
    if op == "neq":
        return a != b
    return None


def _describe_operand(operand: Dict[str, Any]) -> str:
    kind = operand.get("type")
    if kind == "constant":
        return str(operand.get("value"))
    if kind == "price":
        return str(operand.get("field", "close"))
    if kind == "volume":
        return str(operand.get("field", "volume_coin"))
    if kind == "indicator":
        params = operand.get("params") or {}
        p = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"{operand.get('id')}({p})[{operand.get('output', 'value')}]"
    if kind == "offset":
        return f"{_describe_operand(operand.get('operand') or {})} ({operand.get('shift', 1)} mum önce)"
    if kind == "math":
        return (
            f"({_describe_operand(operand.get('left') or {})} {operand.get('op')} "
            f"{_describe_operand(operand.get('right') or {})})"
        )
    return str(kind)


class CompiledStrategy:
    def __init__(self, definition: Dict[str, Any], strategy_id: str, version: int = 1):
        self.definition = definition
        self.id = strategy_id
        self.name = definition.get("name", strategy_id)
        self.version = version
        self.warmup = warmup_of(definition)

    # ---------- signals ----------
    def evaluate(self, data: Dict[str, List[float]]) -> Dict[str, Any]:
        n = len(data.get("close") or [])
        idx = n - 2
        return self.evaluate_at(data, IndicatorCache(data), idx)

    def evaluate_at(
        self,
        data: Dict[str, List[float]],
        cache: "IndicatorCache",
        idx: int,
        detail: bool = True,
    ) -> Dict[str, Any]:
        """Sinyali değerlendirir.

        `detail=False` iken koşul açıklamaları (okunur metin) üretilmez. Backtest
        binlerce mumu tararken bu metinler hiçbir yerde kullanılmıyor; üretmek
        tek başına ölçülen sürenin ~%10'unu yiyordu.
        """
        n = len(data.get("close") or [])
        result: Dict[str, Any] = {
            "strategy_id": self.id,
            "version": self.version,
            "candle_index": idx,
            "candle_time": (data.get("opendate") or [None] * n)[idx] if 0 <= idx < n else None,
            "buy": False,
            "sell": False,
            "buy_detail": None,
            "sell_detail": None,
            "warmup_ok": n >= self.warmup and idx >= 0,
        }
        if not result["warmup_ok"]:
            return result
        buy_def = self.definition.get("buy") or {}
        sell_def = self.definition.get("sell") or {}
        if buy_def.get("conditions"):
            ok, info = self._eval_node(buy_def, data, cache, idx, detail)
            result["buy"] = bool(ok)
            result["buy_detail"] = info
        if sell_def.get("conditions"):
            ok, info = self._eval_node(sell_def, data, cache, idx, detail)
            result["sell"] = bool(ok)
            result["sell_detail"] = info
        return result

    def buy_signal(self, data: Dict[str, List[float]]) -> bool:
        return self.evaluate(data)["buy"]

    def sell_signal(self, data: Dict[str, List[float]]) -> bool:
        return self.evaluate(data)["sell"]

    # ---------- evaluation ----------
    def _eval_node(
        self, node: Dict[str, Any], data, cache: IndicatorCache, idx: int, detail: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if node.get("type") == "within_last_n":
            return self._eval_within(node, data, cache, idx, detail)
        conditions = node.get("conditions") or []
        logic = (node.get("logic") or "AND").upper()
        results: List[bool] = []
        details: List[Dict[str, Any]] = []
        # `detail=False` (backtest) modunda kısa devre yapılır: AND'de ilk false,
        # OR'de ilk true sonucu belirler; kalan koşulları hesaplamak gereksizdir.
        # İndikatörler saf (yan etkisiz) olduğundan sonuç değişmez.
        short_circuit = not detail and logic in {"AND", "OR"}
        for cond in conditions:
            if cond.get("conditions") or cond.get("type") == "within_last_n":
                ok, info = self._eval_node(cond, data, cache, idx, detail)
            else:
                ok, info = self._eval_condition(cond, data, cache, idx, detail)
            results.append(bool(ok))
            if detail:
                details.append(info)
            elif short_circuit:
                if logic == "AND" and not ok:
                    break
                if logic == "OR" and ok:
                    break
        if not results:
            return False, ({"logic": logic, "conditions": [], "result": False} if detail else None)
        if logic == "OR":
            final = any(results)
        elif logic == "NOT":
            final = not any(results)
        else:
            final = all(results)
        return final, ({"logic": logic, "conditions": details, "result": final} if detail else None)

    def _eval_within(
        self, node: Dict[str, Any], data, cache: IndicatorCache, idx: int, detail: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        lookback = max(1, int(node.get("lookback", 3)))
        inner = node.get("condition") or {}
        hits = []
        for offset in range(lookback):
            i = idx - offset
            if i < 0:
                hits.append(False)
                continue
            if inner.get("conditions") or inner.get("type") == "within_last_n":
                ok, _ = self._eval_node(inner, data, cache, i, False)
            else:
                ok, _ = self._eval_condition(inner, data, cache, i, False)
            hits.append(bool(ok))
        final = any(hits)
        return final, (
            {"type": "within_last_n", "lookback": lookback, "hits": hits, "result": final}
            if detail else None
        )

    def _eval_condition(
        self, cond: Dict[str, Any], data, cache: IndicatorCache, idx: int, detail: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        left_op = cond.get("left") or {}
        right_op = cond.get("right") or {}
        op = cond.get("op", "gt")
        left = _resolve_operand(left_op, data, cache)
        right = _resolve_operand(right_op, data, cache)
        a, b = _value(left, idx), _value(right, idx)
        result: Optional[bool] = None

        # Önceki mum değerleri yalnızca bunlara ihtiyaç duyan operatörlerde
        # hesaplanır (her koşulda hesaplamak ölçülen sürenin ~%15'iydi).
        a_prev = b_prev = None
        if op in {"crosses_above", "crosses_below", "rising", "falling"}:
            a_prev, b_prev = _value(left, idx - 1), _value(right, idx - 1)

        if op in {"gt", "gte", "lt", "lte", "eq", "neq"}:
            result = _compare(op, a, b)
        elif op == "crosses_above":
            if None not in (a, b, a_prev, b_prev):
                result = a > b and a_prev <= b_prev
            else:
                result = False
        elif op == "crosses_below":
            if None not in (a, b, a_prev, b_prev):
                result = a < b and a_prev >= b_prev
            else:
                result = False
        elif op in {"rising", "falling"}:
            if None not in (a, a_prev):
                result = a > a_prev if op == "rising" else a < a_prev
            else:
                result = False
        elif op in {"rising_for_n", "falling_for_n"}:
            n = max(2, int(cond.get("lookback", 3)))
            vals = [_value(left, idx - i) for i in range(n)]
            if any(v is None for v in vals):
                result = False
            elif op == "rising_for_n":
                result = all(vals[i] > vals[i + 1] for i in range(n - 1))
            else:
                result = all(vals[i] < vals[i + 1] for i in range(n - 1))
        elif op in {"between", "outside"}:
            low = cond.get("min")
            high = cond.get("max")
            if a is None or low is None or high is None:
                result = False
            else:
                inside = float(low) <= a <= float(high)
                result = inside if op == "between" else not inside
        elif op in {"pct_change_gt", "pct_change_lt"}:
            lookback = max(1, int(cond.get("lookback", 1)))
            past = _value(left, idx - lookback)
            if a is None or past in (None, 0) or b is None:
                result = False
            else:
                change = (a - past) / past * 100
                result = change > b if op == "pct_change_gt" else change < b
        else:
            raise StrategyValidationError(f"Geçersiz operatör: {op}")

        if not detail:
            return bool(result), None
        return bool(result), {
            "left": _describe_operand(left_op),
            "op": OPERATORS.get(op, op),
            "right": (
                f"[{cond.get('min')}, {cond.get('max')}]"
                if op in {"between", "outside"}
                else _describe_operand(right_op)
            ),
            "left_value": a,
            "right_value": b,
            "result": bool(result),
        }


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------

def _validate_operand(operand: Dict[str, Any], errors: List[str], path: str) -> None:
    kind = operand.get("type")
    if kind == "indicator":
        name = operand.get("id")
        spec = INDICATORS.get(name or "")
        if not spec:
            errors.append(f"{path}: bilinmeyen indikatör '{name}'")
            return
        output = operand.get("output", "value")
        if output not in spec["outputs"]:
            errors.append(f"{path}: '{name}' için geçersiz çıktı '{output}'")
        params = operand.get("params") or {}
        for p in spec["params"]:
            value = params.get(p["name"], p["default"])
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                errors.append(f"{path}: '{p['label']}' sayı olmalı")
                continue
            if numeric < p["min"] or numeric > p["max"]:
                errors.append(
                    f"{path}: '{p['label']}' {p['min']} ile {p['max']} arasında olmalı"
                )
    elif kind == "constant":
        if not isinstance(operand.get("value"), (int, float)):
            errors.append(f"{path}: sabit değer sayı olmalı")
    elif kind == "price":
        if operand.get("field", "close") not in {
            "open", "high", "low", "close", "hl2", "hlc3", "ohlc4"
        }:
            errors.append(f"{path}: geçersiz fiyat alanı")
    elif kind == "volume":
        if operand.get("field", "volume_coin") not in {"volume_coin", "volume_usdt"}:
            errors.append(f"{path}: geçersiz hacim alanı")
    elif kind == "offset":
        _validate_operand(operand.get("operand") or {}, errors, path)
        if int(operand.get("shift", 1)) < 1:
            errors.append(f"{path}: offset en az 1 olmalı")
    elif kind == "math":
        _validate_operand(operand.get("left") or {}, errors, path)
        _validate_operand(operand.get("right") or {}, errors, path)
    else:
        errors.append(f"{path}: geçersiz operand türü '{kind}'")


def _validate_node(node: Dict[str, Any], errors: List[str], path: str) -> None:
    if node.get("type") == "within_last_n":
        if int(node.get("lookback", 3)) < 1:
            errors.append(f"{path}: lookback en az 1 olmalı")
        _validate_node(node.get("condition") or {}, errors, path)
        return
    conditions = node.get("conditions") or []
    logic = (node.get("logic") or "AND").upper()
    if logic not in {"AND", "OR", "NOT"}:
        errors.append(f"{path}: geçersiz mantık '{logic}'")
    for i, cond in enumerate(conditions):
        if cond.get("conditions") or cond.get("type") == "within_last_n":
            _validate_node(cond, errors, f"{path}.grup{i + 1}")
            continue
        op = cond.get("op")
        if op not in OPERATORS:
            errors.append(f"{path}.koşul{i + 1}: geçersiz operatör '{op}'")
        _validate_operand(cond.get("left") or {}, errors, f"{path}.koşul{i + 1}.sol")
        if op in {"between", "outside"}:
            if cond.get("min") is None or cond.get("max") is None:
                errors.append(f"{path}.koşul{i + 1}: min ve max gerekli")
            elif float(cond["min"]) >= float(cond["max"]):
                errors.append(f"{path}.koşul{i + 1}: min, max'tan küçük olmalı")
        else:
            _validate_operand(cond.get("right") or {}, errors, f"{path}.koşul{i + 1}.sağ")

    # Basit çelişki kontrolü (aynı operatör, AND grubunda imkansız aralık)
    if logic == "AND":
        seen: Dict[str, List[str]] = {}
        for cond in conditions:
            left = cond.get("left") or {}
            right = cond.get("right") or {}
            if left.get("type") == "indicator" and right.get("type") == "constant":
                key = _describe_operand(left)
                seen.setdefault(key, []).append(f"{cond.get('op')}:{right.get('value')}")
        for key, items in seen.items():
            if any(x.startswith("lt:") for x in items) and any(x.startswith("gt:") for x in items):
                lt_val = float(next(x for x in items if x.startswith("lt:")).split(":")[1])
                gt_val = float(next(x for x in items if x.startswith("gt:")).split(":")[1])
                if gt_val >= lt_val:
                    errors.append(f"{key} için çelişkili koşullar: > {gt_val} ve < {lt_val}")


def _validate_wrapper(definition: Dict[str, Any]) -> List[str]:
    """Hazır motordan türetilmiş tanımı doğrular."""
    from app.config import settings
    from app.strategies.builtin import builtin_names

    name = definition.get("builtin")
    if name not in builtin_names(include_ai=settings.AI_ENABLED):
        return [f"Bilinmeyen hazır strateji: {name}"]
    return []


def validate_definition(definition: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if definition.get("builtin"):
        if not definition.get("name"):
            errors.append("Strateji adı gerekli")
        errors.extend(_validate_wrapper(definition))
        return errors
    if not definition.get("name"):
        errors.append("Strateji adı gerekli")
    buy = definition.get("buy") or {}
    sell = definition.get("sell") or {}
    if not (buy.get("conditions") or []):
        errors.append("En az bir alım koşulu gerekli")
    has_sell = bool(sell.get("conditions") or [])
    if not has_sell and not definition.get("inherit_sell", True):
        errors.append("Satım koşulu gerekli")
    if buy.get("conditions"):
        _validate_node(buy, errors, "alım")
    if has_sell:
        _validate_node(sell, errors, "satım")
    if definition.get("version") is not None and not isinstance(definition["version"], int):
        errors.append("Sürüm tam sayı olmalı")
    return errors


def compile_strategy(definition: Dict[str, Any], strategy_id: str, version: int = 1) -> CompiledStrategy:
    errors = validate_definition(definition)
    if errors:
        raise StrategyValidationError("; ".join(errors))
    return CompiledStrategy(definition, strategy_id, version)
