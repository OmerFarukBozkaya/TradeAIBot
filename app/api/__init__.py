from __future__ import annotations

from fastapi import APIRouter, Depends

from app.security import csrf_protect, current_user

auth_router = APIRouter()

protected = APIRouter(dependencies=[Depends(current_user), Depends(csrf_protect)])

__all__ = ["auth_router", "protected"]
