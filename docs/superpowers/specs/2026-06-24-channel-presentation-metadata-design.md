# Channel presentation metadata — design spec

**Datum:** 2026-06-24  
**Type:** Design spec (extends `ARCHITECTURE.md` §5 write-policy)  
**Status:** Approved (design dialogue 2026-06-24)  
**Scope:** Gateway northbound model + companion write-path. MQTT/Matter adapters consume the same layer when implemented (Fase 9–10).

**Repos:** `IPBuilding Gateway` (primary), `ha-ipbuilding-gateway` (configurator UI + PATCH client)

---

## 1. Probleem

Relay- en dimmerkanalen worden vandaag in de companion vrijwel altijd als **`light.*`** geëxposeerd, omdat:

1. Module-HTTP (`backupConfig`) levert alleen `descr` (naam) en `gr` (groep/ruimte) — **geen** light/fan/switch-type.
2. Discovery seedt elk kanaal met `semantic_type: "light"` (`gateway/discovery.py`).
3. Operators die ventilatie-relais als `fan`/`switch` willen (bv. ch 9 “Badkamer ventilatie”, ch 23 “Keuken Ventilatie”) moeten `devices.json` **handmatig** bewerken; er is geen REST write-pad.
4. `ARCHITECTURE.md` noemt `semantic_type` eigenaar “companion / gebruiker”, maar bewaart het in **`devices.json`** zonder update-API — dat voelt inconsistent: metadata die niet van de veldbus komt, zonder duidelijk write-model.

**Operator-use-case (concrete):** “Verdieping licht uit” via `light.turn_off` op area/floor mag ventilatie **niet** meenemen. Zolang ventilatie-relais `semantic_type: light` heeft, faalt area-targeting.

**Architectuurkeuze (bevestigd):** **Model A** — één gedeelde presentatiebron in de gateway voor alle northbound clients (HA companion, toekomstige MQTT/Matter). Clients zijn **readers**; niet iedere client mag schrijven.

---

## 2. Doel

1. **Scheiding** tussen wat de module objectief levert (inventory) en wat de installateur beslist (presentation).
2. **Eén stabiele bron** voor `semantic_type`, `active`, `max_watt` — gelezen door HA, MQTT en Matter zonder parallelle mapping per client.
3. **Single writer** voor presentation: companion options-flow (primair) via gateway REST; discovery mag alleen **seeden**, nooit operator-keuzes overschrijven.
4. **Update-pad** zodat operators ventilatie (en andere niet-licht lasten) kunnen herclassificeren zonder JSON te editen.

**Niet in scope (deze iteratie):** MQTT/Matter adapter-implementatie; IPBox-import van output-types; automatische `fan`-detectie op basis van kanaalnaam zonder operator-bevestiging.

---

## 3. Alternatieven (samenvatting)

| # | Aanpak | Oordeel |
|---|--------|---------|
| **1** | Alles in `devices.json`, PATCH toevoegen | Minste migratie; verwart inventory en presentation |
| **2** | Inventory + presentation (aanbevolen) | Zelfde logische bron A; duidelijke write-policy; module-refresh raakt typing niet |
| **3** | Alleen `capabilities` op gateway; typing per client | Past **niet** bij A — drievoudige mapping, inconsistent voor Matter |

**Gekozen: optie 2** — één northbound API-surface, twee conceptuele lagen. Fase 1 mag beide in hetzelfde `devices.json` blijven (geen apart bestand verplicht).

---

## 4. Datamodel

### 4.1 Stabiele identiteit

| Entiteit | `device_id` | Voorbeeld |
|----------|-------------|-----------|
| Relay/dimmer kanaal | `{module_ip}-{channel}` (bestaand) | `10.10.1.30-9` |
| IP1100PoE knop | hardware-id (14 hex, lowercase) | `2de341851900001f` |

MAC-based sleutels zijn wenselijk voor IP-wijzigingen; **MVP behoudt** het bestaande `{ip}-{ch}`-contract in REST/WS om geen breaking change te introduceren.

### 4.2 Inventory (objectief — module / veldbus)

| Veld | Bron | Gateway schrijft |
|------|------|------------------|
| `device_type` | `relay` / `dimmer` / `input` | Discovery, type-detectie |
| `module_id` (MAC) | `getSysSet` | Discovery |
| `module_ip` | `getSysSet` / runtime | Registry; `devices.json` `ip` alleen bij expliciete policy |
| `channel` | kanaalindex | Discovery |
| `module_label.name` | `backupConfig` → `descr` | Refresh/sync (zie §6) |
| `module_label.room` | `backupConfig` → `gr` | Refresh/sync (zie §6) |
| `capabilities` | afgeleid | Gateway (read-only in API) |

