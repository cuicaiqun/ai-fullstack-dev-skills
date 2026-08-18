#!/usr/bin/env bash
# P0-2：真实依赖断存储联调入口。
# 会短暂 docker stop/start agenthub-chromadb / agenthub-neo4j。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RUN_STORAGE_E2E=1
# Real Chroma/Neo4j, but inject test embeddings in the suite (avoid ONNX/HF download hang).
export DISABLE_LOCAL_EMBEDDINGS="${DISABLE_LOCAL_EMBEDDINGS:-1}"
export CHROMA_HOST="${CHROMA_HOST:-localhost}"
export CHROMA_PORT="${CHROMA_PORT:-8000}"
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
export REQUIRE_OPENAI_API_KEY=false
export UPDATE_MODE=off
export WALL_TIMEOUT="${WALL_TIMEOUT:-300}"
exec bash scripts/run_unit_tests.sh tests/test_p0_2_storage_fault_e2e.py -vv "$@"
