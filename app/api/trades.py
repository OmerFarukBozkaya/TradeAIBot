from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
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
    # Bot adı da döner: panelde kimlik yerine okunur ad gösterilir.
    sql = (
        "SELECT trades.*, COALESCE(bots.name, trades.bot_id) AS bot_name "
        "FROM trades LEFT JOIN bots ON bots.id=trades.bot_id WHERE 1=1"
    )
    params: List[Any] = []
    if bot_id:
        sql += " AND trades.bot_id=?"
        params.append(bot_id)
    if coin:
        sql += " AND trades.coin=?"
        params.append(coin)
    if side:
        sql += " AND trades.side=?"
        params.append(side.upper())
    if mode:
        sql += " AND trades.mode=?"
        params.append(mode)
    sql += " ORDER BY trades.created_at DESC, trades.id DESC LIMIT ? OFFSET ?"
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
                    "pnl_pct": row.get("pnl_pct"),
                    "fee": fee,
                    "mode": row.get("mode"),
                    "id": row.get("id"),
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


def closed_round_trips(rows: List[dict]) -> List[Dict[str, Any]]:
    """Tüm botların kapanmış turlarını **komisyon dahil para K/Z'si** ile toplar.

    FIFO eşleştirmesi bot bazında yapılır: iki bot aynı coini alıp sattığında
    lotlar birbirine karışmaz. Dönen liste çıkış zamanına göre artan sıradadır
    ve her turda ``pnl_money`` (net para), ``invested`` (maliyet) ve
    ``bot_id`` bulunur. Kümülatif K/Z bu seriden hesaplanır; işlem başına
    yüzdeliklerin bileşik çarpımı yanlış sonuç verir (pozisyon büyüklüğü
    portföyün tamamı değildir, kısmi satışlar çok kez sayılır).

    Alış kaydı bulunmayan satışlar (eski sürümden kalan veriler) satırdaki
    ``pnl_pct`` değerinden türetilir ve ``estimated=True`` ile işaretlenir.
    """
    groups: Dict[str, List[dict]] = {}
    for row in rows:
        key = str(row.get("bot_id") or "-")
        groups.setdefault(key, []).append(row)

    closed: List[Dict[str, Any]] = []
    for key, group in groups.items():
        bot_id = None if key == "-" else key
        result = pair_round_trips(group)
        for item in result["trades"]:
            entry = dict(item)
            entry["bot_id"] = bot_id
            entry["estimated"] = False
            closed.append(entry)
        # Alış kaydı olmayan (eski sürüm/elle eklenmiş) satışlar: satırda
        # kayıtlı ``pnl_pct`` tek doğru bilgidir. Satış gelirinden maliyeti
        # türetip para K/Z'sine çevir; böylece geçmiş boş kalıp grafik sıfıra
        # düşmez.
        for sell in result["unmatched_sells"]:
            raw_pct = sell.get("pnl_pct")
            if raw_pct is None:
                continue
            try:
                pct = float(raw_pct)
                qty = float(sell.get("quantity") or 0.0)
                price = float(sell.get("price") or 0.0)
                fee = float(sell.get("fee") or 0.0)
            except (TypeError, ValueError):
                continue
            if qty <= 0 or price <= 0 or pct <= -100:
                continue
            proceeds = qty * price - fee
            if proceeds <= 0:
                continue
            cost = proceeds / (1.0 + pct / 100.0)
            closed.append(
                {
                    "coin": sell.get("coin"),
                    "quantity": round(qty, 10),
                    "entry_price": None,
                    "exit_price": round(price, 10),
                    "entry_time": None,
                    "exit_time": sell.get("time"),
                    "hold_seconds": None,
                    "invested": round(cost, 6),
                    "proceeds": round(proceeds, 6),
                    "pnl_money": round(proceeds - cost, 6),
                    "pnl_pct": round(pct, 3),
                    "fee": round(fee, 6),
                    "exit_reason": sell.get("reason"),
                    "entry_reason": None,
                    "mode": sell.get("mode"),
                    "partial": False,
                    "estimated": True,
                    "bot_id": bot_id,
                }
            )
    closed.sort(
        key=lambda t: (
            str(t.get("exit_time") or ""),
            str(t.get("bot_id") or ""),
            str(t.get("coin") or ""),
        )
    )
    return closed


