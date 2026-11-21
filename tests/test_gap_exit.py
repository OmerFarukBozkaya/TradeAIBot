"""Gap (boşluk) durumunda stop çıkış fiyatı."""

from __future__ import annotations

import pytest

from app.job_runner import _risk_exit


def _data(open_, high, low, close):
    return {"open": [open_], "high": [high], "low": [low], "close": [close]}


def _pos():
    return {"entry": 100.0, "atr": 2.0, "highest": 100.0}


def test_stop_fills_at_level_without_gap():
    # stop 96; mum 98'de açıldı, 94'e indi → 96'dan çık
    hit = _risk_exit(_pos(), _data(98, 99, 94, 95), 0, [], {"stop_atr": 2})
    assert hit == (96.0, "stop")


def test_stop_fills_at_open_on_gap_down():
    # stop 96; mum 90'da açıldı (gap) → 90'dan çık (daha kötümser)
    hit = _risk_exit(_pos(), _data(90, 91, 88, 89), 0, [], {"stop_atr": 2})
    assert hit == (90.0, "stop")


def test_no_open_series_uses_stop_level():
    data = {"high": [99], "low": [94], "close": [95]}
    hit = _risk_exit(_pos(), data, 0, [], {"stop_atr": 2})
    assert hit == (96.0, "stop")


def test_take_profit_unaffected_by_gap():
    hit = _risk_exit(_pos(), _data(101, 112, 100, 110), 0, [], {"take_profit_pct": 5})
    assert hit is not None
    assert hit[1] == "take-profit"
    assert hit[0] == pytest.approx(105.0)
