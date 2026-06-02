# IPBuilding Gateway — Architectuurontwerp

> ⚠️ **Superseded door [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) (2026-06-02).**  
> Dit document blijft bewaard als historische referentie. Gebruik `ARCHITECTURE.md` als canonical bron.

**Datum:** 2026-05-18 (roadmap bijgewerkt 2026-05-22)  
**Status:** Superseded — zie ARCHITECTURE.md  
**Beslissing:** Aanpak C — HA Add-on + Companion Component

---

## Context

De IPBox (IP0000X) is verouderde, propriëtaire hardware die als hub fungeert tussen de IPBuilding veldcontrollers en domotica-systemen. Hij is de zwakke schakel in de installatie: kwetsbaar, duur om te vervangen, en een afhankelijkheid die autonomie blokkeert.

**Doel:** de IPBox vervangen door een open-source gateway die:
- Rechtstreeks communiceert met veldcontrollers via UDP/1001
- Home Assistant integreert als primaire domotica (gouden standaard)
- Architectureel voorbereid is op Apple Home en Google Home (via HA Matter bridge)
- Installeerbaar is als één coherent pakket op een HA OS-installatie

**Scope van dit document:** northbound-architectuur (hoe clients de gateway aanspreken). De UDP/1001 veldbus-wire (relay, dimmer, input `B-…E`) is **afgerond** (RE Sprint 1–5); codecs in `gateway/payloads/`. Zie `resources_and_docs/RE_STATE.md`, `IPBUILDING_KNOWLEDGE.md` §10.5.

**Productprincipe (2026-05-22):** de gateway is een **dunne veldbus-hub** (pollen, commando’s, events doorsturen). **Geen** IPBox-pariteit voor sferen/scenes of knop→actie-regels — dat hoort in Home Assistant (`ipbuilding-open`).

---

## Beslissing: Aanpak C — HA Add-on + Companion Component

Gekozen op basis van:
1. HA OS is de target (Supervisor + add-on store beschikbaar)
2. Volledige vervanging van het bestaande `HA-IPBuilding` component — geen legacy-API-laag nodig als eindproduct
3. Realtime push (WebSocket) lost de 20s polling-lag op
4. Process-isolatie: gateway-crash raakt HA niet
5. Toekomstpad naar Apple Home / Google Home via ingebouwde HA Matter bridge

---

## Doelarchitectuur

```
╔══════════════════════════════════════════════════════════════╗
║  IPBuilding VLAN  (10.10.1.x / 10.10.0.x)                   ║
║                                                              ║
║   10.10.1.30  IP0200PoE  (24 relay-kanalen)                  ║
║   10.10.1.40  IP0300PoE  (dimmer-kanalen)                    ║
║   10.10.1.40  IP0300PoE  (tweede dimmer-module)              ║
║   10.10.1.50  IP1100PoE  (ingangsmodule / drukknoppen)       ║
╚═══════════════════════════╤══════════════════════════════════╝
                            │  UDP/1001  (binary protocol)
╔═══════════════════════════▼══════════════════════════════════╗
║  ipbuilding-gateway  (HA Add-on — Docker container)          ║
║                                                              ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │  UDP Bus Manager (asyncio)                           │     ║
║  │  • Polling loop (2s) → relay/dimmer/input modules   │     ║
║  │  • Command sender (relay ON/OFF, dimmer DIM)        │     ║
║  │  • Event listener (IP1100PoE button presses)        │     ║
║  │  • payloads/ library (encode/decode)                │     ║
║  └──────────────────────┬──────────────────────────────┘     ║
║                         │                                    ║
║  ┌──────────────────────▼──────────────────────────────┐     ║
║  │  Gateway API Server (aiohttp)                        │     ║
║  │  • WebSocket endpoint  /ws  (JSON events + commands)│     ║
║  │  • REST API  /api/v1/  (device list, actions)       │     ║
║  │  • REST shim  :30200  (IPBox-compatibel, tijdelijk) │     ║
║  └──────────────────────────────────────────────────────┘    ║
╚══════════════════════════╤═══════════════════════════════════╝
                           │  WebSocket + REST  (LAN)
╔══════════════════════════▼═══════════════════════════════════╗
║  Home Assistant (HA OS — Supervisor)                         ║
║                                                              ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │  ipbuilding-open  (companion custom component)       │     ║
║  │  • config_flow.py  → auto-discovery via Supervisor  │     ║
║  │  • WebSocket client  → realtime state + events      │     ║
║  │  • Entity layer:  light, switch, scene, button,     │     ║
║  │                   sensor, cover                     │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  [HA Matter bridge]  →  Apple Home  /  Google Home           ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Componenten

### 1. `ipbuilding-gateway` — HA Add-on

**Taal:** Python 3.11+, asyncio  
**Container:** Docker (HA OS add-on)  
**Repository:** `IPBuilding Gateway` (dit project)

#### Modules

| Module | Functie |
|--------|---------|
| `udp_bus.py` | asyncio UDP socket manager; polling + command send + event listen |
| `payloads/` | encode/decode bibliotheek (relay, dimmer, input) — **aanwezig** (RE + tests) |
| `device_registry.py` | In-memory model van alle gekende devices met huidige status |
| `gateway_api.py` | aiohttp server: WebSocket `/ws` + REST `/api/v1/` |
| `rest_shim.py` | IPBox-compatibele REST op `:30200` (transitie-hulp, optioneel) |
| `config.py` | Configuratie: controller IP-adressen, poorten, polling interval |

#### WebSocket protocol (JSON)

```jsonc
// Gateway → client: toestandwijziging
{"type": "state_changed", "id": 5,  "device_type": 1, "value": 1}
{"type": "state_changed", "id": 12, "device_type": 2, "value": 75}

