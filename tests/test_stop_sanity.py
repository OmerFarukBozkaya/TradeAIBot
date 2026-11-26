"""Uzak sunucudaki gerçek botlardan alınan stop sorununun regresyon testleri.

Gözlem (26 Kasım 2026, 4 paper bot):

* 1h bot  : risk ``stop_atr=20, trail_atr=25`` → DODO giriş 0.03976, stop
  0.01893 (**%52 uzak**). Stop hiç tetiklenmedi; kârlar destek-stop ile
  %-4 kapanışa döndü.
* 15m bot : risk ``stop_atr=35, max_stop_pct=15`` → FTT pozisyonu "stop" ile
  **-%16,25** kapandı. 15m bir bot için felaket.
* 4h bot  : risk bloğu boş → hiç sert stop yok (state'te ``stop_price=None``);
  açık LISTA pozisyonu -%12'ye kadar düştü.
* 1d bot  : risk bloğu boş → stop yok; RARE -%5,78 destek-stop ile kapandı.

Bu testler, gerçek pozisyon değerleriyle stopun artık periyoda uygun ve
**her zaman var** olduğunu doğrular.
"""

from __future__ import annotations

import pytest

from app import db, risk as risk_rules
from app import bot_state

# (ad, periyot, entry, atr, ham risk, en fazla izin verilen stop mesafesi %)
REAL_POSITIONS = [
    ("1h DODO", "1h", 0.03975987, 0.00107818,
     {"stop_atr": 20, "trail_atr": 25, "cooldown": 0, "support_stop": True}, 6.0),
    ("15m XRP", "15m", 0.97408680, 0.01012181,
     {"stop_atr": 35, "max_stop_pct": 15, "cooldown": 5, "support_stop": False}, 4.0),
    ("4h LISTA", "4h", 0.10115055, 0.00838065,
     {"support_stop": True, "take_profit": True}, 8.0),
    ("1d HMSTR", "1d", 0.0001358679, 1.0864636e-05,
     {"support_stop": True, "take_profit": True}, 12.0),
]


@pytest.mark.parametrize("name,period,entry,atr,raw,cap", REAL_POSITIONS)
def test_real_positions_get_sane_stop(name, period, entry, atr, raw, cap):
    clean, warnings = risk_rules.normalize_risk(raw, period)
    stop, kind = risk_rules.effective_stop(entry, atr, entry, clean, period=period)
    assert stop is not None, f"{name}: stop yok"
    distance = (entry - stop) / entry * 100
    assert 0 < distance <= cap + 1e-9, f"{name}: stop %{distance:.2f} (tavan %{cap})"
    assert kind == "stop"
    # Düzeltme kullanıcıya bildirilir (panel/log).
    assert warnings


def test_1h_dodo_stop_is_no_longer_52_percent():
    entry, atr = 0.03975987, 0.00107818
    stop, _ = risk_rules.effective_stop(
        entry, atr, entry,
        {"stop_atr": 20, "trail_atr": 25}, period="1h",
    )
    distance = (entry - stop) / entry * 100
    assert distance <= 6.0 + 1e-9
    assert distance >= 3.0, "stop çok sıkı olmamalı (gürültüde kesilmesin)"


def test_15m_stop_cannot_lose_16_percent():
    """Eski ayarda yaşanan -%16,25'lik tek işlem tekrar edemez."""
    entry, atr = 0.2066, 0.0098  # FTT girişi ve 15m ATR'si (yaklaşık)
    clean, _ = risk_rules.normalize_risk(
        {"stop_atr": 35, "max_stop_pct": 15}, "15m"
    )
    stop, _ = risk_rules.effective_stop(entry, atr, entry, clean, period="15m")
    worst = (entry - stop) / entry * 100
    assert worst <= 4.0 + 1e-9
    # Gap olsa bile stop seviyesi %4'ten uzak değil.
    assert worst < 16.25 / 2


def test_bots_without_risk_always_have_stop():
    for period in ("1m", "5m", "15m", "1h", "4h", "1d"):
        clean, _ = risk_rules.normalize_risk({}, period)
        stop, kind = risk_rules.effective_stop(100.0, 1.0, 100.0, clean, period=period)
        assert stop is not None and stop < 100.0, period
        assert kind == "stop", period


def test_breakeven_default_protects_profit():
    """Kârdayken zarara dönmeyi engelleyen kâr koruması varsayılan olarak gelir."""
    clean, _ = risk_rules.normalize_risk({"stop_atr": 2}, "1h")
    breakeven = clean["breakeven_pct"]
    assert breakeven == pytest.approx(3.6)
    entry, atr = 100.0, 1.0
    # %3,6 kâra ulaşmadan stop ATR seviyesinde kalır (2×1 → 98).
    stop, kind = risk_rules.effective_stop(entry, atr, 103.0, clean, period="1h")
    assert stop == pytest.approx(98.0) and kind == "stop"
    # %3,6 kârı geçince stop girişe çekilir → zarara dönemez.
    stop, kind = risk_rules.effective_stop(entry, atr, 104.0, clean, period="1h")
    assert stop == pytest.approx(100.0) and kind == "breakeven"


def test_period_caps_are_ordered():
    caps = [risk_rules.period_stop_cap(p) for p in ("1m", "5m", "15m", "1h", "4h", "1d")]
    assert caps == sorted(caps), "kısa periyot daha sıkı olmalı"
    assert caps[0] <= 2.0 and caps[-1] <= 12.0


def test_serialized_bot_stop_matches_engine(tmp_path, monkeypatch):
    """Panelde görünen stop, motorun kullanacağı stop ile aynı olmalı."""
    monkeypatch.setattr(bot_state, "STATE_DIR", tmp_path / "state")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    from app.api import bots as bots_api

    bot_id = "bot_stop_parity"
    config = {
        "period": "15m",
        "strategies": [{"type": "builtin", "name": "MACD"}],
        "coins": ["BTCUSDT"],
        "cash": 100.0,
        "risk": {"stop_atr": 35, "max_stop_pct": 15},
    }
    now = db.utcnow()
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, "Stop", "trade", "paper", "15m", db.json.dumps(config),
         "running", 1, now, now),
    )
    bot_state.save_state(bot_id, {
        "bot_id": bot_id, "cash": 50.0, "initial_cash": 100.0,
        "total_realized_pnl": 0.0, "trade_count": 1,
        "position": {
            "coin": "BTCUSDT", "quantity": 0.001, "entry_price": 100.0,
            "atr": 1.0, "highest_price": 100.0, "last_price": 100.0,
            "opened_at": now, "candles": 0,
        },
    })
    payload = bots_api._serialize(db.row("SELECT * FROM bots WHERE id=?", (bot_id,)))
    risk = payload["config"]["risk"]
    # Kayıtlı 35×ATR gösterilmez; güvenli değer ve uyarı döner.
    assert risk["stop_atr"] == risk_rules.MAX_STOP_ATR
    assert risk["max_stop_pct"] == 4.0
    assert payload["config"]["risk_warnings"]
    # Panelde görünen stop = motorun hesapladığı stop.
    entry, atr = 100.0, 1.0
    expected, _ = risk_rules.effective_stop(entry, atr, entry, risk, period="15m")
    assert payload["state"]["position"]["stop_price"] == pytest.approx(expected)
    assert (entry - expected) / entry * 100 <= 4.0
