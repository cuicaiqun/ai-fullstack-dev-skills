#!/usr/bin/env bash
# P1-1：Watchdog + Kafka CDC 真实依赖 E2E
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RUN_CDC_E2E=1
export UPDATE_MODE=off
export REQUIRE_OPENAI_API_KEY=false
export WALL_TIMEOUT="${WALL_TIMEOUT:-300}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-localhost:29092}"
export KAFKA_TOPIC_DOC_CHANGES="${KAFKA_TOPIC_DOC_CHANGES:-doc-changes}"

echo "=== P1-1 CDC watch E2E ==="
bash scripts/run_unit_tests.sh tests/test_cdc_watch_kafka_e2e.py::test_watchdog_picks_up_created_file \
  tests/test_cdc_watch_kafka_e2e.py::test_watchdog_suppress_skips_during_ttl -vv "$@"

_kafka_tests=(
  tests/test_cdc_watch_kafka_e2e.py::test_kafka_produce_consume_and_process
  tests/test_cdc_watch_kafka_e2e.py::test_kafka_invalid_json_poison_to_dlq
  tests/test_cdc_watch_kafka_e2e.py::test_kafka_process_failure_poison_to_dlq
  tests/test_cdc_watch_kafka_e2e.py::test_kafka_rebalance_consumer_handoff
)

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q agenthub-kafka; then
  echo "=== P1-1 Kafka E2E (kafka container up) ==="
  export RUN_KAFKA_E2E=1
  bash scripts/run_unit_tests.sh "${_kafka_tests[@]}" -vv "$@"
else
  CODE_DIR="$(cd "$ROOT/.." && pwd)"
  echo "=== Starting kafka for E2E ==="
  docker compose -f "$CODE_DIR/docker-compose.yml" -f "$CODE_DIR/docker-compose.dev.yml" up -d kafka 2>/dev/null || true
  sleep 8
  if docker ps --format '{{.Names}}' | grep -q agenthub-kafka; then
    export RUN_KAFKA_E2E=1
    bash scripts/run_unit_tests.sh tests/test_cdc_watch_kafka_e2e.py::test_kafka_produce_consume_and_process -vv "$@"
  else
    echo "SKIP Kafka E2E: agenthub-kafka not running (watch tests passed)"
  fi
fi

echo "P1-1 CDC E2E finished"
