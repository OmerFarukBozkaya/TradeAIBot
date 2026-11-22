"""Dayanıklılık: geçici DB / borsa kesintileri botu çökertmemeli.

Loglarda görülen iki hata:
  1) sqlite3.OperationalError: unable to open database file
     → Docker yeniden oluşturulurken Windows bind-mount (Data/) kısa süre erişilemez.
  2) Binance /api/v3/klines 500 → borsanın geçici sunucu hatası.
"""

import sqlite3

import pytest

from app import db
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


class FakeClient:
    def __init__(self, balances=None):
        self._balances = balances or []

    def get_account(self):
        return {"balances": self._balances}


class FakeBinance:
    """İlk N çağrıda 500 hatası veren sahte borsa."""

    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = 0
        self.client = FakeClient()

    def get_coin_data(self, coin, period, limit):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(
                "500 Server Error: Internal Server Error for url: "
                "https://api.binance.com/api/v3/klines?symbol=DODOUSDT"
            )
        return {"close": [1.0, 2.0], "open": [1.0, 1.0], "high": [1.0, 2.0], "low": [1.0, 1.0]}


def make_engine(monkeypatch, binance=None):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    created = create_custom(
        {
            "name": "Dayanıklılık",
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
    )
    engine = TradingEngine(
        "bot_res",
        {"period": "15m", "strategies": [{"type": "custom", "id": created["id"]}], "cash": 100},
        "paper",
    )
    engine.binance = binance or FakeBinance()
    monkeypatch.setattr("app.engine.time.sleep", lambda *a, **k: None)
    monkeypatch.setattr("app.engine.notifier.send", lambda *a, **k: None)
    return engine


def test_data_retries_then_succeeds(monkeypatch):
    engine = make_engine(monkeypatch, FakeBinance(fail_times=2))
    data = engine._data("DODOUSDT")
    assert data["close"] == [1.0, 2.0]
    assert engine.binance.calls == 3


def test_data_raises_after_retries(monkeypatch):
    engine = make_engine(monkeypatch, FakeBinance(fail_times=99))
    with pytest.raises(RuntimeError):
        engine._data("DODOUSDT")
    assert engine.binance.calls == 4


def test_heartbeat_survives_db_failure(monkeypatch, capsys):
    engine = make_engine(monkeypatch)

    def boom(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(db, "execute", boom)
    monkeypatch.setattr(engine, "_save_state", boom)
    engine.heartbeat()  # istisna yükselmemeli
    out = capsys.readouterr().out
    assert "pid yazılamadı" in out or "state yazılamadı" in out


def test_log_survives_db_failure(monkeypatch):
    engine = make_engine(monkeypatch)
    monkeypatch.setattr(db, "log_event", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    engine._log("bot_res", "deneme", "warning")  # istisna yükselmemeli


def test_finish_run_survives_db_failure(monkeypatch):
    engine = make_engine(monkeypatch)
    engine.run_id = 5
    monkeypatch.setattr(db, "execute", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    engine._finish_run("error")  # istisna yükselmemeli


def test_connect_retries_when_mount_missing(monkeypatch, tmp_path):
    """İlk denemelerde dosya açılamazsa bağlantı bekleyip tekrar dener."""
    real_connect = sqlite3.connect
    attempts = {"n": 0}

    def flaky(dsn, *args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise sqlite3.OperationalError("unable to open database file")
        return real_connect(dsn, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", flaky)
    monkeypatch.setattr("app.db.time.sleep", lambda *a, **k: None)
    conn = db.connect()
    assert attempts["n"] == 3
    conn.close()


def test_missing_schema_is_repaired_automatically(tmp_path, monkeypatch):
    """Şemasız bir DB dosyası (eski/kopya) ilk sorguda kendini onarır."""
    target = tmp_path / "empty.db"
    sqlite3.connect(str(target)).close()  # boş dosya, tablo yok
    monkeypatch.setattr(paths, "db", target)

    # conftest'in kurduğu şema bu dosyada yok; sorgu düşmemeli.
    assert db.rows("SELECT COUNT(*) AS c FROM ai_models")[0]["c"] == 0
    db.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)",
        ("probe", "1", db.utcnow()),
    )
    assert db.row("SELECT value FROM settings WHERE key='probe'")["value"] == "1"
