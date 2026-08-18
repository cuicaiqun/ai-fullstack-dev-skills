from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from config.secrets_guard import (
    collect_secret_issues,
    enforce_secrets_or_raise,
    find_published_datastore_ports,
    is_weak_secret,
    password_from_dsn,
    secrets_enforcement_enabled,
)


def _settings(**kwargs):
    base = dict(
        app_env="development",
        require_strong_secrets=False,
        jwt_secret="change-me-in-production",
        neo4j_password="password",
        auth_bootstrap_admin_password="admin123",
        auth_bootstrap_admin_username="admin",
        state_store_dsn="postgresql://postgres:postgres@localhost:5432/knowledge",
        pgvector_dsn="",
        redis_url="redis://localhost:6379/0",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_is_weak_secret_detects_defaults():
    assert is_weak_secret("password")
    assert is_weak_secret("admin123")
    assert is_weak_secret("short")
    assert not is_weak_secret("a-sufficiently-long-secret-value")


def test_password_from_dsn():
    assert password_from_dsn("postgresql://u:s3cret-long-pass@host/db") == "s3cret-long-pass"
    assert password_from_dsn("") == ""


def test_collect_issues_for_demo_defaults():
    issues = collect_secret_issues(_settings())
    assert any("JWT_SECRET" in i for i in issues)
    assert any("NEO4J_PASSWORD" in i for i in issues)
    assert any("AUTH_BOOTSTRAP_ADMIN_PASSWORD" in i for i in issues)
    assert any("STATE_STORE_DSN" in i for i in issues)


def test_strong_settings_pass():
    strong = _settings(
        jwt_secret="x" * 32,
        neo4j_password="neo4j-strong-pass-1",
        auth_bootstrap_admin_password="admin-strong-pass-1",
        state_store_dsn="postgresql://postgres:db-strong-pass-1@localhost:5432/knowledge",
    )
    assert collect_secret_issues(strong) == []


def test_enforce_skipped_in_development():
    enforce_secrets_or_raise(_settings(app_env="development"))  # must not raise


def test_enforce_blocks_production_weak_config():
    with pytest.raises(RuntimeError, match="insecure secrets"):
        enforce_secrets_or_raise(_settings(app_env="production"))


def test_enforce_blocks_when_require_flag_set():
    with pytest.raises(RuntimeError, match="insecure secrets"):
        enforce_secrets_or_raise(_settings(require_strong_secrets=True))


def test_enforcement_flag_helpers():
    assert not secrets_enforcement_enabled(_settings())
    assert secrets_enforcement_enabled(_settings(app_env="prod"))
    assert secrets_enforcement_enabled(_settings(require_strong_secrets=True))


def test_compose_prod_has_no_datastore_host_ports():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")
    assert find_published_datastore_ports(text) == []
    assert "8080:8080" in text
    assert "NEO4J_PASSWORD:?NEO4J_PASSWORD" in text
    assert "POSTGRES_PASSWORD:?POSTGRES_PASSWORD" in text
