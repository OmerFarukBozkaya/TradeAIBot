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
    from sklearn.ensemble import (  # type: ignore
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
    )

    SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover - yedek yol
    HistGradientBoostingClassifier = None  # type: ignore
    HistGradientBoostingRegressor = None  # type: ignore
    SKLEARN_AVAILABLE = False

from app.ai.nn import MLP, NumpyLogistic


class ConstantModel:
    """Tek sınıflı eğitimde olasılık döndüren basit model."""

    def __init__(self, probability: float):
        self.probability = float(probability)
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        p = np.full((len(X), 2), 1.0 - self.probability, dtype=float)
        p[:, 1] = self.probability
        return p


class AveragedModel:
    """Aynı mimariyle farklı tohumlardan eğitilmiş modellerin ortalaması.

    Tek bir modelin şanslı/şanssız ağırlık seçimine bağlı kalmamak için
    olasılıklar ortalanır. Bu, ek veri gerektirmeyen ve aşırı öğrenmeyi
    artırmayan (tersine azaltan) bir topluluk yöntemidir.
    """

    def __init__(self, models: Optional[list] = None):
        self.models = list(models or [])
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.models:
            raise RuntimeError("Topluluk boş")
        probs = [np.asarray(m.predict_proba(X), dtype=float) for m in self.models]
        return np.mean(np.stack(probs, axis=0), axis=0)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.predict_proba(X), axis=1)

    def __len__(self) -> int:
        return len(self.models)


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


def _gbm(spec: Dict[str, Any], output: str, n_classes: int, random_state: int) -> Any:
    if not SKLEARN_AVAILABLE:
        return None
    # Docker/CPU kotası altında hızlı kalsın diye iterasyon ve bin sayısı sınırlı.
    iters = int(spec.get("epochs") or 220)
    iters = max(30, min(iters, 200))
    if output == "regression":
        return HistGradientBoostingRegressor(
            max_iter=iters,
            learning_rate=0.06,
            max_leaf_nodes=31,
            min_samples_leaf=max(20, int(spec.get("batch_size") or 256) // 8),
            l2_regularization=max(0.1, float(spec.get("l2") or 0.0) * 100),
            max_bins=128,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=max(5, min(int(spec.get("patience") or 15), 20)),
            random_state=random_state,
        )
    return HistGradientBoostingClassifier(
        max_iter=iters,
        learning_rate=0.06,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=1.0,
        class_weight="balanced",
        max_bins=128,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=max(5, min(int(spec.get("patience") or 15), 20)),
        random_state=random_state,
    )


def fit_model(
    spec: Dict[str, Any],
    output: str,
    X: np.ndarray,
    y: np.ndarray,
    sample_weight: Optional[np.ndarray] = None,
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
    sample_weight_val: Optional[np.ndarray] = None,
    n_classes: int = 2,
    random_state: int = 42,
    init_model: Any = None,
) -> Any:
    """Mimari tanımına göre tek bir model eğitir.

    ``output``: ``binary`` | ``multiclass`` | ``regression``.
    """
    y = np.asarray(y, dtype=int) if output != "regression" else np.asarray(y, dtype=float)
    engine = str(spec.get("engine") or "mlp")
    if output == "binary" and len(np.unique(y)) < 2:
        return ConstantModel(float(np.mean(y)) if len(y) else 0.5)

    if engine == "gbm" and SKLEARN_AVAILABLE:
        model = _gbm(spec, output, n_classes, random_state)
        if model is None:
            engine = "mlp"
        else:
            if output == "regression":
                model.fit(X, y, sample_weight=sample_weight)
            else:
                model.fit(X, y, sample_weight=sample_weight)
            return model

    # GBM sıcak başlangıcı desteklemez; bu durumda model sıfırdan eğitilir.
    if engine == "gbm":
        init_model = None

    model = MLP(
        hidden_layers=spec.get("hidden_layers") or (64, 32),
        activation=str(spec.get("activation") or "relu"),
        dropout=float(spec.get("dropout") or 0.0),
        learning_rate=float(spec.get("learning_rate") or 0.003),
        epochs=int(spec.get("epochs") or 120),
        batch_size=int(spec.get("batch_size") or 256),
        l2=float(spec.get("l2") or 0.0),
        patience=int(spec.get("patience") or 15),
        min_delta=float(spec.get("es_min_delta") or 1e-4),
        grad_clip=float(spec.get("grad_clip") or 5.0),
        lr_decay=bool(spec.get("lr_decay", True)),
        output=output,
        n_classes=n_classes,
        random_state=random_state,
    )
    model.fit(
        X,
        y,
        sample_weight=sample_weight,
        X_val=X_val,
        y_val=y_val,
        sample_weight_val=sample_weight_val,
        init_model=init_model,
    )
    return model


class SequenceEnsemble:
    """Aynı mimariyle farklı tohumlardan eğitilmiş sıra modellerinin ortalaması."""

    def __init__(self, models: Optional[list] = None):
        self.models = list(models or [])
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.models:
            raise RuntimeError("Topluluk boş")
        probs = [np.asarray(m.predict_proba(X), dtype=np.float64) for m in self.models]
        return np.mean(np.stack(probs, axis=0), axis=0)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X) >= 0.5).astype(int)

    def __len__(self) -> int:
        return len(self.models)


