from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.auth.store import AuthStore
from config import settings


def _client(tmp_path: Path, monkeypatch):
    db = tmp_path / "auth.db"
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_db_path", str(db))
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_username", "admin")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_password", "admin123")
    monkeypatch.setattr(settings, "update_mode", "off")
    monkeypatch.setattr(settings, "qa_checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "require_openai_api_key", False)

    from api.auth import deps as deps_mod
    from api.auth import router as router_mod
    from api.auth import store as store_mod
    from api import main as main_mod

    store = AuthStore(str(db))
    store.init()
    store_mod.auth_store = store
    main_mod.auth_store = store
    router_mod.auth_store = store
    deps_mod.auth_store = store

    async def _noop_init():
        return None

    async def _noop_close():
        return None

    monkeypatch.setattr(main_mod.vector_store, "init", _noop_init)
    monkeypatch.setattr(main_mod.knowledge_graph, "init", _noop_init)
    monkeypatch.setattr(main_mod.knowledge_graph, "close", _noop_close)

    return TestClient(main_mod.app)


def test_login_and_me(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        bad = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert bad.status_code == 401

        ok = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert ok.status_code == 200
        token = ok.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["username"] == "admin"
        assert me.json()["role"] == "admin"


def test_protected_routes_require_auth(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        assert client.post("/api/qa/ask", json={"question": "hi"}).status_code == 401
        assert client.get("/api/admin/stats").status_code == 401

        login = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        async def fake_stats():
            return {"backend": "chroma", "total_vectors": 0, "collection": "knowledge_chunks"}

        from api import main as main_mod

        monkeypatch.setattr(main_mod.vector_store, "get_stats", fake_stats)
        monkeypatch.setattr(main_mod.knowledge_graph, "get_stats", fake_stats)
        stats = client.get("/api/admin/stats", headers=headers)
        assert stats.status_code == 200
        assert stats.json()["vector_store"]["backend"] == "chroma"
