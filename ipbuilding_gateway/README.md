# IPBuilding Gateway

Open veldbus-hub voor IPBuilding relais, dimmers en drukknoppen via **UDP/1001**.

> **Zonder companion geen Home Assistant-entiteiten.**  
> Deze add-on levert alleen de gateway-service. Lichten, schakelaars, sensoren
> en knoppen komen pas via de **IPBuilding Gateway** companion-integratie.

## About

Vervangt de propriëtaire IPBox-hub op de veldbus. De gateway praat UDP/1001 met
je modules en biedt een northbound API (WebSocket `/ws` + REST `/api/v1/` op
poort **8080**). Scenes en automatiseringen horen in Home Assistant, niet in de
gateway.

| Je installeert | Resultaat |
|----------------|-----------|
| Alleen deze add-on | Gateway draait — geen HA-entiteiten |
| Add-on + companion | Lights, switches, sensors, knoppen in HA |

Add-on en companion volgen **onafhankelijk semver** — gebruik recente releases
van beide.

## Vereist: companion installeren

Installeer de companion **vóór of direct na** deze add-on:

[![Open companion in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ha-ipbuilding-gateway&category=integration)

Handmatig: **HACS → Integraties → ⋮ → Aangepaste repositories** →

```text
https://github.com/markminnoye/ha-ipbuilding-gateway
```

Download **IPBuilding Gateway**, herstart Home Assistant.

Na installatie van beide: **Instellingen → Apparaten & diensten → Ontdekt** →
voeg **IPBuilding Gateway** toe (geen handmatig host/poort nodig op HA OS).

## Installatie add-on

Zie de **Documentatie**-tab voor netwerk, `devices.json`, discovery en
troubleshooting.

## Support

- [Companion (HACS)](https://github.com/markminnoye/ha-ipbuilding-gateway)
- [Gateway releases](https://github.com/markminnoye/IPBuilding-Gateway/releases)
- [Issues](https://github.com/markminnoye/IPBuilding-Gateway/issues)
