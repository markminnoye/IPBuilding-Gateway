#!/usr/bin/env bash
# Pre-flight: verify gateway REST + a sample command. Optional HA reachability.
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"
HA_URL="${HA_URL:-http://127.0.0.1:8123}"

echo "=== Gateway REST: GET /api/v1/devices ==="
DEVICES_JSON=$(curl -sf "${GATEWAY_URL}/api/v1/devices")
DEVICE_COUNT=$(python3 -c "import json,sys; print(len(json.load(sys.stdin).get('devices', [])))" <<< "${DEVICES_JSON}")
echo "devices: ${DEVICE_COUNT}"
if [ "${DEVICE_COUNT}" -lt 1 ]; then
  echo "FAIL: expected at least 1 device from devices.json" >&2
  exit 1
fi

SAMPLE_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['devices'][0]['id'])" <<< "${DEVICES_JSON}")
echo "sample entity id: ${SAMPLE_ID}"

echo "=== Gateway command: POST /api/v1/devices/${SAMPLE_ID}/command ==="
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${GATEWAY_URL}/api/v1/devices/${SAMPLE_ID}/command" \
  -H 'Content-Type: application/json' \
  -d '{"action":"ON"}')
echo "HTTP ${HTTP_CODE}"
if [ "${HTTP_CODE}" != "200" ]; then
  echo "FAIL: expected HTTP 200 from /command" >&2
  exit 1
fi

if curl -sf "${HA_URL}/" >/dev/null 2>&1; then
  echo "=== Home Assistant UI: reachable at ${HA_URL} ==="
else
  echo "=== Home Assistant UI: not yet ready (skip) ==="
fi

echo "PASS"
