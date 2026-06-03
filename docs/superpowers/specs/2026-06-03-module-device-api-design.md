# Module vs Device API — Firmware & Module-Metadata

**Datum:** 2026-06-03
**Type:** Design doc (breaking change)
**Status:** Concept

---

## Doel

Scheid de **fysieke module-identiteit** (firmware, MAC, netwerkconfig, knoppen) van de **logische kanaal-devices** (licht, ventilator) in het northbound contract. Dit lost twee problemen op:

1. **Firmware per kanaal is onzin** — alle 24 kanalen op een IP0200PoE delen firmware `5.1`; de waarde werd gedupliceerd in elke device-entry.
2. **DHCP-IP is onstabiel** — als een module een nieuw IP krijgt via DHCP, verandert `10.10.1.30-0` maar de MAC `00:24:77:52:ac:be` blijft identiek.

---

## Terminologie

| Term | Betekenis |
|------|-----------|
| **Module** | Fysieke IPBuilding-controller (relay / dimmer / input). Identificatie via MAC. |
| **Device** | Logisch kanaal op een module (bijv. "Keuken LED"). Identificatie via custom slug of fallback `{ip}-{channel}`. |
| **Module-id** | Genormaliseerde MAC in lowercase kolon-notatie (`00:24:77:52:ac:be`). Stabiel. |
| **Device-id** | Custom slug (bv. `keuken-led`) of fallback `{module_ip}-{channel}`. |
| **Firmware** | Softwareversie van de fysieke module. Hoort bij module, niet bij device. |

---

## Redesign: twee resources

### `GET /api/v1/modules`