def pair_history(rows: List[dict]) -> Dict[str, Any]:
    """İşlem geçmişi için alım/satım turlarını eşleştirir.

    Eşleştirme **(bot, coin)** bazında FIFO yapılır: aynı hesapta çalışan iki
    bot aynı coini alıp sattığında işlemler birbirine karışmaz. Dönen her tur
    giriş ve çıkış fiyatını ayrı ayrı taşır; panelde ikisi de gösterilir.
    """
    groups: Dict[tuple, List[dict]] = {}
    for row in rows:
        key = (str(row.get("bot_id") or ""), str(row.get("coin") or "").upper())
        groups.setdefault(key, []).append(row)

    closed: List[Dict[str, Any]] = []
    open_legs: List[Dict[str, Any]] = []
    for (bot_id, coin), items in groups.items():
        items.sort(key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))
        lots: List[Dict[str, Any]] = []
        for row in items:
            side = str(row.get("side") or "").upper()
            qty = float(row.get("quantity") or 0.0)
            price = float(row.get("price") or 0.0)
            if qty <= 0 or price <= 0:
                continue
            fee = float(row.get("fee") or 0.0)
            unit_fee = fee / qty
            if side == "BUY":
                lots.append(
                    {
                        "quantity": qty,
                        "price": price,
                        "unit_fee": unit_fee,
                        "time": row.get("created_at"),
                        "id": row.get("id"),
                        "reason": row.get("reason"),
                        "bot_name": row.get("bot_name") or bot_id,
                    }
                )
                continue
            if side != "SELL":
                continue

            remaining = qty
            consumed: List[Dict[str, Any]] = []
            while remaining > 1e-12 and lots:
                lot = lots[0]
                take = min(remaining, float(lot["quantity"]))
                consumed.append(
                    {
                        "quantity": take,
                        "price": float(lot["price"]),
                        "unit_fee": float(lot["unit_fee"]),
                        "time": lot["time"],
                        "id": lot.get("id"),
                    }
                )
                lot["quantity"] = float(lot["quantity"]) - take
                remaining -= take
                if lot["quantity"] <= 1e-12:
                    lots.pop(0)
            if not consumed:
                # Alış bu pencerede yok (çok eski) veya harici satış: satır
                # yine görünsün, yalnızca K/Z hesaplanmaz.
                closed.append(
                    {
                        "bot_id": bot_id,
                        "bot_name": row.get("bot_name") or bot_id,
                        "coin": coin,
                        "quantity": round(qty, 10),
                        "entry_price": None,
                        "exit_price": round(price, 10),
                        "entry_time": None,
                        "exit_time": row.get("created_at"),
                        "hold_seconds": None,
                        "invested": None,
                        "pnl_money": None,
                        "pnl_pct": None,
                        "fee": round(fee, 6),
                        "exit_reason": row.get("reason"),
                        "entry_reason": None,
                        "mode": row.get("mode"),
                        "partial": False,
                        "unmatched": True,
                        "exit_id": row.get("id"),
                        "entry_ids": [],
                    }
                )
                continue

            matched = sum(c["quantity"] for c in consumed)
            if matched <= 0:
                continue
            cost = sum(c["quantity"] * (c["price"] + c["unit_fee"]) for c in consumed)
            proceeds = matched * (price - unit_fee)
            pnl_money = proceeds - cost
            closed.append(
                {
                    "bot_id": bot_id,
                    "bot_name": row.get("bot_name") or bot_id,
                    "coin": coin,
                    "quantity": round(matched, 10),
                    "entry_price": round(
                        sum(c["quantity"] * c["price"] for c in consumed) / matched, 10
                    ),
                    "exit_price": round(price, 10),
                    "entry_time": consumed[0]["time"],
                    "exit_time": row.get("created_at"),
                    "hold_seconds": _seconds_between(consumed[0]["time"], row.get("created_at")),
                    "invested": round(cost, 6),
                    "pnl_money": round(pnl_money, 6),
                    "pnl_pct": round(pnl_money / cost * 100, 3) if cost > 0 else 0.0,
                    "fee": round(sum(c["quantity"] * c["unit_fee"] for c in consumed)
                                 + matched * unit_fee, 6),
                    "exit_reason": row.get("reason"),
                    "entry_reason": consumed[0].get("reason"),
                    "mode": row.get("mode"),
                    "partial": bool(remaining > 1e-12),
                    "exit_id": row.get("id"),
                    "entry_ids": [c.get("id") for c in consumed],
                }
            )

        for lot in lots:
            if float(lot["quantity"]) <= 1e-12:
                continue
            open_legs.append(
                {
                    "bot_id": bot_id,
                    "bot_name": lot.get("bot_name") or bot_id,
                    "coin": coin,
                    "quantity": round(float(lot["quantity"]), 10),
                    "entry_price": round(float(lot["price"]), 10),
                    "entry_time": lot["time"],
                    "invested": round(float(lot["quantity"]) * float(lot["price"]), 6),
                }
            )

    closed.sort(
        key=lambda t: (str(t.get("exit_time") or ""), int(t.get("exit_id") or 0)),
        reverse=True,
    )
    open_legs.sort(key=lambda t: str(t.get("entry_time") or ""), reverse=True)

    return {"trades": closed, "open": open_legs}


