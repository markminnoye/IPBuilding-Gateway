# RE Wizards — IPBox WebConfig

**Status:** actief (Modules-wizard deels uitgewerkt)  
**Laatste update:** 2026-05-17  
**Doel:** provisioning-flow van de IPBox nabootsen in de gateway (naast REST `:30200`)

---

## Doel

De **Wizards** in IPBox WebConfig zijn de provisioning-flow: modules ontdekken, uitgangen benoemen, project koppelen. Voor een IPBox-vervanging moeten we deze laag begrijpen **naast** de bekende REST API op poort **30200**.

| Parameter | Waarde |
|-----------|--------|
| WebConfig basis | `http://<ipbox-thuis>/general/` (lab: `http://192.168.0.185`) |
| REST basis | `http://<ipbox-thuis>:30200/api/v1` |
| WebConfig versie | v1.8.4.3 |
| Service versie | 1.8.0.3 |
| Centrale | `ip2017-814` |

---

## Architectuur: twee lagen

```
[Browser/HA]
    |  :80  /general/Wizards/...     → provisioning (dit document)
    |  :30200 /api/v1/...            → runtime (comp/items, action)
    v
[IPBox dual-homed]
    |  thuis-LAN (192.168.x.x)
    |  IPBuilding-VLAN (10.10.1.1)
    v
[Controllers 10.10.1.30 / .40 / .50]
    UDP 10001 = discovery (DS-manager-achtig)
    UDP 1001  = runtime veldbus
```

| Laag | Poort | Pad | Rol |
|------|-------|-----|-----|
| **WebConfig Wizards** | 80 | `/general/Wizards/...` | Discovery, kanaalnamen, project |
| **REST (HA)** | 30200 | `/api/v1/comp/items`, `/action/action` | Status + schakelen |
| **Veld-bus** | 1001 / 10001 | UDP | Poll/commando + module discovery |

**Kernbevinding:** *Scan modules* gebruikt **geen** `:30200` en **geen** SignalR voor de scan zelf.

---

## UI-navigatie (Wizards-sectie)

WebConfig → tab **Wizards**. Zijbalk (geobserveerd):

| Menu-item | Status RE |
|-----------|-----------|
| **Modules** | Deels — zie hieronder |
| **Drukknoppen** | Open — wizard-URLs nog niet vastgelegd |
| **REST API** | Link/documentatie, geen wizard-flow |

---

## Modules-wizard — vastgelegde IPBox-URL's

Volledige basis: `http://192.168.0.185`

### Stap 1 — Scan

| Methode | Pad | Functie |
|---------|-----|---------|
| `GET` | `/general/Wizards/Modules/Index` | Wizard pagina |
| **`POST`** | **`/general/Wizards/Modules/ScanForModules`** | **Start scan** → modulelijst (JSON) |

- **Auth:** zonder sessie-cookie → `302` → `/general/Home/Unauthorized`
- **SignalR:** alleen `loadingHub` voor voortgangsindicator (niet voor scan-data)
- **Request body:** leeg (geen parameters nodig)
- **Response:** `application/json`, keys: `IP`, `Mac` (decimale bytes), `IsNew`, `Type`, `Version`

### Stap 2 — Configuratie per module

| Methode | Pad | Functie |
|---------|-----|---------|
| `GET` | `/general/Wizards/Modules/Step2?ip={ip}&type={type}` | Config-UI per controller |
| `POST` | `/general/Hardware/Relais/ImportRelayInfo` | Relay: haalt 24 uitgangen op — body: `ip=10.10.1.30` |
| `POST` | `/general/Hardware/Relais/UpdateRelay` | **Bewaren:** stuurt alle 24 kanalen als JSON-array |
| `POST` | `/general/Hardware/Dim/ImportDimInfo` | Dimmer: haalt 8 kanalen op — body: `ip=10.10.1.40` |
| `POST` | `/general/Hardware/Dim/UpdateDim` | **Bewaren:** stuurt alle 8 kanalen als JSON-array |

