from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import coin_lists

router = APIRouter()


class CoinListBody(BaseModel):
    name: str
    coins: List[str] = []


class CoinListUpdateBody(BaseModel):
    name: Optional[str] = None
    coins: Optional[List[str]] = None


class DuplicateBody(BaseModel):
    name: Optional[str] = None


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(400, str(exc))


@router.get("")
async def lists():
    return coin_lists.list_lists()


@router.post("")
async def create(body: CoinListBody):
    try:
        return coin_lists.create_list(body.name, body.coins)
    except Exception as exc:  # noqa: BLE001 - tek noktadan HTTP'ye çevrilir
        raise _translate(exc)


@router.get("/{list_id}")
async def detail(list_id: str):
    item = coin_lists.get_list(list_id)
    if not item:
        raise HTTPException(404, "Coin listesi bulunamadı")
    return item


@router.put("/{list_id}")
async def update(list_id: str, body: CoinListUpdateBody):
    try:
        return coin_lists.update_list(list_id, body.name, body.coins)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc)


@router.delete("/{list_id}")
async def delete(list_id: str):
    try:
        coin_lists.delete_list(list_id)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc)
    return {"ok": True}


@router.post("/{list_id}/duplicate")
async def duplicate(list_id: str, body: Optional[DuplicateBody] = None):
    try:
        return coin_lists.duplicate_list(list_id, (body.name if body else None))
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc)
