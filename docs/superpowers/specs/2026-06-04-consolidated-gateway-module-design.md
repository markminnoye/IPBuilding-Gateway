# Consolidated gateway as HA module — design spec

**Datum:** 2026-06-04
**Type:** Onderzoek / design-scope (low prio — backlog)
**Status:** Draft (niet goedgekeurd)
**Vervangt niets:** dit document beschrijft een optionele consolidatie van `gateway/` (HA add-on) en `ipbuilding-gateway-ha` (HA custom component) tot één HA-module. Huidige 2-delige architectuur blijft leidend — zie [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §3 Deployment A en [`AGENTS.md`](../../../AGENTS.md).

---

## 1. Vraag

Kan de gateway-functionaliteit (UDP/1001 veldbus-hub + device registry + REST/WS northbound) draaien **als één module in Home Assistant**, dus zonder de huidige HA add-on (`ipbuilding_gateway` Docker-container met `host_network: true`)?

**Kort antwoord:** technisch ja, maar in de huidige topologie niet zinvol. Zie §6 voor de afweging per deployment.

---

## 2. Huidige structuur (referentie)

Twee gescheiden artefacten die WebSocket-naar-elkaar-praten over `127.0.0.1:8080`:

| Component | Locatie | Verantwoordelijkheid |
|---|---|---|
| **Gateway add-on** | `gateway/` + `ipbuilding_gateway/` (Docker) | UDP-bus, device registry, `devices.json`, REST `:30200` shim, WS/REST `:8080`, ARP/HTTP discovery |
| **HA companion** | `ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha/` | WebSocket-client, HA-entities (light/switch/button/sensor), config flow met Supervisor auto-detect |

Communicatie vandaag:

```
[veldmodules 10.10.1.x] --UDP/1001--> [gateway add-on (host_network:true, eigen process)]
                                          |
                                          |--- aiohttp WS :8080 ---> [companion]
                                          |--- aiohttp REST :30200 (shim, opt-in)
                                          v
                                     [devices.json, ARP-table polls]
```

Geen van beide componenten bevat HA-specifieke logica; de gateway is zuivere asyncio Python en de companion is zuivere HA-integratie.

---

## 3. Wat verhuist er bij consolidatie

### 3.1 Gateway → `gateway_lib/` (geïsoleerde package)

Volgende modules zijn **proces-onafhankelijk** en kunnen in elke asyncio-loop draaien:

| Module | Huidige locatie | Opmerking |
|---|---|---|
| `UDPBus` | `gateway/udp_bus.py` | `loop.create_datagram_endpoint(local_addr=(self.config.bind_ip, 0))` — geen Docker/Supervisor dependency |
| `DeviceRegistry` | `gateway/device_registry.py` | In-memory state + sync callbacks; geen IO |
| `Payloads` (relay/dimmer/input) | `gateway/payloads/` | Pure encode/decode, geen state |
| `InstallationConfig` | `gateway/installation.py` | `devices.json` I/O; pad-parameteriseerbaar |
| `ModuleMetadataCache` | `gateway/module_metadata.py` | aiohttp HTTP naar modules — vereist `bind_ip` op `10.10.1.x` |

### 3.2 Wat **niet** zonder aanpassing verhuist

| Module | Probleem bij in-proces draaien |
|---|---|
| `DiscoveryOrchestrator` + `ArpMonitor` (`gateway/auto_discovery.py`) | Leest `/proc/net/arp` (Linux) of doet `arp -an` (macOS) en `asyncio.create_subprocess_exec("ping", ...)`. ICMP-ping vereist `CAP_NET_RAW`; in een HA custom_component-proces is dat **niet** beschikbaar. `/proc/net/arp` is wel leesbaar als de container `/proc` mount, maar ARP-tabel is dan leeg zonder `host_network: true` op de **HA-host** (niet de add-on). |
| `GatewayAPI` (`gateway/gateway_api.py`) | `aiohttp.web` server op `0.0.0.0:8080` — voor in-proces overbodig; vervangen door directe `async_dispatcher_send` vanuit registry-callbacks. |
| `RESTShim` (`gateway/rest_shim.py`) | Opt-in `:30200` — bewust uit; geen IPBox-compat nodig als IPBox uit de chain is. |
| `run.sh` (`ipbuilding_gateway/run.sh`) | Leest Supervisor `/data/options.json`; bij consolidatie wordt dat `ConfigEntry.data` uit de config flow. |

### 3.3 Companion: alleen listener-laag

De companion wordt gereduceerd tot:

1. `__init__.py` — entry setup; start een `IPBuildingHub`-instantie in `hass.data[DOMAIN]`.
2. `coordinator.py` — registries en listeners (huidige `IPBuildingCoordinator` met directe in-proces callbacks i.p.v. WS).
3. `light.py` / `switch.py` / `button.py` / `sensor.py` — ongewijzigd.
4. `config_flow.py` — vervangt Supervisor-detectie door handmatige host invoer (of niets als alles in-proces is).
5. `manifest.json` — voegt mogelijk een `requirements` hook toe voor `aiohttp`, `pydantic`.

---

## 4. Benodigde netwerk- en permissieconfig aan HA-zijde

Onafhankelijk van in-proces of add-on, de **host** moet voldoen aan:

| Vereiste | Huidige add-on | Geconsolideerde HA-module |
|---|---|---|
| Source-IP op `10.10.1.x` voor UDP-replies | Ja (container met `host_network: true`) | Ja — vereist dat **HA-host** (niet de integratie) een adres op `10.10.1.x` heeft. Meestal via VLAN trunk op de fysieke NIC. |
| ARP-tabel zichtbaar vanuit het proces | `/proc/net/arp` in container (`host_network: true`) | `/proc/net/arp` in HA-proces, of via syscall in Python — maar ARP is **leeg** zonder `host_network: true` op de host. |
| `CAP_NET_RAW` voor ICMP-ping | Container privilege | **Niet beschikbaar** in HA standaard; ARP-monitor moet uit of via host-shell-wrapper. |
| Eigen poort :8080 / :30200 | Toegewezen door Supervisor | In HA-proces: geen socket nodig, WS laag valt weg. REST shim is sowieso uit. |

**Conclusie:** discovery-functionaliteit verliest gegarandeerd mogelijkheden. De passieve ARP-monitor (zie [`2026-06-04-runtime-auto-discovery-design.md`](2026-06-04-runtime-auto-discovery-design.md) §6) werkt in-proces **niet** zonder aanvullende host-config.

---

## 5. Trade-offs

| Voordeel | Nadeel |
|---|---|
| Eén artefact installeren i.p.v. add-on + HACS | Companion verliest `host_network: true` privileges → UDP-bus kan alleen werken als HA-host een `10.10.1.x`-adres heeft. In de praktijk op HA Green meestal via VLAN trunk — afhankelijk van netwerk-setup. |
| Geen Supervisor-vereiste → werkt ook in HA Container zonder Supervisor | ARP-discovery breekt (geen `CAP_NET_RAW`, geen `host_network: true`). Fallback: alleen init-sweep via HTTP `getSysSet` (zonder ARP-prefix), trager en minder betrouwbaar. |
| Geen WS-laag → minder latentie voor state_changed events | `host_network: true` moet op **HA-host** niveau gezet worden (niet op de integratie) — buiten de controle van de integratie. |
| Eén proces te debuggen | Single point of failure: HA restart = veldbus-hub uit (behalve voor IP1100PoE EEPROM-autonomie). |
| Geen versie-coördinatie add-on ↔ companion | Add-on updates (atomic rollback) gaan verloren; HA-rolback herlaadt integratie. |

---

## 6. Per deployment-variant

Overgenomen uit [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §3.

### Deployment A — HA Green / Linux (primair)
**Aanbeveling: niet consolideren.**
- Huidige add-on heeft `host_network: true` en dedicated process-isolation.
- Companion Supervisor auto-detectie (`config_flow.py` regel 32-42) werkt alleen bij Supervisor.
- Consolidatie verliest ARP-monitor zonder `CAP_NET_RAW`.

### Deployment B — Standalone (RPi / NAS / VPS)
**Aanbeveling: n.v.t.** — hier draait **geen** HA, dus geen sprake van consolidatie. Gateway draait als `python -m gateway` (zie `ARCHITECTURE.md` §3 Deployment B).

### Deployment C — ESP32 POC (toekomstig)
**Aanbeveling: n.v.t.** — C++ firmware; geen Python in HA-proces.

### Container zonder Supervisor (HA Core in Docker, HA Container, etc.)
**Aanbeveling: niet consolideren.**
- Geen Supervisor ⇒ geen `ipbuilding_gateway` add-on mogelijk.
- HA Container kan `host_network: true` krijgen, maar verliest de privilege-isolatie en update-flow.
- Gebruik liever **Deployment B** (gateway als losse Docker naast HA) + huidige companion.

---

## 7. Backlog-acties (alleen als dit ooit opgepakt wordt)

Genummerd in volgorde van uitvoering; elk item is een aparte PR.

1. **Extract `gateway_lib/`** — verplaats `udp_bus.py`, `device_registry.py`, `payloads/`, `installation.py`, `module_metadata.py` naar `gateway_lib/` met één `__init__.py`. Geen `aiohttp.web` of `subprocess` in deze package.
2. **Companion in-proces variant** — optionele flag in `manifest.json` (`"gateway_in_process": true`) die de companion vertelt om `gateway_lib` te importeren i.p.v. WS-connectie.
3. **Config flow zonder Supervisor-detectie** — `ConfigEntry.data` met `hub_ip`, `bind_ip`, `poll_interval_s`, `devices_file`. Geen env-vars, geen `run.sh`.
4. **Discovery-rewrite** — vervang `ArpMonitor` door een variant die alleen HTTP `getSysSet` doet (geen ARP); of maak ARP een optionele feature met expliciete permissie-vraag via een Supervisor-only hook.
5. **Documentation pass** — update [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §3 om een "Deployment A.5 (HA Container zonder Supervisor)" op te nemen met de trade-offs.
6. **Fallback tests** — min-een test met alleen `bind_ip` op `10.10.1.x` en geen ARP-monitor, om te bevestigen dat UDP-poll werkt.

---

## 8. Niet in scope

- Herschrijven van payloads (`gateway/payloads/`) — reeds wire-confirmed, geen wijziging nodig.
- MQTT- of Matter-adapter verplaatsen — die horen bij de gateway, niet bij HA.
- Button→actie-regels of sferen — die horen sowieso in HA (`AGENTS.md` "Productprincipe"), niet in de gateway.
- `RESTShim` op `:30200` behouden — uitfaserend; in een geconsolideerde versie sowieso niet nodig.

---

## 9. Referenties

- [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) — canonieke architectuur; Deployment A/B/C
- [`AGENTS.md`](../../../AGENTS.md) — "Productprincipe": gateway = dunne veldbus-hub, logica in HA
- [`resources_and_docs/IPBUILDING_KNOWLEDGE.md`](../../../resources_and_docs/IPBUILDING_KNOWLEDGE.md) — netwerk-topologie en module HTTP API
- [`docs/superpowers/specs/2026-06-04-runtime-auto-discovery-design.md`](2026-06-04-runtime-auto-discovery-design.md) — ARP/HTTP discovery details (relevant voor §4)
- [`ipbuilding_gateway/DOCS.md`](../../../ipbuilding_gateway/DOCS.md) regel 91-104 — netwerk-vereisten voor de add-on
- [`gateway/udp_bus.py`](../../../gateway/udp_bus.py) regel 71-74 — `bind_ip` source-routing
- [`gateway/auto_discovery.py`](../../../gateway/auto_discovery.py) regel 184, 288 — `ArpMonitor` en `DiscoveryOrchestrator`
- [`ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha/config_flow.py`](../../../ipbuilding-gateway-ha/custom_components/ipbuilding_gateway_ha/config_flow.py) regel 32-42 — Supervisor auto-detectie
- [HA skill `home-assistant-best-practices`](../../../.agents/skills/home-assistant-best-practices/SKILL.md) regel 30 — "use native Home Assistant constructs"
