"""Ağır işler (backtest, tarama, analiz) için ayrı süreç.

Web API'sini kilitlememek adına her iş kendi alt sürecinde çalışır.
Sonuç `jobs` tablosuna yazılır.
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from app import db
from app.config import settings
from app.strategies.compiler import CompiledStrategy
from app.strategies.registry import IndicatorCache, catalog
from app.strategies.service import build_evaluator, get_custom, normalize_specs


def _client():
    from core import Binance

    return Binance()


def _araclar():
    from core import Araclar

    return Araclar()


# Binance tek istekte en fazla 1000 mum verir; uzun backtest için sayfalanır.
_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
    "3d": 259_200_000, "1w": 604_800_000,
}


def _history(client, coin: str, period: str, limit: int) -> tuple:
    """`limit` 1000'den büyükse geçmişi sayfalayarak çeker.

    Döndürür: (veri, meta). `meta` çekilen ham satır sayısını, tekrarları ve
    kaç sayfa istendiğini taşır (veri kalitesi raporu için).
    """
    limit = max(1, int(limit))
    meta = {"requested": limit, "raw_rows": 0, "duplicates_removed": 0, "pages": 0}
    if limit <= 1000:
        data = client.get_coin_data(coin, period, limit)
        meta["raw_rows"] = len(data.get("close") or [])
        meta["pages"] = 1
        return data, meta

    import requests

    step = _INTERVAL_MS.get(period)
    if not step:
        data = client.get_coin_data(coin, period, min(limit, 1000))
        meta["raw_rows"] = len(data.get("close") or [])
        meta["pages"] = 1
        return data, meta

    base = getattr(client, "base_url", "https://api.binance.com")
    end_time = None
    rows: List[list] = []
    while len(rows) < limit:
        want = min(1000, limit - len(rows))
        params = {"symbol": coin, "interval": period, "limit": want}
        if end_time:
            params["endTime"] = end_time
        resp = requests.get(base + "/api/v3/klines", params=params, timeout=20)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows = batch + rows
        meta["pages"] += 1
        end_time = int(batch[0][0]) - 1
    meta["raw_rows"] = len(rows)
    seen = set()
    uniq = []
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        uniq.append(row)
    meta["duplicates_removed"] = len(rows) - len(uniq)
    uniq.sort(key=lambda r: r[0])
    data = {
        "opendate": [float(r[0]) for r in uniq],
        "open": [float(r[1]) for r in uniq],
        "high": [float(r[2]) for r in uniq],
        "low": [float(r[3]) for r in uniq],
        "close": [float(r[4]) for r in uniq],
        "volume_coin": [float(r[5]) for r in uniq],
        "closedate": [float(r[6]) for r in uniq],
        "volume_usdt": [float(r[7]) for r in uniq],
        "trade_number": [float(r[8]) for r in uniq],
        "buy_coin_volume": [float(r[9]) for r in uniq],
        "buy_usdt_volume": [float(r[10]) for r in uniq],
    }
    return data, meta


def _format_span(ms: float) -> str:
    """Milisaniyeyi '2 yıl 8 ay 12 gün' biçimine çevirir."""
    if not ms or ms <= 0:
        return "0 gün"
    days = ms / 86400000.0
    years = int(days // 365)
    rem = days - years * 365
    months = int(rem // 30)
    d = int(rem - months * 30)
    parts = []
    if years:
        parts.append(f"{years} yıl")
    if months:
        parts.append(f"{months} ay")
    if d or not parts:
        parts.append(f"{d} gün")
    return " ".join(parts)


def _data_report(data: Dict[str, Any], period: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Çekilen verinin gerçekten kaç mum olduğunu ve temizliğini raporlar."""
    import datetime as dt

    opendate = data.get("opendate") or []
    close = data.get("close") or []
    high = data.get("high") or []
    low = data.get("low") or []
    n = len(close)

    def iso(ms):
        try:
            return dt.datetime.fromtimestamp(float(ms) / 1000.0, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError, TypeError):
            return None

    report: Dict[str, Any] = {
        "requested": int(meta.get("requested") or 0),
        "received": n,
        "raw_rows": int(meta.get("raw_rows") or n),
        "duplicates_removed": int(meta.get("duplicates_removed") or 0),
        "pages": int(meta.get("pages") or 0),
        "period": period,
        "first": iso(opendate[0]) if n else None,
        "last": iso(opendate[-1]) if n else None,
        "first_ms": opendate[0] if n else None,
        "last_ms": opendate[-1] if n else None,
        "span_ms": (opendate[-1] - opendate[0]) if n > 1 else 0,
        "span_text": _format_span((opendate[-1] - opendate[0]) if n > 1 else 0),
        "complete": n >= int(meta.get("requested") or 0),
        "shortfall": max(0, int(meta.get("requested") or 0) - n),
    }

    # --- temizlik kontrolleri ---
    bad_price = 0
    bad_ohlc = 0
    nan = 0
    for i in range(n):
        c = close[i]
        if c is None or c != c or c <= 0:  # None / NaN / <=0
            nan += 1
            continue
        hi, lo = high[i], low[i]
        if hi is None or lo is None or hi != hi or lo != lo:
            nan += 1
            continue
        if hi < lo:
            bad_ohlc += 1
        elif not (lo <= c <= hi):
            bad_price += 1

    step = _INTERVAL_MS.get(period)
    gaps = 0
    missing = 0
    if step and n > 1:
        for i in range(1, n):
            delta = opendate[i] - opendate[i - 1]
            if delta > step * 1.5:
                gaps += 1
                missing += max(0, int(round(delta / step)) - 1)

    expected = int(report["span_ms"] / step) + 1 if step and n else n
    report["clean"] = (nan == 0 and bad_ohlc == 0 and bad_price == 0 and gaps == 0)
    report["nan_count"] = nan
    report["bad_ohlc_count"] = bad_ohlc
    report["bad_price_count"] = bad_price
    report["gaps"] = gaps
    report["missing_candles"] = missing
    report["coverage_pct"] = round(n / expected * 100, 2) if expected else 100.0
    return report


