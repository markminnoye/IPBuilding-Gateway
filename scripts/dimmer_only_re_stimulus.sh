#!/usr/bin/env bash
# Dimmer-only RE stimulus: operator mirrors UniFi port 12 -> mirror port 7 (en7) and
# runs dumpcap/tshark separately; use same UDP host-scope BPF as ipbuilding_golden_runbook (any UDP port).
# This script only issues timed IPBox REST actions + optional HTTP status snapshots
# (UTC timestamps in manifest for pcap correlation).

set -euo pipefail

IPBOX_BASE="${IPBOX_BASE:-http://192.168.0.185:30200/api/v1}"
DIMMER_ID="${DIMMER_ID:-572}"
STEP_PAUSE_SEC="${STEP_PAUSE_SEC:-22}"
STATUS_URL="${STATUS_URL:-http://10.10.1.40/api.html?method=statuses}"
MANIFEST_PATH="${MANIFEST_PATH:-${PWD}/dimmer_re_manifest.log}"
CURL_STATUS="${CURL_STATUS:-1}"

log_action_line() {
  local action="$1"
  local url="$2"
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  printf '%s %s %s\n' "$ts" "$action" "$url" | tee -a "$MANIFEST_PATH"
}

do_rest() {
  local action="$1"
  local url="$2"
  local combined http_line code

  log_action_line "$action" "$url"

  combined="$(curl -sS -m 10 -w '\nHTTP:%{http_code}\n' "$url")" || {
    echo "curl failed for $action" >&2
    return 1
  }

  http_line="$(printf '%s' "$combined" | tail -n 1 | tr -d '\r')"
  code="${http_line#HTTP:}"
  if [[ "$code" != "200" ]]; then
    printf 'Expected HTTP 200 for %s, got %s\n' "$action" "$code" >&2
    printf '%s\n' "$combined" | sed '$d' >&2 || true
    return 1
  fi

  if [[ "$CURL_STATUS" == "1" ]]; then
    local snip
    snip="$(curl -sS -m 4 "$STATUS_URL" 2>/dev/null | head -c 500 || true)"
    printf '# statuses: %s\n' "$snip" >> "$MANIFEST_PATH"
  fi
}

sleep_step() {
  sleep "$STEP_PAUSE_SEC"
}

main() {
  : >"$MANIFEST_PATH"

  cat >&2 <<'EOF'
WARNING: Before the first REST action, ensure UniFi mirror (e.g. 7←12 or 7←15) is active and
packet capture on en7 is already running. Suggested BPF (any UDP port to/from IPBuilding hosts):
  udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)
EOF

  do_rest "OFF" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=OFF&value=0"
  sleep_step
  do_rest "DIM_30" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=DIM&value=30"
  sleep_step
  do_rest "DIM_70" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=DIM&value=70"
  sleep_step
  do_rest "DIM_100" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=DIM&value=100"
  sleep_step
  do_rest "OFF" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=OFF&value=0"
}

main "$@"
