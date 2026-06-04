#!/usr/bin/env bash
# run.sh — HA Supervisor options → GATEWAY_* env vars → gateway entrypoint
#
# Reads /data/options.json (written by HA Supervisor) and exports equivalent
# environment variables before invoking the gateway.

set -e

OPTIONS_FILE="/data/options.json"

# Helper: read a JSON top-level key, return "" if absent or not a string.
json_str() {
    local key="$1"
    local value
    value=$(python3 -c "
import json, sys
try:
    with open('$OPTIONS_FILE') as f:
        opts = json.load(f)
    v = opts.get('$key', '')
    if isinstance(v, str):
        print(v)
    elif v is None:
        print('')
    else:
        print(str(v))
except Exception:
    print('')
" 2>/dev/null || echo "")
    printf '%s' "$value"
}

# Helper: read a JSON top-level key, return the provided default if absent.
json_str_or() {
    local key="$1"
    local default="$2"
    local value
    value=$(json_str "$key")
    if [ -z "$value" ]; then
        printf '%s' "$default"
    else
        printf '%s' "$value"
    fi
}

json_int_or() {
    local key="$1"
    local default="$2"
    local value
    value=$(json_str "$key")
    if [ -z "$value" ]; then
        printf '%s' "$default"
    else
        printf '%s' "$value"
    fi
}

json_bool() {
    local key="$1"
    local value
    value=$(python3 -c "
import json
try:
    with open('$OPTIONS_FILE') as f:
        opts = json.load(f)
    v = opts.get('$key', False)
    print('1' if v else '0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")
    printf '%s' "$value"
}

# ── Network ──────────────────────────────────────────────────────────────────
export GATEWAY_HUB_IP
GATEWAY_HUB_IP=$(json_str_or "hub_ip" "10.10.1.1")

# ── Polling ──────────────────────────────────────────────────────────────────
export GATEWAY_POLL_INTERVAL
GATEWAY_POLL_INTERVAL=$(json_str_or "poll_interval" "2.0")

# ── API ──────────────────────────────────────────────────────────────────────
export GATEWAY_API_PORT
GATEWAY_API_PORT=$(json_int_or "api_port" "8080")

# ── REST Shim (optional, for IPBox migration) ───────────────────────────────
# The shim is always started on 0.0.0.0:30200; we just don't register it
# on the bus unless explicitly enabled.  For simplicity the gateway always
# binds both ports; the shim is a no-op when rest_shim_enabled=false.
export GATEWAY_REST_SHIM_ENABLED
GATEWAY_REST_SHIM_ENABLED=$(json_bool "rest_shim_enabled")

# ── Logging ──────────────────────────────────────────────────────────────────
export GATEWAY_LOG_LEVEL
GATEWAY_LOG_LEVEL=$(json_str_or "log_level" "info")

# ── Persistent devices.json ──────────────────────────────────────────────────
export GATEWAY_DEVICES_FILE
GATEWAY_DEVICES_FILE=$(json_str_or "devices_file" "/data/devices.json")

# ── Discovery / auto-discovery ───────────────────────────────────────────────
export GATEWAY_DISCOVERY_SUBNET
GATEWAY_DISCOVERY_SUBNET=$(json_str_or "discovery_subnet" "10.10.1")

export GATEWAY_DISCOVERY_RANGE_START
GATEWAY_DISCOVERY_RANGE_START=$(json_int_or "discovery_range_start" "0")

export GATEWAY_DISCOVERY_RANGE_END
GATEWAY_DISCOVERY_RANGE_END=$(json_int_or "discovery_range_end" "254")

export GATEWAY_AUTO_DISCOVER_ON_START
GATEWAY_AUTO_DISCOVER_ON_START=$(json_bool "auto_discover_on_start")

export GATEWAY_PASSIVE_ARP_MONITOR
GATEWAY_PASSIVE_ARP_MONITOR=$(json_bool "passive_arp_monitor")

export GATEWAY_ARP_POLL_INTERVAL_S
GATEWAY_ARP_POLL_INTERVAL_S=$(json_str_or "arp_poll_interval_s" "30.0")

export GATEWAY_HTTP_TIMEOUT_S
GATEWAY_HTTP_TIMEOUT_S=$(json_str_or "http_timeout_s" "2.0")

# ── Simulated mode (default off) ─────────────────────────────────────────────
# Set GATEWAY_SIMULATED=1 to run without field hardware during development
export GATEWAY_SIMULATED
GATEWAY_SIMULATED="${GATEWAY_SIMULATED:-0}"

echo "[run.sh] GATEWAY_HUB_IP=$GATEWAY_HUB_IP"
echo "[run.sh] GATEWAY_API_PORT=$GATEWAY_API_PORT"
echo "[run.sh] GATEWAY_DEVICES_FILE=$GATEWAY_DEVICES_FILE"
echo "[run.sh] GATEWAY_REST_SHIM_ENABLED=$GATEWAY_REST_SHIM_ENABLED"
echo "[run.sh] GATEWAY_LOG_LEVEL=$GATEWAY_LOG_LEVEL"
echo "[run.sh] GATEWAY_DISCOVERY_SUBNET=$GATEWAY_DISCOVERY_SUBNET"
echo "[run.sh] GATEWAY_DISCOVERY_RANGE_START=$GATEWAY_DISCOVERY_RANGE_START"
echo "[run.sh] GATEWAY_DISCOVERY_RANGE_END=$GATEWAY_DISCOVERY_RANGE_END"
echo "[run.sh] GATEWAY_AUTO_DISCOVER_ON_START=$GATEWAY_AUTO_DISCOVER_ON_START"
echo "[run.sh] GATEWAY_PASSIVE_ARP_MONITOR=$GATEWAY_PASSIVE_ARP_MONITOR"
echo "[run.sh] GATEWAY_ARP_POLL_INTERVAL_S=$GATEWAY_ARP_POLL_INTERVAL_S"
echo "[run.sh] GATEWAY_HTTP_TIMEOUT_S=$GATEWAY_HTTP_TIMEOUT_S"

# Apply log level
export PYTHON_LOG_LEVEL
case "$GATEWAY_LOG_LEVEL" in
    debug) PYTHON_LOG_LEVEL=DEBUG ;;
    info)  PYTHON_LOG_LEVEL=INFO ;;
    warning) PYTHON_LOG_LEVEL=WARNING ;;
    error) PYTHON_LOG_LEVEL=ERROR ;;
    *) PYTHON_LOG_LEVEL=INFO ;;
esac

# Start the gateway — Entrypoint: python -m gateway (from gateway/ module)
exec python3 -m gateway