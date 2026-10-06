"""Fixtures partagées : base SQLite temporaire (la vraie base n'est jamais touchée)."""
import pytest

from app import db, search


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    monkeypatch.setitem(search._cache, "metas", None)  # l'index mémoire est reconstruit depuis la base de test
    monkeypatch.setitem(search._cache, "mat", None)
    return tmp_path