@router.get("/trades/history")
def trade_history(
    bot_id: Optional[str] = None,
    coin: Optional[str] = None,
    limit: int = Query(default=2000, le=10000),
):
    """İşlem geçmişi: her tur için alış ve satış fiyatı ayrı ayrı."""
    sql = (
        "SELECT trades.*, COALESCE(bots.name, trades.bot_id) AS bot_name "
        "FROM trades LEFT JOIN bots ON bots.id=trades.bot_id WHERE 1=1"
    )
    params: List[Any] = []
    if bot_id:
        sql += " AND trades.bot_id=?"
        params.append(bot_id)
    if coin:
        sql += " AND trades.coin=?"
        params.append(coin.upper())
    sql += " ORDER BY trades.created_at DESC, trades.id DESC LIMIT ?"
    params.append(int(limit))
    rows = db.rows(sql, params)
    result = pair_history(rows)
    result["orders"] = len(rows)
    result["limited"] = len(rows) >= int(limit)
    return result


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


@router.get("/trades/{trade_id}/chart")
def trade_chart(trade_id: int):
    """Bir işlemin grafiği: alış/satış noktaları ve aradaki mumlar.

    İşlem geçmişinde satıra tıklandığında botun nereden alıp nereden sattığını
    ve kararın sonucunu göstermek için kullanılır.
    """
    row = db.row("SELECT * FROM trades WHERE id=?", (trade_id,))
    if not row:
        raise HTTPException(404, "İşlem bulunamadı")
    coin = str(row.get("coin") or "").upper()
    side = str(row.get("side") or "").upper()
    bot_id = row.get("bot_id")
    if bot_id:
        rows = db.rows(
            "SELECT * FROM trades WHERE bot_id=? AND coin=? ORDER BY created_at, id",
            (bot_id, coin),
        )
        if not rows:
            rows = db.rows(
                "SELECT * FROM trades WHERE coin=? ORDER BY created_at, id", (coin,)
            )
    else:
        rows = db.rows("SELECT * FROM trades WHERE coin=? ORDER BY created_at, id", (coin,))

    entry = None
    exit_leg = None
    if side == "SELL":
        entry = _fifo_entry(rows, row)
        exit_leg = {
            "id": row.get("id"),
            "price": float(row.get("price") or 0.0),
            "time": row.get("created_at"),
            "reason": row.get("reason"),
        }
    else:
        entry = {
            "id": row.get("id"),
            "price": float(row.get("price") or 0.0),
            "time": row.get("created_at"),
            "reason": row.get("reason"),
        }
        exit_leg = _next_sell(rows, row)

    period = _bot_period(bot_id)
    entry_ms = _time_ms(entry.get("time") if entry else row.get("created_at"))
    exit_ms = _time_ms(exit_leg.get("time") if exit_leg else None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if exit_ms is None:
        exit_ms = now_ms
    if entry_ms is None:
        entry_ms = exit_ms
    if exit_ms < entry_ms:
        entry_ms, exit_ms = exit_ms, entry_ms

    base_ms = _period_ms(period) or 3_600_000.0
    span = max(1, exit_ms - entry_ms)
    chart_period = _chart_period(span)
    bar_ms = _period_ms(chart_period) or base_ms
    padding = max(1, int(round(20 * bar_ms)))
    start_ms = entry_ms - padding
    end_ms = exit_ms + padding
    limit = max(20, min(1000, int((end_ms - start_ms) / bar_ms) + 2))

    candles: List[Dict[str, Any]] = []
    error: Optional[str] = None
    try:
        from app.market_data import load_history

        data, _meta = load_history(
            coin, chart_period, limit, start=start_ms, end=end_ms
        )
        opens = data.get("opendate") or []
        closes = data.get("close") or []
        for i in range(len(opens)):
            candles.append(
                {
                    "time": opens[i],
                    "open": data["open"][i],
                    "high": data["high"][i],
                    "low": data["low"][i],
                    "close": closes[i],
                    "volume": (data.get("volume_usdt") or data.get("volume_coin") or [0] * len(opens))[i],
                }
            )
    except Exception as exc:  # noqa: BLE001 - grafik yoksa işlem bilgisi yine dönsün
        error = str(exc)

    entry_price = float(entry.get("price") or 0.0) if entry else 0.0
    exit_price = float(exit_leg.get("price") or 0.0) if exit_leg else 0.0
    pnl_pct = (
        (exit_price / entry_price - 1) * 100 if entry_price > 0 and exit_price > 0 else None
    )
    # Satıştan sonraki mumlar: "erken mi sattım?" sorusunu cevaplar.
    # Fiyat mum verisiyle uyuşmuyorsa (yanlış sembol/eski kayıt) yüzde
    # anlamsız olur; bu durumda hiç hesaplanmaz.
    after_high = None
    after_low = None
    after_bars = 0
    price_consistent = True
    if candles:
        lows = [float(c.get("low") or 0) for c in candles if float(c.get("low") or 0) > 0]
        highs = [float(c.get("high") or 0) for c in candles if float(c.get("high") or 0) > 0]
        if lows and highs:
            low_edge, high_edge = min(lows) * 0.8, max(highs) * 1.2
            checks = [p for p in (entry_price, exit_price) if p > 0]
            if checks:
                price_consistent = all(low_edge <= p <= high_edge for p in checks)
        if price_consistent and exit_leg and exit_price > 0:
            after = [c for c in candles if int(c.get("time") or 0) > exit_ms]
            after_bars = len(after)
            if after:
                after_high = max(float(c.get("high") or 0) for c in after)
                after_low = min(float(c.get("low") or 0) for c in after)
    return {
        "trade": row,
        "coin": coin,
        "side": side,
        "period": chart_period,
        "entry": entry,
        "exit": exit_leg,
        "pnl_pct": round(pnl_pct, 3) if pnl_pct is not None else None,
        "candles": candles,
        # Mum fiyatları işlem fiyatıyla uyuşmuyorsa (eski kayıt/farklı sembol)
        # grafik yanıltıcı olur; panel bu durumda mumları çizmez.
        "price_consistent": price_consistent,
        "after_exit": {
            "bars": after_bars,
            "high": after_high,
            "low": after_low,
            "high_pct": round((after_high / exit_price - 1) * 100, 3)
            if after_high and exit_price > 0 else None,
            "low_pct": round((after_low / exit_price - 1) * 100, 3)
            if after_low and exit_price > 0 else None,
        },
        "error": error,
    }


def _fifo_entry(rows: List[dict], sell_row: dict) -> Optional[Dict[str, Any]]:
    """Satışın FIFO ile eşleştiği alım lotlarının ağırlıklı girişini bulur."""
    target_id = sell_row.get("id")
    coin = str(sell_row.get("coin") or "").upper()
    lots: List[Dict[str, Any]] = []
    ordered = sorted(
        rows, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0))
    )
    for item in ordered:
        if str(item.get("coin") or "").upper() != coin:
            continue
        item_side = str(item.get("side") or "").upper()
        qty = float(item.get("quantity") or 0.0)
        price = float(item.get("price") or 0.0)
        if qty <= 0:
            continue
        if item_side == "BUY":
            lots.append(
                {
                    "quantity": qty,
                    "price": price,
                    "time": item.get("created_at"),
                    "id": item.get("id"),
                }
            )
            continue
        if item_side != "SELL":
            continue
        remaining = qty
        consumed: List[Dict[str, Any]] = []
        while remaining > 1e-12 and lots:
            lot = lots[0]
            take = min(remaining, float(lot["quantity"]))
            consumed.append(
                {
                    "quantity": take,
                    "price": float(lot["price"]),
                    "time": lot.get("time"),
                    "id": lot.get("id"),
                }
            )
            lot["quantity"] = float(lot["quantity"]) - take
            remaining -= take
            if lot["quantity"] <= 1e-12:
                lots.pop(0)
        if item.get("id") == target_id:
            if not consumed:
                return None
            total = sum(c["quantity"] for c in consumed)
            if total <= 0:
                return None
            return {
                "id": consumed[0].get("id"),
                "ids": [c.get("id") for c in consumed],
                "price": sum(c["quantity"] * c["price"] for c in consumed) / total,
                "time": consumed[0].get("time"),
                "quantity": total,
            }
    return None


