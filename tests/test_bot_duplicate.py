"""Bot kopyalama testleri."""

import asyncio
import json

import pytest
from fastapi import HTTPException

from app import bot_state, db
from app.api.bots import DuplicateBody, duplicate_bot

CONFIG = {
    "period": "1h",
    "strategies": [{"type": "builtin", "name": "MACD"}],
    "coins": ["BTCUSDT", "ETHUSDT"],
    "cash": 500.0,
    "risk": {"stop_atr": 2, "max_stop_pct": 15},
    "filters": {"min_volume": 1000},
    "max_position_pct": 50,
}


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_state, "STATE_DIR", tmp_path / "state")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    yield tmp_path


def _seed_source(mode="paper"):
    now = db.utcnow()
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("src", "Kaynak Bot", "trade", mode, "1h", json.dumps(CONFIG), "stopped", 1, now, now),
    )
    # Kopyalanmaması gereken geçmiş veriler
    db.execute(
        "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,mode,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        ("src", "BTCUSDT", "SELL", 1.0, 100.0, 0.1, mode, 3.0, now),
    )
    db.execute(
        "INSERT INTO positions(bot_id,coin,quantity,entry_price,opened_at,status) VALUES(?,?,?,?,?,?)",
        ("src", "BTCUSDT", 1, 100, now, "open"),
    )
    db.execute(
        "INSERT INTO events(bot_id,level,message,created_at) VALUES(?,?,?,?)",
        ("src", "info", "eski log", now),
    )
    bot_state.save_state(
        "src",
        {"cash": 500.0, "total_realized_pnl": 12.0, "position": {"coin": "BTCUSDT", "quantity": 1}},
    )


def test_duplicate_copies_config_but_not_history():
    _seed_source()
    res = asyncio.run(duplicate_bot("src", DuplicateBody(name="Kopya Bot")))

    assert res["name"] == "Kopya Bot"
    assert res["period"] == "1h"
    assert res["mode"] == "paper"
    assert res["status"] == "stopped"
    assert res["config"]["coins"] == ["BTCUSDT", "ETHUSDT"]
    assert res["config"]["risk"]["stop_atr"] == 2
    assert res["config"]["filters"] == {"min_volume": 1000}
    assert res["config"]["max_position_pct"] == 50
    # Yeni bot sıfırdan başlar: durum yok, geçmiş yok.
    assert res["state"]["cash"] is None
    assert res["state"]["position"] is None
    new_id = res["id"]
    assert db.row("SELECT COUNT(*) c FROM trades WHERE bot_id=?", (new_id,))["c"] == 0
    assert db.row("SELECT COUNT(*) c FROM positions WHERE bot_id=?", (new_id,))["c"] == 0
    assert bot_state.load_state(new_id) is None
    # Yalnızca "kopyalandı" olayı yazılır.
    events = db.rows("SELECT message FROM events WHERE bot_id=?", (new_id,))
    assert len(events) == 1 and "kopyalandı" in events[0]["message"]


def test_duplicate_default_name_and_source_untouched():
    _seed_source()
    res = asyncio.run(duplicate_bot("src"))
    assert res["name"] == "Kaynak Bot (kopya)"
    # Kaynak botun verisi değişmemeli.
    assert db.row("SELECT COUNT(*) c FROM trades WHERE bot_id='src'")["c"] == 1
    assert bot_state.load_state("src")["total_realized_pnl"] == 12.0


def test_duplicate_live_mode_requires_gate():
    _seed_source(mode="paper")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(duplicate_bot("src", DuplicateBody(name="Canli Kopya", mode="live")))
    assert exc.value.status_code == 403


def test_duplicate_rejects_broken_strategy():
    _seed_source()
    db.execute(
        "UPDATE bots SET config_json=? WHERE id='src'",
        (json.dumps({**CONFIG, "strategies": [{"type": "custom", "id": "yok"}]}),),
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(duplicate_bot("src", DuplicateBody(name="Bozuk")))
    assert exc.value.status_code == 400
    assert "Strateji" in exc.value.detail


def test_duplicate_missing_bot():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(duplicate_bot("yok"))
    assert exc.value.status_code == 404