**Module** — fysieke controller.

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
      "allow": "...",
      "fetched_at": "2026-06-03T18:00:00Z"
    }
  ]
}
```

**Veld voorbeelden** (van `getSysSet`):

| Veld | Bron | Type |
|------|------|------|
| `id` | Genormaliseerde MAC (PK) | string |
| `ip` | Config + getSysSet `network.ip` | string |
| `mac` | Zelfde als `id` (expliciet) | string |
| `name` | Config `name` | string |
| `model` | Config `model` | string |
| `type` | Config `type` | `relay` \| `dimmer` \| `input` |
| `firmware` | Config `firmware` | string |
| `network.dhcp` | getSysSet `dhcp` | string |
| `network.ip` | getSysSet `ip` | string |
| `network.subnet` | getSysSet `subnet` | string |
| `network.gateway` | getSysSet `gateway` | string |
| `button` | getSysSet `button` | string |
| `allow` | getSysSet `allow` | string |
| `fetched_at` | Cache timestamp | ISO 8601 |

**Alleen `type=input`** — extra `getButtons`:

```json
{
  "buttons": [
    {
      "index": 0,
      "id": "2D2F8185190000DF",
      "descr": "Badkamer knop",
      "gr": "1e verdieping",
      "func1": { "ip": "30", "ch": 0, "outType": "relay", "action": "on" },
      "func2": { "ip": "40", "ch": 1, "outType": "dimmer", "action": "dim" }
    }
  ]
}
```

`func1`/`func2` zijn **configureerde mappings** ( EEPROM in IP1100), niet live button presses.

### `GET /api/v1/modules/{module_id}`

Single module lookup via MAC. Retourneert `{}` of `404`.

### `POST /api/v1/modules/refresh`

Herlaadt `network` / `button` / `allow` via HTTP van elke module. Retourneert volledige `{ "modules": [...] }`.

### `GET /api/v1/devices`

**Device** — logisch kanaal. `firmware` verwijderd. `module_id` + `module_ip` + `channel` toegevoegd.

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

**Veld wijzigingen t.o.v. vorig contract:**

| Wijziging | Veld |
|-----------|------|
| Verwijderd | `firmware` |
| Toegevoegd | `module_id` (MAC, stabiel) |
| Toegevoegd | `module_ip` (huidig IP, mutable) |
| Toegevoegd | `channel` (int) |

`id` blijft `{module_ip}-{channel}` voor default of custom slug uit config.

---

## WebSocket

Bij connect: **`snapshot`** (was `device_list`).

```json
{
  "type": "snapshot",
  "modules": [ /* zie GET /modules */ ],
  "devices": [ /* zie GET /devices */ ]
}
```

**Event messages** (`state_changed`, `button_event`) ongewijzigd.

---

## MAC als module-id

IPBuilding-modules hebben **factory MAC** met OUI `00:24:77`. Dit is de stabiele identifier.

| Veld | Waarde voorbeeld | Stabiliteit |
|------|------------------|-------------|
| `id` (module) | `00:24:77:52:ac:be` | **Stabiel** — factory, wijzigt nooit |
| `ip` | `10.10.1.30` | **Mutable** — kan via DHCP of `setIp` wijzigen |

**REST URL:** `/api/v1/modules/{module_id}` — MAC als path parameter (URL-encoded door client, colons `%3A` of literal).

**Discovery IP-sync:** bij `gateway.discover` match op MAC. Als MAC bekend is en IP gewijzigd:
- Update `modules[].ip` in output draft
- Log: `"Module 00:24:77:52:ac:be IP changed 10.10.1.30 → 10.10.2.30; device ids may need review"`

**Config `devices.json`:** geen breaking wijziging. Blijft `modules[].mac`.

---

## Achtergrond: waarom MAC in devices.json al stond maar niet gebruikt werd

Discovery ([`build_devices_json_draft()`](gateway/discovery.py) ~regel 600) schrijft MAC al uit:

```python
"mac": mac_hex,   # from getSysSet decimal → hex
```

[`ModuleConfig`](gateway/installation.py) las het **niet** in. De gateway negeerde MAC in runtime. Nu wordt het de **PK** voor modules.

---

## Overzicht wijzigingen per bestand

| Bestand | Wijziging |
|---------|-----------|
| `gateway/installation.py` | `ModuleConfig.mac` parsen; `_modules_by_mac` index; `module_by_mac()` |
| `gateway/discovery.py` | IP-sync hint in `build_devices_json_draft()` voor bestaande MAC |
| `gateway/module_metadata.py` | **Nieuw** — `ModuleMetadataCache` met `async refresh()` |
| `gateway/gateway_api.py` | Routes `/modules`, `_build_module_list()`, `_build_snapshot()`, devices met `module_id` |
| `gateway/main.py` | `cache.refresh()` vóór `api.start()` |
| `ipbuilding-gateway-ha/coordinator.py` | `snapshot` handler (WS) |
| `docs/api/rest.md` | Modules endpoints gedocumenteerd |
| `docs/api/websocket.md` | `snapshot` message gedocumenteerd |
| `docs/api/modules.md` | **Nieuw** — module resource referentie |
| `ARCHITECTURE.md` §6 | WS/API bijgewerkt |
| `tests/test_installation.py` | MAC parsing + `module_by_mac()` |
| `tests/test_module_metadata.py` | **Nieuw** — cache + parse |
| `tests/test_gateway_api_modules.py` | **Nieuw** — snapshot shape |
| `tests/test_api_docs.py` | Routes bijgewerkt |

---

## Niet in scope

- Runtime button press via modules (blijft `button_event`)
- Relay/dimmer kanaalstatus via HTTP `statuses` (UDP/registry → devices)
- Volledige `backupConfig` in northbound
- REST shim `:30200`
- MQTT/Matter northbound
- Config persistentie van network/button naast `devices.json`

---

## Validatie

```bash
# Modules endpoint
curl http://localhost:8080/api/v1/modules

# Single module
curl http://localhost:8080/api/v1/modules/00:24:77:52:ac:be

# Refresh
curl -X POST http://localhost:8080/api/v1/modules/refresh

# Devices (geen firmware)
curl http://localhost:8080/api/v1/devices

# WebSocket connect → verwacht snapshot
```

Verwachte velden per device: `id`, `module_id`, `module_ip`, `channel`, `name`, `room`, `semantic_type`, `device_type`, `active`, `max_watt`, `state`, `current_watt`, optioneel `level` / `current_watt`.