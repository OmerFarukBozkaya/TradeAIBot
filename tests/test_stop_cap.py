"""Stop sınırları: periyot tavanı + ATR çarpanı güvenlik sınırı.

Gerçek olay: stratejilerde ``stop_atr`` yüzde sanılarak 20–35 yazılmıştı.
Kod bunu ATR çarpanı olarak kullandığından 1h'de %52, 15m'de %36 uzaklıkta
stoplar oluşuyor; bunlar hiç tetiklenmiyordu. Aşağıdaki testler stopun her
zaman periyot tavanı içinde ve canlı/backtest için aynı olduğunu doğrular.
"""

import pytest

from app import db, job_runner as jr, risk as risk_rules
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _position(entry=100.0, atr=10.0, highest=None):
    return {
        "entry": entry,
        "atr": atr,
        "highest": highest if highest is not None else entry,
    }


def _data(high=101.0, low=99.0, close=100.0):
    return {"high": [high], "low": [low], "close": [close]}


def test_absurd_atr_multiplier_is_clamped():
    # 35×ATR = %70 aşağı; güvenlik sınırı 6×ATR → 100 - 12 = 88
    pos = _position(entry=100.0, atr=2.0)
    hit = jr._risk_exit(pos, _data(low=87.0), 0, [], {"stop_atr": 35})
    assert hit is not None and hit[1] == "stop"
    assert hit[0] == pytest.approx(88.0)
    # 88'in üstündeki mum tetiklemez
    assert jr._risk_exit(pos, _data(low=89.0), 0, [], {"stop_atr": 35}) is None


def test_period_cap_applies_in_backtest():
    # 15m tavanı %4 → 96; 6×ATR daha uzak olsa bile tavan kazanır
    pos = _position(entry=100.0, atr=2.0)
    hit = jr._risk_exit(pos, _data(low=95.5), 0, [], {"stop_atr": 35}, period="15m")
    assert hit is not None
    assert hit[0] == pytest.approx(96.0)
    # 1h tavanı %6 → 94 (her çağrı kendi pozisyonuyla; ratchet taşınmasın)
    hit = jr._risk_exit(
        _position(entry=100.0, atr=2.0), _data(low=93.0), 0, [], {"stop_atr": 35}, period="1h"
    )
    assert hit[0] == pytest.approx(94.0)


def test_live_and_backtest_produce_same_stop():
    entry, atr = 100.0, 2.0
    risk = {"stop_atr": 35, "max_stop_pct": 15}
    live_stop, live_kind = risk_rules.effective_stop(entry, atr, entry, risk, period="1h")
    hit = jr._risk_exit(_position(entry, atr), _data(low=1.0), 0, [], risk, period="1h")
    assert hit is not None
    assert hit[0] == pytest.approx(live_stop)
    assert hit[1] == live_kind == "stop"


def test_normalize_risk_fixes_legacy_values():
    clean, warnings = risk_rules.normalize_risk(
        {"stop_atr": 20, "trail_atr": 25, "max_stop_pct": 30}, "1h"
    )
    assert clean["stop_atr"] == risk_rules.MAX_STOP_ATR
    assert clean["trail_atr"] == risk_rules.MAX_TRAIL_ATR
    assert clean["max_stop_pct"] == 6.0
    assert clean["breakeven_pct"] > 0
    assert len(warnings) >= 3


def test_normalize_risk_adds_stop_when_missing():
    clean, warnings = risk_rules.normalize_risk({"support_stop": True}, "4h")
    assert clean["stop_atr"] == risk_rules.DEFAULT_STOP_ATR
    assert clean["max_stop_pct"] == 8.0
    stop, _ = risk_rules.effective_stop(100.0, 2.0, 100.0, clean, period="4h")
    # 2×ATR = %4 (tavan %8'in içinde)
    assert stop == pytest.approx(96.0)
    # Yüksek oynaklıkta tavan devreye girer.
    stop, _ = risk_rules.effective_stop(100.0, 10.0, 100.0, clean, period="4h")
    assert stop == pytest.approx(92.0)


def test_normalize_risk_keeps_user_tighter_cap():
    clean, warnings = risk_rules.normalize_risk({"stop_atr": 2, "max_stop_pct": 2.5}, "1h")
    assert clean["max_stop_pct"] == 2.5
    assert not any("max_stop_pct" in w for w in warnings)


def test_engine_stop_uses_period_cap(temp_db):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(
        {
            "name": "Stop cap",
            "risk": {"stop_atr": 35, "max_stop_pct": 15, "cooldown": 0},
            "buy": {
                "logic": "AND",
                "conditions": [
                    {"left": {"type": "price", "field": "close"}, "op": "gt",
                     "right": {"type": "constant", "value": 0}}
                ],
            },
            "sell": {
                "logic": "OR",
                "conditions": [
                    {"left": {"type": "price", "field": "close"}, "op": "lt",
                     "right": {"type": "constant", "value": 0}}
                ],
            },
        }
    )
    engine = TradingEngine(
        "bot_cap",
        {"period": "1h", "strategies": [{"type": "custom", "id": created["id"]}], "cash": 100},
        "paper",
    )
    assert engine.risk["max_stop_pct"] == 6.0
    assert engine.risk["stop_atr"] == risk_rules.MAX_STOP_ATR
    assert engine.risk_warnings
    stop, _ = risk_rules.effective_stop(100.0, 2.0, 100.0, engine.risk, period="1h")
    assert stop == pytest.approx(94.0)
