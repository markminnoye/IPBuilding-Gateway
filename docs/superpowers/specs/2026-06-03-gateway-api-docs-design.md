# Gateway API Docs — Design Spec

**Datum:** 2026-06-03
**Status:** Goedgekeurd (brainstorming 2026-06-03)

## Doel

Een importable REST API-documentatiebestand (Postman Collection v2.1) plus een WebSocket message catalog in git, bruikbaar in RapidAPI for Mac (primair) en optioneel GetAPI. De bestanden worden in sync gehouden met `gateway_api.py` via een pytest-contracttest.

## Tooling

| Rol | Tool | Ondersteuning |
|-----|------|--------------|
| Primair dev | RapidAPI for Mac (PAW) | REST import via Postman-v2.1; WS handmatig |
| Optioneel dev | GetAPI | Zelfde Postman v2.1 importeren |
| Contract in git | Postman Collection v2.1 | Machine-leesbaar, importeerbaar in beide clients |
| WS-documentatie | `websocket.md` | Geen import in PAW/GetAPI — markdown als catalogus |

**Niet gebruiken:** Postman Collection v1.0 (deprecated, geen directe import), GetAPI-native folder tree (dubbel onderhoud), gateway-served OpenAPI (out of scope voor v1), AsyncAPI (overkill), Bruno `.bru` files (geen import in PAW).

## Postman Collection v2.1

**Waarom v2.1 boven v1.0:**
- v1.0 wordt door Postman en Newman v4 niet meer ondersteund; directe import in PAW faalt
- v2.1 is de huidige standaard (auth als array, URL altijd object)
- v2.1 is backwards compatible met tools die v2.0 verwachten

**Endpoints:**

| Request | Methode | Pad |
|---------|---------|-----|
| List devices | GET | `/api/v1/devices` |
| Get device | GET | `/api/v1/devices/{module_ip}/{channel}` |
| Command relay ON/OFF/PULSE | POST | `…/command` body `{"action":"ON\|OFF\|PULSE"}` |
| Command dimmer DIM | POST | `…/command` body `{"action":"DIM","value":0-100}` |
| Provision autonomy | POST | `/api/v1/provision/autonomy` (stub, 501) |

**Entity-ID:** `{module_ip}:{channel}` (bijv. `10.10.1.30:0`). Device type wordt server-side resolved uit `devices.json` — nooit door client meegegeven.

**Environment-variabelen:**

| Variable | Default | Beschrijving |
|----------|---------|-------------|
| `gateway_host` | `localhost` | Gateway host (thuis-LAN IP) |
| `gateway_port` | `8080` | `GatewayConfig.api_port` |
| `module_ip` | `10.10.1.30` | Relay-module IP (voorbeeld) |
| `channel` | `0` | Kanaalnummer |
| `base_url` | `http://{{gateway_host}}:{{gateway_port}}` | Basis-URL voor requests |

## WebSocket (websocket.md)

**Endpoint:** `ws://{{gateway_host}}:{{gateway_port}}/ws` — heartbeat 30s.

**Berichttypen (gateway-gedocumenteerd, niet importeerbaar):**

| Richting | Type | Doel |
|----------|------|------|
| GW → client | `device_list` | Full snapshot bij connect |
| GW → client | `state_changed` | Relay/dimmer toestandswijziging |
| GW → client | `button_event` | Input `B-…E` gebeurtenis |
| client → GW | `command` | ON/OFF/PULSE/DIM actie |
| GW → client | `command_result` | Ack `{ok, error}` |

WS-handmatig aanmaken in PAW (/geen import mogelijk).

## Bestandsstructuur

```
docs/api/
├── ipbuilding-gateway.postman_collection.json   # REST, v2.1, 7 requests
├── environments/
│   └── local.postman_environment.json           # gateway_host, gateway_port, etc.
├── websocket.md                                 # WS message catalog
└── README.md                                    # import-instructies
```

## Sync-workflow

```
gateway_api.py wijziging
    ↓
Update postman_collection.json + websocket.md
    ↓
Commit naar git
    ↓
pytest tests/test_api_docs.py  (CI guard — FAILS als routes ontbreken in collection)
    ↓
PAW: re-import (Remote URL of lokaal bestand na git pull)
GetAPI: Import → Postman (optioneel)
```

**Contracttest:** parsed de Postman collection en vergelijkt alle routes met `gateway_api.py` router. Bij ontbrekende route → test FAIL → PR blokkeert.

## Beperkingen

- WebSocket message types zijn **niet importeerbaar** via Postman/PAW/GetAPI collection import (Postman WS export niet beschikbaar; [GitHub #11252](https://github.com/postmanlabs/postman-app-support/issues/11252))
- GetAPI ondersteunt WS sinds 2025-12 (issue #148 open), maar export uit collection ontbreekt — WS daarom handmatig in PAW
- Remote URL sync in PAW vereist handmatige re-import na git pull

## Out of scope

- Gateway `GET /api/v1/openapi.json` endpoint
- AsyncAPI YAML voor WS
- Bruno `.bru` files
- Newman collection runner in CI
- Postman WebSocket items in collection