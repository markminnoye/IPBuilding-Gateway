# IPBuilding field bus library (`gateway/`)

Python package for **UDP/1001** communication with IPBuilding field modules (relay, dimmer, input).

## Product direction

We are building an **open replacement for the IPBox hub role** on the field bus (`10.10.1.1`) — **not** an IPBox REST clone on port 30200.

| Layer | Status (2026-06-01) |
|-------|------------------------|
| **Fase 1 — wire + codecs** | **Done** — RE Sprint 1–5; `gateway/payloads/` + tests |
| **Fase 2 — hub service** | **Done** — poll-loop, `device_registry`, `rest_shim`; entrypoint in `main.py` |
| **Fase 3 — northbound** | **Done** — WebSocket `/ws` + REST `/api/v1/` in `gateway_api.py`; PAW/GetAPI docs in [`docs/api/`](docs/api/) |
| **Fase 4 — HA add-on** | **Done** — CI publish naar ghcr.io (GitHub Actions multi-arch); install via Add-on Store; `host_network: true`; REST shim opt-in via `GATEWAY_REST_SHIM_ENABLED`; Supervisor auto-discovery in companion |
| **Fase 5 — companion** | **Done** — entities (switch, light, button, sensor); WebSocket coordinator; Supervisor auto-detection |

