# Documentation index (`resources_and_docs/`)

Last updated: 2026-05-22 (reorganized)

**Navigatie:** agents starten bij [RE_STATE.md](RE_STATE.md) (canonieke status). Dit bestand is de **volledige index** na mappen-reorganisatie (zie [REORGANIZE_BRIEF.md](REORGANIZE_BRIEF.md)).

## Canoniek (root — altijd eerst)

| Bestand | Rol |
|---------|-----|
| [RE_STATE.md](RE_STATE.md) | Source of truth RE + volgende acties (post–Fase 1) |
| [CAPTURES.md](CAPTURES.md) | Waar PCAPs staan (`captures/`, archive, Downloads) |
| [2026-05-17_ipbuilding_fieldbus_capability_matrix.md](2026-05-17_ipbuilding_fieldbus_capability_matrix.md) | Wat de eigen hub op UDP/1001 kan |
| [IPBUILDING_KNOWLEDGE.md](IPBUILDING_KNOWLEDGE.md) | Diepte-kennis (T1) — alleen relevante secties laden |

## Architectuur & product (links naar `docs/`)

| Bestand | Rol |
|---------|-----|
| [../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md) | Goedgekeurd northbound (HA add-on + companion) |
| [../README_gateway.md](../README_gateway.md) | `gateway/` package — Fase 1 done, Fase 2 open |
| [../AGENTS.md](../AGENTS.md) | Agent brief |

## `workflows/` — capture, mirror, runbooks

| Bestand | Rol |
|---------|-----|
| [workflows/IPBUILDING_CAPTURE_WORKFLOW.md](workflows/IPBUILDING_CAPTURE_WORKFLOW.md) | Golden capture-run (mirror, dumpcap, stimulus) |
| [workflows/CAPTURE_LIVE_STATUS.md](workflows/CAPTURE_LIVE_STATUS.md) | Live netwerk/mirror-gates |
| [workflows/SUBAGENT_CAPTURE_EXECUTION_WORKFLOW.md](workflows/SUBAGENT_CAPTURE_EXECUTION_WORKFLOW.md) | Subagent capture-taken |
| [workflows/2026-05-14_relay_run_a_operational_playbook.md](workflows/2026-05-14_relay_run_a_operational_playbook.md) | Relay Run A (standaard **7←15**) |
| `workflows/*.yaml` (14) | Orchestrator/manifest-runbooks (`ipbuilding_golden`, `push_pull_*`, `relay_*`, `sprint4_*`, `sprint5_input_physical`) |

## `evidence/` — RE sessies (gedateerde markdown)

