from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, status

from app.config import settings
from app import db

COOKIE_NAME = "tradeai_session"
MAX_FAILED = 5
LOCK_MINUTES = 15

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, salt_hex, digest_hex = encoded.split("$", 2)
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=32,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bootstrap_admin() -> None:
    """İlk açılışta admin kullanıcı oluşturur."""
    existing = db.row("SELECT id FROM users LIMIT 1")
    if existing:
        return
    password = settings.ADMIN_PASSWORD or secrets.token_urlsafe(12)
    db.execute(
        "INSERT INTO users(username,password_hash,role,must_change_password,created_at) "
        "VALUES(?,?,?,?,?)",
        (settings.ADMIN_USER, hash_password(password), "admin", 1, db.utcnow()),
    )
    if settings.ADMIN_PASSWORD:
        db.log_event(None, f"Admin kullanıcısı oluşturuldu: {settings.ADMIN_USER}", "info")
    else:
        # Şifre yoksa konsola yaz. Container loglarından okunabilir.
        print("=" * 60)
        print(" İLK KURULUM ADMIN BİLGİLERİ")
        print(f" Kullanıcı : {settings.ADMIN_USER}")
        print(f" Şifre     : {password}")
        print(" Bu şifreyi girişten sonra değiştirin.")
        print("=" * 60)


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_HOURS)).isoformat(
        timespec="seconds"
    )
    db.execute(
        "INSERT INTO sessions(id,user_id,token_hash,csrf_token,created_at,expires_at) "
        "VALUES(?,?,?,?,?,?)",
        (secrets.token_hex(16), user_id, _token_hash(token), csrf, db.utcnow(), expires),
    )
    return token, csrf


def delete_session(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def _session_from_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    item = db.row(
        "SELECT s.*, u.username, u.role, u.must_change_password "
        "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
        (_token_hash(token),),
    )
    if not item:
        return None
    try:
        expires = datetime.fromisoformat(item["expires_at"])
    except ValueError:
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.execute("DELETE FROM sessions WHERE id=?", (item["id"],))
        return None
    return item


def authenticate(username: str, password: str) -> Optional[dict]:
    user = db.row("SELECT * FROM users WHERE username=?", (username,))
    if not user:
        return None
    if user["locked_until"]:
        try:
            until = datetime.fromisoformat(user["locked_until"])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Çok fazla hatalı deneme. Hesap geçici olarak kilitli.",
                )
        except ValueError:
            pass
    if not verify_password(password, user["password_hash"]):
        failed = int(user["failed_attempts"]) + 1
        locked_until = None
        if failed >= MAX_FAILED:
            locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)
            ).isoformat(timespec="seconds")
            failed = 0
        db.execute(
            "UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
            (failed, locked_until, user["id"]),
        )
        return None
    db.execute(
        "UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?", (user["id"],)
    )
    return user


async def current_user(
    request: Request,
    tradeai_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> dict:
    session = _session_from_token(tradeai_session)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli"
        )
    request.state.session = session
    return session


async def csrf_protect(
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    session = getattr(request.state, "session", None)
    if not session:
        # Bağımlılık sırası garanti olmadığı için oturumu burada da çöz.
        from app.security import _session_from_token

        session = _session_from_token(request.cookies.get(COOKIE_NAME))
        if session:
            request.state.session = session
    if not session:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, session["csrf_token"]):
        raise HTTPException(status_code=403, detail="Geçersiz CSRF token")


def get_csrf_from_request(request: Request) -> Optional[str]:
    session = getattr(request.state, "session", None)
    return session["csrf_token"] if session else None


def reset_password(user_id: int, new_password: str) -> None:
    db.execute(
        "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
        (hash_password(new_password), user_id),
    )


def verify_user_password(user_id: int, password: str) -> bool:
    user = db.row("SELECT password_hash FROM users WHERE id=?", (user_id,))
    return bool(user and verify_password(password, user["password_hash"]))