**Voorbeeld request bodies:**

```
POST /general/Hardware/Relais/ImportRelayInfo
ip=10.10.1.30

POST /general/Hardware/Relais/UpdateRelay
ip=10.10.1.30&outputs=[{"ID":"547","CH":0,"Description":"Keuken LED [30.1.1]","Group":"Keuken","Pulse":0,"Lock":"00000000","LockTimer":0},{"ID":"548","CH":1,"Description":"Patio [30.1.2]","Group":"Buitenverlichting","Pulse":0,"Lock":"00000000","LockTimer":0},...]
```

**`UpdateRelay` JSON model per kanaal:**

| Veld | Voorbeeld | Betekenis |
|------|-----------|-----------|
| `ID` | `547` | Comp/item ID (overeenkomst met REST `comp/items`) |
| `CH` | `0` | Kanaal index 0–23 |
| `Description` | `Keuken LED [30.1.1]` | Display naam + `[30.x.y]` suffix |
| `Group` | `Keuken` | Ruimte/groep |
| `Pulse` | `0` | Pulserend (0 = nee) |
| `Lock` | `00011000` | Lock bits als 8-char hex string |
| `LockTimer` | `240` | Lock timer in minuten |

### Stap 2 — Dimmer (`type=Dim`)

**Import + Update model (`Dim`):**

```
POST /general/Hardware/Dim/ImportDimInfo
ip=10.10.1.40

POST /general/Hardware/Dim/UpdateDim
ip=10.10.1.40&outputs=[{"ID":"571","CH":0,"Description":"Living [40.1.1]","Group":"Gelijkvloers","DimMax":"70","DimMin":"20"},{"ID":"572","CH":1,"Description":"Bureau [40.1.2]","Group":"Gelijkvloers","DimMax":"70","DimMin":"20"},...]
```

**`UpdateDim` JSON model per kanaal:**

| Veld | Voorbeeld | Betekenis |
|------|-----------|-----------|
| `ID` | `571` | Comp/item ID (Type 2) |
| `CH` | `0` | Kanaal index 0–7 |
| `Description` | `Living [40.1.1]` | Display naam + `[40.x.y]` suffix |
| `Group` | `Gelijkvloers` | Ruimte/groep |
| `DimMin` | `20` | Minimum dimmerwaarde (%) |
| `DimMax` | `70` | Maximum dimmerwaarde (%) |

**`api.html?method=saveChannel` (pcaps 21:40/21:50):** Directe client-side save van kanaalconfiguratie naar dimmer, zelfde parametern als `UpdateDim` maar als HTTP GET query string per kanaal. Wordt door de browser aangeroepen vóór `UpdateDim` POST naar IPBox.

**Vastgelegd voorbeeld:**

```
GET /general/Wizards/Modules/Step2?ip=10.10.1.30&type=Relais
POST /general/Hardware/Relais/ImportRelayInfo
GET /general/Wizards/Modules/Step2?ip=10.10.1.40&type=Dim
POST /general/Hardware/Dim/ImportDimInfo
```

→ UI-titel *Relais stuurmodule*; 24 uitgangen = zelfde data als `comp/items` Type 1 op `10.10.1.30`.
→ UI-titel *Dimmer module*; 8 kanalen = zelfde data als `comp/items` Type 2 op `10.10.1.40`.

**Verwachte `type`-querywaarden:** `Relais` (gezien), `Dim` (gezien), vermoedelijk ook `Input`.

### Bevestiging (2026-05-18 HAR `01-36.har`)

Capture `01-36.har` bevestigt de volledige flow: relay lijst openen → "bewaar" knop. Nieuwe bevestigingen:

