"""Trend takibi çekirdeği: ratchet'li takipli stop, güncel ATR, tekrar giriş.

Gerçek sorunlar:
  * Takipli stop her mumda yeniden hesaplanıyordu ve **geri inebiliyordu**;
    oynaklık artınca veya zirve gerileyince stop gevşiyor, kâr geri veriliyordu.
  * Takipli stop girişteki ATR'ye sabitlenmişti; trend sırasında oynaklık
    değişince stop ya çok sıkı ya çok gevşek kalıyordu.
  * Hazır strateji sarmalayıcısı, stop ile çıkıldıktan sonra (SELL sinyali
    üretilmediği için) yeniden girişi **kalıcı olarak** engelliyordu.
"""

from __future__ import annotations

import pytest

from app import risk as risk_rules
from app.strategies.builtin import BuiltinStrategy


# --- Ratchet --------------------------------------------------------------
def test_stop_never_goes_backwards():
    risk = {"stop_atr": 2, "trail_atr": 5, "trail_after_pct": 0}
    # Zirve 120, ATR 2 → trail 110
    stop1, _ = risk_rules.effective_stop(100, 2, 120, risk, period="4h", atr_now=2)
    assert stop1 == pytest.approx(110.0)
    # Aynı zirvede ATR 4'e çıktı → trail 100'a düşerdi; ratchet 110'da tutar.
    stop2, _ = risk_rules.effective_stop(
        100, 2, 120, risk, period="4h", atr_now=4, previous_stop=stop1
    )
    assert stop2 == pytest.approx(110.0), "stop gevşedi (kâr geri verilir)"


def test_ratchet_beats_shrinking_peak():
    risk = {"stop_atr": 3, "trail_atr": 5, "trail_after_pct": 0}
    peak_stop, _ = risk_rules.effective_stop(100, 2, 130, risk, period="4h", atr_now=2)
    # Zirve kaydı düşük gelirse (ör. geçici veri) stop yine düşmemeli.
    later, _ = risk_rules.effective_stop(
        100, 2, 120, risk, period="4h", atr_now=2, previous_stop=peak_stop
    )
    assert later >= peak_stop - 1e-9


def test_trailing_uses_current_atr():
    """Oynaklık artınca takipli stop genişler (giriş ATR'sine kilitlenmez)."""
    risk = {"stop_atr": 2, "trail_atr": 5, "trail_after_pct": 0}
    tight, _ = risk_rules.effective_stop(100, 1, 130, risk, period="4h", atr_now=1)
    wide, _ = risk_rules.effective_stop(100, 1, 130, risk, period="4h", atr_now=3)
    assert tight == pytest.approx(125.0)
    assert wide == pytest.approx(115.0)
    # İlk stop her zaman giriş ATR'siyle (atr=1 → 98)
    hard, _ = risk_rules.effective_stop(100, 1, 100, risk, period="4h", atr_now=3)
    assert hard == pytest.approx(98.0)


def test_trail_arms_only_after_threshold():
    risk = {"stop_atr": 2, "trail_atr": 5, "trail_after_pct": 10}
    # +5% kâr: takipli stop henüz devrede değil → sabit ATR stop (96)
    stop, kind = risk_rules.effective_stop(100, 2, 105, risk, period="4h", atr_now=2)
    assert stop == pytest.approx(96.0) and kind == "stop"
    # +12%: trail devrede → 112 - 10 = 102
    stop, kind = risk_rules.effective_stop(100, 2, 112, risk, period="4h", atr_now=2)
    assert stop == pytest.approx(102.0) and kind == "takipli-stop"


def test_breakeven_default_is_not_too_early():
    """Erken breakeven trendi sıfıra çekiyordu; varsayılan artık geç."""
    clean, _ = risk_rules.normalize_risk({"stop_atr": 3}, "4h")
    assert clean["breakeven_pct"] >= 4.5, "breakeven çok erken (trend kesilir)"


