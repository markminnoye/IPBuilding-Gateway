# Context policy (IPBuilding repo)

Doel: **minimaal tokens**, maximale signal. Algemene principes: *context quality > quantity*, progressive disclosure, subagent-isolatie (vergelijk skill **context-engineering** indien geïnstalleerd).

## Vier buckets


| Bucket       | Actie                                                                                   |
| ------------ | --------------------------------------------------------------------------------------- |
| **Write**    | Feiten in repo (`resources_and_docs/`, sessienotities); niet alles in de chat herhalen. |
| **Select**   | Alleen secties/files pullen die bij de vraag passen.                                    |
| **Compress** | Tabellen > lange paragraaf; verwijs naar knowledge-doc i.p.v. kopiëren.                 |
| **Isolate**  | Zware taken splitsen (capture vs code vs netwerk).                                      |


## Progressive disclosure (dit project)


| Tier   | Wanneer                     | Voorbeelden                                                                                                               |
| ------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **T0** | Altijd in scope van de rule | `AGENTS.md`, deze file, `resources_and_docs/README.md` (index)                                                            |
| **T1** | Deep technical work         | `resources_and_docs/IPBUILDING_KNOWLEDGE.md` — **alleen relevante sectie**                                                |
| **T2** | Capture / RE / architectuur / Wizards | `RE_STATE.md`, `CAPTURES.md`, `evidence/2026-05-22_sprint5_input_physical_completion.md`, `2026-05-18-gateway-architecture-design.md`, `2026-05-17_ipbuilding_fieldbus_capability_matrix.md`, `workflows/CAPTURE_LIVE_STATUS.md`, `reference/IPBOX_REST_API_TEST_CALLS.md` (IPBox referentie), `archive/NEXT_AGENT_STATUS_QUO_*.md` (historisch) |
| **T3** | Zeldzaam / groot            | PDFs, volledige `.pcapng`, YAML golden runbook — **nooit** hele bestand in context tenzij slice-analyse                   |


## Anti-patterns

- Hele `IPBUILDING_KNOWLEDGE.md` of grote pcaps “voor context” laden.
- AGENTS.md-achtige tabellen dupliceren in antwoorden.
- Middelste van lange dumps als enige bron van waarheid (attention valt begin/einde aan).

## MCP / tools

- **wireshark-mcp:** gestructureerde pcap-stats — geen volledige capture in de chat.
- **UniFi MCP:** alleen voor switch/capture-config; geen brede device dumps tenzij nodig.

## Repo-onderhoud

- `**AGENTS.md`:** kort houden; detail naar knowledge + tier-T2 files.
- **Handoff:** canoniek `RE_STATE.md`; `NEXT_AGENT_STATUS_QUO_*.md` alleen historisch. PCAP-index: `CAPTURES.md`.