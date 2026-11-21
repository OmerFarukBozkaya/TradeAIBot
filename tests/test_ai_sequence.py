"""Sıra modelleri (LSTM / Transformer) ve yeni etiket/politika testleri."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.labels import build_labels
from app.ai.lstm import LSTMClassifier
from app.ai.transformer import TransformerClassifier
from app.ai.sequence import SequenceData, subsample


def _toy(n=2400, T=12, F=6, seed=3):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, T, F)).astype(np.float32)
    # Etiket, pencerenin sonundaki kümülatif eğimin işareti.
    # Etiket son 3 mumun yönüne bağlı (son token yeterli bilgi taşır).
    signal = X[:, -3:, 0].sum(axis=1)
    y = np.stack([(signal > 0).astype(float), (signal <= 0).astype(float)], axis=1)
    return X, y


def test_sequence_windows_shape_and_scaler():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 5))
    data = SequenceData(X, window=8)
    data.fit_scaler(np.arange(0, 120))
    win = data.windows([50, 100])
    assert win.shape == (2, 8, 5)
    assert np.all(np.isfinite(win))
    # Pencere, konumun kendisiyle biter (gelecek yok).
    assert np.allclose(win[0, -1], data.Z[50], atol=1e-6)


def test_sequence_rejects_short_history():
    data = SequenceData(np.zeros((50, 3)), window=10)
    data.fit_scaler(np.arange(0, 40))
    with pytest.raises(ValueError):
        data.windows([3])


def test_sequence_from_bundle_roundtrip():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(150, 4))
    data = SequenceData(X, window=6)
    data.fit_scaler(np.arange(0, 100))
    bundle = {"seq_window": 6, "seq_scaler": data.scalar()}
    restored = SequenceData.from_bundle(X, bundle)
    assert np.allclose(restored.windows([40]), data.windows([40]))


def test_subsample_keeps_coverage():
    pos = np.arange(1000)
    picked = subsample(pos, 100, stride=1)
    assert len(picked) == 100
    assert picked[0] == 0 and picked[-1] == 999


def test_lstm_learns_sequence_pattern():
    X, y = _toy()
    model = LSTMClassifier(6, hidden=16, epochs=25, batch_size=64, learning_rate=0.01,
                           patience=8, dropout=0.0, random_state=1)
    model.fit(X[:1800], y[:1800], X_val=X[1800:], y_val=y[1800:])
    p = model.predict_proba(X[1800:])[:, 0]
    acc = float(np.mean((p >= 0.5) == (y[1800:, 0] >= 0.5)))
    assert acc > 0.85, acc
    info = model.info()
    assert info["type"] == "LSTM" and info["params"] > 0


def test_transformer_learns_sequence_pattern():
    X, y = _toy()
    model = TransformerClassifier(6, window=12, dim=16, heads=2, layers=1,
                                  epochs=80, batch_size=64, learning_rate=0.008,
                                  patience=15, dropout=0.0, random_state=2)
    model.fit(X[:1800], y[:1800], X_val=X[1800:], y_val=y[1800:])
    p = model.predict_proba(X[1800:])[:, 0]
    acc = float(np.mean((p >= 0.5) == (y[1800:, 0] >= 0.5)))
    assert acc > 0.85, acc
    info = model.info()
    assert info["type"] == "Transformer" and info["params"] > 0


def test_transformer_gradients_match_numeric():
    rng = np.random.default_rng(0)
    B, T, F, D = 3, 5, 4, 8
    model = TransformerClassifier(F, window=T, dim=D, heads=2, layers=1, dropout=0.0, random_state=1)
    model.params = model._seed_params()
    X = rng.normal(size=(B, T, F)).astype(np.float32)
    y = rng.integers(0, 2, size=(B, 2)).astype(np.float32)
    w = np.ones((B, 2), dtype=np.float32)
    grads, _ = model._backward(X, y, w)

    def loss() -> float:
        logits, _, _, _, _, _ = model._forward(X, training=False)
        return model._bce(logits, y, w)

    eps = 1e-4
    for key in ("Win", "wh", "L0_q", "L0_w1", "L0_g1", "pos"):
        arr = model.params[key]
        for _ in range(3):
            idx = tuple(int(rng.integers(0, s)) for s in arr.shape)
            old = float(arr[idx])
            arr[idx] = old + eps
            up = loss()
            arr[idx] = old - eps
            down = loss()
            arr[idx] = old
            numeric = (up - down) / (2 * eps)
            analytic = float(grads[key][idx])
            assert abs(numeric - analytic) < 5e-3 + 0.05 * abs(numeric), (key, numeric, analytic)


def test_lstm_gradients_match_numeric():
    rng = np.random.default_rng(0)
    B, T, F = 3, 5, 4
    model = LSTMClassifier(F, hidden=4, dropout=0.0, random_state=2)
    model._init_params()
    X = rng.normal(size=(B, T, F)).astype(np.float32)
    y = rng.integers(0, 2, size=(B, 2)).astype(np.float32)
    w = np.ones((B, 2), dtype=np.float32)
    grads, _ = model._backward(X, y, w)

    def loss() -> float:
        logits, _, _ = model._forward(X, training=False)
        return model._bce(logits, y, w)

    eps = 1e-4
    for key in ("Wx", "Wh", "b", "Wo", "bo"):
        arr = {"Wx": model.Wx, "Wh": model.Wh, "b": model.b, "Wo": model.Wo, "bo": model.bo}[key]
        for _ in range(3):
            idx = tuple(int(rng.integers(0, s)) for s in arr.shape)
            old = float(arr[idx])
            arr[idx] = old + eps
            up = loss()
            arr[idx] = old - eps
            down = loss()
            arr[idx] = old
            numeric = (up - down) / (2 * eps)
            analytic = float(grads[key][idx])
            assert abs(numeric - analytic) < 5e-3 + 0.05 * abs(numeric), (key, numeric, analytic)


def test_excess_labels_are_causal_and_balanced():
    rng = np.random.default_rng(9)
    n = 8000
    drift = np.concatenate([np.full(n // 2, 0.0002), np.full(n - n // 2, -0.0002)])
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.004, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    labels = build_labels(close, high, low, {"kind": "excess_return", "horizon": 24})
    valid = labels["valid"]
    assert valid.sum() > 1000
    buy_rate = float(labels["buy"][valid].mean())
    sell_rate = float(labels["sell"][valid].mean())
    assert 0.005 < buy_rate < 0.25, buy_rate
    assert 0.02 < sell_rate < 0.45, sell_rate
    # Son horizon mumun etiketi kesinleşmemiş olmalı.
    assert not labels["valid"][-3:].any()
    assert labels["thresholds"]["high"] > 0


def test_excess_thresholds_use_only_training_region():
    """Eşikler yalnızca eğitim bölümünden hesaplanır (sızıntı yok)."""
    rng = np.random.default_rng(11)
    n = 6000
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    high = close * (1.002)
    low = close * (0.998)
    a = build_labels(close, high, low, {"kind": "excess_return", "horizon": 12, "label_train_frac": 0.55})
    # Test bölgesini (son %30) bozalım: eşik değişmemeli.
    close2 = close.copy()
    close2[int(n * 0.75):] *= 1.5
    high2 = close2 * (1.002)
    low2 = close2 * (0.998)
    b = build_labels(close2, high2, low2, {"kind": "excess_return", "horizon": 12, "label_train_frac": 0.55})
    # Eşikler aynı kalmalı (yalnızca eğitim bölgesine bağlı).
    assert a["thresholds"]["quantile"] == b["thresholds"]["quantile"]
