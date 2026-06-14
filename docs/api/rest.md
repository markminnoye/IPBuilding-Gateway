# IPBuilding Gateway -- REST API

**Base URL:** `http://{{gateway_host}}:{{gateway_port}}`
**Port:** `8080` (default)

Device-ID format: `{module_ip}-{channel}` (e.g. `10.10.1.30-0`) or an optional custom slug (e.g. `keuken-led`). Device type and physical channel/IP are resolved server-side from `devices.json` -- never supplied by the client.

**Module-ID:** the normalised MAC address of a physical controller (`00:24:77:52:ac:be`). Stable across DHCP IP changes.

---

## GET /api/v1/modules

**Description:** Return all physical field-bus modules with cached network metadata.

**Response 200:**
```json
{
  "modules": [
    {
      "id": "00:24:77:52:ac:be",
      "ip": "10.10.1.30",
      "name": "IP0200PoE",
      "model": "IP0200PoE",
      "type": "relay",
      "firmware": "5.1",
      "mac": "00:24:77:52:ac:be",
      "network": {
        "dhcp": "0",
        "ip": "10.10.1.30",
        "subnet": "255.255.255.0",
        "gateway": "10.10.1.1"
      },
      "button": "0",
      "allow": "",
      "fetched_at": "2026-06-03T18:00:00Z"
    }
  ]
}
```

**Fields per module:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Normalised MAC -- stable module identifier |
| `ip` | string | Current field-bus IP (may change via DHCP) |
| `name` | string | Module name from config |
| `model` | string | Factory model label (e.g. `IP0200PoE`) |
| `type` | string | `relay` / `dimmer` / `input` |
| `firmware` | string | Firmware version from `devices.json` |
| `mac` | string | Same as `id` (explicit for readability) |
| `network` | object | `dhcp`, `ip`, `subnet`, `gateway` from getSysSet |
| `button` | string | HTTP security setting |
| `allow` | string | HTTP access policy |
| `buttons` | array | Input button config (type=input only, from getButtons) |
| `fetched_at` | string | ISO 8601 timestamp of last getSysSet fetch |
| `last_seen` | string | ISO 8601 timestamp of most recent ARP or UDP activity (runtime-only, not in `devices.json`) |
| `last_seen_source` | string | How `last_seen` was last updated: `arp`, `udp`, or `http` (runtime-only) |

---

## GET /api/v1/modules/{module_id}

**Description:** Return a single module by MAC-based module_id.

**Response 200:** single module object (same shape as above).

**Response 404:**
```json
{"error": "not found"}
```

---

## POST /api/v1/modules/refresh

**Description:** Re-fetch getSysSet (and getButtons for input modules) from all field modules. Updates the in-memory cache.

**Request body:** `{}`

**Response 200:** full `{ "modules": [...] }` with refreshed data.

---

## GET /api/v1/devices

**Description:** Return the full device list with current state.

**Response 200:**
```json
{
  "devices": [
    {
      "id": "10.10.1.30-0",
      "module_id": "00:24:77:52:ac:be",
      "module_ip": "10.10.1.30",
      "channel": 0,
      "name": "Keuken LED",
      "room": "Keuken",
      "semantic_type": "light",
      "device_type": "relay",
      "active": true,
      "max_watt": 60,
      "state": "off",
      "current_watt": 0
    },
    {
      "id": "10.10.1.40-0",
      "module_id": "00:24:77:52:9e:a8",
      "module_ip": "10.10.1.40",
      "channel": 0,
      "name": "Living",
      "room": "Gelijkvloers",
      "semantic_type": "light",
      "device_type": "dimmer",
      "active": true,
      "max_watt": 200,
      "state": "on",
      "level": 75,
      "current_watt": 150
    }
  ]
}
```

**Fields per device:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Device-ID: `{module_ip}-{channel}` or custom slug |
| `module_id` | string | Parent module MAC (stable, use for grouping) |
| `module_ip` | string | Current module IP (mutable, use for display) |
| `channel` | integer | Channel index on the module |
| `name` | string | Channel name from `devices.json` |
| `room` | string | Room from config |
| `semantic_type` | string | `light` / `fan` / `switch` |
| `device_type` | string | `relay` / `dimmer` / `input` |
| `active` | boolean | Whether channel is active |
| `max_watt` | integer | Configured maximum power |
| `state` | string | `on` / `off` / `inactive` / `unknown` |
| `current_watt` | integer | Current consumption (0 when off) |
| `level` | integer | Dimmer percentage 0-100 (dimmer only) |

**Inactive channels** (`active: false` in `devices.json`) are still included in the
response so the companion can show them as disabled+hidden entities. Their
`state` is always `"inactive"` (channel disabled in `devices.json`) and
`current_watt` is `0`. A `state` of `"unknown"` means the channel is active in
config but no recent fieldbus response was received. Commands to inactive
channels are rejected by `POST /api/v1/devices/{id}/command` with HTTP 422
and a `"channel inactive"` error.

---

## GET /api/v1/devices/{device_id}

**Description:** Return a single device by device-ID.

**Response 200:** see `devices[0]` structure above.

**Response 404:**
```json
{"error": "not found"}
```

---

## POST /api/v1/devices/{device_id}/command

**Description:** Send a command to a relay or dimmer channel.

**Request headers:** `Content-Type: application/json`

**Request body -- Relay:**
```json
{"action": "ON"}
{"action": "OFF"}
{"action": "PULSE"}
{"action": "TOGGLE"}
```

**Request body -- Dimmer:**
```json
{"action": "DIM", "value": 75}
```

| Action | Valid for | Value |
|--------|-----------|-------|
| `ON` | Relay | -- |
| `OFF` | Relay | -- |
| `PULSE` | Relay | -- |
| `TOGGLE` | Relay | -- |
| `DIM` | Dimmer | `0-100` (0 = off) |

**Response 200:**
```json
{"ok": true}
```

**Response 400** (missing action):
```json
{"ok": false, "error": "missing 'action'"}
```

**Response 422** (unsupported action):
```json
{"ok": false, "error": "unsupported relay action: FOO"}
```

---

## POST /api/v1/discover

**Description:** Trigger a forced discovery sweep (ARP-first + HTTP identify). Ignores the `passive_arp_monitor` and `auto_discover_on_start` toggles. Always available.

**Request body:** `{}`

**Response 200:**
```json
{
  "ok": true,
  "added": ["00:24:77:52:ac:be"],
  "changed": [],
  "removed": [],
  "duration_ms": 2341
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | `true` if sweep completed |
| `added` | array of MAC strings | Modules newly discovered (written to `devices.json` with `active: false`) |
| `changed` | array of MAC strings | Modules where firmware or IP changed |
| `removed` | array of MAC strings | Modules not seen after N polls (runtime-only; not removed from `devices.json`) |
| `duration_ms` | integer | Time taken for the full sweep in milliseconds |

**Response 200 (no changes):**
```json
{"ok": true, "added": [], "changed": [], "removed": [], "duration_ms": 512}
```

---

## POST /api/v1/provision/autonomy

**Description:** EEPROM sync to IP1100PoE (saveAutonomy). Stub -- not implemented (Fase 8).

**Request body:** `{}`

**Response 501:**
```json
{"ok": false, "error": "not yet implemented"}
```

---

See also:
- [`websocket.md`](websocket.md) -- WebSocket message catalog
- [`modules.md`](modules.md) -- Module resource reference
- [`ipbuilding-gateway.postman_collection.json`](ipbuilding-gateway.postman_collection.json) -- importable in RapidAPI for Mac
- [`ARCHITECTURE.md`](../../ARCHITECTURE.md) -- architecture context