| Onderwerp | Bestanden |
|-----------|-----------|
| Relay | [2026-05-04_relay_payload_correlation.md](evidence/2026-05-04_relay_payload_correlation.md), [2026-05-14_relay_quiet_evening_session_notes.md](evidence/2026-05-14_relay_quiet_evening_session_notes.md), [2026-05-14_udp_payload_semantics_matrix.md](evidence/2026-05-14_udp_payload_semantics_matrix.md) |
| Dimmer | [2026-05-17_dimmer_I0154xxx_full_decode.md](evidence/2026-05-17_dimmer_I0154xxx_full_decode.md), [2026-05-03_dimmer_udp_payload_correlation.md](evidence/2026-05-03_dimmer_udp_payload_correlation.md), [2026-05-04_dimmer_channel_value_sweep.md](evidence/2026-05-04_dimmer_channel_value_sweep.md), [2026-06-22_dimmer_p2p_hold_dim_capture.md](evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md) — **operator-keuze:** [fieldbus matrix §Dimmer](2026-05-17_ipbuilding_fieldbus_capability_matrix.md#dimmer-welk-commando-wanneer) |
| Input | [2026-05-17_ip1100_input_payload_decode.md](evidence/2026-05-17_ip1100_input_payload_decode.md), [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md), [2026-05-22_sprint5_input_10-25_session_notes.md](evidence/2026-05-22_sprint5_input_10-25_session_notes.md) |
| POV / bidirectioneel | [2026-05-15_capture_bidirectional_explainer.md](evidence/2026-05-15_capture_bidirectional_explainer.md), [2026-05-05_push_pull_experiment_contract.md](evidence/2026-05-05_push_pull_experiment_contract.md), push-pull sessienotities `2026-05-14*`, `2026-05-15*` in `evidence/` |
| Golden / correlatie | [2026-05-04_golden_session_udp_correlation.md](evidence/2026-05-04_golden_session_udp_correlation.md), [2026-05-14_dimmer_rest_udp_timeline_writeup.md](evidence/2026-05-14_dimmer_rest_udp_timeline_writeup.md), [2026-05-15_long_capture_reference.md](evidence/2026-05-15_long_capture_reference.md) |

## `reference/` — IPBox REST, inventory, wizards, scan

| Bestand | Rol |
|---------|-----|
| [reference/IPBOX_REST_API_TEST_CALLS.md](reference/IPBOX_REST_API_TEST_CALLS.md) | IPBox REST referentie (stimulus) |
| [reference/device-inventory-local-ipbox.md](reference/device-inventory-local-ipbox.md) | Lokale device-lijst referentie |
| [reference/2026-05-17_RE_WIZARDS_PLAN.md](reference/2026-05-17_RE_WIZARDS_PLAN.md) | WebConfig wizard URL-kaart |
| [reference/2026-05-17_RE_WIZARDS_Configuration_stack_analysis.md](reference/2026-05-17_RE_WIZARDS_Configuration_stack_analysis.md) | Config stack |
| [reference/2026-05-17_scan_modules_http_analysis.md](reference/2026-05-17_scan_modules_http_analysis.md) | Scan Modules HTTP |
| [reference/2026-05-17_scan_modules_udp_payloads.md](reference/2026-05-17_scan_modules_udp_payloads.md) | UDP/10001 discovery |
| [reference/2026-06-14-deployment-hardware-evaluation.md](reference/2026-06-14-deployment-hardware-evaluation.md) | Deployment B/C hardware: Pi 3B, ESP32, Pico W — effort & beslissing |

## `archive/` — historisch / deprecated

| Bestand | Opmerking |
|---------|-----------|
| [archive/NEXT_AGENT_STATUS_QUO_2026-05-03.md](archive/NEXT_AGENT_STATUS_QUO_2026-05-03.md) | Handoff snapshot; **niet** statusbron |
| [archive/2026-05-17_RE_TEST_PLAN_5_SPRINTS.md](archive/2026-05-17_RE_TEST_PLAN_5_SPRINTS.md) | Sprintplan — **CLOSED** 2026-05-22 |
| [archive/2026-05-17_ipbuilding_gateway_parity_matrix.md](archive/2026-05-17_ipbuilding_gateway_parity_matrix.md) | DEPRECATED → fieldbus matrix |
| [../docs/superpowers/plans/2026-05-17-ipbuilding-phase1-re-completion.md](../docs/superpowers/plans/2026-05-17-ipbuilding-phase1-re-completion.md) | Phase 1 plan — **CLOSED** |

## Binaries (T3)

| Pad | Opmerking |
|-----|-----------|
| `pcap_archive/long_capture.pcapng` | Enige grote PCAP in git |
| `Installatie handleiding (versie 6.0).pdf` | Fabrikant-PDF — niet standaard in context laden |
| `captures/` (repo-root) | Lokaal, gitignored — zie [CAPTURES.md](CAPTURES.md) |

## Code ↔ docs

| Code | Docs |
|------|------|
| `gateway/payloads/` | Dimmer/input/relay decode docs in `evidence/` |
| `scripts/*_payload_parser.py` | Zelfde families |
| `ipbuilding_capture_run.py` | `workflows/` capture workflow + runbooks |
