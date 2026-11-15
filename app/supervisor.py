"""Bot süreç yöneticisi.

Tmux/systemd yerine kendi supervisor'ımız:
- alt süreç başlatma/durdurma
- heartbeat ve PID takibi
- çökme sonrası opsiyonel yeniden başlatma
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

from app import bot_state, db
from app.config import BASE_DIR, settings

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def _is_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    if psutil:
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


class Supervisor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._monitor: Optional[threading.Thread] = None
        self._stopping = False
        self._restart_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    def start(self, bot_id: str, restart: bool = False) -> Dict[str, object]:
        with self._lock:
            bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
            if not bot:
                raise ValueError("Bot bulunamadı")
            if _is_alive(bot["pid"]) and bot["status"] == "running":
                return {"ok": True, "message": "Bot zaten çalışıyor", "pid": bot["pid"]}

            bot_state.clear_stop(bot_id)
            cmd = [sys.executable, "-m", "app.bot_runner", "--bot-id", bot_id]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            log_file = paths_log(bot_id)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handle = open(log_file, "a", encoding="utf-8")
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            process = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
                creationflags=creationflags,
            )
            db.execute(
                "UPDATE bots SET status='running', pid=?, updated_at=? WHERE id=?",
                (process.pid, db.utcnow(), bot_id),
            )
            db.log_event(
                bot_id,
                f"Supervisor başlattı (PID {process.pid})" + (" [restart]" if restart else ""),
                "info",
            )
            return {"ok": True, "pid": process.pid}

    # ------------------------------------------------------------------
    def stop(self, bot_id: str, timeout: int = 20) -> Dict[str, object]:
        bot = db.row("SELECT * FROM bots WHERE id=?", (bot_id,))
        if not bot:
            raise ValueError("Bot bulunamadı")
        pid = bot["pid"]
        db.execute("UPDATE bots SET status='stopping', updated_at=? WHERE id=?", (db.utcnow(), bot_id))
        bot_state.request_stop(bot_id)
        if not _is_alive(pid):
            bot_state.clear_stop(bot_id)
            db.execute(
                "UPDATE bots SET status='stopped', pid=NULL, updated_at=? WHERE id=?",
                (db.utcnow(), bot_id),
            )
            return {"ok": True, "message": "Bot zaten durmuş"}
        # Önce nazik durdurma (stop dosyası + SIGTERM)
        try:
            if os.name == "nt":
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _is_alive(pid):
                break
            time.sleep(1)
        if _is_alive(pid):
            try:
                if psutil:
                    psutil.Process(pid).kill()
                elif os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
            time.sleep(1)
        bot_state.clear_stop(bot_id)
        db.execute(
            "UPDATE bots SET status='stopped', pid=NULL, updated_at=? WHERE id=?",
            (db.utcnow(), bot_id),
        )
        db.log_event(bot_id, "Supervisor durdurdu", "info")
        return {"ok": True, "message": "Bot durduruldu"}

    def restart(self, bot_id: str) -> Dict[str, object]:
        self.stop(bot_id)
        return self.start(bot_id, restart=True)

    # ------------------------------------------------------------------
    def resume_all(self) -> None:
        """Uygulama yeniden başladığında çalışması gereken botları ayağa kaldırır.

        Yalnız `running`/`stopping` değil, yeniden başlatma açıkken çökmüş
        (`error`) botlar da kaldırılır: container yeniden oluşturulduğunda
        altyapı kesintisi yüzünden düşen botlar kendiliğinden geri gelir.
        """
        for bot in db.rows(
            "SELECT * FROM bots WHERE status IN ('running','stopping') "
            "OR (status='error' AND COALESCE(auto_restart,1)=1)"
        ):
            bot_id = bot["id"]
            if _is_alive(bot["pid"]) and bot["status"] == "running":
                db.log_event(bot_id, "Supervisor mevcut süreci devraldı", "info")
                continue
            if bot["status"] == "error":
                db.log_event(bot_id, "Çökmüş bot otomatik geri getiriliyor", "warning")
            try:
                self.start(bot_id, restart=True)
            except Exception as exc:
                db.log_event(bot_id, f"Otomatik başlatma hatası: {exc}", "error")

    def start_monitor(self) -> None:
        if self._monitor and self._monitor.is_alive():
            return
        self._stopping = False
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor.start()

    def stop_monitor(self) -> None:
        self._stopping = True

    def _monitor_loop(self) -> None:
        while not self._stopping:
            time.sleep(max(5, settings.HEARTBEAT_SECONDS))
            try:
                self._check_once()
            except Exception as exc:
                db.log_event(None, f"Supervisor izleme hatası: {exc}", "error")

    def _check_once(self) -> None:
        for bot in db.rows("SELECT * FROM bots WHERE status IN ('running','stopping')"):
            bot_id = bot["id"]
            if _is_alive(bot["pid"]):
                continue
            if bot["status"] == "stopping":
                db.execute(
                    "UPDATE bots SET status='stopped', pid=NULL, updated_at=? WHERE id=?",
                    (db.utcnow(), bot_id),
                )
                continue
            if int(bot["auto_restart"] or 0) and settings.AUTO_RESTART:
                count = self._restart_counts.get(bot_id, 0) + 1
                self._restart_counts[bot_id] = count
                if count <= 5:
                    db.log_event(bot_id, "Süreç ölmüş, yeniden başlatılıyor", "warning")
                    try:
                        self.start(bot_id, restart=True)
                    except Exception as exc:
                        db.log_event(bot_id, f"Yeniden başlatma hatası: {exc}", "error")
                    continue
            db.execute(
                "UPDATE bots SET status='stopped', pid=NULL, updated_at=? WHERE id=?",
                (db.utcnow(), bot_id),
            )
            db.log_event(bot_id, "Süreç sonlandı", "warning")


def paths_log(bot_id: str):
    from app.config import LOG_DIR

    return LOG_DIR / "bots" / f"{bot_id}.log"


supervisor = Supervisor()
