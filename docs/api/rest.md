# IPBuilding Gateway -- REST API

**Base URL:** `http://{{gateway_host}}:{{gateway_port}}`
**Port:** `8080` (default)

Device-ID format: `{module_ip}-{channel}` (e.g. `10.10.1.30-0`) or an optional custom slug (e.g. `keuken-led`). Device type and physical channel/IP are resolved server-side from `devices.json` -- never supplied by the client.

**Module-ID:** the normalised MAC address of a physical controller (`00:24:77:52:ac:be`). Stable across DHCP IP changes.

**Ingress / Web UI:** `GET /` serves a self-contained HTML page (device list + inline edit via the existing `PATCH /api/v1/devices/{id}` endpoint) when the add-on is opened through HA Supervisor's "Open Web UI" / Ingress panel. Not a documented API contract -- internal to the add-on UI.

---

## GET /health

**Description:** Liveness probe for the HA Supervisor watchdog. Minimal status + gateway version.

**Response 200:**
```json
{
  "status": "ok",
  "version": "0.4.0"
}
```

`status` is `ok` | `degraded` | `unhealthy` (same enum as `/api/v1/status`).

---

## GET /api/v1/status

**Description:** Full gateway health snapshot for operators and the HA companion.

**Response 200:**
```json
{
  "status": "degraded",
  "version": "0.4.0",
  "uptime_seconds": 8642,
  "updated_at": "2026-06-15T11:42:00Z",
  "subsystems": {
    "installation": "ok",
    "module_metadata": "degraded",
    "discovery": "ok"
  },
  "issues": [
    {
      "id": "module_metadata.getSysSet.10.10.1.30",
      "level": "warning",
      "code": "module_metadata.http_failed",
      "technical": "HTTP getSysSet 10.10.1.30 failed: timeout",
      "message": "Module 10.10.1.30 is not responding to getSysSet configuration requests",
      "context": { "ip": "10.10.1.30", "method": "getSysSet" },
      "since": "2026-06-15T11:40:00Z"
    }
  ],
  "buttons_via_ha": true,
  "hub_role": "slave",
  "input_mode_label": "Slave",
  "multi_press": false,
  "multi_press_window_ms": 350,
  "remote_debugging": false,
  "capabilities": ["log_stream", "udp_frame", "module_reachability"],
  "actions": {
    "discover": { "method": "POST", "path": "/api/v1/discover" },
    "refresh_modules": { "method": "POST", "path": "/api/v1/modules/refresh" }
  }
}
```

Push updates are sent on WebSocket as `gateway_status` when aggregate `status` or open issues change. See [websocket.md](websocket.md).

| Field | Type | Description |
|-------|------|-------------|
| `buttons_via_ha` | boolean | When `true`, wall buttons are polled and sent to HA; when `false`, buttons stay local on the input module. |
| `hub_role` | string | Derived IP1100 term: `slave` if `buttons_via_ha`, else `master` (LED meaning). |
| `input_mode_label` | string | Operator label: `Slave` / `Master`. |
| `multi_press` | boolean | Global double/triple-press classification for all wall buttons (add-on option). When `false`, short release emits `single_press` immediately. |
| `multi_press_window_ms` | integer | Inter-click window in ms when `multi_press` is enabled (default 350). |
| `remote_debugging` | boolean | Add-on option **Remote control (for debugging)**. `false` until a user turns it on in the add-on configuration. It stays on until they turn it off. While it is on, anyone on the network can read field-bus traffic and send raw packets through this gateway. Check this field before calling a remote-debugging route. |
| `capabilities` | list of strings | Features this gateway build actually implements. `log_stream` is live logs over WebSocket. `udp_frame` is live field-bus frames over WebSocket (`subscribe_udp_frames`). `module_reachability` is command confirmation and per-module reply timing (see below); it does not depend on `remote_debugging`. A later build may add `raw_send`. The list stays present when `remote_debugging` is `false`, so a client can tell “this build has the feature” from “the option is off”. Unknown extra fields are safe for older clients. |

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
| `reachability` | object | Reply timing for this module. Always present. See the fields below. |

`reachability` is filled from field-bus traffic the gateway already sends and receives (keepalive and commands). It is not written to `devices.json`. `last_seen` stays the ARP/HTTP contact time; `reachability.last_reply_at` is the last inbound UDP packet from that module.

