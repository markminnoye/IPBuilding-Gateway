# local/ — development tooling

Dev-only launchers. **Not** part of the product. Not packaged, not
shipped, not required to build or run the gateway add-on.

Three independent helpers, all run on the Mac host:

| Path | Purpose |
|------|---------|
| `local/gateway/start.sh` | Start the gateway on `http://127.0.0.1:8080` (real field bus, sim, or `--init` refresh) |
| `local/gateway/smoke.sh` | Pre-flight: hit gateway REST + a sample command |
| `local/ha-core/setup.sh`  | One-time: create venv, install `homeassistant`, symlink companion |
| `local/ha-core/start.sh`  | Run Home Assistant in the venv on `http://127.0.0.1:8123` |

## Gateway modes (`local/gateway/start.sh`)

The script supports three modes; default is real field bus + passive ARP.

```bash
./local/gateway/start.sh            # real field bus, existing devices.json
./local/gateway/start.sh --sim      # simulated UDP, no hardware required
./local/gateway/start.sh --init     # prompt: refresh install from field bus
./local/gateway/start.sh --help     # usage
```

### `--init` — refresh from the field bus

Running with `--init` shows an interactive prompt **before** the gateway
starts. Your answer decides which discovery mode the gateway uses at boot:

```
Overwrite devices.json? Names, rooms, and active flags will be lost
(backup -> devices.json.bak).
  [y] Yes - reset and init-sweep from field bus
  [N] No  - merge discovery (keep existing config)
```

| Choice | What happens before the gateway starts | What the gateway does |
|--------|------------------------------------------|----------------------|
| **y** | backup `devices.json` → `devices.json.bak`, wipe to `{"modules":[]}` | `GATEWAY_AUTO_DISCOVER_ON_START=1` → init-sweep on empty file |
| **N** *(default)* | no file change | `GATEWAY_FORCE_DISCOVER_ON_START=1` → in-process merge: keeps your names/rooms/`active` flags, updates IP/firmware, adds new modules as `active:false` |

Both paths run the gateway as a single foreground process. No separate
HTTP round-trip or background launcher is involved — merge and reset
share the existing runtime API.

The reset (y) path is destructive. Your only vangnet is `devices.json.bak`.
Home Assistant (`~/.homeassistant`) and the module EEPROMs are not
touched. The companion entities in HA will show stale state until you
reload the integration.

## Daily use (two terminals)

```bash
# Terminal 1 — gateway
./local/gateway/start.sh
# or with hardware-free sim:
./local/gateway/start.sh --sim
# or to refresh the install from the field bus:
./local/gateway/start.sh --init

# Terminal 2 — Home Assistant
./local/ha-core/start.sh
# Open http://localhost:8123
```

## Network layout

```
[Browser] ──> http://localhost:8123 ──> [HA in venv]
                                          │ http://127.0.0.1:8080
                                          ▼
                                       [gateway: python -m gateway]
```

Both run on the Mac host, so they reach each other over plain
`127.0.0.1`. No Docker, no `host.docker.internal`, no bridge.

## First-time HA setup

```bash
./local/ha-core/setup.sh
./local/ha-core/start.sh
# Onboard at http://localhost:8123
# Add integration: IPBuilding Gateway HA
#   Host: 127.0.0.1
#   Port: 8080
```

## Editing the companion

Files in `ipbuilding-gateway-ha/custom_components/...` are symlinked
into `~/.homeassistant/custom_components/`. After Python changes:

```bash
# In Terminal 2 — restart hass (Ctrl+C, then up-arrow + Enter)
```

HA re-reads the custom component on startup. A reload is faster than
Docker (`~10 s` vs `~60 s`).

## Reset

```bash
rm -rf ~/.homeassistant
./local/ha-core/setup.sh    # rebuild from scratch
```

## Out of scope

- EEPROM / `POST /api/v1/provision/autonomy` (MVP off-scope)
- Supervisor auto-detect (no add-on, no Supervisor in plain HA Core)
- Companion v2 (device_added WS events, post-MVP)