// Gateway → client: drukknop event (IP1100PoE)
{"type": "button_event", "id": 50, "action": "press"}

// Gateway → client: volledige device-lijst (bij verbinding)
{"type": "device_list", "devices": [...]}

// Client → gateway: commando
{"type": "command", "id": 5,  "action": "ON"}
{"type": "command", "id": 12, "action": "DIM", "value": 50}
{"type": "command", "id": 20, "action": "OFF"}
{"type": "command", "id": 100, "action": "ACTIVATE"}  // scene
```

#### HA Add-on configuratie (`config.yaml`)

```yaml
name: IPBuilding Gateway
slug: ipbuilding_gateway
version: "0.1.0"
host_network: true          # Vereist voor UDP/1001 op IPBuilding VLAN
```

### 2. `ipbuilding-open` — Companion Custom Component

**Taal:** Python 3.11+ (HA custom component)  
**Installatie:** HACS (custom repository)

#### Bestanden

| Bestand | Functie |
|---------|---------|
| `config_flow.py` | Auto-discovery via Supervisor API slug; fallback: handmatig host invullen |
| `coordinator.py` | WebSocket client; verdeelt push-events naar entities |
| `light.py` | HA `LightEntity` voor relays (aan/uit) en dimmers (helderheid 0-100%) |
| `switch.py` | HA `SwitchEntity` voor relay-types die niet als licht zijn ingesteld |
| `scene.py` | HA `SceneEntity` voor TYPE_SPHERE / sferen |
| `button.py` | HA `ButtonEntity` voor fysieke drukknoppen (IP1100PoE events) |
| `sensor.py` | HA `SensorEntity` voor energietellers, temperatuursensoren |
| `cover.py` | HA `CoverEntity` voor rolluiken / screens (relay-paren) |
| `const.py` | Constanten (device types, kinds) |

---

## Netwerkconstraint

De gateway moet UDP/1001-pakketten kunnen sturen naar en ontvangen van `10.10.1.x` en `10.10.0.x`. Dit vereist dat de add-on-container een interface heeft op het IPBuilding VLAN.

**Gekozen oplossing: HA Green — single-NIC via VLAN trunk**

Hardware: **Home Assistant Green** (HA OS, één Ethernet-poort, geen aparte hardware).

```
[HA Green — eth0]
        │
        │  trunk: native = Default LAN (192.168.1.x)
        │           tagged = VLAN 2 / IPBuilding (10.10.1.x)
        │
