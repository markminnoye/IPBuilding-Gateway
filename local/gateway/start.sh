#!/usr/bin/env bash
# Start the simulated gateway on the Mac host. Foreground; Ctrl+C to stop.
# HA Core in ~/.homeassistant reaches it via http://127.0.0.1:8080.
set -euo pipefail

cd "/Users/markminnoye/git/IPBuilding Gateway"

GATEWAY_SIMULATED=1 \
GATEWAY_DEVICES_FILE=./devices.json \
GATEWAY_PASSIVE_ARP_MONITOR=0 \
GATEWAY_AUTO_DISCOVER_ON_START=0 \
PYTHONPATH=. .venv/bin/python -m gateway
