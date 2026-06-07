"""Unit 0 smoke tests: app imports, /health responds, storage seam works."""
import tempfile

from fastapi.testclient import TestClient

from app.main import app
from app.storage.local import LocalStorage

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_local_storage_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalStorage(tmp)
        assert store.exists("books/1/scene.txt") is False
        store.put("books/1/scene.txt", b"hello")
        assert store.exists("books/1/scene.txt") is True
        assert store.get("books/1/scene.txt") == b"hello"
