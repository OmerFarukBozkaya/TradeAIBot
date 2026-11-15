from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.paths import paths

_WAL_READY = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS bots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'trade',
    mode TEXT NOT NULL DEFAULT 'paper',
    period TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped',
    pid INTEGER,
    auto_restart INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    config_snapshot TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    exit_reason TEXT,
    pid INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT,
    run_id INTEGER,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    order_id TEXT,
    client_order_id TEXT,
    mode TEXT NOT NULL,
    reason TEXT,
    pnl_pct REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    coin TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL,
    target_price REAL,
    highest_price REAL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    close_price REAL,
    pnl_pct REAL,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT,
    total_value REAL NOT NULL,
    cash REAL NOT NULL,
    pnl REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    result_json TEXT,
    error TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    pid INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(strategy_id, version)
);

CREATE TABLE IF NOT EXISTS strategy_backtests (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    coin TEXT NOT NULL,
    period TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT,
    strategy_id TEXT,
    version INTEGER,
    coin TEXT,
    period TEXT,
    candle_time TEXT,
    decision TEXT,
    conditions_json TEXT,
    values_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coin_lists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    coins_json TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_bot ON trades(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trades_coin ON trades(coin, created_at);
CREATE INDEX IF NOT EXISTS idx_events_bot ON events(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_signals_bot ON signal_events(bot_id, created_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    """SQLite bağlantısı açar.

    Docker yeniden oluşturulurken bind-mount (`Data/`) kısa süreliğine erişilemez
    olabiliyor; bu yüzden artan beklemeyle birkaç kez denenir. Botların bu yüzden
    çökmesi yerine bağlantı beklenir.
    """
    paths.data.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(8):
        try:
            conn = sqlite3.connect(str(paths.db), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            # WAL yalnızca bir kez ayarlanır; kilitliyken hata kritik değildir,
            # mevcut journal moduyla devam edilir (kesinti olmasın).
            global _WAL_READY
            if not _WAL_READY:
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    _WAL_READY = True
                except sqlite3.OperationalError:
                    pass
            return conn
        except sqlite3.OperationalError as exc:
            last_error = exc
            time.sleep(min(2.0, 0.15 * (2 ** attempt)))
    if last_error:
        raise last_error
    raise sqlite3.OperationalError("Veritabanı açılamadı")


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    # Hazır coin listeleri (idempotent): tablo oluştuktan sonra tohumlanır.
    from app.coin_lists import ensure_presets

    ensure_presets()


def _migrate(conn: sqlite3.Connection) -> None:
    """Eski veritabanlarına eksik kolonları ekler (idempotent)."""
    additions = {
        "jobs": {
            "progress": "INTEGER NOT NULL DEFAULT 0",
            "message": "TEXT",
            "pid": "INTEGER",
        },
    }
    for table, columns in additions.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def rows(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def row(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    items = rows(sql, params)
    return items[0] if items else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with db() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def get_setting(key: str, default: Any = None) -> Any:
    item = row("SELECT value FROM settings WHERE key=?", (key,))
    if not item:
        return default
    try:
        return json.loads(item["value"])
    except (TypeError, ValueError):
        return item["value"]


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, json.dumps(value), utcnow()),
    )


def log_event(bot_id: Optional[str], message: str, level: str = "info") -> None:
    execute(
        "INSERT INTO events(bot_id,level,message,created_at) VALUES(?,?,?,?)",
        (bot_id, level, message, utcnow()),
    )


def atomic_write_json(path: Path, payload: Any) -> None:
    """Atomik JSON yazımı. Yarım dosya / bozuk state riskini ortadan kaldırır."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default
