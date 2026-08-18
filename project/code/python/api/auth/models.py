from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class User:
    user_id: str
    username: str
    tenant_id: str
    role: str  # admin | member | viewer
    password_hash: str = ""
    disabled: bool = False
    token_version: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "disabled": self.disabled,
        }


@dataclass
class DocumentACL:
    doc_id: str
    tenant_id: str
    owner_id: str
    visibility: str = "tenant"  # private | tenant | public
    allowed_roles: list[str] = field(default_factory=lambda: ["admin", "member", "viewer"])
    source_path: str = ""

    def to_chunk_metadata(self) -> dict[str, str]:
        """Chroma 仅支持标量 metadata，角色用逗号拼接。"""
        return {
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "visibility": self.visibility,
            "allowed_roles": ",".join(self.allowed_roles),
            "doc_id": self.doc_id,
            "source_path": self.source_path or "",
        }
