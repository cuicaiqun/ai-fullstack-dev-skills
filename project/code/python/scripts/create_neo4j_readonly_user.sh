#!/usr/bin/env bash
# P0-5：在运行中的 Neo4j 创建只读用户（Community reader 角色）。
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
GRANT ROLE reader TO $READ_USER;
SHOW USERS;
EOF

echo
echo "Add to python/.env (do not commit real secrets):"
echo "NEO4J_READ_USER=$READ_USER"
echo "NEO4J_READ_PASSWORD=$READ_PASS"
