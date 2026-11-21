"""NumPy ile yazılmış LSTM sınıflandırıcı (çok çıktılı).

Harici derin öğrenme kütüphanesi yok; bu yüzden Docker imajı şişmez ve
eğitim deterministik olur. Model **son T mumun gidişatını** görür:

- giriş: (N, T, F) pencere
- katman: tek yönlü LSTM (varsayılan 32–64 hücre), dropout, L2
- çıkış: iki sigmoid (AL olasılığı, SAT olasılığı)

Eğitim: Adam + kosinüs öğrenme hızı + gradyan kırpma + göreli erken durma.
Bellek dostudur: geri yayılım için yalnızca bir batch'in ara değerleri tutulur.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.ai.nn import _Adam, _activation_grad  # noqa: F401  (ortak yardımcılar)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


class LSTMClassifier:
    """Çok çıktılı LSTM (AL ve SAT olasılıkları birlikte öğrenilir)."""

    def __init__(
        self,
        input_size: int,
        *,
        hidden: int = 32,
        dropout: float = 0.1,
        learning_rate: float = 0.01,
        epochs: int = 60,
        batch_size: int = 64,
        l2: float = 1e-4,
        patience: int = 10,
        min_delta: float = 1e-4,
        grad_clip: float = 1.0,
        lr_decay: bool = True,
        n_outputs: int = 2,
        random_state: int = 42,
    ):
        self.input_size = int(input_size)
        self.hidden = max(4, int(hidden))
        self.dropout = float(max(0.0, min(dropout, 0.8)))
        self.learning_rate = float(max(1e-5, learning_rate))
        self.epochs = int(max(1, epochs))
        self.batch_size = int(max(8, batch_size))
        self.l2 = float(max(0.0, l2))
        self.patience = int(max(1, patience))
        self.min_delta = float(max(1e-9, min(min_delta, 0.5)))
        self.grad_clip = float(max(0.0, grad_clip))
        self.lr_decay = bool(lr_decay)
        self.n_outputs = int(n_outputs)
        self.random_state = int(random_state)
        self.rng = np.random.default_rng(random_state)
        self.history: List[Dict[str, float]] = []
        self.best_epoch = 0
        self.best_val_loss: Optional[float] = None
        self.stopped_early = False
        self.warm_started = False
        # Ağırlıklar (fit içinde kurulur)
        self.Wx: Optional[np.ndarray] = None
        self.Wh: Optional[np.ndarray] = None
        self.b: Optional[np.ndarray] = None
        self.Wo: Optional[np.ndarray] = None
        self.bo: Optional[np.ndarray] = None
        self.classes_ = np.arange(self.n_outputs)

    # ------------------------------------------------------------------
    def _init_params(self) -> None:
        F, H, O = self.input_size, self.hidden, self.n_outputs
        # Xavier/Glorot
        f32 = np.float32
        lx = np.sqrt(6.0 / (F + 4 * H))
        lh = np.sqrt(6.0 / (H + 4 * H))
        self.Wx = self.rng.uniform(-lx, lx, size=(F, 4 * H)).astype(f32)
        self.Wh = self.rng.uniform(-lh, lh, size=(H, 4 * H)).astype(f32)
        b = np.zeros(4 * H, dtype=f32)
        b[H : 2 * H] = 1.0  # unut kapısı ön yargısı: uzun bağımlılık öğrensin
        self.b = b
        lo = np.sqrt(6.0 / (H + O))
        self.Wo = self.rng.uniform(-lo, lo, size=(H, O)).astype(f32)
        self.bo = np.zeros(O, dtype=f32)

    def _forward(self, X: np.ndarray, training: bool = False):
        N, T, _ = X.shape
        H = self.hidden
        h = np.zeros((N, H))
        c = np.zeros((N, H))
        cache: List[tuple] = []
        use_dropout = training and self.dropout > 0
        for t in range(T):
            x_t = X[:, t, :]
            if use_dropout:
                x_t = x_t * (self.rng.random(x_t.shape) >= self.dropout) / (1.0 - self.dropout)
            z = x_t @ self.Wx + h @ self.Wh + self.b
            i = _sigmoid(z[:, :H])
            f = _sigmoid(z[:, H : 2 * H])
            o = _sigmoid(z[:, 2 * H : 3 * H])
            g = np.tanh(z[:, 3 * H :])
            c_prev = c
            c = f * c_prev + i * g
            tc = np.tanh(c)
            h_prev = h
            h = o * tc
            if training:
                cache.append((x_t, h_prev, c_prev, i, f, o, g, tc))
        feat = h
        if use_dropout:
            feat = feat * (self.rng.random(feat.shape) >= self.dropout) / (1.0 - self.dropout)
        logits = feat @ self.Wo + self.bo
        return logits, feat, cache

    @staticmethod
    def _bce(logits: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
        p = _sigmoid(logits)
        eps = 1e-9
        loss = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        return float((loss * w).sum() / max(float(w.sum()), 1e-9))

    # ------------------------------------------------------------------
    def _backward(
        self, X: np.ndarray, y: np.ndarray, w: np.ndarray
    ) -> tuple[Dict[str, np.ndarray], np.ndarray]:
        logits, feat, cache = self._forward(X, training=True)
        p = _sigmoid(logits)
        dlogits = (p - y) * w / max(float(w.sum()), 1e-9)
        dWo = feat.T @ dlogits
        dbo = dlogits.sum(axis=0)
        dh = dlogits @ self.Wo.T
        dc = np.zeros_like(dh)
        dWx = np.zeros_like(self.Wx)
        dWh = np.zeros_like(self.Wh)
        db = np.zeros_like(self.b)
        for t in range(len(cache) - 1, -1, -1):
            x_t, h_prev, c_prev, i, f, o, g, tc = cache[t]
            do = dh * tc
            dc = dc + dh * o * (1.0 - tc * tc)
            di = dc * g
            dg = dc * i
            df = dc * c_prev
            dc = dc * f
            dz = np.concatenate(
                [
                    di * i * (1.0 - i),
                    df * f * (1.0 - f),
                    do * o * (1.0 - o),
                    dg * (1.0 - g * g),
                ],
                axis=1,
            )
            dWx += x_t.T @ dz
            dWh += h_prev.T @ dz
            db += dz.sum(axis=0)
            dh = dz @ self.Wh.T
        return {"Wx": dWx, "Wh": dWh, "b": db, "Wo": dWo, "bo": dbo}, logits

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: Optional[np.ndarray] = None,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        sample_weight_val: Optional[np.ndarray] = None,
        init_model: Optional["LSTMClassifier"] = None,
    ) -> "LSTMClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim == 1:
            y = y.reshape(-1, 1)
        if y.shape[1] != self.n_outputs:
            raise ValueError("Hedef boyutu çıktı sayısıyla uyuşmuyor")
        if sample_weight is None:
            w = np.ones_like(y)
        else:
            w = np.asarray(sample_weight, dtype=np.float32)
            if w.ndim == 1:
                w = np.repeat(w.reshape(-1, 1), self.n_outputs, axis=1)
        w = np.where(np.isfinite(w) & (w > 0), w, 1.0)

        if self.Wx is None:
            self._init_params()
        self.warm_started = False
        if init_model is not None and getattr(init_model, "Wx", None) is not None:
            same = (
                init_model.Wx.shape == self.Wx.shape
                and init_model.Wh.shape == self.Wh.shape
                and init_model.Wo.shape == self.Wo.shape
            )
            if same:
                self.Wx = init_model.Wx.copy()
                self.Wh = init_model.Wh.copy()
                self.b = init_model.b.copy()
                self.Wo = init_model.Wo.copy()
                self.bo = init_model.bo.copy()
                self.warm_started = True

        base_lr = self.learning_rate * (0.5 if self.warm_started else 1.0)
        lr_min = base_lr * 0.1
        opts = {
            "Wx": _Adam(self.Wx.shape, base_lr, dtype=self.Wx.dtype),
            "Wh": _Adam(self.Wh.shape, base_lr, dtype=self.Wh.dtype),
            "b": _Adam(self.b.shape, base_lr, dtype=self.b.dtype),
            "Wo": _Adam(self.Wo.shape, base_lr, dtype=self.Wo.dtype),
            "bo": _Adam(self.bo.shape, base_lr, dtype=self.bo.dtype),
        }

        has_val = X_val is not None and y_val is not None and len(X_val) > 0
        if has_val:
            Xv = np.asarray(X_val, dtype=np.float32)
            yv = np.asarray(y_val, dtype=np.float32)
            if yv.ndim == 1:
                yv = yv.reshape(-1, 1)
            wv = (
                np.ones_like(yv)
                if sample_weight_val is None
                else np.asarray(sample_weight_val, dtype=np.float32)
            )
            if wv.ndim == 1:
                wv = np.repeat(wv.reshape(-1, 1), self.n_outputs, axis=1)
            wv = np.where(np.isfinite(wv) & (wv > 0), wv, 1.0)

        n = len(X)
        best_loss = np.inf
        best: Optional[Dict[str, np.ndarray]] = None
        for epoch in range(1, self.epochs + 1):
            if self.lr_decay:
                progress = (epoch - 1) / max(1, self.epochs - 1)
                lr = max(lr_min, base_lr * (0.1 + 0.9 * 0.5 * (1.0 + np.cos(np.pi * progress))))
                for opt in opts.values():
                    opt.lr = float(lr)
            order = self.rng.permutation(n)
            total = 0.0
            batches = 0
            for start in range(0, n, self.batch_size):
                idx = order[start : start + self.batch_size]
                xb, yb, wb = X[idx], y[idx], w[idx]
                grads, logits = self._backward(xb, yb, wb)
                # Gradyan kırpma (global norm)
                if self.grad_clip > 0:
                    norm = float(np.sqrt(sum(float(np.sum(v * v)) for v in grads.values())))
                    if norm > self.grad_clip:
                        scale = self.grad_clip / (norm + 1e-9)
                        grads = {k: v * scale for k, v in grads.items()}
                # L2 yalnızca ağırlık matrislerine uygulanır (önyargılara değil).
                grads["Wx"] = grads["Wx"] + self.l2 * self.Wx
                grads["Wh"] = grads["Wh"] + self.l2 * self.Wh
                grads["Wo"] = grads["Wo"] + self.l2 * self.Wo
                self.Wx = opts["Wx"].step(self.Wx, grads["Wx"])
                self.Wh = opts["Wh"].step(self.Wh, grads["Wh"])
                self.b = opts["b"].step(self.b, grads["b"])
                self.Wo = opts["Wo"].step(self.Wo, grads["Wo"])
                self.bo = opts["bo"].step(self.bo, grads["bo"])
                total += self._bce(logits, yb, wb)
                batches += 1

            train_loss = total / max(batches, 1)
            if has_val:
                vlogits, _, _ = self._forward(Xv, training=False)
                val_loss = self._bce(vlogits, yv, wv)
            else:
                val_loss = train_loss
            self.history.append(
                {"epoch": epoch, "train_loss": round(train_loss, 6), "val_loss": round(val_loss, 6)}
            )
            if best is None or val_loss < best_loss * (1.0 - self.min_delta):
                best_loss = val_loss
                self.best_epoch = epoch
                best = {
                    "Wx": self.Wx.copy(),
                    "Wh": self.Wh.copy(),
                    "b": self.b.copy(),
                    "Wo": self.Wo.copy(),
                    "bo": self.bo.copy(),
                }
            elif epoch - self.best_epoch >= self.patience:
                self.stopped_early = True
                break

        if best:
            self.Wx = best["Wx"]
            self.Wh = best["Wh"]
            self.b = best["b"]
            self.Wo = best["Wo"]
            self.bo = best["bo"]
            self.best_val_loss = float(best_loss)
        return self

    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.Wx is None:
            raise RuntimeError("Model eğitilmemiş")
        logits, _, _ = self._forward(np.asarray(X, dtype=np.float32), training=False)
        return _sigmoid(logits)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X) >= 0.5).astype(int)

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        params = 0
        for arr in (self.Wx, self.Wh, self.b, self.Wo, self.bo):
            if arr is not None:
                params += int(arr.size)
        return {
            "type": "LSTM",
            "hidden": self.hidden,
            "params": params,
            "epochs_run": len(self.history),
            "best_epoch": self.best_epoch,
            "stopped_early": self.stopped_early,
            "warm_started": self.warm_started,
            "curve": self.history[-200:],
        }
