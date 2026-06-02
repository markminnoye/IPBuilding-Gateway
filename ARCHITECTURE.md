# IPBuilding Gateway — Architectuur

**Versie:** 2026-06-02  
**Status:** Goedgekeurd (vervangt [docs/superpowers/specs/2026-05-18-gateway-architecture-design.md](docs/superpowers/specs/2026-05-18-gateway-architecture-design.md))  
**Doelgroep:** ontwikkelaars, AI-agenten, integratie-partners

---

## 1. Doelstelling & scope

De propriëtaire **IPBox** (IP0000X) vervangen door een open, zelfbeheerde gateway die:

- Rechtstreeks communiceert met IPBuilding veldcontrollers via **UDP/1001**
- Een **protocol-agnostisch northbound-API** biedt (WebSocket, MQTT, Matter)
- Installeerbaar is als **HA add-on**, als **standalone Docker-container**, of als **ESP32-firmware** (toekomstige POC)
- **Home Assistant** integreert als primaire domotica via een companion custom component

**Buiten scope:**
- IPBox REST API `:30200` nabootsen als eindproduct (enkel als tijdelijke migratie-shim)
- Sferen / scenes in de gateway (hoort in HA)
- Knop→actie automatie-logica in de gateway (hoort in de companion / HA)

---

## 2. Componenten

### 2.1 `ipbuilding-gateway` — de gateway

**Verantwoordelijkheid:** veldbus-hub + device-model. Kent devices en hun toestand. Heeft **geen automatie-logica**.

| Wat het doet | Wat het NIET doet |
|---|---|
| UDP/1001 pollen, commando's sturen, events ontvangen | Knop→actie beslissen |
| Device Registry bijhouden (huidige toestand) | HA-entities aanmaken |
| Config lezen/schrijven (naam, room, type, watt, active) | Sferen of scenes beheren |
| Discovery: HTTP-sweep + `getButtons` op modules | IPBox REST nabootsen (enkel shim, tijdelijk) |
| Northbound: WS, REST, MQTT, Matter adapters | Button-mapping opslaan |
| Provisioning: EEPROM-sync doorgeven aan input-module | — |

**Talen/runtimes:**
- Python 3.11+ (HA add-on en standalone Docker/RPi) — primaire implementatie
- C++ ESP-IDF (ESP32 POC) — toekomstig, zelfde northbound-protocol

### 2.2 `ipbuilding-open` — de companion (HA custom component)

**Verantwoordelijkheid:** HA-specifieke laag. Vertaalt het gateway-protocol naar HA-entities en beheert de knop→actie-mapping.

| Wat het doet | Wat het NIET doet |
|---|---|
| WebSocket-client naar gateway `/ws` | UDP-communicatie |
| HA-entities aanmaken (light, switch, cover, button, sensor) | Provisioning rechtstreeks naar veldmodules |
| Button→actie mapping bewaren (HA config storage) | Device Registry beheren |
| "Sync naar EEPROM" triggeren via `POST /api/v1/provision/autonomy` | — |
| config_flow: auto-discovery via Supervisor of handmatig IP | — |

**Installatie:** HACS custom repository

### 2.3 Veldmodules

| Module | IP | Functie |
|---|---|---|
| IP0200PoE | 10.10.1.30 | 24× relay (aan/uit, pulse) |
| IP0300PoE | 10.10.1.40 | 8× dimmer (0–100%) |
| IP1100PoE | 10.10.1.50 | Drukknoppen — events + autonome EEPROM-mapping |

Communicatieprotocol: **UDP/1001** (binary ASCII, poort 1001). Configuratie-API: **HTTP `api.html`** rechtstreeks op elke module (backupConfig, saveOutput, saveChannel, saveAutonomy, getButtons).

---

## 3. Deployment-varianten

