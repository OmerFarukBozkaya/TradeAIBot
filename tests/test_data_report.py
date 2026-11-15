"""Veri raporu: istenen/gelen mum, süre biçimi, temizlik kontrolleri."""

from app.job_runner import _data_report, _format_span

DAY = 86_400_000


def make_data(n, step_ms=3_600_000, start=0, bad=None):
    """bad: {"nan": idx, "ohlc": idx, "price": idx}"""
    bad = bad or {}
    opendate = [start + i * step_ms for i in range(n)]
    close = [100.0 + i for i in range(n)]
    high = [c + 1 for c in close]
    low = [c - 1 for c in close]
    if "nan" in bad:
        close[bad["nan"]] = float("nan")
    if "ohlc" in bad:
        high[bad["ohlc"]] = low[bad["ohlc"]] - 5
    if "price" in bad:
        close[bad["price"]] = high[bad["price"]] + 10
    return {"opendate": opendate, "close": close, "high": high, "low": low}


def test_format_span_years_months_days():
    ms = (2 * 365 + 8 * 30 + 12) * DAY
    assert _format_span(ms) == "2 yıl 8 ay 12 gün"


def test_format_span_only_days():
    assert _format_span(5 * DAY) == "5 gün"
    assert _format_span(0) == "0 gün"


def test_report_counts_received_vs_requested():
    data = make_data(500)
    report = _data_report(data, "1h", {"requested": 1000, "raw_rows": 520,
                                       "duplicates_removed": 20, "pages": 2})
    assert report["received"] == 500
    assert report["requested"] == 1000
    assert report["shortfall"] == 500
    assert report["complete"] is False
    assert report["duplicates_removed"] == 20
    assert report["clean"] is True


def test_report_span_and_dates():
    data = make_data(25, step_ms=DAY, start=0)
    report = _data_report(data, "1d", {"requested": 25, "raw_rows": 25,
                                       "duplicates_removed": 0, "pages": 1})
    assert report["span_text"] == "24 gün"
    assert report["first"] == "1970-01-01 00:00"
    assert report["complete"] is True


def test_report_detects_gaps():
    data = make_data(100, step_ms=3_600_000)
    # 40. ve 41. mum arasında 5 mumluk boşluk
    for i in range(41, 100):
        data["opendate"][i] += 4 * 3_600_000
    report = _data_report(data, "1h", {"requested": 100, "raw_rows": 100,
                                       "duplicates_removed": 0, "pages": 1})
    assert report["gaps"] == 1
    assert report["missing_candles"] == 4
    assert report["clean"] is False


def test_report_detects_bad_rows():
    data = make_data(50, bad={"nan": 10, "ohlc": 20, "price": 30})
    report = _data_report(data, "1h", {"requested": 50, "raw_rows": 50,
                                       "duplicates_removed": 0, "pages": 1})
    assert report["nan_count"] == 1
    assert report["bad_ohlc_count"] == 1
    assert report["bad_price_count"] == 1
    assert report["clean"] is False


def test_report_coverage_percent():
    data = make_data(100, step_ms=3_600_000)
    for i in range(51, 100):
        data["opendate"][i] += 50 * 3_600_000
    report = _data_report(data, "1h", {"requested": 100, "raw_rows": 100,
                                       "duplicates_removed": 0, "pages": 1})
    assert report["coverage_pct"] < 100
    assert report["coverage_pct"] > 50
