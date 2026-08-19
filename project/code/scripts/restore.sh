#!/usr/bin/env bash
# 从 backup.sh 产出目录恢复 Postgres（Neo4j 需手工 neo4j-admin load）。
# Usage:
#   RESTORE_FROM=backups/20260819_120000 RESTORE_CONFIRM=1 bash scripts/restore.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${RESTORE_FROM:-}"
CONTAINER="${POSTGRES_CONTAINER:-agenthub-postgres}"
DB="${POSTGRES_DB:-knowledge}"
USER="${POSTGRES_USER:-postgres}"

if [[ -z "$SRC" ]]; then
  echo "Set RESTORE_FROM to a backup stamp directory (e.g. backups/20260819_120000)" >&2
  exit 1
fi

if [[ "$SRC" != /* ]]; then
  SRC="$ROOT/$SRC"
fi

DUMP="$SRC/knowledge.dump"
if [[ ! -f "$DUMP" ]]; then
  echo "missing $DUMP" >&2
  exit 1
fi

if [[ "${RESTORE_CONFIRM:-}" != "1" ]]; then
  echo "Refusing restore without RESTORE_CONFIRM=1 (destructive)." >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "postgres container $CONTAINER not running" >&2
  exit 1
fi

echo "==> restoring Postgres from $DUMP into $CONTAINER/$DB"
docker exec -i "$CONTAINER" psql -U "$USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid();" \
  2>/dev/null || true
docker exec -i "$CONTAINER" psql -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS \"$DB\";"
docker exec -i "$CONTAINER" psql -U "$USER" -d postgres -c "CREATE DATABASE \"$DB\";"
docker exec -i "$CONTAINER" pg_restore -U "$USER" -d "$DB" --no-owner --role="$USER" < "$DUMP"
echo "==> postgres restore done"

if [[ -d "$SRC/neo4j" ]] && ls "$SRC/neo4j"/* >/dev/null 2>&1; then
  echo "Neo4j artifacts present under $SRC/neo4j — load manually, e.g.:"
  echo "  docker cp $SRC/neo4j/. agenthub-neo4j:/backups/"
  echo "  docker exec agenthub-neo4j neo4j-admin database load neo4j --from-path=/backups/ ..."
fi
