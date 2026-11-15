from __future__ import annotations

import csv
import io
from typing import Optional

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
