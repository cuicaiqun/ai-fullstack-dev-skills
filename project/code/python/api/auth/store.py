from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from api.auth.models import DocumentACL, User
from api.auth.security import hash_password
from config import settings


class AuthStore:
    """SQLite 用户 / 文档 ACL / token 撤销 / 审计（P0-4）。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.auth_db_path
        self._lock = threading.Lock()
        self._initialized = False

    def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        tenant_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        disabled INTEGER NOT NULL DEFAULT 0,
                        token_version INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS document_acl (
                        doc_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        visibility TEXT NOT NULL,
                        allowed_roles TEXT NOT NULL,
                        source_path TEXT NOT NULL DEFAULT ''
                    );
                    CREATE TABLE IF NOT EXISTS revoked_tokens (
                        jti TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL DEFAULT '',
                        expires_at REAL NOT NULL,
                        revoked_at REAL NOT NULL,
                        reason TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_revoked_tokens_exp
                        ON revoked_tokens (expires_at);
                    CREATE TABLE IF NOT EXISTS audit_events (
                        event_id TEXT PRIMARY KEY,
                        ts REAL NOT NULL,
                        action TEXT NOT NULL,
                        actor_user_id TEXT NOT NULL DEFAULT '',
                        actor_username TEXT NOT NULL DEFAULT '',
                        tenant_id TEXT NOT NULL DEFAULT '',
                        resource_type TEXT NOT NULL DEFAULT '',
                        resource_id TEXT NOT NULL DEFAULT '',
                        success INTEGER NOT NULL DEFAULT 1,
                        detail_json TEXT NOT NULL DEFAULT '{}',
                        ip TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_audit_events_ts
                        ON audit_events (ts DESC);
                    CREATE INDEX IF NOT EXISTS idx_audit_events_action
                        ON audit_events (action, ts DESC);
                    """
                )
                self._migrate(conn)
                conn.commit()
                self._ensure_bootstrap_admin(conn)
                self._initialized = True
            finally:
                conn.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "token_version" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_bootstrap_admin(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT user_id FROM users WHERE username = ?",
            (settings.auth_bootstrap_admin_username,),
        ).fetchone()
        if row:
            return
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users
                (user_id, username, tenant_id, role, password_hash, disabled, token_version)
            VALUES (?, ?, ?, 'admin', ?, 0, 0)
            """,
            (
                user_id,
                settings.auth_bootstrap_admin_username,
                settings.auth_bootstrap_tenant_id,
                hash_password(settings.auth_bootstrap_admin_password),
            ),
        )
        conn.commit()

    def get_user_by_username(self, username: str) -> User | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
                return self._row_to_user(row) if row else None
            finally:
                conn.close()

    def get_user_by_id(self, user_id: str) -> User | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM users WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                return self._row_to_user(row) if row else None
            finally:
                conn.close()

    def create_user(
        self,
        username: str,
        password: str,
        tenant_id: str,
        role: str = "member",
    ) -> User:
        user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            tenant_id=tenant_id,
            role=role,
            password_hash=hash_password(password),
            token_version=0,
        )
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO users
                        (user_id, username, tenant_id, role, password_hash, disabled, token_version)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                    """,
                    (
                        user.user_id,
                        user.username,
                        user.tenant_id,
                        user.role,
                        user.password_hash,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return user

    def list_users(self, *, tenant_id: str | None = None) -> list[User]:
        """List users; when tenant_id set, restrict to that tenant."""
        with self._lock:
            conn = self._connect()
            try:
                if tenant_id:
                    rows = conn.execute(
                        "SELECT * FROM users WHERE tenant_id = ? ORDER BY username",
                        (tenant_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM users ORDER BY username"
                    ).fetchall()
                return [self._row_to_user(row) for row in rows]
            finally:
                conn.close()

    def set_user_disabled(self, user_id: str, disabled: bool) -> User | None:
        """禁用/启用用户并 bump token_version，使既有 JWT 立即失效。"""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE users
                    SET disabled = ?,
                        token_version = token_version + 1
                    WHERE user_id = ?
                    """,
                    (1 if disabled else 0, user_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return self._row_to_user(row) if row else None
            finally:
                conn.close()

    def bump_token_version(self, user_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE users
                    SET token_version = token_version + 1
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT token_version FROM users WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

    def revoke_token(self, jti: str, user_id: str, expires_at: float, reason: str = "") -> None:
        if not jti:
            return
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO revoked_tokens
                        (jti, user_id, expires_at, revoked_at, reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (jti, user_id or "", float(expires_at), now, reason or ""),
                )
                # 清理过期撤销记录
                conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now,))
                conn.commit()
            finally:
                conn.close()

    def is_token_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT jti FROM revoked_tokens
                    WHERE jti = ? AND expires_at >= ?
                    """,
                    (jti, now),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def append_audit(
        self,
        action: str,
        *,
        actor: User | None = None,
        actor_user_id: str = "",
        actor_username: str = "",
        tenant_id: str = "",
        resource_type: str = "",
        resource_id: str = "",
        success: bool = True,
        detail: dict[str, Any] | None = None,
        ip: str = "",
    ) -> str:
        event_id = str(uuid.uuid4())
        if actor is not None:
            actor_user_id = actor.user_id
            actor_username = actor.username
            tenant_id = tenant_id or actor.tenant_id
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, ts, action, actor_user_id, actor_username, tenant_id,
                        resource_type, resource_id, success, detail_json, ip
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        time.time(),
                        action,
                        actor_user_id,
                        actor_username,
                        tenant_id,
                        resource_type,
                        resource_id,
                        1 if success else 0,
                        json.dumps(detail or {}, ensure_ascii=False),
                        ip or "",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return event_id

    def list_audit_events(
        self,
        *,
        limit: int = 50,
        action: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        clauses = ["1=1"]
        params: list[Any] = []
        if action:
            clauses.append("action = ?")
            params.append(action)
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        params.append(limit)
        sql = f"""
            SELECT * FROM audit_events
            WHERE {' AND '.join(clauses)}
            ORDER BY ts DESC
            LIMIT ?
        """
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                out: list[dict[str, Any]] = []
                for row in rows:
                    out.append(
                        {
                            "event_id": row["event_id"],
                            "ts": row["ts"],
                            "action": row["action"],
                            "actor_user_id": row["actor_user_id"],
                            "actor_username": row["actor_username"],
                            "tenant_id": row["tenant_id"],
                            "resource_type": row["resource_type"],
                            "resource_id": row["resource_id"],
                            "success": bool(row["success"]),
                            "detail": json.loads(row["detail_json"] or "{}"),
                            "ip": row["ip"],
                        }
                    )
                return out
            finally:
                conn.close()

    def upsert_document_acl(self, acl: DocumentACL) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO document_acl
                        (doc_id, tenant_id, owner_id, visibility, allowed_roles, source_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        tenant_id=excluded.tenant_id,
                        owner_id=excluded.owner_id,
                        visibility=excluded.visibility,
                        allowed_roles=excluded.allowed_roles,
                        source_path=excluded.source_path
                    """,
                    (
                        acl.doc_id,
                        acl.tenant_id,
                        acl.owner_id,
                        acl.visibility,
                        json.dumps(acl.allowed_roles, ensure_ascii=False),
                        acl.source_path,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_document_acl(self, doc_id: str) -> DocumentACL | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM document_acl WHERE doc_id = ?",
                    (doc_id,),
                ).fetchone()
                if not row:
                    return None
                return DocumentACL(
                    doc_id=row["doc_id"],
                    tenant_id=row["tenant_id"],
                    owner_id=row["owner_id"],
                    visibility=row["visibility"],
                    allowed_roles=json.loads(row["allowed_roles"] or "[]"),
                    source_path=row["source_path"] or "",
                )
            finally:
                conn.close()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        keys = row.keys()
        return User(
            user_id=row["user_id"],
            username=row["username"],
            tenant_id=row["tenant_id"],
            role=row["role"],
            password_hash=row["password_hash"],
            disabled=bool(row["disabled"]),
            token_version=int(row["token_version"]) if "token_version" in keys else 0,
        )


auth_store = AuthStore()
