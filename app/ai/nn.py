"""Yapılandırılabilir NumPy sinir ağı (MLP).

Harici derin öğrenme kütüphanesi gerekmez; bu sayede eğitim hem Docker
imajını şişirmez hem de her ortamda aynı sonucu verir.

Özellikler:
- Seçilebilir gizli katmanlar, aktivasyon, dropout, L2, öğrenme oranı
- Adam optimizer, mini-batch eğitim
- Sınıf dengesizliği için örnek ağırlıkları
- Validation kaybına göre erken durdurma ve en iyi ağırlıkları geri yükleme
- Deterministik tohum → tekrar üretilebilir sonuç
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

ACTIVATIONS = ("relu", "leaky_relu", "tanh", "gelu", "sigmoid")


def _activation(name: str, x: np.ndarray) -> np.ndarray:
    if name == "relu":
        return np.maximum(x, 0.0)
    if name == "leaky_relu":
        return np.where(x > 0, x, 0.01 * x)
    if name == "tanh":
        return np.tanh(x)
    if name == "gelu":
        return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)))
    if name == "sigmoid":
        return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))
    return np.maximum(x, 0.0)


def _activation_grad(name: str, x: np.ndarray, out: np.ndarray) -> np.ndarray:
    if name == "relu":
        return (x > 0).astype(float)
    if name == "leaky_relu":
        return np.where(x > 0, 1.0, 0.01)
    if name == "tanh":
        return 1.0 - out ** 2
    if name == "gelu":
        # Yaklaşık türev; pratikte yeterince iyi.
        c = np.sqrt(2.0 / np.pi)
        inner = c * (x + 0.044715 * x ** 3)
        t = np.tanh(inner)
        return 0.5 * (1 + t) + 0.5 * x * (1 - t ** 2) * c * (1 + 3 * 0.044715 * x ** 2)
    if name == "sigmoid":
        return out * (1.0 - out)
    return (x > 0).astype(float)


class _Adam:
    def __init__(self, shape: Sequence[int], lr: float, beta1=0.9, beta2=0.999, eps=1e-8, dtype=np.float64):
        self.m = np.zeros(shape, dtype=dtype)
        self.v = np.zeros(shape, dtype=dtype)
        self.dtype = dtype
        self.lr = float(lr)
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.t = 0

    def step(self, param: np.ndarray, grad: np.ndarray) -> np.ndarray:
        self.t += 1
        g = grad.astype(self.dtype, copy=False)
        self.m = self.beta1 * self.m + (1 - self.beta1) * g
        self.v = self.beta2 * self.v + (1 - self.beta2) * g * g
        m_hat = self.m / (1 - self.beta1 ** self.t)
        v_hat = self.v / (1 - self.beta2 ** self.t)
        out = param - self.lr * m_hat / (np.sqrt(v_hat) + self.eps)
        return out.astype(param.dtype, copy=False)


class MLP:
    """Küçük, bağımsız çok katmanlı algılayıcı.

    ``output``:
    - ``binary``  → sigmoid, tek çıktı
    - ``multiclass`` → softmax, ``n_classes`` çıktı
    - ``regression`` → lineer, tek çıktı
    """

    def __init__(
        self,
        hidden_layers: Sequence[int] = (64, 32),
        activation: str = "relu",
        dropout: float = 0.1,
        learning_rate: float = 0.003,
        epochs: int = 120,
        batch_size: int = 256,
        l2: float = 5e-4,
        patience: int = 15,
        min_delta: float = 1e-4,
        grad_clip: float = 5.0,
        lr_decay: bool = True,
        output: str = "binary",
        n_classes: int = 2,
        random_state: int = 42,
    ):
        self.hidden_layers = [int(v) for v in hidden_layers if int(v) > 0]
        self.activation = activation if activation in ACTIVATIONS else "relu"
        self.dropout = float(max(0.0, min(dropout, 0.8)))
        self.learning_rate = float(max(1e-5, learning_rate))
        self.epochs = int(max(1, epochs))
        self.batch_size = int(max(8, batch_size))
        self.l2 = float(max(0.0, l2))
        self.patience = int(max(1, patience))
        # Erken durma eşiği: göreli iyileşme. 1e-4 → on binde bir iyileşme.
        self.min_delta = float(max(1e-9, min(min_delta, 0.5)))
        self.grad_clip = float(max(0.0, grad_clip))
        self.lr_decay = bool(lr_decay)
        self.output = output
        self.n_classes = int(n_classes)
        self.rng = np.random.default_rng(random_state)
        self.mean_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None
        self.y_mean_: float = 0.0
        self.y_scale_: float = 1.0
        self.weights_: List[np.ndarray] = []
        self.biases_: List[np.ndarray] = []
        self.history: List[Dict[str, float]] = []
        self.best_epoch = 0
        self.best_val_loss: Optional[float] = None
        self.stopped_early = False
        self.warm_started = False
        self.classes_ = np.arange(self.n_classes) if output == "multiclass" else np.array([0, 1])

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    def _standardize(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        X = np.where(np.isfinite(X), X, np.nan)
        if fit:
            med = np.nanmedian(X, axis=0)
            med = np.where(np.isfinite(med), med, 0.0)
            X = np.where(np.isfinite(X), X, med)
            self.mean_ = X.mean(axis=0)
            scale = X.std(axis=0)
            self.scale_ = np.where(scale > 1e-9, scale, 1.0)
        else:
            X = np.where(np.isfinite(X), X, self.mean_ if self.mean_ is not None else 0.0)
        return (X - self.mean_) / self.scale_

    def _init_params(self, n_in: int) -> None:
        dims = [n_in] + self.hidden_layers + [
            self.n_classes if self.output == "multiclass" else 1
        ]
        self.weights_ = []
        self.biases_ = []
        for i in range(len(dims) - 1):
            fan_in, fan_out = dims[i], dims[i + 1]
            limit = np.sqrt(6.0 / (fan_in + fan_out))
            self.weights_.append(self.rng.uniform(-limit, limit, size=(fan_in, fan_out)))
            self.biases_.append(np.zeros(fan_out))

    def _forward(self, X: np.ndarray, training: bool = False):
        acts = [X]
        pre = []
        h = X
        last = len(self.weights_) - 1
        for i, (w, b) in enumerate(zip(self.weights_, self.biases_)):
            z = h @ w + b
            pre.append(z)
            if i == last:
                if self.output == "binary":
                    out = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
                elif self.output == "multiclass":
                    zz = z - z.max(axis=1, keepdims=True)
                    e = np.exp(zz)
                    out = e / e.sum(axis=1, keepdims=True)
                else:
                    out = z
            else:
                a = _activation(self.activation, z)
                if training and self.dropout > 0:
                    mask = (self.rng.random(a.shape) >= self.dropout).astype(float)
                    a = a * mask / (1.0 - self.dropout)
                else:
                    mask = None
                out = a
                # mask bir sonraki adımda kullanılmaz; dropout ileri yönde uygulandı.
                _ = mask
            acts.append(out)
            h = out
        return acts, pre

    def _loss(self, y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
        eps = 1e-9
        if self.output == "binary":
            yv = np.asarray(y, dtype=float).reshape(-1)
            pv = p.reshape(-1)
            loss = -(yv * np.log(pv + eps) + (1 - yv) * np.log(1 - pv + eps))
        elif self.output == "multiclass":
            idx = np.asarray(y, dtype=int)
            loss = -np.log(np.clip(p[np.arange(len(idx)), idx], eps, 1.0))
        else:
            loss = 0.5 * (np.asarray(y, dtype=float).reshape(-1) - p.reshape(-1)) ** 2
        total_w = float(w.sum()) if len(w) else 1.0
        return float((loss * w).sum() / max(total_w, 1e-9))

    # ------------------------------------------------------------------
    # Eğitim
    # ------------------------------------------------------------------
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: Optional[np.ndarray] = None,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        sample_weight_val: Optional[np.ndarray] = None,
        init_model: Optional["MLP"] = None,
    ) -> "MLP":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y)
        w = (
            np.ones(len(X), dtype=float)
            if sample_weight is None
            else np.asarray(sample_weight, dtype=float)
        )
        w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
        Xs = self._standardize(X, fit=True)
        if self.output == "regression":
            yv = np.asarray(y, dtype=float)
            finite = yv[np.isfinite(yv)]
            self.y_mean_ = float(np.mean(finite)) if len(finite) else 0.0
            scale = float(np.std(finite)) if len(finite) else 1.0
            self.y_scale_ = scale if scale > 1e-9 else 1.0
            y = (yv - self.y_mean_) / self.y_scale_
        self._init_params(Xs.shape[1])

        # Önceki nesilden sıcak başlangıç: aynı şekle sahip ağırlıklar kopyalanır
        # ve model sıfırdan öğrenmek yerine kaldığı yerden ince ayar yapar.
        self.warm_started = False
        if init_model is not None and getattr(init_model, "weights_", None):
            same = (
                len(init_model.weights_) == len(self.weights_)
                and all(a.shape == b.shape for a, b in zip(init_model.weights_, self.weights_))
                and all(a.shape == b.shape for a, b in zip(init_model.biases_, self.biases_))
            )
            if same:
                self.weights_ = [np.array(w_, dtype=float, copy=True) for w_ in init_model.weights_]
                self.biases_ = [np.array(b_, dtype=float, copy=True) for b_ in init_model.biases_]
                # Özellik ölçeği de önceki nesilden devralınır; aksi halde aynı
                # girdi farklı ölçeklenip öğrenilen temsil bozulur.
                if (
                    getattr(init_model, "mean_", None) is not None
                    and init_model.mean_.shape == self.mean_.shape
                ):
                    self.mean_ = np.array(init_model.mean_, copy=True)
                    self.scale_ = np.array(init_model.scale_, copy=True)
                    Xs = self._standardize(X, fit=False)
                self.y_mean_ = float(getattr(init_model, "y_mean_", 0.0))
                self.y_scale_ = float(getattr(init_model, "y_scale_", 1.0)) or 1.0
                self.warm_started = True

        base_lr = self.learning_rate * (0.6 if getattr(self, "warm_started", False) else 1.0)
        optimizers = [_Adam(p.shape, base_lr) for p in self.weights_]
        opt_b = [_Adam(b.shape, base_lr) for b in self.biases_]
        min_lr = base_lr * 0.08
        warmup_epochs = max(1, int(self.epochs * 0.05)) if not self.warm_started else 0

        have_val = X_val is not None and y_val is not None and len(X_val) > 0
        if have_val:
            Xv = self._standardize(np.asarray(X_val, dtype=float), fit=False)
            yv = np.asarray(y_val)
            if self.output == "regression":
                yv = (np.asarray(y_val, dtype=float) - self.y_mean_) / self.y_scale_
            wv = (
                np.ones(len(Xv), dtype=float)
                if sample_weight_val is None
                else np.asarray(sample_weight_val, dtype=float)
            )
            wv = np.where(np.isfinite(wv) & (wv > 0), wv, 1.0)

        best_loss = np.inf
        best_weights = None
        best_biases = None
        n = len(Xs)
        for epoch in range(1, self.epochs + 1):
            # Öğrenme hızı programı: kısa ısınma + kosinüs azalma.
            # Erken epochlarda hızlı ilerler, sonlara doğru ince ayar yapar.
            if self.lr_decay:
                if warmup_epochs and epoch <= warmup_epochs:
                    factor = 0.35 + 0.65 * (epoch / warmup_epochs)
                else:
                    span = max(1, self.epochs - warmup_epochs)
                    progress = min(1.0, max(0.0, (epoch - warmup_epochs) / span))
                    factor = 0.08 + 0.92 * 0.5 * (1.0 + np.cos(np.pi * progress))
                epoch_lr = max(min_lr, base_lr * float(factor))
                for opt in optimizers:
                    opt.lr = epoch_lr
                for opt in opt_b:
                    opt.lr = epoch_lr
            order = self.rng.permutation(n)
            epoch_loss = 0.0
            batches = 0
            for start in range(0, n, self.batch_size):
                idx = order[start : start + self.batch_size]
                xb, yb, wb = Xs[idx], y[idx], w[idx]
                acts, pre = self._forward(xb, training=True)
                p = acts[-1]
                # Çıkış katmanı gradyanı
                if self.output == "binary":
                    yv_b = yb.astype(float).reshape(-1, 1)
                    dz = (p - yv_b) * wb.reshape(-1, 1)
                    dz /= max(float(wb.sum()), 1e-9)
                elif self.output == "multiclass":
                    grad = p.copy()
                    grad[np.arange(len(yb)), yb.astype(int)] -= 1.0
                    dz = grad * wb.reshape(-1, 1)
                    dz /= max(float(wb.sum()), 1e-9)
                else:
                    dz = (p - yb.astype(float).reshape(-1, 1)) * wb.reshape(-1, 1)
                    dz /= max(float(wb.sum()), 1e-9)

                # Geriye yayılım (gradyan kırpma ile: patlayan gradyanları engeller)
                grads: List[np.ndarray] = []
                bgrads: List[np.ndarray] = []
                for layer in range(len(self.weights_) - 1, -1, -1):
                    dw = acts[layer].T @ dz + self.l2 * self.weights_[layer]
                    db = dz.sum(axis=0)
                    grads.append(dw)
                    bgrads.append(db)
                    if layer > 0:
                        da = dz @ self.weights_[layer].T
                        dz = da * _activation_grad(self.activation, pre[layer - 1], acts[layer])
                if self.grad_clip > 0 and grads:
                    norm = float(np.sqrt(sum(float(np.sum(g * g)) for g in grads)))
                    if norm > self.grad_clip:
                        scale = self.grad_clip / (norm + 1e-9)
                        grads = [g * scale for g in grads]
                for pos in range(len(grads)):
                    layer = len(self.weights_) - 1 - pos
                    self.weights_[layer] = optimizers[layer].step(self.weights_[layer], grads[pos])
                    self.biases_[layer] = opt_b[layer].step(self.biases_[layer], bgrads[pos])
                epoch_loss += self._loss(yb, acts[-1], wb)
                batches += 1

            train_loss = epoch_loss / max(batches, 1)
            if have_val:
                acts_v, _ = self._forward(Xv, training=False)
                val_loss = self._loss(yv, acts_v[-1], wv)
            else:
                val_loss = train_loss
            self.history.append(
                {"epoch": epoch, "train_loss": round(train_loss, 6), "val_loss": round(val_loss, 6)}
            )

            # Göreli iyileşme: gürültü düzeyindeki minik dalgalanmalar eğitimi kesmez.
            if best_weights is None or val_loss < best_loss * (1.0 - self.min_delta):
                best_loss = val_loss
                best_weights = [w.copy() for w in self.weights_]
                best_biases = [b.copy() for b in self.biases_]
                self.best_epoch = epoch
            elif epoch - self.best_epoch >= self.patience:
                self.stopped_early = True
                break

        if best_weights is not None:
            self.weights_ = best_weights
            self.biases_ = best_biases
            self.best_val_loss = float(best_loss)
        return self

    # ------------------------------------------------------------------
    # Çıkarım
    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.weights_:
            raise RuntimeError("Model eğitilmemiş")
        Xs = self._standardize(np.asarray(X, dtype=float), fit=False)
        acts, _ = self._forward(Xs, training=False)
        out = acts[-1]
        if self.output == "binary":
            p = out.reshape(-1)
            return np.column_stack([1.0 - p, p])
        if self.output == "multiclass":
            return out
        return out.reshape(-1, 1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = self.predict_proba(X)
        if self.output == "regression":
            return out.reshape(-1) * self.y_scale_ + self.y_mean_
        return np.argmax(out, axis=1)


class NumpyLogistic:
    """Eski/çok küçük veri setleri için basit lojistik regresyon yedeği."""

    def __init__(self, l2: float = 1.0, iterations: int = 250, lr: float = 0.15):
        self.l2 = float(l2)
        self.iterations = int(iterations)
        self.lr = float(lr)
        self.mean_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None
        self.coef_: Optional[np.ndarray] = None
        self.classes_ = np.array([0, 1])
        self.history: List[Dict[str, float]] = []

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

    def fit(self, X, y, sample_weight=None, X_val=None, y_val=None, sample_weight_val=None):
        Xs = self._prepare(X)
        Xb = np.column_stack([np.ones(len(Xs)), Xs])
        y = np.asarray(y, dtype=float)
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
        w = w / w.sum()
        coef = np.zeros(Xb.shape[1])
        for step in range(self.iterations):
            z = np.clip(Xb @ coef, -30, 30)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = Xb.T @ (w * (p - y))
            grad[1:] += self.l2 * coef[1:] / len(y)
            coef -= self.lr * grad
            if step % 25 == 0:
                loss = float(-(w * (y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9))).sum())
                self.history.append({"epoch": step, "train_loss": round(loss, 6), "val_loss": round(loss, 6)})
        self.coef_ = coef
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("Model eğitilmemiş")
        Xs = self._prepare(np.asarray(X, dtype=float))
        Xb = np.column_stack([np.ones(len(Xs)), Xs])
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ self.coef_, -30, 30)))
        return np.column_stack([1 - p, p])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
