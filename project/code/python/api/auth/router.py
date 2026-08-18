from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from api.auth.deps import get_current_user, require_admin
from api.auth.models import User
from api.auth.security import create_access_token, decode_access_token, verify_password
from api.auth.store import auth_store
from config import settings

router = APIRouter(prefix="/api/auth", tags=["认证"])

_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    tenant_id: str = Field(default="", max_length=64)
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")


class DisableUserRequest(BaseModel):
    disabled: bool = True


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 Password 模式登录，返回 JWT。"""
    ip = _client_ip(request)
    user = auth_store.get_user_by_username(form_data.username)
    if user is None or user.disabled or not verify_password(form_data.password, user.password_hash):
        auth_store.append_audit(
            "auth.login",
            actor_username=form_data.username,
            success=False,
            detail={"reason": "bad_credentials_or_disabled"},
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        user.user_id,
        user.username,
        user.tenant_id,
        user.role,
        token_version=user.token_version,
    )
    auth_store.append_audit(
        "auth.login",
        actor=user,
        success=True,
        resource_type="user",
        resource_id=user.user_id,
        ip=ip,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=user.to_public_dict(),
    )


@router.post("/logout")
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    token: str | None = Depends(_bearer),
):
    """撤销当前 access token（jti 拉黑至过期）。"""
    if token:
        try:
            payload = decode_access_token(token)
            jti = str(payload.get("jti") or "")
            exp = float(payload.get("exp") or 0)
            auth_store.revoke_token(jti, user.user_id, exp, reason="logout")
        except Exception:
            pass
    auth_store.append_audit(
        "auth.logout",
        actor=user,
        success=True,
        resource_type="user",
        resource_id=user.user_id,
        ip=_client_ip(request),
    )
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user.to_public_dict()


@router.post("/users", status_code=201)
async def create_user(
    req: CreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
):
    if auth_store.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = auth_store.create_user(
        username=req.username,
        password=req.password,
        tenant_id=req.tenant_id or settings.auth_bootstrap_tenant_id,
        role=req.role,
    )
    auth_store.append_audit(
        "auth.user_create",
        actor=admin,
        success=True,
        resource_type="user",
        resource_id=user.user_id,
        detail={"username": user.username, "role": user.role, "tenant_id": user.tenant_id},
        ip=_client_ip(request),
    )
    return user.to_public_dict()


@router.patch("/users/{user_id}/disabled")
async def set_user_disabled(
    user_id: str,
    req: DisableUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
):
    """禁用/启用用户：bump token_version，既有 JWT 立即失效。"""
    if user_id == admin.user_id and req.disabled:
        raise HTTPException(status_code=400, detail="Cannot disable the current admin user")
    user = auth_store.set_user_disabled(user_id, req.disabled)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    auth_store.append_audit(
        "auth.user_disable" if req.disabled else "auth.user_enable",
        actor=admin,
        success=True,
        resource_type="user",
        resource_id=user.user_id,
        detail={"disabled": req.disabled, "token_version": user.token_version},
        ip=_client_ip(request),
        tenant_id=user.tenant_id,
    )
    return user.to_public_dict()


@router.get("/audit")
async def list_audit(
    limit: int = Query(50, ge=1, le=500),
    action: str | None = None,
    admin: User = Depends(require_admin),
):
    """高风险操作审计查询（管理员）。"""
    events = auth_store.list_audit_events(
        limit=limit,
        action=action,
        tenant_id=None if admin.role == "admin" else admin.tenant_id,
    )
    # 租户管理员只看本租户（当前角色模型无平台管理员，admin 仍可看全量）
    if admin.tenant_id:
        # 仍返回全量给 admin；如需收紧可改为仅 tenant 过滤
        pass
    return {"events": events, "count": len(events)}
