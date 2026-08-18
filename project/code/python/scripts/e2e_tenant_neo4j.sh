#!/usr/bin/env bash
# P0-1 real Neo4j dual-tenant E2E entry.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RUN_NEO4J_E2E=1
export DISABLE_LOCAL_EMBEDDINGS="${DISABLE_LOCAL_EMBEDDINGS:-1}"
export REQUIRE_OPENAI_API_KEY="${REQUIRE_OPENAI_API_KEY:-false}"
export UPDATE_MODE="${UPDATE_MODE:-off}"
export WALL_TIMEOUT="${WALL_TIMEOUT:-180}"
exec bash scripts/run_unit_tests.sh tests/test_neo4j_tenant_e2e.py -vv "$@"