def build_sequence_model(
    spec: Dict[str, Any],
    input_size: int,
    *,
    seed: int = 42,
    init_model: Any = None,
) -> Any:
    """Mimari tanımına göre LSTM veya Transformer kurar (eğitmez)."""
    engine = str(spec.get("engine") or "lstm")
    # LSTM küçük batch'te hızlı, Transformer büyük batch'te (BLAS) hızlı.
    seq_batch = int(spec.get("seq_batch") or 0)
    if seq_batch <= 0:
        seq_batch = 256 if engine == "transformer" else 64
    common = dict(
        dropout=float(spec.get("dropout") or 0.1),
        learning_rate=float(spec.get("learning_rate") or 0.003),
        epochs=int(spec.get("epochs") or 40),
        batch_size=seq_batch,
        l2=float(spec.get("l2") or 1e-4),
        patience=int(spec.get("patience") or 10),
        min_delta=float(spec.get("es_min_delta") or 1e-4),
        grad_clip=float(spec.get("grad_clip") or 1.0),
        lr_decay=bool(spec.get("lr_decay", True)),
        random_state=int(seed),
    )
    if engine == "transformer":
        from app.ai.transformer import TransformerClassifier

        model = TransformerClassifier(
            input_size,
            window=int(spec.get("seq_window") or 24),
            dim=int(spec.get("trans_dim") or 28),
            heads=int(spec.get("trans_heads") or 2),
            layers=int(spec.get("trans_layers") or 1),
            ffn_activation=str(spec.get("ffn_activation") or "relu"),
            **common,
        )
    else:
        from app.ai.lstm import LSTMClassifier

        model = LSTMClassifier(input_size, hidden=int(spec.get("lstm_hidden") or 28), **common)
    _ = init_model  # sıcak başlangıç fit içinde modele verilir
    return model


def predict_sequence(
    bundle: Dict[str, Any],
    seq_data: Any,
    positions: Optional[np.ndarray] = None,
    *,
    chunk: int = 2048,
) -> tuple:
    """Sıra modeli için AL/SAT olasılıklarını (tam seri üzerinden) üretir."""
    model = bundle.get("sequence_model")
    if model is None:
        raise ValueError("Pakette sıra modeli yok")
    pos = np.arange(seq_data.n) if positions is None else np.asarray(positions, dtype=int)
    buy = np.zeros(len(pos), dtype=float)
    sell = np.zeros(len(pos), dtype=float)
    for start, x_chunk in seq_data.windows_batched(pos, batch_size=chunk):
        proba = np.asarray(model.predict_proba(x_chunk), dtype=float)
        take = len(x_chunk)
        buy[start : start + take] = proba[:, 0]
        sell[start : start + take] = proba[:, 1]
    return buy, sell


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


