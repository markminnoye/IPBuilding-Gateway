# IPBuilding Gateway HA — Home Assistant Custom Component

HA custom component voor de **ipbuilding-gateway** (Fase 3 product-API op `8080`).

## Installatie (HACS)

1. Voeg toe als **custom repository** in HACS:
   `https://github.com/markminnoye/IPBuilding-Gateway`
2. Zoek naar **IPBuilding Gateway HA** en installeer
3. Herstart Home Assistant
4. Via **Integraties**: voeg `IPBuilding Gateway HA` toe
   - Voer host + poort (`8080`) van de gateway in
   - Validatie via `GET /api/v1/devices` — gateway moet bereikbaar zijn

## Architectuur

```
IPBuilding veldbus (UDP/1001)
  └── ipbuilding-gateway (Python)
        ├── REST :30200  (IPBox shim — transitie, Fase 1-2)
        ├── WebSocket /ws  (product northbound, Fase 3)  ←── ipbuilding-gateway-ha
        └── REST /api/v1/  (product northbound, Fase 3)
  └── ipbuilding-gateway-ha (HA custom component)
        ├── WebSocket-client (coordinator)
        └── HA entities:
              ├── light      (relay ONOFF + dimmer BRIGHTNESS)
              ├── switch     (relay/dimmer met semantic_type switch/plug/fan)
              ├── button     (IP1100PoE fysieke knop → HA events)
              └── sensor     (current_watt per kanaal)
```

## Entity ID formaat

De companion gebruikt het gateway entity-ID:
```
{module_ip}:{device_type}:{channel}
Bijv. "10.10.1.30:relay:0"
```

## Knoppen (button events)

Knop events van de IP1100PoE verschijnen als HA events:
- Event type: `ipbuilding_gateway_ha.button_pressed`
- Data: `{"hardware_id": "2DE341851900001F", "action": "press"}`

Gebruik in automations:
```yaml
trigger:
  platform: event
  event_type: ipbuilding_gateway_ha.button_pressed
  event_data:
    hardware_id: "2DE341851900001F"
```

## Commandos sturen

Vanuit een HA automation of service call:
*(Command interface via WebSocket `command` berichten — automations/scenes spreken direct via de coordinator.)*

## Ontwikkeling

Bestanden in `custom_components/ipbuilding_gateway_ha/`:
- `coordinator.py` — WebSocket-client + state management
- `light.py` — relay/dimmer light entities
- `switch.py` — switch entities
- `button.py` — button/event entities
- `sensor.py` — power sensor entities
- `config_flow.py` — gebruiker invoer + validatie
- `manifest.json` — HA integratie manifest

## Vereisten

- Home Assistant >= 2023.8 (voor EventEntity)
- `aiohttp` Python package
- Gateway moet WebSocket `/ws` en REST `/api/v1/devices` exposed hebben (poort 8080)