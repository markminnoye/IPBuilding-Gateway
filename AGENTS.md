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

**Veldbus-RE (afgesloten 2026-05-22):**
- 5-sprint RE: relay, dimmer, input wire (mirror POV) — afgerond
- Sprint 5 fysieke input (`B-…E`, mirror 7←13) — afgerond
- Veldtest relay/dimmer/input via open hub: 2026-06-01 (met mirror) + 2026-06-02 (zonder mirror) — PASS
  - Evidence: `resources_and_docs/evidence/2026-06-01_gateway_field_test.md`, `resources_and_docs/evidence/2026-06-02_relay_poll_i_ch_test.md`
- **Relay status poll RE (2026-06-02):** Scenario B — `I<ch>` geeft geen kanaalstatus; `P0000` blijft poll; status komt pas na `S`/`C`. Bewijs: `scripts/test_relay_poll.py`

**Implementatie (alfa 0.0.4 — 2026-06-04):**
- **Fase 1** UDP-protocol RE + `gateway/payloads/` + tests ✅
- **Fase 2** UDP Bus Manager, Device Registry, REST-shim, veldtest ✅ (2026-06-01)
- **Fase 3** `gateway_api.py` (WebSocket `/ws` + REST `/api/v1/`) ✅ (2026-06-02)
- **Fase 4** Gateway als HA add-on: Dockerfile + `config.yaml` + Supervisor auto-detection + GH Actions CI ✅ (2026-06-04, v0.0.1 → v0.0.4)
- **Fase 5** Companion `ipbuilding-gateway-ha` (entities, button→actie via HA) ✅ (2026-06-02)
- **Fase 6** Input-events IP1100PoE via WS → companion ✅ (verpakt in Fase 5)
- **Fase 7** Runtime auto-discovery: init-sweep + passieve ARP-monitor + forced REST + write-policy ✅ (2026-06-04, v0.0.4)
  - Spec: [`docs/superpowers/specs/2026-06-04-runtime-auto-discovery-design.md`](docs/superpowers/specs/2026-06-04-runtime-auto-discovery-design.md)
  - Code: `gateway/auto_discovery.py` (`ArpMonitor`, `DiscoveryOrchestrator`, `AtomicWriter`)
  - 7 nieuwe add-on options + 4 nieuwe WS-events + `POST /api/v1/discover` endpoint

**Open:**
- Optionele RE: input logical flow IPBox-project (referentie, niet blokkerend)
- **Fase 8** EEPROM-sync (`POST /api/v1/provision/autonomy`) — REST-stub aanwezig; HTTP `saveAutonomy`-call nog niet geïmplementeerd
- **Fase 9** MQTT adapter · **Fase 10** Matter bridge · **Fase 11** Cover/screen entities · **Fase 12** ESP32 POC — **design draft:** [`docs/superpowers/specs/2026-07-09-embedded-ipbuilding-gateway-design.md`](docs/superpowers/specs/2026-07-09-embedded-ipbuilding-gateway-design.md) (lab-hardware: ESP32-S3-ETH besteld; nieuwe repo `embedded-ipbuilding-gateway` na architect-goedkeuring)
- **Fase 13** Periodieke 24h ARP-sweep + HTTP-identify voor bestaande modules tijdens passieve monitor (backlog uit runtime-discovery spec §15)
- **Bind `10.10.1.1`** (optioneel) — gateway expliciet op hub-IP wanneer IPBox uit; zonder-mirror hub-validatie **PASS 2026-06-02** — klaar voor gebruik, niet standaard geactiveerd

**Canonieke RE-status:** [resources_and_docs/RE_STATE.md](resources_and_docs/RE_STATE.md) — Fase 1 RE **afgesloten** 2026-05-22. PCAP-index: [CAPTURES.md](resources_and_docs/CAPTURES.md).

**Sprint 5 afsluiting:** [resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md](resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md) (incl. § Architectuurdoel: hub beslist bij druk — logica in HA, niet in gateway)

**Field-bus capabilities:** [resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md)

**RE Wizards (IPBox WebConfig):** [resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md](resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md) — referentie; geen verplicht eindmodel.

---

## Scope (MVP — actief)

**Buiten scope (voorlopig):** EEPROM-sync / `saveAutonomy` / button→relay provisioning in gateway (Fase 8). Logica hoort in HA; EEPROM-push is geen MVP-blocker.

**MVP-doel:** gateway add-on + companion stabiel testbaar — entities, realtime state, button-events, handmatige `devices.json`. Discovery-events in companion en operator-UI zijn nice-to-have, geen MVP.

## Volgende focus (implementatie)

