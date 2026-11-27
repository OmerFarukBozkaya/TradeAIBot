#!/usr/bin/env python3
"""Trend takibi için mevcut stratejileri günceller (ölçülmüş risk + sinyal).

Ne yapar?
  1. Seçili stratejilerin **risk** bloğunu trend takibine uygun hale getirir:
     stop 3×ATR, takipli stop 5×ATR (%5 kârda devreye girer), breakeven %12,
     kâr koruma Donchian(10). Ölçüm: 4h'de getiri ~2×, en kötü senaryo yarıya
     iniyor (eski 20/25 ayarlarında stop 6×ATR'ye kırpılıyor ve breakeven
     %4,8'de çalışıp trendi sıfıra çekiyordu).
  2. (isteğe bağlı) `--signal` ile giriş/çıkış kurallarını **Trend Sürücü**'ye
     çevirir: 40 mumluk zirve kırılımı + EMA50>EMA200 rejimi + ADX>18; çıkış
     40 mum dibi veya rejim bozulması. Ölçülen 4h sonucu: 4/5 coin pozitif,
     medyan +%70 (eski SuperTrend(20,5) sinyali testere dişinde kaybediyordu).
  3. (isteğe bağlı) `--update-bots` ile bu stratejiyi kullanan botları yeni
     sürüme bağlar (botlar sürümü sabitlediği için aksi halde eski kurallar
     çalışmaya devam eder).

Güvenlik: varsayılan **dry-run**'dır; hiçbir şey yazmaz. Uygulamak için
`--apply`. Uygularken önce `Data/tradeai.db` yedeği alınır. Her değişiklik
**yeni sürüm** olarak yazılır; eski sürüm `strategy_versions` tablosunda kalır
(geri dönmek için botu eski sürüme bağlamak yeterli).

Kullanım:
    python scripts/upgrade_trend_strategies.py                 # önizleme
    python scripts/upgrade_trend_strategies.py --apply          # sadece risk
    python scripts/upgrade_trend_strategies.py --apply --signal # risk + sinyal
    python scripts/upgrade_trend_strategies.py --apply --signal --update-bots
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.paths import paths  # noqa: E402
from app.strategies import service  # noqa: E402

# Trend takibi risk şablonu (periyoda göre).
TREND_RISK = {
    "15m": {"stop_atr": 2.5, "trail_atr": 4, "trail_after_pct": 3, "breakeven_pct": 8,
            "profit_exit_donchian": 10, "cooldown": 5, "take_profit": True},
    "1h": {"stop_atr": 3, "trail_atr": 5, "trail_after_pct": 5, "breakeven_pct": 12,
           "profit_exit_donchian": 10, "cooldown": 5, "take_profit": True},
    "4h": {"stop_atr": 3, "trail_atr": 5, "trail_after_pct": 5, "breakeven_pct": 12,
           "profit_exit_donchian": 10, "cooldown": 5, "take_profit": True},
    "1d": {"stop_atr": 3, "trail_atr": 6, "trail_after_pct": 8, "breakeven_pct": 15,
           "profit_exit_donchian": 20, "cooldown": 3, "take_profit": True},
}

# Trend Sürücü kuralları (compiled JSON). 40/40 kırılım + EMA rejimi + ADX.
# ÖNEMLİ: Donchian bandı kendi mumunu içerir; "kesti" koşulu için bant bir mum
# geriye kaydırılmalı (offset shift 1). Aksi halde upper >= high >= close
# olduğundan kırılım hiç tetiklenmez ve strateji işlem açmaz.
TREND_SIGNAL = {
    "buy": {
        "logic": "AND",
        "conditions": [
            {"left": {"type": "price", "field": "close"}, "op": "crosses_above",
             "right": {"type": "offset", "shift": 1, "operand": {
                 "type": "indicator", "id": "DONCHIAN", "params": {"length": 40},
                 "output": "upper"}}},
            {"left": {"type": "indicator", "id": "EMA", "params": {"length": 50}, "output": "value"},
             "op": "gt",
             "right": {"type": "indicator", "id": "EMA", "params": {"length": 200}, "output": "value"}},
            {"left": {"type": "indicator", "id": "ADX", "params": {"length": 14}, "output": "adx"},
             "op": "gt", "right": {"type": "constant", "value": 18}},
        ],
    },
    "sell": {
        "logic": "OR",
        "conditions": [
            {"left": {"type": "price", "field": "close"}, "op": "crosses_below",
             "right": {"type": "offset", "shift": 1, "operand": {
                 "type": "indicator", "id": "DONCHIAN", "params": {"length": 40},
                 "output": "lower"}}},
            {"left": {"type": "indicator", "id": "EMA", "params": {"length": 50}, "output": "value"},
             "op": "lt",
             "right": {"type": "indicator", "id": "EMA", "params": {"length": 200}, "output": "value"}},
        ],
    },
}

# Varsayılan hedefler: sunucudaki 4 botun stratejileri.
DEFAULT_TARGETS = {
    "1h Kısa Vade": "1h",
    "4h Kırılım Swing": "4h",
    "15m Kısa Vade": "15m",
    "15m Kısa Vade Pro": "15m",
    "1d Kırılım Pozisyon": "1d",
    "Genel Trend Takipçisi": "4h",
}


def _bot_period(strategy_name: str) -> str:
    return DEFAULT_TARGETS.get(strategy_name, "")


def _plan(apply: bool, signal: bool, update_bots: bool) -> int:
    rows = db.rows("SELECT id,name,version,status,definition_json FROM strategies ORDER BY name")
    targets = [r for r in rows if r["name"] in DEFAULT_TARGETS]
    if not targets:
        print("Güncellenecek strateji bulunamadı (isimler eşleşmedi).")
        print("Mevcut:", ", ".join(r["name"] for r in rows) or "-")
        return 1

    bots = db.rows("SELECT id,name,period,config_json FROM bots")
    changes = 0
    for row in targets:
        definition = json.loads(row["definition_json"] or "{}")
        period = _bot_period(row["name"])
        risk = dict(TREND_RISK.get(period, TREND_RISK["4h"]))
        old_risk = definition.get("risk") or {}
        new_def = dict(definition)
        new_def["risk"] = risk
        if signal:
            new_def.update(json.loads(json.dumps(TREND_SIGNAL)))

        print(f"\n=== {row['name']} (v{row['version']}, {period})")
        print("  risk  eski:", json.dumps(old_risk, ensure_ascii=False))
        print("  risk  yeni:", json.dumps(risk, ensure_ascii=False))
        if signal:
            print("  sinyal: Trend Sürücü (Donchian40 kırılım + EMA50/200 + ADX18)")

        up_to_date = new_def == definition
        if up_to_date:
            print("  = tanım zaten güncel")

        linked = []
        for bot in bots:
            try:
                cfg = json.loads(bot["config_json"] or "{}")
            except ValueError:
                continue
            for spec in cfg.get("strategies") or []:
                if (spec.get("type") or spec.get("kind")) != "custom":
                    continue
                if spec.get("id") != row["id"]:
                    continue
                linked.append((bot, cfg, spec))
                print(f"  bot: {bot['name']} ({bot['period']}) → pinli sürüm {spec.get('version')}")

        if up_to_date:
            # Tanım değişmese bile botlar eski sürüme sabit olabilir.
            stale = [(b, c, s) for b, c, s in linked
                     if int(s.get("version") or 0) != int(row["version"])]
            if stale and update_bots and apply:
                for bot, cfg, spec in stale:
                    spec["version"] = row["version"]
                    db.execute(
                        "UPDATE bots SET config_json=?, updated_at=? WHERE id=?",
                        (json.dumps(cfg, ensure_ascii=False), db.utcnow(), bot["id"]),
                    )
                    print(f"  → bot {bot['name']} v{row['version']} sürümüne bağlandı")
                changes += 1
            elif stale:
                print(f"  ! {len(stale)} bot eski sürüme sabit; --update-bots ile bağlanır.")
            continue

        changes += 1
        if not apply:
            continue

        updated = service.update_custom(row["id"], new_def)
        new_version = updated["version"]
        print(f"  → yeni sürüm v{new_version} yazıldı")
        if update_bots:
            for bot, cfg, spec in linked:
                spec["version"] = new_version
                db.execute(
                    "UPDATE bots SET config_json=?, updated_at=? WHERE id=?",
                    (json.dumps(cfg, ensure_ascii=False), db.utcnow(), bot["id"]),
                )
                print(f"  → bot {bot['name']} v{new_version} sürümüne bağlandı")
        elif linked:
            print("  ! Botlar eski sürüme sabitli; --update-bots olmadan etkilenmez.")

    print()
    if not apply:
        print(f"ÖNİZLEME: {changes} strateji güncellenecek. Uygulamak için --apply ekleyin.")
        if not signal:
            print("İpucu: sinyalleri de Trend Sürücü'ye çevirmek için --signal ekleyin.")
        if not update_bots:
            print("İpucu: çalışan botları bağlamak için --update-bots ekleyin.")
    else:
        print(f"{changes} strateji güncellendi.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="değişiklikleri yaz (varsayılan: önizleme)")
    ap.add_argument("--signal", action="store_true", help="giriş/çıkış kurallarını Trend Sürücü yap")
    ap.add_argument("--update-bots", action="store_true", help="bu stratejiyi kullanan botları yeni sürüme bağla")
    ap.add_argument("--no-backup", action="store_true", help="DB yedeği alma (önerilmez)")
    args = ap.parse_args()

    if args.apply and not args.no_backup:
        src = Path(paths.db)
        if src.exists():
            stamp = db.utcnow()[:10]
            dst = src.with_name(f"{src.stem}.before_trend_{stamp}.db")
            shutil.copy2(src, dst)
            print(f"Yedek: {dst}")
        else:
            print(f"UYARI: veritabanı bulunamadı: {src}")

    return _plan(args.apply, args.signal, args.update_bots)


if __name__ == "__main__":
    raise SystemExit(main())
