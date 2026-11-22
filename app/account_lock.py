"""Canlı hesap için süreçler arası kilit.

Aynı Binance hesabını birden fazla bot kullanabiliyor. Emirler aynı anda
gönderilirse bakiye iki kez kullanılabilir (ikisi de aynı USDT'yi görür).
Bu modül emir gönderimini kısa süreliğine sıraya koyar.

Kilit bir dosyadır; süreç çökerse eski kilit ``stale`` süresi sonunda kırılır.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from app.config import STATE_DIR

LOCK_NAME = "live_account.lock"


def lock_path() -> Path:
    return STATE_DIR / LOCK_NAME


def _stale_seconds() -> float:
    try:
        from app.config import settings

        return max(30.0, float(settings.LIVE_LOCK_STALE_SECONDS))
    except Exception:  # pragma: no cover - ayar okunamazsa güvenli varsayılan
        return 180.0


def acquire(timeout: Optional[float] = None, stale: Optional[float] = None) -> bool:
    """Kilidi alır. Alınamazsa ``False`` döner (bot yine de işlem yapabilir)."""
    path = lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    deadline = time.time() + (30.0 if timeout is None else max(0.0, timeout))
    stale_after = _stale_seconds() if stale is None else max(1.0, stale)
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()} {time.time():.3f}".encode("ascii"))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > stale_after:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                return False
            time.sleep(0.05)
        except OSError:
            return False


def release() -> None:
    try:
        lock_path().unlink()
    except OSError:
        pass


@contextmanager
def live_account_lock(timeout: Optional[float] = None) -> Iterator[bool]:
    """``with live_account_lock() as ok:`` — kilit alınamazsa ``ok`` False olur."""
    ok = acquire(timeout=timeout)
    try:
        yield ok
    finally:
        if ok:
            release()
