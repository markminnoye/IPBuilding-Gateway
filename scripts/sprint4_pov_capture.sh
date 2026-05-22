#!/bin/bash
# Sprint 4 — POV-vergelijking: 3 mirrors, identieke stimulus
# Mirror-stappen:
#   A: 7←15 (IPBox hub / veldbus been) — standaard
#   B: 7←14 (relay-switchpoort 10.10.1.30)
#   C: 7←12 (dimmer-poort 10.10.1.40)
#
# Gebruik: ./scripts/sprint4_pov_capture.sh
# Vereisten: sudo, virtualenv met requirements-capture.txt, UniFi mirror vooraf ingesteld

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
RUNBOOK_DIR="$REPO_ROOT/resources_and_docs/workflows"
SCRATCH_DIR="$REPO_ROOT/captures/sprint4_pov_comparison_$(date +%Y%m%dT%H%M%S)"

# ---- vars ----
# Vervang met je effectieve IPBox-thuis-IP (192.168.1.x)
IPBOX_REST_HOST="${IPBUILDING_IPBOX_REST_HOST:-192.168.1.x}"
REST_PORT="${REST_PORT:-30200}"
INTERFACE="${INTERFACE:-en7}"
CAPTURE_DURATION="${CAPTURE_DURATION:-60}"  # seconden per capture

#BPF voor alle POV's: busverkeer + thuis-IP
BPF="udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host ${IPBOX_REST_HOST})"

# De drie runbooks (zelfde stimulus, verschillende mirror-config in UniFi)
POV_RUNBOOKS=(
    "$RUNBOOK_DIR/sprint4_pov_a_runbook.yaml"
    "$RUNBOOK_DIR/sprint4_pov_b_runbook.yaml"
    "$RUNBOOK_DIR/sprint4_pov_c_runbook.yaml"
)

echo "=== Sprint 4 — POV-vergelijking ==="
echo "IPBox REST: $IPBOX_REST_HOST:$REST_PORT"
echo "Interface: $INTERFACE"
echo "Capture duration: ${CAPTURE_DURATION}s per POV"
echo ""
echo "BELANGRIJK: Stel UniFi mirror in VÓÓR elk van de 3 runs:"
echo "  POV A: 7←15 (IPBox hub)         → UniFi: source 15 → dest 7"
echo "  POV B: 7←14 (relay switch)     → UniFi: source 14 → dest 7"
echo "  POV C: 7←12 (dimmer switch)    → UniFi: source 12 → dest 7"
echo ""
echo "Druk ENTER na elke UniFi-mirror-wijziging om de volgende run te starten."
read -r

mkdir -p "$SCRATCH_DIR"

for i in "${!POV_RUNBOOKS[@]}"; do
    run_idx=$((i+1))
    runbook="${POV_RUNBOOKS[$i]}"
    session_dir="$SCRATCH_DIR/pov_${run_idx}_$(basename "$runbook" .yaml)"
    pov_label=$(basename "$runbook" .yaml | sed 's/sprint4_pov_//')

    echo ""
    echo "=========================================="
    echo "POV $run_idx / 3 — $pov_label"
    echo "=========================================="

    if [[ ! -f "$runbook" ]]; then
        echo "FOUT: runbook niet gevonden: $runbook"
        exit 1
    fi

    # Bewerk runbook in-place voor dit IPBox-thuis-IP
    TMP_RUNBOOK="$session_dir/runbook.yaml"
    mkdir -p "$session_dir"
    sed "s/192.168.1.x/${IPBOX_REST_HOST}/g" "$runbook" > "$TMP_RUNBOOK"

    echo "Start capture ($CAPTURE_DURATION s)..."
    echo "Session: $session_dir"

    # Start capture (dumpcap) op de achtergrond
    "$VENV/bin/python" "$REPO_ROOT/ipbuilding_capture_run.py" \
        --runbook "$TMP_RUNBOOK" \
        --interface "$INTERFACE" \
        --output-dir "$session_dir" \
        --capture-duration "$CAPTURE_DURATION" \
        2>&1 | tee "$session_dir/run.log"

    echo ""
    echo "POV $run_idx capture done. Resultaten in: $session_dir"
    echo "Run log: $session_dir/run.log"
    echo ""

    # Check of capture pcap bestaat
    if [[ -f "$session_dir/capture.pcapng" ]]; then
        echo "pcap gevonden: $(wc -c < "$session_dir/capture.pcapng") bytes"
    else
        echo "WAARSCHUWING: geen capture.pcapng in $session_dir"
    fi

    if [[ $run_idx -lt 3 ]]; then
        echo ""
        echo "=== UniFi mirror aanpassen voor POV $((run_idx+1)) ==="
        case $((run_idx+1)) in
            2) echo "Zet mirror: 7←14 (relay switch poort 14)" ;;
            3) echo "Zet mirror: 7←12 (dimmer poort 12)" ;;
        esac
        read -r -p "Druk ENTER als mirror is ingesteld..."
    fi
done

echo ""
echo "=== Alle 3 POV captures voltooid ==="
echo "Resultaten: $SCRATCH_DIR"
echo ""
echo "Analyseer met:"
echo "  for d in $SCRATCH_DIR/pov_*/; do"
echo "    echo --- \$(basename \$d) ---"
echo "    python3 scripts/correlate_capture_session.py \$d --verdict-profile relay --rest-ip $IPBOX_REST_HOST"
echo "  done"