**Afgeleide capabilities (niet bewerkbaar):**

| `device_type` | `capabilities` |
|---------------|----------------|
| `relay` | `on_off` |
| `dimmer` | `on_off`, `brightness` |
| `input` (knop) | `button_events` |

### 4.3 Presentation (operator — gedeeld northbound)

| Veld | Default (seed) | Eigenaar |
|------|----------------|----------|
| `semantic_type` | `light` (relay/dimmer); `button` (input) | Operator via companion |
| `active` | `false` bij **nieuwe** module via init-sweep; `true` bij discovery-draft uit `backupConfig` (bestaand gedrag documenteren) | Operator |
| `max_watt` | `60` relay, `200` dimmer | Operator |
| `name` | fallback → `module_label.name` | Operator override optioneel (fase 2) |
| `room` | fallback → `module_label.room` | Operator override optioneel (fase 2) |

**Toegestane combinaties (`semantic_type` × `device_type`):**

| `device_type` | Toegestaan `semantic_type` |
|---------------|----------------------------|
| `relay` | `light`, `fan`, `switch`, `plug`, `cover` |
| `dimmer` | `light`, `switch` |
| `input` | `button` (vast) |

Ongeldige combinaties → REST `422` met duidelijke fout.

**Companion mapping (bestaand, ongewijzigd):**

| `semantic_type` | HA platform |
|-----------------|-------------|
| `light` | `light` |
| `fan`, `switch`, `plug` | `switch` |
| `button` | `event` |

### 4.4 Northbound API merge

`GET /api/v1/devices` blijft één platte lijst. Elk item bevat:

- Inventory-velden (`device_type`, `capabilities`, …)
- Presentation-velden (`semantic_type`, `active`, `max_watt`, …)
- Effectieve `name` / `room` (presentation override indien gezet, anders module label)

Optioneel nieuw veld in response: `capabilities: ["on_off"]` — clients die Matter/MQTT bouwen gebruiken `capabilities` + `semantic_type` samen.

---

## 5. Write-policy: single writer, many readers

```
  Module HTTP ──► Inventory (gateway)     ◄── discovery / refresh (labels)
                        │
                        │ merge (read-only voor northbound clients)
                        ▼
  Companion UI ──► Presentation (gateway)   ◄── PATCH /api/v1/channels/{id}
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       HA entities   MQTT (later)  Matter (later)
```

| Actor | Mag presentation schrijven? |
|-------|----------------------------|
| Gateway init/forced discovery | **Alleen seed** op **nieuwe** kanalen |
| `POST /api/v1/modules/refresh` | **Nee** voor `semantic_type` / `active` / `max_watt` |
| Companion options-flow “Kanaaltypen” | **Ja** (primair pad) |
| `PATCH /api/v1/channels/{id}` | **Ja** (technisch; bedoeld voor companion) |
| Handmatig `devices.json` | Break-glass / migratie |
| MQTT/Matter/Node-RED clients | **Nee** (read-only) |

**Stabiliteit:** operator zet ch 9 op `fan` → blijft `fan` na reboot, module refresh en companion reload, tenzij expliciet gewijzigd via PATCH.

### 5.1 Discovery merge-regels

| Situatie | Gedrag |
|----------|--------|
| Nieuw kanaal (nieuwe module of nieuw ch in sweep) | Seed `semantic_type: light`, `active: false` (init-sweep) of bestaande discovery-defaults |
| Bestaand kanaal, forced discovery | **Behoud** presentation-velden (`semantic_type`, `active`, `max_watt`) — reeds deels zo via `mc.to_dict()` |
| Module refresh | Update **alleen** runtime metadata + optioneel `module_label`; **niet** presentation |
| Naam op module gewijzigd in WebConfig | MVP: `name`/`room` in presentation **niet** auto-overschrijven als operator ze heeft gezet; fase 2: `label_sync` policy |

---

## 6. REST API (gateway)

### 6.1 `PATCH /api/v1/channels/{device_id}`

**Body (alle velden optioneel):**

```json
{
  "semantic_type": "fan",
  "active": true,
  "max_watt": 60
}
```

**Response 200:** bijgewerkt kanaal-object (merged view).

**Fouten:**

| Code | Wanneer |
|------|---------|
| `404` | Onbekend `device_id` |
| `422` | Ongeldige `semantic_type` voor `device_type` |
| `409` | Optioneel later: revision conflict |

**Side effects:**

1. Atomic write naar `devices.json` via bestaande `AtomicWriter`.
2. Herlaad `InstallationConfig` in memory.
3. WS broadcast: `channel_presentation_changed` met `{ "id", "semantic_type", "active", "max_watt" }`.

### 6.2 Auth (MVP)