```json
"reachability": {
  "last_reply_at": "2026-10-08T12:00:00+00:00",
  "last_reply_ms": 18,
  "avg_reply_ms": 22,
  "missed_replies": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `last_reply_at` | string or null | ISO 8601 UTC time of the last inbound UDP packet from this module. `null` until one arrives. |
| `last_reply_ms` | integer or null | Milliseconds from the latest unanswered send to the reply that landed inside the reply window. `null` when no reply has been paired yet. |
| `avg_reply_ms` | integer or null | Rounded mean of the last 20 paired response times. `null` when there is no sample. |
| `missed_replies` | integer | Sends whose reply window closed with no reply. A newer send inside the window replaces the pending one and is not a miss. |

The same object is on `GET /api/v1/modules/{module_id}` and on each module in the WebSocket `snapshot`. A module that has not answered yet:

```json
"reachability": {
  "last_reply_at": null,
  "last_reply_ms": null,
  "avg_reply_ms": null,
  "missed_replies": 0
}
```

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

**Description:** Re-fetch getSysSet (and getButtons for input modules) from all field modules. For relay/dimmer modules also fetches `backupConfig` and merges channel slots into `devices.json`. Updates the in-memory metadata cache.

**Request body:** `{}`

**Response 200:** full `{ "modules": [...] }` with refreshed data. Each module includes `reachability`.

---

## POST /api/v1/modules/reachability

**Description:** Ask every configured module for one keepalive reply and report how fast it answered. The gateway sends the same poll payload the poll loop already uses (`P0000` for a relay, `I9900` for a dimmer, `I0000` for an input). It does not move poll timers. Probes run together. At most one sweep is accepted every 10 seconds.

Input modules are not probed when this gateway does not claim them (`buttons_via_ha` is false). Those modules are returned as `none` and nothing is sent to them.

Requires capability `module_reachability` on `GET /api/v1/status`. The route is available while `remote_debugging` is false.

**Request body:** `{}` (ignored).

**Response 200:**

```json
{
  "ok": true,
  "schema_version": 2,
  "modules": [
    {"id": "02:00:00:00:00:01", "reachability": "ok", "reply_ms": 40},
    {"id": "02:00:00:00:00:02", "reachability": "slow", "reply_ms": 250},
    {"id": "02:00:00:00:00:03", "reachability": "none", "reply_ms": null}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Northbound module id: MAC when known, otherwise the module IP. |
| `reachability` | string | `ok` when the reply arrived within 200 ms, `slow` when it arrived later but still inside the reply window, `none` when there was no reply, the type is unknown, or an input module was not claimed. |
| `reply_ms` | integer or null | Milliseconds from the probe send to that reply. `null` when `reachability` is `none`. |

A missing reply is not an error. The HTTP status stays 200 and that module is `none`.

**Response 429** — another sweep was requested before 10 seconds had passed:

```json
{
  "error": "reachability_rate_limited",
  "message": "Reachability check is rate limited. Wait and try again."
}
```

**Response 500** — no installation is loaded (`no_installation`). That response does not consume the 10-second window.

---

## POST /api/v1/modules/{module_id}/refresh

**Description:** Re-fetch getSysSet (and getButtons for input modules) from a single module identified by MAC. For relay/dimmer modules also merges `backupConfig` channel slots into `devices.json`. Updates the in-memory cache for that module only and broadcasts a WebSocket snapshot.

**Request body:** none

**Response 200:** single module object (same shape as `GET /api/v1/modules/{module_id}`) plus `"schema_version": 2`.

**Response 404:** `{ "error": "module_not_found", ... }` when the MAC is not in `devices.json`.

---

## GET /api/v1/devices

**Description:** Return the device list with current state.

**Query parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `include_inactive` | follows add-on `expose_inactive_channels` | When `true`, include relay/dimmer channels with `active: false`. The Web UI uses `?include_inactive=true`. |

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
    },
    {
      "id": "2f8185df",
      "module_id": "00:24:77:52:ad:aa",
      "module_ip": "10.10.1.50",
      "channel": 1,
      "name": "Badkamer knop",
      "room": "1e verdieping",
      "semantic_type": "button",
      "device_type": "input",
      "active": true
    }
  ]
}
```

**Fields per device:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Device-ID: `{module_ip}-{channel}` (relay/dimmer) or `custom slug`, or the IP1100PoE button **hardware id** (lowercase, 8 hex chars) for input modules |
| `module_id` | string | Parent module MAC (stable, use for grouping) |
| `module_ip` | string | Current module IP (mutable, use for display) |
| `channel` | integer | Channel index on the module (relay/dimmer), or physical wiring position for buttons. For buttons this is **read-only** (from the module's physical wiring), not PATCH-able |
| `name` | string | Channel name from `devices.json` (or `descr` from `getButtons` for input) |
| `room` | string | Room from config (or `gr` from `getButtons` for input) |
| `semantic_type` | string | `light` / `fan` / `switch` / `button` (dimmer channels are always `light`) |
| `device_type` | string | `relay` / `dimmer` / `input` |
| `active` | boolean | Whether channel is active |
| `max_watt` | integer | Configured maximum power (relay/dimmer only) |
| `state` | string | `on` / `off` / `inactive` / `unknown` (relay/dimmer only) |
| `current_watt` | integer | Current consumption (0 when off; relay/dimmer only) |
| `level` | integer | Dimmer percentage 0-100 (dimmer only) |

**Input modules (`device_type: "input"`)** carry one entry per physical button
from `devices.json` `modules[].pushbuttons[]` (canonical inventory). Cached
HTTP `getButtons` on the IP1100PoE only **enriches** empty `name` / `room` /
`channel` when the same normalized hardware id is present. Live presses arrive
as `button_event` on the WebSocket; a first press for an unknown id is
**learned** into `devices.json` and announced via `device_added`
(`semantic_type: "button"`) before the `button_event`. There is no
`state`/`max_watt` — buttons are event-only. `channel` is present but
**read-only**. The `id` matches `button_event.id`. When `name` is empty on
disk, the snapshot may show a display fallback `Button {id}` (not written
back). Soft retention: pushbuttons are never auto-removed when absent from
`getButtons`. Multi-press is a **global** add-on option — see
`GET /api/v1/status` (`multi_press` / `multi_press_window_ms`).

**Inactive channels** (`active: false` in `devices.json`) are **omitted** from
the list unless add-on `expose_inactive_channels` is enabled or the client
passes `?include_inactive=true`. When included, their `state` is always
`"inactive"` and `current_watt` is `0`. `GET /api/v1/devices/{device_id}` and
`PATCH` still work by device id. Commands to inactive channels are rejected
with HTTP 422 and a `"channel inactive"` error.

---

## GET /api/v1/devices/{device_id}

**Description:** Return a single device by device-ID.

**Response 200:** see `devices[0]` structure above.

**Response 404:**
```json
{"error": "not found"}
```

---

## PATCH /api/v1/devices/{device_id}

**Description:** Update northbound-only configuration fields for a channel or button in `devices.json` at runtime. Changes are persisted atomically (advisory lock + tempfile rename) and do not require a gateway restart. A WebSocket `snapshot` broadcast is sent to all connected clients after a successful patch.

**Allowed fields — channel (relay/dimmer):**

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Operator-friendly label |
| `room` | string | Room / area name |
| `semantic_type` | string | One of: `light`, `fan`, `cover`, `switch`, `plug`. Dimmer channels only accept `light` (PATCH rejects other values; import/load normalizes to `light`). |
| `active` | boolean | `false` = do not poll or expose |
| `max_watt` | integer | Non-negative wattage cap |

**Allowed fields — button (IP1100PoE, id from `devices.json` `modules[].pushbuttons[]`):**

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Operator-friendly label |
| `room` | string | Room / area name |
| `active` | boolean | `false` = disable button entity |

Any other field (e.g. `ip`, `mac`, `type`, `hold_threshold_s`, `multi_press`) returns **400** `unknown_field`. Multi-press is configured globally via the add-on options (see `GET /api/v1/status`).

**Request headers:** `Content-Type: application/json`

**Request body example (channel):**
```json
{"room": "Keuken", "semantic_type": "light", "active": true, "max_watt": 60}
```

**Request body example (button):**
```json
{"name": "Badkamer knop", "room": "1e verdieping", "active": true}
```

**Response 200:** Same shape as `GET /api/v1/devices/{device_id}` for the updated device, plus `schema_version: 2`.

**Response 400** (invalid JSON):
```json
{"error": "invalid_json", "message": "Body must be valid JSON"}
```

**Response 400** (empty body — no fields to update):
```json
{"error": "empty_body", "message": "Body must include at least one field to update"}
```

**Response 400** (unknown field):
```json
{"error": "unknown_field", "message": "Unknown field(s): ip", "details": {"fields": ["ip"]}}
```

**Response 400** (validation):
```json
{"error": "validation", "message": "semantic_type must be one of ['cover', 'fan', 'light', 'plug', 'switch']"}
```

**Response 404:**
```json
{"error": "device_not_found", "details": {"device_id": "10.10.1.99-0"}}
```

**Response 503** (lock timeout — another writer holds `devices.json.lock`):
```json
{"error": "write_locked", "message": "devices.json is locked; retry later"}
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

