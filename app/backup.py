"""Yedekleme ve geri yükleme.

Yedek içeriği (varsayılan):
  * `tradeai.db`      — SQLite veritabanı (botlar, işlemler, stratejiler, ayarlar)
  * `Data/snapshots/` — regresyon testi kayıtları
  * `state/`          — bot çalışma durumları (açık pozisyon, nakit)
  * `Data/*.txt`, `Data/Strategy/` — coin listesi ve eski strateji dosyaları
  * `Log/bots/`        — bot log dosyaları (isteğe bağlı)

`.env` **varsayılan olarak yedeğe girmez** (API anahtarları içerir). İstenirse
`include_env=True` ile dahil edilebilir.

Geri yükleme güvenliği:
  * Önce tüm botlar durdurulur (çalışırken DB değiştirmek bozulmaya yol açar).
  * Mevcut veri, geri yükleme öncesi otomatik olarak `Data/backups/pre-restore_*.zip`
    olarak yedeklenir; böylece yanlış yedek seçilirse geri dönülebilir.
  * SQLite `-wal` / `-shm` dosyaları temizlenir.

Kullanım (CLI, container içinde):
    python -m app.backup create
    python -m app.backup list
    python -m app.backup restore <dosya.zip>

Yedekler `Data/backups/` altında tutulur (host'a mount edilen klasör), böylece
container yeniden oluşturulsa da kaybolmaz. Dışarı almak için:
    docker cp tradeai:/app/Data/backups/<dosya>.zip .
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.paths import BASE_DIR, paths

# Yedekler, host'a mount edilen `Data/` altında tutulur; container yeniden
# oluşturulduğunda (docker compose up) silinmez.
BACKUP_DIR = paths.data / "backups"
MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


# ---------------------------------------------------------------------------
# Yedek oluşturma
# ---------------------------------------------------------------------------
def _db_snapshot(dest: Path) -> None:
    """SQLite'ı tutarlı biçimde kopyalar (WAL dahil, yazma sürerken bile)."""
    source = sqlite3.connect(str(paths.db), timeout=30)
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".feather", ".h5", ".pkl"}
MAX_DATA_FILE_MB = 20


def _add_tree(
    zf: zipfile.ZipFile,
    root: Path,
    arc_prefix: str,
    skip: set[str],
    include_datasets: bool = False,
) -> List[str]:
    """Klasörü arşive ekler.

    Varsayılan olarak büyük veri dosyaları (.csv/.xlsx/.parquet, >20 MB) atlanır:
    `Data/` altında GB'lık geçmiş veri dökümleri olabiliyor ve bunlar yedeği
    kullanılamaz hâle getiriyordu.
    """
    added: List[str] = []
    if not root.exists():
        return added
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(root).parts):
            continue
        if not include_datasets:
            if path.suffix.lower() in DATA_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > MAX_DATA_FILE_MB * 1048576:
                    continue
            except OSError:
                continue
        arc = f"{arc_prefix}/{path.relative_to(root).as_posix()}"
        zf.write(path, arc)
        added.append(arc)
    return added


def create(
    note: str = "",
    include_logs: bool = False,
    include_env: bool = False,
    include_datasets: bool = False,
) -> Dict[str, Any]:
    """Yedek arşivi oluşturur ve meta bilgisini döndürür."""
    _dir()
    backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    target = _dir() / f"{backup_id}.zip"

    tmpdir = Path(tempfile.mkdtemp(prefix="tradeai_bak_"))
    files: List[str] = []
    try:
        db_copy = tmpdir / "tradeai.db"
        if paths.db.exists():
            _db_snapshot(db_copy)

        manifest = {
            "format": FORMAT_VERSION,
            "id": backup_id,
            "created_at": _now(),
            "note": note[:200],
            "app": "TradeAIBot",
            "includes": {
                "db": db_copy.exists(),
                "snapshots": (paths.data / "snapshots").exists(),
                "state": paths.state.exists(),
                "data_files": paths.data.exists(),
                "logs": bool(include_logs),
                "env": bool(include_env),
                "datasets": bool(include_datasets),
            },
        }

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            if db_copy.exists():
                zf.write(db_copy, "tradeai.db")
                files.append("tradeai.db")

            # Data: veritabanı ve snapshots ayrı ele alınır, kalan veri dosyaları.
            # `backups` atlanmalı: yedek klasörü Data içinde olduğu için arşiv
            # kendi kendini okumaya başlar (sonsuz büyüme).
            data_files = _add_tree(
                zf,
                paths.data,
                "Data",
                skip={"snapshots", "tradeai.db", BACKUP_DIR.name},
                include_datasets=include_datasets,
            )
            files.extend(data_files)

            files.extend(
                _add_tree(zf, paths.data / "snapshots", "Data/snapshots", skip=set())
            )
            files.extend(_add_tree(zf, paths.state, "state", skip=set()))
            if include_logs:
                files.extend(_add_tree(zf, paths.logs / "bots", "Log/bots", skip=set()))
            if include_env and (BASE_DIR / ".env").exists():
                zf.write(BASE_DIR / ".env", ".env")
                files.append(".env")

            manifest["file_count"] = len(set(files))
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=1))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    info = dict(manifest)
    info["size_mb"] = round(target.stat().st_size / 1048576, 2)
    info["path"] = target.name
    return info


