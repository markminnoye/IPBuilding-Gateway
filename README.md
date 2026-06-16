# IPBuilding Gateway — Home Assistant Add-on

[![Version](https://img.shields.io/github/v/release/markminnoye/IPBuilding-Gateway)](https://github.com/markminnoye/IPBuilding-Gateway/releases/latest)

> ## Companion required — this add-on alone is not enough
>
> **Installing only this add-on will not give you lights, switches, or sensors in
> Home Assistant.** The add-on is the **field-bus hub** (UDP/1001). To see and
> control your installation in HA you **must also install the companion
> integration**
> [**IPBuilding Gateway HA**](https://github.com/markminnoye/ipbuilding-gateway-ha)
> at the **same version** (currently **v0.3.0**).
>
> | You install | You get |
> |-------------|---------|
> | **Add-on only** | Gateway service on port 8080 — **no HA entities** |
> | **Add-on + companion** | Lights, switches, sensors, buttons, dashboards ✅ |

Open replacement for the proprietary **IPBox hub** on the IPBuilding field bus.
The add-on speaks **UDP/1001** to relay, dimmer, and input modules and exposes
a northbound API for the companion. Scenes and automations live in **Home
Assistant**, not in this add-on.

**Install type:** Home Assistant **OS** or **Supervised** only (Supervisor
add-on). Container / Core-only installs need a
[standalone gateway](ipbuilding_gateway/DOCS.md) instead.

## Two-part setup (read this first)

```text
  IPBuilding modules (UDP/1001)
           │
           ▼
  ┌─────────────────────────────┐
  │  IPBuilding Gateway add-on   │  ← this repository
  │  (field-bus hub, port 8080)  │
  └──────────────┬──────────────┘
                 │ WebSocket / REST
                 ▼
  ┌─────────────────────────────┐
  │  IPBuilding Gateway HA       │  ← required companion (HACS)
  │  (lights, switches, sensors) │
  └─────────────────────────────┘
                 │
                 ▼
         Home Assistant UI
```

1. **[Install the companion](https://github.com/markminnoye/ipbuilding-gateway-ha#installation)**
   (HACS → custom repository `markminnoye/ipbuilding-gateway-ha`).
2. **Add this add-on repository** and install **IPBuilding Gateway** (below).
3. Provide **`devices.json`**, start the add-on, then add the integration under
   **Settings → Devices & Services → Discovered**.

Version numbers are **lockstep**: always upgrade add-on and companion together.

## Features

- **UDP/1001 field bus** — IP0200PoE relays, IP0300PoE dimmers, IP1100PoE inputs
- **Northbound API** — WebSocket `/ws` and REST `/api/v1/` on port **8080**
- **Runtime discovery** — ARP monitor and optional init-sweep; updates
  `devices.json`
- **Supervisor discovery** — registers with HA when the companion is installed
  (no manual host/port on HA OS)
- **Health reporting** — `/api/v1/status` and watchdog `/health`
- **Optional IPBox REST shim** on `:30200` for migration only (off by default)

This add-on does **not** implement IPBox scenes, moods, or button→relay rules.

## Requirements {#prerequisites}

- Home Assistant **OS** or **Supervised**
- [**IPBuilding Gateway HA**](https://github.com/markminnoye/ipbuilding-gateway-ha)
  companion (**same version** as this add-on)
- IPBuilding modules reachable on **`10.10.1.x`** with HA using a **source IP on
  that segment** (`host_network: true` — see
  [network notes](ipbuilding_gateway/DOCS.md#network))
- A valid **`devices.json`** in the add-on config folder

## Installation

### 1. Companion (required — do this first or in parallel)

[![Open companion in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ipbuilding-gateway-ha&category=integration)

Adds custom repository `markminnoye/ipbuilding-gateway-ha` in HACS, then download
**IPBuilding Gateway HA** and restart HA. Full steps:
[companion README](https://github.com/markminnoye/ipbuilding-gateway-ha/blob/main/README.md#2-companion-integration-hacs-recommended)

### 2. Add-on repository

[![Add add-on repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway)

Or: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**

```text
https://github.com/markminnoye/IPBuilding-Gateway
```

### 3. Install and configure the add-on

**Add-on Store** → **IPBuilding Gateway** → **Install**

Then follow **[add-on documentation](ipbuilding_gateway/DOCS.md)** for:

- copying or generating **`devices.json`**
- add-on **options** (hub IP, discovery, timeouts)
- **starting** the add-on and reading logs

### 4. Link in Home Assistant

With the add-on **running** and the companion **installed**:

**Settings → Devices & Services → Discovered** → **IPBuilding Gateway HA** →
**Add**

Manual host/port remains available if discovery is blocked; see the
[companion configuration guide](https://github.com/markminnoye/ipbuilding-gateway-ha/blob/main/README.md#configuration).

## Security

- **`host_network: true`** — the add-on joins your host network stack; use only
  on a trusted LAN segment. See
  [Home Assistant app security](https://developers.home-assistant.io/docs/apps/security/).
- The gateway API has **no authentication** and uses **plain HTTP/WebSocket**.
  Do not expose port **8080** outside your network.

## Documentation

| Document | Audience |
|----------|----------|
| **[Add-on DOCS](ipbuilding_gateway/DOCS.md)** | Operators — install, options, network, troubleshooting |
| **[Companion README](https://github.com/markminnoye/ipbuilding-gateway-ha)** | HA integration — entities, automations, dashboard |
| **[Changelog](ipbuilding_gateway/CHANGELOG.md)** | Release notes (lockstep with companion) |
| **[Architecture](ARCHITECTURE.md)** | Migration from IPBox, deployment variants |
| **[API reference](docs/api/)** | Northbound REST/WebSocket |
| **[Developer library](README_gateway.md)** | Python `gateway/` package (not the add-on UI) |

Add-on manifest and Supervisor integration follow the official
[Home Assistant Apps developer docs](https://developers.home-assistant.io/docs/apps/).

## Support

- Add-on / gateway:
  [IPBuilding-Gateway issues](https://github.com/markminnoye/IPBuilding-Gateway/issues)
- Companion / HA entities:
  [ipbuilding-gateway-ha issues](https://github.com/markminnoye/ipbuilding-gateway-ha/issues)

When reporting problems, state **both versions** (add-on and companion) from
`GET /api/v1/status` or the add-on info panel.

## Migrating from IPBox / HA-IPBuilding

The legacy [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding)
integration uses the IPBox REST API (`:30200`). This stack uses the open gateway
plus companion on `:8080`. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
cutover path.
