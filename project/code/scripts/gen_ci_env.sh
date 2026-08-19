#!/usr/bin/env bash
# Generate CI/staging .env for docker compose (strong secrets, in-network DSNs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/python/.env.ci}"
JWT="$(openssl rand -hex 32)"
NEO4J_PASS="$(openssl rand -hex 16)"
PG_PASS="$(openssl rand -hex 16)"
ADMIN_PASS="$(openssl rand -hex 12)"

cat > "$OUT" <<EOF
APP_ENV=development
REQUIRE_STRONG_SECRETS=false
AUTH_ENABLED=true
OPENAI_API_KEY=sk-ci-placeholder-not-used
REQUIRE_OPENAI_API_KEY=false
DISABLE_LOCAL_EMBEDDINGS=1
UPDATE_MODE=off
INGEST_QUEUE=local
INGEST_ASYNC=false

JWT_SECRET=$JWT
NEO4J_USER=neo4j
NEO4J_PASSWORD=$NEO4J_PASS
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$PG_PASS
POSTGRES_DB=knowledge
AUTH_BOOTSTRAP_ADMIN_USERNAME=admin
AUTH_BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASS

NEO4J_URI=bolt://neo4j:7687
CHROMA_HOST=chromadb
CHROMA_PORT=8000
STATE_STORE_DSN=postgresql://postgres:${PG_PASS}@postgres:5432/knowledge
PGVECTOR_DSN=postgresql://postgres:${PG_PASS}@postgres:5432/knowledge
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
REDIS_URL=redis://redis:6379/0
EOF

echo "Wrote $OUT"
echo "CI_ADMIN_PASSWORD=$ADMIN_PASS"
