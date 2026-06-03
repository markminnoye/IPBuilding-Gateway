# IPBuilding — agent brief

**Doel:** een **eigen open centrale** bouwen die de rol van de propriëtaire **IPBox op de veldbus** overneemt (UDP/1001 naar relay/dimmer/input modules).

**Niet het doel:** de IPBox REST API op `:30200` nabootsen. IPBox REST en WebConfig blijven **referentie** voor RE/correlatie en het bestaande HA-project — geen verplicht northbound-contract voor de nieuwe centrale.

**Productprincipe (2026-05-22):** de gateway is een **dunne veldbus-hub** (pollen, commando’s, `B-…E` doorgeven). **Geen** IPBox-pariteit voor sferen/scenes, knop→actie-regels of andere “slimme” logica in de gateway — dat hoort in **Home Assistant** (scenes, automations, Matter). Minimale mapping (device/kanaal ↔ veldbus) in de companion; geen tweede projectdatabase in de add-on.

**Architectuur (goedgekeurd):** [`ARCHITECTURE.md`](ARCHITECTURE.md) — deployment-varianten (HA add-on / Docker standalone / ESP32 POC), gateway-config model (naam/room/type/watt/active), northbound-protocol (WS/MQTT/Matter), migratiepad + EEPROM-sync. Vervangt [docs/superpowers/specs/2026-05-18-gateway-architecture-design.md](docs/superpowers/specs/2026-05-18-gateway-architecture-design.md).

**Fase 1 RE (veldbus):** relay, dimmer en input **wire** afgerond (5-sprint plan + Sprint 5 fysieke input). IPBox GUI (wizards, provisioning) deels gedocumenteerd als **referentie**, niet als eindmodel. Zie [RE_STATE.md](resources_and_docs/RE_STATE.md).

**Diepte-facts:** `resources_and_docs/IPBUILDING_KNOWLEDGE.md` — niet herschrijven in de chat; verwijs naar sectie.

**Token-/contextbeleid:** `docs/context-policy.md`.

---

## Status

| Done | Open |
|------|------|
| 5-sprint RE (relay/dimmer/input wire, mirror POV) | Optionele RE: input logical flow IPBox-project (referentie) |
| Sprint 5 fysieke input (`B-…E`, mirror 7←13) | **Fase 3** — `gateway_api.py` ✅ + **Fase 5** — `ipbuilding-gateway-ha` ✅ |
| Fase 2 voltooid (2026-06-01): `devices.json`, poll-loop, registry, REST-shim, veldtest alle checks PASS | Dun provisioning (entiteiten in HA, niet in gateway) |
| `gateway/payloads/` + tests | Productie add-on + companion WebSocket |
| Architectuur northbound (2026-05-18) | **Bind `10.10.1.1`** — optioneel: gateway expliciet op hub-IP wanneer IPBox uit |
| **Relay status poll RE (2026-06-02):** Scenario B — `I<ch>` geen kanaalstatus; `P0000` blijft poll; status alleen na `S`/`C`. Bewijs: `scripts/test_relay_poll.py`, `evidence/2026-06-02_relay_poll_i_ch_test.md` | |
| Veldtest relay/dimmer/input via open hub — 2026-06-01 + **zonder mirror** 2026-06-02 (evidence: `evidence/2026-06-01_gateway_field_test.md`) | |

**Canonieke RE-status:** [resources_and_docs/RE_STATE.md](resources_and_docs/RE_STATE.md) — Fase 1 RE **afgesloten** 2026-05-22. PCAP-index: [CAPTURES.md](resources_and_docs/CAPTURES.md).

**Sprint 5 afsluiting:** [resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md](resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md) (incl. § Architectuurdoel: hub beslist bij druk — logica in HA, niet in gateway)

**Field-bus capabilities:** [resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md)

**RE Wizards (IPBox WebConfig):** [resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md](resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md) — referentie; geen verplicht eindmodel.

---

## Volgende focus (implementatie)

1. **Fase 3 — `gateway_api.py`** — WebSocket `/ws` + REST `/api/v1/` (product northbound) ✅
2. **`ipbuilding-gateway-ha`** — entiteiten (switch, light, button, sensor); knop→actie via HA automations/scenes ✅
3. **HA add-on** — packaging zodra companion stabiel is (Dockerfile + `config.yaml`)
4. **Bind `10.10.1.1`** (optioneel) — gateway expliciet op hub-IP wanneer IPBox uit; zonder-mirror hub-validatie **PASS 2026-06-02**
5. Captures bij regressie; standaard mirror **7←15** ([playbook](resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md))

