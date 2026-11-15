"""Yıllık kırılım ve CAGR yardımcılarının doğruluğu."""

import datetime as dt

from app.job_runner import _cagr, _yearly_breakdown

MS_YEAR = 365.25 * 24 * 3600 * 1000


def ms(year, month=1, day=1):
    return dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp() * 1000


def test_cagr_doubles_in_one_year():
    assert round(_cagr(100.0, 200.0, 0.0, MS_YEAR), 1) == 100.0


def test_cagr_guards():
    # sıfır süre, sıfır başlangıç ve negatif sonuç -> 0
    assert _cagr(100.0, 200.0, 1000.0, 1000.0) == 0.0
    assert _cagr(0.0, 200.0, 0.0, MS_YEAR) == 0.0
    assert _cagr(100.0, 0.0, 0.0, MS_YEAR) == 0.0


def test_yearly_breakdown_splits_years():
    points = [
        (ms(2020, 1, 1), 100.0, 100.0),
        (ms(2020, 12, 31), 150.0, 120.0),
        (ms(2021, 1, 1), 150.0, 120.0),
        (ms(2021, 12, 31), 300.0, 240.0),
    ]
    rows = _yearly_breakdown(points)
    assert [r["year"] for r in rows] == [2020, 2021]
    assert rows[0]["strategy_pct"] == 50.0
    assert rows[0]["buy_hold_pct"] == 20.0
    assert rows[0]["diff"] == 30.0
    assert rows[1]["strategy_pct"] == 100.0
    assert rows[1]["buy_hold_pct"] == 100.0
    assert rows[1]["diff"] == 0.0


def test_yearly_breakdown_uses_previous_year_close():
    # ikinci yıl, ilk yılın kapanışına göre ölçülür
    points = [
        (ms(2019, 6, 1), 80.0, 80.0),
        (ms(2019, 12, 31), 100.0, 100.0),
        (ms(2020, 6, 1), 120.0, 110.0),
        (ms(2020, 12, 31), 200.0, 150.0),
    ]
    rows = _yearly_breakdown(points)
    assert rows[1]["year"] == 2020
    assert rows[1]["strategy_pct"] == 100.0  # 100 -> 200
    assert rows[1]["buy_hold_pct"] == 50.0  # 100 -> 150
