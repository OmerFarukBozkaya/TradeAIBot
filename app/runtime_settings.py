"""Çalışma zamanı ayarları.

Öncelik: SQLite (panelden kaydedilen) > `.env` / varsayılan.

- Panelden yapılan değişiklikler `settings` tablosunda tutulur.
- Gizli değerler (API secret, e-posta şifresi, Telegram token) AES yerine
  stdlib ile kurulan HMAC tabanlı akış şifrelemesi + MAC ile saklanır.
- `config.settings.<KEY>` erişimleri bu katmandan geçer; böylece çalışan
  botlar ve API'ler ek bir değişiklik gerektirmeden yeni değerleri görür.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from typing import Any, Dict, Iterable, Optional

from app.settings_schema import BY_KEY

_CACHE: Dict[str, Any] = {}
_LOADED_AT = 0.0
_LOCK = threading.Lock()
_TTL_SECONDS = 5.0
_PREFIX = "enc:v1:"
_SCHEMA_READY = False


# ---------------------------------------------------------------------------
# Şifreleme yardımcıları
# ---------------------------------------------------------------------------
def _material() -> tuple[bytes, bytes]:
    from app.config import settings as _settings

    secret = str(_settings.SECRET_KEY or "tradeai-local").encode("utf-8")
    enc_key = hashlib.sha256(secret + b"|tradeai-enc").digest()
    mac_key = hashlib.sha256(secret + b"|tradeai-mac").digest()
    return enc_key, mac_key


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def encrypt(value: str) -> str:
    if value is None:
        return ""
    raw = str(value).encode("utf-8")
    if not raw:
        return ""
    enc_key, mac_key = _material()
    nonce = os.urandom(16)
    cipher = _xor(raw, _keystream(enc_key, nonce, len(raw)))
    tag = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()[:16]
    payload = base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")
    return _PREFIX + payload


def decrypt(value: str) -> str:
    if not value:
        return ""
    text = str(value)
    if not text.startswith(_PREFIX):
        return text  # eski/düz değerlerle geriye uyum
    try:
        blob = base64.urlsafe_b64decode(text[len(_PREFIX):].encode("ascii"))
        nonce, tag, cipher = blob[:16], blob[16:32], blob[32:]
        enc_key, mac_key = _material()
        expected = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            return ""
        return _xor(cipher, _keystream(enc_key, nonce, len(cipher))).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# DB okuma / yazma
# ---------------------------------------------------------------------------
def _ensure_schema() -> bool:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True
    try:
        from app import db as _db

        _db.init_db()
        _SCHEMA_READY = True
        return True
    except Exception:
        return False


def _load(force: bool = False) -> None:
    global _LOADED_AT
    if not _ensure_schema():
        return
    with _LOCK:
        if not force and time.time() - _LOADED_AT < _TTL_SECONDS:
            return
        try:
            from app import db as _db

            rows = _db.rows("SELECT key, value FROM settings")
            _CACHE.clear()
            for row in rows:
                key = row["key"]
                if key in BY_KEY:
                    _CACHE[key] = _db.get_setting(key)
            _LOADED_AT = time.time()
        except Exception:
            _LOADED_AT = time.time()


def invalidate() -> None:
    global _LOADED_AT
    with _LOCK:
        _CACHE.clear()
        _LOADED_AT = 0.0


def value(name: str, default: Any = None) -> Any:
    if name not in BY_KEY:
        return default
    _load()
    if name in _CACHE:
        return _CACHE[name]
    return default


def all_values() -> Dict[str, Any]:
    _load(force=True)
    return dict(_CACHE)


def set_many(values: Dict[str, Any]) -> Dict[str, Any]:
    """Doğrulanmış değerleri kaydeder. Gizli alanlar şifrelenir."""
    from app import db as _db

    saved: Dict[str, Any] = {}
    for key, raw in values.items():
        spec = BY_KEY.get(key)
        if not spec:
            continue
        if spec.secret:
            text = "" if raw is None else str(raw)
            if not text:
                continue  # boş = mevcut değeri koru
            _db.set_setting(key, encrypt(text))
            saved[key] = text
        else:
            _db.set_setting(key, raw)
            saved[key] = raw
    invalidate()
    return saved


def clear_secret(key: str) -> None:
    from app import db as _db

    _db.execute("DELETE FROM settings WHERE key=?", (key,))
    invalidate()


def secret_keys() -> Iterable[str]:
    return (key for key, spec in BY_KEY.items() if spec.secret)


def is_configured(key: str) -> bool:
    return bool(value(key, ""))


def mask(value_: str) -> str:
    if not value_:
        return ""
    if len(value_) <= 8:
        return "*" * len(value_)
    return value_[:4] + "*" * (len(value_) - 8) + value_[-4:]


def secret_preview(key: str) -> str:
    return mask(decrypt(str(value(key, "") or "")))