# ---------------------------------------------------------------------------
# Listeleme / silme
# ---------------------------------------------------------------------------
def _read_manifest(path: Path) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            raw = zf.read(MANIFEST_NAME)
        return json.loads(raw.decode("utf-8"))
    except Exception:  # eski/bozuk arşiv: temel bilgi
        return {"id": path.stem, "created_at": None, "note": "", "file_count": None}


def list_backups() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for path in sorted(_dir().glob("*.zip"), reverse=True):
        meta = _read_manifest(path)
        meta["path"] = path.name
        meta["size_mb"] = round(path.stat().st_size / 1048576, 2)
        meta["kind"] = "pre-restore" if path.name.startswith("pre-restore") else "backup"
        items.append(meta)
    return items


def delete_backup(name: str) -> bool:
    path = _resolve(name)
    if not path.exists():
        return False
    path.unlink()
    return True


def _resolve(name: str) -> Path:
    """Arşiv adını güvenli biçimde yola çevirir (dizin dışına çıkış yok)."""
    clean = os.path.basename(str(name or ""))
    if not clean or clean != str(name) or not clean.endswith(".zip"):
        raise ValueError("Geçersiz yedek adı")
    path = (_dir() / clean).resolve()
    if _dir().resolve() not in path.parents:
        raise ValueError("Geçersiz yedek yolu")
    return path


# ---------------------------------------------------------------------------
# Geri yükleme
# ---------------------------------------------------------------------------
def _stop_all_bots() -> Dict[str, Any]:
    """Geri yükleme öncesi tüm botları durdurur (DB değişimi güvenli olsun)."""
    stopped: List[str] = []
    try:
        from app import db

        for bot in db.rows("SELECT id,name,status FROM bots"):
            try:
                from app.supervisor import supervisor

                supervisor.stop(bot["id"])
            except Exception:
                pass
            stopped.append(bot["name"] or bot["id"])
            try:
                db.execute(
                    "UPDATE bots SET status='stopped', pid=NULL, updated_at=? WHERE id=?",
                    (db.utcnow(), bot["id"]),
                )
            except Exception:
                pass
    except Exception:
        pass
    return {"stopped": stopped}


def _clear_sqlite_sidecars() -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        candidate = Path(str(paths.db) + suffix)
        try:
            candidate.unlink()
        except OSError:
            pass


