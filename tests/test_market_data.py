"""Çoklu piyasa verisi katmanı: periyot, yeniden örnekleme ve sembol testleri."""

from __future__ import annotations

import datetime as dt

import pytest

from app.market_data.catalog import is_live_symbol, resolve_symbol
from app.market_data.periods import choose_base_period, parse_period
from app.market_data.providers.tefas import parse_rows as parse_tefas_rows
from app.market_data.providers.yahoo import parse_chart
from app.market_data.resample import resample_data


def make_data(step_ms=3_600_000, n=6):
    start = 1_699_992_000_000  # saat başına hizalı
    return {
        "opendate": [start + i * step_ms for i in range(n)],
        "open": [100.0 + i for i in range(n)],
        "high": [105.0 + i for i in range(n)],
        "low": [95.0 + i for i in range(n)],
        "close": [101.0 + i for i in range(n)],
        "volume_coin": [2.0] * n,
        "volume_usdt": [200.0] * n,
        "trade_number": [10.0] * n,
        "buy_coin_volume": [1.0] * n,
        "buy_usdt_volume": [100.0] * n,
        "closedate": [start + i * step_ms + step_ms - 1 for i in range(n)],
    }


def test_parse_period_units():
    assert parse_period("45m").text == "45m"
    assert parse_period("2h").text == "2h"
    assert parse_period("1w").text == "1w"
    assert parse_period("1M").text == "1M"
    assert parse_period(" 1y ").text == "1y"
    with pytest.raises(ValueError):
        parse_period("0h")
    with pytest.raises(ValueError):
        parse_period("abc")


def test_choose_base_period_uses_divisible_source():
    # 45m, 30m'nin tam katı değil; 15m seçilmeli.
    assert choose_base_period("45m", ["1m", "5m", "15m", "30m", "1h"]) == "15m"
    assert choose_base_period("2h", ["1h", "4h"]) == "1h"
    assert choose_base_period("1w", ["1d", "1w"]) == "1w"
    assert choose_base_period("1M", ["1d", "1w", "1M"]) == "1M"


def test_resample_ohlcv_math():
    data = make_data(step_ms=3_600_000, n=4)
    out = resample_data(data, "2h")
    assert out["opendate"] == [data["opendate"][0], data["opendate"][2]]
    assert out["open"] == [data["open"][0], data["open"][2]]
    assert out["high"] == [data["high"][1], data["high"][3]]
    assert out["low"] == [data["low"][0], data["low"][2]]
    assert out["close"] == [data["close"][1], data["close"][3]]
    assert out["volume_coin"] == [4.0, 4.0]
    assert out["volume_usdt"] == [400.0, 400.0]
    assert out["closedate"][0] == data["opendate"][2] - 1


def test_resample_weekly_does_not_create_empty_buckets():
    data = make_data(step_ms=86_400_000, n=10)
    out = resample_data(data, "1w")
    assert len(out["close"]) >= 1
    assert all(out["high"][i] >= out["close"][i] for i in range(len(out["close"])))


def test_resolve_symbols():
    gold = resolve_symbol("XAUUSD")
    assert gold.provider == "yahoo"
    assert gold.native == "GC=F"
    assert gold.live_supported is False

    crypto = resolve_symbol("BTCUSDT")
    assert crypto.provider == "binance"
    assert crypto.live_supported is True

    stock = resolve_symbol("GARAN.IS")
    assert stock.provider == "yahoo"
    assert stock.asset_class == "stock"

    fund = resolve_symbol("TEFAS:AFT")
    assert fund.provider == "tefas"
    assert fund.native == "AFT"
    assert is_live_symbol("TEFAS:AFT") is False


def test_parse_yahoo_chart_adjusts_prices():
    stamp = int(dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc).timestamp())
    payload = {
        "chart": {
            "result": [{
                "timestamp": [stamp],
                "indicators": {
                    "quote": [{
                        "open": [10.0], "high": [12.0], "low": [9.0],
                        "close": [10.0], "volume": [100.0],
                    }],
                    "adjclose": [{"adjclose": [5.0]}],
                },
            }],
            "error": None,
        }
    }
    data = parse_chart(payload, "1d")
    assert data["close"] == [5.0]
    assert data["open"] == [5.0]
    assert data["high"] == [6.0]
    assert data["low"] == [4.5]
    assert data["volume_coin"] == [100.0]


def test_parse_tefas_rows_uses_nav_as_ohlc():
    rows = [
        {"tarih": "2024-01-02", "fiyat": 1.25},
        {"tarih": "2024-01-03", "fiyat": 1.30},
        {"tarih": "bozuk", "fiyat": 1.0},
    ]
    data = parse_tefas_rows(rows)
    assert len(data["close"]) == 2
    assert data["close"] == [1.25, 1.30]
    assert data["open"] == data["close"]
    assert data["high"] == data["close"]
    assert data["low"] == data["close"]
    assert data["volume_coin"] == [0.0, 0.0]


