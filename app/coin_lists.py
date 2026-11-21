"""Kullanıcı tanımlı coin listeleri.

Bir liste bir kez oluşturulur; tarama ve bot formlarında tek seçimle
kullanılabilir. Hazır (builtin) listeler silinemez/değiştirilemez, ancak
kopyalanarak düzenlenebilir.

Liste içeriği kayıt anında coin'lere çözülür: bot oluşturulurken dinlenecek
coinler sabitlenir, sonradan liste değişse bile çalışan botun evreni değişmez.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional

from app import db

COIN_RE = re.compile(r"^[A-Z0-9:._=]{2,40}$")
MAX_COINS = 500
MAX_NAME = 60

# Sistem listeleri. `id` sabittir; güncelleme yeni sürümlerde de korunur.
PRESETS: List[Dict[str, Any]] = [
    {
        "id": "list_top10",
        "name": "Top 10",
        "coins": [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
        ],
    },
    {
        "id": "list_layer1",
        "name": "Layer 1",
        "coins": [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT",
            "AVAXUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT", "SUIUSDT",
        ],
    },
    {
        "id": "list_l2_defi",
        "name": "DeFi & L2",
        "coins": [
            "UNIUSDT", "AAVEUSDT", "LINKUSDT", "MKRUSDT", "LDOUSDT",
            "CRVUSDT", "COMPUSDT", "SNXUSDT", "INJUSDT", "ARBUSDT",
        ],
    },
    {
        "id": "list_meme",
        "name": "Meme",
        "coins": [
            "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT",
            "FLOKIUSDT", "BONKUSDT", "BOMEUSDT",
        ],
    },
]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def normalize_coins(coins: Iterable[Any]) -> List[str]:
    """Büyük harfe çevirir, boşları atar, tekrarları temizler, sembolü doğrular."""
    out: List[str] = []
    seen = set()
    for raw in coins or []:
        coin = str(raw or "").strip().upper()
        if not coin or coin in seen:
            continue
        if not COIN_RE.match(coin):
            raise ValueError(f"Geçersiz coin sembolü: {coin}")
        seen.add(coin)
        out.append(coin)
    if len(out) > MAX_COINS:
        raise ValueError(f"Bir listede en fazla {MAX_COINS} coin olabilir")
    return out


def normalize_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValueError("Liste adı gerekli")
    if len(text) > MAX_NAME:
        raise ValueError(f"Liste adı en fazla {MAX_NAME} karakter olabilir")
    return text


def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
    coins = []
    try:
        parsed = json.loads(row.get("coins_json") or "[]")
        if isinstance(parsed, list):
            coins = [str(c) for c in parsed]
    except (TypeError, ValueError):
        coins = []
    return {
        "id": row["id"],
        "name": row["name"],
        "coins": coins,
        "count": len(coins),
        "builtin": bool(row.get("builtin")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _name_taken(name: str, exclude_id: Optional[str] = None) -> bool:
    item = db.row(
        "SELECT id FROM coin_lists WHERE lower(name)=lower(?) AND id<>?",
        (name, exclude_id or ""),
    )
    return bool(item)


def _require(list_id: str) -> Dict[str, Any]:
    item = get_list(list_id)
    if not item:
        raise LookupError("Coin listesi bulunamadı")
    return item


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def list_lists() -> List[Dict[str, Any]]:
    rows = db.rows(
        "SELECT * FROM coin_lists ORDER BY builtin DESC, lower(name) ASC"
    )
    return [_serialize(r) for r in rows]


def get_list(list_id: str) -> Optional[Dict[str, Any]]:
    if not list_id:
        return None
    row = db.row("SELECT * FROM coin_lists WHERE id=?", (list_id,))
    return _serialize(row) if row else None


def list_coins(list_id: str) -> Optional[List[str]]:
    """Listeyi coinlere çözer; liste yoksa ``None`` döner."""
    item = get_list(list_id)
    return list(item["coins"]) if item else None


def create_list(name: str, coins: Iterable[Any], builtin: bool = False) -> Dict[str, Any]:
    text = normalize_name(name)
    items = normalize_coins(coins)
    if not items:
        raise ValueError("Listeye en az bir coin eklenmeli")
    if _name_taken(text):
        raise ValueError(f"Bu isimde bir liste zaten var: {text}")
    now = db.utcnow()
    list_id = f"lst_{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO coin_lists(id,name,coins_json,builtin,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?)",
        (list_id, text, json.dumps(items, ensure_ascii=False), 1 if builtin else 0, now, now),
    )
    return _require(list_id)


def update_list(
    list_id: str,
    name: Optional[str] = None,
    coins: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    item = _require(list_id)
    if item["builtin"]:
        raise PermissionError("Hazır listeler değiştirilemez; kopyalayıp düzenleyin")
    text = normalize_name(name) if name is not None else item["name"]
    if _name_taken(text, exclude_id=list_id):
        raise ValueError(f"Bu isimde bir liste zaten var: {text}")
    items = normalize_coins(coins) if coins is not None else item["coins"]
    if not items:
        raise ValueError("Listeye en az bir coin eklenmeli")
    db.execute(
        "UPDATE coin_lists SET name=?, coins_json=?, updated_at=? WHERE id=?",
        (text, json.dumps(items, ensure_ascii=False), db.utcnow(), list_id),
    )
    return _require(list_id)


def duplicate_list(list_id: str, name: Optional[str] = None) -> Dict[str, Any]:
    item = _require(list_id)
    base = normalize_name(name) if name else f"{item['name']} (kopya)"
    # Aynı ad varsa numaralandır.
    candidate = base
    index = 2
    while _name_taken(candidate):
        candidate = f"{base} {index}"
        index += 1
        if index > 99:
            raise ValueError("Uygun bir liste adı bulunamadı")
    return create_list(candidate, item["coins"], builtin=False)


def delete_list(list_id: str) -> None:
    item = _require(list_id)
    if item["builtin"]:
        raise PermissionError("Hazır listeler silinemez")
    db.execute("DELETE FROM coin_lists WHERE id=?", (list_id,))


def ensure_presets() -> None:
    """Hazır listeleri eksikse ekler (mevcut kullanıcı listelerine dokunmaz)."""
    for preset in PRESETS:
        exists = db.row("SELECT id FROM coin_lists WHERE id=?", (preset["id"],))
        if exists:
            continue
        # Aynı adlı kullanıcı listesi varsa çakışmayı önle.
        if _name_taken(preset["name"]):
            continue
        now = db.utcnow()
        db.execute(
            "INSERT INTO coin_lists(id,name,coins_json,builtin,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                preset["id"],
                preset["name"],
                json.dumps(preset["coins"], ensure_ascii=False),
                1,
                now,
                now,
            ),
        )
