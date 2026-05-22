#!/usr/bin/env bash
# Operator checklist before relay Run A capture (UniFi mirror + optional pcap sanity).
# Does not change UniFi; prints steps and copy-paste commands. See:
#   resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md
#   resources_and_docs/evidence/2026-05-15_capture_bidirectional_explainer.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IFACE="${CAPTURE_INTERFACE:-en7}"

echo "=== Relay Run A — mirror preflight (operator) ==="
echo ""
echo "1) UniFi Network: port mirror to capture NIC (${IFACE})."
echo "   Recommended default: destination port 7 (Mac) <- source port 15 (IPBox VLAN leg / hub POV, 10.10.1.1)."
echo "   Alternate (only if you need relay-switch-port POV instead of default 7<-15): destination 7 <- source 14 (10.10.1.30)."
echo "   Match manifest + notes to the actual UI for this run."
echo "   Preview -> Apply. Do NOT leave IPBox access port (often 8) mirrored if IPBox must stay online."
echo ""
echo "2) Smoke: ping 10.10.1.30; curl IPBox :30200 /api/v1/comp/items (from home LAN)."
echo ""
echo "3) After capture, check bidirectional UDP on the raw pcap (Wireshark MCP — recommended):"
echo "   wireshark_stats_endpoints(<pcap_file>, type=\"udp\")  # Rx count > 0 = PASS"
echo ""
echo "   Or objective relay->hub check with ip.addr (NOT ip.src, which drops replies):"
echo "   tshark -r captures/<SESSION>/capture.pcapng -Y \"udp.port==1001 && ip.addr==10.10.1.30\" | wc -l"
echo ""
echo "4) Or use:"
echo "   python3 \"$ROOT/scripts/udp1001_bidir_counts.py\" captures/<SESSION>/capture.pcapng --rest-ip <IPBox_thuis_IP>"
echo ""
echo "5) Rollback mirror to your normal profile after the session."
echo ""
echo "Next: generate aligned runbook (REST + BPF + correlate --rest-ip):"
echo "   IPBUILDING_IPBOX_REST_HOST=<thuis-ip> python3 \"$ROOT/scripts/prepare_local_push_pull_run_a_runbook.py\""
echo "   ./scripts/relay_run_a_capture.sh --interface ${IFACE} --runbook captures/_local_push_pull_run_a.yaml"
echo ""
