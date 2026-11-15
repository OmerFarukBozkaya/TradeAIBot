"""Grafik işaretleri: numaralandırma ve tablo eşleşmesi."""

from app.job_runner import _trade_markers


def make_trade(no_entry_idx, exit_idx, pnl=5.0, reason="signal"):
    return {
        "entry_time": no_entry_idx * 1000,
        "exit_time": exit_idx * 1000,
        "entry": 100.0,
        "exit": 105.0,
        "qty": 1.0,
        "pnl_pct": pnl,
        "candles": exit_idx - no_entry_idx,
        "reason": reason,
        "entry_idx": no_entry_idx,
        "exit_idx": exit_idx,
    }


def test_markers_are_numbered_from_one():
    trades = [make_trade(10, 20), make_trade(30, 40)]
    mk = _trade_markers(trades)
    assert len(mk) == 4
    assert [m["no"] for m in mk] == [1, 1, 2, 2]
    assert [m["side"] for m in mk] == ["buy", "sell", "buy", "sell"]


def test_markers_keep_idx_and_price():
    trades = [make_trade(10, 20)]
    buy, sell = _trade_markers(trades)
    assert buy["idx"] == 10 and sell["idx"] == 20
    assert buy["price"] == 100.0 and sell["price"] == 105.0
    assert buy["candles"] == 10
    assert buy["reason"] == "signal"


def test_markers_limit_keeps_global_numbering():
    # 250 işlem varsa son 200 gösterilir; numaralar 51'den başlar.
    trades = [make_trade(i, i + 5) for i in range(250)]
    mk = _trade_markers(trades, limit=200)
    assert len(mk) == 400
    assert mk[0]["no"] == 51
    assert mk[-1]["no"] == 250
    assert mk[0]["idx"] == 50  # 51. işlem (0-tabanlı 50)
