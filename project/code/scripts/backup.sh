#!/usr/bin/env bash
# 数据备份：Postgres + Neo4j dump（生产运维最小可用）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR:-$ROOT/backups}/$STAMP"
mkdir -p "$OUT"

echo "==> backup dir: $OUT"

if docker ps --format '{{.Names}}' | grep -qx agenthub-postgres; then
  echo "==> postgres dump"
  docker exec agenthub-postgres pg_dump -U postgres -d knowledge -Fc > "$OUT/knowledge.dump"
else
  echo "skip postgres (container agenthub-postgres not running)"
fi

if docker ps --format '{{.Names}}' | grep -qx agenthub-neo4j; then
  echo "==> neo4j dump (stop DB briefly inside container)"
  docker exec agenthub-neo4j bash -lc 'neo4j stop || true; neo4j-admin database dump neo4j --to-path=/backups || neo4j-admin dump --database=neo4j --to=/backups/neo4j.dump; neo4j start || true'
  docker cp agenthub-neo4j:/backups/. "$OUT/neo4j/" 2>/dev/null || true
else
  echo "skip neo4j (container agenthub-neo4j not running)"
fi

echo "==> done: $OUT"
ls -lah "$OUT" || true