def predict_signals(bundle: Dict[str, Any], X: np.ndarray) -> tuple:
    """Paketten AL ve SAT olasılıklarını üretir (motor bağımsız)."""
    mode = str(bundle.get("output_mode") or "dual_binary")
    if X is None or len(X) == 0:
        empty = np.array([], dtype=float)
        return empty, empty
    if mode == "ternary":
        proba = np.asarray(bundle["action_model"].predict_proba(X), dtype=float)
        if proba.shape[1] < 3:
            zeros = np.zeros(len(X))
            return zeros, zeros
        return proba[:, 1], proba[:, 2]
    if mode == "regression":
        pred = np.asarray(bundle["return_model"].predict(X), dtype=float).reshape(-1)
        scale = float(bundle.get("prob_scale") or 0.01)
        scale = scale if scale > 1e-9 else 0.01
        buy = 1.0 / (1.0 + np.exp(-np.clip(pred / scale, -30, 30)))
        sell = 1.0 / (1.0 + np.exp(np.clip(pred / scale, -30, 30)))
        return buy, sell
    return (
        predict_positive(bundle["buy_model"], X),
        predict_positive(bundle["sell_model"], X),
    )


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
        "precision": round(precision, 4),        "recall": round(recall, 4),
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
    grid = np.arange(0.45, 0.951, 0.05) if grid is None else np.asarray(grid)
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
    trend_ok: Optional[np.ndarray] = None,
    trailing_stop: float = 0.0,
    min_hold: int = 0,
    cooldown: int = 0,
    exit_on_regime: bool = False,
) -> Dict[str, Any]:
    """Sadece verilen zaman aralığında, sırayla sanal işlem yapar.

    Giriş/çıkış kararı yalnızca o anki kapanmış mum ve model olasılıklarıyla
    verilir. Stop/hedef için sonraki mumun high/low'u kullanılır; aynı mumda
    ikisi de vurulursa kötümser varsayımla stop önce sayılır.

    ``trend_ok`` verilirse yalnızca trendin uygun olduğu mumlarda alım yapılır
    (genel trende göre işlem). ``trailing_stop`` > 0 ise en yüksek fiyattan bu
    kadar geri çekilmede çıkılır (trend kârını korur).
    """
    indices = np.asarray(indices, dtype=int)
    if len(indices) == 0:
        return {"trades": [], "equity": [], "metrics": {}}
    start_i = int(indices[0])
    end_i = int(indices[-1])
    cash = 1.0
    position: Optional[Dict[str, Any]] = None
    last_exit = -10**9
    equity_points = []
    trades = []
    equity_curve = []

    for i in range(start_i, min(end_i + 1, len(close))):
        price = float(close[i])
        if position is None:
            gate = True if trend_ok is None else bool(trend_ok[i])
            ready = (i - last_exit) >= int(cooldown)
            if buy_prob[i] >= buy_threshold and sell_prob[i] < sell_threshold and gate and ready:
                entry = price * (1 + slippage)
                position = {
                    "entry": entry,
                    "entry_idx": i,
                    "entry_time": i,
                    "qty": cash / (entry * (1 + fee)),
                    "highest": price,
                    "equity_before": cash,
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
                elif trailing_stop > 0 and float(low[i]) <= float(position["highest"]) * (1 - trailing_stop):
                    exit_price = float(position["highest"]) * (1 - trailing_stop)
                    reason = "trailing"
                elif float(high[i]) >= float(position["entry"]) * (1 + target_move):
                    exit_price = float(position["entry"]) * (1 + target_move)
                    reason = "take-profit"
                elif exit_on_regime and trend_ok is not None and not bool(trend_ok[i]):
                    exit_price = price * (1 - slippage)
                    reason = "regime"
                elif sell_prob[i] >= sell_threshold and (i - int(position["entry_idx"])) >= int(min_hold):
                    exit_price = price * (1 - slippage)
                    reason = "signal"
                elif i - int(position["entry_idx"]) >= horizon:
                    exit_price = price * (1 - slippage)
                    reason = "horizon"
            if exit_price is not None:
                gross = float(position["qty"]) * exit_price
                cash = gross * (1 - fee)
                base = float(position.get("equity_before") or 1.0)
                ret = (cash / base - 1.0) * 100.0
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
                last_exit = i
        equity_curve.append(cash + (float(position["qty"]) * price if position else 0.0))
        equity_points.append({"i": i, "value": round(cash + (float(position["qty"]) * price if position else 0.0), 6)})

    if position is not None:
        i = min(end_i, len(close) - 1)
        exit_price = float(close[i]) * (1 - slippage)
        cash = float(position["qty"]) * exit_price * (1 - fee)
        base = float(position.get("equity_before") or 1.0)
        ret = (cash / base - 1.0) * 100.0
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