def _progress(job_id: Optional[str], pct: int, message: str = "") -> None:
    """Aktif işin ilerlemesini dashboard için günceller."""
    if not job_id:
        return
    try:
        db.execute(
            "UPDATE jobs SET progress=?, message=? WHERE id=? AND status='running'",
            (max(0, min(100, int(pct))), message[:200], job_id),
        )
    except Exception:
        pass


def _cancelled(job_id: Optional[str]) -> bool:
    if not job_id:
        return False
    row = db.row("SELECT status FROM jobs WHERE id=?", (job_id,))
    return bool(row and row["status"] == "cancelled")


def _cagr(initial: float, final: float, start_ms: float, end_ms: float) -> float:
    """Yıllık bileşik büyüme oranı (%)."""
    try:
        years = (float(end_ms) - float(start_ms)) / (365.25 * 24 * 3600 * 1000)
    except (TypeError, ValueError):
        return 0.0
    if years <= 0 or initial <= 0 or final <= 0:
        return 0.0
    return (pow(final / initial, 1.0 / years) - 1.0) * 100


def _yearly_breakdown(points: List[tuple]) -> List[Dict[str, Any]]:
    """Yıl bazında strateji ve al-tut getirisi.

    `points` her mum için (zaman_ms, strateji_değeri, al_tut_değeri) taşır.
    Yıl getirisi, önceki yılın son değerine göre hesaplanır.
    """
    import datetime as dt

    buckets: Dict[int, list] = {}
    for t, s, b in points:
        year = dt.datetime.fromtimestamp(float(t) / 1000.0, dt.timezone.utc).year
        bucket = buckets.get(year)
        if bucket is None:
            buckets[year] = [s, s, b, b]
        else:
            bucket[1] = s
            bucket[3] = b

    out: List[Dict[str, Any]] = []
    prev_s = prev_b = None
    for year in sorted(buckets):
        first_s, last_s, first_b, last_b = buckets[year]
        base_s = prev_s if prev_s is not None else first_s
        base_b = prev_b if prev_b is not None else first_b
        s_pct = (last_s / base_s - 1.0) * 100 if base_s else 0.0
        b_pct = (last_b / base_b - 1.0) * 100 if base_b else 0.0
        out.append(
            {
                "year": year,
                "strategy_pct": round(s_pct, 2),
                "buy_hold_pct": round(b_pct, 2),
                "diff": round(s_pct - b_pct, 2),
            }
        )
        prev_s, prev_b = last_s, last_b
    return out


# ---------------------------------------------------------------------------
# Risk yönetimi (stop / kâr al / iz süren / zaman aşımı)
# ---------------------------------------------------------------------------
def _atr_series(data: Dict[str, Any], length: int = 14) -> List[Optional[float]]:
    from app.strategies.registry import IndicatorCache

    vals = IndicatorCache(data).compute("ATR", {"length": length}, "value")
    return [None if (v is None or v != v) else float(v) for v in vals]


def _risk_exit(
    position: Dict[str, Any],
    data: Dict[str, Any],
    idx: int,
    atr: List[Optional[float]],
    risk: Dict[str, Any],
) -> Optional[tuple]:
    """Açık pozisyon için stop / kâr al / zaman aşımı kontrolü.

    Döndürür: (çıkış_fiyatı, neden) veya None. Mum içi (high/low) kullanılır;
    stop seviyesi ile kâr hedefi aynı mumda vurulursa **stop** önce sayılır
    (kötümser varsayım).
    """
    high = float(data["high"][idx])
    low = float(data["low"][idx])
    close = float(data["close"][idx])
    entry = float(position["entry"])
    base_atr = position.get("atr") or 0.0

    stop_atr = float(risk.get("stop_atr") or 0)
    trail_atr = float(risk.get("trail_atr") or 0)
    trail_after = float(risk.get("trail_after_pct") or 0)
    tp_atr = float(risk.get("take_profit_atr") or 0)
    tp_pct = float(risk.get("take_profit_pct") or 0)

    stop_price = None
    if base_atr > 0:
        if stop_atr > 0:
            stop_price = entry - stop_atr * base_atr
            # Üst sınır: stop, girişten en fazla `max_stop_pct` kadar aşağıda olabilir.
            # Yüksek volatiliteli coinlerde 35×ATR neredeyse %100'e yaklaşıp
            # işlevsiz kalıyor ("felaket koruması" bile denemez).
            max_stop_pct = float(risk.get("max_stop_pct") or 0)
            if max_stop_pct > 0:
                stop_price = max(stop_price, entry * (1 - max_stop_pct / 100))
        armed = True
        if trail_atr > 0 and trail_after > 0:
            # Takipli stop ancak kâr eşiği aşıldıktan sonra devreye girer;
            # erken pullback'lerde pozisyonu kesmez.
            armed = float(position.get("highest") or entry) >= entry * (1 + trail_after / 100)
        if trail_atr > 0 and armed:
            trail = float(position.get("highest") or entry) - trail_atr * base_atr
            stop_price = trail if stop_price is None else max(stop_price, trail)

    if stop_price is not None and low <= stop_price:
        return (min(stop_price, high), "stop")

    if tp_pct > 0 and high >= entry * (1 + tp_pct / 100):
        return (entry * (1 + tp_pct / 100), "take-profit")
    if tp_atr > 0 and base_atr > 0 and high >= entry + tp_atr * base_atr:
        return (entry + tp_atr * base_atr, "take-profit")

    return None


