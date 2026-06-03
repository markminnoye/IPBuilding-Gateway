# IPBuilding Gateway — REST API

**Base URL:** `http://{{gateway_host}}:{{gateway_port}}`
**Poort:** `8080` (default)

Entity-ID formaat: `{module_ip}:{channel}` (bijv. `10.10.1.30:0`). Device type wordt server-side resolved uit `devices.json` — nooit door client meegegeven.

---

## GET /api/v1/devices

**Beschrijving:** Retourneer de volledige device lijst met huidige toestand.

**Response 200:**
```json
{
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

**Velden per device:**

| Veld | Type | Beschrijving |
|------|------|-------------|
| `id` | string | Entity-ID: `{module_ip}:{channel}` |
| `name` | string | Kanaalnaam uit `devices.json` |
| `room` | string | Ruimte uit configuratie |
| `semantic_type` | string | `light` (relay/dimmer) of `input` |
| `active` | boolean | Of kanaal actief is |
| `max_watt` | integer | Geconfigureerd maximaal vermogen |
| `state` | string | `on` / `off` / `unknown` |
| `current_watt` | integer | Actueel verbruik (0 als uit) |
| `firmware` | string | Firmware versie module |
| `level` | integer | Dimmer percentage 0–100 (dimmer only) |

---

## GET /api/v1/devices/{module_ip}/{channel}

**Beschrijving:** Retourneer één device op basis van entity-ID.

**Response 200:** zie `devices[0]` structuur hierboven.

**Response 404:**
```json
{"error": "not found"}
```

---

## POST /api/v1/devices/{module_ip}/{channel}/command

**Beschrijving:** Stuur een commando naar een relay of dimmer kanaal.

**Request headers:** `Content-Type: application/json`

**Request body — Relay:**
```json
{"action": "ON"}
{"action": "OFF"}
{"action": "PULSE"}
{"action": "TOGGLE"}
```

**Request body — Dimmer:**
```json
{"action": "DIM", "value": 75}
```

| Action | Geldig voor | Value |
|--------|-------------|-------|
| `ON` | Relay | — |
| `OFF` | Relay | — |
| `PULSE` | Relay | — |
| `TOGGLE` | Relay | — |
| `DIM` | Dimmer | `0–100` (0 = uit) |

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
{"ok": false, "error": "unsupported device type: input"}
```

---

## POST /api/v1/provision/autonomy

**Beschrijving:** EEPROM sync triggeren naar IP1100PoE (saveAutonomy). Stub — niet geimplementeerd (Fase 8).

**Request body:** `{}`

**Response 501:**
```json
{"ok": false, "error": "not yet implemented"}
```

---

Zie ook:
- [`websocket.md`](websocket.md) — WebSocket message catalog
- [`ipbuilding-gateway.postman_collection.json`](ipbuilding-gateway.postman_collection.json) — importeerbaar in RapidAPI for Mac
- [`ARCHITECTURE.md`](../../ARCHITECTURE.md) — architectuur context