# IPBuilding field bus library (`gateway/`)

Python package for **UDP/1001** communication with IPBuilding field modules (relay, dimmer, input).

## Product direction

We are building an **open replacement for the IPBox hub role** on the field bus (`10.10.1.1`) — **not** an IPBox REST clone on port 30200.

| Layer | Status (2026-06-01) |
|-------|------------------------|
| **Fase 1 — wire + codecs** | **Done** — RE Sprint 1–5; `gateway/payloads/` + tests |
| **Fase 2 — hub service** | **In progress** — poll-loop, `device_registry`, `rest_shim` (dev entrypoint wired in `main.py`) |
| **Fase 3+ — northbound** | **Open** — WebSocket `/ws`, HA add-on, `ipbuilding-open` companion |

Architecture: [Gateway architecture design](docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Canonical RE status: [RE_STATE.md](resources_and_docs/RE_STATE.md).

**Principle:** thin field-bus transport only; scenes and button→action logic live in **Home Assistant**, not in the gateway container.

## `rest_shim` vs `rest_api`

Both modules exist; they are **not** two different APIs.

| Module | Role |
|--------|------|
| **`gateway/rest_shim.py`** | **Canonical implementation.** IPBox-compatible REST on `:30200` (`/api/v1/comp/items`, `/api/v1/action/action`) for **transition only** — lets existing [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) talk to the open hub while the companion is built. Wired to `UDPBus` + `DeviceRegistry`. |
| **`gateway/rest_api.py`** | **Backward-compat alias** — re-exports `RESTShim` as `RESTApp` and `create_app` so older imports and `tests/test_rest_api.py` keep working. No separate logic. |

The name **shim** (not `rest_api`) signals intent from the architecture spec: this layer is a **temporary bridge**, not the product northbound API. The product API is **`gateway_api.py`** (own REST `/api/v1/` + WebSocket `/ws`) — not started yet.

Do **not** extend IPBox REST parity (scenes, moods, project DB) in `rest_shim`; that stays in HA.

## What exists today

### Fase 1 (stable)

- **`gateway/payloads/`** — encode/decode relay, dimmer, input (incl. `B-…E` button events)
- **`gateway/config.py`** — env-based hub/module addresses, poll interval, simulated mode

### Fase 2 (current work)

- **`gateway/udp_bus.py`** — async UDP client, background poll loop (`P0000` / `I9900` / `I0000`), packet listeners, `GATEWAY_SIMULATED=1` for tests
- **`gateway/device_registry.py`** — relay/dimmer state from replies; input button press/release events
- **`gateway/installation.py`** — loads `devices.json`; `make_entity_id(ip, type, ch)` → `"10.10.1.30:relay:0"`; optional `legacy_id` lookup for shim; derived into `GatewayConfig.field_modules`
- **`gateway/rest_shim.py`** — transition REST shim (see table above); uses `legacy_id_to_channel()` for IPBox-compatible ID lookup
- **`gateway/main.py`** — dev entrypoint: starts UDP bus → registry → REST shim on `GATEWAY_REST_HOST`:`GATEWAY_REST_PORT` (default `0.0.0.0:30200`); registers modules from `InstallationConfig` if `devices.json` is loaded
- **`devices.json`** (repo root) — installation channels with optional `legacy_id` (IPBox comp_id, shim only); loaded via `GATEWAY_DEVICES_FILE` env
- **`gateway/discovery.py`** — standalone HTTP sweep + optional UDP/10001 probe; see [Discovery tools](#discovery-tools-optional-provisioning) below
- **`gateway/__main__discover.py`** — CLI: `python -m gateway.discover`

## Not built yet

- **`gateway_api.py`** — WebSocket `/ws` + own REST `/api/v1/` (product northbound); uses `entity_id` not `legacy_id`
- HA add-on packaging, **`ipbuilding-open`** companion
- Field validation with gateway bound as hub `10.10.1.1` (IPBox off or second NIC); see [veldtest-runbook](resources_and_docs/workflows/2026-06-01_gateway_field_test_runbook.md)

## ID model

| Concept | Format | Stored? | Used by |
|---------|--------|---------|---------|
| `entity_id` | `"10.10.1.30:relay:0"` | No — derived from `(ip, type, ch)` | Product API, WebSocket, companion |
| `legacy_id` | integer `547` | Optional in `devices.json` per channel | REST shim only (HA-IPBuilding transition) |

`legacy_id` disappears when the shim is retired. `entity_id` is always `make_entity_id(ip, type, ch)`.

## Discovery tools (optional provisioning)

| Tool | Requires | Output |
|------|----------|--------|
| `python scripts/discover_from_ipbox.py` | IPBox WebConfig + session cookie | Full `devices.json` with `legacy_id` per channel |
| `python -m gateway.discover` | IPBuilding VLAN access | Draft `devices.json` — no `legacy_id`, channels empty |

```bash
# Migrate from IPBox (full channels + legacy_id for shim)
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python scripts/discover_from_ipbox.py

# Open gateway discovery (no IPBox needed; run RE spike first — see evidence/)
python -m gateway.discover --range-start 30 --range-end 59
```

See `resources_and_docs/evidence/2026-06-XX_udp10001_discovery_spike.md` for UDP/10001 RE verdict.

## Configuration (environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GATEWAY_HUB_IP` | `10.10.1.1` | Documented hub address (modules send replies here) |
| `GATEWAY_RELAY_IP` / `GATEWAY_DIMMER_IP` / `GATEWAY_INPUT_IP` | `.30` / `.40` / `.50` | Fallback module targets (used when `GATEWAY_DEVICES_FILE` is not set) |
| `GATEWAY_POLL_INTERVAL` | `2.0` | Seconds between poll rounds |
| `GATEWAY_REST_HOST` / `GATEWAY_REST_PORT` | `0.0.0.0` / `30200` | REST shim listen address |
| `GATEWAY_DEVICES_FILE` | `./devices.json` | Path to installation config; if set, `field_modules` is derived from it and env IP overrides are ignored |
| `GATEWAY_SIMULATED` | off | `1` / `true` — no real UDP socket; in-process reply simulation for dev/tests |

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-gateway.txt pytest pytest-asyncio
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
```

Relevant suites: `test_udp_bus.py`, `test_device_registry.py`, `test_rest_shim.py`, `test_bus_registry_integration.py`, `test_rest_api.py` (alias compatibility), `test_installation.py`, `test_discover_from_ipbox.py`, `test_discovery.py`.

Also install `aioresponses` for the discover test:

```bash
.venv/bin/pip install aioresponses
```

## Run locally

**Simulated (no hardware):**

```bash
GATEWAY_SIMULATED=1 PYTHONPATH=. .venv/bin/python -m gateway
```

**Against the field bus** (host must be reachable as hub `10.10.1.1`, modules on `10.10.1.x`):

```bash
PYTHONPATH=. .venv/bin/python -m gateway
```

Logs state changes and button events; REST shim answers on port 30200 for legacy HA integration tests.

## RE / evidence

- [RE_STATE.md](resources_and_docs/RE_STATE.md)
- [Field bus capability matrix](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md)
- [Sprint 5 input completion](resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md)