# --- Hazır strateji: tekrar giriş ----------------------------------------
def test_builtin_allows_reentry_after_stop_out():
    """Stop ile çıkıldıktan sonra yeni kırılıma girilebilmeli."""
    strat = BuiltinStrategy("TrendRider")
    # Elle sinyal dizisi: kesintili iki yükseliş (arada stop olmuş gibi)
    signals = [None] * 65
    signals[60:65] = ["BUY", "BUY", "False", "BUY", "SELL"]
    strat._prepared = signals
    n = len(signals)
    data = {
        "close": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n,
        "opendate": list(range(n)), "volume_usdt": [1.0] * n,
    }
    # İlk giriş (60) ve stop sonrası ikinci giriş (63) ikisi de olmalı.
    assert strat.evaluate_at(data, 60)["buy"] is True
    assert strat.evaluate_at(data, 61)["buy"] is False, "aynı sinyal serisinde tekrar alım"
    assert strat.evaluate_at(data, 63)["buy"] is True, "stop sonrası tekrar giriş engellendi"
    assert strat.evaluate_at(data, 64)["sell"] is True


# --- TrendRider: lookahead yok, az işlem ---------------------------------
def _series(n=600):
    """Konsolidasyon → geri çekilmeli yükseliş → düşüş (gerçekçi).

    Düzgün (monoton) bir yükselişte "bant kırılımı" hiç oluşmaz; gerçek
    piyasada her yükseliş dalgası geri çekilme içerir. Test serisi bunu
    taklit eder: 5 mum yükseliş + 2 mum geri çekilme.
    """
    close, high, low = [], [], []
    price = 100.0
    for i in range(n):
        if i < 260:
            price = 100.0 + ((i % 7) - 3) * 0.2
        elif i < 420:
            price *= 1.010 if (i % 7) < 5 else 0.985
        else:
            price *= 0.990 if (i % 7) < 5 else 1.004
        close.append(price)
        high.append(price * 1.008)
        low.append(price * 0.992)
    return high, low, close


def test_trend_rider_has_no_lookahead():
    from Stratejiler import Stratejiler

    high, low, close = _series()
    full = Stratejiler.TrendRider(high, low, close)
    # Veri kısaltıldığında **önceki** sinyaller değişmemeli.
    cut = 300
    part = Stratejiler.TrendRider(high[:cut], low[:cut], close[:cut])
    assert full[:cut] == part[:cut], "gelecekteki barlar geçmiş sinyalleri değiştiriyor"


def test_trend_rider_enters_trend_and_exits_at_end():
    from Stratejiler import Stratejiler
    from app.strategies.builtin import BuiltinStrategy

    high, low, close = _series()
    sig = Stratejiler.TrendRider(high, low, close)
    strat = BuiltinStrategy("TrendRider")
    strat._prepared = sig
    data = {
        "close": close, "high": high, "low": low,
        "opendate": list(range(len(close))), "volume_usdt": [1.0] * len(close),
    }
    entries = [i for i in range(260, len(close)) if strat.evaluate_at(data, i)["buy"]]
    assert entries, "yükseliş trendinde hiç alım yok"
    # Trend 260. mumda başlıyor; giriş ilk 40 mum içinde (geç değil).
    assert 260 <= entries[0] < 300, f"giriş trendin başında değil: {entries[0]}"
    # Düşüş başladıktan sonra (430+) yeni alım olmamalı: rejim aşağı.
    assert not [i for i in entries if i >= 430], "düşüş trendinde alım yapılıyor"
    # Testere dişi sınırı: bu yapay seride geri çekilmeler çok derin; yine de
    # işlem sayısı makul kalmalı (gerçek 4h verisinde ~1 işlem/140 mum).
    assert len(entries) <= 30, f"aşırı işlem: {len(entries)}"


def test_compiled_trend_signal_triggers_trades():
    """Donchian bandı offset'siz kullanılırsa hiç işlem açılmıyordu (regresyon)."""
    import importlib.util
    from pathlib import Path

    from app.strategies.compiler import compile_strategy

    path = Path(__file__).resolve().parents[1] / "scripts" / "upgrade_trend_strategies.py"
    spec = importlib.util.spec_from_file_location("upgrade_trend", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    definition = {"name": "Trend test", "risk": {"stop_atr": 3}, **mod.TREND_SIGNAL}
    compiled = compile_strategy(definition, "tmp", 1)

    high, low, close = _series(600)
    data = {
        "close": close, "high": high, "low": low,
        "open": close, "opendate": list(range(len(close))),
        "volume_usdt": [1] * len(close),
    }
    from app.strategies.registry import IndicatorCache

    cache = IndicatorCache(data)
    signals = [
        compiled.evaluate_at(data, cache, i, detail=False)["buy"]
        for i in range(300, 600)
    ]
    assert any(signals), "sinyal hiç tetiklenmiyor (offset shift 1 eksik olabilir)"