- **`ImportRelayInfo` response** bevat 24 kanalen (`id` 0–23) met velden `id/descr/gr/status/pulse/lock/lockTimer` — zelfde structuur als `comp/items` Type 1.
- **`UpdateRelay` POST body** bevat `ID` = REST comp/item ID (547–570, hex in POST body: `"547"` als string). Dit bevestigt de koppeling tussen WebConfig-GUI-laag (`/general/Hardware/Relais/UpdateRelay`) en REST API comp/items (`ID` 547–570 = 24 kanalen relay).
- **Signaalroute:** browser → IPBox `POST /UpdateRelay` → IPBox proxyt naar veldbus UDP/1001 → relay `10.10.1.30`. De browser praat **nooit rechtstreeks** met de relaymodule voor save-bewerkingen; dit doet de IPBox.

**Captures:** `01-36.har` + `01:36.pcapng` (zie `resources_and_docs/` voor opslag).

### Stap 3 — Samenvatting + kanaalnamen bewaren

**URL:** `GET /general/Wizards/Modules/Step3?ip={ip}&type={type}`

**Voorbeeld:** `GET /general/Wizards/Modules/Step3?ip=10.10.1.30&type=Relais`

**Inhoud:** HTML-pagina met de 24 kanalen, hun display strings (`[30.x.y]` suffix) en ruimte/groep. Geen server-side formulier-post.

**Bewaren ("Bewaar"-knop):** Drukt niet op een IPBox-URL. In plaats daarvan schrijft de browser **24 individuele HTTP GET requests** rechtstreeks naar de relay op `10.10.1.30:80`, één per kanaal:

```
GET /api.html?method=saveOutput&ds={display_name}&gr={group}&pulse={pulse}&lock={lock}&lockTimer={lockTimer}&ch={channel}
```

**Veld-bus:** zie §Veld-bus bij kanaalnaam-save hieronder.

**Onbekend:** `POST ScanForModules` response JSON (HAR legde body niet vast), `Import*` voor dimmer/input.

### SignalR (infrastructuur)

| Methode | Pad |
|---------|-----|
| `GET` | `/general/signalr/hubs` |
| `GET` | `/general/signalr/negotiate` |
| `GET` | `/general/signalr/start` |
| `GET` | `/general/signalr/connect` (SSE, `transport=serverSentEvents`) |
| `GET` | `/general/signalr/ping` |

- Enige hub: **`loadingHub`**
- `connectionData`: `[{"name":"loadinghub"}]`

---

## Kanaalnaam-save mechanisme (Step3 → api.html)

**Capture:** `21:40.pcapng` (37s, en7, 1245 pakketten)

### HTTP — api.html saveOutput

De "Bewaar"-knop in Step3 triggert **24 parallelle HTTP GET requests** van de browser rechtstreeks naar de relay op `10.10.1.30:80`:

```
GET /api.html?method=saveOutput&ds={display_name}&gr={group}&pulse={pulse}&lock={lock}&lockTimer={lockTimer}&ch={channel}
```

**Parameter-semantiek:**

| Parameter | Voorbeeld | Betekenis |
|-----------|-----------|-----------|
| `ds` | `Keuken LED [30.1.1]` | Display naam + module-index suffix |
| `gr` | `Keuken` | Groep / ruimte |
| `pulse` | `0` | Pulserend relay (0 = nee) |
| `lock` | `00011000` | Lock bits als 8-char hex string (bit 3+4 = timer active) |
| `lockTimer` | `240` | Lock timer in minuten |
| `ch` | `0` | Kanaal index (0–23) |

**Lock-bit betekenis (binaire notatie):**
```
76543210  (bitpositie)
00011000  → bit 3 + bit 4 = timer lock actief, timer = lockTimer minuten
00000000  → geen lock
11000000  → permanent lock
```

**Channel suffix in display name:** `[30.x.y]` — `30` = vast (relay IP-laatste octet), `x` = block (1-3), `y` = kanaal (1-8).

### Veld-bus bij kanaalnaam-save

Tijdens de 37s capture zijn er **geen** UDP/10001- of UDP/1001-bursts. De saveOutput naar de relay gebeurt puur via HTTP ( TCP 80). UDP/1001 verkeer tijdens de capture bestaat enkel uit:
- Dimmer poll (`I0000` / `I0154999`) — bestaande achtergrondpoll
- Regelmatige UDP/10001-discovery probes (`01 00 00 00`) van `10.10.1.1`

