"""AI stratejisinde trend filtresi kapısı (numpy bool dizisi) regresyon testi.

Hata: ``prepared.get("trend_ok") or [True] * n`` numpy dizisinin tamamını
bool'a çevirmeye çalışıyor ve "truth value of an array ... is ambiguous"
istisnası atıyordu.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ai import strategy as st

N = 300


def _make_data(direction: float = 1.0):
    close = [1000.0 + direction * i for i in range(N)]
    return {
        "opendate": [1_700_000_000_000 + i * 3_600_000 for i in range(N)],
        "open": close,
        "high": [c + 1 for c in close],
        "low": [c - 1 for c in close],
        "close": close,
        "volume_coin": [1.0] * N,
        "volume_usdt": [100.0] * N,
    }


def _install_fake_model(monkeypatch, data, *, buy_p=0.9, sell_p=0.1, trend_filter=True):
    frame = pd.DataFrame({"f1": np.arange(N, dtype=float)})
    feature = {
        "frame": frame,
        "X": frame.to_numpy(dtype=float),
        "close": np.asarray(data["close"], dtype=float),
        "feature_names": ["f1"],
        "warmup": 5,
    }
    monkeypatch.setattr(st, "build_features", lambda d, g: feature)
    monkeypatch.setattr(
        st,
        "predict_signals",
        lambda bundle, X: (np.full(len(X), buy_p), np.full(len(X), sell_p)),
    )
    monkeypatch.setattr(
        st.artifacts,
        "load_manifest",
        lambda model_id: {"name": "test", "version": 1, "params": {}, "status": "active"},
    )
    bundle = {
        "feature_names": ["f1"],
        "fill_values": [0.0],
        "thresholds": {"buy": 0.5, "sell": 0.5},
        "horizon": 12,
        "feature_groups": [],
        "output_mode": "dual_binary",
        "trend_filter": trend_filter,
    }
    monkeypatch.setattr(st.artifacts, "load_bundle", lambda model_id: bundle)


def test_trend_gate_uses_numpy_array_without_ambiguity(monkeypatch):
    data = _make_data(direction=1.0)
    _install_fake_model(monkeypatch, data)
    model = st.AIModelStrategy("ai_test")
    model.prepare(data)
    result = model.evaluate_at(data, N - 2)
    # Yükselen trend: EMA20 > EMA50 > EMA200, kapı açık.
    assert result["buy_detail"]["trend_ok"] is True
    assert result["buy"] is True
    assert result["sell"] is False


def test_trend_gate_closed_when_trend_down(monkeypatch):
    data = _make_data(direction=-1.0)
    _install_fake_model(monkeypatch, data)
    model = st.AIModelStrategy("ai_test")
    model.prepare(data)
    result = model.evaluate_at(data, N - 2)
    assert result["buy_detail"]["trend_ok"] is False
    assert result["buy"] is False


def test_evaluate_at_out_of_range_index_does_not_crash(monkeypatch):
    data = _make_data()
    _install_fake_model(monkeypatch, data)
    model = st.AIModelStrategy("ai_test")
    model.prepare(data)
    result = model.evaluate_at(data, N + 5)
    assert result["buy"] is False
    assert result["sell"] is False