# ---------------------------------------------------------------------------
# Periyot doğruluğu: haftalık/aylık hizalama, işlem günü gruplama, rapor
# ---------------------------------------------------------------------------
def _yahoo_payload(stamps, closes, highs=None, lows=None):
    return {
        "chart": {
            "result": [{
                "timestamp": stamps,
                "indicators": {
                    "quote": [{
                        "open": list(closes),
                        "high": list(highs or closes),
                        "low": list(lows or closes),
                        "close": list(closes),
                        "volume": [1.0] * len(stamps),
                    }],
                },
            }],
            "error": None,
        }
    }


def test_yahoo_weekly_bar_is_anchored_to_monday():
    # Devam eden haftalık bar "şu an" damgasıyla gelir; kendi haftasının
    # pazartesisine çekilmeli (önceki haftanın barıyla karışmamalı).
    prev_monday = int(dt.datetime(2023, 12, 25, tzinfo=dt.timezone.utc).timestamp())
    in_progress = int(dt.datetime(2024, 1, 5, 19, 30, tzinfo=dt.timezone.utc).timestamp())
    data = parse_chart(_yahoo_payload([prev_monday, in_progress], [10.0, 11.0]), "1w")
    assert len(data["opendate"]) == 2
    assert data["opendate"][1] == int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def test_yahoo_monthly_bar_is_anchored_to_month_start():
    first = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    in_progress = int(dt.datetime(2024, 2, 14, 10, 0, tzinfo=dt.timezone.utc).timestamp())
    data = parse_chart(_yahoo_payload([first, in_progress], [10.0, 12.0]), "1M")
    assert data["opendate"][1] == int(dt.datetime(2024, 2, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def test_yahoo_ohlc_is_sanitized():
    # Kapanış, bildirilen high'ın üstünde gelirse aralığa çekilir.
    stamp = int(dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc).timestamp())
    data = parse_chart(_yahoo_payload([stamp], [10.0], highs=[9.0], lows=[8.0]), "1d")
    assert data["high"][0] == 10.0
    assert data["low"][0] == 8.0


def _sessions(n=50, start=dt.date(2024, 1, 1), step_ms=86_400_000):
    """Hafta sonu atlayan sentetik işlem günü serisi."""
    stamps, day = [], start
    while len(stamps) < n:
        if day.weekday() < 5:
            stamps.append(int(dt.datetime(day.year, day.month, day.day,
                                           tzinfo=dt.timezone.utc).timestamp() * 1000))
        day += dt.timedelta(days=1)
    return {
        "opendate": stamps,
        "open": [100.0 + i for i in range(len(stamps))],
        "high": [101.0 + i for i in range(len(stamps))],
        "low": [99.0 + i for i in range(len(stamps))],
        "close": [100.5 + i for i in range(len(stamps))],
        "volume_coin": [1.0] * len(stamps),
        "volume_usdt": [1.0] * len(stamps),
    }


def test_session_resample_2d_groups_trading_days_without_empty_buckets():
    data = _sessions(60)
    out = resample_data(data, "2d", session_based=True)
    # 60 işlem günü -> 30 adet 2 günlük bar; hafta sonu boş kova yok.
    assert len(out["close"]) == 30
    assert out["open"][0] == data["open"][0]
    assert out["close"][0] == data["close"][1]
    assert out["high"][0] == data["high"][1]
    assert out["low"][0] == data["low"][0]


def test_session_resample_weekly_uses_calendar_weeks():
    data = _sessions(60)
    out = resample_data(data, "1w", session_based=True)
    # 60 işlem günü ≈ 12 hafta
    assert 11 <= len(out["close"]) <= 13
    assert all(out["high"][i] >= out["close"][i] for i in range(len(out["close"])))


def test_report_no_false_gaps_for_variable_month_lengths():
    from app.job_runner import _data_report

    stamps, day = [], dt.date(2020, 1, 1)
    while len(stamps) < 60:
        stamps.append(int(dt.datetime(day.year, day.month, day.day,
                                       tzinfo=dt.timezone.utc).timestamp() * 1000))
        month = day.month + 1
        year = day.year + (1 if month > 12 else 0)
        day = dt.date(year, 1 if month > 12 else month, 1)
    data = {
        "opendate": stamps,
        "open": [100.0] * len(stamps),
        "high": [101.0] * len(stamps),
        "low": [99.0] * len(stamps),
        "close": [100.5] * len(stamps),
    }
    report = _data_report(data, "1M", {"requested": len(stamps), "asset_class": "crypto"})
    assert report["gaps"] == 0
    assert report["coverage_pct"] == 100.0
    assert report["clean"] is True


def test_report_session_asset_ignores_weekends():
    from app.job_runner import _data_report

    data = _sessions(100)
    report = _data_report(data, "1d", {"requested": 100, "asset_class": "stock"})
    assert report["session_based"] is True
    assert report["gaps"] == 0
    assert report["clean"] is True


def test_report_session_asset_2d_has_no_false_gaps():
    from app.job_runner import _data_report

    data = _sessions(200)
    out = resample_data(data, "2d", session_based=True)
    report = _data_report(out, "2d", {"requested": len(out["close"]), "asset_class": "metal"})
    assert report["gaps"] == 0
    assert report["clean"] is True