[UniFi Switch — poort X  (profile: customize / trunk)]
```

HA OS maakt een VLAN-sub-interface aan: `eth0.2` met een statisch IP op `10.10.1.x` (bv. `10.10.1.2`).

**Configuratiestappen (eenmalig):**
1. **UniFi:** schakelpoort van HA Green instellen op `forward: customize`, native VLAN = Default, tagged VLAN = IPBuilding (tag 2)
2. **HA OS:** Instellingen → Systeem → Netwerk → VLAN-interface toevoegen op `eth0`, VLAN-ID `2`, statisch IP `10.10.1.2/24`
3. **Add-on:** `host_network: true` in `config.yaml` — de add-on ziet beide interfaces van de host

**Gevolg:** de add-on kan UDP/1001 sturen naar `10.10.1.30`, `.40`, `.50` via `eth0.2`, en de WebSocket-API is bereikbaar via het thuis-LAN op `eth0`.

**Geen aparte hardware nodig.** Dedicated RPi/NUC blijft een latere optie als de HA Green-belasting te hoog wordt, maar is niet vereist voor het opstarten.

---

## Installatie-ervaring (eindgebruiker)

1. **Add-on installeren:** Add-on repository URL toevoegen in HA → `IPBuilding Gateway` installeren → netwerk configureren
2. **Companion installeren:** HACS → custom repository → `ipbuilding-open` installeren
3. **Integratie toevoegen:** HA Instellingen → Integraties → `+` → `IPBuilding Open` → config flow detecteert add-on automatisch
4. **Klaar:** entities verschijnen automatisch in HA

---

## Transitiestrategie (van `HA-IPBuilding` naar `ipbuilding-open`)

```
Stap 1: Gateway add-on installeren + IPBox-REST-shim aanzetten (:30200)
        → bestaande HA-IPBuilding component herwijzen naar gateway-IP
        → valideer dat alle entities correct werken

Stap 2: ipbuilding-open companion installeren
        → parallel naast bestaande component uitproberen
        → vergelijk entities en gedrag

Stap 3: HA-IPBuilding component uitschakelen / verwijderen
        → IPBox-REST-shim optioneel uitzetten

Stap 4: IPBox fysiek verwijderen uit het netwerk 🎉
```

---

## Roadmap

| Fase | Beschrijving | Status (2026-06-01) |
|------|-------------|---------------------|
| **1** | UDP-protocol decoderen (relay, dimmer, input `B-…E`) + `gateway/payloads/` | **Voltooid** — Sprint 1–5, zie [RE_STATE.md](../../../resources_and_docs/RE_STATE.md) |
| **2** | UDP Bus Manager (poll-loop op `10.10.1.1`) + `device_registry` + basis REST-shim (`rest_shim.py`) | **In uitvoering** — poll-loop, registry, shim + `main.py` in repo; open: `devices.json` laden, veldtest, commit |
| **3** | WebSocket API server (`gateway_api.py`, `/ws` + REST `/api/v1/`) | Open |
| **4** | Gateway als HA Add-on (Dockerfile + `config.yaml`, `host_network`) | Open |
| **5** | Companion (`ipbuilding-open`) — entiteiten, automations voor knop→actie | Open |
| **6** | Input-events IP1100PoE naar companion via WebSocket | Open (wire bevestigd in fase 1) |
| **7** | Cover / screen entities (relay-paren met interlock) | Open |
| **8** | Apple Home / Google Home via HA Matter bridge | Open |

**Huidige code in dit repo:** `gateway/payloads/`, `gateway/udp_bus.py` (poll-loop), `gateway/device_registry.py`, `gateway/rest_shim.py` (transitie-REST `:30200`; `rest_api.py` = backward-compat alias). Nog open: `gateway_api.py`, add-on, companion. Zie [README_gateway.md](../../../README_gateway.md).

**Volgende implementatiefocus:** Fase 2 (zie [AGENTS.md](../../../AGENTS.md), [README_gateway.md](../../../README_gateway.md)).

---

## Tech stack

```
Python 3.11+
asyncio                  # UDP socket loop + WebSocket server
aiohttp                  # HTTP + WebSocket server
pydantic                 # config models + device registry
# HA add-on: Dockerfile + config.yaml
# Companion: standaard HA custom component structuur
```

---

## Openstaande vragen (voor implementatie)

| # | Vraag | Prioriteit |
|---|-------|-----------|
| 1 | Is het HA-huis al op het IPBuilding VLAN gerouteerd, of moet VLAN-interface aangemaakt worden? | 🔴 Hoog |
| 2 | Hoe worden screens/rolluiken gerepresenteerd in het huidige systeem (relay-paren)? | 🟡 Middel |
| 3 | Welke entities uit `HA-IPBuilding` worden actief gebruikt in jouw installatie? | 🟡 Middel |
| 4 | UDP: stuurt IP0300PoE commands op dezelfde poort 1001 als polling, of anders? | ✅ Bevestigd — zelfde poort 1001 (Sprint 3/4 RE) |
