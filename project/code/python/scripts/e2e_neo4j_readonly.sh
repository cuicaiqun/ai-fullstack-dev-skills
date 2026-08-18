#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RUN_NEO4J_READONLY_E2E=1
export REQUIRE_OPENAI_API_KEY=false
export UPDATE_MODE=off
export WALL_TIMEOUT="${WALL_TIMEOUT:-180}"
: "${NEO4J_READ_USER:?set NEO4J_READ_USER}"
: "${NEO4J_READ_PASSWORD:?set NEO4J_READ_PASSWORD}"
exec bash scripts/run_unit_tests.sh tests/test_neo4j_readonly_e2e.py -vv "$@"
