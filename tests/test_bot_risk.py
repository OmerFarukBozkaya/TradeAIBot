"""Bot risk devralma ve çökmüş botların geri getirilmesi."""

import pytest

from app import db
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


def _definition(name="Risk", risk=None):
    return {
        "name": name,
        "risk": risk or {"stop_atr": 35, "cooldown": 10},
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "gt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "lt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
    }


def test_engine_clears_stale_error_on_start(temp_db, monkeypatch):
    from app import bot_state
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(_definition())
    bot_state.save_state(
        "bot_e",
        {
            "bot_id": "bot_e",
            "cash": 100.0,
            "initial_cash": 100.0,
            "position": None,
            "last_error": "eski çöküntü",
            "total_realized_pnl": 0.0,
            "trade_count": 0,
        },
    )
    engine = TradingEngine(
        "bot_e",
        {"period": "1h", "strategies": [{"type": "custom", "id": created["id"]}], "cash": 100},
        "paper",
    )
    engine._save_state()  # run() içindeki ilk adımı taklit eder
    assert engine.state["last_error"] == "eski çöküntü"
    engine.state["last_error"] = None  # run() başında temizlenir
    assert bot_state.load_state("bot_e")["last_error"] == "eski çöküntü"


def test_resume_all_includes_errored_bots_with_autorestart(temp_db, monkeypatch):
    from app import supervisor as supervisor_module

    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("bot_err", "Hata", "trade", "paper", "1h", "{}", "error", 1, db.utcnow(), db.utcnow()),
    )
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("bot_err2", "Hata2", "trade", "paper", "1h", "{}", "error", 0, db.utcnow(), db.utcnow()),
    )
    started = []
    sup = supervisor_module.Supervisor()
    monkeypatch.setattr(sup, "start", lambda bot_id, restart=False: started.append(bot_id))
    monkeypatch.setattr(supervisor_module, "_is_alive", lambda pid: False)
    sup.resume_all()
    assert "bot_err" in started
    assert "bot_err2" not in started


def test_cooldown_only_after_configured_loss(temp_db, monkeypatch):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(_definition(risk={"cooldown": 5, "cooldown_min_loss_pct": 5}))
    engine = TradingEngine(
        "bot_cd",
        {
            "period": "1h",
            "strategies": [{"type": "custom", "id": created["id"]}],
            "cash": 100,
            "risk": {"cooldown": 5, "cooldown_min_loss_pct": 5},
        },
        "paper",
    )
    engine.state["candle_seq"] = 10
    engine.state["cooldown_until"] = -1

    # Küçük zarar eşiğin altında: cooldown uygulanmaz.
    engine._apply_cooldown(-3.0)
    assert engine.state.get("cooldown_until", -1) == -1

    # Eşiğe ulaşan zarar: 5 mum bekleme.
    engine._apply_cooldown(-5.0)
    assert engine.state["cooldown_until"] == 15


def test_cooldown_without_condition_applies_always(temp_db, monkeypatch):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(_definition(risk={"cooldown": 3}))
    engine = TradingEngine(
        "bot_cd2",
        {
            "period": "1h",
            "strategies": [{"type": "custom", "id": created["id"]}],
            "cash": 100,
            "risk": {"cooldown": 3},
        },
        "paper",
    )
    engine.state["candle_seq"] = 7
    engine._apply_cooldown(2.5)
    assert engine.state["cooldown_until"] == 10