```mermaid
graph TB
    subgraph VLAN["🔌 IPBuilding veldbus · UDP/1001 · 10.10.1.x"]
        direction LR
        R["IP0200PoE\n24× relay\n10.10.1.30"]
        D["IP0300PoE\n8× dimmer\n10.10.1.40"]
        IN["IP1100PoE\nknoppen\n10.10.1.50"]
    end

    subgraph DA["📦 Deployment A — HA Green / Linux (primair)"]
        direction LR
        GWA["Gateway\nPython · Docker\nHA add-on"]
        COMP["Companion\nipbuilding-open"]
        HA["Home Assistant\nentities · automations\nbutton→actie"]
        GWA -. "WebSocket intern" .-> COMP --> HA
    end

    subgraph DB["🐳 Deployment B — Standalone"]
        GWB["Gateway\nPython · Docker\nRPi · NAS · VPS · Linux"]
    end

    subgraph DC["🔬 Deployment C — ESP32 POC (toekomstig)"]
        GWC["Gateway\nC++ firmware\nESP32"]
    end

    subgraph NB["Northbound adapters · alle deployments"]
        direction LR
        WS["WebSocket\nJSON /ws"]
        MQ["MQTT"]
        MT["Matter"]
    end

    subgraph CLI["🏠 Clients"]
        direction LR
        AH["Apple Home"]
        GH["Google Home"]
        NR["Node-RED\nandere apps"]
        MHA["HA MQTT\nintegratie"]
    end

    R & D & IN -->|"UDP/1001"| GWA
    R & D & IN -->|"UDP/1001"| GWB
    R & D & IN -->|"UDP/1001"| GWC

    GWA & GWB & GWC --> WS & MQ & MT

    MT --> AH & GH & HA
    MQ --> NR & MHA
    WS --> NR
```

**Deployment A** is de primaire target: gateway als HA add-on (Docker, beheerd door HA Supervisor), companion als HACS custom component op hetzelfde device.

**Deployment B** gebruikt exact dezelfde Python-code als A, maar zonder Supervisor-wrapper. Draait als `docker run` of `python -m gateway` op elke Linux-machine.

**Deployment C** is een toekomstige standalone POC in C++ voor ESP32. Implementeert hetzelfde northbound-protocol als A en B — de companion en andere clients werken er transparant mee.

---

## 4. Interne architectuur van de gateway

```mermaid
graph LR
    subgraph FIELD["Veldmodules · 10.10.1.x"]
        MOD["IP0200 · IP0300 · IP1100"]
    end

    subgraph GW["ipbuilding-gateway"]
        direction TB

        subgraph CORE["Core"]
            UDP["UDP Bus Manager\nasyncio · poort 1001\npoll · command · event"]
            REG["Device Registry\nin-memory\nhuidige toestand"]
            CFG["Config · devices.json\nnaam · room · type · watt · active"]
        end

        subgraph SETUP["Setup & Sync"]
            DISC["Discovery\nHTTP sweep 10.10.1.30–59\n+ getButtons"]
            PROV["Provisioning\nEEPROM sync\nknop→relay mapping"]
        end

        subgraph NB["Northbound adapters"]
            WS_S["WebSocket /ws"]
            REST_S["REST /api/v1/"]
            MQ_S["MQTT"]
            MT_S["Matter bridge"]
        end

        UDP <-->|"events / status"| REG
        CFG --> REG
        DISC -->|"eerste start + on-demand"| CFG
        REG --> WS_S & REST_S & MQ_S & MT_S
    end

    MOD <-->|"UDP/1001\ncommands + events"| UDP
    MOD -->|"HTTP backupConfig\ngetButtons"| DISC
    PROV -->|"HTTP saveAutonomy\n→ 10.10.1.50"| MOD
```

### Module-beschrijvingen

| Module | Bestand | Verantwoordelijkheid |
|---|---|---|
| `udp_bus.py` | `gateway/udp_bus.py` | asyncio UDP socket; polling (2s), command send, event listen |
| `device_registry.py` | `gateway/device_registry.py` | In-memory state van alle devices; update bij elk event |
| `installation.py` | `gateway/installation.py` | Laadt en valideert `devices.json`; levert entity-IDs |
| `discovery.py` | `gateway/discovery.py` | HTTP-sweep modules; `getButtons` op IP1100PoE |
| `gateway_api.py` | `gateway/gateway_api.py` | aiohttp server: WS `/ws` + REST `/api/v1/` *(Fase 3)* |
| `rest_shim.py` | `gateway/rest_shim.py` | IPBox-compatibele REST `:30200` *(tijdelijk, transitie)* |
| `payloads/` | `gateway/payloads/` | encode/decode relay, dimmer, input — **aanwezig en getest** |

---

## 5. Config-datamodel (`devices.json`)

De gateway bewaart een persistente config met alle metadata die de veldbus zelf niet kent. Aangemaakt via Discovery bij eerste start; daarna bewaard en on-demand bijgewerkt.

