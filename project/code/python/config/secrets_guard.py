"""
P0-3：生产密钥与弱口令门禁。

开发环境可保留演示默认值；APP_ENV=production 或 REQUIRE_STRONG_SECRETS=true 时拒绝弱配置启动。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

# 明确禁止出现在生产配置中的演示/占位值（大小写不敏感）
WEAK_SECRET_VALUES: frozenset[str] = frozenset(
    {
        "",
        "password",
        "postgres",
        "change-me-in-production",
        "admin123",
        "admin",
        "secret",
        "changeme",
        "123456",
        "root",
        "toor",
        "pass",
        "test",
        "demo",
        "neo4j",
        "chromadb",
        "redis",
        "sk-your-api-key-here",
    }
)

_DATASTORE_HOST_PORTS = frozenset(
    {
        "7474",  # Neo4j HTTP
        "7687",  # Neo4j Bolt
        "8000",  # Chroma
        "5432",  # Postgres
        "5433",  # Postgres published
        "6379",  # Redis
        "9092",  # Kafka
        "2181",  # Zookeeper
        "29092",  # Kafka host listener
    }
)


def _norm(value: str | None) -> str:
    return (value or "").strip()


def is_weak_secret(value: str | None, *, min_length: int = 12) -> bool:
    v = _norm(value)
    if v.lower() in WEAK_SECRET_VALUES:
        return True
    if len(v) < min_length:
        return True
    return False


def password_from_dsn(dsn: str | None) -> str:
    raw = _norm(dsn)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        return unquote(parsed.password or "")
    except Exception:
        return ""


def collect_secret_issues(settings: Any) -> list[str]:
    """返回人类可读的问题列表；空列表表示通过。"""
    issues: list[str] = []

    jwt = _norm(getattr(settings, "jwt_secret", None))
    if is_weak_secret(jwt, min_length=32):
        issues.append(
            "JWT_SECRET is weak or shorter than 32 characters "
            "(refuse defaults like change-me-in-production)"
        )

    neo4j_pw = _norm(getattr(settings, "neo4j_password", None))
    if is_weak_secret(neo4j_pw, min_length=12):
        issues.append("NEO4J_PASSWORD is weak or shorter than 12 characters")

    admin_pw = _norm(getattr(settings, "auth_bootstrap_admin_password", None))
    if is_weak_secret(admin_pw, min_length=12):
        issues.append("AUTH_BOOTSTRAP_ADMIN_PASSWORD is weak or shorter than 12 characters")
    admin_user = _norm(getattr(settings, "auth_bootstrap_admin_username", None))
    if admin_pw and admin_user and admin_pw.lower() == admin_user.lower():
        issues.append("AUTH_BOOTSTRAP_ADMIN_PASSWORD must not equal the admin username")

    for attr, label in (
        ("state_store_dsn", "STATE_STORE_DSN"),
        ("pgvector_dsn", "PGVECTOR_DSN"),
    ):
        dsn = _norm(getattr(settings, attr, None))
        if not dsn:
            continue
        pw = password_from_dsn(dsn)
        if pw and is_weak_secret(pw, min_length=12):
            issues.append(f"{label} embeds a weak database password")

    redis_url = _norm(getattr(settings, "redis_url", None))
    if redis_url:
        pw = password_from_dsn(redis_url)
        if pw and is_weak_secret(pw, min_length=12):
            issues.append("REDIS_URL embeds a weak password")

    return issues


def secrets_enforcement_enabled(settings: Any) -> bool:
    if bool(getattr(settings, "require_strong_secrets", False)):
        return True
    env = _norm(getattr(settings, "app_env", "development")).lower()
    return env in {"production", "prod"}


def enforce_secrets_or_raise(settings: Any) -> None:
    if not secrets_enforcement_enabled(settings):
        return
    issues = collect_secret_issues(settings)
    if not issues:
        return
    detail = "; ".join(issues)
    raise RuntimeError(
        "Refusing to start with insecure secrets in production mode "
        f"(APP_ENV={getattr(settings, 'app_env', '')!r}, "
        f"REQUIRE_STRONG_SECRETS={getattr(settings, 'require_strong_secrets', False)}): {detail}"
    )


_PORT_PUBLISH_RE = re.compile(
    r"""^\s*-\s*["']?(?:0\.0\.0\.0:|127\.0\.0\.1:|\[::\]:)?(\d{2,5}):""",
    re.MULTILINE,
)


def find_published_datastore_ports(compose_text: str) -> list[str]:
    """从 compose YAML 文本中找出对外发布的数据面端口（粗检，供 CI）。"""
    found: list[str] = []
    for match in _PORT_PUBLISH_RE.finditer(compose_text or ""):
        port = match.group(1)
        if port in _DATASTORE_HOST_PORTS:
            found.append(port)
    return sorted(set(found))


def find_literal_weak_secrets_in_text(text: str) -> list[str]:
    """检测配置文本中写死的弱口令字面量（忽略注释行）。"""
    hits: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lower = stripped.lower()
        for weak in WEAK_SECRET_VALUES:
            if not weak or len(weak) < 4:
                continue
            if weak in lower and any(
                key in lower
                for key in (
                    "password",
                    "secret",
                    "auth",
                    "postgres",
                    "jwt",
                    "neo4j_auth",
                )
            ):
                hits.append(f"{weak!r} in: {stripped[:120]}")
                break
    return hits
