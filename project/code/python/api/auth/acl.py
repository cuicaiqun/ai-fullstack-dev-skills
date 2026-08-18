from __future__ import annotations

from typing import Any

from api.auth.models import User


def can_access_document(user: User, metadata: dict[str, Any] | None) -> bool:
    """文档级 ACL：admin 全开；否则按 visibility / owner / tenant / role 判定。"""
    if user.role == "admin":
        return True
    meta = metadata or {}
    visibility = str(meta.get("visibility") or "tenant")
    owner_id = str(meta.get("owner_id") or "")
    tenant_id = str(meta.get("tenant_id") or "")
    allowed_roles_raw = str(meta.get("allowed_roles") or "")
    allowed_roles = {r.strip() for r in allowed_roles_raw.split(",") if r.strip()}

    if owner_id and owner_id == user.user_id:
        return True
    if visibility == "public":
        return True
    if visibility == "private":
        return False
    if visibility == "tenant":
        if tenant_id and tenant_id != user.tenant_id:
            return False
        if allowed_roles and user.role not in allowed_roles:
            return False
        return True
    return False


def build_chroma_access_where(user: User) -> dict[str, Any] | None:
    """
    生成 Chroma where 过滤。admin 不过滤。
    注意：Chroma 对复杂 $or 支持因版本而异；调用方仍应做后置 can_access 校验。
    """
    if user.role == "admin":
        return None
    return {
        "$or": [
            {"visibility": "public"},
            {"owner_id": user.user_id},
            {
                "$and": [
                    {"visibility": "tenant"},
                    {"tenant_id": user.tenant_id},
                ]
            },
        ]
    }


def filter_contexts_by_acl(user: User, contexts: list[Any]) -> list[Any]:
    """过滤 RetrievedContext / 带 metadata 的检索结果。"""
    kept = []
    for ctx in contexts:
        metadata = getattr(ctx, "metadata", None)
        if metadata is None and isinstance(ctx, dict):
            metadata = ctx.get("metadata") or {}
        if can_access_document(user, metadata or {}):
            kept.append(ctx)
    return kept
