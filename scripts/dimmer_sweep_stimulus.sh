#!/usr/bin/env bash
# Dimmer channel/value sweep (RE): timed REST steps + UTC manifest for UDP correlation.
#
# Operator setup BEFORE first REST action:
# - UniFi port mirror to capture Mac (e.g. destination 7 ← source 15 IPBox VLAN leg, or 7←12 for
#   dimmer-only path). See resources_and_docs/workflows/IPBUILDING_CAPTURE_WORKFLOW.md and resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md.
# - dumpcap or tcpdump on interface en7 using the broad BPF from
#   resources_and_docs/workflows/ipbuilding_golden_runbook.yaml → capture.bpf_filter (matches golden golden-protocol scope).
#
# This script only issues IPBox REST actions + optional HTTP status snapshots (plain-text manifest).

set -euo pipefail

IPBOX_BASE="${IPBOX_BASE:-http://192.168.0.185:30200/api/v1}"
# Default for convenience; set explicitly per run (571 / 572 / 573) so logs label the right comp.
DIMMER_ID="${DIMMER_ID:-572}"
STEP_PAUSE_SEC="${STEP_PAUSE_SEC:-22}"
STATUS_URL="${STATUS_URL:-http://10.10.1.40/api.html?method=statuses}"
MANIFEST_PATH="${MANIFEST_PATH:-${PWD}/dimmer_sweep_manifest.log}"
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
WARNING: DIMMER SWEEP STIMULUS (NO CAPTURE STARTED BY THIS SCRIPT)
- Verify UniFi mirror is already active (example: 7<-15 for IPBox VLAN leg, or 7<-12 for dimmer path).
- Verify dumpcap/tcpdump is already running on en7 before first REST action.
- Suggested broad UDP BPF:
    udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)
EOF

  printf '# run DIMMER_ID=%s STEP_PAUSE_SEC=%s IPBOX_BASE=%s\n' "$DIMMER_ID" "$STEP_PAUSE_SEC" "$IPBOX_BASE" >> "$MANIFEST_PATH"

  do_rest "ON" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=ON&value=1"
  sleep_step
  do_rest "OFF" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=OFF&value=0"
  sleep_step

  local v
  for v in 100 90 80 70 60 50 40 30 20 10; do
    do_rest "DIM_${v}" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=DIM&value=${v}"
    sleep_step
  done

  do_rest "OFF_FINAL" "${IPBOX_BASE}/action/action?id=${DIMMER_ID}&actionType=OFF&value=0"
}

main "$@"
