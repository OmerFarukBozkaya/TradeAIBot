"""Yedekleme ve geri yükleme testleri."""

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app import backup, db
from app.paths import paths


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "Data" / "tradeai.db")
    monkeypatch.setattr(paths, "data", tmp_path / "Data")
    monkeypatch.setattr(paths, "state", tmp_path / "state")
    monkeypatch.setattr(paths, "logs", tmp_path / "Log")
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "BASE_DIR", tmp_path)
    paths.data.mkdir(parents=True, exist_ok=True)
    paths.state.mkdir(parents=True, exist_ok=True)
    db.init_db()
    # Gerçekçi içerik
    db.execute(
        "INSERT INTO bots(id,name,type,mode,period,config_json,status,auto_restart,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("bot_a", "Test Bot", "trade", "paper", "1h", "{}", "stopped", 1, db.utcnow(), db.utcnow()),
    )
    (paths.data / "coin_list.txt").write_text("BTCUSDT,ETHUSDT", encoding="utf-8")
    (paths.data / ".secret_key").write_text("test-secret-key", encoding="utf-8")
    (paths.data / "Strategy").mkdir(parents=True, exist_ok=True)
    (paths.data / "Strategy" / "strategys.json").write_text("{}", encoding="utf-8")
    (paths.data / "snapshots").mkdir(parents=True, exist_ok=True)
    (paths.data / "snapshots" / "snap_x.json.gz").write_bytes(b"fake")
    (paths.data / "Model").mkdir(parents=True, exist_ok=True)
    (paths.data / "Model" / "model.keras").write_bytes(b"model")
    (paths.data / "esra.py").write_text("print('x')", encoding="utf-8")
    (paths.state / "bot_a.json").write_text('{"cash": 100}', encoding="utf-8")
    (paths.state / "bot_orphan.json").write_text('{"cash": 5}', encoding="utf-8")
    yield tmp_path


def test_create_archive_contents():
    info = backup.create(note="ilk yedek")
    path = backup.BACKUP_DIR / info["path"]
    assert path.exists()
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        # Zorunlu: DB (botlar, stratejiler, ayarlar, coin listeleri) + anahtar + küçük dosyalar
        assert "tradeai.db" in names
        assert "manifest.json" in names
        assert "Data/.secret_key" in names
        assert "Data/coin_list.txt" in names
        assert "Data/Strategy/strategys.json" in names
        # Sadece mevcut botun durumu
        assert "state/bot_a.json" in names
        assert "state/bot_orphan.json" not in names
        # Gereksizler varsayılan olarak girmez
        assert not any(n.startswith("Data/snapshots/") for n in names)
        assert "Data/Model/model.keras" not in names
        assert not any("esra" in n for n in names)
        assert ".env" not in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["note"] == "ilk yedek"
        assert manifest["format"] == backup.FORMAT_VERSION
        assert manifest["scope"] == "minimal"
        assert manifest["includes"]["db"] is True
        assert manifest["includes"]["secret_key"] is True
        assert manifest["includes"]["state"] == 1
        assert manifest["includes"]["snapshots"] is False


def test_optional_extras_only_when_requested():
    info = backup.create(include_snapshots=True, include_models=True)
    with zipfile.ZipFile(backup.BACKUP_DIR / info["path"]) as zf:
        names = set(zf.namelist())
        assert "Data/snapshots/snap_x.json.gz" in names
        assert "Data/Model/model.keras" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["includes"]["snapshots"] is True
        assert manifest["includes"]["models"] is True


def test_datasets_only_include_data_extensions():
    (paths.data / "BTC.csv").write_text("a,b\n1,2", encoding="utf-8")
    info = backup.create(include_datasets=True)
    with zipfile.ZipFile(backup.BACKUP_DIR / info["path"]) as zf:
        names = set(zf.namelist())
        assert "Data/BTC.csv" in names
        # datasets seçeneği rastgele dosyaları veya modelleri içeri almamalı
        assert not any("esra" in n for n in names)
        assert "Data/Model/model.keras" not in names


def test_db_in_archive_is_readable_and_consistent():
    info = backup.create()
    path = backup.BACKUP_DIR / info["path"]
    with zipfile.ZipFile(path) as zf:
        target = backup.BACKUP_DIR / "extracted.db"
        target.write_bytes(zf.read("tradeai.db"))
    conn = sqlite3.connect(str(target))
    try:
        rows = conn.execute("SELECT name FROM bots").fetchall()
        assert rows == [("Test Bot",)]
    finally:
        conn.close()


def test_list_and_delete():
    info = backup.create()
    items = backup.list_backups()
    assert any(i["path"] == info["path"] for i in items)
    assert backup.delete_backup(info["path"]) is True
    assert backup.delete_backup(info["path"]) is False


def test_backups_are_not_nested_in_new_archives():
    """Yedek klasörü Data içinde; yeni arşiv kendi kendini içermemeli."""
    first = backup.create(note="bir")
    second = backup.create(note="iki")
    assert second["size_mb"] < 50, "yeni yedek önceki yedeği içine alıyor"
    with zipfile.ZipFile(backup.BACKUP_DIR / second["path"]) as zf:
        names = zf.namelist()
    assert not any(n.startswith("Data/backups/") for n in names)
    assert all(first["path"] not in n for n in names)


