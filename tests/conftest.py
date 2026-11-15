"""Testlerin üretim veritabanına yazmasını engeller.

Her test, kendi geçici SQLite dosyasını kullanır; `Data/tradeai.db`'ye hiçbir
şey yazılmaz (daha önce testler üretim DB'sine "Dayanıklılık"/"Manuel test"
gibi sahte stratejiler eklemişti).
"""

import pytest

from app import db
from app.paths import paths


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    monkeypatch.setattr(db, "_WAL_READY", False)
    db.init_db()
    yield
