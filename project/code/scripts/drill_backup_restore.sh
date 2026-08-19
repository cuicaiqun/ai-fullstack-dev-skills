#!/usr/bin/env bash
# P1-4：备份 + 校验 + 可选 Postgres 恢复到临时库演练
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== P1-4 Step 1: backup ==="
bash scripts/backup.sh

STAMP="$(ls -1dt backups/*/ 2>/dev/null | head -1 | xargs basename)"
OUT="${BACKUP_DIR:-$ROOT/backups}/$STAMP"
echo "Latest backup: $OUT"

errors=0

if [[ -f "$OUT/knowledge.dump" ]]; then
  size=$(stat -c%s "$OUT/knowledge.dump" 2>/dev/null || stat -f%z "$OUT/knowledge.dump")
  if [[ "$size" -lt 100 ]]; then
    echo "FAIL: knowledge.dump too small ($size bytes)" >&2
    errors=$((errors + 1))
  else
    echo "OK: knowledge.dump ($size bytes)"
    if command -v pg_restore >/dev/null 2>&1; then
      pg_restore --list "$OUT/knowledge.dump" >/dev/null && echo "OK: pg_restore --list"
    elif docker ps --format '{{.Names}}' | grep -qx agenthub-postgres; then
      cat "$OUT/knowledge.dump" | docker exec -i agenthub-postgres pg_restore -U postgres --list >/dev/null \
        && echo "OK: pg_restore --list (via container)"
    else
      echo "WARN: pg_restore not available locally; skip list check"
    fi
  fi
else
  echo "SKIP: no postgres dump (agenthub-postgres not running?)"
fi

if [[ -d "$OUT/neo4j" ]] && [[ -n "$(ls -A "$OUT/neo4j" 2>/dev/null || true)" ]]; then
  echo "OK: neo4j artifacts present"
else
  echo "SKIP/WARN: no neo4j dump artifacts"
fi

if [[ "${DRILL_RESTORE:-}" == "1" ]] && [[ -f "$OUT/knowledge.dump" ]]; then
  echo "=== P1-4 Step 2: restore drill (RESTORE_CONFIRM=1) ==="
  RESTORE_FROM="$OUT" RESTORE_CONFIRM=1 bash scripts/restore.sh
  if docker ps --format '{{.Names}}' | grep -qx agenthub-postgres; then
    tables=$(docker exec agenthub-postgres psql -U postgres -d knowledge -tAc \
      "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
    echo "OK: restored database public tables=$tables"
  fi
fi

if [[ "$errors" -gt 0 ]]; then
  echo "P1-4 backup drill FAILED ($errors errors)" >&2
  exit 1
fi

echo "P1-4 backup drill PASSED (backup validated; set DRILL_RESTORE=1 for live restore)"
