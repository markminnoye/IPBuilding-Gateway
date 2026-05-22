# IPBuilding Phase 1 RE Completion — 4-Sprint Plan

> **Status: CLOSED (2026-05-22)** — Sprints Dimmer, Input, Gateway, Matrix (2026-05-17); Sprint 5 fysieke input (2026-05-22). [completion doc](../../resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md). **Volgende:** Gateway Fase 2 (hub op `10.10.1.1`) — [architectuurdoc](../specs/2026-05-18-gateway-architecture-design.md), `AGENTS.md`.

**Goal (historisch):** Fase 1 RE afronden + gateway-skeleton — **bereikt** 2026-05-22.

## Deliverables

| Sprint | Output |
|--------|--------|
| Dimmer | [2026-05-17_dimmer_I0154xxx_full_decode.md](../../resources_and_docs/evidence/2026-05-17_dimmer_I0154xxx_full_decode.md) |
| Input | [2026-05-17_ip1100_input_payload_decode.md](../../resources_and_docs/evidence/2026-05-17_ip1100_input_payload_decode.md), `scripts/input_payload_parser.py` |
| Gateway | `gateway/` package, `tests/`, [README_gateway.md](../../README_gateway.md) |
| Matrix | [RE_STATE.md](../../resources_and_docs/RE_STATE.md), [semantics matrix](../../resources_and_docs/evidence/2026-05-14_udp_payload_semantics_matrix.md), [field bus capability matrix](../../resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md) (parity doc deprecated) |

## Verification

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-gateway.txt pytest pytest-asyncio
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
PYTHONPATH=. python3 scripts/input_payload_parser.py --self-test
```

## Next

**Gateway Fase 2** (architectuurdoc) — thin UDP hub + companion; scenes/sferen in HA.

**Uitgestelde optionele RE:** IPBox Moods `http://192.168.0.185/general/Configuration/Moods/Index` — waarschijnlijk overslaan (`AGENTS.md`, knowledge §10.6).
