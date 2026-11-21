"""Backtest risk kuralları: stop, iz süren, kâr al, zaman limiti."""

from app.job_runner import _format_span, _risk_exit


def make_data(rows):
    """rows: [(open, high, low, close)]"""
    return {
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "opendate": [i * 3600000 for i in range(len(rows))],
    }


def pos(entry=100.0, index=0, highest=100.0, atr=2.0):
    return {"entry": entry, "index": index, "highest": highest, "atr": atr}


def test_stop_hits_when_low_under_level():
    data = make_data([(100, 101, 95, 96)])
    hit = _risk_exit(pos(), data, 0, [2.0], {"stop_atr": 2})
    assert hit is not None
    price, reason = hit
    assert reason == "stop"
    assert price == 96.0  # 100 - 2*2


def test_stop_not_hit_when_low_above_level():
    data = make_data([(100, 102, 98, 101)])
    assert _risk_exit(pos(), data, 0, [2.0], {"stop_atr": 2}) is None


def test_trailing_stop_follows_high():
    data = make_data([(110, 112, 108, 109)])
    # tepe 112, iz süren 3*ATR => 106
    hit = _risk_exit(pos(highest=112), data, 0, [2.0], {"trail_atr": 3})
    assert hit is None  # 108 > 106
    data2 = make_data([(110, 112, 100, 101)])
    hit2 = _risk_exit(pos(highest=112), data2, 0, [2.0], {"trail_atr": 3})
    assert hit2 and hit2[1] == "takipli-stop"


def test_take_profit_pct():
    data = make_data([(100, 107, 100, 106)])
    hit = _risk_exit(pos(), data, 0, [2.0], {"take_profit_pct": 5})
    assert hit and hit[1] == "take-profit"
    assert abs(hit[0] - 105.0) < 1e-9


def test_take_profit_atr():
    data = make_data([(100, 108, 100, 107)])
    hit = _risk_exit(pos(), data, 0, [2.0], {"take_profit_atr": 3})
    assert hit and hit[1] == "take-profit"
    assert abs(hit[0] - 106.0) < 1e-9


def test_time_limit_removed():
    # Zaman limiti kaldırıldı: max_candles verilse bile zamanla kapanmaz.
    data = make_data([(100, 101, 99, 100)] * 11)
    assert _risk_exit(pos(index=0), data, 10, [2.0], {"max_candles": 10}) is None


def test_stop_has_priority_over_take_profit():
    # aynı mumda hem stop hem kâr hedefi vuruluyor -> kötümser: stop
    data = make_data([(100, 120, 90, 100)])
    hit = _risk_exit(pos(), data, 0, [2.0], {"stop_atr": 2, "take_profit_pct": 5})
    assert hit and hit[1] == "stop"


def test_no_risk_returns_none():
    data = make_data([(100, 200, 1, 100)])
    assert _risk_exit(pos(), data, 0, [2.0], {}) is None


def test_no_time_limit_no_exit_without_stop():
    # Zaman limiti kaldırıldı: stop/kâr yoksa pozisyon kapanmaz.
    data = make_data([(100, 101, 99, 100)] * 500)
    assert _risk_exit(pos(index=0), data, 400, [2.0], {"max_candles": 10}) is None


def test_trailing_waits_for_profit_threshold():
    # Kâr %10'da henüz eşik (%20) aşılmadı: takipli stop devreye girmez.
    data = make_data([(110, 112, 100, 101)])
    assert _risk_exit(pos(highest=112), data, 0, [2.0],
                      {"trail_atr": 3, "trail_after_pct": 20}) is None
    # Tepe %25 kâra ulaştı: takipli stop = 125 - 3*2 = 119, düşük 118 -> çıkış.
    data2 = make_data([(120, 125, 118, 119)])
    hit = _risk_exit(pos(highest=125), data2, 0, [2.0],
                     {"trail_atr": 3, "trail_after_pct": 20})
    assert hit and hit[1] == "takipli-stop"
    assert abs(hit[0] - 119.0) < 1e-9


def test_profit_exit_only_when_in_profit():
    from app.job_runner import _profit_exit

    lower = [70.0, 80.0, 90.0, 95.0, 92.0]
    close = [100.0, 101.0, 96.0, 85.0, 84.0]
    # 4. mum: kapanış 85 < önceki alt bant 90, önceki kapanış 96 >= 80 -> kırılım
    assert _profit_exit(lower, close, 3, 80.0) is True
    # Aynı kırılım ama pozisyon kârda değil (giriş 100) -> çıkış yok
    assert _profit_exit(lower, close, 3, 100.0) is False


def test_profit_exit_requires_cross_not_just_below():
    from app.job_runner import _profit_exit

    lower = [70.0, 80.0, 90.0, 95.0, 92.0]
    # Önceki kapanış da bandın altındaysa yeni kırılım sayılmaz.
    close = [100.0, 101.0, 75.0, 85.0, 84.0]
    assert _profit_exit(lower, close, 3, 70.0) is False