1. **Companion MVP afronden** — HA 2026.3-compat, `active: false` respecteren, dynamische entities bij discovery (minimaal voor test)
2. **Companion uitbreidingen (v2, post-MVP)** — reageren op `device_added`/`device_removed`/`device_ip_changed`/`device_firmware_changed` (`binary_sensor`, `ipbuilding.discover` service, configureer-UI)
3. ~~**Fase 8 — EEPROM-sync**~~ — uitgesteld (buiten MVP-scope)
4. **Bind `10.10.1.1`** (optioneel) — gateway expliciet op hub-IP wanneer IPBox uit; zonder-mirror hub-validatie **PASS 2026-06-02**; standalone **Pi 3B** (Deployment B): [`reference/2026-06-14-deployment-hardware-evaluation.md`](resources_and_docs/reference/2026-06-14-deployment-hardware-evaluation.md)
5. Captures bij regressie; standaard mirror **7←15** ([playbook](resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md))
6. **Migratiepad** — bestaande HA-IPBuilding installaties overzetten via [§7 ARCHITECTURE.md](ARCHITECTURE.md) (import uit IPBox → REST shim actief → companion installeren → button-mapping in HA → IPBox afkoppelen)

### Companion issues (gefilmd 2026-06-15, [ipbuilding-gateway-ha](https://github.com/markminnoye/ha-ipbuilding-gateway))

Companion-issues geïnspireerd op de legacy [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) integratie. Logica hoort in HA, niet in de gateway; deze issues raken daarom **alleen** de companion.

- [ha-ipbuilding-gateway#2 — Onboarding: koppel channels aan HA-areas (room → area)](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/2) — open. Eerste installatie-ervaring. Lees legacy `entity.py` (`suggested_area` patroon) en `_register_hubs` voor de device-tree opzet.
- [ha-ipbuilding-gateway#3 — Companion: correcte HA application / hub integratie-metadata](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/3) — **afgerond in companion v0.2.1** (`manifest.json`, drie-tier device tree gateway → module → channel, expliciete device-registry voor gateway + modules, `sw_version` via `/api/v1/status`).
- [ha-ipbuilding-gateway#4 — Companion: hardware knoppen (IP1100PoE) als routeable entities](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/4) — open. Gateway moet `getButtons` meenemen in `/api/v1/devices` snapshot; companion `button.py` moet dynamisch via `register_platform` werken. Vervolg-issue (nog te filen): button→action mappings in HA i.p.v. in IPBox-project DB.

Legacy referentie (geen verplicht eindmodel, alleen inspiratie): [`markminnoye/HA-IPBuilding/custom_components/ipbuilding/`](https://github.com/markminnoye/HA-IPBuilding/tree/main/custom_components/ipbuilding) — `entity.py` (`suggested_area`, `via_device`), `__init__.py` (`_register_hubs`, `HUB_BY_TYPE`), `const.py` (type-constanten), `button.py` (legacy `ButtonEntity` vs onze `EventEntity`).

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
| **home-assistant-best-practices** | HA automation/helper/dashboard keuzes; vermijd Jinja2 waar native opties bestaan; YAML-only integraties vs. AppDaemon |

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
- **T2:** `RE_STATE.md`, `CAPTURES.md`, sprint5 completion, gateway-architectuur, fieldbus matrix, capture workflows, [`docs/api/`](docs/api/) — northbound REST (`rest.md`, Postman v2.1 collection) + WS message catalog (`websocket.md`) + module resource (`modules.md`) + discovery (`discovery.md`)
- **T3:** PDFs, volledige pcaps (`captures/` lokaal)
- **Doc-structuur:** [REORGANIZE_BRIEF.md](resources_and_docs/REORGANIZE_BRIEF.md) — uitgevoerd 2026-05-22 (`workflows/`, `evidence/`, `reference/`, `archive/`)

**Code:** `gateway/payloads/`, `gateway/udp_bus.py`, `gateway/device_registry.py`, `gateway/installation.py`, `gateway/discovery.py`, `gateway/auto_discovery.py`, `gateway/module_metadata.py`, `gateway/rest_shim.py` (+ alias `rest_api.py`), `gateway/main.py`, `gateway/gateway_api.py`, `gateway/config.py` — zie [README_gateway.md](README_gateway.md).

---

## Einddoel

**IPBuilding Gateway** HA Add-on (v0.0.4): UDP/1001 veldbus-hub met runtime auto-discovery; WebSocket `/ws` + REST `/api/v1/` naar **`ipbuilding-gateway-ha`**; optionele REST-shim `:30200` in transitie. Scenes/logica in HA, niet in de gateway.