def _next_sell(rows: List[dict], buy_row: dict) -> Optional[Dict[str, Any]]:
    """Bir alıştan sonra gelen ilk satışı (varsa) döndürür."""
    buy_key = (str(buy_row.get("created_at") or ""), int(buy_row.get("id") or 0))
    coin = str(buy_row.get("coin") or "").upper()
    candidates = [
        item
        for item in rows
        if str(item.get("side") or "").upper() == "SELL"
        and str(item.get("coin") or "").upper() == coin
        and (str(item.get("created_at") or ""), int(item.get("id") or 0)) > buy_key
    ]
    if not candidates:
        return None
    item = min(candidates, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))
    return {
        "id": item.get("id"),
        "price": float(item.get("price") or 0.0),
        "time": item.get("created_at"),
        "reason": item.get("reason"),
    }


def _bot_period(bot_id: Optional[str]) -> str:
    if not bot_id:
        return "1h"
    try:
        bot = db.row("SELECT config_json FROM bots WHERE id=?", (bot_id,))
        if bot:
            import json

            config = json.loads(bot.get("config_json") or "{}")
            period = str(config.get("period") or "").strip()
            if period:
                return period
    except (TypeError, ValueError):
        pass
    return "1h"


def _period_ms(period: str) -> Optional[float]:
    try:
        from app.market_data import parse_period

        return parse_period(period).ms
    except Exception:  # noqa: BLE001 - bilinmeyen periyot: varsayılana düş
        return None


