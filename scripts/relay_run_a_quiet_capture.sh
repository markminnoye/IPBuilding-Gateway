#!/usr/bin/env bash
# Quiet evening relay capture: Run A without ID 570 (kitchen ventilation). Same mirror guidance as Run A (7<-15 default; 7<-14 alternate).
# Requires: sudo for dumpcap, tshark, aiohttp; UniFi mirror per playbook (see relay_run_a_operational_playbook.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; fi
echo "=== Pre-flight (quiet evening) ==="
echo "1) UniFi: mirror destination 7 <- source 15 (IPBox leg) — default; alternate (relay leg only, not hub default): 7 <- source 14 (relay 10.10.1.30). Preview, apply, then ping 10.10.1.30 and REST smoke."
echo "2) Stimulus: relays 547 (Keuken LED), 557 (Inkom), 563 (Keuken Eettafel) — no 570 fan."
echo "3) Capture NIC: en7 (pass through extra args to ipbuilding_capture_run.py if needed)."
echo ""
exec "$PY" ipbuilding_capture_run.py \
  --runbook resources_and_docs/workflows/push_pull_run_a_quiet_evening.yaml \
  "$@"