```jsonc
{
  "modules": [
    {
      "ip": "10.10.1.30",
      "type": "relay",              // relay | dimmer | input
      "firmware": "5.1",            // gelezen via getSysSet bij Discovery; bewaard voor diagnostiek
      "channels": [
        {
          "ch": 0,
          "name": "2e SlpK L",      // uit IPBox Configuration/Output of handmatig
          "room": "2e verd",        // uit IPBox groep of module backupConfig
          "semantic_type": "light", // light | fan | cover | switch | plug
          "active": true,           // false = niet pollen, niet exposen
          "max_watt": 60            // theoretisch maximum (configureerbaar)
        }
      ]
    },
    {
      "ip": "10.10.1.40",
      "type": "dimmer",
      "firmware": "5.4",
      "channels": [
        {
          "ch": 0,
          "name": "Woonkamer",
          "room": "Woonkamer",
          "semantic_type": "light",
          "active": true,
          "max_watt": 200
        }
      ]
    },
    {
      "ip": "10.10.1.50",
      "type": "input",
      "firmware": "5.2.4",
      "channels": []                // gevuld door Discovery via getButtons
    }
  ],
  "buttons": [
    {
      "id": "2DE341851900001F",      // hardware-ID van IP1100PoE
      "name": "Badkamer knop",
      "room": "1e verdieping",
      "active": true
    }
  ]
}
```

**Vermogen:**
- `max_watt` = geconfigureerde waarde (theoretisch maximum)
- `current_watt` = berekend door gateway (`max_watt × dim_level / 100`), meegegeven in elk `state_changed` event — geen apart power-event nodig

**Firmware:** het veld `firmware` per module wordt gelezen via `GET api.html?method=getSysSet` tijdens Discovery en bewaard in `devices.json`. Het wordt meegegeven in elk `device_list` event zodat clients (companion, diagnostiek-tools) de firmwareversie kennen. Wordt automatisch bijgewerkt bij elke herontdekking. Bekende versies uit RE: relay `5.1`, dimmer `5.4`, input `5.2.4` — gedrag van andere versies is onbekend; log altijd de versie bij opstart.

**Initiële import:** tijdens migratie kan `name`, `room`, `semantic_type`, `active` en `max_watt` automatisch ingeladen worden vanuit `GET /general/Configuration/Output` op de IPBox (zolang die nog online is).

---

## 6. Northbound protocol — WebSocket

Alle northbound-adapters (WS, MQTT, Matter) publiceren hetzelfde logische device-model. WebSocket is de primaire adapter voor de companion.

```mermaid
sequenceDiagram
    participant GW as Gateway
    participant CL as Client (companion / app)

    CL->>GW: WebSocket connect /ws
    GW-->>CL: device_list · alle devices + huidige toestand

    Note over GW,CL: Realtime push — gateway → client
    GW-->>CL: state_changed · relay aan · current_watt 60W
    GW-->>CL: state_changed · dimmer 75% · current_watt 150W
    GW-->>CL: button_event · knop 2DE34… ingedrukt

    Note over GW,CL: Commando's — client → gateway
    CL->>GW: command · relay ON
    CL->>GW: command · dimmer DIM 50%
    GW-->>CL: state_changed · bevestiging
```

### Berichtformaten

```jsonc
// Gateway → client: toestandswijziging
{"type": "state_changed", "id": "10.10.1.30:relay:0",
 "state": "on", "max_watt": 60, "current_watt": 60}

{"type": "state_changed", "id": "10.10.1.40:dimmer:0",
 "state": "on", "level": 75, "max_watt": 200, "current_watt": 150}

// Gateway → client: knopgebeurtenis
{"type": "button_event", "id": "2DE341851900001F", "action": "press"}

// Gateway → client: volledige lijst bij verbinding (incl. firmware per module)
{"type": "device_list", "devices": [
  {"id": "10.10.1.30:relay:0",  "name": "2e SlpK L",  "room": "2e verd",
   "semantic_type": "light", "active": true, "max_watt": 60,
   "state": "off", "firmware": "5.1"},
  {"id": "10.10.1.40:dimmer:0", "name": "Woonkamer",   "room": "Woonkamer",
   "semantic_type": "light", "active": true, "max_watt": 200,
   "state": "on", "level": 75, "firmware": "5.4"}
]}

// Client → gateway: commando's
{"type": "command", "id": "10.10.1.30:relay:0", "action": "ON"}
{"type": "command", "id": "10.10.1.40:dimmer:0", "action": "DIM", "value": 75}
{"type": "command", "id": "10.10.1.30:relay:0", "action": "OFF"}
```

