"""Titiz zaman serisi eğitimi.

Akış:
1. Veri çekilir (kronolojik), seçilen özellik grupları hesaplanır.
2. Gelecek etiketleri üretilir (al / sat / nötr / gelecek getiri).
3. %70 öğrenme / %30 test. Öğrenmenin son %15'i validation (eşik ve tur
   seçimi) için ayrılır. Bölmeler arasında etiket ufku kadar embargo vardır.
4. Mimari tanımına göre model eğitilir (MLP veya GBM; iki başlı, üç sınıf
   veya regresyon).
5. Yinelemeli iyileştirme: eğitim kümesindeki işlemler "erken / geç /
   zamanında" olarak sınıflandırılır, ağırlıklar güncellenir ve model
   yeniden eğitilir. Tur seçimi yalnızca validation skoruyla yapılır.
6. Test kümesi **yalnızca bir kez** değerlendirilir.
7. Model aday olarak kaydedilir; panelden onaylanmadan botlara bağlanmaz.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.ai import artifacts
from app.ai.data import load_market_data
from app.ai.features import build_features
from app.ai.labels import action_targets, build_labels
from app.ai.model import (
    SKLEARN_AVAILABLE,
    AveragedModel,
    choose_threshold,
    classification_metrics,
    fit_model,
    predict_positive,
    predict_sequence,
    predict_signals,
    roc_auc,
    simulate_trades,
)
from app.ai.spec import spec_from_params, validate_spec
from app.ai.objective import (
    agreement,
    choose_agreement_threshold,
    objective_score,
    pivot_marks,
    robust_trading_score,
    trading_score,
)
from app.ai.timing import analyze_trades, summarize as summarize_timing


def _date(ms: Any) -> Optional[str]:
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(ms) / 1000.0, timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def _row_features(feature_names: List[str], payload: Dict[str, Any]) -> Optional[List[float]]:
    try:
        row = [float(payload[name]) if payload.get(name) is not None else np.nan for name in feature_names]
    except (TypeError, ValueError):
        return None
    if not any(np.isfinite(v) for v in row):
        return None
    return row


def _load_feedback(
    feature_names: List[str],
    coin: str,
    period: str,
    max_items: int = 3000,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Kapanan işlemleri ek eğitim örneği olarak hazırlar.

    Yalnızca aynı coin/periyot ve aynı özellik şemasındaki deneyimler alınır.
    Etiket, gerçekleşen K/Z'dir. Bu örnekler doğrulama/test kümelerine
    karıştırılmaz; sadece eğitim kümesine sınırlı ağırlıkla eklenir.
    """
    rows: List[List[float]] = []
    buy_y: List[int] = []
    sell_y: List[int] = []
    try:
        items = artifacts.list_experiences(None, limit=max_items)
    except Exception:
        items = []
    used = 0
    for item in items:
        if str(item.get("coin") or "").upper() != coin.upper():
            continue
        if str(item.get("period") or "") != period:
            continue
        pnl = item.get("pnl_pct")
        if pnl is None:
            continue
        row = _row_features(feature_names, item.get("features") or {})
        if row is None:
            continue
        win = 1 if float(pnl) > 0 else 0
        side = str(item.get("side") or "BUY").upper()
        rows.append(row)
        buy_y.append(win if side == "BUY" else 0)
        sell_y.append(win if side == "SELL" else 0)
        used += 1
    if not rows:
        return np.empty((0, len(feature_names))), np.empty(0, dtype=int), np.empty(0, dtype=int), 0
    return np.asarray(rows, dtype=float), np.asarray(buy_y, dtype=int), np.asarray(sell_y, dtype=int), used


def _classification_report(y: np.ndarray, p: np.ndarray, threshold: float) -> Dict[str, Any]:
    metrics = classification_metrics(y, p, threshold)
    auc = roc_auc(y, p)
    if auc is not None:
        metrics["roc_auc"] = round(auc, 4)
    return metrics


def _atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> float:
    """Medyan ATR yüzdesi (volatiliteye göre hedef/stop türetmek için)."""
    n = len(close)
    if n < length + 2:
        return 0.0
    prev = close[:-1]
    tr = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - prev),
            np.abs(low[1:] - prev),
        ]
    )
    atr = np.convolve(tr, np.ones(length) / length, mode="valid")
    denom = close[length:]
    mask = denom > 0
    if not mask.any():
        return 0.0
    pct = atr[mask] / denom[mask]
    return float(np.median(pct))


def _auto_moves(cfg: Dict[str, Any], high: np.ndarray, low: np.ndarray, close: np.ndarray) -> None:
    """Hedef/stop yüzdelerini volatiliteden türetir.

    Kâr odaklı (``excess_return``) hedefte amaç **trendi yakalamak**: hedef
    çok uzak (6×ATR), stop geniş (2,5×ATR) tutulur ve kâr takipli stopla
    korunur. Böylece tek bir mumun gürültüsünde pozisyondan atılmaz.
    """
    atr = _atr_pct(high, low, close)
    if atr <= 0:
        return
    kind = str(cfg.get("kind") or "local_min_max")
    profit_mode = kind in {"excess_return", "excess"}
    target_mult = 6.0 if profit_mode else 2.0
    stop_mult = 2.5 if profit_mode else 1.2
    cfg["atr_pct"] = round(atr, 5)
    cfg["target_move"] = round(min(0.5, max(0.002, atr * target_mult)), 5)
    cfg["stop_move"] = round(min(0.3, max(0.002, atr * stop_mult)), 5)
    cfg["moves_source"] = "atr"


def _validation_score(metrics: Dict[str, Any], min_trades: int) -> float:
    """Bir turun iyiliğini tek sayıya indirger (yalnızca validation)."""
    trades = int(metrics.get("trade_count") or 0)
    ret = float(metrics.get("total_return_pct") or 0.0)
    edge = float(metrics.get("edge_pct") or 0.0)
    win = float(metrics.get("win_rate") or 0.0)
    score = edge + 0.25 * ret + 0.02 * win
    if trades < min_trades:
        score -= (min_trades - trades) * 1.5
    return round(score, 4)


