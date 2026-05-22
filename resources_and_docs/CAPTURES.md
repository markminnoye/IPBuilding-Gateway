# Capture artifacts — waar staan de bestanden?

Last updated: 2026-05-22

Volledige doc-index: [README.md](README.md).

**Niet verwijderd:** lokale RE-captures staan nog op schijf; ze worden alleen **niet** in git gecommit (`.gitignore`).

## Locaties

| Locatie | In git? | Inhoud |
|---------|---------|--------|
| **`captures/`** (repo-root) | Nee (`captures/` in `.gitignore`) | Orchestrator-runs: `capture.pcapng`, `manifest.jsonl`, `run.log` per sessie-map. **~16 MB** lokaal (mei 2026). |
| **`resources_and_docs/pcap_archive/`** | Ja (uitzondering) | Referentie-PCAP, bv. `long_capture.pcapng` (~708 KB). |
| **`tests/fixtures/minimal_udp1001_session/`** | Ja | Minimale fixture voor pytest/correlate-scripts. |
| **`~/Downloads/*.pcapng`** | Nee | Sprint 1–5 handmatige captures (Wireshark export); paden in `RE_STATE.md` evidence pointers. |
| **`/tmp/wireshark_mcp_*.pcapng`** | Nee | Tijdelijke MCP-rooktests (RE_STATE evidence). |

## Sessies in `captures/` (selectie)

Volledige lijst: `ls captures/` op de capture-Mac.

| Map / patroon | Doel |
|---------------|------|
| `2026-05-05T1040Z_user-full-capture/` | Bidirectioneel UDP, relay reply timing |
| `2026-05-14T*push-pull*` | Quiet-evening / idle / Run A retest |
| `sprint4_pov_comparison_20260517T012600Z/` | POV A/B/C mirror-vergelijking |
| `2026-05-17T210800Z_scan_modules/` | Scan Modules wizard |
| `RE_WIZARDS_2026-05-17T*` | WebConfig wizard pcaps |
| `2026-05-22T*sprint5*` | Sprint 5 input fysiek |

Analyse: Wireshark MCP (zie `.cursor/mcp.json`), `scripts/correlate_capture_session.py`, `scripts/udp1001_bidir_counts.py`.

## Workflow

Operationeel: [IPBUILDING_CAPTURE_WORKFLOW.md](workflows/IPBUILDING_CAPTURE_WORKFLOW.md). Live gate: [CAPTURE_LIVE_STATUS.md](workflows/CAPTURE_LIVE_STATUS.md).

## Backup / opruimen

- **Backup:** kopieer `captures/` naar NAS of externe schijf vóór grote disk-opruiming.
- **Verwijderen:** alleen na export van conclusies naar `resources_and_docs/*.md`; bewijs staat in markdown + `RE_STATE.md`, niet alleen in PCAP.
