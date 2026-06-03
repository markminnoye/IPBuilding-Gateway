# IPBuilding Gateway — WebSocket API

**Endpoint:** `ws://{{gateway_host}}:{{gateway_port}}/ws`
**Heartbeat:** 30 seconds (gateway sends ping / client sends pong)

The WebSocket connection is the primary channel for real-time device state pushed from the gateway to clients. It is also used to send commands bidirectionally.

> **Note:** WebSocket requests cannot be imported via Postman Collection or RapidAPI for Mac import (Postman export limitation — [GitHub #11252](https://github.com/postmanlabs/postman-app-support/issues/11252)). Create the `/ws` request manually in PAW as described below.

---

## Connection

1. In RapidAPI for Mac, create a new **WebSocket** request
2. URL: `ws://{{gateway_host}}:{{gateway_port}}/ws`
3. Enable **heartbeat** (ping/pong every 30 s) — some clients auto-enable this
4. Connect

On connect, the gateway immediately sends a `device_list` snapshot.

---

## Gateway → Client messages

### `device_list` — full snapshot (sent on connect)

```json
{
  "type": "device_list",
  "devices": [
    {
      "id": "10.10.1.30:0",
      "name": "Keuken LED",
      "room": "Keuken",
      "semantic_type": "light",
      "active": true,
      "max_watt": 60,
      "state": "off",
      "current_watt": 0,
      "firmware": "5.1"
    },
    {
      "id": "10.10.1.40:0",
      "name": "Woonkamer Dimmer 1",
      "room": "Woonkamer",
      "semantic_type": "light",
      "active": true,
      "max_watt": 200,
      "state": "on",
      "level": 75,
      "current_watt": 150,
      "firmware": "5.4"
    }
  ]
}
```

### `state_changed` — relay update

```json
{
  "type": "state_changed",
  "id": "10.10.1.30:0",
  "state": "on",
  "max_watt": 60,
  "current_watt": 60
}
```

### `state_changed` — dimmer update

```json
{
  "type": "state_changed",
  "id": "10.10.1.40:0",
  "state": "on",
  "level": 75,
  "max_watt": 200,
  "current_watt": 150
}
```

### `button_event` — input press/release

```json
{
  "type": "button_event",
  "id": "2DE341851900001F",
  "action": "press"
}
```

Possible `action` values: `press`, `release`, `long_press` (firmware-dependent).

---

## Client → Gateway messages

### `command` — relay

```json
{"type": "command", "id": "10.10.1.30:0", "action": "ON"}
{"type": "command", "id": "10.10.1.30:0", "action": "OFF"}
{"type": "command", "id": "10.10.1.30:0", "action": "PULSE"}
```

### `command` — dimmer

```json
{"type": "command", "id": "10.10.1.40:0", "action": "DIM", "value": 75}
```

---

## Gateway → Client ack

### `command_result`

```json
{"type": "command_result", "id": "10.10.1.30:0", "ok": true, "error": null}
{"type": "command_result", "id": "10.10.1.30:0", "ok": false, "error": "unknown entity_id: 10.10.1.99:0"}
```

---

## Saved example messages in PAW

Save these as **example messages** on the `/ws` WebSocket request for quick reuse:

**Relay ON:**
```json
{"type": "command", "id": "10.10.1.30:0", "action": "ON"}
```

**Relay OFF:**
```json
{"type": "command", "id": "10.10.1.30:0", "action": "OFF"}
```

**Dimmer DIM 75:**
```json
{"type": "command", "id": "10.10.1.40:0", "action": "DIM", "value": 75}
```

---

## Entity ID format

All `id` values use `{module_ip}:{channel}` (e.g. `10.10.1.30:0`). The device type is resolved server-side from `devices.json` and is never part of the client-supplied ID. This prevents clients from spoofing device type (e.g. sending a DIM command to a relay module).

---

## Routing button events to HA entities

`button_event.id` is the hardware hex ID from the IP1100PoE (e.g. `2DE341851900001F`). Route these to Home Assistant button entities via the `ipbuilding-gateway-ha` companion automation.

See [ARCHITECTURE.md — §6](../ARCHITECTURE.md#6-northbound-protocol-websocket) for the full sequence diagram and [coordinator.py](../../ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha/coordinator.py) for how button events are dispatched in the HA companion.