def _reweight_from_timing(
    weights_buy: np.ndarray,
    weights_sell: np.ndarray,
    timed: List[Dict[str, Any]],
    pos_of_abs: Dict[int, int],
    y_buy: np.ndarray,
    y_sell: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """İşlem zamanlama hatalarına göre örnek ağırlıklarını günceller.

    - Erken giriş: sinyal erken ateşlendi → o örneğin ağırlığı düşer.
    - Geç giriş: sinyal geç ateşlendi → ideal dip örneği güçlenir.
    - Erken çıkış (sinyalle): sat sinyali erken geldi → sat örneği zayıflar.
    - Geç çıkış (sinyalle): ideal zirve örneği güçlenir.

    Ağırlıklar [0.3, 3.0] aralığında tutulur ve ortalaması 1'e normalize edilir.
    """
    entry_factor = {"erken": 0.55, "geç": 1.30, "zamanında": 1.08}
    exit_factor = {"erken": 0.55, "geç": 1.30, "zamanında": 1.08}

    for item in timed:
        entry_idx = int(item.get("entry_idx") or 0)
        pos = pos_of_abs.get(entry_idx)
        if pos is not None and y_buy[pos] == 1:
            weights_buy[pos] *= entry_factor.get(item.get("entry_verdict"), 1.0)
        ideal_entry = int(item.get("ideal_entry_idx") or entry_idx)
        ideal_pos = pos_of_abs.get(ideal_entry)
        if ideal_pos is not None and y_buy[ideal_pos] == 1 and item.get("entry_verdict") in {"erken", "geç"}:
            weights_buy[ideal_pos] *= 1.25 if item.get("entry_verdict") == "geç" else 1.15

        if item.get("reason") == "signal":
            exit_idx = int(item.get("exit_idx") or 0)
            pos = pos_of_abs.get(exit_idx)
            if pos is not None and y_sell[pos] == 1:
                weights_sell[pos] *= exit_factor.get(item.get("exit_verdict"), 1.0)
            ideal_exit = int(item.get("ideal_exit_idx") or exit_idx)
            ideal_pos = pos_of_abs.get(ideal_exit)
            if ideal_pos is not None and y_sell[ideal_pos] == 1 and item.get("exit_verdict") in {"erken", "geç"}:
                weights_sell[ideal_pos] *= 1.25 if item.get("exit_verdict") == "geç" else 1.15

    def normalize(w: np.ndarray) -> np.ndarray:
        w = np.clip(np.asarray(w, dtype=float), 0.3, 3.0)
        mean = float(np.mean(w)) if len(w) else 1.0
        return w / mean if mean > 0 else w

    return normalize(weights_buy), normalize(weights_sell)


def _threshold_adjustment(timing: Dict[str, Any]) -> Dict[str, Any]:
    """Erken/geç giriş oranından eşik düzeltmesi üretir.

    Sinyaller sürekli erken geliyorsa daha güçlü sinyal istenir (eşik yukarı),
    sürekli geç geliyorsa eşik aşağı çekilir. Etki ±0.05 ile sınırlıdır.
    """
    entry = timing.get("entry") or {}
    total = int(entry.get("erken", 0)) + int(entry.get("geç", 0)) + int(entry.get("zamanında", 0))
    if total < 10:
        return {"delta": 0.0, "reason": "Yeterli işlem yok", "early_ratio": None, "late_ratio": None}
    early = float(entry.get("erken", 0)) / total
    late = float(entry.get("geç", 0)) / total
    # Erken sinyal çoğunluktaysa daha güçlü sinyal istenir (eşik yukarı).
    delta = max(-0.05, min(0.05, (early - late) * 0.05))
    return {
        "delta": round(delta, 4),
        "early_ratio": round(early, 3),
        "late_ratio": round(late, 3),
        "reason": (
            "Sinyaller erken geliyor → eşik yükseltildi"
            if delta > 0
            else "Sinyaller geç geliyor → eşik düşürüldü"
            if delta < 0
            else "Zamanlama dengeli"
        ),
    }


def _simulate(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    buy_prob: np.ndarray,
    sell_prob: np.ndarray,
    indices: np.ndarray,
    buy_threshold: float,
    sell_threshold: float,
    cfg: Dict[str, Any],
    trade_limit: int = 200,
    trend_ok: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    effective_sell = float(sell_threshold) if bool(cfg.get("sell_exit", True)) else 2.0
    return simulate_trades(
        close,
        high,
        low,
        buy_prob,
        sell_prob,
        indices,
        buy_threshold=buy_threshold,
        sell_threshold=effective_sell,
        horizon=int(cfg.get("horizon", 12)),
        fee=float(cfg.get("fee", 0.001)),
        slippage=float(cfg.get("slippage", 0.0005)),
        stop_move=float(cfg.get("stop_move", 0.01)),
        target_move=float(cfg.get("target_move", 0.02)),
        trade_limit=trade_limit,
        trend_ok=trend_ok,
        trailing_stop=float(cfg.get("trailing_stop") or 0.0),
        min_hold=int(cfg.get("min_hold") or 0),
        cooldown=int(cfg.get("cooldown") or 0),
        exit_on_regime=bool(cfg.get("exit_on_regime", False)),
    )


def _regime_gate(close: np.ndarray, band: float = 0.02) -> np.ndarray:
    """Histerezisli trend rejimi: EMA200 üstünde kal, altına inince çık.

    ``band`` = %2. Fiyat EMA200'ün %2 üstüne çıkınca rejim "açık" olur ve
    %2 altına inene kadar açık kalır. Bu, EMA200 etrafındaki testere
    sinyallerini (ve gereksiz işlem maliyetini) engeller.
    """
    from app.ai.labels import _ema

    close = np.asarray(close, dtype=float)
    ema = _ema(close, 200)
    out = np.zeros(len(close), dtype=bool)
    state = False
    for i in range(len(close)):
        e = ema[i]
        if not np.isfinite(e) or e <= 0:
            out[i] = state
            continue
        if close[i] > e * (1.0 + band):
            state = True
        elif close[i] < e * (1.0 - band):
            state = False
        out[i] = state
    return out


def _multi_window_quality(
    buy_full: np.ndarray,
    sell_full: np.ndarray,
    positions: np.ndarray,
    idx: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    buy_threshold: float,
    sell_threshold: float,
    cfg: Dict[str, Any],
    trend_ok: Optional[np.ndarray] = None,
    windows: int = 3,
) -> Dict[str, Any]:
    """Doğrulama bölgesini 3 parçaya bölüp işlem kalitesini ayrı ayrı ölçer.

    Test verisi hiç kullanılmaz. Tek bir şanslı dönem yerine **tutarlılık**
    ödüllendirilir. Olasılıklar önceden hesaplanmış tam seri dizileridir;
    bu yüzden eşik aramasında tekrar tekrar ölçmek ucuzdur.
    """
    positions = np.asarray(positions, dtype=int)
    if len(positions) < 120:
        return {"score": -50.0, "windows": 0}
    bounds = np.linspace(0, len(positions), int(windows) + 1).astype(int)
    metrics_list: List[Dict[str, Any]] = []
    bars_list: List[int] = []
    for k in range(int(windows)):
        seg = positions[bounds[k] : bounds[k + 1]]
        if len(seg) < 40:
            continue
        sim = _simulate(
            close, high, low, buy_full, sell_full, idx[seg],
            buy_threshold, sell_threshold, cfg, trend_ok=trend_ok,
        )
        metrics_list.append(sim["metrics"])
        bars_list.append(len(seg))
    return robust_trading_score(metrics_list, int(cfg.get("min_trades") or 6), bars_list)


def _refine_thresholds_trading(
    buy_full: np.ndarray,
    sell_full: np.ndarray,
    p_buy: np.ndarray,
    p_sell: np.ndarray,
    positions: np.ndarray,
    idx: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    thr_buy: float,
    thr_sell: float,
    cfg: Dict[str, Any],
    trend_ok: Optional[np.ndarray],
    best_quality: Dict[str, Any],
) -> tuple[float, float, Dict[str, Any]]:
    """Eşikleri işlem kalitesine göre ince ayarlar (koordinat araması).

    Yalnızca validation bölgesi kullanılır; test hiç görülmez. Amaç, F1'i
    değil **al-tut'u geçen** eşiği bulmaktır.
    """
    def quality(b: float, s: float) -> Dict[str, Any]:
        return _multi_window_quality(
            buy_full, sell_full, positions, idx, close, high, low, b, s, cfg,
            trend_ok=trend_ok,
        )

    if len(p_buy):
        # Rejimden bağımsız başlangıç: en yüksek conviction dilimi.
        rate = max(0.002, min(float(cfg.get("entry_rate") or 0.02), 0.2))
        thr_buy = float(np.quantile(p_buy, 1.0 - rate))
    best_b, best_s = float(thr_buy), float(thr_sell)
    best_q = best_quality
    best_score = float(best_quality.get("score") or -50.0)
    if len(p_buy) and len(p_sell):
        buy_grid = sorted({round(float(np.quantile(p_buy, q)), 4) for q in (0.98, 0.99, 0.995, 0.999)})
        sell_grid = sorted({round(float(np.quantile(p_sell, q)), 4) for q in (0.5, 0.8, 0.95)})
        for b in buy_grid:
            q = quality(b, best_s)
            score = float(q.get("score") or -50.0)
            if score > best_score + 0.05:
                best_score, best_q, best_b = score, q, b
        for sv in sell_grid:
            q = quality(best_b, sv)
            score = float(q.get("score") or -50.0)
            if score > best_score + 0.05:
                best_score, best_q, best_s = score, q, sv
    return best_b, best_s, best_q


def _fit_sequence_bundle(
    spec: Dict[str, Any],
    seq,
    train_positions: np.ndarray,
    y_train: np.ndarray,
    w_train: np.ndarray,
    val_positions: Optional[np.ndarray],
    y_val: Optional[np.ndarray],
    w_val: Optional[np.ndarray],
    seed: int,
    init_model: Optional[Any] = None,
) -> Dict[str, Any]:
    """LSTM/Transformer paketini eğitir (AL ve SAT birlikte)."""
    from app.ai.model import build_sequence_model

    model = build_sequence_model(spec, seq.features, seed=seed)
    X_tr = seq.windows(np.asarray(train_positions, dtype=int))
    X_va = None
    if val_positions is not None and len(val_positions):
        X_va = seq.windows(np.asarray(val_positions, dtype=int))
    model.fit(
        X_tr,
        y_train,
        sample_weight=w_train,
        X_val=X_va,
        y_val=y_val,
        sample_weight_val=w_val,
        init_model=init_model,
    )
    return {
        "output_mode": "dual_binary",
        "sequence_model": model,
        "seq_window": int(seq.window),
        "seq_engine": str(spec.get("engine") or "lstm"),
    }


def _targets_for(
    indices: np.ndarray,
    y_buy: np.ndarray,
    y_sell: np.ndarray,
    action: np.ndarray,
    future_return: np.ndarray,
) -> Dict[str, np.ndarray]:
    return {
        "buy": y_buy[indices],
        "sell": y_sell[indices],
        "action": action[indices],
        "return": future_return[indices],
    }


def _average_bundles(bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aynı mimarideki birden çok eğitimi olasılık ortalamasıyla birleştirir."""
    valid = [b for b in bundles if isinstance(b, dict) and b]
    if not valid:
        raise RuntimeError("Birleştirilecek model yok")
    if len(valid) == 1:
        return valid[0]
    mode = str(valid[0].get("output_mode") or "dual_binary")
    merged: Dict[str, Any] = {"output_mode": mode}
    if mode == "dual_binary":
        for key in ("buy_model", "sell_model"):
            merged[key] = AveragedModel([b[key] for b in valid])
    elif mode == "ternary":
        merged["action_model"] = AveragedModel([b["action_model"] for b in valid])
    else:
        merged["return_model"] = AveragedModel([b["return_model"] for b in valid])
        merged["prob_scale"] = valid[0].get("prob_scale")
    return merged


def _class_balance_weights(
    labels: np.ndarray,
    weights: np.ndarray,
    power: float = 0.6,
) -> np.ndarray:
    """Pozitif sınıfı ağırlıklandırarak dengesizliği telafi eder.

    Etiketlerin yalnızca ~%4'ü pozitif olduğu için ham log-kayıp neredeyse
    tamamen "hep 0 de" çözümünü ödüllendirir. ``power`` ile kısmi ters frekans
    uygulanır (1.0 = tam ters frekans, 0.0 = kapalı). Ağırlıkların ortalaması
    1'e çekilir; böylece öğrenme hızı ölçeklenmez. Yalnızca eğitim/validation
    etiketlerinden hesaplanır; test hiç görülmez.
    """
    y = np.asarray(labels, dtype=float).reshape(-1)
    w = np.asarray(weights, dtype=float).reshape(-1)
    if power <= 0 or len(y) == 0:
        return w
    pos = float(np.mean(y))
    if pos <= 1e-6 or pos >= 1.0 - 1e-6:
        return w
    ratio = min(((1.0 - pos) / pos) ** float(power), 25.0)
    boost = np.where(y >= 0.5, ratio, 1.0)
    mean = float(np.mean(boost))
    if mean > 0:
        boost = boost / mean
    return w * boost


def _fit_bundle(
    spec: Dict[str, Any],
    X_train: np.ndarray,
    t_train: Dict[str, np.ndarray],
    w_buy: np.ndarray,
    w_sell: np.ndarray,
    X_val: Optional[np.ndarray],
    t_val: Optional[Dict[str, np.ndarray]],
    w_val: Optional[np.ndarray],
    seed: int,
    init_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mimari tanımına göre model paketini eğitir.

    ``init_bundle`` verilirse (önceki nesil), uyumlu başlıklar sıcak başlatılır.
    """
    mode = str(spec.get("output_mode") or "dual_binary")
    init_bundle = init_bundle or {}
    val_buy = None if t_val is None else t_val["buy"]
    val_sell = None if t_val is None else t_val["sell"]
    if mode == "ternary":
        w_row = 0.5 * (w_buy + w_sell)
        mean = float(np.mean(w_row)) if len(w_row) else 1.0
        w_row = w_row / mean if mean > 0 else w_row
        model = fit_model(
            spec, "multiclass", X_train, t_train["action"],
            sample_weight=w_row,
            X_val=X_val, y_val=(None if t_val is None else t_val["action"]),
            sample_weight_val=w_val, n_classes=3, random_state=seed,
            init_model=init_bundle.get("action_model"),
        )
        return {"output_mode": mode, "action_model": model}
    if mode == "regression":
        w_row = 0.5 * (w_buy + w_sell)
        mean = float(np.mean(w_row)) if len(w_row) else 1.0
        w_row = w_row / mean if mean > 0 else w_row
        model = fit_model(
            spec, "regression", X_train, t_train["return"],
            sample_weight=w_row,
            X_val=X_val, y_val=(None if t_val is None else t_val["return"]),
            sample_weight_val=w_val, random_state=seed,
            init_model=init_bundle.get("return_model"),
        )
        pred = np.asarray(model.predict(X_train), dtype=float)
        scale = float(np.nanstd(pred)) or float(spec.get("target_move") or 0.01)
        return {"output_mode": mode, "return_model": model, "prob_scale": scale}
    buy_model = fit_model(
        spec, "binary", X_train, t_train["buy"],
        sample_weight=w_buy,
        X_val=X_val, y_val=val_buy, sample_weight_val=w_val,
        random_state=seed,
        init_model=init_bundle.get("buy_model"),
    )
    sell_model = fit_model(
        spec, "binary", X_train, t_train["sell"],
        sample_weight=w_sell,
        X_val=X_val, y_val=val_sell, sample_weight_val=w_val,
        random_state=seed + 1,
        init_model=init_bundle.get("sell_model"),
    )
    return {"output_mode": mode, "buy_model": buy_model, "sell_model": sell_model}


def _layers_metric(value: Any) -> Optional[List[int]]:
    """``layers`` metriğini her zaman liste (ya da None) olarak döndürür.

    Transformer eski sürümlerde blok sayısını (int) yazıyordu; panel bunu
    katman listesi sanıp ``.join`` çağırınca çöküyordu. Burada normalize
    edilir; sıra modellerinin boyutları ayrı alanlarda tutulur.
    """
    if isinstance(value, (list, tuple)):
        out: List[int] = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out or None
    return None


def _model_info(bundle: Dict[str, Any], feature_names: List[str]) -> Dict[str, Any]:
    """Panelde gösterilecek model bilgisi (katmanlar, epoch, önem)."""
    info: Dict[str, Any] = {"params": 0, "models": []}
    for key, model in bundle.items():
        if not hasattr(model, "predict_proba") and not hasattr(model, "predict"):
            continue
        if key in {"output_mode", "prob_scale"}:
            continue
        item: Dict[str, Any] = {"head": key, "type": type(model).__name__}
        # Toplulukta ayrıntılar ilk üyeden alınır; üye sayısı ayrıca yazılır.
        member = model
        if isinstance(model, AveragedModel) and getattr(model, "models", None):
            item["ensemble"] = len(model.models)
            member = model.models[0]
        elif hasattr(model, "models") and getattr(model, "models", None) and hasattr(model.models[0], "info"):
            item["ensemble"] = len(model.models)
            member = model.models[0]
        if hasattr(member, "info"):
            try:
                minfo = member.info()
                item.update({k: v for k, v in minfo.items() if k != "type"})
                item["type"] = minfo.get("type") or item["type"]
            except Exception:
                pass
        if hasattr(member, "hidden_layers"):
            item["layers"] = [int(v) for v in member.hidden_layers]
            item["activation"] = getattr(member, "activation", None)
            item["dropout"] = getattr(member, "dropout", None)
            item["params"] = int(
                sum(int(w.size) for w in getattr(member, "weights_", []))
                + sum(int(b.size) for b in getattr(member, "biases_", []))
            )
        history = getattr(member, "history", None)
        if history:
            item["epochs_run"] = len(history)
            item["best_epoch"] = getattr(member, "best_epoch", len(history))
            item["stopped_early"] = bool(getattr(member, "stopped_early", False))
            item["warm_started"] = bool(getattr(member, "warm_started", False))
            item["curve"] = history[-200:]
        # Özellik önemi: GBM'de gerçek önem, MLP'de ilk katman ağırlık
        # büyüklüğü (açıklayıcı bir vekil).
        importance = None
        if hasattr(member, "feature_importances_"):
            try:
                importance = np.asarray(member.feature_importances_, dtype=float)
            except Exception:
                importance = None
        elif getattr(member, "Wx", None) is not None:
            # LSTM: giriş izdüşüm ağırlıkları (özellik önemi vekili)
            try:
                importance = np.abs(np.asarray(member.Wx)).sum(axis=1)
            except Exception:
                importance = None
        elif isinstance(getattr(member, "params", None), dict) and "Win" in member.params:
            # Transformer: giriş izdüşümü
            try:
                importance = np.abs(np.asarray(member.params["Win"])).sum(axis=1)
            except Exception:
                importance = None
        elif getattr(member, "weights_", None):
            try:
                importance = np.abs(member.weights_[0]).sum(axis=1)
            except Exception:
                importance = None
        if importance is not None and len(importance) == len(feature_names) and importance.sum() > 0:
            norm = importance / importance.sum()
            order = np.argsort(norm)[::-1][:15]
            item["top_features"] = [
                {"feature": feature_names[int(i)], "weight": round(float(norm[int(i)]), 4)}
                for i in order
            ]
        info["params"] += int(item.get("params") or 0)
        info["models"].append(item)
    return info


def _multi_window_agreement_f1(
    bundle: Dict[str, Any],
    X: np.ndarray,
    idx: np.ndarray,
    positions: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    cfg: Dict[str, Any],
    windows: int = 3,
    probs_fn=None,
) -> Optional[float]:
    """Modeli doğrulama bölgesinin birkaç ayrı penceresinde ölçer.

    Tek bir validation dilimi şanslı olabilir; model seçimini tek pencereye
    bağlamak yanıltıcıdır. Burada öğrenme bölgesi ``windows`` parçaya bölünür
    ve her parça için uyum F1'i hesaplanıp ortalanır. **Test verisi hiç
    kullanılmaz.** Ağırlıklar yeniden eğitilmez; yalnızca tahmin yapılır,
    dolayısıyla maliyeti çok düşüktür.
    """
    positions = np.asarray(positions, dtype=int)
    if len(positions) < 90 or windows < 2:
        return None
    marks = pivot_marks(high, low, int(cfg["extreme_window"]))
    bounds = np.linspace(0, len(positions), int(windows) + 1).astype(int)
    scores: List[float] = []
    for k in range(int(windows)):
        seg = positions[bounds[k] : bounds[k + 1]]
        if len(seg) < 30:
            continue
        if probs_fn is not None:
            p_buy, p_sell = probs_fn(seg)
        else:
            p_buy, p_sell = predict_signals(bundle, X[seg])
        pick_buy = choose_agreement_threshold(
            p_buy, idx[seg], marks["buy"],
            tolerance=int(cfg["agree_tolerance"]), min_precision=cfg["min_precision"],
        )
        pick_sell = choose_agreement_threshold(
            p_sell, idx[seg], marks["sell"],
            tolerance=int(cfg["agree_tolerance"]), min_precision=cfg["min_precision"],
        )
        scores.append((float(pick_buy.get("f1") or 0.0) + float(pick_sell.get("f1") or 0.0)) / 2.0)
    if not scores:
        return None
    return round(float(np.mean(scores)), 4)


def _fold_summary(folds: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [f for f in folds if isinstance(f, dict) and f.get("trading")]
    if not valid:
        return {"folds": 0}
    returns = [float(f["trading"].get("total_return_pct") or 0.0) for f in valid]
    edges = [float(f["trading"].get("edge_pct") or 0.0) for f in valid]
    trades = [int(f["trading"].get("trade_count") or 0) for f in valid]
    return {
        "folds": len(valid),
        "avg_return_pct": round(sum(returns) / len(returns), 2),
        "avg_edge_pct": round(sum(edges) / len(edges), 2),
        "positive_folds": sum(1 for r in returns if r > 0),
        "avg_trade_count": round(sum(trades) / len(trades), 1),
    }


def _walk_forward(
    spec: Dict[str, Any],
    X: np.ndarray,
    y_buy: np.ndarray,
    y_sell: np.ndarray,
    action: np.ndarray,
    future_return: np.ndarray,
    idx: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    opendate: List[Any],
    cfg: Dict[str, Any],
    folds: int,
    embargo: int,
) -> List[Dict[str, Any]]:
    """Genişleyen pencereli, embargolu zaman serisi çapraz doğrulaması."""
    if folds <= 0:
        return []
    n = len(idx)
    if n < 1200:
        return [{"skipped": "Walk-forward için en az 1200 geçerli satır gerekir"}]
    start_pos = max(400, int(n * 0.5))
    edges = np.linspace(start_pos, n, folds + 1, dtype=int)
    out: List[Dict[str, Any]] = []
    for k in range(folds):
        test_start, test_end = int(edges[k]), int(edges[k + 1])
        if test_end - test_start < 100:
            continue
        train_end_pos = test_start
        train_end_abs = int(idx[train_end_pos]) - embargo
        train_mask = idx < train_end_abs
        train_pos = np.where(train_mask)[0]
        if len(train_pos) < 500:
            continue
        val_count = max(150, int(len(train_pos) * 0.15))
        val_pos = train_pos[-val_count:]
        core_pos = train_pos[:-val_count]
        if len(core_pos) < 300:
            continue
        t_core = _targets_for(core_pos, y_buy, y_sell, action, future_return)
        t_val = _targets_for(val_pos, y_buy, y_sell, action, future_return)
        w = np.ones(len(core_pos))
        wv = np.ones(len(val_pos))
        bundle = _fit_bundle(
            spec, X[core_pos], t_core, w, w, X[val_pos], t_val, wv, seed=42 + k * 7
        )
        p_buy_val, p_sell_val = predict_signals(bundle, X[val_pos])
        if str(cfg.get("kind")) in {"local_min_max", "local_extreme"}:
            marks = pivot_marks(high, low, int(cfg.get("extreme_window") or 13))
            thr_buy = float(
                choose_agreement_threshold(
                    p_buy_val, idx[val_pos], marks["buy"],
                    tolerance=int(cfg.get("agree_tolerance") or 2),
                    min_precision=float(cfg.get("min_precision", 0.35)),
                )["threshold"]
            )
            thr_sell = float(
                choose_agreement_threshold(
                    p_sell_val, idx[val_pos], marks["sell"],
                    tolerance=int(cfg.get("agree_tolerance") or 2),
                    min_precision=float(cfg.get("min_precision", 0.35)),
                )["threshold"]
            )
        else:
            thr_buy, _ = choose_threshold(t_val["buy"], p_buy_val, float(cfg.get("min_precision", 0.35)))
            thr_sell, _ = choose_threshold(t_val["sell"], p_sell_val, float(cfg.get("min_precision", 0.35)))
        test_pos = np.arange(test_start, test_end)
        t_test = _targets_for(test_pos, y_buy, y_sell, action, future_return)
        p_buy, p_sell = predict_signals(bundle, X[test_pos])
        buy_full = np.zeros(len(close))
        sell_full = np.zeros(len(close))
        buy_full[idx[test_pos]] = p_buy
        sell_full[idx[test_pos]] = p_sell
        sim = _simulate(close, high, low, buy_full, sell_full, idx[test_pos], thr_buy, thr_sell, cfg)
        out.append(
            {
                "fold": k + 1,
                "train_rows": int(len(core_pos)),
                "validation_rows": int(len(val_pos)),
                "test_rows": int(len(test_pos)),
                "test_start": _date(opendate[int(idx[test_start])]) if opendate else None,
                "thresholds": {"buy": thr_buy, "sell": thr_sell},
                "buy": _classification_report(t_test["buy"], p_buy, thr_buy),
                "sell": _classification_report(t_test["sell"], p_sell, thr_sell),
                "trading": sim["metrics"],
            }
        )
    return out


def train_model(params: Dict[str, Any]) -> Dict[str, Any]:
    """Panelden gelen mimari ve eğitim parametreleriyle model üretir."""
    coin = str(params.get("coin") or "BTCUSDT").upper()
    period = str(params.get("period") or "1h")
    limit = int(params.get("limit") or 20000)
    source = str(params.get("source") or "binance")
    csv_path = str(params.get("csv_path") or "")
    spec = spec_from_params(params)
    retrain_id = str(params.get("retrain_model_id") or "").strip() or None
    retrain_manifest = None
    if retrain_id:
        # Aynı modeli tekrar eğitirken mimari/kimlik mevcut modelden alınır;
        # yalnızca veri ve eğitim bütçesi değişebilir.
        retrain_manifest = artifacts.load_manifest(retrain_id)
        if not retrain_manifest:
            raise ValueError(f"Yeniden eğitilecek model bulunamadı: {retrain_id}")
        existing_params = retrain_manifest.get("params") or {}
        merged = {**existing_params, **{k: v for k, v in params.items() if v not in (None, "")}}
        spec = spec_from_params({**merged, "spec": existing_params.get("spec") or params.get("spec")})
        params = {**merged, "spec": spec}
    errors = validate_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))

    parent_id = str(params.get("parent_model_id") or "") or None
    warm_start = bool(params.get("warm_start", True))
    generation = max(1, int(params.get("generation") or 1))
    skip_test = bool(params.get("skip_test", False))
    # Aynı modeli tekrar eğit: kimlik korunur, sürüm artar, ağırlıklar devralınır.
    if retrain_id:
        parent_id = retrain_id
        warm_start = True
    if retrain_manifest:
        generation = int(retrain_manifest.get("version") or 1) + 1

    # Hedef türü: sıra modelleri ve otomatik arama için kâr odaklı
    # ``excess_return``; Local_Min_Max taklidi istenirse o korunur.
    engine_name = str(spec.get("engine") or "mlp")
    default_kind = "excess_return" if engine_name in {"lstm", "transformer"} else "local_min_max"
    kind = str(params.get("label_kind") or default_kind)
    default_horizon = 24 if kind in {"excess_return", "excess"} else 12
    default_window = {"15m": 10, "1h": 13, "4h": 10, "1d": 7}.get(str(period), 13)
    cfg = {
        "kind": kind,
        "horizon": max(2, min(int(params.get("horizon") or default_horizon), 500)),
        "target_move": max(0.0005, min(float(params.get("target_move") or 0.01), 0.5)),
        "stop_move": max(0.0005, min(float(params.get("stop_move") or 0.01), 0.5)),
        "extreme_window": max(2, min(int(params.get("extreme_window") or default_window), 100)),
        "extreme_tolerance": max(0.0, min(float(params.get("proximity_band") or 0.004), 0.05)),
        "proximity_band": max(0.0, min(float(params.get("proximity_band") or 0.004), 0.05)),
        "agree_tolerance": max(0, min(int(params.get("agree_tolerance") or 2), 20)),
        "excess_quantile": max(0.5, min(float(params.get("excess_quantile") or 0.65), 0.95)),
        "trend_gate": bool(params.get("trend_gate", True)),
        "dip_gate": bool(params.get("dip_gate", True)),
        "top_gate": bool(params.get("top_gate", True)),
        "label_train_frac": max(0.3, min(float(params.get("label_train_frac") or 0.55), 0.9)),
        "fee": max(0.0, min(float(params.get("fee") or 0.001), 0.05)),
        "slippage": max(0.0, min(float(params.get("slippage") or 0.0005), 0.05)),
        "min_precision": max(0.05, min(float(params.get("min_precision") or 0.35), 0.95)),
        "walk_forward": bool(params.get("walk_forward", True)),
        "folds": max(0, min(int(params.get("folds") or 3), 6)),
        "use_feedback": bool(params.get("use_feedback", True)),
        "feedback_weight": max(0.0, min(float(params.get("feedback_weight") or 0.5), 2.0)),
        "refine": bool(params.get("refine", True)),
        "iterations": max(1, min(int(params.get("iterations") or 5), 12)),
        "patience": max(1, min(int(params.get("patience") or 2), 6)),
        "min_delta": max(0.0, min(float(params.get("min_delta") or 0.02), 5.0)),
        "timing_tolerance": max(0.0005, min(float(params.get("timing_tolerance") or 0.004), 0.05)),
        "min_trades": max(1, min(int(params.get("min_trades") or 8), 5000)),
        "threshold_adjust": bool(params.get("threshold_adjust", True)),
        "auto_moves": bool(params.get("auto_moves", True)),
        # Her tekrar eğitim turu farklı bir başlangıç sırası görsün; aynı veri
        # ve aynı tohumla birebir aynı model üretilirdi.
        "seed_offset": int(params.get("seed_offset") or 0),
        "focus": max(0.0, min(float(params.get("focus") or 0.0), 3.0)),
        # Sınıf dengesizliği telafisi (0 = kapalı, 1 = tam ters frekans).
        "class_balance": max(0.0, min(float(params.get("class_balance", 0.6)), 1.0)),
        # Nihai modelde tohum topluluğu (1 = tek model).
        "ensemble": max(1, min(int(params.get("ensemble") or 1), 5)),
        # Trend kapısı ve takipli stop: genel trende göre işlem.
        "trend_filter": bool(params.get("trend_filter", True)),
        "trailing_stop": max(0.0, min(float(params.get("trailing_stop") or 0.0), 0.5)),
        "min_hold": max(0, min(int(params.get("min_hold") or 0), 500)),
        "cooldown": max(0, min(int(params.get("cooldown") or 0), 500)),
        "regime_band": max(0.0, min(float(params.get("regime_band") or 0.02), 0.2)),
        # Kâr odaklı modda çıkış rejim kırılımı + takipli stoptur; zayıf
        # "sat" sinyali trendi erken kesmesin.
        "exit_on_regime": bool(params.get("exit_on_regime", True)),
        "sell_exit": bool(params.get("sell_exit", False)),
        # Giriş seçiciliği: doğrulamada en yüksek olasılıklı %2'lik dilim.
        "entry_rate": max(0.002, min(float(params.get("entry_rate") or 0.02), 0.2)),
        # Sıra modeli örnek bütçesi (maliyet kontrolü).
        "seq_max_samples": max(500, min(int(params.get("seq_max_samples") or 5000), 40000)),
        "seq_stride": max(1, min(int(params.get("seq_stride") or 1), 8)),
    }
    name = str(params.get("name") or f"{coin} {period} AI").strip()[:80]
    if retrain_manifest:
        # Aynı modeli tekrar eğitirken ad korunur.
        name = str(retrain_manifest.get("name") or name)

    # Fiyat verisi: sabit veri seti varsa ağa hiç çıkılmaz.
    dataset_id = str(params.get("dataset_id") or "").strip()
    auto_snapshot = bool(params.get("auto_snapshot", False))
    refresh_data = bool(params.get("refresh_data", False))
    # CSV açıkça seçildiyse dosya kazanır; snapshot/ağ devreye girmez.
    use_csv = source == "csv" and bool(csv_path)
    if not use_csv and (dataset_id or auto_snapshot):
        from app.ai import datasets

        data, data_meta = datasets.resolve(
            coin,
            period,
            limit,
            dataset_id=dataset_id,
            refresh=refresh_data,
            auto_snapshot=auto_snapshot,
            source=source,
            asset_class=str(params.get("asset_class") or ""),
        )
        coin = str(data_meta.get("coin") or coin).upper()
        period = str(data_meta.get("period") or period)
    else:
        data, data_meta = load_market_data(
            coin, period, limit, source, csv_path,
            asset_class=str(params.get("asset_class") or ""),
        )
        data_meta = dict(data_meta)
        data_meta.setdefault("dataset_id", None)
        data_meta.setdefault("reused", False)
    feature = build_features(data, spec["feature_groups"])
    if not feature["feature_names"]:
        raise RuntimeError("Seçilen özellik grupları hiç kolon üretmedi")
    close = feature["close"]
    high = feature["high"]
    low = feature["low"]
    # Hedef/stop: kullanıcı vermediyse volatiliteden türet (etiketlerden önce).
    if cfg["auto_moves"] and not (params.get("target_move") and params.get("stop_move")):
        _auto_moves(cfg, high, low, close)
    labels = build_labels(data["close"], data["high"], data["low"], cfg)
    X = feature["X"]
    feature_names = feature["feature_names"]
    n = len(close)
    action = action_targets(labels)

    valid = np.arange(n) >= int(feature["warmup"])
    valid &= labels["buy"] >= 0
    valid &= labels["sell"] >= 0
    valid &= np.isfinite(close)
    # Regresyon hedefi ufkun sonunu gerektirir.
    valid &= np.isfinite(labels["future_return"])
    idx = np.where(valid)[0]
    if len(idx) < 800:
        raise RuntimeError(
            f"Yeterli geçerli satır yok ({len(idx)}). Daha uzun geçmiş veya daha kısa horizon seçin."
        )

    y_buy = labels["buy"][idx].astype(int)
    y_sell = labels["sell"][idx].astype(int)
    y_action = action[idx]
    y_return = labels["future_return"][idx].astype(float)
    X_valid = X[idx]

    # Etiketin kesinleşmesi için gereken ileri bakış. Local_Min_Max etiketinde
    # bu, pivot penceresidir (horizon değil); yanlış seçmek sızıntıya yol açar.
    if cfg["kind"] in {"local_min_max", "local_extreme"}:
        label_lookahead = max(int(cfg["extreme_window"]), int(cfg["horizon"]))
    else:
        label_lookahead = int(cfg["horizon"])
    embargo = label_lookahead + 2

    # %55 öğrenme / %15 validation / %30 test (kronolojik, karıştırma yok).
    pos1 = int(len(idx) * 0.55)
    pos2 = int(len(idx) * 0.70)
    split1_abs = int(idx[pos1])
    split2_abs = int(idx[pos2])
    train_pos = np.where(idx < split1_abs - embargo)[0]
    val_pos = np.where((idx >= split1_abs) & (idx < split2_abs - embargo))[0]
    test_pos = np.where(idx >= split2_abs)[0]
    if len(train_pos) < 400 or len(val_pos) < 100 or len(test_pos) < 100:
        raise RuntimeError(
            f"Bölünmüş kümeler çok küçük (train={len(train_pos)}, val={len(val_pos)}, test={len(test_pos)})"
        )

    X_train = X_valid[train_pos]
    X_val = X_valid[val_pos]
    X_test = X_valid[test_pos]
    t_train = _targets_for(train_pos, y_buy, y_sell, y_action, y_return)
    t_val = _targets_for(val_pos, y_buy, y_sell, y_action, y_return)
    t_test = _targets_for(test_pos, y_buy, y_sell, y_action, y_return)

    # ------------------------------------------------------------------
    # Sıra (LSTM/Transformer) hazırlığı ve ortak olasılık arayüzü
    # ------------------------------------------------------------------
    use_seq = str(spec.get("engine") or "mlp") in {"lstm", "transformer"}
    seq = None
    row_of_abs = {int(a): k for k, a in enumerate(idx)}
    if use_seq:
        from app.ai.sequence import SequenceData, subsample

        seq = SequenceData(X, window=int(spec.get("seq_window") or 24))
        seq.fit_scaler(idx[train_pos])
        # Sıra modelleri pencereye oturmayan geri besleme satırlarını kullanmaz.
        cfg["use_feedback"] = False
        # Walk-forward her kat için yeniden eğitim demek; sıra modellerinde
        # maliyet çok yüksek. Bunun yerine 3 pencereli sağlam değerlendirme
        # kullanılır (test yine hiç görülmez).
        cfg["walk_forward"] = False

    def probs_for(bundle: Dict[str, Any], abs_positions: np.ndarray) -> tuple:
        """Verilen mutlak bar konumları için (AL, SAT) olasılıkları."""
        pos = np.asarray(abs_positions, dtype=int)
        if use_seq:
            return predict_sequence(bundle, seq, pos)
        rows = np.array([row_of_abs[int(p)] for p in pos], dtype=int)
        return predict_signals(bundle, X_valid[rows])

    trend_ok_series = labels.get("trend_up")
    if cfg["trend_filter"]:
        trend_ok = (
            np.asarray(trend_ok_series, dtype=bool)
            if trend_ok_series is not None
            else _regime_gate(close, float(cfg.get("regime_band") or 0.02))
        )
    else:
        trend_ok = None

    # Canlı işlemlerden öğrenme: yalnızca eğitim kümesine, sınırlı oranda.
    feedback_used = 0
    w_buy = np.ones(len(X_train), dtype=float)
    w_sell = np.ones(len(X_train), dtype=float)
    if cfg["use_feedback"]:
        X_fb, yb_fb, ys_fb, feedback_used = _load_feedback(feature_names, coin, period)
        cap = min(1500, max(0, int(len(X_train) * 0.20)))
        if feedback_used and cap > 0:
            take = min(feedback_used, cap)
            X_fb, yb_fb, ys_fb = X_fb[-take:], yb_fb[-take:], ys_fb[-take:]
            feedback_used = take
            X_train = np.vstack([X_train, X_fb])
            t_train["buy"] = np.concatenate([t_train["buy"], yb_fb])
            t_train["sell"] = np.concatenate([t_train["sell"], ys_fb])
            # Deneyimlerin sınıf/regresyon hedefi: kazanç → alım, zarar → satım.
            fb_action = np.where(yb_fb == 1, 1, np.where(ys_fb == 1, 2, 0)).astype(int)
            t_train["action"] = np.concatenate([t_train["action"], fb_action])
            t_train["return"] = np.concatenate(
                [t_train["return"], np.where(yb_fb == 1, 1.0, -1.0) * float(cfg["target_move"])]
            )
            extra = np.full(take, float(cfg["feedback_weight"]))
            w_buy = np.concatenate([w_buy, extra])
            w_sell = np.concatenate([w_sell, extra])
        else:
            feedback_used = 0

    # Eksik değerler yalnızca eğitim kümesinden öğrenilen medyanla doldurulur.
    fill_values = np.nanmedian(X_train, axis=0)
    fill_values = np.where(np.isfinite(fill_values), fill_values, 0.0)
    X_train = np.where(np.isfinite(X_train), X_train, fill_values)
    X_val = np.where(np.isfinite(X_val), X_val, fill_values)
    X_test = np.where(np.isfinite(X_test), X_test, fill_values)
    X_valid = np.where(np.isfinite(X_valid), X_valid, fill_values)

    base_count = int(len(train_pos))
    pos_of_abs = {int(idx[train_pos[i]]): i for i in range(base_count)}
    w_val = np.ones(len(X_val), dtype=float)

    # Sınıf dengesizliği: eğitim ve validation ağırlıkları yalnızca kendi
    # etiketlerinden hesaplanır (test hiç kullanılmaz). Bu olmadan model
    # neredeyse her mumda "0" der ve F1 düşük kalır.
    balance = float(cfg.get("class_balance") or 0.0)
    if balance > 0:
        w_buy = _class_balance_weights(t_train["buy"], w_buy, balance)
        w_sell = _class_balance_weights(t_train["sell"], w_sell, balance)
        # Validation'da tek ağırlık vektörü iki başlığa da verilir; AL/SAT
        # pozitif oranları birbirine çok yakın olduğu için bir kez uygulanır.
        w_val = _class_balance_weights(t_val["buy"], w_val, balance)

    # Önceki nesil (varsa) sıcak başlangıç için yüklenir. Aynı mimari ve
    # özellik şeması değilse sessizce sıfırdan eğitime düşer.
    init_bundle: Optional[Dict[str, Any]] = None
    lineage: Dict[str, Any] = {
        "parent_id": parent_id,
        "generation": generation,
        "warm_start_requested": bool(warm_start and parent_id),
        "warm_start_used": False,
        "warm_start_note": "Önceki nesil yok",
        "parent_validation": None,
        "parent_test": None,
    }
    if warm_start and parent_id:
        try:
            parent_manifest = artifacts.load_manifest(parent_id)
            parent_bundle = artifacts.load_bundle(parent_id)
        except Exception as exc:  # noqa: BLE001
            parent_manifest, parent_bundle = None, None
            lineage["warm_start_note"] = f"Önceki model yüklenemedi: {exc}"
        if parent_manifest and parent_bundle:
            parent_features = list(parent_bundle.get("feature_names") or [])
            if parent_features and parent_features != feature_names:
                lineage["warm_start_note"] = "Özellik şeması farklı (mimari değişmiş)"
            else:
                init_bundle = parent_bundle
                lineage["warm_start_used"] = True
                lineage["warm_start_note"] = "Önceki nesilden ince ayar"
                parent_metrics = parent_manifest.get("metrics") or {}
                lineage["parent_validation"] = parent_metrics.get("validation")
                lineage["parent_test"] = parent_metrics.get("test")

    # Hata odaklı öğrenme: aynı veri kalır, ama önceki neslin eğitim kümesinde
    # yanıldığı örnekler daha yüksek ağırlıkla gösterilir. Böylece tekrar
    # eğitim "aynı modeli kopyalamak" yerine gerçekten hatalarına odaklanır.
    focus = cfg["focus"]
    if focus > 0 and init_bundle is not None and not use_seq:
        try:
            p_buy_old, p_sell_old = predict_signals(init_bundle, X_train[:base_count])
            err_buy = np.abs(np.asarray(p_buy_old, dtype=float) - t_train["buy"][:base_count])
            err_sell = np.abs(np.asarray(p_sell_old, dtype=float) - t_train["sell"][:base_count])
            w_buy[:base_count] = w_buy[:base_count] * (1.0 + focus * err_buy)
            w_sell[:base_count] = w_sell[:base_count] * (1.0 + focus * err_sell)
            # Ölçek korunur: ağırlık ortalaması 1'e çekilir, öğrenme hızı şişmez.
            mean_buy = float(np.mean(w_buy[:base_count])) or 1.0
            mean_sell = float(np.mean(w_sell[:base_count])) or 1.0
            w_buy[:base_count] /= mean_buy
            w_sell[:base_count] /= mean_sell
            lineage["focus"] = {
                "weight": round(focus, 3),
                "mean_error": round(float(np.mean((err_buy + err_sell) / 2.0)), 4),
                "boosted": int(np.sum(1.0 + focus * (err_buy + err_sell) / 2.0 > 1.25)),
            }
        except Exception as exc:  # noqa: BLE001 - odak hesabı eğitimi durdurmasın
            lineage["focus"] = {"weight": 0.0, "error": str(exc)[:150]}
    else:
        lineage["focus"] = {"weight": 0.0}

    val_positions = np.arange(len(val_pos))
    parent_robust_f1: Optional[float] = None
    if init_bundle is not None:
        try:
            parent_robust_f1 = _multi_window_agreement_f1(
                init_bundle, X_valid[val_pos], idx[val_pos], val_positions, high, low, cfg
            )
        except Exception:  # noqa: BLE001 - ölçüm başarısızsa karar validation'a düşer
            parent_robust_f1 = None
    lineage["parent_robust_f1"] = parent_robust_f1

    total_iterations = int(cfg["iterations"]) if cfg["refine"] else 1
    if use_seq:
        # Sıra modelleri tek eğitimde uzun ve pahalıdır; 1-2 tur yeterli.
        total_iterations = min(total_iterations, 2)
    best: Optional[Dict[str, Any]] = None
    no_improve = 0
    history: List[Dict[str, Any]] = []
    timing_final: Dict[str, Any] = {}

    train_abs = idx[train_pos]
    val_abs = idx[val_pos]
    seq_sel = subsample(np.arange(len(train_abs)), cfg["seq_max_samples"], cfg["seq_stride"]) if use_seq else None

    for iteration in range(1, total_iterations + 1):
        start_from = init_bundle if iteration == 1 else (best or {}).get("bundle")
        seed = 100 + iteration * 10 + int(cfg["seed_offset"])
        if use_seq:
            y_tr = np.stack([t_train["buy"][seq_sel], t_train["sell"][seq_sel]], axis=1)
            w_tr = np.stack([w_buy[seq_sel], w_sell[seq_sel]], axis=1)
            y_va = np.stack([t_val["buy"], t_val["sell"]], axis=1)
            w_va = np.stack([w_val, w_val], axis=1)
            bundle = _fit_sequence_bundle(
                spec, seq, train_abs[seq_sel], y_tr, w_tr, val_abs, y_va, w_va,
                seed=seed, init_model=(start_from or {}).get("sequence_model"),
            )
        else:
            bundle = _fit_bundle(
                spec, X_train, t_train, w_buy, w_sell, X_val, t_val, w_val,
                seed=seed, init_bundle=start_from,
            )

        p_buy_val, p_sell_val = probs_for(bundle, val_abs)
        if cfg["kind"] in {"local_min_max", "local_extreme"}:
            # Eşikleri doğrudan Local_Min_Max uyumuna göre seç.
            marks = pivot_marks(high, low, int(cfg["extreme_window"]))
            pick_buy = choose_agreement_threshold(
                p_buy_val, val_abs, marks["buy"],
                tolerance=int(cfg["agree_tolerance"]), min_precision=cfg["min_precision"],
            )
            pick_sell = choose_agreement_threshold(
                p_sell_val, val_abs, marks["sell"],
                tolerance=int(cfg["agree_tolerance"]), min_precision=cfg["min_precision"],
            )
            thr_buy = float(pick_buy["threshold"])
            thr_sell = float(pick_sell["threshold"])
        else:
            thr_buy, _ = choose_threshold(t_val["buy"], p_buy_val, cfg["min_precision"])
            thr_sell, _ = choose_threshold(t_val["sell"], p_sell_val, cfg["min_precision"])

        buy_val_full = np.zeros(n)
        sell_val_full = np.zeros(n)
        buy_val_full[val_abs] = p_buy_val
        sell_val_full[val_abs] = p_sell_val

        val_agreement = agreement(
            p_buy_val,
            p_sell_val,
            val_abs,
            high,
            low,
            buy_threshold=thr_buy,
            sell_threshold=thr_sell,
            window=int(cfg["extreme_window"]),
            tolerance=int(cfg["agree_tolerance"]),
        )

        # Ana ölçüt: 3 ayrı validation penceresinde işlem kalitesi (test yok).
        quality = _multi_window_quality(
            buy_val_full, sell_val_full, val_abs, idx, close, high, low,
            thr_buy, thr_sell, cfg, trend_ok=trend_ok,
        )
        thr_buy, thr_sell, quality = _refine_thresholds_trading(
            buy_val_full, sell_val_full, p_buy_val, p_sell_val, val_abs, idx,
            close, high, low, thr_buy, thr_sell, cfg, trend_ok, quality,
        )
        buy_val_metrics = _classification_report(t_val["buy"], p_buy_val, thr_buy)
        sell_val_metrics = _classification_report(t_val["sell"], p_sell_val, thr_sell)
        val_sim = _simulate(
            close, high, low, buy_val_full, sell_val_full, val_abs,
            thr_buy, thr_sell, cfg, trend_ok=trend_ok,
        )

        score = float(quality.get("score") or -50.0)
        if cfg["kind"] in {"local_min_max", "local_extreme"}:
            # Uyum ikincil ama yine de puanı biraz etkiler.
            score += 6.0 * float(val_agreement.get("f1") or 0.0)

        # Hata analizi yalnızca eğitim kümesinde yapılır.
        p_buy_train, p_sell_train = probs_for(bundle, train_abs)
        buy_train_full = np.zeros(n)
        sell_train_full = np.zeros(n)
        buy_train_full[train_abs] = p_buy_train
        sell_train_full[train_abs] = p_sell_train
        train_sim = _simulate(
            close, high, low, buy_train_full, sell_train_full, train_abs,
            thr_buy, thr_sell, cfg, trade_limit=100_000, trend_ok=trend_ok,
        )
        timed = analyze_trades(
            train_sim["trades"], high, low,
            window=int(cfg["horizon"]), tolerance=float(cfg["timing_tolerance"]),
        )
        timing_summary = summarize_timing(timed)

        history.append(
            {
                "iteration": iteration,
                "score": score,
                "thresholds": {"buy": float(thr_buy), "sell": float(thr_sell)},
                "validation": {
                    "buy": buy_val_metrics,
                    "sell": sell_val_metrics,
                    "trading": val_sim["metrics"],
                },
                "agreement": val_agreement,
                "quality": quality,
                "train_trading": train_sim["metrics"],
                "timing": timing_summary,
            }
        )
        timing_final = timing_summary

        if best is None or score > float(best["score"]) + cfg["min_delta"]:
            best = {
                "iteration": iteration,
                "score": score,
                "bundle": bundle,
                "thresholds": {"buy": float(thr_buy), "sell": float(thr_sell)},
                "buy_val_metrics": buy_val_metrics,
                "sell_val_metrics": sell_val_metrics,
                "val_metrics": val_sim["metrics"],
                "agreement": val_agreement,
                "quality": quality,
                "timing": timing_summary,
                "w_buy": w_buy.copy(),
                "w_sell": w_sell.copy(),
            }
            no_improve = 0
        else:
            no_improve += 1

        if not cfg["refine"] or no_improve >= cfg["patience"]:
            break

        if not use_seq:
            w_buy, w_sell = _reweight_from_timing(
                w_buy, w_sell, timed, pos_of_abs,
                t_train["buy"][:base_count], t_train["sell"][:base_count],
            )

    chosen = best or {}
    thr_buy = float(chosen.get("thresholds", {}).get("buy", 0.6))
    thr_sell = float(chosen.get("thresholds", {}).get("sell", 0.6))
    adjust = _threshold_adjustment(chosen.get("timing") or {}) if cfg["threshold_adjust"] else {"delta": 0.0, "reason": "Kapalı"}
    if cfg["threshold_adjust"] and adjust.get("delta"):
        thr_buy = max(0.45, min(0.95, thr_buy + float(adjust["delta"])))
        thr_sell = max(0.45, min(0.95, thr_sell + float(adjust["delta"])))
    buy_val_metrics = chosen.get("buy_val_metrics", {})
    sell_val_metrics = chosen.get("sell_val_metrics", {})
    val_metrics = chosen.get("val_metrics", {})
    best_iteration = int(chosen.get("iteration") or 1)
    best_score = float(chosen.get("score") or 0.0)

    # Nihai model. Tabular modellerde train+validation birlikte kullanılır;
    # sıra modellerinde validation erken durma için ayrı tutulur.
    ensemble_size = max(1, min(int(cfg.get("ensemble") or 1), 5))
    if use_seq:
        y_tr_full = np.stack([t_train["buy"][seq_sel], t_train["sell"][seq_sel]], axis=1)
        w_tr_full = np.stack([w_buy[seq_sel], w_sell[seq_sel]], axis=1)
        y_va_full = np.stack([t_val["buy"], t_val["sell"]], axis=1)
        w_va_full = np.stack([w_val, w_val], axis=1)
        members = []
        for k in range(ensemble_size):
            members.append(
                _fit_sequence_bundle(
                    spec, seq, train_abs[seq_sel], y_tr_full, w_tr_full, val_abs, y_va_full, w_va_full,
                    seed=999 + 37 * k,
                    init_model=(chosen.get("bundle") or {}).get("sequence_model") if k == 0 else None,
                )
            )
        if len(members) == 1:
            final_bundle = members[0]
        else:
            from app.ai.model import SequenceEnsemble

            base = members[0]
            final_bundle = {
                **base,
                "sequence_model": SequenceEnsemble([m["sequence_model"] for m in members]),
            }
    else:
        X_fit = np.vstack([X_train, X_val])
        t_fit = {key: np.concatenate([t_train[key], t_val[key]]) for key in t_train}
        wb_fit = np.concatenate([chosen.get("w_buy", w_buy), w_val])
        ws_fit = np.concatenate([chosen.get("w_sell", w_sell), w_val])
        final_bundle = _fit_bundle(
            spec, X_fit, t_fit, wb_fit, ws_fit, None, None, None, seed=999,
            init_bundle=chosen.get("bundle"),
        )
        # Topluluk: aynı veri ve bütçeyle farklı tohumlardan birkaç model
        # eğitilip olasılıkları ortalanır (aşırı öğrenmeyi artırmadan
        # genellemeyi iyileştirir).
        if ensemble_size > 1:
            member_spec = dict(spec)
            member_spec["epochs"] = max(40, int(int(spec.get("epochs") or 120) // ensemble_size))
            member_spec["patience"] = max(10, int(spec.get("patience") or 15))
            members = [_fit_bundle(
                member_spec, X_fit, t_fit, wb_fit, ws_fit, None, None, None,
                seed=999 + 37 * k, init_bundle=chosen.get("bundle"),
            ) for k in range(ensemble_size)]
            final_bundle = _average_bundles(members)

    # Nihai modelin çoklu-pencere uyumu. Yalnızca LMM etiketinde anlamlıdır;
    # kâr odaklı modda hesaplanmaz (maliyet ve anlamsız metrik).
    if cfg["kind"] in {"local_min_max", "local_extreme"}:
        robust_f1 = _multi_window_agreement_f1(
            final_bundle, X_valid[val_pos], idx[val_pos], val_positions, high, low, cfg,
            probs_fn=(lambda seg: probs_for(final_bundle, val_abs[seg])) if use_seq else None,
        )
    else:
        robust_f1 = None

    if skip_test:
        # Ara nesillerde test kümesi hiç değerlendirilmez; böylece kuşak
        # seçimi teste bakmadan yapılabilir.
        buy_test_metrics = {}
        sell_test_metrics = {}
        test_sim = {"metrics": {}, "equity": [], "trades": [], "trade_total": 0}
        p_buy_test = np.array([])
        p_sell_test = np.array([])
        test_agreement = {}
    else:
        p_buy_test, p_sell_test = probs_for(final_bundle, idx[test_pos])
        buy_test_metrics = _classification_report(t_test["buy"], p_buy_test, thr_buy)
        sell_test_metrics = _classification_report(t_test["sell"], p_sell_test, thr_sell)
        buy_full = np.zeros(n)
        sell_full = np.zeros(n)
        buy_full[idx[test_pos]] = p_buy_test
        sell_full[idx[test_pos]] = p_sell_test
        test_sim = _simulate(
            close, high, low, buy_full, sell_full, idx[test_pos], thr_buy, thr_sell, cfg,
            trend_ok=trend_ok,
        )
        test_agreement = agreement(
            p_buy_test,
            p_sell_test,
            idx[test_pos],
            high,
            low,
            buy_threshold=thr_buy,
            sell_threshold=thr_sell,
            window=int(cfg["extreme_window"]),
            tolerance=int(cfg["agree_tolerance"]),
        )

    # Validation tekrar (nihai eşiklerle) rapora girer.
    p_buy_val_final, p_sell_val_final = probs_for(final_bundle, val_abs)
    buy_val_full = np.zeros(n)
    sell_val_full = np.zeros(n)
    buy_val_full[idx[val_pos]] = p_buy_val_final
    sell_val_full[idx[val_pos]] = p_sell_val_final
    val_sim_final = _simulate(
        close, high, low, buy_val_full, sell_val_full, val_abs, thr_buy, thr_sell, cfg,
        trend_ok=trend_ok,
    )
    # Nihai modelin 3 pencereli işlem kalitesi (test görmez).
    quality_final = _multi_window_quality(
        buy_val_full, sell_val_full, val_abs, idx, close, high, low,
        thr_buy, thr_sell, cfg, trend_ok=trend_ok,
    )

    # Walk-forward yalnızca öğrenme+validation bölgesinde çalışır; test
    # dönemi bu değerlendirmeye hiç girmez (sızıntısız rapor).
    folds_report = (
        _walk_forward(
            spec, X_valid[:pos2], y_buy[:pos2], y_sell[:pos2], y_action[:pos2], y_return[:pos2],
            idx[:pos2], close, high, low,
            list(data.get("opendate") or []), cfg, cfg["folds"], embargo,
        )
        if cfg["walk_forward"]
        else []
    )
    wf_summary = _fold_summary(folds_report)

    # Eğitim (in-sample) simülasyonu: aşırı öğrenme teşhisi. Sıra modellerinde
    # tüm eğitim pencerelerini üretmek pahalı olduğu için örneklenir.
    train_eval_abs = train_abs
    if use_seq and len(train_abs) > 6000:
        train_eval_abs = train_abs[subsample(np.arange(len(train_abs)), 6000, 1)]
    p_buy_train, p_sell_train = probs_for(final_bundle, train_eval_abs)
    buy_train_full = np.zeros(n)
    sell_train_full = np.zeros(n)
    buy_train_full[train_eval_abs] = p_buy_train
    sell_train_full[train_eval_abs] = p_sell_train
    train_sim = _simulate(
        close, high, low, buy_train_full, sell_train_full, train_eval_abs, thr_buy, thr_sell, cfg,
        trend_ok=trend_ok,
    )

    thresholds = {"buy": float(thr_buy), "sell": float(thr_sell)}
    model_info = _model_info(final_bundle, feature_names)
    bundle = {
        **final_bundle,
        "feature_names": feature_names,
        "fill_values": fill_values.tolist(),
        "feature_groups": spec["feature_groups"],
        "spec": spec,
        "thresholds": thresholds,
        "params": cfg,
        "kind": "ai-model",
        "label_kind": cfg["kind"],
        "horizon": cfg["horizon"],
        "target_move": cfg["target_move"],
        "stop_move": cfg["stop_move"],
        "trend_filter": bool(cfg["trend_filter"]),
        "trailing_stop": float(cfg["trailing_stop"]),
    }
    if use_seq and seq is not None:
        bundle["seq_scaler"] = seq.scalar()
        bundle["seq_window"] = int(seq.window)
        bundle["seq_engine"] = str(spec.get("engine") or "lstm")

    regression_report = None
    if spec["output_mode"] == "regression":
        pred = np.asarray(final_bundle["return_model"].predict(X_test), dtype=float)
        regression_report = {
            "mae": round(float(np.mean(np.abs(pred - t_test["return"]))), 6),
            "correlation": round(
                float(np.corrcoef(pred, t_test["return"])[0, 1]) if len(pred) > 2 else 0.0, 4
            ),
            "pred_std": round(float(np.std(pred)), 6),
        }

    report = {
        "kind": "walk-forward-supervised",
        "created_at": artifacts._now(),
        "coin": coin,
        "period": period,
        "data": data_meta,
        "spec": spec,
        "lineage": lineage,
        "skip_test": bool(skip_test),
        "feature_names": feature_names,
        "config": cfg,
        "label": {
            "kind": cfg["kind"],
            "horizon": cfg["horizon"],
            "target_move": cfg["target_move"],
            "stop_move": cfg["stop_move"],
            "embargo_bars": embargo,
            "quantile": cfg.get("excess_quantile"),
            "trend_gate": bool(cfg.get("trend_gate")),
            "dip_gate": bool(cfg.get("dip_gate")),
            "top_gate": bool(cfg.get("top_gate")),
            "thresholds": labels.get("thresholds"),
        },
        "split": {
            "train": {
                "rows": int(len(train_pos)),
                "start": _date(data["opendate"][int(idx[train_pos[0]])]),
                "end": _date(data["opendate"][int(idx[train_pos[-1]])]),
            },
            "validation": {
                "rows": int(len(val_pos)),
                "start": _date(data["opendate"][int(idx[val_pos[0]])]),
                "end": _date(data["opendate"][int(idx[val_pos[-1]])]),
            },
            "test": {
                "rows": int(len(test_pos)),
                "start": _date(data["opendate"][int(idx[test_pos[0]])]),
                "end": _date(data["opendate"][int(idx[test_pos[-1]])]),
            },
        },
        "split_policy": {
            "learn_pct": 70,
            "test_pct": 30,
            "note": (
                "Öğrenme %70: ilk %55 saf eğitim, son %15 eşik/tur seçimi (validation). "
                "Test %30 hiçbir seçimde kullanılmaz. Bölmeler arasında horizon kadar embargo var."
            ),
        },
        "class_balance": {
            "buy_positive_rate": round(float(np.mean(y_buy)), 4),
            "sell_positive_rate": round(float(np.mean(y_sell)), 4),
            "neutral_rate": round(float(np.mean(y_action == 0)), 4),
        },
        "thresholds": thresholds,
        "threshold_adjustment": adjust,
        "objective": {
            "kind": cfg["kind"],
            "description": (
                "Local_Min_Max dip/zirve bölgelerine yaklaşma (F1) + kâr"
                if cfg["kind"] in {"local_min_max", "local_extreme"}
                else "Trende uygun dip alımı + tepe satışı; kâr odaklı"
            ),
            "extreme_window": int(cfg["extreme_window"]),
            "proximity_band": float(cfg.get("proximity_band") or 0),
            "agree_tolerance": int(cfg["agree_tolerance"]),
            "moves_source": cfg.get("moves_source") or "manual",
            "atr_pct": cfg.get("atr_pct"),
        },
        "agreement": {
            "validation": chosen.get("agreement") or {},
            "test": test_agreement,
            "robust": {
                "f1": robust_f1,
                "windows": len(val_positions),
                "note": "Öğrenme bölgesinin 3 ayrı penceresi; test kullanılmaz",
            },
        },
        "quality": {
            "robust": quality_final,
            "best_iteration": chosen.get("quality") or {},
            "metric": "3 pencereli işlem kalitesi (edge + getiri + kâr faktörü)",
        },
        "validation": {
            "buy": buy_val_metrics,
            "sell": sell_val_metrics,
            "trading": val_sim_final["metrics"],
        },
        "train": {
            "trading": train_sim["metrics"],
        },
        "test": {
            "buy": buy_test_metrics,
            "sell": sell_test_metrics,
            "trading": test_sim["metrics"],
            "equity": test_sim["equity"],
            "trades": test_sim["trades"],
        },
        "regression": regression_report,
        "refinement": {
            "enabled": bool(cfg["refine"]),
            "iterations_run": len(history),
            "best_iteration": best_iteration,
            "best_score": best_score,
            "patience": cfg["patience"],
            "min_delta": cfg["min_delta"],
            "timing_tolerance": cfg["timing_tolerance"],
            "history": history,
            "timing": timing_final,
            "method": (
                "Her turda eğitim kümesindeki işlemler erken/geç/zamanında olarak "
                "sınıflandırılır; hatalı zamanlamadaki örneklerin ağırlığı düşürülür, "
                "ideal dip/zirve örneklerinin ağırlığı artırılır. Tur seçimi yalnızca "
                "validation skoruyla yapılır, test kümesi hiç kullanılmaz."
            ),
        },
        "model": model_info,
        "walk_forward": folds_report,
        "walk_forward_summary": wf_summary,
        "feedback": {"used": feedback_used, "weight": cfg["feedback_weight"]},
        "engine": {
            "spec": spec,
            "sklearn": SKLEARN_AVAILABLE,
            "features": len(feature_names),
        },
    }

    manifest = artifacts.save_model(
        name=name,
        bundle=bundle,
        model_id=retrain_id,
        params={
            **cfg, **spec, "coin": coin, "period": period, "limit": limit, "source": source,
            "dataset_id": data_meta.get("dataset_id"),
            "parent_id": (lineage.get("parent_id") if lineage.get("warm_start_used") else None),
            "generation": generation,
            "warm_start_used": bool(lineage.get("warm_start_used")),
        },
        metrics={
            "test": report["test"]["trading"],
            "validation": report["validation"]["trading"],
            "train": report["train"]["trading"],
            "buy": report["test"]["buy"],
            "sell": report["test"]["sell"],
            "walk_forward": wf_summary,
            "lineage": lineage,
            "agreement": {
                "validation": report["agreement"]["validation"],
                "test": report["agreement"]["test"],
                "robust": report["agreement"]["robust"],
            },
            "objective": report["objective"],
            "quality": report["quality"],
            "refinement": {
                "iterations_run": len(history),
                "best_iteration": best_iteration,
                "best_score": best_score,
                "timing": timing_final,
            },
            "model": {
                "engine": str(spec.get("engine") or "mlp"),
                "params": model_info.get("params"),
                "heads": [m.get("type") for m in model_info.get("models", [])],
                # ``layers`` yalnızca MLP'de gizli katman listesidir. Sıra
                # modelleri kendi boyutlarını ayrı alanlarda verir; burada
                # sayı gelirse panelde katman listesi sanılmasın diye
                # normalize edilir.
                "layers": _layers_metric((model_info.get("models") or [{}])[0].get("layers")),
                "depth": (model_info.get("models") or [{}])[0].get("depth"),
                "dim": (model_info.get("models") or [{}])[0].get("dim"),
                "hidden": (model_info.get("models") or [{}])[0].get("hidden"),
                "epochs": (model_info.get("models") or [{}])[0].get("epochs_run"),
                "best_epoch": (model_info.get("models") or [{}])[0].get("best_epoch"),
                "stopped_early": (model_info.get("models") or [{}])[0].get("stopped_early"),
                "warm_started": (model_info.get("models") or [{}])[0].get("warm_started"),
                "ensemble": (model_info.get("models") or [{}])[0].get("ensemble"),
                "top_features": (model_info.get("models") or [{}])[0].get("top_features") or [],
            },
        },
        data_meta=data_meta,
        feature_names=feature_names,
        thresholds=thresholds,
        notes=str(params.get("notes") or ""),
    )
    artifacts.write_report(manifest["id"], report)
    return {"ok": True, "model": manifest, "report": report}