---

## Discovery-mechanisme op de veldbus

Tijdens de wizard-captures (21:50 pcap, frames 457/458) zijn **twee parallelle discovery-mechanismen** waargenomen:

### 1. UDP/10001 broadcast (`01 00 00 00`)

| Aspect | Waarde |
|--------|--------|
| Van | `10.10.1.1` (IPBox hub-been) |
| Naar | `255.255.255.255:10001` + `233.89.188.1:10001` |
| Payload | `01 00 00 00` (4 bytes) |
| Interval | ~10,5 s |
| Module-replies | **Geen zichtbaar** op mirror 7←15 |

### 2. WS-Discovery `Resolve` (UDP/698)

| Aspect | Waarde |
|--------|--------|
| Protocol | **WS-Discovery** — SOAP over UDP multicast |
| Van | `10.10.1.1` (IPBox) + `192.168.0.185` (thuis-LAN) |
| Naar | `239.255.255.250:698` (multicast) |
| SOAP Action | `http://schemas.xmlsoap.org/ws/2005/04/discovery/Resolve` |
| Payload | `<wsd:Resolve>` met URN `urn:uuid:0dcdd209-7281-4b83-b920-59707060a3c5` |
| Module-replies | **Geen zichtbaar** op mirror 7←15 |

**Conclusie:** de modules antwoorden via **UDP/1001** (bevestigd: relay `P3` reply, input status, dimmer poll), niet via UDP/698 of UDP/10001. WS-Discovery `Resolve` berichten van de IPBox krijgen geen reply van de modules op de gemirrorde POV. Mogelijk gaan discovery-antwoorden via een ander pad (niet via poort 15 van de IPBox).

---

## Scan-resultaat (sessie 2026-05-17)

| IP | Type | Firmware | MAC (hex) | UI |
|----|------|----------|-----------|-----|
| `10.10.1.30` | Relay | 5.1 | `00:24:77:52:ac:be` | Bestaande |
| `10.10.1.40` | Dimmer | 5.4 | `00:24:77:52:9e:a8` | Bestaande |
| `10.10.1.50` | Input | 5.2.4 | `00:24:77:52:ad:aa` | Bestaande |

MAC in UI: `0.36.119.82.172.190` = decimale bytes → `00:24:77:52:ac:be`.

**Afgeleid response-model** `ScanForModules`:

```json
[
  {
    "IP": "10.10.1.30",
    "Mac": "0.36.119.82.172.190",
    "IsNew": false,
    "Type": "Relais",
    "Version": "5.1"
  },
  {
    "IP": "10.10.1.40",
    "Mac": "0.36.119.82.158.168",
    "IsNew": false,
    "Type": "Dim",
    "Version": "5.4"
  },
  {
    "IP": "10.10.1.50",
    "Mac": "0.36.119.82.173.170",
    "IsNew": false,
    "Type": "Input",
    "Version": "5.2.4"
  }
]
```

**Mac decimaal → hex:** `0.36.119.82.172.190` → `00:24:77:52:ac:be`.

---

## Veld-bus bij scan

**Capture:** `captures/2026-05-17T210800Z_scan_modules/capture.pcapng` (128 s, en7, mirror 7←15)

| Mechanisme | Bevinding |
|------------|-----------|
| **UDP 10001** | `10.10.1.1` → `255.255.255.255` + `233.89.188.1`, payload `01 00 00 00`, ~elke 10,5 s |
| **UDP 1001** | Alleen dimmer-poll `I0000` / `I0154999`; geen scan-burst |
| **ARP** | `10.10.1.1` → `10.10.1.254` ~1 Hz; geen who-has naar `.30`/`.50` op mirror |

Geen UDP/10001-replies en geen unicast van relay/input op deze POV → discovery-antwoord mogelijk intern op IPBox of niet gemirrord.

