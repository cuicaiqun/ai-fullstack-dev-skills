#!/usr/bin/env bash
# P0-5：在运行中的 Neo4j 创建只读用户（Community：凭据 + driver READ access mode）。
set -euo pipefail
CONTAINER="${NEO4J_CONTAINER:-agenthub-neo4j}"
ADMIN_USER="${NEO4J_USER:-neo4j}"
ADMIN_PASS="${NEO4J_PASSWORD:-password}"
READ_USER="${NEO4J_READ_USER:-readonly}"
READ_PASS="${NEO4J_READ_PASSWORD:-}"

if [[ -z "$READ_PASS" ]]; then
  READ_PASS="$(openssl rand -hex 16)"
  echo "Generated NEO4J_READ_PASSWORD=$READ_PASS"
fi

docker exec -i "$CONTAINER" cypher-shell -u "$ADMIN_USER" -p "$ADMIN_PASS" <<EOF
CREATE USER $READ_USER IF NOT EXISTS SET PASSWORD '$READ_PASS' CHANGE NOT REQUIRED;
SHOW USERS;
EOF

set +e
alter_out=$(docker exec -i "$CONTAINER" cypher-shell -u "$ADMIN_USER" -p "$ADMIN_PASS" \
  "ALTER USER $READ_USER SET PASSWORD '$READ_PASS' CHANGE NOT REQUIRED;" 2>&1)
alter_rc=$?
set -e
if [[ $alter_rc -ne 0 ]]; then
  if [[ "$alter_out" == *"cannot be the same"* ]]; then
    echo "Readonly user password already set"
  else
    echo "$alter_out" >&2
    exit "$alter_rc"
  fi
fi

if docker exec -i "$CONTAINER" cypher-shell -u "$ADMIN_USER" -p "$ADMIN_PASS" \
  "GRANT ROLE reader TO $READ_USER;" 2>/dev/null; then
  echo "Granted Neo4j reader role to $READ_USER"
else
  echo "Note: GRANT ROLE reader skipped (Neo4j Community has no RBAC); use driver READ access mode."
fi

docker exec "$CONTAINER" cypher-shell -u "$READ_USER" -p "$READ_PASS" "RETURN 1 AS ok;" >/dev/null

echo
echo "Add to python/.env (do not commit real secrets):"
echo "NEO4J_READ_USER=$READ_USER"
echo "NEO4J_READ_PASSWORD=$READ_PASS"
