"""Database storage backend and hosting-friendly database URLs."""

import pytest

from app.config import normalize_database_url
from app.models import StoredObject
from app.services.storage import DatabaseEncryptedStorage


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///./axiom.db", "sqlite:///./axiom.db"),
    ],
)
def test_normalize_database_url(url, expected):
    assert normalize_database_url(url) == expected


def test_database_storage_roundtrip_is_encrypted(client):
    from app.db import SessionLocal

    storage = DatabaseEncryptedStorage(b"k" * 32)
    key = "org-test/doc-test/file.pdf"
    assert not storage.exists(key)
    with pytest.raises(FileNotFoundError):
        storage.get(key)

    storage.put(key, b"%PDF secret contents", "application/pdf")
    assert storage.exists(key)
    assert storage.get(key) == b"%PDF secret contents"
    with SessionLocal() as db:
        row = db.get(StoredObject, key)
        assert row.content_type == "application/pdf"
        assert b"secret" not in row.data  # stored encrypted

    storage.put(key, b"replaced", "text/plain")  # overwrite
    assert storage.get(key) == b"replaced"
    assert storage.signed_url(key, "file.pdf", "application/pdf").startswith("/api/files/")

    storage.delete(key)
    storage.delete(key)  # idempotent
    assert not storage.exists(key)