def test_restore_replaces_data_and_makes_safety_backup():
    info = backup.create(note="eski durum")
    # Veriyi boz
    db.execute("DELETE FROM bots")
    (paths.data / "coin_list.txt").write_text("SOLUSDT", encoding="utf-8")

    result = backup.restore(info["path"])
    assert result["ok"] is True
    assert result["safety_backup"], "geri yükleme öncesi güvenlik yedeği alınmalı"
    assert (backup.BACKUP_DIR / result["safety_backup"]).exists()
    # Güvenlik yedeği kopya değil taşınmış olmalı: 2 arşiv (asıl + pre-restore).
    assert len(list(backup.BACKUP_DIR.glob("*.zip"))) == 2

    names = [row["name"] for row in db.rows("SELECT name FROM bots")]
    assert names == ["Test Bot"]
    assert (paths.data / "coin_list.txt").read_text(encoding="utf-8").startswith("BTCUSDT")
    assert (paths.state / "bot_a.json").exists()


def test_restore_without_safety_backup():
    info = backup.create()
    result = backup.restore(info["path"], make_safety_backup=False)
    assert result["safety_backup"] is None
    assert result["ok"] is True


def test_restore_stops_running_bots(monkeypatch):
    db.execute("UPDATE bots SET status='running', pid=1 WHERE id='bot_a'")
    info = backup.create()
    stopped = []
    monkeypatch.setattr("app.supervisor.supervisor.stop", lambda bot_id: stopped.append(bot_id))
    result = backup.restore(info["path"], make_safety_backup=False)
    assert "bot_a" in stopped
    assert result["bots_stopped"]
    status = db.row("SELECT status FROM bots WHERE id='bot_a'")["status"]
    assert status == "stopped"


def test_rejects_path_traversal():
    with pytest.raises(ValueError):
        backup._resolve("../etc/passwd")
    with pytest.raises(ValueError):
        backup._resolve("sub/dir/x.zip")
    with pytest.raises(ValueError):
        backup._resolve("x.txt")


def test_restore_rejects_zip_slip(tmp_path):
    bad = backup.BACKUP_DIR / "bad.zip"
    backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    with pytest.raises(ValueError):
        backup.restore("bad.zip", make_safety_backup=False)


def test_restore_missing_archive():
    with pytest.raises(LookupError):
        backup.restore("yok.zip")


def test_env_only_when_requested(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SECRET=1", encoding="utf-8")
    info = backup.create(include_env=True)
    with zipfile.ZipFile(backup.BACKUP_DIR / info["path"]) as zf:
        assert ".env" in zf.namelist()
    assert (backup.BACKUP_DIR / info["path"]).exists()


# ---------------------------------------------------------------------------
# Tarayıcıdan yükleme (Data/backups/upload)
# ---------------------------------------------------------------------------
def _zip_bytes(entries):
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_upload_saves_valid_archive_in_chunks():
    data = _zip_bytes({"tradeai.db": b"SQLite format 3\x00", "manifest.json": b"{}"})
    info = backup.save_upload("uploaded.zip", [data[:10], data[10:20], data[20:]])
    assert info["path"] == "uploaded.zip"
    assert info["size_mb"] >= 0
    target = backup.BACKUP_DIR / "uploaded.zip"
    assert target.exists()
    assert backup.list_backups()[0]["path"] == "uploaded.zip"
    assert not list(backup.BACKUP_DIR.glob("*.part"))


def test_upload_rejects_existing_name():
    info = backup.create()
    data = _zip_bytes({"tradeai.db": b"x"})
    with pytest.raises(FileExistsError):
        backup.save_upload(info["path"], [data])
    # Mevcut arşiv bozulmamalı
    assert (backup.BACKUP_DIR / info["path"]).exists()


def test_upload_rejects_invalid_and_empty():
    with pytest.raises(ValueError):
        backup.save_upload("bad.zip", [b"not a zip"])
    with pytest.raises(ValueError):
        backup.save_upload("empty.zip", [])
    assert not (backup.BACKUP_DIR / "bad.zip").exists()
    assert not list(backup.BACKUP_DIR.glob("*.part"))


def test_upload_rejects_archive_without_data():
    data = _zip_bytes({"foo.txt": b"x"})
    with pytest.raises(ValueError):
        backup.save_upload("nope.zip", [data])
    assert not (backup.BACKUP_DIR / "nope.zip").exists()


def test_upload_size_limit():
    with pytest.raises(ValueError):
        backup.save_upload("big.zip", [b"x" * (1024 * 1024 + 10)], max_mb=1)
    assert not (backup.BACKUP_DIR / "big.zip").exists()
    assert not list(backup.BACKUP_DIR.glob("*.part"))


def test_upload_rejects_path_traversal():
    data = _zip_bytes({"tradeai.db": b"x"})
    with pytest.raises(ValueError):
        backup.save_upload("../evil.zip", [data])
