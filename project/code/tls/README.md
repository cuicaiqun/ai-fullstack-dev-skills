# Local TLS certs (self-signed)

Generated for CN=localhost. Trust is local-only; browsers will warn.

Bring up TLS terminator:

```bash
cd code
bash scripts/gen_selfsigned_tls.sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.tls.yml --env-file python/.env up -d tls
curl -k https://127.0.0.1:8443/api/health
```
