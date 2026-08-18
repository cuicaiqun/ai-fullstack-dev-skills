from __future__ import annotations

from api.auth.acl import build_chroma_access_where, can_access_document
from api.auth.models import User
from api.auth.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("secret-pass")
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("secret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip(monkeypatch):
    monkeypatch.setattr("api.auth.security.settings.jwt_secret", "test-secret")
    monkeypatch.setattr("api.auth.security.settings.jwt_expire_minutes", 60)
    token = create_access_token("u1", "alice", "tenant-a", "member")
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["role"] == "member"


def test_acl_matrix():
    owner = User(user_id="u1", username="alice", tenant_id="t1", role="member")
    peer = User(user_id="u2", username="bob", tenant_id="t1", role="viewer")
    outsider = User(user_id="u3", username="eve", tenant_id="t2", role="member")
    admin = User(user_id="a1", username="admin", tenant_id="t1", role="admin")

    private_doc = {"visibility": "private", "owner_id": "u1", "tenant_id": "t1"}
    tenant_doc = {"visibility": "tenant", "owner_id": "u1", "tenant_id": "t1", "allowed_roles": "admin,member,viewer"}
    public_doc = {"visibility": "public", "owner_id": "u1", "tenant_id": "t1"}

    assert can_access_document(owner, private_doc)
    assert not can_access_document(peer, private_doc)
    assert can_access_document(peer, tenant_doc)
    assert not can_access_document(outsider, tenant_doc)
    assert can_access_document(outsider, public_doc)
    assert can_access_document(admin, private_doc)


def test_chroma_where_skipped_for_admin():
    admin = User(user_id="a1", username="admin", tenant_id="t1", role="admin")
    member = User(user_id="u1", username="alice", tenant_id="t1", role="member")
    assert build_chroma_access_where(admin) is None
    where = build_chroma_access_where(member)
    assert where["$or"]