def _time_ms(value: Any) -> Optional[int]:
    stamp = _parse_ts(value) if not isinstance(value, (int, float)) else None
    if isinstance(value, (int, float)):
        number = float(value)
        return int(number if number > 1e11 else number * 1000)
    if stamp is None:
        return None
    return int(stamp.timestamp() * 1000)


_CHART_PERIODS = [
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
]


def _chart_period(span_ms: int) -> str:
    """İşlem süresine göre grafik periyodu seçer (yaklaşık 120 mum hedefi).

    Kısa işlemlerde botun periyodu yerine daha ince bir periyot kullanılır ki
    giriş ve çıkış aynı mumda kaybolmasın; uzun işlemlerde ise grafik
    okunabilir kalsın diye periyot büyütülür.
    """
    ideal = max(1.0, span_ms / 120.0)
    for text in _CHART_PERIODS:
        if (_period_ms(text) or 0) >= ideal:
            return text
    return "1w"


@router.get("/positions")
async def positions(status: str = "open"):
    return db.rows(
        "SELECT * FROM positions WHERE status=? ORDER BY opened_at DESC LIMIT 500", (status,)
    )


@router.get("/stats")
async def stats(days: int = Query(default=30, ge=1, le=365)):
    """Dashboard grafikleri için özet seriler.

    Tüm değerler **kapanmış turların net (komisyon dahil) para K/Z'si**
    üzerinden hesaplanır. Kümülatif seri, işlem başına yüzdeliklerin bileşik
    çarpımı değil, gerçekleşen K/Z'nin toplamıdır; böylece "Toplam K/Z" ile
    aynı işareti ve büyüklüğü gösterir.
    """
    rows = db.rows(
        "SELECT id, created_at, pnl_pct, mode, bot_id, coin, side, quantity, price, fee, reason "
        "FROM trades ORDER BY created_at, id"
    )
    closed = closed_round_trips(rows)

    equity: List[Dict[str, Any]] = []
    cumulative = 0.0
    invested_cum = 0.0
    for t in closed:
        cumulative += float(t["pnl_money"])
        invested_cum += float(t["invested"])
        equity.append(
            {
                "t": t["exit_time"],
                "value": round(cumulative, 4),
                "pnl": round(float(t["pnl_money"]), 4),
                "pct": round(cumulative / invested_cum * 100, 3) if invested_cum else 0.0,
            }
        )

    daily_map: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        day = str(t.get("exit_time") or "")[:10]
        if not day:
            continue
        bucket = daily_map.setdefault(
            day, {"date": day, "pnl": 0.0, "trades": 0, "invested": 0.0}
        )
        bucket["pnl"] += float(t["pnl_money"])
        bucket["invested"] += float(t["invested"])
        bucket["trades"] += 1
    daily = []
    for key in sorted(daily_map):
        bucket = daily_map[key]
        invested = bucket.pop("invested")
        bucket["pnl"] = round(bucket["pnl"], 4)
        bucket["pnl_pct"] = round(bucket["pnl"] / invested * 100, 3) if invested else None
        daily.append(bucket)
    daily = daily[-days:]

    names = {
        str(row["id"]): row.get("name")
        for row in db.rows("SELECT id, name FROM bots")
    }
    by_bot: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        key = str(t.get("bot_id") or "-")
        item = by_bot.setdefault(
            key,
            {
                "bot_id": t.get("bot_id"),
                "name": names.get(key),
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0,
                "invested": 0.0,
                "series": [],
            },
        )
        pnl = float(t["pnl_money"])
        item["trades"] += 1
        item["wins" if pnl > 0 else "losses"] += 1
        item["pnl"] += pnl
        item["invested"] += float(t["invested"])
        item["series"].append(round(item["pnl"], 4))
    bot_rows = []
    for item in by_bot.values():
        invested = item.pop("invested")
        item["pnl"] = round(item["pnl"], 4)
        item["pnl_pct"] = round(item["pnl"] / invested * 100, 3) if invested else None
        item["series"] = item["series"][-40:]
        bot_rows.append(item)
    bot_rows.sort(key=lambda x: x["pnl"], reverse=True)

    by_coin: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        key = str(t.get("coin") or "-")
        item = by_coin.setdefault(
            key, {"coin": key, "trades": 0, "pnl": 0.0, "invested": 0.0}
        )
        item["trades"] += 1
        item["pnl"] += float(t["pnl_money"])
        item["invested"] += float(t["invested"])
    coins = []
    for item in by_coin.values():
        invested = item.pop("invested")
        item["pnl"] = round(item["pnl"], 4)
        item["pnl_pct"] = round(item["pnl"] / invested * 100, 3) if invested else None
        coins.append(item)
    coins.sort(key=lambda x: x["trades"], reverse=True)
    coins = coins[:8]

    modes = {"paper": 0, "live": 0}
    for t in closed:
        mode = t.get("mode")
        if mode in modes:
            modes[mode] += 1

    wins = sum(1 for t in closed if float(t["pnl_money"]) > 0)
    losses = sum(1 for t in closed if float(t["pnl_money"]) <= 0)
    invested_total = sum(float(t["invested"]) for t in closed)
    pnl_total = sum(float(t["pnl_money"]) for t in closed)
    fees_total = sum(float(t.get("fee") or 0.0) for t in closed)
    estimated_total = sum(1 for t in closed if t.get("estimated"))
    return {
        "equity": equity,
        "daily": daily,
        "by_bot": bot_rows,
        "by_coin": coins,
        "modes": modes,
        "totals": {
            "trades": len(closed),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(closed) * 100, 1) if closed else None,
            "pnl_money": round(pnl_total, 4),
            "pnl_pct": round(pnl_total / invested_total * 100, 3) if invested_total else None,
            "invested": round(invested_total, 4),
            "fees": round(fees_total, 4),
            "estimated_trades": estimated_total,
        },
    }