| Deployment | Policy |
|------------|--------|
| HA add-on | PATCH alleen vanaf localhost / Supervisor-netwerk; geen token in MVP als add-on op `127.0.0.1:8080` |
| Standalone Docker/Pi | `GATEWAY_API_TOKEN` env; `Authorization: Bearer …` op PATCH |

GET blijft ongewijzigd (lokaal vertrouwd netwerk); PATCH is het enige gevoelige oppervlak.

---

## 7. Companion (`ha-ipbuilding-gateway`)

### 7.1 Configurator — geen tweede waarheid

- Nieuwe options-flow-stap: **“Kanaaltypen”** (naast “Ruimtes koppelen”).
- UI: lijst actieve kanalen met dropdown `light` / `fan` / `switch` / `plug` / `cover` (gefilterd op `device_type`).
- **Heuristiek (suggestie only):** naam bevat `ventilatie` (case-insensitive) → pre-select `fan`; operator moet opslaan.
- Opslaan → `PATCH` naar gateway; **niet** alleen `config_entry.options` als bron van waarheid.
- Na PATCH: companion reload / coordinator refresh zodat entities platform wisselen (`light` → `switch` vereist entity teardown — documenteer operator-impact).

### 7.2 Entity lifecycle bij type-wijziging

Wanneer `semantic_type` van `light` naar `fan` gaat:

1. Oude `light.*` entity uit registry verwijderen of disabled.
2. Nieuwe `switch.*` entity aanmaken.

Dit is een **bewuste operator-actie**; UI toont waarschuwing (“entity_id kan wijzigen; controleer automations”).

---

## 8. Toekomstige northbound adapters

Zelfde presentation-laag; adapter-specifieke mappingtabel:

| `device_type` | `semantic_type` | MQTT (HA discovery) | Matter (indicatief) |
|---------------|-----------------|---------------------|---------------------|
| relay | light | `light` | On/Off Light |
| dimmer | light | `light` | Dimmable Light |
| relay | fan | `switch` (+ icoon) | Fan of On/Off Plug-In Unit |
| relay | switch | `switch` | On/Off Plug-In Unit |

Adapters **lezen**; ze schrijven nooit naar presentation.

---

## 9. MVP-implementatie (volgorde)

| # | Repo | Taak |
|---|------|------|
| 1 | Gateway | `PATCH /api/v1/channels/{id}` + validatie + atomic write + WS event |
| 2 | Gateway | Documenteer merge-policy in discovery (expliciet test: bestaand `semantic_type` blijft bij forced discover) |
| 3 | Gateway | `docs/api/rest.md` + Postman bijwerken |
| 4 | Companion | Options-flow “Kanaaltypen” + PATCH client |
| 5 | Companion | Entity platform switch bij type change |
| 6 | Operator | ch 9 + ch 23 → `fan` (via UI of eenmalige PATCH) |

**Directe win voor operator:** `light.turn_off` op floor/area raakt ventilatie niet meer als die `switch` zijn.

---

## 10. Migratie

- Bestaande `devices.json` blijft geldig; geen schema-version bump verplicht.
- Kanalen met `semantic_type: light` blijven licht tot operator herclassificeert.
- Scratch-test runbook (`resources_and_docs/workflows/2026-06-03_discovery_scratch_test_runbook.md`) blijft referentie voor ch 9 / ch 23 → `fan`.

---

## 11. Testplan (acceptatie)

1. PATCH ch 9 → `fan`; `GET /api/v1/devices` toont `semantic_type: fan`; companion toont `switch.*`.
2. Forced discovery + module refresh: ch 9 blijft `fan`.
3. Nieuw kanaal via init-sweep: default `light`, `active: false`.
4. PATCH ongeldige combo (dimmer + `fan`) → `422`.
5. `light.turn_off` op area met gemixte kanalen: alleen `light.*` gaat uit; `switch.*` ventilatie blijft aan.

---

## 12. Relatie met bestaande docs

| Document | Relatie |
|----------|---------|
| `ARCHITECTURE.md` §5 write-policy | Presentation = noordbound-velden; dit spec maakt write-pad expliciet |
| `docs/api/rest.md` | Uitbreiden met PATCH |
| `resources_and_docs/workflows/2026-06-03_discovery_scratch_test_runbook.md` | Operator checklist ventilatie |
| Companion `room_mapping.py` | Zelfde configurator-patroon voor typing |

---

## 13. Open punten (bewust niet geblokkeerd)

- Apart `presentation.json` vs embedded in `devices.json` — **fase 2** als bestandsgrootte of merge-complexiteit groeit.
- `presentation_revision` / optimistic locking — alleen nodig bij meerdere gelijktijdige beheerders.
- `name`/`room` override los van module label — fase 2; MVP gebruikt bestaande velden in `devices.json`.
