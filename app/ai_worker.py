"""AI profili için arka plan işçisi.

Çekirdek imajda AI bağımlılıkları yoktur. `docker compose --profile ai up` ile
bu işçi ayağa kalkar ve `ai_*` türündeki işleri işler.
"""

from __future__ import annotations

import json
import time
import traceback

from app import db
from app.job_runner import HANDLERS


def main() -> None:
    db.init_db()
    print("AI worker başladı. Kuyruk izleniyor…", flush=True)
    while True:
        try:
            job = db.row(
                "SELECT * FROM jobs WHERE status='queued' AND type LIKE 'ai_%' ORDER BY created_at LIMIT 1"
            )
            if not job:
                time.sleep(5)
                continue
            db.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (db.utcnow(), job["id"]),
            )
            print(f"AI işi alındı: {job['id']} ({job['type']})", flush=True)
            try:
                params = json.loads(job["params_json"])
                handler = HANDLERS.get(job["type"])
                if not handler:
                    raise ValueError(f"Bilinmeyen AI işi: {job['type']}")
                result = handler(params)
                db.execute(
                    "UPDATE jobs SET status='done', result_json=?, finished_at=? WHERE id=?",
                    (json.dumps(result, ensure_ascii=False), db.utcnow(), job["id"]),
                )
            except Exception as exc:
                db.execute(
                    "UPDATE jobs SET status='error', error=?, finished_at=? WHERE id=?",
                    (f"{exc}\n{traceback.format_exc()}", db.utcnow(), job["id"]),
                )
                print(f"AI işi hatası: {exc}", flush=True)
        except Exception as exc:
            print(f"AI worker ana döngü hatası: {exc}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
