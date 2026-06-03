"""Constants for ipbuilding_gateway_ha."""

from homeassistant.const import CONF_HOST, CONF_PORT

DOMAIN = "ipbuilding_gateway_ha"

CONF_API_HOST = CONF_HOST
CONF_API_PORT = CONF_PORT

DEFAULT_API_PORT = 8080

# Entity device types
DEVICE_TYPE_RELAY = "relay"
DEVICE_TYPE_DIMMER = "dimmer"
DEVICE_TYPE_INPUT = "input"

# Semantic types
SEMANTIC_TYPE_LIGHT = "light"
SEMANTIC_TYPE_SWITCH = "switch"
SEMANTIC_TYPE_FAN = "fan"
SEMANTIC_TYPE_PLUG = "plug"
SEMANTIC_TYPE_COVER = "cover"
SEMANTIC_TYPE_SENSOR = "sensor"

# WS reconnect delays (seconds)
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
RECONNECT_BACKOFF_MULT = 2.0

# Polling interval for REST fallback (if WS unavailable)
REST_POLL_INTERVAL = 30.0  # seconds