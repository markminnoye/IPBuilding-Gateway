#!/usr/bin/env bash
# Controlled relay Run A capture (push/pull runbook) + post-session correlate with relay verdict profile.
# Requires: sudo for dumpcap, tshark, aiohttp; UniFi mirror 7<-15 default (IPBox leg); 7<-14 = relay-leg alternate (see playbook).
# Preflight + local IP alignment: scripts/relay_run_a_mirror_preflight.sh, scripts/prepare_local_push_pull_run_a_runbook.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; fi
echo "0) Mirror + IP prep: ./scripts/relay_run_a_mirror_preflight.sh"
echo "   IPBUILDING_IPBOX_REST_HOST=<ip> python3 scripts/prepare_local_push_pull_run_a_runbook.py"
echo "   ./scripts/relay_run_a_capture.sh --interface en7 --runbook captures/_local_push_pull_run_a.yaml"
echo ""
echo "1) UniFi: mirror destination 7 <- source 15 (IPBox VLAN leg 10.10.1.1 hub POV) — recommended default."
echo "   Alternate (relay switch port only, not the hub default above): destination 7 <- source 14 (10.10.1.30)."
echo "   Preview, apply, then ping 10.10.1.30 and REST smoke to IPBox."
echo "2) Do NOT leave IPBox access port (often 8) as mirror source while IPBox must stay online."
echo "3) Capture NIC: en7 (override with extra args passed through to ipbuilding_capture_run.py)."
echo ""
exec "$PY" ipbuilding_capture_run.py \
  --runbook resources_and_docs/workflows/push_pull_run_a_runbook.yaml \
  "$@"
