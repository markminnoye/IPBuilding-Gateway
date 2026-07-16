#!/usr/bin/env bash
# run.sh — HA Supervisor options → GATEWAY_* env vars → gateway entrypoint
#
# Reads /data/options.json (written by HA Supervisor) and exports equivalent
# environment variables before invoking the gateway.
# Supports nested option groups (network, fieldbus, …) with fallback to legacy
# flat top-level keys for existing installations.

set -e

OPTIONS_FILE="/data/options.json"

# Read nested or flat option from options.json; print default if missing.
# Usage: opt nested.path flat_key default
opt() {
    local nested_path="$1"
    local flat_key="$2"
    local default="$3"
    python3 -c "
import json, sys
nested = '''$nested_path'''.split('.')
flat = '''$flat_key'''
default = '''$default'''
try:
    with open('$OPTIONS_FILE') as f:
        opts = json.load(f)
except Exception:
    print(default)
    sys.exit(0)
cur = opts
for part in nested:
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        cur = None
        break
if cur is None or cur == '':
    cur = opts.get(flat, default)
if isinstance(cur, bool):
    print('1' if cur else '0')
elif cur is None:
    print(default)
else:
    print(cur)
" 2>/dev/null || printf '%s' "$default"
}

# ── Field bus / modules ──────────────────────────────────────────────────────
export GATEWAY_POLL_INTERVAL
GATEWAY_POLL_INTERVAL=$(opt fieldbus.poll_interval poll_interval "2.0")

export GATEWAY_ACTUATOR_POLL_INTERVAL
GATEWAY_ACTUATOR_POLL_INTERVAL=$(opt fieldbus.actuator_poll_interval actuator_poll_interval "20.0")

# Buttons via HA (bool). Prefer new key; fall back to legacy hub_role slave|master.
export GATEWAY_BUTTONS_VIA_HA
_BVH=$(opt fieldbus.buttons_via_ha buttons_via_ha "")
if [ -n "$_BVH" ]; then
    GATEWAY_BUTTONS_VIA_HA="$_BVH"
else
    _ROLE=$(opt fieldbus.hub_role hub_role "")
    if [ -z "$_ROLE" ] && [ -n "${GATEWAY_HUB_ROLE:-}" ]; then
        _ROLE="$GATEWAY_HUB_ROLE"
    fi
    case "$(printf '%s' "$_ROLE" | tr '[:upper:]' '[:lower:]')" in
        master)
            GATEWAY_BUTTONS_VIA_HA=0
            echo "[run.sh] Migrated legacy hub_role=master → GATEWAY_BUTTONS_VIA_HA=0"
            ;;
        slave|"")
            GATEWAY_BUTTONS_VIA_HA=1
            if [ -n "$_ROLE" ]; then
                echo "[run.sh] Migrated legacy hub_role=slave → GATEWAY_BUTTONS_VIA_HA=1"
            fi
            ;;
        *)
            GATEWAY_BUTTONS_VIA_HA=1
            echo "[run.sh] Unknown legacy hub_role='$_ROLE' — using GATEWAY_BUTTONS_VIA_HA=1"
            ;;
    esac
fi
unset _BVH _ROLE

# ── Network ──────────────────────────────────────────────────────────────────
export GATEWAY_BIND_IP
GATEWAY_BIND_IP=$(opt network.bind_ip bind_ip "0.0.0.0")

export GATEWAY_REST_SHIM_ENABLED
GATEWAY_REST_SHIM_ENABLED=$(opt network.rest_shim_enabled rest_shim_enabled "0")

export GATEWAY_HTTP_TIMEOUT_S
GATEWAY_HTTP_TIMEOUT_S=$(opt network.http_timeout_s http_timeout_s "2.0")

export GATEWAY_METADATA_TIMEOUT_S
GATEWAY_METADATA_TIMEOUT_S=$(opt network.metadata_timeout_s metadata_timeout_s "5.0")

# ── Installation ─────────────────────────────────────────────────────────────
export GATEWAY_DEVICES_FILE
GATEWAY_DEVICES_FILE=$(opt installation.devices_file devices_file "/config/devices.json")

export GATEWAY_EXPOSE_INACTIVE_CHANNELS
GATEWAY_EXPOSE_INACTIVE_CHANNELS=$(opt installation.expose_inactive_channels expose_inactive_channels "0")

mkdir -p "$(dirname "$GATEWAY_DEVICES_FILE")"

# One-time migration from the pre-0.3.4 internal /data volume.
if [ "$GATEWAY_DEVICES_FILE" = "/data/devices.json" ] && [ -f /data/devices.json ]; then
    if [ ! -f /config/devices.json ]; then
        cp -a /data/devices.json /config/devices.json
        echo "[run.sh] Migrated devices.json from /data to /config"
    fi
    GATEWAY_DEVICES_FILE="/config/devices.json"
elif [ ! -f "$GATEWAY_DEVICES_FILE" ] && [ -f /data/devices.json ]; then
    cp -a /data/devices.json "$GATEWAY_DEVICES_FILE"
    echo "[run.sh] Migrated devices.json from /data to $GATEWAY_DEVICES_FILE"
fi
export GATEWAY_DEVICES_FILE

# ── Discovery ────────────────────────────────────────────────────────────────
export GATEWAY_DISCOVERY_SUBNET
GATEWAY_DISCOVERY_SUBNET=$(opt discovery.discovery_subnet discovery_subnet "10.10.1")

export GATEWAY_DISCOVERY_RANGE_START
GATEWAY_DISCOVERY_RANGE_START=$(opt discovery.discovery_range_start discovery_range_start "0")

export GATEWAY_DISCOVERY_RANGE_END
GATEWAY_DISCOVERY_RANGE_END=$(opt discovery.discovery_range_end discovery_range_end "254")

export GATEWAY_AUTO_DISCOVER_ON_START
GATEWAY_AUTO_DISCOVER_ON_START=$(opt discovery.auto_discover_on_start auto_discover_on_start "0")

export GATEWAY_PASSIVE_ARP_MONITOR
GATEWAY_PASSIVE_ARP_MONITOR=$(opt discovery.passive_arp_monitor passive_arp_monitor "1")

export GATEWAY_ARP_POLL_INTERVAL_S
GATEWAY_ARP_POLL_INTERVAL_S=$(opt discovery.arp_poll_interval_s arp_poll_interval_s "30.0")

export GATEWAY_USE_ENV_DEFAULTS
GATEWAY_USE_ENV_DEFAULTS=$(opt discovery.use_env_defaults use_env_defaults "0")

# ── Logging ──────────────────────────────────────────────────────────────────
export GATEWAY_LOG_LEVEL
GATEWAY_LOG_LEVEL=$(opt logging.log_level log_level "info")

# ── Simulated mode (default off) ─────────────────────────────────────────────
export GATEWAY_SIMULATED
GATEWAY_SIMULATED="${GATEWAY_SIMULATED:-0}"

echo "[run.sh] GATEWAY_POLL_INTERVAL=$GATEWAY_POLL_INTERVAL"
echo "[run.sh] GATEWAY_ACTUATOR_POLL_INTERVAL=$GATEWAY_ACTUATOR_POLL_INTERVAL"
echo "[run.sh] GATEWAY_BUTTONS_VIA_HA=$GATEWAY_BUTTONS_VIA_HA"
echo "[run.sh] GATEWAY_BIND_IP=$GATEWAY_BIND_IP"
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
echo "[run.sh] GATEWAY_USE_ENV_DEFAULTS=$GATEWAY_USE_ENV_DEFAULTS"

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
