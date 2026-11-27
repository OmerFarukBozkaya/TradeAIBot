"""Yanlışlıkla aynı sinyale çevrilen stratejilerin ÖZGÜN sinyalini geri yükler.

`upgrade_trend_strategies.py --signal` altı stratejinin giriş/çıkış kurallarını
TrendRider kırılımıyla değiştirmişti. Bu, 6 farklı stratejiyi birebir aynı
yaparak çeşitliliği yok etti (panelde hepsi aynı sonucu verince "bozuk"
görünüyor). Burada her stratejinin **önceki özgün sinyali** sürüm geçmişinden
geri alınır; yalnızca risk bloğu iyileştirilmiş hâliyle kalır.

Kullanım:
    python scripts/restore_original_signals.py            # önizleme
    python scripts/restore_original_signals.py --apply
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

TARGETS = [
    "15m Kısa Vade",
    "15m Kısa Vade Pro",
    "1h Kısa Vade",
    "4h Kırılım Swing",
    "1d Kırılım Pozisyon",
    "Genel Trend Takipçisi",
]


def _same_signal(a: dict, b: dict) -> bool:
    return (
        json.dumps(a.get("buy"), sort_keys=True) == json.dumps(b.get("buy"), sort_keys=True)
        and json.dumps(a.get("sell"), sort_keys=True) == json.dumps(b.get("sell"), sort_keys=True)
    )


def _original(sid: str) -> dict | None:
    """Sürüm geçmişinde, mevcut (kırılım) sinyalden farklı en yeni tanım."""
    current = service.get_custom(sid)
    if not current:
        return None
    cur_def = current["definition"]
    rows = db.rows(
        "SELECT version, definition_json FROM strategy_versions WHERE strategy_id=? "
        "ORDER BY version DESC",
        (sid,),
    )
    skipped = 0
    for row in rows:
        try:
            d = json.loads(row["definition_json"] or "{}")
        except ValueError:
            continue
        if _same_signal(d, cur_def):
            skipped += 1
            continue
        # Kırılım imzasını taşıyan sürümleri atla (bizim yazdıklarımız).
        buy = json.dumps(d.get("buy"), sort_keys=True)
        if "Donchian" in buy or '"DONCHIAN"' in buy or '"length": 40' in buy:
            # Bu sürüm de bizim kırılımımız olabilir; risk bloğu ve ADX'e bak.
            if '"value": 18' in buy or '"value": 25' in buy:
                skipped += 1
                continue
        return d
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    strategies = {r["name"]: r for r in db.rows("SELECT id,name,version FROM strategies")}
    plan = []
    for name in TARGETS:
        row = strategies.get(name)
        if not row:
            print(f"  ! bulunamadı: {name}")
            continue
        current = service.get_custom(row["id"])
        original = _original(row["id"])
        if not original:
            print(f"  ? {name}: özgün sürüm bulunamadı, atlanıyor")
            continue
        new_def = dict(original)
        new_def["name"] = name
        # Risk bloğunu mevcut (iyileştirilmiş) hâliyle koru.
        new_def["risk"] = (current["definition"].get("risk") or original.get("risk") or {})
        changed = json.dumps(new_def, sort_keys=True) != json.dumps(
            current["definition"], sort_keys=True
        )
        print(f"  {name}: v{row['version']} → özgün sinyal geri yüklenecek "
              f"(risk korunur) {'[değişiklik var]' if changed else '[zaten aynı]'}")
        if changed:
            plan.append((name, row["id"], new_def))

    if not args.apply:
        print(f"\nÖNİZLEME: {len(plan)} strateji geri yüklenecek. --apply ile uygula.")
        return 0
    if not plan:
        print("\nYapılacak değişiklik yok.")
        return 0

    src = Path(paths.db)
    if src.exists():
        stamp = db.utcnow()[:10]
        dst = src.with_name(f"{src.stem}.before_restore_{stamp}.db")
        shutil.copy2(src, dst)
        print(f"Yedek: {dst}")

    for name, sid, new_def in plan:
        updated = service.update_custom(sid, new_def)
        print(f"  → {name} v{updated['version']} yazıldı")
    print(f"\n{len(plan)} strateji özgün sinyaline döndü (risk iyileştirmesi korundu).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
