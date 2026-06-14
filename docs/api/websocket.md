# IPBuilding Gateway -- WebSocket API

**Endpoint:** `ws://{{gateway_host}}:{{gateway_port}}/ws`
**Heartbeat:** 30 seconds (gateway sends ping / client sends pong)

The WebSocket connection is the primary channel for real-time device state pushed from the gateway to clients. It is also used to send commands bidirectionally.

> **Note:** WebSocket requests cannot be imported via Postman Collection or RapidAPI for Mac import (Postman export limitation -- [GitHub #11252](https://github.com/postmanlabs/postman-app-support/issues/11252)). Create the `/ws` request manually in PAW as described below.

---

## Connection

1. In RapidAPI for Mac, create a new **WebSocket** request
2. URL: `ws://{{gateway_host}}:{{gateway_port}}/ws`
3. Enable **heartbeat** (ping/pong every 30 s) -- some clients auto-enable this
4. Connect

On connect, the gateway immediately sends a `snapshot` message containing both modules and devices.

---

## Gateway -> Client messages

### `snapshot` -- full snapshot (sent on connect)

Contains physical modules (with firmware, network config, MAC) and logical devices (channels with current state). Replaces the old `device_list` message.

```json
{
  "type": "snapshot",
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
    },
    {
      "id": "00:24:77:52:9e:a8",
      "ip": "10.10.1.40",
      "name": "IP0300PoE",
      "model": "IP0300PoE",
      "type": "dimmer",
      "firmware": "5.4",
      "mac": "00:24:77:52:9e:a8",
      "network": {},
      "button": "",
      "allow": ""
    },
    {
      "id": "00:24:77:52:ad:aa",
      "ip": "10.10.1.50",
      "name": "IP1100PoE",
      "model": "IP1100PoE",
      "type": "input",
      "firmware": "5.2.4",
      "mac": "00:24:77:52:ad:aa",
      "network": {},
      "button": "",
      "allow": "",
      "buttons": [
        {
          "index": 0,
          "id": "2D2F8185190000DF",
          "descr": "Badkamer knop",
          "gr": "1e verdieping",
          "func1": {"ip": "30", "ch": 0, "outType": "relay", "action": "on"},
          "func2": null
        }
      ]
    }
  ],
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

The `devices` array includes channels with `active: false` from `devices.json`.
Their `state` is fixed to `"unknown"` and `current_watt` to `0`. The companion
creates disabled+hidden entities for them. `state_changed` is **not** emitted
for inactive channels.

### `state_changed` -- relay update

```json
{
  "type": "state_changed",
  "id": "10.10.1.30-0",
  "state": "on",
  "max_watt": 60,
  "current_watt": 60
}
```

### `state_changed` -- dimmer update

```json
{
  "type": "state_changed",
  "id": "10.10.1.40-0",
  "state": "on",
  "level": 75,
  "max_watt": 200,
  "current_watt": 150
}
```

### `button_event` -- input press/release

```json
{
  "type": "button_event",
  "id": "2DE341851900001F",
  "action": "press"
}
```

Possible `action` values: `press`, `release`, `long_press` (firmware-dependent).

### `device_added` -- new module detected

Emitted by the passive ARP monitor or after a forced/init discovery sweep. The module has been written to `devices.json` with `active: false` and `room: "Unconfigured"`.

```json
{
  "type": "device_added",
  "id": "00:24:77:52:ac:be",
  "ip": "10.10.1.55",
  "type": "unknown",
  "model": "",
  "firmware": "",
  "mac": "00:24:77:52:ac:be",
  "first_seen": "2026-06-04T20:15:00Z",
  "last_seen": "2026-06-04T20:15:00Z",
  "source": "arp"
}
```

### `device_removed` -- module not seen for N polls

Emitted after `removed_after_n_polls` (default 3) consecutive ARP polls without seeing this MAC. The module remains in `devices.json`; it is marked `unreachable` in the runtime registry.

```json
{
  "type": "device_removed",
  "id": "00:24:77:52:ac:be",
  "last_seen": "2026-06-04T19:58:00Z"
}
```

### `device_ip_changed` -- DHCP IP change detected

Emitted when a known MAC is seen on a different IP. The runtime registry is updated; `devices.json` is NOT modified.

```json
{
  "type": "device_ip_changed",
  "id": "00:24:77:52:ac:be",
  "old_ip": "10.10.1.30",
  "new_ip": "10.10.1.42"
}
```

### `device_firmware_changed` -- firmware version changed

Emitted after HTTP identify detects a different firmware version than stored in `devices.json`. The `devices.json` is updated atomically.

```json
{
  "type": "device_firmware_changed",
  "id": "00:24:77:52:ac:be",
  "old_firmware": "5.1",
  "new_firmware": "5.2"
}
```

### `discovery_completed` -- init or forced sweep finished

Emitted after a forced sweep (`POST /api/v1/discover` or WS `discover` message) or an init sweep completes.

```json
{
  "type": "discovery_completed",
  "trigger": "forced",
  "added": ["00:24:77:52:ac:be"],
  "changed": ["00:24:77:52:9e:a8"],
  "removed": [],
  "duration_ms": 2341
}
```

`trigger`: `"init" | "passive" | "forced"`.

---

## Client -> Gateway messages

### `discover` -- force discovery sweep

Trigger the same ARP-first + HTTP discovery as `POST /api/v1/discover`. Ignores toggles.

```json
{"type": "discover"}
```

The gateway responds with a `discovery_completed` event (see below).

### `command` -- relay

```json
{"type": "command", "id": "10.10.1.30-0", "action": "ON"}
{"type": "command", "id": "10.10.1.30-0", "action": "OFF"}
{"type": "command", "id": "10.10.1.30-0", "action": "PULSE"}
```

### `command` -- dimmer

```json
{"type": "command", "id": "10.10.1.40-0", "action": "DIM", "value": 75}
```

---

## Gateway -> Client ack

### `command_result`

```json
{"type": "command_result", "id": "10.10.1.30-0", "ok": true, "error": null}
{"type": "command_result", "id": "10.10.1.30-0", "ok": false, "error": "unknown device_id: 10.10.1.99-0"}
```

---

## Saved example messages in PAW

Save these as **example messages** on the `/ws` WebSocket request for quick reuse:

**Relay ON:**
```json
{"type": "command", "id": "10.10.1.30-0", "action": "ON"}
```

**Relay OFF:**
```json
{"type": "command", "id": "10.10.1.30-0", "action": "OFF"}
```

**Dimmer DIM 75:**
```json
{"type": "command", "id": "10.10.1.40-0", "action": "DIM", "value": 75}
```

---

## Device ID format

All `id` values use `{module_ip}-{channel}` (e.g. `10.10.1.30-0`) or a custom slug (e.g. `keuken-led`). The device type is resolved server-side from `devices.json` and is never part of the client-supplied ID. This prevents clients from spoofing device type (e.g. sending a DIM command to a relay module).

The `module_id` field on each device contains the stable MAC of the parent module. Use `module_id` to group devices by module or join with the `modules[]` list. Use `module_ip` for display; it can change if the module receives a new DHCP address.

---

## Routing button events to HA entities

`button_event.id` is the hardware hex ID from the IP1100PoE (e.g. `2DE341851900001F`). Route these to Home Assistant button entities via the `ipbuilding-gateway-ha` companion automation.

See [ARCHITECTURE.md -- section 6](../../ARCHITECTURE.md#6-northbound-protocol-websocket) for the full sequence diagram and [`coordinator.py`](https://github.com/markminnoye/ipbuilding-gateway-ha/blob/main/custom_components/ipbuilding_gateway_ha/coordinator.py) in the companion repo for how button events are dispatched in HA.
