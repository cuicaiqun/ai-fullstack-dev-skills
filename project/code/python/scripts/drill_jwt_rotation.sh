#!/usr/bin/env bash
# P0-3：JWT 密钥轮换 / 回滚演练（runbook §2）
# Usage (from code/python):
#   bash scripts/drill_jwt_rotation.sh
# Requires: agenthub-api reachable at API_BASE (default http://127.0.0.1:8080)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODE_DIR="$(cd "$ROOT/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
API_BASE="${API_BASE:-http://127.0.0.1:8080}"
ADMIN_USER="${DRILL_ADMIN_USER:-admin}"
ADMIN_PASS="${DRILL_ADMIN_PASS:-admin123}"
COMPOSE=(docker compose -f "$CODE_DIR/docker-compose.yml" -f "$CODE_DIR/docker-compose.dev.yml" --env-file "$ENV_FILE")

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi

read_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true
}

write_env() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

OLD_SECRET="$(read_env JWT_SECRET)"
if [[ -z "$OLD_SECRET" ]]; then
  echo "JWT_SECRET not set in $ENV_FILE" >&2
  exit 1
fi

BACKUP="$ENV_FILE.jwt-drill-backup-$(date +%Y%m%d%H%M%S)"
cp "$ENV_FILE" "$BACKUP"
echo "Backed up env to $BACKUP"

login_token() {
  curl -sf -X POST "$API_BASE/api/auth/login" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

me_status() {
  local token="$1"
  curl -s -o /dev/null -w '%{http_code}' "$API_BASE/api/auth/me" \
    -H "Authorization: Bearer $token"
}

restart_api() {
  "${COMPOSE[@]}" up -d api ingest-worker 2>/dev/null || "${COMPOSE[@]}" up -d api
  for _ in $(seq 1 30); do
    if curl -sf "$API_BASE/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "API not healthy after restart" >&2
  return 1
}

echo "=== Step 1: login with current JWT_SECRET ==="
TOKEN_OLD="$(login_token)"
echo "old token acquired (${#TOKEN_OLD} chars)"

echo "=== Step 2: verify old token works ==="
code="$(me_status "$TOKEN_OLD")"
if [[ "$code" != "200" ]]; then
  echo "expected 200 on /me before rotation, got $code" >&2
  exit 1
fi
echo "pre-rotation /me -> 200 OK"

NEW_SECRET="$(openssl rand -hex 32)"
echo "=== Step 3: rotate JWT_SECRET and restart API ==="
write_env JWT_SECRET "$NEW_SECRET"
restart_api

echo "=== Step 4: old token must be 401 ==="
code="$(me_status "$TOKEN_OLD")"
if [[ "$code" != "401" ]]; then
  echo "FAIL: expected 401 after rotation, got $code" >&2
  exit 1
fi
echo "post-rotation old token /me -> 401 OK"

echo "=== Step 5: new login must work ==="
TOKEN_NEW="$(login_token)"
code="$(me_status "$TOKEN_NEW")"
if [[ "$code" != "200" ]]; then
  echo "FAIL: new login /me expected 200, got $code" >&2
  exit 1
fi
echo "new login /me -> 200 OK"

echo "=== Step 6: rollback JWT_SECRET ==="
write_env JWT_SECRET "$OLD_SECRET"
restart_api
TOKEN_ROLLBACK="$(login_token)"
code="$(me_status "$TOKEN_ROLLBACK")"
if [[ "$code" != "200" ]]; then
  echo "FAIL: rollback login /me expected 200, got $code" >&2
  exit 1
fi
echo "rollback login /me -> 200 OK"

echo
echo "P0-3 JWT rotation drill PASSED"
echo "Checklist: old JWT 401 after rotate | new login 200 | rollback re-login 200"
echo "Backup env: $BACKUP"
