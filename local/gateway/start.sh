#!/usr/bin/env bash
# Start the IPBuilding gateway on the Mac host. Foreground; Ctrl+C to stop.
# HA Core in ~/.homeassistant reaches it via http://127.0.0.1:8080.
#
# Modes:
#   (default)            Real field bus + passive ARP
#   --sim                Simulated UDP (no hardware required)
#   --init               Field bus install/refresh: prompt before launching
#   -h | --help          Show this help
#
# With --init, an interactive prompt runs BEFORE the gateway starts:
#   y -> reset devices.json (backup -> devices.json.bak) + init-sweep
#   N -> keep devices.json, force discovery (merge: preserves names/rooms/active)
#
# Env vars set for python -m gateway:
#   GATEWAY_SIMULATED
#   GATEWAY_PASSIVE_ARP_MONITOR
#   GATEWAY_AUTO_DISCOVER_ON_START         (--init + y)
#   GATEWAY_FORCE_DISCOVER_ON_START        (--init + N)
#   GATEWAY_DEVICES_FILE
#   PYTHONPATH
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

usage() {
    cat <<EOF
Usage: ./local/gateway/start.sh [--sim] [--init] [-h|--help]

Starts the IPBuilding gateway in the foreground (Ctrl+C to stop). HA Core in
~/.homeassistant reaches it at http://127.0.0.1:8080.

Modes
  (default)            Real field bus; passive ARP monitor; existing devices.json
  --sim                Simulated UDP (no real hardware, no discovery)
  --init               Field bus install/refresh (see prompt below)

--init interactive prompt (before the gateway starts):

  Overwrite devices.json? Names, rooms, and active flags will be lost
  (backup -> devices.json.bak).
    [y] Yes - reset and init-sweep from field bus
    [N] No  - merge discovery (keep existing config)

Environment variables used by python -m gateway:

  GATEWAY_SIMULATED                1 with --sim, else 0
  GATEWAY_PASSIVE_ARP_MONITOR      0 with --sim, else 1
  GATEWAY_AUTO_DISCOVER_ON_START   1 with --init and prompt y, else 0
  GATEWAY_FORCE_DISCOVER_ON_START  1 with --init and prompt N, else 0
  GATEWAY_DEVICES_FILE             ./devices.json
  PYTHONPATH                       repo root

Examples
  ./local/gateway/start.sh
  ./local/gateway/start.sh --sim
  ./local/gateway/start.sh --init        # prompt: y = reset, N = merge

See local/README.md for the two-terminal HA workflow.
EOF
}

# --- Argument parsing ---
sim=0
init_mode=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --sim)
            sim=1
            shift
            ;;
        --init)
            init_mode=1
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "error: unknown option '$1'" >&2
            usage >&2
            exit 1
            ;;
        *)
            echo "error: unexpected argument '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ "${sim}" -eq 1 ] && [ "${init_mode}" -eq 1 ]; then
    echo "error: --init requires the real field bus; cannot combine with --sim" >&2
    exit 1
fi

# --- Venv ---
if [ -n "${GATEWAY_VENV:-}" ]; then
    PYTHON_BIN="${GATEWAY_VENV}/bin/python"
elif [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif [ -x "${REPO_ROOT}/venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/venv/bin/python"
else
    echo "error: no gateway venv found (looked in .venv and venv under ${REPO_ROOT})" >&2
    echo "       create one with: python3 -m venv .venv && .venv/bin/pip install -r requirements-gateway.txt" >&2
    exit 1
fi

# --- Sanity check required dependencies ---
# Gateway v0.3.0 introduced `zeroconf` for HA discovery (mDNS broadcast).
# If the venv pre-dates that release the import below will fail with
# `ModuleNotFoundError: No module named 'zeroconf'`. We auto-install on
# first run so the operator doesn't have to remember the requirements.
if ! "${PYTHON_BIN}" -c "import zeroconf" >/dev/null 2>&1; then
    echo "[start.sh] zeroconf not found in venv — installing requirements-gateway.txt"
    "${PYTHON_BIN}" -m pip install -q -r "${REPO_ROOT}/requirements-gateway.txt"
fi

# --- Build env for python -m gateway ---
export GATEWAY_DEVICES_FILE="${GATEWAY_DEVICES_FILE:-./devices.json}"
export PYTHONPATH="${REPO_ROOT}"

simulated=0
passive=1
auto_discover=0
force_discover=0

if [ "${sim}" -eq 1 ]; then
    simulated=1
    passive=0
else
    if [ "${init_mode}" -eq 1 ]; then
        echo
        echo "Overwrite devices.json? Names, rooms, and active flags will be lost"
        echo "(backup -> devices.json.bak)."
        printf "  [y] Yes - reset and init-sweep from field bus\n"
        printf "  [N] No  - merge discovery (keep existing config)\n"
        printf "Choice [y/N]: "
        if [ ! -r /dev/tty ]; then
            echo "error: --init requires an interactive terminal (stdin not a tty)" >&2
            exit 1
        fi
        read -r choice </dev/tty
        case "${choice}" in
            y|Y|yes|YES|Yes)
                if [ -f "./devices.json" ]; then
                    cp ./devices.json ./devices.json.bak
                    echo "backup written to ./devices.json.bak"
                fi
                printf '%s\n' '{"modules":[]}' >./devices.json
                echo "devices.json wiped (modules=[])"
                auto_discover=1
                ;;
            *)
                echo "merge: keeping existing devices.json"
                force_discover=1
                ;;
        esac
    fi
fi

export GATEWAY_SIMULATED="${simulated}"
export GATEWAY_PASSIVE_ARP_MONITOR="${passive}"
export GATEWAY_AUTO_DISCOVER_ON_START="${auto_discover}"
export GATEWAY_FORCE_DISCOVER_ON_START="${force_discover}"

echo "[start.sh] GATEWAY_SIMULATED=${simulated}  passive_arp=${passive}  auto_discover=${auto_discover}  force_discover=${force_discover}"

exec "${PYTHON_BIN}" -m gateway