Architecture: [Gateway architecture design](docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Canonical RE status: [RE_STATE.md](resources_and_docs/RE_STATE.md).

**Principle:** thin field-bus transport only; scenes and button→action logic live in **Home Assistant**, not in the gateway container.

## `rest_shim` vs `rest_api`

Both modules exist; they are **not** two different APIs.

| Module | Role |
|--------|------|
| **`gateway/rest_shim.py`** | **Canonical implementation.** IPBox-compatible REST on `:30200` (`/api/v1/comp/items`, `/api/v1/action/action`) for **transition only** — lets existing [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) talk to the open hub while the companion is built. Wired to `UDPBus` + `DeviceRegistry`. |
| **`gateway/rest_api.py`** | **Backward-compat alias** — re-exports `RESTShim` as `RESTApp` and `create_app` so older imports and `tests/test_rest_api.py` keep working. No separate logic. |

The name **shim** (not `rest_api`) signals intent from the architecture spec: this layer is a **temporary bridge**, not the product northbound API. The product API is **`gateway_api.py`** (own REST `/api/v1/` + WebSocket `/ws`) — implemented. API docs for RapidAPI for Mac and GetAPI: [`docs/api/README.md`](docs/api/).

Do **not** extend IPBox REST parity (scenes, moods, project DB) in `rest_shim`; that stays in HA.

## What exists today

### Fase 1 (stable)

- **`gateway/payloads/`** — encode/decode relay, dimmer, input (incl. `B-…E` button events)
- **`gateway/config.py`** — env-based hub/module addresses, poll interval, simulated mode

### Fase 2 (current work)

- **`gateway/udp_bus.py`** — async UDP client, background poll loop (`P0000` / `I9900` / `I0000`), packet listeners, `GATEWAY_SIMULATED=1` for tests
- **`gateway/device_registry.py`** — relay/dimmer state from replies; input button press/release events
- **`gateway/installation.py`** — loads `devices.json`; `make_entity_id(ip, type, ch)` → `"10.10.1.30:relay:0"`; optional `ipbox_id` lookup for shim; derived into `GatewayConfig.field_modules`
- **`gateway/rest_shim.py`** — transition REST shim (see table above); uses `ipbox_id_to_channel()` for IPBox-compatible ID lookup
- **`gateway/main.py`** — dev entrypoint: starts UDP bus → registry → REST shim on `GATEWAY_REST_HOST`:`GATEWAY_REST_PORT` (default `0.0.0.0:30200`); registers modules from `InstallationConfig` if `devices.json` is loaded
- **`devices.json`** (repo root) — installation channels with optional `ipbox_id` (IPBox comp_id, shim only); loaded via `GATEWAY_DEVICES_FILE` env
- **`gateway/discovery.py`** — standalone HTTP sweep + optional UDP/10001 probe; see [Discovery tools](#discovery-tools-optional-provisioning) below
- **`gateway/__main__discover.py`** — CLI: `python -m gateway.discover`

## What exists today

- **`gateway_api.py`** — WebSocket `/ws` + REST `/api/v1/` (product northbound); uses `entity_id` not `ipbox_id`; see [`docs/api/`](docs/api/) for PAW/GetAPI import
- **`ipbuilding_gateway/`** — HA Supervisor add-on (Docker, `config.yaml`, `host_network: true`); persistent `/data/devices.json`; REST shim opt-in; see [`ipbuilding_gateway/DOCS.md`](ipbuilding_gateway/DOCS.md)
- **HA companion (separate repo)** — [`markminnoye/ha-ipbuilding-gateway`](https://github.com/markminnoye/ha-ipbuilding-gateway); switch, light, button, sensor entities; WebSocket coordinator; Supervisor auto-detection. Install via HACS → Integrations.
- **EEPROM sync** (Fase 8) still open

> **Note (2026-06-05):** the companion lived in `ha-ipbuilding-gateway/` in this repo until today and has been moved to its own repo ([`markminnoye/ha-ipbuilding-gateway`](https://github.com/markminnoye/ha-ipbuilding-gateway)) so HACS accepts it as an Integration (this repo's root is an add-on repository, which HACS rejects as an Integration). Update any existing HACS custom-repo URL accordingly.

## ID model

| Concept | Format | Stored? | Used by |
|---------|--------|---------|---------|
| `entity_id` | `"10.10.1.30:relay:0"` | No — derived from `(ip, type, ch)` | Product API, WebSocket, companion |
| `ipbox_id` | integer `547` | Optional in `devices.json` per channel | REST shim only (HA-IPBuilding transition) |

`ipbox_id` disappears when the shim is retired. `entity_id` is always `make_entity_id(ip, type, ch)`.

## Long-press detection (button timer)

Physical IP1100PoE wall switches produce only `press` and `release`
edges on the field bus (`B-…E`, see Sprint 5 evidence). The gateway
classifies the press→release interval into a `long_press` event using a
per-button timer:

- `press`  → broadcast `button_event.action="press"`, arm a
  `loop.call_later(threshold, ...)` timer
- threshold reached while still pressed → broadcast `long_press`
- `release` → cancel the timer, broadcast `release`

The threshold is read from `installation.buttons[*].hold_threshold_s`
(default 1.5 s), which is normally seeded from
`getButtons.func2.holdSeconds` on the IP1100PoE. This is the same
drempelwaarde the IPBox uses — see
`resources_and_docs/IPBUILDING_KNOWLEDGE.md` §12.7.

WebSocket `snapshot` and the new companion (v0.4.0) carry a
`schema_version: 2` field; v1 clients ignore unknown fields and
unknown `action` values, so this is backward-compatible.

REST error responses (plan §A) use typed HTTP status codes (400/404/422/
500/501/504) with a `{"error": "<code>", "message": "...", "details": {...}}`
body, replacing the old `200 + {"ok": false, "error": "..."}` pattern.
URL paths are unchanged.

## Import IPBox → HA

`scripts/import_ipbox_to_ha.py` reads the IP1100PoE `getButtons` endpoint
(single source of truth for the knop → uitgang mapping) and optionally
the IPBox REST `/comp/items` for channel naming, then writes four files
to the output directory:

- `automations.yaml`     import-ready HA automations
- `helpers.yaml`         `input_boolean` direction helpers
- `import_report.md`     conversion report + warnings
- `checksum.txt`         SHA256 of inputs (idempotency gate)

Idempotent: re-running with an unchanged source produces a no-op.
Existing helpers are never silently overwritten on name/icon conflicts.

```bash
# Default: read getButtons from 10.10.1.50 + /comp/items from IPBox.
python3 scripts/import_ipbox_to_ha.py \
    --ipbox-host 192.168.0.185 \
    --out ./out

# Only getButtons — useful when IPBox REST is no longer reachable.
python3 scripts/import_ipbox_to_ha.py --no-ipbox --out ./out
```

## Discovery tools (optional provisioning)

| Tool | Requires | Output |
|------|----------|--------|
| `python scripts/discover_from_ipbox.py` | IPBox WebConfig + session cookie | Full `devices.json` with `ipbox_id` per channel |
| `python -m gateway.discover` | IPBuilding VLAN access | Draft `devices.json` — no `ipbox_id`, channels empty |

```bash
# Migrate from IPBox (full channels + ipbox_id for shim)
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python scripts/discover_from_ipbox.py

# Open gateway discovery (no IPBox needed; run RE spike first — see evidence/)
python -m gateway.discover --range-start 30 --range-end 59
python -m gateway.discover --no-arp   # HTTP-only fallback
```

**ARP-first discovery** (default since 2026-06-03):
ping-sweep → ARP OUI `00:24:77` → HTTP `getSysSet` + `backupConfig` → `model`/`type` from `device.refNr`, channel labels from `channels[]`; `--no-backup-config` for getSysSet-only.
See [`resources_and_docs/evidence/2026-06-03_arp_discover_spike.md`](resources_and_docs/evidence/2026-06-03_arp_discover_spike.md) for field-test evidence.

## Configuration (environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GATEWAY_HUB_IP` | `10.10.1.1` | Documented hub address (modules send replies here) |
| `GATEWAY_RELAY_IP` / `GATEWAY_DIMMER_IP` / `GATEWAY_INPUT_IP` | `.30` / `.40` / `.50` | Lab poll targets when `GATEWAY_USE_ENV_DEFAULTS=1` or `GATEWAY_SIMULATED=1` |
| `GATEWAY_USE_ENV_DEFAULTS` | `0` | Opt-in: poll env relay/dimmer/input IPs when `devices.json` is missing or invalid (off in production) |
| `GATEWAY_POLL_INTERVAL` | `2.0` | Seconds between input (IP1100) poll rounds (`I0000`) |
| `GATEWAY_ACTUATOR_POLL_INTERVAL` | `20.0` | Seconds between relay/dimmer keep-alive polls (`P0000` / `I9900`) |
| `GATEWAY_REST_HOST` / `GATEWAY_REST_PORT` | `0.0.0.0` / `30200` | REST shim listen address (shim is **disabled by default** — set `GATEWAY_REST_SHIM_ENABLED=1` to enable) |
| `GATEWAY_REST_SHIM_ENABLED` | `0` | Enable the IPBox REST shim on `:30200` (for migration only) |
| `GATEWAY_API_PORT` | `8080` | Product northbound REST + WebSocket port |
| `GATEWAY_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `GATEWAY_DEVICES_FILE` | `./devices.json` | Path to installation config; if set, `field_modules` is derived from it and env IP overrides are ignored |
| `GATEWAY_SIMULATED` | off | `1` / `true` — no real UDP socket; in-process reply simulation for dev/tests |
| `GATEWAY_FORCE_DISCOVER_ON_START` | off | `1` / `true` — run forced (merge) discovery at startup. Preserves names/rooms/active flags, updates IP/firmware, adds new modules as `active:false`. |

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

**Dev launcher (recommended on the Mac):** `./local/gateway/start.sh` supports `--sim`, `--init` (interactive refresh from the field bus) and `--help`. See [`local/README.md`](local/README.md) for the two-terminal HA workflow.

**Simulated (no hardware):**

```bash
GATEWAY_SIMULATED=1 PYTHONPATH=. .venv/bin/python -m gateway
```

**Against the field bus** (host on `10.10.1.x` with reachability to modules; `10.10.1.1` hub IP optional — see `ipbuilding_gateway/DOCS.md`):

```bash
PYTHONPATH=. .venv/bin/python -m gateway
```

Logs state changes and button events; REST shim answers on port 30200 for legacy HA integration tests.

## RE / evidence

- [RE_STATE.md](resources_and_docs/RE_STATE.md)
- [Field bus capability matrix](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md)
- [Sprint 5 input completion](resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md)
