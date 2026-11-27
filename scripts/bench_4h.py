"""4h TrendRider ayarlarını aynı veriyle yeniden ölçer.

Kullanım:
    python scripts/bench_4h.py                       # dengeli (risk %4)
    python scripts/bench_4h.py --risk-pct 8          # agresif
    python scripts/bench_4h.py --bars 20000 --json out.json

Çıktı: coin başına getiri, drawdown, işlem sayısı, kazanma oranı, R:R ve
en kötü işlem. Tüm koşular komisyon + kayma dahil `run_backtest` ile yapılır.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import job_runner as jr  # noqa: E402

DEFAULT_COINS = [
    "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "SUIUSDT", "ENAUSDT", "WLDUSDT", "PEPEUSDT",
]
BASE_RISK = {
    "stop_atr": 3.0,
    "trail_atr": 6.0,
    "trail_after_pct": 10.0,
    "breakeven_pct": 20.0,
    "profit_exit_donchian": 10,
    "cooldown": 5,
}


def run(coin: str, period: str, bars: int, risk: dict, btc_regime: bool = True) -> dict:
    res = jr.run_backtest({
        "strategy": {"type": "builtin", "name": "TrendRider"},
        "coin": coin,
        "period": period,
        "cash": 100.0,
        "limit": bars,
        "risk": dict(risk),
        "filters": {"btc_regime": bool(btc_regime)},
        "source": "binance",
        "asset_class": "crypto",
    })
    m = res["metrics"]
    pnls = [
        float(t.get("pnl_pct") or 0)
        for t in (res.get("trades") or [])
        if t.get("pnl_pct") is not None
    ]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "coin": coin,
        "return_pct": round(float(m["total_return_pct"]), 1),
        "drawdown_pct": round(float(m["max_drawdown_pct"]), 1),
        "trades": int(m["trade_count"]),
        "win_rate": round(float(m["win_rate"] or 0), 0),
        "profit_factor": round(float(m.get("profit_factor") or 0), 2),
        "avg_win_pct": round(st.mean(wins), 2) if wins else 0.0,
        "avg_loss_pct": round(abs(st.mean(losses)), 2) if losses else 0.0,
        "rr": round(st.mean(wins) / abs(st.mean(losses)), 2)
        if wins and losses
        else None,
        "worst_trade_pct": round(min(pnls), 2) if pnls else None,
        "avg_hold_candles": round(float(m["avg_hold_candles"] or 0), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", default="4h")
    ap.add_argument("--bars", type=int, default=12000)
    ap.add_argument("--coins", default=",".join(DEFAULT_COINS))
    ap.add_argument("--risk-pct", type=float, default=4.0,
                    help="İşlem başına risk (sermaye yüzdesi)")
    ap.add_argument("--json", default="", help="Sonuçları bu dosyaya yaz")
    ap.add_argument("--btc-regime", dest="btc_regime", action="store_true",
                    default=True,
                    help="BTC > EMA200 değilken alım yok (varsayılan: açık)")
    ap.add_argument("--no-btc-regime", dest="btc_regime", action="store_false")
    args = ap.parse_args()

    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    risk = {**BASE_RISK, "risk_per_trade_pct": args.risk_pct}
    print(f"{args.period} / {args.bars} mum / risk %{args.risk_pct:g} / "
          f"BTC rejimi {'açık' if args.btc_regime else 'kapalı'}")
    print(f"Risk bloğu: {json.dumps(risk, ensure_ascii=False)}")

    rows = [
        run(coin, args.period, args.bars, risk, args.btc_regime)
        for coin in coins
    ]
    print(f"\n{'Coin':10} {'Getiri':>9} {'DD':>6} {'İşlem':>6} {'Kazanma':>8} "
          f"{'PF':>5} {'R:R':>5} {'En kötü':>8} {'Tutuş':>7}")
    for r in rows:
        print(f"{r['coin']:10} {r['return_pct']:8.1f}% {r['drawdown_pct']:5.1f}% "
              f"{r['trades']:6} {r['win_rate']:7.0f}% {r['profit_factor']:5.2f} "
              f"{str(r['rr']):>5} {str(r['worst_trade_pct']):>7}% "
              f"{r['avg_hold_candles']:7.1f}")

    rets = [r["return_pct"] for r in rows]
    dds = [r["drawdown_pct"] for r in rows]
    wins = [r["win_rate"] for r in rows]
    rrs = [r["rr"] for r in rows if r["rr"]]
    worst = min(r["worst_trade_pct"] for r in rows if r["worst_trade_pct"] is not None)
    print(f"\nMedyan getiri : {st.median(rets):+.1f}%")
    print(f"Ortalama      : {st.mean(rets):+.1f}%")
    print(f"En kötü coin  : {min(rets):+.1f}%")
    print(f"Ort. drawdown : {st.mean(dds):.1f}%")
    print(f"Ort. kazanma  : {st.mean(wins):.0f}%")
    print(f"Ort. R:R      : {st.mean(rrs):.2f}")
    print(f"En kötü işlem : {worst:.2f}% (fiyat)")
    if rrs:
        wr = st.mean(wins) / 100
        rr = st.mean(rrs)
        print(f"Beklenti/işlem: {wr * rr - (1 - wr):+.2f} R")
    print(f"Pozitif coin  : {sum(1 for r in rets if r > 0)}/{len(rets)}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"risk": risk, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nYazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
