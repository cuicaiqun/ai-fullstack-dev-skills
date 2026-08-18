#!/usr/bin/env python3
"""
P0-3 CI gate: reject weak secrets in production compose and published datastore ports.

Usage (repo root or code/):
  python code/python/scripts/check_p0_3_deploy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # enterprise-knowledge-agent-v2
CODE = ROOT / "code"
PY_ROOT = CODE / "python"
sys.path.insert(0, str(PY_ROOT))

from config.secrets_guard import (  # noqa: E402
    find_published_datastore_ports,
)


def main() -> int:
    compose_prod = CODE / "docker-compose.yml"
    compose_dev = CODE / "docker-compose.dev.yml"
    errors: list[str] = []

    if not compose_prod.is_file():
        errors.append(f"missing {compose_prod}")
    else:
        text = compose_prod.read_text(encoding="utf-8")
        ports = find_published_datastore_ports(text)
        # API gateway 8080 is allowed; datastore host publishes are not
        if ports:
            errors.append(
                f"{compose_prod.name} publishes datastore ports to the host: {ports}. "
                "Keep data plane internal; use docker-compose.dev.yml for local ports."
            )
        # Only flag weak *password default* patterns, not usernames like POSTGRES_USER:-postgres
        lowered = text.lower()
        if ":-password}" in lowered or "neo4j_password:-password" in lowered:
            errors.append("docker-compose.yml must not default NEO4J_PASSWORD to a weak value")
        if "postgres_password:-postgres" in lowered or "${postgres_password:-" in lowered:
            errors.append("docker-compose.yml must not default POSTGRES_PASSWORD to a weak value")
        if "jwt_secret:-change-me" in lowered or "admin123" in lowered:
            errors.append("docker-compose.yml must not embed demo JWT/admin secrets")
        if "8080:8080" not in text:
            errors.append("docker-compose.yml should publish only the API gateway (8080)")

    if compose_dev.is_file():
        # Dev overlay is allowed to publish ports; ensure it relaxes secret gate
        dev = compose_dev.read_text(encoding="utf-8")
        if "REQUIRE_STRONG_SECRETS" not in dev:
            errors.append("docker-compose.dev.yml should set REQUIRE_STRONG_SECRETS=false for local use")

    compose_tls = CODE / "docker-compose.tls.yml"
    if compose_tls.is_file():
        tls_text = compose_tls.read_text(encoding="utf-8")
        tls_ports = find_published_datastore_ports(tls_text)
        if tls_ports:
            errors.append(
                f"{compose_tls.name} publishes datastore ports: {tls_ports}. TLS overlay may only expose 8443."
            )
        if "8443:8443" not in tls_text:
            errors.append("docker-compose.tls.yml should publish HTTPS 8443")

    compose_tls = CODE / "docker-compose.tls.yml"
    if compose_tls.is_file():
        tls_text = compose_tls.read_text(encoding="utf-8")
        tls_ports = find_published_datastore_ports(tls_text)
        if tls_ports:
            errors.append(
                f"{compose_tls.name} must not publish datastore ports: {tls_ports}"
            )
        if "8443:8443" not in tls_text:
            errors.append("docker-compose.tls.yml should publish HTTPS terminator on 8443")

    if errors:
        print("P0-3 deploy check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("P0-3 deploy check OK: production compose has no datastore host ports / weak password defaults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
