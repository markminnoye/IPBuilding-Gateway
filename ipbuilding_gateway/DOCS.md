# IPBuilding Gateway — HA Add-on

## Overview

The IPBuilding Gateway add-on replaces the proprietary IPBox hub on the field bus (UDP/1001). It communicates directly with IPBuilding controllers (relay/dimmer/input) and exposes a WebSocket + REST northbound API on port **8080** for the `ipbuilding-gateway-ha` companion.

**Scope:** thin field-bus hub only. No scenes, automations, or button→action logic in the gateway — that belongs in Home Assistant.

---

## Hardware prerequisites

### Network: field-bus reachability (`10.10.1.x`)

The add-on uses `host_network: true` and shares the Home Assistant OS network stack. For the **field bus** (UDP/1001 to relay/dimmer/input modules, plus HTTP/80 for discovery and module metadata), HA must reach the module IPs (`10.10.1.30`, `.40`, `.50` in a typical install) **using a source IP in `10.10.1.0/24`**.

This is **not** the same as “HA may only live on the field-bus subnet”. HA normally stays on your home LAN (`192.168.1.x`); the `ipbuilding-gateway-ha` companion talks to the add-on via `localhost:8080` and does not need a field-bus IP.

| Requirement | Why |
|-------------|-----|
| L3 reachability to module IPs | Poll, commands, input events |
| Source IP on `10.10.1.x` (not home-LAN only) | Modules reply to the UDP **source IP**; embedded controllers usually cannot route back to `192.168.1.x` |
| Home LAN still available | HA UI, HACS, other integrations |

**Sufficient** (pick one):

- **Trunk on one NIC** (recommended on HA Green): native = home LAN, **tagged** = IPBuilding VLAN → VLAN subinterface `eth0.2` with e.g. `10.10.1.2/24`
- **Extra NIC** on the field-bus segment with a fixed `10.10.1.x` address

**Usually not sufficient:**

- Inter-VLAN routing from `192.168.1.x` **without** a `10.10.1.x` address on HA (ping via a router may work; UDP replies often do not)
- Switch port “in VLAN 2” with **no IP** on HA in that VLAN

**Optional — hub IP `10.10.1.1`:** that was the IPBox hub role. The gateway also works on another `10.10.1.x` address (field-tested). Avoid a conflict with IPBox on `.1` when you take over the hub role, or leave IPBox online during migration (`rest_shim_enabled` on `:30200`).

#### Setup: HA Green (single NIC, trunk)

1. **UniFi switch** — HA port: `forward: customize`, native VLAN = home LAN, **tagged** VLAN = IPBuilding (tag 2)
2. **HA OS** — VLAN on `eth0`, ID 2, static IP `10.10.1.2/24` (any free address on `10.10.1.x/24`)
3. **IPBox** — no conflict on `10.10.1.1` if the gateway assumes the hub role (see above)

#### Verify (SSH on HA or add-on shell)

```bash
ip addr show | grep 10.10.1
ping -c1 10.10.1.30
ping -c1 10.10.1.40
ping -c1 10.10.1.50
```

All three should respond from an interface with a `10.10.1.x` address.

---

## Installation

### 1. Add the repository

Add this repository to the HA Supervisor add-on store:

| Method | URL / action |
|--------|-------------|
| **One-click** (My Home Assistant) | [Add repository in HA](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway) |
| **Manual** | Settings → Add-ons → Add-on Store → ⋮ → Repositories → paste `https://github.com/markminnoye/IPBuilding-Gateway` |

After adding: **Add-on Store** → **IPBuilding Gateway** → **Install**.

### 2. Build locally (for development)

The CI pipeline (GitHub Actions) builds and publishes multi-arch images to `ghcr.io` automatically. For local development without pushing to the registry:

```bash
./ipbuilding_gateway/prepare-build.sh
docker build -f ipbuilding_gateway/Dockerfile ipbuilding_gateway \
  -t ghcr.io/markminnoye/ipbuilding-gateway:dev
```

### 3. Install the add-on (from source, without the store)

If you prefer not to use the add-on store:

1. Copy `ipbuilding_gateway/` to your HA's `/addons/local/` directory
2. Restart Home Assistant
3. Go to **Settings → Add-ons → Add-on Store** → find **IPBuilding Gateway**
4. Click **Install**

#### Add-on repository (GitHub)

| Method | URL |
|--------|-----|
| **One-click** (My Home Assistant) | [Add repository in HA](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway) |
| **Manual** (Settings → Add-ons → Add-on Store → ⋮ → Repositories) | `https://github.com/markminnoye/IPBuilding-Gateway` |

