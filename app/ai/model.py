"""Model sarmalayıcıları ve metrikler.

Üretimde ``scikit-learn`` (HistGradientBoosting) kullanılır. AI profili
kurulmamış bir makinede test/deneme yapılabilsin diye küçük bir NumPy lojistik
regresyon yedeği vardır. Yedek model, NaN içeren satırları eğitim medyanıyla
doldurur; ağaç modeli NaN'ı doğrudan tolere eder.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:  # AI profili
    from sklearn.ensemble import HistGradientBoostingClassifier  # type: ignore

    SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover - yedek yol
    HistGradientBoostingClassifier = None  # type: ignore
    SKLEARN_AVAILABLE = False


class ConstantModel:
    """Tek sınıflı eğitimde olasılık döndüren basit model."""

    def __init__(self, probability: float):
        self.probability = float(probability)
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        p = np.full((len(X), 2), 1.0 - self.probability, dtype=float)
        p[:, 1] = self.probability
        return p


class NumpyLogistic:
    """Küçük, bağımlılıksız lojistik regresyon yedeği."""

    def __init__(self, l2: float = 1.0, iterations: int = 250, lr: float = 0.15):
        self.l2 = float(l2)
        self.iterations = int(iterations)
        self.lr = float(lr)
        self.mean_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None
        self.coef_: Optional[np.ndarray] = None
        self.classes_ = np.array([0, 1])

    def _prepare(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        if self.mean_ is None:
            med = np.nanmedian(X, axis=0)
            med = np.where(np.isfinite(med), med, 0.0)
            X = np.where(np.isfinite(X), X, med)
            self.mean_ = X.mean(axis=0)
            scale = X.std(axis=0)
            self.scale_ = np.where(scale > 1e-9, scale, 1.0)
        else:
            X = np.where(np.isfinite(X), X, self.mean_)
        return (X - self.mean_) / self.scale_

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "NumpyLogistic":
        Xs = self._prepare(X)
        Xb = np.column_stack([np.ones(len(Xs)), Xs])
        y = np.asarray(y, dtype=float)
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
        w = w / w.sum()
        coef = np.zeros(Xb.shape[1])
        for _ in range(self.iterations):
            z = np.clip(Xb @ coef, -30, 30)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = Xb.T @ (w * (p - y))
            grad[1:] += self.l2 * coef[1:] / len(y)
            coef -= self.lr * grad
        self.coef_ = coef
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("Model eğitilmemiş")
        Xs = self._prepare(np.asarray(X, dtype=float))
        Xb = np.column_stack([np.ones(len(Xs)), Xs])
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ self.coef_, -30, 30)))
        return np.column_stack([1 - p, p])


def fit_classifier(
    X: np.ndarray,
    y: np.ndarray,
    sample_weight: Optional[np.ndarray] = None,
    random_state: int = 42,
) -> Any:
    """İkili sınıflandırıcı eğitir; sınıf dengesizliğini telafi eder."""
    y = np.asarray(y, dtype=int)
    if len(np.unique(y)) < 2:
        return ConstantModel(float(np.mean(y)) if len(y) else 0.5)
    if SKLEARN_AVAILABLE:
        model = HistGradientBoostingClassifier(
            max_iter=220,
            learning_rate=0.06,
            max_leaf_nodes=31,
            min_samples_leaf=40,
            l2_regularization=1.0,
            class_weight="balanced",
            random_state=random_state,
        )
        model.fit(X, y, sample_weight=sample_weight)
        return model
    return NumpyLogistic().fit(X, y, sample_weight=sample_weight)


def predict_positive(model: Any, X: np.ndarray) -> np.ndarray:
    """Pozitif sınıf olasılığını güvenli biçimde döndürür."""
    if X is None or len(X) == 0:
        return np.array([], dtype=float)
    proba = model.predict_proba(X)
    if proba.ndim == 1:
        return np.asarray(proba, dtype=float)
    if proba.shape[1] == 1:
        return np.asarray(proba[:, 0], dtype=float)
    return np.asarray(proba[:, 1], dtype=float)


def classification_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> Dict[str, Any]:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    pred = (p >= float(threshold)).astype(int)
    tp = int(np.sum((pred == 1) & (y == 1)))
    fp = int(np.sum((pred == 1) & (y == 0)))
    fn = int(np.sum((pred == 0) & (y == 1)))
    tn = int(np.sum((pred == 0) & (y == 0)))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "threshold": round(float(threshold), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "support": int(len(y)),
        "positive_rate": round(float(np.mean(y)) if len(y) else 0.0, 4),
    }


def roc_auc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    """Sıra tabanlı AUC (harici bağımlılık yok)."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(p)
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    # Eşit olasılıklarda ortalama sıra
    sorted_p = p[order]
    start = 0
    for i in range(1, len(sorted_p) + 1):
        if i == len(sorted_p) or sorted_p[i] != sorted_p[start]:
            if i - start > 1:
                ranks[order[start:i]] = np.mean(np.arange(start + 1, i + 1))
            start = i
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def choose_threshold(
    y: np.ndarray,
    p: np.ndarray,
    min_precision: float = 0.35,
    grid: Optional[np.ndarray] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Doğrulama kümesinde F1'i büyüten eşiği seçer.

    Düşük kesinlikli eşikler cezalandırılır; böylece model "her muma al" demez.
    """
    grid = np.arange(0.35, 0.951, 0.05) if grid is None else np.asarray(grid)
    best_thr = 0.6
    best_metrics = classification_metrics(y, p, best_thr)
    best_score = -1.0
    for thr in grid:
        m = classification_metrics(y, p, float(thr))
        penalty = 1.0 if m["precision"] >= min_precision else m["precision"] / max(min_precision, 1e-9)
        score = m["f1"] * penalty + min(m["precision"], 0.95) * 0.05
        if score > best_score:
            best_score = score
            best_thr = float(thr)
            best_metrics = m
    return round(best_thr, 4), best_metrics


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = np.divide(equity, peak, out=np.ones_like(equity), where=peak > 0) - 1.0
    return float(dd.min() * 100.0)


def simulate_trades(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    buy_prob: np.ndarray,
    sell_prob: np.ndarray,
    indices: np.ndarray,
    buy_threshold: float,
    sell_threshold: float,
    horizon: int,
    fee: float = 0.001,
    slippage: float = 0.0005,
    stop_move: float = 0.01,
    target_move: float = 0.02,
    trade_limit: int = 200,
) -> Dict[str, Any]:
    """Sadece verilen zaman aralığında, sırayla sanal işlem yapar.

    Giriş/çıkış kararı yalnızca o anki kapanmış mum ve model olasılıklarıyla
    verilir. Stop/hedef için sonraki mumun high/low'u kullanılır; aynı mumda
    ikisi de vurulursa kötümser varsayımla stop önce sayılır.
    """
    indices = np.asarray(indices, dtype=int)
    if len(indices) == 0:
        return {"trades": [], "equity": [], "metrics": {}}
    start_i = int(indices[0])
    end_i = int(indices[-1])
    cash = 1.0
    position: Optional[Dict[str, Any]] = None
    equity_points = []
    trades = []
    equity_curve = []

    for i in range(start_i, min(end_i + 1, len(close))):
        price = float(close[i])
        if position is None:
            if buy_prob[i] >= buy_threshold and sell_prob[i] < sell_threshold:
                entry = price * (1 + slippage)
                position = {
                    "entry": entry,
                    "entry_idx": i,
                    "entry_time": i,
                    "qty": cash / (entry * (1 + fee)),
                    "highest": price,
                }
                cash = 0.0
        else:
            position["highest"] = max(float(position["highest"]), float(high[i]))
            exit_price = None
            reason = None
            if i > int(position["entry_idx"]):
                if float(low[i]) <= float(position["entry"]) * (1 - stop_move):
                    exit_price = float(position["entry"]) * (1 - stop_move)
                    reason = "stop"
                elif float(high[i]) >= float(position["entry"]) * (1 + target_move):
                    exit_price = float(position["entry"]) * (1 + target_move)
                    reason = "take-profit"
                elif sell_prob[i] >= sell_threshold:
                    exit_price = price * (1 - slippage)
                    reason = "signal"
                elif i - int(position["entry_idx"]) >= horizon:
                    exit_price = price * (1 - slippage)
                    reason = "horizon"
            if exit_price is not None:
                gross = float(position["qty"]) * exit_price
                cash = gross * (1 - fee)
                ret = (cash / 1.0 - 1.0) * 100.0
                trades.append(
                    {
                        "entry_idx": int(position["entry_idx"]),
                        "exit_idx": i,
                        "entry": float(position["entry"]),
                        "exit": float(exit_price),
                        "pnl_pct": round(ret, 3),
                        "candles": i - int(position["entry_idx"]),
                        "reason": reason,
                    }
                )
                position = None
        equity_curve.append(cash + (float(position["qty"]) * price if position else 0.0))
        equity_points.append({"i": i, "value": round(cash + (float(position["qty"]) * price if position else 0.0), 6)})

    if position is not None:
        i = min(end_i, len(close) - 1)
        exit_price = float(close[i]) * (1 - slippage)
        cash = float(position["qty"]) * exit_price * (1 - fee)
        ret = (cash / 1.0 - 1.0) * 100.0
        trades.append(
            {
                "entry_idx": int(position["entry_idx"]),
                "exit_idx": i,
                "entry": float(position["entry"]),
                "exit": exit_price,
                "pnl_pct": round(ret, 3),
                "candles": i - int(position["entry_idx"]),
                "reason": "end",
            }
        )
        equity_curve.append(cash)

    equity = np.asarray(equity_curve or [1.0], dtype=float)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    gross_win = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    total_return = (cash - 1.0) * 100.0
    buy_hold = (float(close[end_i]) / float(close[start_i]) - 1.0) * 100.0 if close[start_i] else 0.0
    metrics = {
        "trade_count": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "avg_trade_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 3) if trades else 0.0,
        "total_return_pct": round(total_return, 2),
        "buy_hold_pct": round(buy_hold, 2),
        "edge_pct": round(total_return - buy_hold, 2),
        "max_drawdown_pct": round(_max_drawdown(equity), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "avg_candles": round(sum(t["candles"] for t in trades) / len(trades), 1) if trades else 0.0,
    }
    return {
        "trades": trades[-max(1, int(trade_limit)):],
        "trade_total": len(trades),
        "equity": equity_points[-1000:],
        "metrics": metrics,
    }
