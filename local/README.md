# local/ — development tooling

Dev-only launchers. **Not** part of the product. Not packaged, not
shipped, not required to build or run the gateway add-on.

Two independent helpers, both run on the Mac host:

| Path | Purpose |
|------|---------|
| `local/gateway/start.sh` | Start the simulated gateway on `http://127.0.0.1:8080` |
| `local/gateway/smoke.sh` | Pre-flight: hit gateway REST + a sample command |
| `local/ha-core/setup.sh`  | One-time: create venv, install `homeassistant`, symlink companion |
| `local/ha-core/start.sh`  | Run Home Assistant in the venv on `http://127.0.0.1:8123` |

## Daily use (two terminals)

```bash
# Terminal 1 — simulated gateway
./local/gateway/start.sh

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

- Veldbus UDP (`10.10.1.x` unreachable from a Mac in this lab)
- EEPROM / `POST /api/v1/provision/autonomy` (MVP off-scope)
- Supervisor auto-detect (no add-on, no Supervisor in plain HA Core)
- Companion v2 (device_added WS events, post-MVP)
