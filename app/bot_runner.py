"""Tek bir botun çalıştığı alt süreç.

Kullanım:
    python -m app.bot_runner --bot-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

from app import db, bot_state
from app.engine import TradingEngine


def _safe_update(bot_id: str, status: str) -> None:
    try:
        db.execute(
            "UPDATE bots SET status=?, pid=NULL, updated_at=? WHERE id=?",
            (status, db.utcnow(), bot_id),
        )
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id", required=True)
    args = parser.parse_args()
    bot_id = args.bot_id

    # Docker yeniden oluşturulurken bind-mount kısa süre erişilemez olabilir:
    # bu pencerede çökmek yerine bekleyip devam et.
    bot = None
    last_error = None
    for attempt in range(12):
        try:
            db.init_db()
            bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(5.0, 0.5 * (attempt + 1)))
    if bot is None:
        print(f"Bot okunamadı: {bot_id} ({last_error})", file=sys.stderr)
        return 1

    config = json.loads(bot["config_json"])
    mode = bot["mode"]
    try:
        db.execute(
            "UPDATE bots SET status='running', pid=?, updated_at=? WHERE id=?",
            (os.getpid(), db.utcnow(), bot_id),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Durum yazılamadı (devam): {exc}", file=sys.stderr)

    engine = TradingEngine(bot_id, config, mode)

    def _handle(signum, frame):
        engine.stop_event = True
        bot_state.request_stop(bot_id)

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    exit_status = "stopped"
    try:
        engine.run()
    except Exception as exc:
        exit_status = "error"
        try:
            db.log_event(bot_id, f"Bot çöktü: {exc}", "error")
        except Exception:  # noqa: BLE001
            print(f"Bot çöktü: {exc}", file=sys.stderr)
        raise
    finally:
        bot_state.clear_stop(bot_id)
        _safe_update(bot_id, exit_status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
