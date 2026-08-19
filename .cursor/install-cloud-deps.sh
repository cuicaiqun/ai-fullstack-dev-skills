#!/usr/bin/env bash
# Idempotent Cloud Agent install script (runs from repo root on each Build).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_DIR="$ROOT/project/code/python"

if [[ ! -f "$PY_DIR/requirements-cloud.txt" ]]; then
  echo "[cloud-install] ERROR: missing $PY_DIR/requirements-cloud.txt" >&2
  exit 1
fi

resolve_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  command -v python
}

PY="$(resolve_python)"
echo "[cloud-install] python=$PY ($("$PY" --version 2>&1))"

# User-site installs avoid permission issues when running as `ubuntu`.
export PIP_USER=1
export PYTHONPATH="${HOME}/.local/lib/python3.12/site-packages:${HOME}/.local/lib/python3.11/site-packages:${PYTHONPATH:-}"

"$PY" -m pip install -U pip wheel setuptools
"$PY" -m pip install -r "$PY_DIR/requirements-cloud.txt" -r "$PY_DIR/requirements-test.txt"

if [[ ! -f "$PY_DIR/.env" && -f "$PY_DIR/.env.example" ]]; then
  cp "$PY_DIR/.env.example" "$PY_DIR/.env"
  echo "[cloud-install] created project/code/python/.env from .env.example"
fi

echo "[cloud-install] dependencies ready under $PY_DIR (lean cloud set; no torch)"
