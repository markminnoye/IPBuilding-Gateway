# IPBuilding field bus library (`gateway/`)

Python package for **UDP/1001** communication with IPBuilding field modules (relay, dimmer, input).

## Product direction

We are building an **open replacement for the IPBox hub role** on the field bus (`10.10.1.1`) — **not** an IPBox REST clone on port 30200.

| Layer | Status (2026-05-22) |
|-------|------------------------|
| **Fase 1 — wire + codecs** | **Done** — RE Sprint 1–5; `gateway/payloads/` + tests |
| **Fase 2 — hub service** | **Open** — poll-loop, `device_registry`, REST-shim productiepad |
| **Fase 3+ — northbound** | **Open** — WebSocket `/ws`, HA add-on, `ipbuilding-open` companion |

Architecture: [Gateway architecture design](docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Canonical RE status: [RE_STATE.md](resources_and_docs/RE_STATE.md). Doc index: [resources_and_docs/README.md](resources_and_docs/README.md).

**Principle:** thin field-bus transport only; scenes and button→action logic live in **Home Assistant**, not in the gateway container.

## What exists today

- **`gateway/payloads/`** — encode/decode relay, dimmer, input (incl. `B-…E` button events)
- **`gateway/udp_bus.py`** — async UDP send/receive, reply correlation (`GATEWAY_SIMULATED=1` for tests)
- **`gateway/main.py`** — dev entrypoint; starts UDP bus + experimental REST only

## Not built yet (Fase 2+)

- **`device_registry.py`** — in-memory devices and state
- **Hub poll loop** — e.g. input `I0000` on interval; relay/dimmer status from replies
- **`gateway_api.py`** — WebSocket `/ws` + REST `/api/v1/`
- **`rest_shim.py`** — IPBox `:30200` transition shim (replace prototype below)
- HA add-on packaging, `ipbuilding-open` companion

## Experimental — do not treat as product API

- **`gateway/rest_api.py`** — RE/debug prototype; target rename/refactor → **`rest_shim.py`** (transition only). Product API: **`gateway_api.py`**.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-gateway.txt pytest pytest-asyncio
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
```

## Simulated UDP (no hardware)

```bash
GATEWAY_SIMULATED=1 .venv/bin/python -m gateway
```

Starts the experimental REST shim for debugging only — not a field-bus hub replacement.

## RE / evidence

- [RE_STATE.md](resources_and_docs/RE_STATE.md)
- [Field bus capability matrix](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md)
- [Sprint 5 input completion](resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md)
