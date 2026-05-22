#!/usr/bin/env bash
# Sprint 5 — manual capture (operator only). No sudo, no orchestrator.
# You run Wireshark/dumpcap, press buttons, save artifacts; agent analyzes later.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="$(date -u +%Y-%m-%dT%H%M%SZ)_sprint5-manual"
OUT="${REPO}/captures/${SESSION}"
IFACE="${CAPTURE_INTERFACE:-en7}"
DURATION="${CAPTURE_SECONDS:-90}"

mkdir -p "$OUT"
cat >"$OUT/README.txt" <<EOF
Sprint 5 manual capture
UTC folder: ${SESSION}
Mirror (UniFi): destination port 7 <- source port 15 (7<-15) on Unify Switch 16
Capture NIC: ${IFACE}
BPF: udp port 1001
Planned duration: ${DURATION}s
EOF

echo "=============================================="
echo " Sprint 5 — manual IP1100 button capture"
echo "=============================================="
echo ""
echo "Session folder (save everything here):"
echo "  ${OUT}"
echo ""
echo "BEFORE YOU START"
echo "  1) UniFi: mirror 7<-15 (dest 7, source 15) on Unify Switch 16"
echo "  2) Mac USB NIC ${IFACE} connected to mirror port 7"
echo "  3) Optional: ping 10.10.1.50 (input module should reply)"
echo ""
read -r -p "Mirror OK and ${IFACE} ready? Press ENTER to continue..."

echo ""
echo "--- Step A: getButtons BEFORE (optional but helpful) ---"
curl -sS "http://10.10.1.50/api.html?method=getButtons" \
  -o "${OUT}/ip1100_buttons_pre.json" \
  && echo "Saved: ip1100_buttons_pre.json" \
  || echo "WARN: getButtons pre failed (continue anyway)"

echo ""
echo "--- Step B: Start capture (${DURATION}s) ---"
echo "Option 1 — Terminal (no Wireshark GUI):"
echo "  dumpcap -i ${IFACE} -f 'udp port 1001' -a duration:${DURATION} -w \"${OUT}/capture.pcapng\""
echo ""
echo "Option 2 — Wireshark GUI:"
echo "  Capture -> Options -> Interface ${IFACE}"
echo "  Capture filter: udp port 1001"
echo "  Start, then stop after ~${DURATION} seconds"
echo "  File -> Save As -> ${OUT}/capture.pcapng"
echo ""
read -r -p "Press ENTER when capture has STARTED..."

echo ""
echo "--- Step C: Press buttons (during capture) ---"
echo "  ~0s   : (capture already running)"
echo "  ~5s   : press physical button A (short)"
echo "  ~15s  : press physical button B (short)"
echo "  ~25s  : press physical button C (short)"
echo "  ~35s  : optional — press same button again"
echo "  then  : wait until capture ends"
echo ""
read -r -p "Press ENTER when capture has STOPPED and capture.pcapng is saved..."

if [[ ! -f "${OUT}/capture.pcapng" ]]; then
  echo ""
  echo "WARN: ${OUT}/capture.pcapng not found yet."
  echo "If you used dumpcap, run:"
  echo "  dumpcap -i ${IFACE} -f 'udp port 1001' -a duration:${DURATION} -w \"${OUT}/capture.pcapng\""
  read -r -p "Press ENTER after capture.pcapng exists..."
fi

echo ""
echo "--- Step D: getButtons AFTER ---"
curl -sS "http://10.10.1.50/api.html?method=getButtons" \
  -o "${OUT}/ip1100_buttons_post.json" \
  && echo "Saved: ip1100_buttons_post.json" \
  || echo "WARN: getButtons post failed"

echo ""
echo "--- Step E: Operator notes (optional) ---"
NOTES="${OUT}/operator_notes.txt"
if [[ ! -f "$NOTES" ]]; then
  cat >"$NOTES" <<'NOTE'
# Fill in after capture (one line per press)
# UTC or local time | button label | room/cable guess
# Example:
# 2026-05-22 10:15:05 | Keuken hal | Cat5-A
NOTE
fi
echo "Edit if you want: ${NOTES}"
"${EDITOR:-nano}" "$NOTES" 2>/dev/null || true

echo ""
echo "=============================================="
echo " DONE — give the agent this folder:"
echo "  ${OUT}"
echo ""
echo "Required:"
echo "  - capture.pcapng"
echo "Recommended:"
echo "  - ip1100_buttons_pre.json"
echo "  - ip1100_buttons_post.json"
echo "  - operator_notes.txt (button times/labels)"
echo "  - README.txt (auto)"
echo "=============================================="
