from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app import db

router = APIRouter()


@router.get("/trades")
async def trades(
    bot_id: Optional[str] = None,
    coin: Optional[str] = None,
    side: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = Query(default=200, le=2000),
    offset: int = 0,
):
    sql = "SELECT * FROM trades WHERE 1=1"
    params = []
    if bot_id:
        sql += " AND bot_id=?"
        params.append(bot_id)
    if coin:
        sql += " AND coin=?"
        params.append(coin)
    if side:
        sql += " AND side=?"
        params.append(side.upper())
    if mode:
        sql += " AND mode=?"
        params.append(mode)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return db.rows(sql, params)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """ISO/DB zaman damgasını datetime'a çevirir (hatalıysa None)."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _seconds_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    a, b = _parse_ts(start), _parse_ts(end)
    if not a or not b:
        return None
    return max(0, int((b - a).total_seconds()))


def pair_round_trips(rows: List[dict]) -> Dict[str, Any]:
    """AL/SAT kayıtlarını FIFO eşleştirip tur başına K/Z üretir.

    ``trades`` tablosunda her satır tek bir emirdir. Bir pozisyonun gerçek
    kârı, alış maliyeti (komisyon dahil) ile satış geliri (komisyon düşülmüş)
    arasındaki farktır; yüzde ise maliyete göre hesaplanır. Kısmi satışlarda
    alış lotu parça parça tüketilir.
    """
    lots: Dict[str, List[Dict[str, Any]]] = {}
    closed: List[Dict[str, Any]] = []
    unmatched_sells: List[Dict[str, Any]] = []
    total_fees = 0.0

    ordered = sorted(rows, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))
    for row in ordered:
        side = str(row.get("side") or "").upper()
        coin = str(row.get("coin") or "").upper()
        qty = float(row.get("quantity") or 0.0)
        price = float(row.get("price") or 0.0)
        fee = float(row.get("fee") or 0.0)
        total_fees += fee
        if qty <= 0 or price <= 0:
            continue
        unit_fee = fee / qty if qty else 0.0
        if side == "BUY":
            lots.setdefault(coin, []).append(
                {
                    "coin": coin,
                    "quantity": qty,
                    "price": price,
                    "unit_fee": unit_fee,
                    "time": row.get("created_at"),
                    "mode": row.get("mode"),
                    "reason": row.get("reason"),
                }
            )
            continue

        # SATIŞ: FIFO tüket
        remaining = qty
        consumed: List[Dict[str, Any]] = []
        queue = lots.get(coin) or []
        while remaining > 1e-12 and queue:
            lot = queue[0]
            take = min(remaining, float(lot["quantity"]))
            consumed.append(
                {
                    "quantity": take,
                    "entry_price": float(lot["price"]),
                    "entry_fee": take * float(lot["unit_fee"]),
                    "entry_time": lot["time"],
                    "entry_reason": lot.get("reason"),
                }
            )
            lot["quantity"] = float(lot["quantity"]) - take
            remaining -= take
            if lot["quantity"] <= 1e-12:
                queue.pop(0)
        if not consumed:
            unmatched_sells.append(
                {
                    "coin": coin,
                    "quantity": qty,
                    "price": price,
                    "time": row.get("created_at"),
                    "reason": row.get("reason"),
                }
            )
            continue

        qty_matched = sum(c["quantity"] for c in consumed)
        cost = sum(c["quantity"] * c["entry_price"] + c["entry_fee"] for c in consumed)
        proceeds = qty_matched * price - qty_matched * unit_fee
        pnl_money = proceeds - cost
        pnl_pct = (pnl_money / cost * 100.0) if cost > 0 else 0.0
        entry_time = consumed[0]["entry_time"]
        closed.append(
            {
                "coin": coin,
                "quantity": round(qty_matched, 10),
                "entry_price": round(
                    sum(c["quantity"] * c["entry_price"] for c in consumed) / qty_matched, 10
                ),
                "exit_price": round(price, 10),
                "entry_time": entry_time,
                "exit_time": row.get("created_at"),
                "hold_seconds": _seconds_between(entry_time, row.get("created_at")),
                "invested": round(cost, 6),
                "proceeds": round(proceeds, 6),
                "pnl_money": round(pnl_money, 6),
                "pnl_pct": round(pnl_pct, 3),
                "fee": round(sum(c["entry_fee"] for c in consumed) + qty_matched * unit_fee, 6),
                "exit_reason": row.get("reason"),
                "entry_reason": consumed[0].get("entry_reason"),
                "mode": row.get("mode"),
                "partial": bool(remaining > 1e-12),
            }
        )

    open_lots = [
        {
            "coin": lot["coin"],
            "quantity": round(float(lot["quantity"]), 10),
            "entry_price": round(float(lot["price"]), 10),
            "invested": round(float(lot["quantity"]) * float(lot["price"]), 6),
            "entry_time": lot["time"],
            "age_seconds": _seconds_between(lot["time"], None),
        }
        for coin_lots in lots.values()
        for lot in coin_lots
        if float(lot["quantity"]) > 1e-12
    ]
    for lot in open_lots:
        lot["age_seconds"] = _seconds_between(lot["entry_time"], datetime.now(timezone.utc).isoformat())

    wins = [t for t in closed if t["pnl_money"] > 0]
    losses = [t for t in closed if t["pnl_money"] <= 0]
    gross_win = sum(t["pnl_money"] for t in wins)
    gross_loss = abs(sum(t["pnl_money"] for t in losses))
    invested = sum(t["invested"] for t in closed)
    total_pnl = sum(t["pnl_money"] for t in closed)
    holds = [t["hold_seconds"] for t in closed if t["hold_seconds"] is not None]

    by_coin: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        item = by_coin.setdefault(
            t["coin"],
            {"coin": t["coin"], "trades": 0, "wins": 0, "losses": 0,
             "pnl_money": 0.0, "invested": 0.0, "hold_seconds": 0},
        )
        item["trades"] += 1
        item["wins" if t["pnl_money"] > 0 else "losses"] += 1
        item["pnl_money"] += t["pnl_money"]
        item["invested"] += t["invested"]
        item["hold_seconds"] += t["hold_seconds"] or 0

    coins = []
    for item in by_coin.values():
        coins.append(
            {
                "coin": item["coin"],
                "trades": item["trades"],
                "wins": item["wins"],
                "losses": item["losses"],
                "win_rate": round(item["wins"] / item["trades"] * 100, 1) if item["trades"] else None,
                "pnl_money": round(item["pnl_money"], 4),
                "pnl_pct": round(item["pnl_money"] / item["invested"] * 100, 2) if item["invested"] else None,
                "avg_hold_seconds": int(item["hold_seconds"] / item["trades"]) if item["trades"] else 0,
            }
        )
    coins.sort(key=lambda c: c["pnl_money"], reverse=True)

    cumulative = 0.0
    series = []
    for t in closed:
        cumulative += t["pnl_money"]
        series.append(round(cumulative, 4))

    reasons: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        key = str(t.get("exit_reason") or "bilinmiyor")
        item = reasons.setdefault(key, {"reason": key, "trades": 0, "pnl_money": 0.0})
        item["trades"] += 1
        item["pnl_money"] += t["pnl_money"]
    exit_reasons = sorted(reasons.values(), key=lambda r: r["trades"], reverse=True)
    for item in exit_reasons:
        item["pnl_money"] = round(item["pnl_money"], 4)

    return {
        "summary": {
            "closed_trades": len(closed),
            "open_positions": len(open_lots),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
            "pnl_money": round(total_pnl, 4),
            "pnl_pct": round(total_pnl / invested * 100, 2) if invested else None,
            "invested": round(invested, 4),
            "avg_pnl_money": round(total_pnl / len(closed), 4) if closed else None,
            "best": round(max((t["pnl_money"] for t in closed), default=0.0), 4),
            "worst": round(min((t["pnl_money"] for t in closed), default=0.0), 4),
            "best_pct": round(max((t["pnl_pct"] for t in closed), default=0.0), 2),
            "worst_pct": round(min((t["pnl_pct"] for t in closed), default=0.0), 2),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            "avg_hold_seconds": int(sum(holds) / len(holds)) if holds else None,
            "min_hold_seconds": min(holds) if holds else None,
            "max_hold_seconds": max(holds) if holds else None,
            "fees": round(total_fees, 4),
            "buy_orders": sum(1 for r in ordered if str(r.get("side") or "").upper() == "BUY"),
            "sell_orders": sum(1 for r in ordered if str(r.get("side") or "").upper() == "SELL"),
        },
        "trades": list(reversed(closed)),
        "open_lots": open_lots,
        "unmatched_sells": unmatched_sells[-20:],
        "by_coin": coins,
        "by_exit_reason": exit_reasons,
        "series": series,
    }


@router.get("/trades/bot/{bot_id}/analysis")
async def bot_trade_analysis(bot_id: str, limit: int = Query(default=2000, le=10000)):
    """Botun işlem analizi: tur bazında K/Z, tutma süresi ve toplamlar."""
    rows = db.rows(
        "SELECT * FROM trades WHERE bot_id=? ORDER BY created_at LIMIT ?",
        (bot_id, int(limit)),
    )
    result = pair_round_trips(rows)
    result["bot_id"] = bot_id
    result["orders"] = len(rows)
    result["limited"] = len(rows) >= int(limit)
    return result


@router.get("/positions")
async def positions(status: str = "open"):
    return db.rows(
        "SELECT * FROM positions WHERE status=? ORDER BY opened_at DESC LIMIT 500", (status,)
    )


@router.get("/stats")
async def stats(days: int = Query(default=30, ge=1, le=365)):
    """Dashboard grafikleri için özet seriler."""
    rows = db.rows("SELECT created_at, pnl_pct, mode, bot_id, coin, side FROM trades ORDER BY created_at")
    sells = [r for r in rows if r["side"] == "SELL" and r["pnl_pct"] is not None]

    equity = []
    factor = 1.0
    for r in sells:
        try:
            factor *= 1 + float(r["pnl_pct"]) / 100.0
        except (TypeError, ValueError):
            continue
        equity.append({"t": r["created_at"], "value": round((factor - 1) * 100, 3)})

    daily_map = {}
    for r in sells:
        day = (r["created_at"] or "")[:10]
        if not day:
            continue
        bucket = daily_map.setdefault(day, {"date": day, "pnl": 0.0, "trades": 0})
        bucket["pnl"] += float(r["pnl_pct"])
        bucket["trades"] += 1
    daily = [daily_map[k] for k in sorted(daily_map)][-days:]

    by_bot = {}
    for r in rows:
        key = r["bot_id"] or "-"
        item = by_bot.setdefault(
            key, {"bot_id": r["bot_id"], "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "series": []}
        )
        if r["side"] == "SELL" and r["pnl_pct"] is not None:
            pnl = float(r["pnl_pct"])
            item["trades"] += 1
            item["wins" if pnl > 0 else "losses"] += 1
            item["pnl"] = round(item["pnl"] + pnl, 3)
            item["series"].append(item["pnl"])
    for item in by_bot.values():
        item["series"] = item["series"][-40:]

    by_coin = {}
    for r in sells:
        key = r["coin"] or "-"
        item = by_coin.setdefault(key, {"coin": key, "trades": 0, "pnl": 0.0})
        item["trades"] += 1
        item["pnl"] = round(item["pnl"] + float(r["pnl_pct"]), 3)
    coins = sorted(by_coin.values(), key=lambda x: x["trades"], reverse=True)[:8]

    modes = {"paper": 0, "live": 0}
    for r in sells:
        if r["mode"] in modes:
            modes[r["mode"]] += 1

    wins = sum(1 for r in sells if float(r["pnl_pct"]) > 0)
    losses = len(sells) - wins
    return {
        "equity": equity,
        "daily": daily,
        "by_bot": list(by_bot.values()),
        "by_coin": coins,
        "modes": modes,
        "totals": {
            "trades": len(sells),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(sells) * 100, 1) if sells else None,
            "pnl_pct": round(sum(float(r["pnl_pct"]) for r in sells), 2),
        },
    }


@router.get("/summary")
async def summary():
    rows = db.rows(
        "SELECT bot_id, mode, COUNT(*) AS trades, "
        "SUM(CASE WHEN side='SELL' AND pnl_pct > 0 THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN side='SELL' AND pnl_pct <= 0 THEN 1 ELSE 0 END) AS losses, "
        "AVG(CASE WHEN side='SELL' THEN pnl_pct END) AS avg_pnl "
        "FROM trades GROUP BY bot_id, mode"
    )
    total = db.row(
        "SELECT COUNT(*) AS trades, "
        "SUM(CASE WHEN side='SELL' AND pnl_pct > 0 THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN side='SELL' AND pnl_pct <= 0 THEN 1 ELSE 0 END) AS losses "
        "FROM trades"
    )
    return {"by_bot": rows, "total": total}


@router.get("/events")
async def events(bot_id: Optional[str] = None, level: Optional[str] = None, limit: int = 200):
    sql = "SELECT * FROM events WHERE 1=1"
    params = []
    if bot_id:
        sql += " AND bot_id=?"
        params.append(bot_id)
    if level:
        sql += " AND level=?"
        params.append(level)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return db.rows(sql, params)


@router.get("/signals")
async def signals(bot_id: Optional[str] = None, decision: Optional[str] = None, limit: int = 200):
    sql = "SELECT * FROM signal_events WHERE 1=1"
    params = []
    if bot_id:
        sql += " AND bot_id=?"
        params.append(bot_id)
    if decision:
        sql += " AND decision=?"
        params.append(decision.upper())
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return db.rows(sql, params)


@router.get("/export.csv")
async def export_csv(bot_id: Optional[str] = None):
    sql = "SELECT * FROM trades"
    params = []
    if bot_id:
        sql += " WHERE bot_id=?"
        params.append(bot_id)
    sql += " ORDER BY created_at DESC"
    items = db.rows(sql, params)
    buffer = io.StringIO()
    if items:
        writer = csv.DictWriter(buffer, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )
