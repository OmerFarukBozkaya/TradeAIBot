"""Dashboard kümülatif K/Z: para bazlı, komisyon dahil ve işaret tutarlı.

Eski hata: kümülatif seri her işlemin ``pnl_pct`` değerini bileşik çarpıyordu.
Bu yüzden küçük pozisyondaki büyük yüzdelik zarar, büyük pozisyondaki küçük
yüzdelik kârı bastırabiliyor ve toplam K/Z pozitifken grafik negatife
düşebiliyordu. Aşağıdaki senaryo bu durumu birebir kurar.
"""

from __future__ import annotations

import asyncio

import pytest

from app import db
from app.api import trades as trades_api


def _trade(bot_id, side, qty, price, fee, when, coin="BTCUSDT", mode="paper"):
    db.execute(
        "INSERT INTO trades(bot_id,run_id,coin,side,quantity,price,fee,order_id,"
        "client_order_id,mode,reason,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (bot_id, 1, coin, side, qty, price, fee, None, None, mode, "sinyal", None, when),
    )


def _seed_bot(bot_id="bot_stats"):
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "İstatistik", "trade", "paper", "1h", "{}", "stopped", 1,
         "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    return bot_id


def _seed_mixed_trades(bot_id):
    """-10% küçük pozisyon + +10% büyük pozisyon → net para +90 USDT.

    Yüzdeliklerin bileşik çarpımı 0.9 × 1.1 = 0.99 yani -%1 verir (hatalı).
    """
    _trade(bot_id, "BUY", 1.0, 100.0, 0.0, "2026-01-01T10:00:00+00:00")
    _trade(bot_id, "SELL", 1.0, 90.0, 0.0, "2026-01-01T11:00:00+00:00")
    _trade(bot_id, "BUY", 100.0, 10.0, 0.0, "2026-01-01T12:00:00+00:00")
    _trade(bot_id, "SELL", 100.0, 11.0, 0.0, "2026-01-01T13:00:00+00:00")


def test_cumulative_pnl_uses_money_not_compounded_percentages():
    bot_id = _seed_bot()
    _seed_mixed_trades(bot_id)

    result = asyncio.run(trades_api.stats(days=30))
    equity = result["equity"]

    assert len(equity) == 2
    # Para bazlı: -10, sonra +90 → kümülatif +90.
    assert equity[0]["value"] == pytest.approx(-10.0)
    assert equity[1]["value"] == pytest.approx(90.0)
    assert equity[-1]["value"] > 0
    # Yüzde, toplam yatırılan maliyete göre ve aynı işarette.
    assert equity[-1]["pct"] > 0

    totals = result["totals"]
    assert totals["trades"] == 2
    assert totals["pnl_money"] == pytest.approx(90.0)
    assert totals["wins"] == 1
    assert totals["losses"] == 1
    assert totals["pnl_pct"] == pytest.approx(90.0 / 1100.0 * 100, abs=1e-3)

    daily = {d["date"]: d for d in result["daily"]}
    assert daily["2026-01-01"]["pnl"] == pytest.approx(90.0)


def test_cumulative_pnl_is_fee_aware_and_matches_bot_total():
    bot_id = _seed_bot("bot_fee")
    _trade(bot_id, "BUY", 2.0, 100.0, 0.2, "2026-01-01T10:00:00+00:00")
    _trade(bot_id, "SELL", 2.0, 108.0, 0.2, "2026-01-01T11:00:00+00:00")

    result = asyncio.run(trades_api.stats(days=30))
    # (2*108 - 0.2) - (2*100 + 0.2) = 15.6
    assert result["equity"][-1]["value"] == pytest.approx(15.6)
    assert result["totals"]["pnl_money"] == pytest.approx(15.6)
    assert result["totals"]["fees"] == pytest.approx(0.4, abs=1e-9)


def test_partial_exits_do_not_multiply_the_same_position():
    bot_id = _seed_bot("bot_partial")
    _trade(bot_id, "BUY", 10.0, 10.0, 0.0, "2026-01-01T10:00:00+00:00")
    # Aynı pozisyon iki parçada satılır; tek tur sayılmalı.
    _trade(bot_id, "SELL", 5.0, 12.0, 0.0, "2026-01-01T11:00:00+00:00")
    _trade(bot_id, "SELL", 5.0, 12.0, 0.0, "2026-01-01T12:00:00+00:00")

    result = asyncio.run(trades_api.stats(days=30))
    assert result["totals"]["trades"] == 2
    assert result["totals"]["pnl_money"] == pytest.approx(20.0)
    assert result["equity"][-1]["value"] == pytest.approx(20.0)
    assert result["equity"][1]["value"] == pytest.approx(20.0)
    assert result["totals"]["wins"] == 2


def test_summary_counts_round_trips_not_raw_sell_rows():
    bot_id = _seed_bot("bot_summary")
    _trade(bot_id, "BUY", 10.0, 10.0, 0.0, "2026-01-01T10:00:00+00:00")
    _trade(bot_id, "SELL", 5.0, 9.0, 0.0, "2026-01-01T11:00:00+00:00")
    _trade(bot_id, "SELL", 5.0, 9.0, 0.0, "2026-01-01T12:00:00+00:00")

    result = asyncio.run(trades_api.summary())
    total = result["total"]
    # İki ham SATIŞ satırı ama iki tur: ikisi de zararlı.
    assert total["trades"] == 2
    assert total["wins"] == 0
    assert total["losses"] == 2
    assert total["pnl_money"] == pytest.approx(-10.0)
    bot_row = next(r for r in result["by_bot"] if r["bot_id"] == bot_id)
    assert bot_row["trades"] == 2
    assert bot_row["pnl_money"] == pytest.approx(-10.0)


def test_orphan_sell_without_buy_uses_recorded_pnl_pct():
    """Alış kaydı olmayan eski satışlar sıfıra düşürülmez; kayıtlı yüzde kullanılır."""
    bot_id = _seed_bot("bot_orphan")
    _trade(bot_id, "SELL", 10.0, 10.0, 0.0, "2026-01-01T10:00:00+00:00")
    # Engine satışta pnl_pct'yi yazmıştı; bu tek doğru bilgidir.
    db.execute(
        "UPDATE trades SET pnl_pct=10.0 WHERE bot_id=? AND side='SELL'", (bot_id,)
    )

    result = asyncio.run(trades_api.stats(days=30))
    assert result["totals"]["trades"] == 1
    assert result["totals"]["estimated_trades"] == 1
    assert result["totals"]["pnl_money"] == pytest.approx(9.0909, abs=1e-3)
    assert result["equity"][-1]["value"] == pytest.approx(9.0909, abs=1e-3)


def test_two_bots_same_coin_lots_are_not_mixed():
    a = _seed_bot("bot_a")
    b = _seed_bot("bot_b")
    _trade(a, "BUY", 1.0, 100.0, 0.0, "2026-01-01T10:00:00+00:00")
    _trade(b, "BUY", 1.0, 100.0, 0.0, "2026-01-01T10:30:00+00:00")
    _trade(a, "SELL", 1.0, 110.0, 0.0, "2026-01-01T11:00:00+00:00")
    _trade(b, "SELL", 1.0, 90.0, 0.0, "2026-01-01T11:30:00+00:00")

    result = asyncio.run(trades_api.stats(days=30))
    assert result["totals"]["trades"] == 2
    assert result["totals"]["pnl_money"] == pytest.approx(0.0)
    by_bot = {row["bot_id"]: row for row in result["by_bot"]}
    assert by_bot[a]["pnl"] == pytest.approx(10.0)
    assert by_bot[b]["pnl"] == pytest.approx(-10.0)
    assert by_bot[a]["trades"] == 1
    assert by_bot[b]["trades"] == 1