Detail: [2026-05-17_scan_modules_udp_payloads.md](2026-05-17_scan_modules_udp_payloads.md)

---

## Correlatie REST `:30200`

`GET http://192.168.0.185:30200/api/v1/comp/items` → 81 items

| IP | Scan-UI | comp/items |
|----|---------|------------|
| `10.10.1.30` | Ja | 24× Type 1 |
| `10.10.1.40` | Nee | 4× Type 2 |
| `10.10.1.50` | Ja | 32× Type 50 |

**Scan** = fysieke controller; **comp/items** = logische kanalen/knoppen in project.

Detail: [2026-05-17_scan_modules_http_analysis.md](2026-05-17_scan_modules_http_analysis.md)

---

## Gateway-parity (streefbeeld)

| Gateway-endpoint | IPBox-equivalent |
|------------------|------------------|
| `POST /wizard/modules/scan` | `POST .../ScanForModules` |
| `GET /wizard/modules/{ip}?type=…` | `GET .../Step2?ip=…&type=…` |
| `POST /wizard/modules/{ip}/import-channels` | `POST .../ImportRelayInfo` (+ dimmer/input) |
| UDP listener `:10001` op veldbus-NIC | IPBox discovery probe |

Runtime blijft: `comp/items` + `action/action` op `:30200`.

---

## Roadmap

### Fase A — Modules wizard

- [x] URL-kaart stap 1–2 + SignalR
- [x] UDP 10001 discovery probe
- [x] Correlatie `comp/items`
- [x] **Step3 + kanaalnaam-save mechanisme** (`api.html?method=saveOutput`, 24× HTTP GET naar relay)
- [x] **UpdateRelay POST-body model** — `ip=…&outputs=[{ID, CH, Description, Group, Pulse, Lock, LockTimer}, …]&updateModule=1` (24 kanalen)
- [x] **ImportRelayInfo POST-body** — `ip=10.10.1.30`
- [x] **ImportRelayInfo response model** — bevestigd 2026-05-18: 24 kanalen `id/descr/gr/status/pulse/lock/lockTimer`
- [x] **ScanForModules request** — lege POST body (geen parameters), response is JSON 190/281 bytes
- [x] **ImportDimInfo + UpdateDim POST-body model** — dimmer-variant (8 kanalen, `DimMax`/`DimMin`)
- [x] **api.html saveChannel** — dimmer client-side direct HTTP GET per kanaal
- [ ] **Input Step2** — `type=Input` in wizard UI niet selecteerbaar; stap moet via een andere route (Handmatig? Direct URL?) worden onderzocht

### Fase B — Drukknoppen-wizard

**Doel:** de drukknoppen/provisioning-flow begrijpen. Input-modules (`10.10.1.50`) leveren fysieke drukknoppen; de wizard koppelt deze aan logische kanalen in het project.

**Workflow om te reproduceren (HAR + pcap):**

1. Open `http://192.168.0.185/general/Wizards/Pushbuttons/Index`
2. Druk "Start scan" of equivalent
3. Kies een input module (als de UI dit toelaat na Stap 1)
4. Doorloop stap 2–3 van de wizard
5. HAR bewaren (preserve-log aan) + veldbus capture parallel

**Te documenteren:**

| Item | Doel |
|------|------|
| `GET /general/Wizards/Pushbuttons/Index` | Wizard entry URL |
| `POST /general/Wizards/Pushbuttons/ScanForPushbuttons` | Scan request body + response |
| `GET /general/Wizards/Pushbuttons/Step2?ip=10.10.1.50&type=Input` | Step2 URL |
| `POST /general/Hardware/Input/ImportInputInfo` | Import endpoint body |
| `POST /general/Hardware/Input/UpdateInput` | Save endpoint body + JSON model |
| `GET /general/Wizards/Pushbuttons/Step3?ip=10.10.1.50&type=Input` | Step3 URL |
| Module-HTTP `api.html?method=getButtons` | Directe knoppen-read op `10.10.1.50:80` |
| Module-HTTP `api.html?method=buttonScan` | Button scan trigger |

