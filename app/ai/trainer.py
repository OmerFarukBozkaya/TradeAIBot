"""Titiz zaman serisi eğitimi.

Sıra:
1. Veri çekilir (kronolojik).
2. Nedensel özellikler + gelecek etiketleri üretilir.
3. Train / validation / test zaman sırasına göre bölünür; etiket ufku kadar
   embargo (purge) bırakılır.
4. İki ikili model (dip/alım ve zirve/satım) eğitilir.
5. Eşikler **sadece validation** üzerinde seçilir.
6. Test kümesi yalnızca bir kez değerlendirilir.
7. İsteğe bağlı walk-forward (genişleyen pencere) raporu üretilir.
8. Model aday olarak kaydedilir; panelden onaylanmadan botlara bağlanmaz.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.ai import artifacts
from app.ai.data import load_market_data
from app.ai.features import build_features
from app.ai.labels import build_labels
from app.ai.model import (
    SKLEARN_AVAILABLE,
    choose_threshold,
    classification_metrics,
    fit_classifier,
    predict_positive,
    roc_auc,
    simulate_trades,
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
    """Kapanan AI işlemlerini ek eğitim örneği olarak hazırlar.

    Yalnızca aynı coin/periyot ve aynı özellik şemasındaki deneyimler alınır.
    Etiket, işlemin gerçekleşen K/Z'sidir (komisyon sonrası). Bu örnekler
    doğrulama/test kümelerine **karıştırılmaz**; sadece eğitim kümesine,
    sınırlı ağırlıkla eklenir.
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


def _fit_pair(
    X_train: np.ndarray,
    y_buy: np.ndarray,
    y_sell: np.ndarray,
    sample_weight: Optional[np.ndarray],
    random_state: int = 42,
) -> Tuple[Any, Any]:
    buy_model = fit_classifier(X_train, y_buy, sample_weight=sample_weight, random_state=random_state)
    sell_model = fit_classifier(X_train, y_sell, sample_weight=sample_weight, random_state=random_state + 1)
    return buy_model, sell_model


def _classification_report(y: np.ndarray, p: np.ndarray, threshold: float) -> Dict[str, Any]:
    metrics = classification_metrics(y, p, threshold)
    auc = roc_auc(y, p)
    if auc is not None:
        metrics["roc_auc"] = round(auc, 4)
    return metrics


def _validation_score(metrics: Dict[str, Any], min_trades: int) -> float:
    """Bir turun iyiliğini tek sayıya indirger (yalnızca validation için)."""
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

    Ağırlıklar [0.3, 3.0] aralığında tutulur ve ortalaması 1'e normalize edilir;
    böylece tek bir hatalı işlem modeli ele geçirmez.
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


def _timed_summary(timed: List[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize_timing(timed)



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
) -> Dict[str, Any]:
    return simulate_trades(
        close,
        high,
        low,
        buy_prob,
        sell_prob,
        indices,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        horizon=int(cfg.get("horizon", 12)),
        fee=float(cfg.get("fee", 0.001)),
        slippage=float(cfg.get("slippage", 0.0005)),
        stop_move=float(cfg.get("stop_move", 0.01)),
        target_move=float(cfg.get("target_move", 0.02)),
        trade_limit=trade_limit,
    )


def _walk_forward(
    X: np.ndarray,
    y_buy: np.ndarray,
    y_sell: np.ndarray,
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
        X_tr, X_val = X[core_pos], X[val_pos]
        buy_model, sell_model = _fit_pair(X_tr, y_buy[core_pos], y_sell[core_pos], None, 42 + k * 7)
        p_buy_val = predict_positive(buy_model, X_val)
        p_sell_val = predict_positive(sell_model, X_val)
        thr_buy, _ = choose_threshold(y_buy[val_pos], p_buy_val, float(cfg.get("min_precision", 0.35)))
        thr_sell, _ = choose_threshold(y_sell[val_pos], p_sell_val, float(cfg.get("min_precision", 0.35)))
        test_pos = np.arange(test_start, test_end)
        X_te = X[test_pos]
        p_buy = predict_positive(buy_model, X_te)
        p_sell = predict_positive(sell_model, X_te)
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
                "buy": _classification_report(y_buy[test_pos], p_buy, thr_buy),
                "sell": _classification_report(y_sell[test_pos], p_sell, thr_sell),
                "trading": sim["metrics"],
            }
        )
    return out


