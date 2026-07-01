# IPBuilding Gateway

Open field-bus hub for IPBuilding relays, dimmers, and buttons via **UDP/1001**.

> **No Home Assistant entities without the companion.**  
> This add-on only runs the gateway service. Lights, switches, sensors, and
> buttons require the **IPBuilding Gateway** companion integration.

## About

Replaces the proprietary IPBox hub on the field bus. The gateway speaks UDP/1001
to your modules and exposes a northbound API (WebSocket `/ws` + REST `/api/v1/`
on port **8080**). Scenes and automations belong in Home Assistant, not in the
gateway.

Add-on and companion follow **independent semver** — use recent releases of both.

## Features

- **UDP/1001 field bus** — IP0200PoE relays, IP0300PoE dimmers, IP1100PoE inputs
- **Northbound API** — WebSocket `/ws` and REST `/api/v1/` on port **8080**
- **Runtime discovery** — ARP monitor and optional init-sweep; updates `devices.json`
- **Supervisor discovery** — registers with HA when the companion is installed (no manual host/port on HA OS)
- **Health reporting** — `/api/v1/status` and watchdog `/health`
- **Optional IPBox REST shim** on `:30200` for migration only (off by default)

This add-on does **not** implement IPBox scenes, moods, or button→relay rules.

## Required: install the companion

Install the companion **before or right after** this add-on:

[![Open companion in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ha-ipbuilding-gateway&category=integration)

Manual: **HACS → Integrations → ⋮ → Custom repositories** →

```text
https://github.com/markminnoye/ha-ipbuilding-gateway
```

Download **IPBuilding Gateway**, then restart Home Assistant.

After both are installed: **Settings → Devices & Services → Discovered** → add
**IPBuilding Gateway** (no manual host/port on HA OS).

## Install this add-on

See the **Documentation** tab for network setup, `devices.json`, discovery, and
troubleshooting.

## Support

- [Companion (HACS)](https://github.com/markminnoye/ha-ipbuilding-gateway)
- [Gateway releases](https://github.com/markminnoye/IPBuilding-Gateway/releases)
- [Issues](https://github.com/markminnoye/IPBuilding-Gateway/issues)
