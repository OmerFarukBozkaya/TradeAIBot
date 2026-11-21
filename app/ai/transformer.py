"""NumPy ile yazılmış küçük Transformer kodlayıcı (encoder).

Model son T mumun **tamamına aynı anda bakar** (self-attention) ve son mumun
temsilinden AL/SAT olasılıklarını üretir. Pencere içindeki tüm mumlar geçmişte
kaldığı için nedensellik ihlali yoktur; pencere dışına hiç bakılmaz.

Mimari (varsayılan):
    giriş izdüşümü (F → d) + konum kodlaması
    N × [ LayerNorm → çok başlı self-attention → artık bağlantı
          LayerNorm → GELU FFN → artık bağlantı ]
    son LayerNorm → son mum → lineer (2 çıktı)

Eğitim: Adam + kosinüs öğrenme hızı + gradyan kırpma + göreli erken durma.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.ai.nn import _Adam

LN_EPS = 1e-5


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _gelu(x: np.ndarray) -> np.ndarray:
    c = np.sqrt(2.0 / np.pi)
    return 0.5 * x * (1.0 + np.tanh(c * (x + 0.044715 * x ** 3)))


def _gelu_grad(x: np.ndarray) -> np.ndarray:
    c = np.sqrt(2.0 / np.pi)
    inner = c * (x + 0.044715 * x ** 3)
    t = np.tanh(inner)
    return 0.5 * (1.0 + t) + 0.5 * x * (1.0 - t ** 2) * c * (1.0 + 3.0 * 0.044715 * x ** 2)


def _softmax(x: np.ndarray) -> np.ndarray:
    z = x - np.max(x, axis=-1, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=-1, keepdims=True)


def _ln_forward(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray):
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + LN_EPS)
    xhat = (x - mean) * inv
    return xhat * gamma + beta, (xhat, inv, gamma)


def _ln_backward(dy: np.ndarray, cache) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xhat, inv, gamma = cache
    axes = tuple(range(dy.ndim - 1))
    dgamma = np.sum(dy * xhat, axis=axes, keepdims=False)
    dbeta = np.sum(dy, axis=axes, keepdims=False)
    dxhat = dy * gamma
    dx = inv * (
        dxhat
        - dxhat.mean(axis=-1, keepdims=True)
        - xhat * (dxhat * xhat).mean(axis=-1, keepdims=True)
    )
    return dx, dgamma, dbeta


class TransformerClassifier:
    """Küçük transformer kodlayıcı; AL ve SAT olasılıklarını birlikte üretir."""

    def __init__(
        self,
        input_size: int,
        *,
        window: int = 32,
        dim: int = 32,
        heads: int = 2,
        layers: int = 1,
        ff_mult: int = 2,
        ffn_activation: str = "relu",
        dropout: float = 0.1,
        learning_rate: float = 0.003,
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
        self.window = int(window)
        self.dim = max(8, int(dim))
        self.heads = max(1, int(heads))
        if self.dim % self.heads != 0:
            self.heads = 1
        self.layers = max(1, int(layers))
        self.ff_mult = max(1, int(ff_mult))
        self.ffn_activation = ffn_activation if ffn_activation in {"relu", "gelu"} else "relu"
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
        self.params: Dict[str, np.ndarray] = {}
        self.classes_ = np.arange(self.n_outputs)

    # ------------------------------------------------------------------
    def _seed_params(self) -> Dict[str, np.ndarray]:
        d, F, T = self.dim, self.input_size, self.window
        hd = d // self.heads
        dff = d * self.ff_mult
        f32 = np.float32
        params: Dict[str, np.ndarray] = {
            "Win": self.rng.normal(0.0, np.sqrt(2.0 / F), size=(F, d)).astype(f32),
            "bin": np.zeros(d, dtype=f32),
            "pos": self.rng.normal(0.0, 0.02, size=(T, d)).astype(f32),
        }
        for l in range(self.layers):
            p = f"L{l}_"
            params[p + "g1"] = np.ones(d, dtype=f32)
            params[p + "b1"] = np.zeros(d, dtype=f32)
            for name in ("q", "k", "v", "o"):
                params[p + name] = self.rng.normal(0.0, np.sqrt(2.0 / d), size=(d, d)).astype(f32)
                params[p + name + "_b"] = np.zeros(d, dtype=f32)
            params[p + "g2"] = np.ones(d, dtype=f32)
            params[p + "b2"] = np.zeros(d, dtype=f32)
            params[p + "w1"] = self.rng.normal(0.0, np.sqrt(2.0 / d), size=(d, dff)).astype(f32)
            params[p + "w1b"] = np.zeros(dff, dtype=f32)
            params[p + "w2"] = self.rng.normal(0.0, np.sqrt(2.0 / dff), size=(dff, d)).astype(f32)
            params[p + "w2b"] = np.zeros(d, dtype=f32)
        params["gf"] = np.ones(d, dtype=f32)
        params["bf"] = np.zeros(d, dtype=f32)
        params["wh"] = self.rng.normal(0.0, np.sqrt(1.0 / d), size=(d, self.n_outputs)).astype(f32)
        params["bh"] = np.zeros(self.n_outputs, dtype=f32)
        _ = hd
        return params

    # ------------------------------------------------------------------
    def _forward(self, X: np.ndarray, training: bool = False):
        B, T, _ = X.shape
        d, H = self.dim, self.heads
        hd = d // H
        p = self.params
        x = X.reshape(B * T, self.input_size) @ p["Win"] + p["bin"]
        x = x.reshape(B, T, d) + p["pos"][None, :T, :]
        masks: List[np.ndarray] = []
        if training and self.dropout > 0:
            m = (self.rng.random(x.shape) >= self.dropout).astype(np.float32) / (1.0 - self.dropout)
            x = x * m
            masks.append(m)
        else:
            masks.append(np.ones((1, 1, 1), dtype=np.float32))
        cache_layers = []
        for l in range(self.layers):
            p = f"L{l}_"
            a, c1 = _ln_forward(x, self.params[p + "g1"], self.params[p + "b1"])
            a_flat = a.reshape(B * T, d)
            Q = (a_flat @ self.params[p + "q"] + self.params[p + "q_b"]).reshape(B, T, H, hd)
            K = (a_flat @ self.params[p + "k"] + self.params[p + "k_b"]).reshape(B, T, H, hd)
            V = (a_flat @ self.params[p + "v"] + self.params[p + "v_b"]).reshape(B, T, H, hd)
            Q = Q.transpose(0, 2, 1, 3)
            K = K.transpose(0, 2, 1, 3)
            V = V.transpose(0, 2, 1, 3)
            scores = (Q @ K.transpose(0, 1, 3, 2)) / np.sqrt(hd)
            P = _softmax(scores)
            C = P @ V
            Cm = C.transpose(0, 2, 1, 3).reshape(B, T, d)
            O = Cm @ self.params[p + "o"] + self.params[p + "o_b"]
            if training and self.dropout > 0:
                mo = (self.rng.random(O.shape) >= self.dropout).astype(np.float32) / (1.0 - self.dropout)
                O = O * mo
            else:
                mo = np.ones((1, 1, 1), dtype=np.float32)
            x_mid = x + O
            b_, c2 = _ln_forward(x_mid, self.params[p + "g2"], self.params[p + "b2"])
            b_flat = b_.reshape(B * T, d)
            pre = b_flat @ self.params[p + "w1"] + self.params[p + "w1b"]
            U = _gelu(pre) if self.ffn_activation == "gelu" else np.maximum(pre, 0.0)
            f = (U @ self.params[p + "w2"] + self.params[p + "w2b"]).reshape(B, T, d)
            if training and self.dropout > 0:
                mf = (self.rng.random(f.shape) >= self.dropout).astype(np.float32) / (1.0 - self.dropout)
                f = f * mf
            else:
                mf = np.ones((1, 1, 1), dtype=np.float32)
            x = x_mid + f
            cache_layers.append((a, c1, Q, K, V, P, C, Cm, mo, x_mid, b_, c2, U, mf))
        last, cf = _ln_forward(x[:, -1, :], self.params["gf"], self.params["bf"])
        logits = last @ self.params["wh"] + self.params["bh"]
        return logits, last, masks, cache_layers, cf, x

    @staticmethod
    def _bce(logits: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
        pr = _sigmoid(logits)
        eps = 1e-9
        loss = -(y * np.log(pr + eps) + (1 - y) * np.log(1 - pr + eps))
        return float((loss * w).sum() / max(float(w.sum()), 1e-9))

    # ------------------------------------------------------------------
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: Optional[np.ndarray] = None,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        sample_weight_val: Optional[np.ndarray] = None,
        init_model: Optional["TransformerClassifier"] = None,
    ) -> "TransformerClassifier":
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
        self.window = int(X.shape[1])

        if not self.params:
            self.params = self._seed_params()
        self.warm_started = False
        if init_model is not None and getattr(init_model, "params", None):
            if all(
                k in init_model.params and init_model.params[k].shape == v.shape
                for k, v in self.params.items()
            ):
                self.params = {k: v.copy() for k, v in init_model.params.items()}
                self.warm_started = True

        base_lr = self.learning_rate * (0.5 if self.warm_started else 1.0)
        lr_min = base_lr * 0.1
        l2 = self.l2

        def make_opts() -> Dict[str, _Adam]:
            return {k: _Adam(v.shape, base_lr, dtype=v.dtype) for k, v in self.params.items()}

        opts = make_opts()
        has_val = X_val is not None and y_val is not None and len(X_val) > 0
        if has_val:
            Xv = np.asarray(X_val, dtype=np.float32)
            yv = np.asarray(y_val, dtype=np.float32)
            if yv.ndim == 1:
                yv = yv.reshape(-1, 1)
            wv = np.ones_like(yv) if sample_weight_val is None else np.asarray(sample_weight_val, dtype=np.float32)
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
                if self.grad_clip > 0:
                    norm = float(np.sqrt(sum(float(np.sum(v * v)) for v in grads.values())))
                    if norm > self.grad_clip:
                        scale = self.grad_clip / (norm + 1e-9)
                        grads = {k: v * scale for k, v in grads.items()}
                for k in self.params:
                    g = grads.get(k)
                    if g is None:
                        continue
                    if k.endswith("g1") or k.endswith("g2") or k == "gf":
                        g = g  # LayerNorm kazançları
                    else:
                        g = g + l2 * self.params[k] if self.params[k].ndim >= 2 else g
                    self.params[k] = opts[k].step(self.params[k], g)
                total += self._bce(logits, yb, wb)
                batches += 1

            train_loss = total / max(batches, 1)
            if has_val:
                vlogits, _, _, _, _, _ = self._forward(Xv, training=False)
                val_loss = self._bce(vlogits, yv, wv)
            else:
                val_loss = train_loss
            self.history.append(
                {"epoch": epoch, "train_loss": round(train_loss, 6), "val_loss": round(val_loss, 6)}
            )
            if best is None or val_loss < best_loss * (1.0 - self.min_delta):
                best_loss = val_loss
                self.best_epoch = epoch
                best = {k: v.copy() for k, v in self.params.items()}
            elif epoch - self.best_epoch >= self.patience:
                self.stopped_early = True
                break

        if best:
            self.params = best
            self.best_val_loss = float(best_loss)
        return self

    # ------------------------------------------------------------------
    def _backward(self, X: np.ndarray, y: np.ndarray, w: np.ndarray):
        B, T, _ = X.shape
        d, H = self.dim, self.heads
        hd = d // H
        logits, last, masks, cache_layers, cf, x_final = self._forward(X, training=True)
        grads: Dict[str, np.ndarray] = {k: np.zeros_like(v) for k, v in self.params.items()}
        pr = _sigmoid(logits)
        dlogits = (pr - y) * w / max(float(w.sum()), 1e-9)
        grads["wh"] = last.T @ dlogits
        grads["bh"] = dlogits.sum(axis=0)
        dlast = dlogits @ self.params["wh"].T
        dx_last, grads["gf"], grads["bf"] = _ln_backward(dlast, cf)
        dx = np.zeros_like(x_final)
        dx[:, -1, :] = dx_last

        for l in range(self.layers - 1, -1, -1):
            p = f"L{l}_"
            (a, c1, Q, K, V, P, C, Cm, mo, x_mid, b_, c2, U, mf) = cache_layers[l]
            dx_mid = dx.copy()
            # FFN yolu
            df = dx_mid * mf
            grads[p + "w2"] = U.reshape(B * T, -1).T @ df.reshape(B * T, d)
            grads[p + "w2b"] = df.reshape(B * T, d).sum(axis=0)
            dU = df.reshape(B * T, d) @ self.params[p + "w2"].T
            pre = b_.reshape(B * T, d) @ self.params[p + "w1"] + self.params[p + "w1b"]
            dpre = dU * (_gelu_grad(pre) if self.ffn_activation == "gelu" else (pre > 0).astype(dU.dtype))
            grads[p + "w1"] = b_.reshape(B * T, d).T @ dpre
            grads[p + "w1b"] = dpre.sum(axis=0)
            db_ = (dpre @ self.params[p + "w1"].T).reshape(B, T, d)
            dx_in_ffn, grads[p + "g2"], grads[p + "b2"] = _ln_backward(db_, c2)
            dx_mid = dx_mid + dx_in_ffn

            # Attention yolu
            dO = dx_mid * mo
            grads[p + "o"] = Cm.reshape(B * T, d).T @ dO.reshape(B * T, d)
            grads[p + "o_b"] = dO.reshape(B * T, d).sum(axis=0)
            dCm = dO.reshape(B * T, d) @ self.params[p + "o"].T
            dC = dCm.reshape(B, T, H, hd).transpose(0, 2, 1, 3)
            dP = dC @ V.transpose(0, 1, 3, 2)
            dV = P.transpose(0, 1, 3, 2) @ dC
            dS = P * (dP - np.sum(dP * P, axis=-1, keepdims=True))
            scale = 1.0 / np.sqrt(hd)
            dQ = (dS @ K) * scale
            dK = (dS.transpose(0, 1, 3, 2) @ Q) * scale
            dQf = dQ.transpose(0, 2, 1, 3).reshape(B * T, d)
            dKf = dK.transpose(0, 2, 1, 3).reshape(B * T, d)
            dVf = dV.transpose(0, 2, 1, 3).reshape(B * T, d)
            a_flat = a.reshape(B * T, d)
            grads[p + "q"] = a_flat.T @ dQf
            grads[p + "k"] = a_flat.T @ dKf
            grads[p + "v"] = a_flat.T @ dVf
            grads[p + "q_b"] = dQf.sum(axis=0)
            grads[p + "k_b"] = dKf.sum(axis=0)
            grads[p + "v_b"] = dVf.sum(axis=0)
            dA = dQf @ self.params[p + "q"].T + dKf @ self.params[p + "k"].T + dVf @ self.params[p + "v"].T
            dx_in_attn, grads[p + "g1"], grads[p + "b1"] = _ln_backward(dA.reshape(B, T, d), c1)
            dx = dx_mid + dx_in_attn

        # Giriş izdüşümü ve konum kodlaması
        dx_flat = dx.reshape(B * T, d)
        grads["Win"] = X.reshape(B * T, self.input_size).T @ dx_flat
        grads["bin"] = dx_flat.sum(axis=0)
        grads["pos"][:T] = dx.sum(axis=0)
        return grads, logits

    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.params:
            raise RuntimeError("Model eğitilmemiş")
        logits, _, _, _, _, _ = self._forward(np.asarray(X, dtype=np.float32), training=False)
        return _sigmoid(logits)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X) >= 0.5).astype(int)

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        return {
            "type": "Transformer",
            "dim": self.dim,
            "heads": self.heads,
            # ``layers`` MLP'de gizli katman listesi anlamına geldiği için burada
            # çakışmayı önlemek adına blok sayısı ``depth`` olarak verilir.
            "depth": self.layers,
            "params": int(sum(v.size for v in self.params.values())),
            "epochs_run": len(self.history),
            "best_epoch": self.best_epoch,
            "stopped_early": self.stopped_early,
            "warm_started": self.warm_started,
            "curve": self.history[-200:],
        }
