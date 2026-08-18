"""P0-4：禁用立即生效、token 撤销、审计、持久 checkpointer。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, TypedDict

from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from api.auth.security import create_access_token
from api.auth.store import AuthStore
from config import settings
from services.qa_checkpoint import close_qa_checkpointer, init_qa_checkpointer


def _patch_auth_store(tmp_path: Path, monkeypatch):
    db = tmp_path / "auth.db"
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_db_path", str(db))
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret-32chars-min!!")
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
    return store, main_mod


def test_disable_user_invalidates_existing_token(tmp_path, monkeypatch):
    store, main_mod = _patch_auth_store(tmp_path, monkeypatch)
    with TestClient(main_mod.app) as client:
        login = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200
        admin_token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        created = client.post(
            "/api/auth/users",
            headers=headers,
            json={"username": "bob", "password": "bob-secret", "role": "member"},
        )
        assert created.status_code == 201
        bob_id = created.json()["user_id"]

        bob_login = client.post(
            "/api/auth/login",
            data={"username": "bob", "password": "bob-secret"},
        )
        bob_token = bob_login.json()["access_token"]
        bob_headers = {"Authorization": f"Bearer {bob_token}"}
        assert client.get("/api/auth/me", headers=bob_headers).status_code == 200

        disabled = client.patch(
            f"/api/auth/users/{bob_id}/disabled",
            headers=headers,
            json={"disabled": True},
        )
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True

        me = client.get("/api/auth/me", headers=bob_headers)
        assert me.status_code == 401
        assert me.json()["detail"] in {"User disabled", "Token revoked"}


def test_logout_revokes_jti(tmp_path, monkeypatch):
    store, main_mod = _patch_auth_store(tmp_path, monkeypatch)
    with TestClient(main_mod.app) as client:
        login = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200

        out = client.post("/api/auth/logout", headers=headers)
        assert out.status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401

        from api.auth.security import decode_access_token

        payload = decode_access_token(token)
        assert store.is_token_revoked(str(payload["jti"]))


def test_audit_records_login_and_user_create(tmp_path, monkeypatch):
    _, main_mod = _patch_auth_store(tmp_path, monkeypatch)
    with TestClient(main_mod.app) as client:
        client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "wrong"},
        )
        ok = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        token = ok.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/auth/users",
            headers=headers,
            json={"username": "carol", "password": "carol-pass", "role": "viewer"},
        )
        audit = client.get("/api/auth/audit", headers=headers)
        assert audit.status_code == 200
        actions = {e["action"] for e in audit.json()["events"]}
        assert "auth.login" in actions
        assert "auth.user_create" in actions
        failed = [
            e for e in audit.json()["events"] if e["action"] == "auth.login" and not e["success"]
        ]
        assert failed


def test_sqlite_checkpointer_persists_across_reinit(tmp_path, monkeypatch):
    path = tmp_path / "ckpt.sqlite"
    monkeypatch.setattr(settings, "qa_checkpoint_backend", "sqlite")
    monkeypatch.setattr(settings, "qa_checkpoint_path", str(path))

    class S(TypedDict):
        messages: Annotated[list, add_messages]

    def node(state: S):
        return {"messages": [HumanMessage(content="hi")]}

    g = StateGraph(S)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    config = {"configurable": {"thread_id": "u1:s-persist"}}

    async def _run():
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        await close_qa_checkpointer()
        ckpt = await init_qa_checkpointer()
        assert isinstance(ckpt, AsyncSqliteSaver)
        app = g.compile(checkpointer=ckpt)
        await app.ainvoke({"messages": []}, config=config)
        await close_qa_checkpointer()

        ckpt2 = await init_qa_checkpointer()
        app2 = g.compile(checkpointer=ckpt2)
        state = await app2.aget_state(config)
        assert state.values.get("messages")
        await close_qa_checkpointer()

    asyncio.run(_run())


def test_token_version_mismatch_rejected(tmp_path, monkeypatch):
    store = AuthStore(str(tmp_path / "a.db"))
    store.init()
    user = store.create_user("dave", "dave-pass-1", "t1", "member")
    token = create_access_token(
        user.user_id,
        user.username,
        user.tenant_id,
        user.role,
        token_version=user.token_version,
    )
    store.bump_token_version(user.user_id)

    from api.auth import deps as deps_mod

    monkeypatch.setattr(deps_mod, "auth_store", store)
    monkeypatch.setattr(deps_mod.settings, "auth_enabled", True)

    async def _run():
        try:
            await deps_mod.get_current_user(token)
            raise AssertionError("should reject")
        except HTTPException as exc:
            assert exc.status_code == 401
            assert "revoked" in str(exc.detail).lower()

    asyncio.run(_run())