def restore(name: str, make_safety_backup: bool = True) -> Dict[str, Any]:
    """Yedeği geri yükler. Önce güvenlik yedeği alır ve botları durdurur."""
    archive = _resolve(name)
    if not archive.exists():
        raise LookupError("Yedek bulunamadı")

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        if "tradeai.db" not in names and not any(n.startswith("Data/") for n in names):
            raise ValueError("Arşivde geri yüklenecek veri bulunamadı")
        # Zip-slip koruması
        for member in names:
            if member.startswith("/") or ".." in Path(member).parts:
                raise ValueError("Arşiv güvenli olmayan yol içeriyor")

        safety = None
        if make_safety_backup:
            safety = create(note=f"Geri yükleme öncesi otomatik yedek ({archive.name})")
            # Güvenlik yedeğini ayrı adla da işaretle (kopya yerine taşı:
            # aynı arşivin iki kopyası diskte durmasın).
            try:
                src = _dir() / safety["path"]
                dst = _dir() / f"pre-restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                shutil.move(str(src), str(dst))
                safety["safety_path"] = dst.name
            except Exception:
                pass

        bot_result = _stop_all_bots()
        _clear_sqlite_sidecars()

        restored: Dict[str, int] = {"db": 0, "data": 0, "snapshots": 0, "state": 0, "logs": 0, "env": 0}
        for member in names:
            if member == MANIFEST_NAME:
                continue
            if member == "tradeai.db":
                dest = paths.db
                bucket = "db"
            elif member == ".env":
                dest = BASE_DIR / ".env"
                bucket = "env"
            elif member.startswith("Data/snapshots/"):
                dest = paths.data / "snapshots" / member[len("Data/snapshots/"):]
                bucket = "snapshots"
            elif member.startswith("Data/"):
                dest = paths.data / member[len("Data/"):]
                bucket = "data"
            elif member.startswith("state/"):
                dest = paths.state / member[len("state/"):]
                bucket = "state"
            elif member.startswith("Log/bots/"):
                dest = paths.logs / "bots" / member[len("Log/bots/"):]
                bucket = "logs"
            else:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            restored[bucket] += 1

    # Yeni DB ile şemayı hazırla (eski yedeklerde eksik tablo olabilir)
    try:
        from app import db

        db.init_db()
        # Yedekteki botlar "running" görünse bile süreçleri yok; durdurulmuş işaretle.
        db.execute(
            "UPDATE bots SET status='stopped', pid=NULL WHERE status IN "
            "('running','stopping','error','reconciliation_required')"
        )
    except Exception:
        pass

    return {
        "ok": True,
        "restored_from": archive.name,
        "safety_backup": safety.get("safety_path") if safety else None,
        "files": restored,
        "bots_stopped": bot_result["stopped"],
        "restored_at": _now(),
        "note": "Botları Botlar sayfasından yeniden başlatın.",
    }


# ---------------------------------------------------------------------------
# Komut satırı: python -m app.backup <komut>
# ---------------------------------------------------------------------------
def _cli() -> int:
    import argparse
    import sys as _sys

    from app import db

    parser = argparse.ArgumentParser(prog="app.backup", description="TradeAIBot yedekleme")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Yeni yedek oluştur")
    p_create.add_argument("--note", default="")
    p_create.add_argument("--logs", action="store_true", help="Bot loglarını da ekle")
    p_create.add_argument("--env", action="store_true", help=".env dosyasını da ekle (API anahtarları!)")
    p_create.add_argument(
        "--datasets",
        action="store_true",
        help="Büyük veri dosyalarını (csv/xlsx/parquet, >20 MB) da ekle",
    )

    sub.add_parser("list", help="Yedekleri listele")
    sub.add_parser("where", help="Yedek klasörünü yazdır")

    p_restore = sub.add_parser("restore", help="Yedekten geri yükle")
    p_restore.add_argument("name")
    p_restore.add_argument("--no-safety", action="store_true", help="Güvenlik yedeği alma")

    p_delete = sub.add_parser("delete", help="Yedeği sil")
    p_delete.add_argument("name")

    args = parser.parse_args()
    try:
        db.init_db()
    except Exception:
        pass

    try:
        if args.command == "create":
            print(
                json.dumps(
                    create(args.note, args.logs, args.env, args.datasets),
                    ensure_ascii=False,
                    indent=1,
                )
            )
        elif args.command == "list":
            items = list_backups()
            if not items:
                print("Yedek yok.")
            for item in items:
                print(
                    f"{item['path']}  {item.get('created_at') or '-'}  "
                    f"{item.get('size_mb')} MB  {item.get('note') or ''}"
                )
        elif args.command == "where":
            print(_dir())
        elif args.command == "restore":
            print(
                json.dumps(
                    restore(args.name, make_safety_backup=not args.no_safety),
                    ensure_ascii=False,
                    indent=1,
                )
            )
        elif args.command == "delete":
            print("silindi" if delete_backup(args.name) else "bulunamadi")
    except Exception as exc:  # noqa: BLE001
        print(f"HATA: {exc}", file=_sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
