from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from app import db
from app.security import (
    COOKIE_NAME,
    authenticate,
    create_session,
    current_user,
    delete_session,
    reset_password,
    verify_user_password,
    get_csrf_from_request,
)

router = APIRouter()


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")
    token, csrf = create_session(int(user["id"]))
    from app.proxy import cookie_secure

    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        max_age=60 * 60 * 24,
    )
    return {
        "ok": True,
        "user": user["username"],
        "role": user["role"],
        "must_change_password": bool(user["must_change_password"]),
        "csrf": csrf,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    tradeai_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
):
    if tradeai_session:
        delete_session(tradeai_session)
    from app.proxy import cookie_secure

    response.delete_cookie(
        COOKIE_NAME, httponly=True, samesite="lax", secure=cookie_secure(request)
    )
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    from app.security import _session_from_token

    token = request.cookies.get(COOKIE_NAME)
    sess = _session_from_token(token)
    if not sess:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    request.state.session = sess
    return {
        "user": sess["username"],
        "role": sess["role"],
        "must_change_password": bool(sess["must_change_password"]),
        "csrf": sess["csrf_token"],
    }


@router.post("/change-password")
async def change_password(body: ChangePasswordBody, request: Request):
    from app.security import _session_from_token

    sess = _session_from_token(request.cookies.get(COOKIE_NAME))
    if not sess:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    if not verify_user_password(int(sess["user_id"]), body.current_password):
        raise HTTPException(status_code=400, detail="Mevcut şifre hatalı")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 8 karakter olmalı")
    reset_password(int(sess["user_id"]), body.new_password)
    db.log_event(None, f"Şifre değiştirildi: {sess['username']}", "info")
    return {"ok": True}