**Entity-ID formaat:** `"{module_ip}:{device_type}:{channel}"` — deterministisch afgeleid, nooit opgeslagen.  
Voorbeeld: `"10.10.1.30:relay:0"`, `"10.10.1.40:dimmer:0"`

---

## 7. Migratiepad & EEPROM-sync

```mermaid
flowchart TD
    A["IPBox nog online"] -->|Stap 1| B["Import uit IPBox\nConfiguration/Output\n→ naam · room · type · watt · active"]
    B --> C["Gateway config\ndevices.json gevuld"]
    C -->|Stap 2| D["Gateway add-on actief\nREST shim :30200 aan\nBestaande HA-IPBuilding\nblijft werken"]
    D -->|Stap 3| E["Companion ipbuilding-open\ninstalleren naast bestaande\n→ nieuwe entities via WS"]
    E -->|Stap 4| F["Button→actie mapping\ninstellen in companion\n→ HA automations"]
    F -->|Stap 5| G["EEPROM sync\nCompanion POST /api/v1/provision/autonomy\n→ Gateway → saveAutonomy op IP1100PoE\n→ online = offline gedrag"]
    G -->|Stap 6| H["🎉 IPBox afkoppelen\nREST shim uitzetten\nGateway volledig autonoom"]

    style A fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
    style H fill:#14532d,stroke:#22c55e,color:#e2e8f0
```

### EEPROM-sync detail

De button→relay mapping voor autonoom werken (gateway offline) leeft in de **IP1100PoE** zelf. De companion bewaart de mapping in HA config storage en kan die op elk moment syncen naar de module:

```
Companion (HA) → POST /api/v1/provision/autonomy
  → Gateway → HTTP api.html?method=saveAutonomy @ 10.10.1.50
    → IP1100PoE slaat mapping op in firmware
```

**Resultaat:** als de gateway uitvalt, voert de IP1100PoE exact dezelfde acties uit als wanneer hij online is — online en offline gedrag zijn synchroon.

---

## 8. Roadmap

| Fase | Beschrijving | Status |
|---|---|---|
| **1** | UDP-protocol RE: relay, dimmer, input `B-…E` + `gateway/payloads/` | ✅ Voltooid |
| **2** | UDP Bus Manager, Device Registry, REST-shim, veldtest | ✅ Voltooid (2026-06-02) |
| **3** | WebSocket API server `gateway_api.py` + REST `/api/v1/` | 🔲 Open |
| **4** | Gateway als HA add-on (Dockerfile + `config.yaml`) | 🔲 Open |
| **5** | Companion `ipbuilding-open` — entities, automations | 🔲 Open |
| **6** | Input-events IP1100PoE naar companion via WS | 🔲 Open |
| **7** | Discovery wizard + config-import vanuit IPBox | 🔲 Open |
| **8** | EEPROM-sync (`/api/v1/provision/autonomy`) | 🔲 Open |
| **9** | MQTT adapter | 🔲 Open |
| **10** | Matter bridge | 🔲 Open |
| **11** | Cover/screen entities (relay-paren) | 🔲 Open |
| **12** | ESP32 POC (C++ firmware) | 🔲 Toekomstig |

---

## 9. Referenties

| Document | Inhoud |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Agent-brief: status, volgende acties, sprint-context |
| [`resources_and_docs/RE_STATE.md`](resources_and_docs/RE_STATE.md) | Canonieke RE-status veldbus (Fase 1 afgesloten) |
| [`resources_and_docs/IPBUILDING_KNOWLEDGE.md`](resources_and_docs/IPBUILDING_KNOWLEDGE.md) | Diepe technische kennis: module HTTP API, UDP payloads, WebConfig |
| [`resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md`](resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md) | IPBox provisioning-RE: saveOutput, saveAutonomy, FlashAutonomyToModule |
| [`resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md`](resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md) | Veldbus capabilities (northbound-agnostisch) |
| [`gateway/`](gateway/) | Huidige implementatie (Fase 1 + 2) |
| [`docs/architecture-diagrams.html`](docs/architecture-diagrams.html) | Gerenderde diagrammen (lokale browser) |
