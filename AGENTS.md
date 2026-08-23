# IPBuilding — agent brief

**Doel:** open centrale die de **IPBox hub-rol op de veldbus** overneemt (UDP/1001 → relay/dimmer/input).

**Niet het doel:** IPBox REST `:30200` nabootsen. IPBox REST/WebConfig = **referentie** voor RE en migratie — geen northbound-contract.

**Productprincipe:** gateway = **dunne veldbus-hub** (pollen, commando's, `B-…E` doorgeven). Sferen/scenes/knop→actie in **Home Assistant**, niet in de gateway. Companion: minimale mapping; geen tweede project-DB in de add-on.

| Onderwerp | Canoniek |
|-----------|----------|
| Architectuur | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| RE-status & bewijs | [`resources_and_docs/RE_STATE.md`](resources_and_docs/RE_STATE.md) |
| Diepte-facts | [`resources_and_docs/IPBUILDING_KNOWLEDGE.md`](resources_and_docs/IPBUILDING_KNOWLEDGE.md) (sectie-gewijs) |
| Context/tokens | [`docs/context-policy.md`](docs/context-policy.md) |
| Topologie / IPs | `.cursor/rules/ipbuilding-core.mdc`, knowledge §3 |
| Northbound API | [`docs/api/`](docs/api/) |
| Gateway code | [`README_gateway.md`](README_gateway.md) |

---

## Status (2026-06)

**Gateway alfa 0.0.4** — veldbus-hub, runtime auto-discovery, WS `/ws`, REST `/api/v1/`, HA add-on, companion-basis.

| Fase | Onderdeel | Status |
|------|-----------|--------|
| 1–7 | UDP RE, bus manager, registry, gateway API, add-on, companion WS, auto-discovery | ✅ |
| 8 | EEPROM-sync (`POST /api/v1/provision/autonomy`) | stub; buiten MVP |
| 9–13 | MQTT · Matter · covers · ESP32 POC · 24h ARP-sweep | backlog |

**Veldbus-RE:** afgesloten 2026-05-22. Veldtest open hub: PASS 2026-06-01/02. Detail: [`RE_STATE.md`](resources_and_docs/RE_STATE.md), evidence onder `resources_and_docs/evidence/`.

**Open (niet MVP):** optionele input logical-flow RE; bind `10.10.1.1` (klaar, niet standaard).

---

## MVP (actief)

Gateway add-on + companion **stabiel testbaar**: entities, realtime state, button-events, handmatige `devices.json`.

**Buiten MVP:** EEPROM-sync, IPBox-pariteit (sferen/scenes/wizards), discovery-UI in companion.

---

## Volgende focus

1. **Companion MVP** — HA 2026.3-compat, `active: false` respecteren, dynamische entities bij discovery
2. **[#4](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/4)** — hardware knoppen (IP1100PoE) als routeable entities (`getButtons` in `/api/v1/devices`; dynamische `button.py`)
3. **[#2](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/2)** — onboarding: channels → HA areas (`suggested_area`; legacy `entity.py`)
4. **Bind `10.10.1.1`** (optioneel) — hub-IP wanneer IPBox uit ([deployment-eval](resources_and_docs/reference/2026-06-14-deployment-hardware-evaluation.md))
5. Regressie-captures; standaard mirror **7←15** ([playbook](resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md))
6. **Migratiepad** — [ARCHITECTURE.md §7](ARCHITECTURE.md)

**Companion:** [ha-ipbuilding-gateway](https://github.com/markminnoye/ha-ipbuilding-gateway) · **#3** afgerond v0.2.1. Legacy inspiratie: [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) (geen eindmodel).

---

## Volgende sprint (uitgesteld)

IPBox sferen/moods RE — **waarschijnlijk overslaan**; logica in HA. Zie knowledge §10.6.

---

## Skills

`protocol-reverse-engineering` · `binary-analysis-patterns` · `network-engineer` · `async-python-patterns` · `home-assistant-*` (companion, add-on, entities, automations). Pad: `.agents/skills/`.

---

## Code entrypoints

`gateway/main.py`, `udp_bus.py`, `device_registry.py`, `gateway_api.py`, `auto_discovery.py`, `rest_shim.py`, `payloads/` — zie [README_gateway.md](README_gateway.md).