**IPBox thuis-LAN (RE-stimulus / archief):** `192.168.0.185` (REST `:30200`, WebConfig). Veld-bus hub: `10.10.1.1`. Zie `IPBUILDING_KNOWLEDGE.md` §3.0.

---

## Volgende sprint (uitgesteld — waarschijnlijk overslaan)

**Gepland voor optionele documentatie-RE (niet blokkerend voor gateway):**

- IPBox **sferen / moods:** `http://192.168.0.185/general/Configuration/Moods/Index` (WebConfig, geen veldbus-wire vereist).
- Gerelateerd: scenes, input→meerdere acties in IPBox-project (§12, REST `action`).

**Intentie:** waarschijnlijk **links laten liggen** — sferen en automatisering in **HA**; gateway alleen veldbus transport. Bij start van die RE: kort HAR/pcap alleen als referentie voor migratie uit bestaand IPBox-project, niet om parity te bouwen.

---

## Netwerk (referentie)

| Rol | IP | Poort / protocol |
|-----|-----|------------------|
| IPBox REST (thuis-LAN; referentie) | host uit router (archief `192.168.0.185`) | 30200 |
| Veld-bus hub (IPBox of gateway) | `10.10.1.1` | UDP/1001 |
| Relays | `10.10.1.30` | 1001, 80 |
| Dimmers | `10.10.1.40` | 1001, 80 |
| Inputs | `10.10.1.50` | 1001, 80 |

**HA vandaag (legacy):** [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) — IPBox REST. **Doel:** companion + gateway add-on per architectuurdoc.

---

## Skills

| Skill | Trigger |
|-------|---------|
| **protocol-reverse-engineering** | PCAP, Wireshark MCP, UDP correlatie |
| **binary-analysis-patterns** | Payload-structuur, parsers |
| **network-engineer** | VLAN, mirror POV |
| **async-python-patterns** | asyncio veldbus + gateway service |
| **home-assistant-custom-integration** | companion, config flow, entities |
| **home-assistant-integrations-addons** | add-on, Supervisor, ha-mcp |
| **home-assistant-entities-services** | services, entity_id, device registry |
| **home-assistant-automation-scripts** | automations, scripts, scenes (logica in HA) |
| **home-assistant-dashboards-cards** | Lovelace, dashboards |
| **home-assistant-esphome** | ESPHome (indien relevant) |
| **home-assistant-awtrix** | AWTRIX (indien relevant) |

Bron HA-skills: [bradsjm/hassio-addons](https://github.com/bradsjm/hassio-addons) (`addon-opencode/skills/`).

---

## Documentation Priority

1. Documentation tools (e.g., `ha_get_domain_docs()`).
2. Official Web Site ([https://www.home-assistant.io/docs/](https://www.home-assistant.io/docs/))
3. Github Repository ([home-assistant/home-assistant.io](https://github.com/home-assistant/home-assistant.io))
4. Search tools

## Search and Freshness

- Assume your knowledge may be out of date.
- When versions, current behavior, or external facts matter, verify them with search tools instead of assuming.

---

## Doc-index (tier — `docs/context-policy.md`)

- **Index:** [resources_and_docs/README.md](resources_and_docs/README.md) (volledig), [docs/README.md](docs/README.md) (specs/plans)
- **T0:** `AGENTS.md`, `docs/context-policy.md`
- **T1:** `IPBUILDING_KNOWLEDGE.md` (sectie-gewijs)
- **T2:** `RE_STATE.md`, `CAPTURES.md`, sprint5 completion, gateway-architectuur, fieldbus matrix, capture workflows, [`docs/api/`](docs/api/) — northbound REST (Postman v2.1) + WS message catalog for PAW/GetAPI
- **T3:** PDFs, volledige pcaps (`captures/` lokaal)
- **Doc-structuur:** [REORGANIZE_BRIEF.md](resources_and_docs/REORGANIZE_BRIEF.md) — uitgevoerd 2026-05-22 (`workflows/`, `evidence/`, `reference/`, `archive/`)

**Code:** `gateway/payloads/`, `gateway/udp_bus.py`, `gateway/device_registry.py`, `gateway/rest_shim.py` (+ alias `rest_api.py`), `gateway/main.py`, `gateway/gateway_api.py` — zie [README_gateway.md](README_gateway.md).

---

## Einddoel

**IPBuilding Gateway** HA Add-on: UDP/1001 veldbus-hub; WebSocket naar **`ipbuilding-gateway-ha`**; optionele REST-shim `:30200` in transitie. Scenes/logica in HA, niet in de gateway. Netwerk: HA Green + VLAN trunk (architectuurdoc § Netwerkconstraint).
