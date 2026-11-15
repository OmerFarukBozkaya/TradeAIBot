"""İstatistik sıfırlama testleri."""

import pytest

from app import bot_state, db
from app.api.settings_api import _reset_statistics


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_state, "STATE_DIR", tmp_path / "state")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "app.supervisor.supervisor.stop", lambda bot_id, timeout=10: {"ok": True}
    )
    yield tmp_path


def _bot(bot_id, name="Bot"):
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, name, "trade", "paper", "1h", "{}", "running", 1, db.utcnow(), db.utcnow()),
    )


def _seed():
    _bot("b1")
    _bot("b2")
    db.execute(
        "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,mode,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        ("b1", "BTCUSDT", "SELL", 1.0, 100.0, 0.1, "paper", 2.0, db.utcnow()),
    )
    db.execute(
        "INSERT INTO trades(bot_id,coin,side,quantity,price,fee,mode,pnl_pct,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        ("b2", "ETHUSDT", "BUY", 1.0, 50.0, 0.1, "paper", None, db.utcnow()),
    )
    db.execute(
        "INSERT INTO positions(bot_id,coin,quantity,entry_price,opened_at,status) VALUES(?,?,?,?,?,?)",
        ("b1", "BTCUSDT", 1, 100, db.utcnow(), "open"),
    )
    db.execute(
        "INSERT INTO positions(bot_id,coin,quantity,entry_price,opened_at,closed_at,status) "
        "VALUES(?,?,?,?,?,?,?)",
        ("b1", "ETHUSDT", 1, 50, db.utcnow(), db.utcnow(), "closed"),
    )
    db.execute(
        "INSERT INTO pnl_snapshots(bot_id,total_value,cash,pnl,created_at) VALUES(?,?,?,?,?)",
        ("b1", 100, 50, 1, db.utcnow()),
    )
    db.execute(
        "INSERT INTO signal_events(bot_id,coin,decision,created_at) VALUES(?,?,?,?)",
        ("b1", "BTCUSDT", "BUY", db.utcnow()),
    )
    db.execute(
        "INSERT INTO events(bot_id,level,message,created_at) VALUES(?,?,?,?)",
        ("b1", "info", "eski kayit", db.utcnow()),
    )
    db.execute(
        "INSERT INTO jobs(id,type,params_json,status,created_at) VALUES(?,?,?,?,?)",
        ("j1", "scan", "{}", "done", db.utcnow()),
    )
    db.execute(
        "INSERT INTO jobs(id,type,params_json,status,created_at) VALUES(?,?,?,?,?)",
        ("j2", "scan", "{}", "running", db.utcnow()),
    )
    bot_state.save_state(
        "b1", {"cash": 100.0, "total_realized_pnl": 42.0, "positions": {"BTCUSDT": {}}}
    )


def test_reset_all_clears_stats_and_keeps_open_position_and_cash():
    _seed()
    res = _reset_statistics(None)
    assert res["ok"] is True
    assert res["scope"] == "all"
    assert db.row("SELECT COUNT(*) c FROM trades")["c"] == 0
    assert db.row("SELECT COUNT(*) c FROM pnl_snapshots")["c"] == 0
    assert db.row("SELECT COUNT(*) c FROM signal_events")["c"] == 0
    # Silinen olayların yerine tek bir denetim kaydı eklenir.
    assert db.row("SELECT COUNT(*) c FROM events")["c"] == 1
    # Kapanmış pozisyon silindi, açık pozisyon korundu.
    assert [r["status"] for r in db.rows("SELECT status FROM positions")] == ["open"]
    # Bitmiş iş silindi, devam eden iş kaldı.
    assert db.row("SELECT COUNT(*) c FROM jobs")["c"] == 1
    assert db.row("SELECT id FROM jobs")["id"] == "j2"
    # Sayaç sıfırlandı; nakit ve açık pozisyon korundu.
    state = bot_state.load_state("b1")
    assert state["total_realized_pnl"] == 0.0
    assert state["cash"] == 100.0
    assert state["positions"]
    # Botlar durdurulmuş işaretlendi.
    assert [r["status"] for r in db.rows("SELECT status FROM bots")] == ["stopped", "stopped"]


def test_reset_single_bot_keeps_other_bot_data():
    _seed()
    _reset_statistics("b1")
    assert db.row("SELECT COUNT(*) c FROM trades WHERE bot_id='b1'")["c"] == 0
    assert db.row("SELECT COUNT(*) c FROM trades WHERE bot_id='b2'")["c"] == 1
    # Tek bot sıfırlamasında iş geçmişine dokunulmaz.
    assert db.row("SELECT COUNT(*) c FROM jobs")["c"] == 2
    # Seçili botun olayları silinir; denetim kaydı (bot_id yok) eklenir.
    assert db.row("SELECT COUNT(*) c FROM events WHERE bot_id='b1'")["c"] == 0
    assert db.row("SELECT COUNT(*) c FROM events")["c"] == 1
    # Diğer bot hâlâ çalışıyor, kendi durumu yok.
    status = {r["id"]: r["status"] for r in db.rows("SELECT id,status FROM bots")}
    assert status == {"b1": "stopped", "b2": "running"}
    assert bot_state.load_state("b2") is None