**Capture filters:**
```bash
# Veld-bus
dumpcap -i en7 -f 'host 10.10.1.1 and (udp port 10001 or udp port 1001 or arp)' \
  -w captures/RE_WIZARDS_pushbuttons_$(date -u +%Y%m%dT%H%M%SZ).pcapng

# HTTP (in browser)
# HAR met preserve-log aan, alle /general/Wizards/Pushbuttons/ requests bewaren
```

**Verwachte bevindingen:**
- `ImportInputInfo` body: `ip=10.10.1.50`
- `UpdateInput` JSON: velden `ID`, `CH`, `Description`, `Group`, + input-specifieke velden (knoptype, adres?)
- Module direct `api.html?method=getButtons` — vergelijkbaar met relay/dimmer `statuses`
- Input levert 32 kanalen (Type 50 in `comp/items`)

### Fase C — Overige WebConfig

- Hardware / Instellingen / Gebruikers (zelfde `/general`-stack, latere fase)

---

## Config sync: IPBox → veldmodules

**Situatie:** als een gebruiker een output/dimmer drukknop wijzigt via WebConfig (`POST /general/Configuration/Output/UpdateComponent`), wordt de data naar de IPBox gestuurd. De IPBox moet dit vervolgens synchroniseren naar de veldmodules (`10.10.1.30/.40/.50`).

### Geziene save-paden

| Pad | Bestemming | Opslag | Gezien in capture |
|-----|-----------|--------|-------------------|
| `GET /api.html?method=saveOutput&ch=N...` | **Direct naar relay** `10.10.1.30:80` | Module firmware | 21:47 (Step3 save) |
| `POST /general/Configuration/Output/UpdateComponent` | **Naar IPBox** `192.168.0.185:80` | IPBox project-DB | 22:58 |

### Architectuur-model

```
[Gateway-to-be]  →  POST /UpdateComponent  →  [IPBox]
                                               ↓ sync (onbekend mechanisme)
                                           [Relay 10.10.1.30:80/api.html?saveOutput]
                                           [Dimmer 10.10.1.40:80/api.html?saveOutput]
                                           [Input 10.10.1.50:80/api.html?saveOutput]
```

**Hypothese:** de IPBox stuurt configuratie door naar de modules via **HTTP `api.html`** (hetzelfde mechanisme als Wizards Step3), of via **UDP/1001** commando's. Het exacte mechanisme is nog niet vastgelegd in captures.

### Bewijs uit captures

- **22:58** — `UpdateComponent` POST naar IPBox bevat `description=Keuken+Eettafel+%5B30.3.1%5D` → dit is `[30.x.y]` suffix = **relay kanaal**. De response bevat de volledige componentenlijst maar geen veldbus-communicatie.
- **21:47 (Step3)** — 24× `GET /api.html?method=saveOutput` direct naar `10.10.1.30:80` → dit is hoe de wizard kanaalnamen bewaart op de relay.
- **UDP/1001** tijdens `UpdateComponent`: alleen input-polling (`FIND` naar `10.10.1.50`) — geen relay-communicatie zichtbaar.

### Gateway-parity (streefbeeld)

De gateway moet de **IPBox-rol als config-brug** overnemen:

1. **Ontvang config** van HA (REST `:30200`) of gebruiker (WebConfig `:80`)
2. **Bewaar** in eigen database (project-model)
3. **Sync naar modules** via het juiste kanaal:
   - `PUT /module/{ip}/channel/{ch}` → HTTP `api.html?method=saveOutput` naar veldmodule
   - OF via UDP/1001 directe commando's (nader te onderzoeken)

### Openstaande vraag

> **Hoe sync de IPBox config naar modules?**
> UDP/1001 direct naar relay/dimmer, of HTTP `api.html` calls, of pas bij module-herstart/scan?
> **Volgende capture:** wijzig een output en capture gelijktijdig op mirror 7←15 + direct naar relay (als je toegang hebt).

---

