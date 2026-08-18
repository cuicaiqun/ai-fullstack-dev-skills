#!/usr/bin/env bash
# Fixed unit-test entry (ROADMAP v0.2-hardening).
# Prefer: conda env `agents` (Python 3.11, matches CI) or PYTHON_BIN override.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return
  fi
  # Local documented env (matches CI 3.11); skip on CI runners.
  if [[ -z "${GITHUB_ACTIONS:-}" && -x "/home/caiqun/miniconda3/envs/agents/bin/python" ]]; then
    echo "/home/caiqun/miniconda3/envs/agents/bin/python"
    return
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  command -v python3
}

PY="$(resolve_python)"
echo "[run_unit_tests] python=$PY ($("$PY" --version 2>&1))"

export REQUIRE_OPENAI_API_KEY="${REQUIRE_OPENAI_API_KEY:-false}"
export UPDATE_MODE="${UPDATE_MODE:-off}"
export AUTH_ENABLED="${AUTH_ENABLED:-true}"
export STATE_STORE_DSN="${STATE_STORE_DSN:-}"
export INGEST_QUEUE="${INGEST_QUEUE:-local}"
export APP_ENV="${APP_ENV:-development}"
export REQUIRE_STRONG_SECRETS="${REQUIRE_STRONG_SECRETS:-false}"
export DISABLE_LOCAL_EMBEDDINGS="${DISABLE_LOCAL_EMBEDDINGS:-1}"

# Outer wall-clock budget (seconds). pytest.ini also sets per-test timeout=60.
WALL_TIMEOUT="${WALL_TIMEOUT:-600}"

if [[ "$#" -eq 0 ]]; then
  set -- tests/
fi

if command -v timeout >/dev/null 2>&1; then
  exec timeout --foreground "$WALL_TIMEOUT" "$PY" -m pytest "$@"
else
  exec "$PY" -m pytest "$@"
fi