def train_model(params: Dict[str, Any]) -> Dict[str, Any]:
    """Panelden gelen parametrelerle bir model eğitir ve aday olarak kaydeder."""
    coin = str(params.get("coin") or "BTCUSDT").upper()
    period = str(params.get("period") or "1h")
    limit = int(params.get("limit") or 20000)
    source = str(params.get("source") or "binance")
    csv_path = str(params.get("csv_path") or "")

    cfg = {
        "kind": str(params.get("label_kind") or "forward"),
        "horizon": max(2, min(int(params.get("horizon") or 12), 500)),
        "target_move": max(0.0005, min(float(params.get("target_move") or 0.01), 0.5)),
        "stop_move": max(0.0005, min(float(params.get("stop_move") or 0.01), 0.5)),
        "extreme_window": max(2, min(int(params.get("extreme_window") or 13), 100)),
        "extreme_tolerance": max(0.0, min(float(params.get("extreme_tolerance") or 0.002), 0.05)),
        "fee": max(0.0, min(float(params.get("fee") or 0.001), 0.05)),
        "slippage": max(0.0, min(float(params.get("slippage") or 0.0005), 0.05)),
        "min_precision": max(0.05, min(float(params.get("min_precision") or 0.35), 0.95)),
        "walk_forward": bool(params.get("walk_forward", True)),
        "folds": max(0, min(int(params.get("folds") or 3), 6)),
        "use_feedback": bool(params.get("use_feedback", True)),
        "feedback_weight": max(0.0, min(float(params.get("feedback_weight") or 0.5), 2.0)),
        # Yinelemeli iyileştirme: hata analizi → ağırlık güncelleme → yeniden eğit.
        "refine": bool(params.get("refine", True)),
        "iterations": max(1, min(int(params.get("iterations") or 5), 12)),
        "patience": max(1, min(int(params.get("patience") or 2), 6)),
        "min_delta": max(0.0, min(float(params.get("min_delta") or 0.02), 5.0)),
        "timing_tolerance": max(0.0005, min(float(params.get("timing_tolerance") or 0.004), 0.05)),
        "min_trades": max(1, min(int(params.get("min_trades") or 8), 5000)),
    }
    name = str(params.get("name") or f"{coin} {period} AI").strip()[:80]

    data, data_meta = load_market_data(coin, period, limit, source, csv_path)
    feature = build_features(data)
    labels = build_labels(data["close"], data["high"], data["low"], cfg)
    close = feature["close"]
    high = feature["high"]
    low = feature["low"]
    X = feature["X"]
    feature_names = feature["feature_names"]
    n = len(close)

    valid = np.arange(n) >= int(feature["warmup"])
    valid &= labels["buy"] >= 0
    valid &= labels["sell"] >= 0
    valid &= np.isfinite(close)
    idx = np.where(valid)[0]
    if len(idx) < 800:
        raise RuntimeError(
            f"Yeterli geçerli satır yok ({len(idx)}). Daha uzun geçmiş veya daha kısa horizon seçin."
        )

    y_buy = labels["buy"][idx].astype(int)
    y_sell = labels["sell"][idx].astype(int)
    X_valid = X[idx]
    # Etiketin kesinleşme ufku: ileri getiri için horizon, yerel ekstrem için
    # onay penceresi. Embargo bu ufka göre bırakılır.
    label_lookahead = (
        int(cfg["extreme_window"]) if cfg["kind"] == "local_extreme" else int(cfg["horizon"])
    )
    embargo = label_lookahead + 2

    # Zaman sırası korunur. İstenen oran: %70 öğrenme / %30 test.
    # Öğrenme kısmının son %15'i mutlak zaman dilimi eşik ve tur seçimi
    # (validation) için ayrılır; test kümesi hiçbir seçimde kullanılmaz.
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

    X_train, yb_train, ys_train = X_valid[train_pos], y_buy[train_pos], y_sell[train_pos]
    X_val, yb_val, ys_val = X_valid[val_pos], y_buy[val_pos], y_sell[val_pos]
    X_test, yb_test, ys_test = X_valid[test_pos], y_buy[test_pos], y_sell[test_pos]

    # Canlı işlemlerden öğrenme: yalnızca eğitim kümesine, düşük ağırlıkla.
    feedback_used = 0
    sample_weight = np.ones(len(X_train), dtype=float)
    if cfg["use_feedback"]:
        X_fb, yb_fb, ys_fb, feedback_used = _load_feedback(feature_names, coin, period)
        if feedback_used:
            # Aşırı öğrenmeyi önlemek için deneyimler eğitim satırlarının en
            # fazla %20'si kadar ve en fazla 1500 kayıt olabilir.
            cap = min(1500, max(0, int(len(X_train) * 0.20)))
            if cap <= 0:
                X_fb = yb_fb = ys_fb = None
                feedback_used = 0
            elif feedback_used > cap:
                X_fb = X_fb[-cap:]
                yb_fb = yb_fb[-cap:]
                ys_fb = ys_fb[-cap:]
                feedback_used = cap
        if feedback_used and X_fb is not None:
            # Aynı deneyim iki sınıfa da örnek olabilir; satırları çoğaltıyoruz.
            X_extra = np.vstack([X_fb, X_fb])
            yb_extra = np.concatenate([yb_fb, np.zeros(len(yb_fb), dtype=int)])
            ys_extra = np.concatenate([np.zeros(len(ys_fb), dtype=int), ys_fb])
            X_train = np.vstack([X_train, X_extra])
            yb_train = np.concatenate([yb_train, yb_extra])
            ys_train = np.concatenate([ys_train, ys_extra])
            sample_weight = np.concatenate(
                [sample_weight, np.full(len(X_extra), cfg["feedback_weight"])]
            )

    # Eksik değerler yalnızca eğitim kümesinden öğrenilen medyanla doldurulur.
    # Aynı doldurma canlı çıkarımda kullanılır; train/serve kayması olmaz.
    fill_values = np.nanmedian(X_train, axis=0)
    fill_values = np.where(np.isfinite(fill_values), fill_values, 0.0)
    X_train = np.where(np.isfinite(X_train), X_train, fill_values)
    X_val = np.where(np.isfinite(X_val), X_val, fill_values)
    X_test = np.where(np.isfinite(X_test), X_test, fill_values)
    X_valid = np.where(np.isfinite(X_valid), X_valid, fill_values)

    # Deneyim satırları X_train'in sonuna eklendi; ilk `base_count` satır
    # gerçek zaman serisi satırlarıdır.
    base_count = int(len(train_pos))
    pos_of_abs = {int(idx[train_pos[i]]): i for i in range(base_count)}
    weights_buy = np.asarray(sample_weight, dtype=float).copy()
    weights_sell = np.asarray(sample_weight, dtype=float).copy()

    total_iterations = int(cfg["iterations"]) if cfg["refine"] else 1
    best: Optional[Dict[str, Any]] = None
    no_improve = 0
    history: List[Dict[str, Any]] = []
    timing_final: Dict[str, Any] = {}

    for iteration in range(1, total_iterations + 1):
        buy_model = fit_classifier(
            X_train, yb_train, sample_weight=weights_buy, random_state=100 + iteration
        )
        sell_model = fit_classifier(
            X_train, ys_train, sample_weight=weights_sell, random_state=200 + iteration
        )

        # Eşikler yalnızca validation'da seçilir; test'e bakılmaz.
        p_buy_val = predict_positive(buy_model, X_val)
        p_sell_val = predict_positive(sell_model, X_val)
        thr_buy, buy_val_metrics = choose_threshold(yb_val, p_buy_val, cfg["min_precision"])
        thr_sell, sell_val_metrics = choose_threshold(ys_val, p_sell_val, cfg["min_precision"])

        buy_val_full = np.zeros(n)
        sell_val_full = np.zeros(n)
        buy_val_full[idx[val_pos]] = p_buy_val
        sell_val_full[idx[val_pos]] = p_sell_val
        val_sim = _simulate(
            close, high, low, buy_val_full, sell_val_full, idx[val_pos], thr_buy, thr_sell, cfg
        )
        score = _validation_score(val_sim["metrics"], cfg["min_trades"])

        # Hata analizi yalnızca eğitim kümesinde yapılır.
        p_buy_train = predict_positive(buy_model, X_train[:base_count])
        p_sell_train = predict_positive(sell_model, X_train[:base_count])
        buy_train_full = np.zeros(n)
        sell_train_full = np.zeros(n)
        buy_train_full[idx[train_pos]] = p_buy_train
        sell_train_full[idx[train_pos]] = p_sell_train
        train_sim = _simulate(
            close, high, low, buy_train_full, sell_train_full, idx[train_pos],
            thr_buy, thr_sell, cfg, trade_limit=100_000,
        )
        timed = analyze_trades(
            train_sim["trades"], high, low,
            window=int(cfg["horizon"]), tolerance=float(cfg["timing_tolerance"]),
        )
        timing_summary = _timed_summary(timed)

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
                "train_trading": train_sim["metrics"],
                "timing": timing_summary,
            }
        )
        timing_final = timing_summary

        if best is None or score > float(best["score"]) + cfg["min_delta"]:
            best = {
                "iteration": iteration,
                "score": score,
                "buy_model": buy_model,
                "sell_model": sell_model,
                "thresholds": {"buy": float(thr_buy), "sell": float(thr_sell)},
                "buy_val_metrics": buy_val_metrics,
                "sell_val_metrics": sell_val_metrics,
                "val_metrics": val_sim["metrics"],
                "timing": timing_summary,
                "weights_buy": weights_buy.copy(),
                "weights_sell": weights_sell.copy(),
            }
            no_improve = 0
        else:
            no_improve += 1

        if not cfg["refine"] or no_improve >= cfg["patience"]:
            break

        # Bir sonraki tur: zamanlama hatalarından ders al, ağırlıkları güncelle.
        weights_buy, weights_sell = _reweight_from_timing(
            weights_buy, weights_sell, timed, pos_of_abs, yb_train[:base_count], ys_train[:base_count]
        )

    chosen = best or {}
    thr_buy = float(chosen.get("thresholds", {}).get("buy", 0.6))
    thr_sell = float(chosen.get("thresholds", {}).get("sell", 0.6))
    buy_val_metrics = chosen.get("buy_val_metrics", {})
    sell_val_metrics = chosen.get("sell_val_metrics", {})
    val_metrics = chosen.get("val_metrics", {})
    best_iteration = int(chosen.get("iteration") or 1)
    best_score = float(chosen.get("score") or 0.0)

    # Nihai aday model: train + validation birlikte, en iyi turun ağırlıklarıyla.
    X_fit = np.vstack([X_train, X_val])
    yb_fit = np.concatenate([yb_train, yb_val])
    ys_fit = np.concatenate([ys_train, ys_val])
    sw_buy_fit = np.concatenate([chosen.get("weights_buy", weights_buy), np.ones(len(X_val), dtype=float)])
    sw_sell_fit = np.concatenate([chosen.get("weights_sell", weights_sell), np.ones(len(X_val), dtype=float)])
    final_buy = fit_classifier(X_fit, yb_fit, sample_weight=sw_buy_fit, random_state=999)
    final_sell = fit_classifier(X_fit, ys_fit, sample_weight=sw_sell_fit, random_state=1000)

    p_buy_test = predict_positive(final_buy, X_test)
    p_sell_test = predict_positive(final_sell, X_test)
    buy_test_metrics = _classification_report(yb_test, p_buy_test, thr_buy)
    sell_test_metrics = _classification_report(ys_test, p_sell_test, thr_sell)

    buy_full = np.zeros(n)
    sell_full = np.zeros(n)
    buy_full[idx[test_pos]] = p_buy_test
    sell_full[idx[test_pos]] = p_sell_test
    test_sim = _simulate(close, high, low, buy_full, sell_full, idx[test_pos], thr_buy, thr_sell, cfg)

    folds_report = (
        _walk_forward(
            X_valid, y_buy, y_sell, idx, close, high, low,
            list(data.get("opendate") or []), cfg, cfg["folds"], embargo,
        )
        if cfg["walk_forward"]
        else []
    )
    wf_summary = _fold_summary(folds_report)

    # Eğitim (in-sample) simülasyonu: aşırı öğrenme teşhisi için.
    buy_train_full = np.zeros(n)
    sell_train_full = np.zeros(n)
    p_buy_train = predict_positive(final_buy, X_train[:base_count])
    p_sell_train = predict_positive(final_sell, X_train[:base_count])
    buy_train_full[idx[train_pos]] = p_buy_train
    sell_train_full[idx[train_pos]] = p_sell_train
    train_sim = _simulate(close, high, low, buy_train_full, sell_train_full, idx[train_pos], thr_buy, thr_sell, cfg)

    thresholds = {"buy": float(thr_buy), "sell": float(thr_sell)}
    bundle = {
        "buy_model": final_buy,
        "sell_model": final_sell,
        "feature_names": feature_names,
        "fill_values": fill_values.tolist(),
        "thresholds": thresholds,
        "params": cfg,
        "kind": "ai-local-minmax",
        "label_kind": cfg["kind"],
        "horizon": cfg["horizon"],
        "target_move": cfg["target_move"],
        "stop_move": cfg["stop_move"],
    }

    report = {
        "kind": "walk-forward-supervised",
        "created_at": artifacts._now(),
        "coin": coin,
        "period": period,
        "data": data_meta,
        "config": cfg,
        "label": {
            "kind": cfg["kind"],
            "horizon": cfg["horizon"],
            "target_move": cfg["target_move"],
            "stop_move": cfg["stop_move"],
            "embargo_bars": embargo,
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
        "class_balance": {
            "buy_positive_rate": round(float(np.mean(y_buy)), 4),
            "sell_positive_rate": round(float(np.mean(y_sell)), 4),
        },
        "thresholds": thresholds,
        "validation": {
            "buy": buy_val_metrics,
            "sell": sell_val_metrics,
            "trading": val_metrics,
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
        "split_policy": {
            "learn_pct": 70,
            "test_pct": 30,
            "note": (
                "Öğrenme %70: ilk %55 saf eğitim, son %15 eşik/tur seçimi (validation). "
                "Test %30 hiçbir seçimde kullanılmaz. Bölmeler arasında horizon kadar embargo var."
            ),
        },
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
        "walk_forward": folds_report,
        "walk_forward_summary": wf_summary,
        "feedback": {"used": feedback_used, "weight": cfg["feedback_weight"]},
        "engine": {
            "classifier": "HistGradientBoostingClassifier" if SKLEARN_AVAILABLE else "NumpyLogistic",
            "sklearn": SKLEARN_AVAILABLE,
            "features": len(feature_names),
        },
    }

    manifest = artifacts.save_model(
        name=name,
        bundle=bundle,
        params={**cfg, "coin": coin, "period": period, "limit": limit, "source": source},
        metrics={
            "test": report["test"]["trading"],
            "validation": report["validation"]["trading"],
            "train": report["train"]["trading"],
            "buy": report["test"]["buy"],
            "sell": report["test"]["sell"],
            "walk_forward": wf_summary,
            "refinement": {
                "iterations_run": len(history),
                "best_iteration": best_iteration,
                "best_score": best_score,
                "timing": timing_final,
            },
        },
        data_meta=data_meta,
        feature_names=feature_names,
        thresholds=thresholds,
        notes=str(params.get("notes") or ""),
    )
    artifacts.write_report(manifest["id"], report)
    return {"ok": True, "model": manifest, "report": report}


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