**Response 200:** the gateway accepted and sent the command. A missing field-bus reply is still `ok: true`. It is not an error.

```json
{
  "ok": true,
  "schema_version": 2,
  "module_confirmed": true,
  "confirm_ms": 42,
  "reported": {"state": "on"}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | `true` when the command was sent. `false` is not used on this status; failures use 4xx below. |
| `schema_version` | integer | `2`. |
| `module_confirmed` | boolean | `true` when a reply from that module arrived inside the reply window (`reply_timeout_ms`, default 500) and the reply has a timestamp. `false` when no reply arrived. |
| `confirm_ms` | integer or null | Milliseconds from the send to that reply. `null` when `module_confirmed` is false. |
| `reported` | object or null | State taken from the reply. A relay status contributes `state` (`on`, `off`, or `unknown`). A dimmer status contributes `level_percent`. `null` when the reply is missing or is not a known status. A confirmed reply can still have `reported: null`. |

No reply inside the window:

```json
{
  "ok": true,
  "schema_version": 2,
  "module_confirmed": false,
  "confirm_ms": null,
  "reported": null
}
```

`DIM_START` does not wait for a status reply. Its 200 body is `module_confirmed: false`, `confirm_ms: null`, `reported: null`, and the send is not counted as a missed reply.

The WebSocket `command_result` frame carries the same three fields. See [websocket.md](websocket.md).

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

## POST /api/v1/debug/log-level

**Description:** Raise or lower the gateway log level for a limited time. The change applies to the whole process (including the Home Assistant add-on log) and is **not** written to add-on options or `GATEWAY_LOG_LEVEL`. When several requests overlap, the most verbose level wins. Each request expires on its own `ttl`. The level is never set quieter than the configured baseline.

There is no login on port 8080. While **Remote control (for debugging)** is on, anyone who can reach this port can change the level and read logs. Token- and password-like values in log lines are redacted. Turn the option off when finished.

**Request body:**
```json
{"level": "debug", "ttl": 900}
```

`level`: `debug`, `info`, `warning`, or `error` (case-insensitive). `ttl`: integer seconds from 1 to 3600. Required. Boolean `true` is rejected.

**Response 200:**
```json
{
  "ok": true,
  "level": "debug",
  "ttl": 900,
  "effective_level": "debug"
}
```

`effective_level` is the level actually applied. A request quieter than the configured baseline leaves the baseline in place.

**Response 403** — remote debugging is off. The same code and sentence are returned on the WebSocket. `GET /api/v1/status` stays available so a client can read `remote_debugging` and `capabilities` before calling this route.

```json
{
  "error": "remote_debugging_disabled",
  "message": "Remote debugging is off. Turn on \"Remote control (for debugging)\" (Nederlands: \"Bediening op afstand (voor debuggen)\") under Settings > Add-ons > IPBuilding Gateway > Configuration."
}
```

| Field | Meaning |
|-------|---------|
| `error` | Stable code `remote_debugging_disabled`. WebSocket `subscribe_udp_frames` uses this same code when the option is off. A later raw-send route will too. |
| `message` | English hint. Names the add-on option in English and Dutch, and where to find it. |

**Response 400:** `invalid_json`, `invalid_log_level`, or `invalid_ttl`.

**Response 429:** `log_level_rate_limited` — more than 10 level changes in 60 seconds from REST.

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
