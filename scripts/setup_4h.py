#!/usr/bin/env python3
"""4h trend botunu ölçülmüş ayarlarla kurar.

Neden 8 bot?
    Canlı/paper motorda bir bot **aynı anda tek pozisyon** tutar. 8 coini tek
    botta çalıştırırsanız ilk sinyal gelen coin pozisyonu açar, diğerleri
    bekler; yani çeşitlendirme olmaz. Backtest'ler her coini bağımsız
    varsaydığı için en tutarlı kurulum **8 bot × 1 coin**'dir.

Kullanım:
    python scripts/setup_4h.py                    # önizleme (8 bot, paper)
    python scripts/setup_4h.py --apply            # 8 bot oluştur
    python scripts/setup_4h.py --apply --mode live
    python scripts/setup_4h.py --apply --single   # tek bot, 8 coin, risk %2,5
    python scripts/setup_4h.py --apply --cash 500 --risk 2.5
    python scripts/setup_4h.py --apply --no-btc-regime

Varsayılanlar: BTC > EMA200 rejim filtresi açık; canlı modda günlük zarar
limiti %3; paper modda günlük limit kapalı (backtest ile aynı davranış).

Güvenlik:
    * Varsayılan **dry-run**'dır; `--apply` olmadan hiçbir şey yazılmaz.
    * Aynı isimde bot varsa atlanır (komut idempotenttir).
    * `--mode live` için sunucudaki canlı işlem anahtarı açık olmalıdır.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import coin_lists, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.risk import normalize_risk  # noqa: E402
from app.strategies.service import build_evaluator, list_builtin  # noqa: E402

COIN_LIST_NAME = "Trend 4h"
DEFAULT_COINS = [
    "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "SUIUSDT", "ENAUSDT", "WLDUSDT", "PEPEUSDT",
]

# Ölçülen ayar (bkz. docs/STRATEGY_4H.md): trail 6×ATR, %10 kârda devreye,
# %20 breakeven, 10 mum kâr koruma, 5 mum bekleme. Kâr al kapalı.
# %10/%20, %8/%15'e göre medyanı ~2 puan düşürüyor ama en kötü coini
# +%29,8'den +%49,8'e çıkarıyor (risk-adjusted daha iyi).
BASE_RISK = {
    "stop_atr": 3.0,
    "trail_atr": 6.0,
    "trail_after_pct": 10.0,
    "breakeven_pct": 20.0,
    "profit_exit_donchian": 10,
    "cooldown": 5,
    "take_profit": False,
}


def _builtin_label(name: str) -> str:
    for item in list_builtin(include_archived=True):
        if item["name"] == name:
            return item.get("label") or name
    return name


def _resolve_coins() -> tuple[list[str], dict | None]:
    """`Trend 4h` listesini bulur; yoksa ölçülen sabit listeye düşer."""
    for item in coin_lists.list_lists():
        if item["name"] == COIN_LIST_NAME and not item.get("builtin"):
            meta = {"id": item["id"], "name": item["name"], "count": item["count"]}
            return list(item["coins"]), meta
    return list(DEFAULT_COINS), None


def _bot_config(
    coins: list[str],
    cash: float,
    risk: dict,
    coin_meta: dict | None,
    filters: dict | None = None,
) -> dict:
    config = {
        "period": "4h",
        "strategies": [
            {
                "type": "builtin",
                "name": "TrendRider",
                "label": _builtin_label("TrendRider"),
            }
        ],
        "coins": coins,
        "cash": round(float(cash), 8),
        "asset_class": "crypto",
        "risk": risk,
        "filters": dict(filters or {}),
        "max_position_pct": 100,
    }
    if coin_meta:
        config["coin_list"] = coin_meta
    return config


def _check_live_gate() -> str | None:
    if not settings.LIVE_ENABLED:
        return (
            "Canlı işlem sunucu izni kapalı. Ayarlar > İşlem bölümünden "
            "LIVE_TRADING_ENABLED açılmalı."
        )
    if not db.get_setting("live_trading_unlocked", False):
        return "Canlı işlem anahtarı kapalı. Panelin üst çubuğundan açın."
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Botları veritabanına yaz")
    ap.add_argument("--single", action="store_true",
                    help="8 bot yerine tek bot (8 coin, tek pozisyon!)")
    ap.add_argument("--mode", choices=("paper", "live"), default="paper")
    ap.add_argument("--risk", type=float, default=None,
                    help="İşlem başına risk yüzdesi (8 bot: 4, tek bot: 2.5)")
    ap.add_argument("--cash", type=float, default=1000.0,
                    help="Toplam sermaye; botlara eşit bölünür")
    ap.add_argument("--daily-loss", type=float, default=None,
                    help="Günlük zarar limiti yüzdesi (canlı: 3, paper: 0)")
    ap.add_argument("--btc-regime", dest="btc_regime", action="store_true",
                    default=True,
                    help="BTC > EMA200 değilken yeni alım açma (varsayılan: açık)")
    ap.add_argument("--no-btc-regime", dest="btc_regime", action="store_false",
                    help="BTC rejim filtresini kapat")
    ap.add_argument("--prefix", default="Trend 4h", help="Bot adı öneki")
    args = ap.parse_args()

    db.init_db()
    if args.cash <= 0:
        print("Hata: --cash pozitif olmalı", file=sys.stderr)
        return 2

    coins, coin_meta = _resolve_coins()
    if not coins:
        print("Hata: coin listesi boş", file=sys.stderr)
        return 2

    default_risk = 2.5 if args.single else 4.0
    risk_pct = default_risk if args.risk is None else float(args.risk)
    if args.mode == "live" and risk_pct > 4.0:
        print(
            f"Uyarı: canlı modda risk %{risk_pct:g}. Ölçülen güvenli üst sınır "
            "%4; %8'de drawdown ~%49.",
            file=sys.stderr,
        )

    daily_loss = args.daily_loss if args.daily_loss is not None else (
        3.0 if args.mode == "live" else 0.0
    )
    risk_block = {**BASE_RISK, "risk_per_trade_pct": risk_pct}
    if daily_loss > 0:
        risk_block["daily_loss_limit_pct"] = daily_loss
    risk, warnings = normalize_risk(risk_block, "4h")
    for warning in warnings:
        print(f"Risk uyarısı: {warning}", file=sys.stderr)

    # Motorun stratejiyi gerçekten kurabildiğini doğrula.
    try:
        build_evaluator({"type": "builtin", "name": "TrendRider"})
    except Exception as exc:  # noqa: BLE001
        print(f"Hata: TrendRider yüklenemedi: {exc}", file=sys.stderr)
        return 2

    if args.mode == "live":
        problem = _check_live_gate()
        if problem:
            print(f"Hata: {problem}", file=sys.stderr)
            return 2

    groups = [([coin], f"{args.prefix} · {coin}") for coin in coins] \
        if not args.single else [(coins, f"{args.prefix} · tek bot")]
    per_bot = args.cash / len(groups)
    filters = {"btc_regime": True} if args.btc_regime else {}

    print(f"Periyot      : 4h")
    print(f"Strateji     : TrendRider (40 mum kırılım + EMA50>EMA200 + ADX>18)")
    print(f"Coin listesi : {COIN_LIST_NAME} ({len(coins)} coin)"
          + ("" if coin_meta else "  [liste yok, sabit liste kullanılıyor]"))
    print(f"Mod          : {args.mode}")
    print(f"Bot sayısı   : {len(groups)}")
    print(f"Sermaye      : {args.cash:g} → bot başına {per_bot:g}")
    print(f"İşlem riski  : %{risk.get('risk_per_trade_pct', 0):g} "
          f"(bot sermayesinin; tek işlem planlı zararı ≈ {per_bot * risk_pct / 100:g})")
    print(f"Günlük limit : " + (f"%{daily_loss:g} (yeni giriş durur)" if daily_loss > 0 else "kapalı"))
    print(f"BTC rejimi   : " + ("açık (BTC > EMA200)" if args.btc_regime else "kapalı"))
    print(f"Risk bloğu   : {json.dumps(risk, ensure_ascii=False)}")
    print()

    created = 0
    skipped = 0
    for group, name in groups:
        if db.row("SELECT id FROM bots WHERE name=?", (name,)):
            print(f"  atla     {name} (zaten var)")
            skipped += 1
            continue
        if not args.apply:
            print(f"  oluştur  {name}  coins={','.join(group)}  cash={per_bot:g}")
            created += 1
            continue

        bot_id = f"bot_{uuid.uuid4().hex[:10]}"
        now = db.utcnow()
        config = _bot_config(
            group, per_bot, risk, coin_meta if args.single else None, filters
        )
        db.execute(
            "INSERT INTO bots(id,name,type,mode,period,config_json,status,"
            "auto_restart,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                bot_id, name, "trade", args.mode, "4h",
                json.dumps(config, ensure_ascii=False),
                "stopped", 1, now, now,
            ),
        )
        db.log_event(bot_id, f"Kurulum betiğiyle oluşturuldu ({args.mode}, 4h)", "info")
        print(f"  eklendi  {name}  ({bot_id})")
        created += 1

    print()
    if not args.apply:
        print(f"Önizleme: {created} bot oluşturulacak, {skipped} atlanacak.")
        print("Uygulamak için: python scripts/setup_4h.py --apply")
    else:
        print(f"Bitti: {created} bot oluşturuldu, {skipped} atlandı.")
        print("Panelden botları tek tek başlatın (durum: stopped).")
    if args.single:
        print(
            "\nNot: tek bot aynı anda tek pozisyon tutar. 8 coin çeşitlendirme "
            "sağlamaz; bu yüzden risk %2,5 ile sınırlı tutulmalı."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
