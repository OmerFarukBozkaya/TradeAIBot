"""Eski `Log/islem_gecmisi.log` kayıtlarını SQLite ledger'a aktarır.

Yalnızca bir kez, tablo boşsa çalışır. Biçim değişirse sessizce atlanır.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app import db

BUY_RE = re.compile(
    r"(?P<ts>\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}).*?"
    r"(?P<strategy>\S+) (?P<period>\S+) AL \| (?P<coin>[A-Z0-9]+) alındı, "
    r"Adet: (?P<qty>[\d.]+), Fiyat: (?P<price>[\d.]+)"
)
SELL_RE = re.compile(
    r"(?P<ts>\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}).*?"
    r"(?P<strategy>\S+) (?P<period>\S+) SAT(?: \[(?P<reason>[A-Z\-]+)\])? \| "
    r"(?P<coin>[A-Z0-9]+) satıldı,.*?Fiyat: (?P<price>[\d.]+)"
    r"(?: Kar/Zarar: (?P<pnl>-?[\d.]+)%)?"
)


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def migrate(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    existing = db.row("SELECT COUNT(*) AS c FROM trades")
    if existing and int(existing["c"]) > 0:
        return 0

    imported = 0
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                buy = BUY_RE.search(line)
                sell = SELL_RE.search(line) if not buy else None
                if buy:
                    qty = _safe_float(buy.group("qty"))
                    price = _safe_float(buy.group("price"))
                    if not qty or not price:
                        continue
                    db.execute(
                        "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,mode,reason,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            None,
                            buy.group("coin"),
                            "BUY",
                            qty,
                            price,
                            0.0,
                            "legacy",
                            f"{buy.group('strategy')} / {buy.group('period')}",
                            buy.group("ts"),
                        ),
                    )
                    imported += 1
                elif sell:
                    qty = 1.0
                    price = _safe_float(sell.group("price"))
                    if not price:
                        continue
                    db.execute(
                        "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,mode,reason,pnl_pct,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            None,
                            sell.group("coin"),
                            "SELL",
                            qty,
                            price,
                            0.0,
                            "legacy",
                            f"{sell.group('strategy')} / {sell.group('period')}",
                            _safe_float(sell.group("pnl")),
                            sell.group("ts"),
                        ),
                    )
                    imported += 1
    except OSError:
        return imported

    if imported:
        db.log_event(None, f"Eski işlem geçmişi içe aktarıldı: {imported} kayıt", "info")
    return imported
