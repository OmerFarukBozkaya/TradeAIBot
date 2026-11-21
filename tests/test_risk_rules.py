"""Ortak risk kuralları (canlı motor + backtest aynı fonksiyonları kullanır)."""

from __future__ import annotations

import pytest

from app import risk as risk_rules
from app.job_runner import _legacy_stop_exit, _risk_exit


# ----------------------------------------------------------------------
# Seviyeler
# ----------------------------------------------------------------------
def test_stop_atr_and_cap():
    stop, kind = risk_rules.effective_stop(100, 2, 100, {"stop_atr": 5})
    assert stop == 90 and kind == "stop"
    capped, _ = risk_rules.effective_stop(100, 50, 100, {"stop_atr": 5, "max_stop_pct": 10})
    assert capped == 90


def test_trailing_requires_threshold_and_moves_up():
    stop, kind = risk_rules.effective_stop(
        100, 2, 110, {"stop_atr": 2, "trail_atr": 3, "trail_after_pct": 20}
    )
    assert stop == 96 and kind == "stop"  # eşik aşılmadı, yalnızca ATR stop
    stop, kind = risk_rules.effective_stop(
        100, 2, 130, {"stop_atr": 2, "trail_atr": 3, "trail_after_pct": 20}
    )
    assert stop == 124 and kind == "takipli-stop"


def test_breakeven_moves_stop_to_entry():
    stop, kind = risk_rules.effective_stop(
        100, 2, 105, {"stop_atr": 5, "breakeven_pct": 3}
    )
    assert stop == 100 and kind == "breakeven"
    # eşik aşılmadıysa stop yerinde kalır
    stop, kind = risk_rules.effective_stop(
        100, 2, 101, {"stop_atr": 5, "breakeven_pct": 5}
    )
    assert stop == 90 and kind == "stop"


def test_floor_wins_after_partial():
    stop, kind = risk_rules.effective_stop(
        100, 2, 103, {"stop_atr": 5}, floor=100
    )
    assert stop == 100 and kind == "breakeven"


def test_target_uses_nearest_of_atr_and_pct():
    assert risk_rules.target_price(100, 2, {"take_profit_pct": 10}) == pytest.approx(110)
    assert risk_rules.target_price(100, 2, {"take_profit_atr": 3}) == 106
    assert risk_rules.target_price(100, 2, {"take_profit_atr": 5, "take_profit_pct": 3}) == pytest.approx(103)
    assert risk_rules.target_price(100, 2, {}) is None


def test_partial_target_and_fraction():
    assert risk_rules.partial_target_price(100, 2, {"partial_tp_pct": 4}) == 104
    assert risk_rules.partial_target_price(100, 2, {}) is None
    assert risk_rules.partial_fraction({"partial_tp_fraction": 3}) == 1.0
    assert risk_rules.partial_fraction({"partial_tp_fraction": 0.25}) == 0.25
    assert risk_rules.partial_fraction({}) == 0.5


def test_static_and_dynamic_stops():
    assert risk_rules.static_stop_price(100, {}) == 97.5
    assert risk_rules.static_stop_price(100, {"static_stop_pct": 5}) == 95.0
    # ADX < 20: dinamik stop kapalı
    assert risk_rules.dynamic_stop_level(110, 2, 15, {}) is None
    # zayıf trend 1,2×ATR, güçlü trend 2×ATR
    assert risk_rules.dynamic_stop_level(110, 2, 25, {}) == 107.6
    assert risk_rules.dynamic_stop_level(110, 2, 35, {}) == 106.0
    assert risk_rules.dynamic_stop_hit(106.5, 107.6, {"dynamic_stop_tolerance_pct": 1})
    assert not risk_rules.dynamic_stop_hit(107.0, 107.6, {"dynamic_stop_tolerance_pct": 1})


def test_position_budget_risk_based():
    # %1 risk, %10 stop mesafesi → 1000 nakitin %10'u (100 USDT) riske edilir.
    budget = risk_rules.position_budget(1000, 100, 90, {"risk_per_trade_pct": 1}, 1.0)
    assert budget == pytest.approx(100.0)
    # risk ayarı yoksa eski davranış
    assert risk_rules.position_budget(1000, 100, 90, {}, 0.5) == 500
    # stop yoksa risk hesabı yapılamaz
    assert risk_rules.position_budget(1000, 100, None, {"risk_per_trade_pct": 1}, 0.5) == 500
    # pozisyon yüzdesi tavanı korunur
    assert risk_rules.position_budget(1000, 100, 99, {"risk_per_trade_pct": 5}, 0.2) == 200


# ----------------------------------------------------------------------
# Backtest entegrasyonu
# ----------------------------------------------------------------------
def _data(rows):
    return {
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "opendate": [i * 3600000 for i in range(len(rows))],
    }


def _pos(**kwargs):
    base = {"entry": 100.0, "index": 0, "highest": 100.0, "atr": 2.0}
    base.update(kwargs)
    return base


def test_risk_exit_take_profit_live_and_backtest_agree():
    data = _data([(100, 110, 100, 108)])
    # aynı ayar canlı motorun kullandığı fonksiyonla aynı seviyeyi üretir
    live_target = risk_rules.target_price(100, 2, {"take_profit_pct": 5})
    hit = _risk_exit(_pos(), data, 0, [2.0], {"take_profit_pct": 5})
    assert hit == (live_target, "take-profit")


def test_risk_exit_breakeven_stop():
    data = _data([(100, 104, 99, 103)])
    assert _risk_exit(_pos(highest=104), data, 0, [2.0],
                      {"stop_atr": 5, "breakeven_pct": 3}) == (100.0, "breakeven")


def test_legacy_static_stop_in_backtest():
    data = _data([(100, 100, 96, 97)])
    hit = _legacy_stop_exit(_pos(), data, 0, [2.0], [], {"static_stop": True})
    # stop %2,5 → 97,5; çıkış mumun dibi ile stop arasında (min) gerçekleşir
    assert hit == (97.5, "statik-stop")


def test_legacy_dynamic_stop_in_backtest():
    data = _data([(110, 110, 103, 104)])
    # ADX 35 → 110 - 2×2 = 106; kapanış 104 < 106×0,99
    hit = _legacy_stop_exit(
        _pos(highest=110), data, 0, [2.0], [35.0], {"dynamic_stop": True}
    )
    assert hit and hit[1] == "dinamik-stop"


def test_legacy_stops_off_by_default():
    data = _data([(100, 100, 80, 81)])
    assert _legacy_stop_exit(_pos(), data, 0, [2.0], [], {}) is None