## FlashAutonomyToModule — Input module sync (BEVESTIGD)

**Capture:** `save_naar_module.har` — "Autonomie naar module flashen" knop gebruikt.

### Endpoint

```
POST /general/Hardware/Input/FlashAutonomyToModule
Body: ip=10.10.1.50&autonomyButtons=[{...json array...}]
Response: {"ExtensionData":null,"Code":200,"Errors":[{"Error":"Autonomy flashed","ID":0}]}
```

### Model — autonomyButtons JSON array

Elke drukknop heeft 33 entries (index 0-32). Elk entry:

```json
{
  "index": 0,
  "id": "2DE341851900001F",       // unieke button ID
  "descr": "Badkamer",            // display naam
  "gr": "1e verdieping",          // groep
  "func1": {"ip": 30, "ch": 12, "outType": 0, "action": 2},  // functie 1
  "func2": {"ip": 30, "ch": 9,  "outType": 0, "action": 2}   // functie 2
}
```

| Veld | Waarden | Betekenis |
|------|---------|-----------|
| `ip` | 30, 40, 0 | Doelmodule: 30=relay, 40=dimmer, 0=none |
| `ch` | 0-23 (relay), 0-7 (dimmer) | Kanaal op doelmodule |
| `outType` | 0=relay, 1=dimmer, 160=special, 255=none | Type van output |
| `action` | 1, 2, 255 | Actie: 1=on?, 2=off?, 255=none |

### architectuur

```
[IPBox]  --POST FlashAutonomyToModule-->  [Input module 10.10.1.50]
                                               ↓
                                          Slaat autonomous logic op
                                               ↓ (bij drukknop-indrukken)
                                          stuurt commando naar:
                                            relay 10.10.1.30 (ip=30)
                                            dimmer 10.10.1.40 (ip=40)
```

**`func1` en `func2`:** elke drukknop kan twee functies hebben (links/rechts ingedrukt, of kort/lang). In het voorbeeld: "Badkamer" triggert relay kanaal 12 EN kanaal 9.

**Belangrijk:** de input module bevat de **autonomous programming** — wat elke drukknop doet als hij wordt ingedrukt. Dit woont in de input module firmware, niet in de relay/dimmer.

### Gateway-parity

De gateway moet de `FlashAutonomyToModule` endpoint kunnen afhandelen:
1. Ontvang POST met `ip` (target input module) + `autonomyButtons` JSON array
2. Sync naar input module via **HTTP `api.html?method=saveAutonomy`** (vermoedelijk) of UDP/1001
3. Input module commit de programming naar flash

---

## Aanbevolen captures

**HTTP:** browser HAR tijdens volledige wizard (scan → kies module → step2 → step3).

**Veld-bus:**

```bash
dumpcap -i en7 -f 'host 10.10.1.1 and (udp port 10001 or udp port 1001 or arp)' \
  -w captures/RE_WIZARDS_$(date -u +%Y%m%dT%H%M%SZ).pcapng
```

---

## Gerelateerde documenten

| Pad | Inhoud |
|-----|--------|
| [2026-05-17_scan_modules_http_analysis.md](2026-05-17_scan_modules_http_analysis.md) | Detail HTTP Modules |
| [2026-05-17_scan_modules_udp_payloads.md](2026-05-17_scan_modules_udp_payloads.md) | Detail UDP/L2 |
| [RE_STATE.md](RE_STATE.md) | Canonieke RE-status |
| [IPBOX_REST_API_TEST_CALLS.md](IPBOX_REST_API_TEST_CALLS.md) | REST-laag (niet wizards) |
| `captures/2026-05-17T210800Z_scan_modules/` | Pcap + `comp_items_baseline.json` |
| `captures/RE_WIZARDS_2026-05-17T214900Z_full/21:47.pcapng` | Full wizard (Stap 1–3), 46s, en7, 1323 pkts |
| `captures/RE_WIZARDS_2026-05-17T214900Z_full/21-47.har` | Full wizard HAR — alle POSTs bewaard |
