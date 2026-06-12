#!/usr/bin/env bash
# Start the gateway in the background, wait until :8080 answers, then
# start the Home Assistant container. Stop the gateway when you Ctrl+C.
set -euo pipefail

cd "$(dirname "$0")/.."
SCRIPTS_DIR="$(pwd)/scripts"

if [ ! -f .env ]; then
  echo "Missing .env — copy .env.example to .env and adjust paths." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found in PATH. Start OrbStack (or Docker Desktop) first." >&2
  exit 1
fi

echo ">>> Starting simulated gateway on the host"
"${SCRIPTS_DIR}/start-gateway.sh" &
GATEWAY_PID=$!
trap 'echo ">>> Stopping gateway (pid ${GATEWAY_PID})"; kill "${GATEWAY_PID}" 2>/dev/null || true; docker compose down >/dev/null 2>&1 || true' EXIT INT TERM

echo ">>> Waiting for gateway on http://127.0.0.1:8080/health"
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
    echo "gateway up"
    break
  fi
  sleep 1
done

if ! curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
  echo "Gateway did not become ready in 30s — aborting." >&2
  exit 1
fi

echo ">>> Starting Home Assistant container"
docker compose up -d

echo
echo "HA UI:    http://localhost:8123"
echo "Gateway:  http://127.0.0.1:8080/api/v1/devices"
echo "Press Ctrl+C to stop gateway + HA"

wait "${GATEWAY_PID}"