The [My Home Assistant](https://my.home-assistant.io/) link opens your instance with the repository URL pre-filled ([supervisor add repository redirect](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/)). Same pattern as other community repos, e.g. [bradsjm/hassio-addons](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbradsjm%2Fhassio-addons).

After adding the repository: **Add-on Store** → **IPBuilding Gateway** → **Install** → configure `devices.json` (below).

### 3. Configure the add-on

Before starting, you need a `devices.json` file with your installation's module and channel configuration.

#### Generate devices.json (fresh install, no IPBox)

From a host with a `10.10.1.x` address (SSH into HA after VLAN setup, or your dev machine on the field bus):

```bash
cd /path/to/IPBuilding-Gateway
PYTHONPATH=. python -m gateway.discover --range-start 30 --range-end 59
# Output: devices.discovered.json
```

Review the output (check channel names, rooms, semantic types), then copy it:

```bash
cp devices.discovered.json devices.json
```

#### Generate devices.json (migrating from IPBox)

```bash
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python scripts/discover_from_ipbox.py
```

See [`docs/api/discovery.md`](docs/api/discovery.md) for full instructions.

#### Place devices.json

The add-on's `/data` directory is persisted across updates. Copy `devices.json` into it using **Samba** or **SSH**:

```
/addon_configs/<repo-hash>_ipbuilding_gateway/data/devices.json
```

Where `<repo-hash>` is a hash derived from your repository URL (visible in the add-on info panel in HA). For local installs (`/addons/local/ipbuilding_gateway/`) use:

```
/addons/local/ipbuilding_gateway/data/devices.json
```

The easiest method: go to **Settings → Add-ons → IPBuilding Gateway → Configuration** and place the file via the Supervisor file editor or Samba share.

### 4. Add the companion integration

1. Install **HACS** if not already installed
2. Add this repository as a **custom repository** in HACS:
   ```
   https://github.com/markminnoye/IPBuilding-Gateway
   ```
3. Search for **IPBuilding Gateway HA** and install
4. Restart Home Assistant
5. Go to **Settings → Integrations → Add Integration** → **IPBuilding Gateway HA**
6. The companion will **auto-detect the add-on** via the HA Supervisor (no need to enter IP/port)
7. Entities (lights, switches, buttons) appear automatically

To add manually (standalone Docker or remote gateway):
- Host: `127.0.0.1` (if add-on is running on the same HA device)
- Port: `8080` (or the configured `api_port`)

---

## Add-on configuration

| Option | Default | Description |
|--------|---------|-------------|
| `hub_ip` | `10.10.1.1` | Documented hub address (IPBox default). Gateway can run on any `10.10.1.x`; modules send UDP replies to the packet source IP |
| `poll_interval` | `2.0` | Seconds between poll rounds |
| `api_port` | `8080` | Product northbound REST + WebSocket port |
| `rest_shim_enabled` | `false` | Enable IPBox REST compatibility on `:30200` (for migration only) |
| `log_level` | `info` | Python log level: `debug`, `info`, `warning`, `error` |
| `devices_file` | `/data/devices.json` | Path to the installation configuration |

### REST shim (IPBox migration only)

When `rest_shim_enabled: true`, the gateway also listens on port `30200` with the IPBox-compatible REST API. This lets you run the existing `HA-IPBuilding` component alongside the new companion during migration. Disable it once the IPBox is removed.

---

## Troubleshooting

### Add-on won't start

- Check the **Supervisor logs** (Settings → Add-ons → IPBuilding Gateway → Logs)
- Verify the VLAN interface is up on HA OS: `ip addr show eth0.2`
- Test connectivity: `ping 10.10.1.30` from within the add-on container

### Companion doesn't find the add-on

- Ensure the add-on is **running** (not just installed)
- Check that `api_port` is `8080` (default)
- Try adding the integration manually with host `127.0.0.1` and port `8080`

### No entities with names — "10.10.1.30:0"

`devices.json` is missing or incomplete. Generate it via the discovery CLI and copy to the add-on's `/data` directory.

### UDP poll not working

- Verify `host_network: true` is set in `config.yaml`
- Confirm HA has an **IP on `10.10.1.x`** (`ip addr`), not only a tagged switch port without an address
- Ping all module IPs from HA SSH; if ping fails, fix VLAN/trunk routing first
- Check the UniFi switch port is trunk with tagged VLAN 2 (or use a dedicated NIC on the field bus)
- Inter-VLAN routing from home LAN alone (no `10.10.1.x` on HA) is a common misconfiguration — see [Network](#network-field-bus-reachability-10101x)

---

## Ports

| Port | Protocol | Use |
|------|----------|-----|
| `8080` | HTTP + WebSocket | Product northbound API — companion, apps, Node-RED |
| `30200` | HTTP (REST) | IPBox compatibility shim — **disabled by default** |

---

## Data persistence

The `/data` directory is persisted across add-on updates and survives container restarts. Files stored there:

| File | Purpose |
|------|---------|
| `devices.json` | Installation configuration (modules, channels, names) |
| `options.json` | HA Supervisor options (managed by HA, not user-editable) |

---

## Architecture

```
IPBuilding field bus (UDP/1001 · 10.10.1.x)
  ├── IP0200PoE relay   → 10.10.1.30
  ├── IP0300PoE dimmer  → 10.10.1.40
  └── IP1100PoE input   → 10.10.1.50

              ↓ UDP/1001 (host_network: true)

         ipbuilding_gateway (HA Add-on)
         ├── REST :30200   (shim, opt-in)
         └── REST :8080 + WebSocket /ws  ←── ipbuilding-gateway-ha
```

Companion docs: [`ipbuilding-gateway-ha/README.md`](ipbuilding-gateway-ha/README.md)
Northbound API docs: [`docs/api/`](docs/api/)