def _profit_exit(
    lower: List[Optional[float]],
    close: List[float],
    idx: int,
    entry: float,
) -> bool:
    """Kâr koruma: pozisyon kârdayken kısa vadeli dip kırılırsa çık.

    `lower`, Donchian alt bandı serisidir. Kırılım, önceki mumun bandın
    üstünde kapanıp bu mumun altında kapanmasıyla doğrulanır (cross).
    """
    if idx < 2 or idx >= len(close) or idx >= len(lower):
        return False
    if float(close[idx]) <= float(entry):
        return False
    a, b = lower[idx - 1], lower[idx - 2]
    if a is None or b is None:
        return False
    return float(close[idx]) < float(a) and float(close[idx - 1]) >= float(b)


def _trade_markers(trades: List[Dict[str, Any]], limit: int = 200) -> List[Dict[str, Any]]:
    """Grafik için AL/SAT işaretleri. Numaralar tablo numaralarıyla aynıdır."""
    tail = trades[-limit:]
    first_no = len(trades) - len(tail) + 1
    markers: List[Dict[str, Any]] = []
    for no, t in enumerate(tail, start=first_no):
        base = {
            "no": no,
            "pnl_pct": round(float(t["pnl_pct"]), 2),
            "candles": int(t["candles"]),
            "reason": t.get("reason"),
        }
        markers.append({
            **base,
            "side": "buy",
            "idx": int(t.get("entry_idx", 0)),
            "price": round(float(t["entry"]), 8),
            "time": t["entry_time"],
        })
        markers.append({
            **base,
            "side": "sell",
            "idx": int(t.get("exit_idx", 0)),
            "price": round(float(t["exit"]), 8),
            "time": t["exit_time"],
        })
    return markers


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def run_backtest(params: Dict[str, Any]) -> Dict[str, Any]:
    spec = params.get("strategy") or {}
    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1h")
    limit = max(200, min(int(params.get("limit", 1000)), 250000))
    job_id = params.get("_job_id")
    cash = float(params.get("cash", 100.0))
    initial_cash = cash
    fee = float(params.get("fee", settings.PAPER_FEE))
    slippage = float(params.get("slippage", settings.PAPER_SLIPPAGE))

    # Backtest teşhis amaçlıdır: arşivlenmiş modelin geçmiş performansı da
    # yeniden ölçülebilir (canlı bota eklenmesi yine engellidir).
    evaluator = build_evaluator(spec, allow_archived=True)
    # Toplu backtest'te veri bir kez çekilir ve paylaşılır (_data / _history_meta).
    cached_data = params.get("_data")
    if isinstance(cached_data, dict) and cached_data.get("close"):
        data = cached_data
        history_meta = params.get("_history_meta")
        if not isinstance(history_meta, dict):
            history_meta = {"requested": limit, "raw_rows": len(data["close"]), "pages": 0}
    else:
        client = _client()
        _progress(job_id, 10, f"{limit} mum veri çekiliyor")
        data, history_meta = _history(client, coin, period, limit)
    _progress(job_id, 30, f"{len(data['close'])} mum alındı, backtest çalışıyor")
    n = len(data["close"])
    data_report = _data_report(data, period, history_meta)
    cache = IndicatorCache(data) if isinstance(evaluator, CompiledStrategy) else None
    if hasattr(evaluator, "prepare"):
        evaluator.prepare(data)

    # Risk ayarları: istekte verilirse o, yoksa strateji tanımındaki `risk`
    risk = params.get("risk")
    if not isinstance(risk, dict) or not risk:
        definition = getattr(evaluator, "definition", None) or {}
        risk = definition.get("risk") if isinstance(definition, dict) else None
    risk = risk if isinstance(risk, dict) else {}
    atr = _atr_series(data) if risk else []
    profit_don = int(risk.get("profit_exit_donchian") or 0)
    profit_lower: Optional[List[Optional[float]]] = None
    if profit_don > 0:
        vals = IndicatorCache(data).compute("DONCHIAN", {"length": profit_don}, "lower")
        profit_lower = [None if (v is None or v != v) else float(v) for v in vals]

    position = None
    trades: List[Dict[str, Any]] = []
    equity = [cash]
    points: List[tuple] = []
    peak = cash
    max_dd = 0.0
    exit_reasons: Dict[str, int] = {}
    cooldown_until = -1
    cooldown = int(risk.get("cooldown") or 0)

    for i in range(max(evaluator.warmup, 2), n - 1):
        idx = i - 1
        if isinstance(evaluator, CompiledStrategy):
            result = evaluator.evaluate_at(data, cache, idx, detail=False)
        else:
            result = evaluator.evaluate_at(data, idx)
        price = float(data["close"][idx])
        candle_time = data["opendate"][idx]

        if position is None and result["buy"] and idx > cooldown_until:
            exec_price = price * (1 + slippage)
            qty = cash / (exec_price * (1 + fee))
            if qty * exec_price >= 5:
                cost = qty * exec_price
                cash -= cost + cost * fee
                position = {
                    "coin": coin,
                    "qty": qty,
                    "entry": exec_price,
                    "time": candle_time,
                    "index": idx,
                    "highest": price,
                    "atr": (atr[idx] if atr and idx < len(atr) else None) or 0.0,
                }
        elif position is not None:
            candle_high = float(data["high"][idx])
            if candle_high > float(position.get("highest") or 0):
                position["highest"] = candle_high

            exit_price = None
            reason = None
            if risk:
                hit = _risk_exit(position, data, idx, atr, risk)
                if hit:
                    exit_price, reason = hit

            if exit_price is None and result["sell"]:
                exit_price, reason = price * (1 - slippage), "signal"

            # Kâr koruma: pozisyon kârdayken daha kısa vadeli yapı kırılırsa çık.
            # Trend devam ederse pozisyon açık kalır; yalnızca kârı geri verirken
            # devreye girdiği için erken çıkışların getiriyi yok etmesini engeller.
            if (
                exit_price is None
                and profit_lower is not None
                and _profit_exit(profit_lower, data["close"], idx, float(position["entry"]))
            ):
                exit_price, reason = price * (1 - slippage), "profit-exit"

            if exit_price is not None:
                proceeds = position["qty"] * exit_price
                cash += proceeds - proceeds * fee
                pnl_pct = (exit_price / position["entry"] - 1) * 100
                exit_reasons[reason or "signal"] = exit_reasons.get(reason or "signal", 0) + 1
                trades.append(
                    {
                        "entry_time": position["time"],
                        "exit_time": candle_time,
                        "entry": position["entry"],
                        "exit": exit_price,
                        "qty": position["qty"],
                        "pnl_pct": pnl_pct,
                        "candles": idx - position["index"],
                        "reason": reason,
                        "entry_idx": position["index"],
                        "exit_idx": idx,
                    }
                )
                position = None
                # Koşullu bekleme: yalnızca zarar eşiği aşıldıysa uygula.
                min_loss = float(risk.get("cooldown_min_loss_pct") or 0)
                if cooldown and (min_loss <= 0 or pnl_pct <= -min_loss):
                    cooldown_until = idx + cooldown

        total = cash + (position["qty"] * price if position else 0)
        equity.append(total)
        points.append((candle_time, total, price))
        peak = max(peak, total)
        if peak > 0:
            max_dd = max(max_dd, (peak - total) / peak * 100)

    if position is not None:
        price = float(data["close"][-2])
        exec_price = price * (1 - slippage)
        proceeds = position["qty"] * exec_price
        cash += proceeds - proceeds * fee
        pnl_pct = (exec_price / position["entry"] - 1) * 100
        exit_reasons["end"] = exit_reasons.get("end", 0) + 1
        trades.append(
            {
                "entry_time": position["time"],
                "exit_time": data["opendate"][-2],
                "entry": position["entry"],
                "exit": exec_price,
                "qty": position["qty"],
                "pnl_pct": pnl_pct,
                "candles": (n - 2) - position["index"],
                "reason": "end",
                "entry_idx": position["index"],
                "exit_idx": n - 2,
            }
        )
        equity.append(cash)

    # --- Al ve tut (buy & hold) karşılaştırması ---
    start_idx = max(evaluator.warmup, 2) - 1
    end_idx = n - 2
    bh_return = 0.0
    bh_final = initial_cash
    bh_dd = 0.0
    bh_curve = []
    qty_bh = 0.0
    bh_start_price = float(data["close"][start_idx]) if 0 <= start_idx < n else 0.0
    bh_end_price = float(data["close"][end_idx]) if 0 <= end_idx < n else 0.0
    if bh_start_price > 0 and end_idx > start_idx:
        entry = bh_start_price * (1 + slippage) * (1 + fee)
        qty_bh = initial_cash / entry
        peak_bh = initial_cash
        for j in range(start_idx, end_idx + 1):
            value = qty_bh * float(data["close"][j])
            peak_bh = max(peak_bh, value)
            if peak_bh > 0:
                bh_dd = max(bh_dd, (peak_bh - value) / peak_bh * 100)
        bh_final = qty_bh * bh_end_price * (1 - slippage) * (1 - fee)
        bh_return = (bh_final / initial_cash - 1) * 100
        step_bh = max(1, (end_idx - start_idx + 1) // 200)
        bh_curve = [
            {"i": k, "value": round(qty_bh * float(data["close"][start_idx + k]), 4)}
            for k in range(0, end_idx - start_idx + 1, step_bh)
        ]
        if bh_curve and bh_curve[-1]["i"] != end_idx - start_idx:
            bh_curve.append({"i": end_idx - start_idx, "value": round(qty_bh * bh_end_price, 4)})

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    gross_win = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    hold = sorted(int(t["candles"]) for t in trades)
    avg_hold = round(sum(hold) / len(hold), 1) if hold else 0.0
    med_hold = hold[len(hold) // 2] if hold else 0
    step = max(1, len(equity) // 200)
    eq_start = max(evaluator.warmup, 2)
    curve = [
        {"i": i, "idx": eq_start + i - 2, "value": round(v, 4)}
        for i, v in enumerate(equity)
        if i % step == 0 or i == len(equity) - 1
    ]

    # --- Fiyat serisi ve işlem işaretleri (grafikte AL/SAT noktaları) ---
    markers = _trade_markers(trades)

    # Yakınlaştırma için OHLC serisi. Pencere büyükse seyreltilir; yakın
    # görünümde mum çizilebilsin diye open/high/low da gönderilir.
    price_series: List[Dict[str, Any]] = []
    span = end_idx - start_idx + 1
    if span > 1:
        pstep = max(1, span // 8000)
        for k in range(0, span, pstep):
            j = start_idx + k
            price_series.append({
                "idx": j,
                "t": data["opendate"][j],
                "o": round(float(data["open"][j]), 8),
                "h": round(float(data["high"][j]), 8),
                "l": round(float(data["low"][j]), 8),
                "c": round(float(data["close"][j]), 8),
            })
        if price_series and price_series[-1]["idx"] != end_idx:
            j = end_idx
            price_series.append({
                "idx": j,
                "t": data["opendate"][j],
                "o": round(float(data["open"][j]), 8),
                "h": round(float(data["high"][j]), 8),
                "l": round(float(data["low"][j]), 8),
                "c": round(float(data["close"][j]), 8),
            })

    start_ms = float(data["opendate"][start_idx]) if 0 <= start_idx < n else 0.0
    end_ms = float(data["opendate"][end_idx]) if 0 <= end_idx < n else 0.0
    cagr = _cagr(initial_cash, cash, start_ms, end_ms)
    bh_cagr = _cagr(initial_cash, bh_final, start_ms, end_ms)

    import datetime as _dt

    def _iso(ms):
        try:
            return _dt.datetime.fromtimestamp(float(ms) / 1000.0, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError, TypeError):
            return None

    data_report["backtest_start"] = _iso(start_ms)
    data_report["backtest_end"] = _iso(end_ms)
    data_report["backtest_span_text"] = _format_span(end_ms - start_ms)
    data_report["backtest_candles"] = max(0, end_idx - start_idx + 1)
    data_report["backtest_start_ms"] = start_ms
    data_report["backtest_end_ms"] = end_ms

    yearly = (
        _yearly_breakdown([(t, s, qty_bh * p) for t, s, p in points])
        if qty_bh > 0
        else []
    )

    return {
        "coin": coin,
        "period": period,
        "strategy": {"id": evaluator.id, "version": evaluator.version},
        "candles": n,
        "warmup": int(evaluator.warmup),
        "data_report": data_report,
        "trades": trades[-200:],
        "markers": markers,
        "price_series": price_series,
        "metrics": {
            "trade_count": len(trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
            "total_return_pct": round((cash / float(params.get("cash", 100.0)) - 1) * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "avg_trade_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 2) if trades else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            "avg_candles": round(sum(t["candles"] for t in trades) / len(trades), 1) if trades else 0.0,
            "cagr_pct": round(cagr, 2),
            "calmar": round(cagr / max_dd, 2) if max_dd > 0 else None,
            "avg_hold_candles": avg_hold,
            "median_hold_candles": med_hold,
            "max_hold_candles": max(hold) if hold else 0,
        },
        "risk": {
            "stop_atr": risk.get("stop_atr") or 0,
            "trail_atr": risk.get("trail_atr") or 0,
            "trail_after_pct": risk.get("trail_after_pct") or 0,
            "profit_exit_donchian": profit_don,
            "take_profit_atr": risk.get("take_profit_atr") or 0,
            "take_profit_pct": risk.get("take_profit_pct") or 0,
            "cooldown": risk.get("cooldown") or 0,
            "cooldown_min_loss_pct": risk.get("cooldown_min_loss_pct") or 0,
            "exit_reasons": exit_reasons,
        },
        "equity": curve,
        "final_cash": round(cash, 4),
        "yearly": yearly,
        "buy_hold": {
            "return_pct": round(bh_return, 2),
            "final_value": round(bh_final, 4),
            "max_drawdown_pct": round(bh_dd, 2),
            "cagr_pct": round(bh_cagr, 2),
            "calmar": round(bh_cagr / bh_dd, 2) if bh_dd > 0 else None,
            "start_price": round(bh_start_price, 8),
            "end_price": round(bh_end_price, 8),
            "candles": max(0, end_idx - start_idx),
            "equity": bh_curve,
        },
    }


# ---------------------------------------------------------------------------
# Toplu backtest (tüm stratejileri karşılaştır)
# ---------------------------------------------------------------------------
def collect_all_specs(include_archived: bool = False) -> List[Dict[str, Any]]:
    """Karşılaştırmaya girecek tüm strateji referanslarını toplar.

    Hazır (kod tabanlı) ve özel stratejiler tek listede birleşir; her kayıt
    satırda gösterilecek ad, tür ve backtest için gereken `spec` taşır.
    """
    from app.strategies.service import list_builtin, list_custom

    items: List[Dict[str, Any]] = []
    for b in list_builtin(include_archived):
        items.append(
            {
                "key": f"builtin:{b['id']}",
                "spec": {"type": "builtin", "name": b["id"]},
                "name": b.get("label") or b["id"],
                "motor": b["id"],
                "kind": "builtin",
                "best_timeframe": b.get("best_timeframe"),
            }
        )
    for c in list_custom(include_archived):
        items.append(
            {
                "key": f"custom:{c['id']}",
                "spec": {"type": "custom", "id": c["id"], "version": c.get("version")},
                "name": c["name"],
                "motor": c["id"],
                "kind": "custom",
                "best_timeframe": c.get("best_timeframe"),
            }
        )
    return items


def run_backtest_all(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tüm stratejileri aynı veriyle backtest eder ve karşılaştırma tablosu döndürür.

    Veri bir kez çekilir, her strateji için tekrar kullanılır; böylece hem hızlı
    hem de tüm satırlar birebir aynı fiyat serisiyle kıyaslanır.
    """
    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1h")
    limit = max(200, min(int(params.get("limit", 20000)), 250000))
    cash = float(params.get("cash", 100.0))
    job_id = params.get("_job_id")
    include_archived = bool(params.get("include_archived"))

    items = collect_all_specs(include_archived)
    if not items:
        raise RuntimeError("Backtest edilecek strateji yok")
    # İsteğe bağlı: yalnız belirli stratejiler (araç/denemeler için).
    wanted = params.get("keys")
    if wanted:
        wanted_set = set(wanted)
        items = [it for it in items if it["key"] in wanted_set]
        if not items:
            raise RuntimeError("Seçilen strateji bulunamadı")

    _progress(job_id, 5, f"{len(items)} strateji için veri çekiliyor")
    data, history_meta = _history(_client(), coin, period, limit)
    report = _data_report(data, period, history_meta)

    rows: List[Dict[str, Any]] = []
    starts: List[float] = []
    ends: List[float] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        _progress(job_id, 5 + int(((index - 1) / total) * 92), f"{item['name']} ({index}/{total})")
        base = {
            "key": item["key"],
            "spec": item["spec"],
            "name": item["name"],
            "motor": item["motor"],
            "kind": item["kind"],
            "best_timeframe": item.get("best_timeframe"),
        }
        try:
            result = run_backtest(
                {
                    "strategy": item["spec"],
                    "coin": coin,
                    "period": period,
                    "limit": limit,
                    "cash": cash,
                    "_data": data,
                    "_history_meta": history_meta,
                }
            )
            metrics = result["metrics"]
            bh = result.get("buy_hold") or {}
            report_row = result.get("data_report") or {}
            if report_row.get("backtest_start_ms"):
                starts.append(float(report_row["backtest_start_ms"]))
            if report_row.get("backtest_end_ms"):
                ends.append(float(report_row["backtest_end_ms"]))
            row = {
                **base,
                "return_pct": metrics["total_return_pct"],
                "buy_hold_pct": bh.get("return_pct"),
                "diff": round(
                    float(metrics["total_return_pct"]) - float(bh.get("return_pct") or 0), 2
                ),
                "drawdown_pct": metrics["max_drawdown_pct"],
                "buy_hold_dd": bh.get("max_drawdown_pct"),
                "calmar": metrics.get("calmar"),
                "buy_hold_calmar": bh.get("calmar"),
                "trades": metrics["trade_count"],
                "win_rate": metrics["win_rate"],
                "avg_hold": metrics.get("avg_hold_candles"),
                "cagr_pct": metrics.get("cagr_pct"),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - tek strateji hatası tabloyu bozmasın
            row = {**base, "error": str(exc)}
        rows.append(row)

    _progress(job_id, 99, "Sonuçlar derleniyor")
    # Gerçek test aralığı: stratejilerin warmup'ı farklı olduğu için en geniş kesişim.
    if starts and ends:
        import datetime as _dt

        first_ms, last_ms = min(starts), max(ends)

        def _iso(ms: float) -> Optional[str]:
            try:
                return _dt.datetime.fromtimestamp(
                    float(ms) / 1000.0, _dt.timezone.utc
                ).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError, TypeError):
                return None

        report["backtest_start"] = _iso(first_ms)
        report["backtest_end"] = _iso(last_ms)
        report["backtest_span_text"] = _format_span(last_ms - first_ms)
    return {
        "coin": coin,
        "period": period,
        "limit": limit,
        "candles": len(data["close"]),
        "data_report": report,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Tarama
# ---------------------------------------------------------------------------
def _scan_coins(params: Dict[str, Any]) -> List[str]:
    """Tarama coinlerini çözer: elle girilenler + seçili coin listesi."""
    coins: List[str] = []
    seen = set()
    for raw in params.get("coins") or []:
        coin = str(raw).strip().upper()
        if coin and coin not in seen:
            seen.add(coin)
            coins.append(coin)
    list_id = params.get("list_id")
    if list_id and not coins:
        from app.coin_lists import list_coins

        listed = list_coins(list_id)
        if listed is None:
            raise RuntimeError("Coin listesi bulunamadı")
        coins = list(listed)
    return coins


def run_scan(params: Dict[str, Any]) -> Dict[str, Any]:
    period = params.get("period", "1h")
    specs = normalize_specs(params.get("strategies") or [])
    coins = _scan_coins(params)
    job_id = params.get("_job_id")
    _progress(job_id, 5, "Coin listesi hazırlanıyor")
    client = _client()
    if not coins:
        coins = client.coin_list()
    _progress(job_id, 10, f"{len(coins)} coin taranacak")
    evaluators = [build_evaluator(spec) for spec in specs]
    results = {
        ev.id: {"BUY": [], "SELL": []} for ev in evaluators
    }
    errors: List[str] = []
    total = len(coins) or 1
    completed = 0

    def check(coin):
        data = client.get_coin_data(coin, period, 1000)
        out = []
        for ev in evaluators:
            r = ev.evaluate(data)
            if r["buy"]:
                out.append((ev.id, "BUY"))
            elif r["sell"]:
                out.append((ev.id, "SELL"))
        return coin, out

    with ThreadPoolExecutor(max_workers=min(10, len(coins) or 1)) as executor:
        futures = {executor.submit(check, coin): coin for coin in coins}
        for future in as_completed(futures):
            if _cancelled(job_id):
                for pending in futures:
                    pending.cancel()
                raise RuntimeError("İş iptal edildi")
            coin = futures[future]
            try:
                coin, hits = future.result()
                for strategy_id, side in hits:
                    results[strategy_id][side].append(coin)
            except Exception as exc:
                errors.append(f"{coin}: {exc}")
            completed += 1
            if completed % max(1, total // 20) == 0 or completed == total:
                pct = 10 + int((completed / total) * 85)
                _progress(job_id, pct, f"{completed}/{total} coin tarandı")

    _progress(job_id, 99, "Sonuçlar derleniyor")
    return {"period": period, "results": results, "errors": errors[:20], "scanned": len(coins)}


# ---------------------------------------------------------------------------
# Analiz
# ---------------------------------------------------------------------------
def run_indicator_values(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tüm kayıtlı indikatörlerin değerlerini tek tabloda döndürür.

    Sütunlar kataloğdan üretilir; arayüz başlıkları indikatöre göre gruplar.
    """
    from app.strategies.registry import INDICATORS, IndicatorCache

    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1h")
    count = min(int(params.get("count", 20)), 500)
    job_id = params.get("_job_id")
    _progress(job_id, 15, "Veri çekiliyor")
    data = _client().get_coin_data(coin, period, 1000)
    start = -count
    cache = IndicatorCache(data)

    # Her indikatör için tabloda gösterilecek çıktılar.
    display = {
        "EMA": ["value"], "SMA": ["value"], "BB": ["lower", "middle", "upper"],
        "RSI": ["value"], "MACD": ["macd", "signal", "histogram"], "ATR": ["value", "atr_pct"],
        "ADX": ["adx"], "SUPERTREND": ["value", "direction"],
        "STOCHRSI": ["k", "d"], "ICHIMOKU": ["tenkan", "kijun"],
        "DONCHIAN": ["upper", "lower"], "CCI": ["value"], "MFI": ["value"],
        "MOMENTUM": ["value"], "PSAR": ["value"], "VOLUME_SMA": ["value", "ratio"],
        "BB_RSI": ["rsi", "upper", "lower"], "T3": ["value", "direction"],
        "QQE_MOD": ["signal", "histogram", "hist_state", "rsi", "trend"],
    }

    series: Dict[str, Any] = {"opendate": data["opendate"][start:]}
    columns: List[Dict[str, Any]] = []
    total = max(1, len(INDICATORS))
    for index, (key, spec) in enumerate(INDICATORS.items()):
        defaults = {p["name"]: p["default"] for p in spec["params"]}
        for output in display.get(key, spec["outputs"][:1]):
            if output not in spec["outputs"]:
                continue
            col_id = key if output == spec["outputs"][0] else f"{key}.{output}"
            try:
                values = cache.compute(key, defaults, output)
            except Exception:
                continue
            series[col_id] = values[start:]
            columns.append(
                {
                    "id": col_id,
                    "indicator": key,
                    "label": spec["label"],
                    "output": output,
                    "category": spec["category"],
                }
            )
        _progress(job_id, 15 + int(((index + 1) / total) * 80), f"{spec['label']} hesaplandı")

    _progress(job_id, 98, "Tablo hazırlanıyor")
    return {
        "coin": coin,
        "period": period,
        "rows": len(series["opendate"]),
        "columns": columns,
        "series": series,
    }


def run_strategy_values(params: Dict[str, Any]) -> Dict[str, Any]:
    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1h")
    count = min(int(params.get("count", 10)), 100)
    specs = normalize_specs(params.get("strategies") or [])
    data = _client().get_coin_data(coin, period, 1000)
    result = {}
    for spec in specs:
        ev = build_evaluator(spec)
        signals = []
        if hasattr(ev, "_run"):
            raw = ev._run(data)
            signals = raw[-count:]
        else:
            signals = []
        result[ev.id] = {
            "last_signal": signals[-1] if signals else None,
            "signals": signals,
        }
    return {"coin": coin, "period": period, "strategies": result}


def run_support_resistance(params: Dict[str, Any]) -> Dict[str, Any]:
    from core import Indikator

    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1h")
    data = _client().get_coin_data(coin, period, 1000)
    price = params.get("price")
    if price in (None, ""):
        price = data["close"][-1]
    destek, direnc, levels = Indikator.destek_direnc_hesapla(
        float(price), data["low"], int(params.get("window", 14)), float(params.get("tolerance", 0.01))
    )
    return {"coin": coin, "period": period, "price": price, "support": destek, "resistance": direnc, "levels": levels}


def run_market(params: Dict[str, Any]) -> Dict[str, Any]:
    period = params.get("period", "1h")
    specs = normalize_specs(params.get("strategies") or [])
    coins = params.get("coins") or []
    client = _client()
    if not coins:
        coins = client.coin_list()[: int(params.get("max_coins", 30))]
    evaluators = [build_evaluator(spec) for spec in specs]
    table = []

    def one(coin):
        data = client.get_coin_data(coin, period, 1000)
        values = []
        for ev in evaluators:
            r = ev.evaluate(data)
            values.append(1 if r["buy"] else -1 if r["sell"] else 0)
        avg = sum(values) / len(values) if values else 0
        return {"coin": coin, "average": round(avg, 2), "values": values}

    with ThreadPoolExecutor(max_workers=min(10, len(coins) or 1)) as executor:
        for item in executor.map(one, coins):
            table.append(item)
    table.sort(key=lambda x: x["average"], reverse=True)
    return {"period": period, "table": table}


def run_monthly(params: Dict[str, Any]) -> Dict[str, Any]:
    coin = params.get("coin", "BTCUSDT")
    period = params.get("period", "1d")
    data = _client().get_coin_data(coin, period, 1000)
    monthly: Dict[int, Dict[str, Any]] = {}
    for i, ts in enumerate(data["opendate"]):
        month = __import__("datetime").datetime.utcfromtimestamp(ts / 1000).month
        change = (data["close"][i] / data["open"][i] - 1) * 100
        bucket = monthly.setdefault(month, {"sum": 0.0, "up": 0, "down": 0, "count": 0})
        bucket["sum"] += change
        bucket["count"] += 1
        bucket["up" if change > 0 else "down"] += 1
    return {"coin": coin, "period": period, "monthly": monthly}


def run_coinlist(params: Dict[str, Any]) -> Dict[str, Any]:
    client = _client()
    if params.get("sort"):
        coins = client.coin_list()
        sorted_coins = client.coins_sorted_by_volume(coins, params.get("period", "1h"))
        client.create_coin_list(sorted_coins)
        return {"coins": sorted_coins, "count": len(sorted_coins)}
    usdt = client.trade_edilebilir_coinler().get("USDT", [])
    client.create_coin_list(usdt)
    return {"coins": usdt, "count": len(usdt)}


def run_buy_result(params: Dict[str, Any]) -> Dict[str, Any]:
    from collections import Counter

    path = "Log/buy_result.log"
    counts = Counter()
    last: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 6:
                    continue
                key = f"{parts[0]} {parts[1]} {parts[2]}"
                counts[key] += 1
                last.append(line.strip())
    except OSError:
        return {"error": "buy_result.log bulunamadı", "counts": {}}
    return {"counts": dict(counts), "last": last[-100:]}


def run_dataset(params: Dict[str, Any]) -> Dict[str, Any]:
    _araclar().veri_seti_olustur(params.get("coin", "BTCUSDT"), params.get("period", "15m"))
    return {"ok": True}


def run_strategy_results(params: Dict[str, Any]) -> Dict[str, Any]:
    from core import Backtest

    bt = Backtest()
    bt.paralel_hesaplama()
    araclar = _araclar()
    araclar.strategy_result_analyze()
    araclar.strategy_analyze_save()
    return {"ok": True}


def run_strategy_analyze_save(params: Dict[str, Any]) -> Dict[str, Any]:
    _araclar().strategy_analyze_save()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Regresyon testi (snapshot)
# ---------------------------------------------------------------------------
def run_snapshot_record(params: Dict[str, Any]) -> Dict[str, Any]:
    from app import snapshots

    job_id = params.get("_job_id")
    return snapshots.record(
        params.get("coin", "BTCUSDT"),
        params.get("period", "15m"),
        int(params.get("candles", 20000)),
        params.get("note", ""),
        progress=lambda pct, msg: _progress(job_id, pct, msg),
    )


def run_snapshot_verify(params: Dict[str, Any]) -> Dict[str, Any]:
    from app import snapshots

    job_id = params.get("_job_id")
    return snapshots.verify(
        str(params.get("snapshot_id")),
        float(params.get("tolerance") or snapshots.DEFAULT_TOL),
        progress=lambda pct, msg: _progress(job_id, pct, msg),
    )


def run_backup_create(params: Dict[str, Any]) -> Dict[str, Any]:
    from app import backup

    job_id = params.get("_job_id")
    _progress(job_id, 10, "Veritabanı kopyalanıyor")
    result = backup.create(
        note=params.get("note", ""),
        include_logs=bool(params.get("include_logs")),
        include_env=bool(params.get("include_env")),
        include_datasets=bool(params.get("include_datasets")),
        include_snapshots=bool(params.get("include_snapshots")),
        include_models=bool(params.get("include_models")),
    )
    _progress(job_id, 95, "Arşiv yazıldı")
    return result


def run_backup_restore(params: Dict[str, Any]) -> Dict[str, Any]:
    from app import backup

    job_id = params.get("_job_id")
    _progress(job_id, 10, "Botlar durduruluyor")
    result = backup.restore(str(params.get("name")))
    _progress(job_id, 95, "Geri yükleme tamamlandı")
    return result


def run_ai_train(params: Dict[str, Any]) -> Dict[str, Any]:
    from app.ai.trainer import train_model

    if not settings.AI_ENABLED:
        raise RuntimeError("AI profili etkin değil. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    job_id = params.get("_job_id")
    _progress(job_id, 5, "Veri hazırlanıyor")

    # Trainer tek seferde tüm işi yapar; ilerlemeyi kaba adımlarla bildiriyoruz.
    _progress(job_id, 15, "Veri çekiliyor ve özellikler hesaplanıyor")
    result = train_model(params)
    _progress(job_id, 95, "Model aday olarak kaydedildi")
    return {
        "ok": True,
        "model_id": (result.get("model") or {}).get("id"),
        "metrics": (result.get("model") or {}).get("metrics"),
        "report": result.get("report"),
    }


def run_ai_auto(params: Dict[str, Any]) -> Dict[str, Any]:
    from app.ai.autopilot import run_once

    if not settings.AI_ENABLED:
        raise RuntimeError("AI kapalı. Ayarlar > Sistem > Yapay zekâ özelliklerini açın.")
    job_id = params.get("_job_id")
    _progress(job_id, 10, "Otomatik öğrenme başladı: veri çekiliyor")
    result = run_once(trigger=str(params.get("trigger") or "manual"))
    _progress(job_id, 95, f"Karar: {result.get('decision')}")
    return result


# ---------------------------------------------------------------------------
HANDLERS = {
    "backtest": run_backtest,
    "backtest_all": run_backtest_all,
    "scan": run_scan,    "indicator_values": run_indicator_values,
    "strategy_values": run_strategy_values,
    "support_resistance": run_support_resistance,
    "market": run_market,
    "monthly": run_monthly,
    "coinlist": run_coinlist,
    "buy_result": run_buy_result,
    "dataset": run_dataset,
    "strategy_results": run_strategy_results,
    "strategy_analyze_save": run_strategy_analyze_save,
    "ai_train": run_ai_train,
    "ai_auto": run_ai_auto,
    "snapshot_record": run_snapshot_record,
    "snapshot_verify": run_snapshot_verify,
    "backup_create": run_backup_create,
    "backup_restore": run_backup_restore,
}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    db.init_db()
    job = db.row("SELECT * FROM jobs WHERE id=?", (args.job_id,))
    if not job:
        return 1
    db.execute(
        "UPDATE jobs SET status='running', started_at=? WHERE id=?", (db.utcnow(), args.job_id)
    )
    try:
        params = json.loads(job["params_json"])
        params["_job_id"] = args.job_id
        handler = HANDLERS.get(job["type"])
        if not handler:
            raise ValueError(f"Bilinmeyen iş türü: {job['type']}")
        db.execute(
            "UPDATE jobs SET message=?, progress=? WHERE id=?",
            ("Çalışıyor", 5, args.job_id),
        )
        result = handler(params)
        db.execute(
            "UPDATE jobs SET status='done', result_json=?, progress=100, message=?, finished_at=? WHERE id=?",
            (
                json.dumps(result, ensure_ascii=False, default=str),
                "Tamamlandı",
                db.utcnow(),
                args.job_id,
            ),
        )
        if job["type"] == "backtest":
            import uuid

            db.execute(
                "INSERT INTO strategy_backtests(id,strategy_id,version,coin,period,start_date,end_date,metrics_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    str(params.get("strategy", {}).get("id", "")),
                    int(params.get("strategy", {}).get("version", 1) or 1),
                    params.get("coin", ""),
                    params.get("period", ""),
                    None,
                    None,
                    json.dumps(result.get("metrics", {}), ensure_ascii=False),
                    db.utcnow(),
                ),
            )
    except Exception as exc:
        current = db.row("SELECT status FROM jobs WHERE id=?", (args.job_id,))
        if current and current["status"] == "cancelled":
            return 1
        db.execute(
            "UPDATE jobs SET status='error', error=?, message=?, finished_at=? WHERE id=?",
            (f"{exc}\n{traceback.format_exc()}", str(exc)[:200], db.utcnow(), args.job_id),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