@router.get("/summary")
async def summary():
    """Üst çubuk ve paneller için tur bazlı kazanma/kaybetme özeti.

    ``wins``/``losses`` kapanmış **turlar** üzerinden sayılır; ham SATIŞ
    satırları kısmi çıkışlarda aynı pozisyonu birden çok kez sayardı.
    """
    rows = db.rows(
        "SELECT id, created_at, pnl_pct, mode, bot_id, coin, side, quantity, price, fee, reason "
        "FROM trades ORDER BY created_at, id"
    )
    closed = closed_round_trips(rows)

    by_bot_map: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        key = str(t.get("bot_id") or "-")
        item = by_bot_map.setdefault(
            key,
            {
                "bot_id": t.get("bot_id"),
                "mode": t.get("mode"),
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_money": 0.0,
                "pnl_pct_sum": 0.0,
            },
        )
        pnl = float(t["pnl_money"])
        item["trades"] += 1
        item["wins" if pnl > 0 else "losses"] += 1
        item["pnl_money"] += pnl
        item["pnl_pct_sum"] += float(t.get("pnl_pct") or 0.0)

    by_bot = []
    for item in by_bot_map.values():
        count = item.pop("trades")
        pct_sum = item.pop("pnl_pct_sum")
        item.update(
            {
                "trades": count,
                "pnl_money": round(item["pnl_money"], 4),
                "avg_pnl": round(pct_sum / count, 3) if count else None,
            }
        )
        by_bot.append(item)

    wins = sum(1 for t in closed if float(t["pnl_money"]) > 0)
    losses = len(closed) - wins
    pnl_total = sum(float(t["pnl_money"]) for t in closed)
    return {
        "by_bot": by_bot,
        "total": {
            "trades": len(closed),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(closed) * 100, 1) if closed else None,
            "pnl_money": round(pnl_total, 4),
        },
    }


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
    sql = (
        "SELECT trades.*, COALESCE(bots.name, '') AS bot_name "
        "FROM trades LEFT JOIN bots ON bots.id=trades.bot_id"
    )
    params = []
    if bot_id:
        sql += " WHERE trades.bot_id=?"
        params.append(bot_id)
    sql += " ORDER BY trades.created_at DESC"
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
