#!/usr/bin/env bash
# Optional dimmer RE (stap 4): reminders only — dumpcap + UniFi mirror 7<-12 are operator steps.
set -euo pipefail
cat <<'EOF'
Dimmer capture preflight (see resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md § Optional dimmer):

1) UniFi: mirror destination 7 <- source 12 (dimmer 10.10.1.40). NOT source 11.
2) Start dumpcap on en7 with BPF e.g. "host 10.10.1.40 and udp port 1001"
3) From repo root: ./scripts/dimmer_only_re_stimulus.sh
4) Stop dumpcap; correlate session folder with --verdict-profile dimmer --rest-ip 192.168.0.185
5) Restore mirror to 7<-15 (default hub) first choice; only if your profile uses relay-leg POV: 7<-14; else your normal profile.

Environment: IPBOX_BASE, DIMMER_ID, STEP_PAUSE_SEC, MANIFEST_PATH optional (see dimmer_only_re_stimulus.sh).
EOF
