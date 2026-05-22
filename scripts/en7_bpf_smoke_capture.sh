#!/usr/bin/env bash
# Fase 2: sluit capture-BPF (hostfilter) uit als oorzaak van "half" zichtbare UDP.
# Draait kort `dumpcap` op en7 met ALLEEN `udp port 1001` (geen host 10.10.1.x filter).
#
# Vereisten: Wireshark dumpcap, sudo, actieve mirror naar en7.
# Voorbeeld:
#   CAP_IFACE=en7 DURATION_SEC=25 OUT=/tmp/en7_smoke_udp1001.pcapng ./scripts/en7_bpf_smoke_capture.sh

set -euo pipefail

CAP_IFACE="${CAP_IFACE:-en7}"
DURATION_SEC="${DURATION_SEC:-25}"
STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
OUT="${OUT:-${HOME}/Downloads/en7_bpf_smoke_udp1001_${STAMP}.pcapng}"

if ! command -v dumpcap >/dev/null 2>&1; then
  echo "dumpcap not found (install Wireshark)" >&2
  exit 1
fi

echo "Writing ${OUT} for ${DURATION_SEC}s on -i ${CAP_IFACE} (filter: udp port 1001 only)"
sudo dumpcap -i "${CAP_IFACE}" -a duration:"${DURATION_SEC}" -f "udp port 1001" -w "${OUT}"

echo "Packets:"
capinfos -c "${OUT}" 2>/dev/null || true

echo "Relay direction spot-check (pas IPs aan indien nodig):"
tshark -r "${OUT}" -Y "udp.port==1001 && ip.src==10.10.1.30 && ip.dst==10.10.1.1" -T fields -e frame.number 2>/dev/null | wc -l | awk '{print "  relay->hub lines:", $1}'
tshark -r "${OUT}" -Y "udp.port==1001 && ip.src==10.10.1.1 && ip.dst==10.10.1.30" -T fields -e frame.number 2>/dev/null | wc -l | awk '{print "  hub->relay lines:", $1}'

echo "Next: python3 scripts/udp1001_bidir_counts.py \"${OUT}\""
