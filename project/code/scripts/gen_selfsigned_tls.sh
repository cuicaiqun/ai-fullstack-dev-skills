#!/usr/bin/env bash
# Generate local self-signed TLS material for P0-3 (localhost).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${TLS_OUT_DIR:-$ROOT/tls}"
mkdir -p "$OUT"
CN="${TLS_CN:-localhost}"
DAYS="${TLS_DAYS:-825}"

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout "$OUT/server.key" \
  -out "$OUT/server.crt" \
  -days "$DAYS" \
  -subj "/CN=$CN" \
  -addext "subjectAltName=DNS:localhost,DNS:$CN,IP:127.0.0.1"

chmod 600 "$OUT/server.key"
cat > "$OUT/README.md" <<EOF
# Local TLS certs (self-signed)

Generated for CN=$CN. Trust is local-only; browsers will warn.

Bring up TLS terminator:

\`\`\`bash
cd code
bash scripts/gen_selfsigned_tls.sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.tls.yml --env-file python/.env up -d tls
curl -k https://127.0.0.1:8443/api/health
\`\`\`
EOF
echo "Wrote $OUT/server.crt and $OUT/server.key"
