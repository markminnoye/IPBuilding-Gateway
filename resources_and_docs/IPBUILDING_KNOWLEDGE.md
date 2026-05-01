# IPBuilding System — Knowledge Base
> **Doel van dit document:** Gestructureerde kennis voor AI agents die werken aan het reverse-engineeren en vervangen van de IPBox. Elke sectie is zelfstandig leesbaar. Gebruik de TOC om direct naar de relevante sectie te springen.

---

## TABLE OF CONTENTS

1. [PROJECT CONTEXT](#1-project-context)
2. [HARDWARE INVENTORY](#2-hardware-inventory)
3. [NETWORK TOPOLOGY](#3-network-topology)
4. [SYSTEM ARCHITECTURE](#4-system-architecture)
5. [PROTOCOL — IPBOX REST API](#5-protocol--ipbox-rest-api)
6. [PROTOCOL — UDP BINARY (CONTROLLER LEVEL)](#6-protocol--udp-binary-controller-level)
7. [BESTAANDE HA INTEGRATIE](#7-bestaande-ha-integratie)
8. [INSTALLATIE SPECIFIEK (MARK)](#8-installatie-specifiek-mark)
9. [REVERSE ENGINEERING PLAN](#9-reverse-engineering-plan)
10. [VERVANGINGSPLAN IPBOX](#10-vervangingsplan-ipbox)
11. [OPENSTAANDE VRAGEN](#11-openstaande-vragen)

---

## 1. PROJECT CONTEXT

**Eigenaar:** Mark Minnoye (mark@sonicrocket.be)  
**Doel:** De IPBox (IP0000X) vervangen door een open-source oplossing die:
- Rechtstreeks communiceert met IPBuilding controllers via hun native UDP protocol
- Integreert met meerdere domotica systemen (Home Assistant, en anderen)
- Niet afhankelijk is van propriëtaire, verouderde hardware

**Status:** Fase 1 — Protocol reverse engineering  
**GitHub HA integratie:** https://github.com/markminnoye/HA-IPBuilding  
**Fabrikant:** IPBuilding NV, Honderdweg 1, 9230 Wetteren — www.ipbuilding.com

---

## 2. HARDWARE INVENTORY

### 2A — IP200PoE (Relay Controller)
- **Functie:** Aansturing van 3 blokken van elk 8 output relays (totaal 24 outputs)
- **Type aangesloten blokken:** IP0201 (elk 8 relays, max 16A/kanaal, 3600W totaal)
- **Verbinding met blokken:** Flat cable per blok (3 aansluitingen)
- **Netwerk:** PoE, bekabeld ethernet
- **IP:** `10.10.1.30`
- **MAC:** `00:24:77:52:AC:BE` *(notatie uit systeem: 0.36.119.82.172.190)*
- **UDP poort:** 1001 (luistert op inkomende polling van IPBox)

### 2B — IP0300PoE (Dimmer Controller)
- **Functie:** Aansturing van 4-kanaals dimmerblok IP0302
- **Type aangesloten blokken:** IP0302 (4 kanalen, 20V input, 7W min / 400W max per kanaal, jumper voor inductief/capacitief)
- **Output types:** 2× connector voor 4 kanalen + 1× connector voor 8 kanalen 12VDC (functie onbekend)
- **Netwerk:** PoE, bekabeld ethernet
- **IP:** `10.10.0.40`
- **MAC:** `00:24:77:52:9E:A8` *(notatie uit systeem: 0.36.119.82.158.168)*
- **UDP poort:** 1001 (vermoedelijk zelfde protocol als IP200PoE)

### 2C — IP1100PoE (Input Module)
- **Functie:** Inlezen van drukknopschakelaars via Cat5 kabels
- **Aansluitingen:** 8 inputs, telkens 1 paar draden (blauw + wit/blauw van Cat5)
- **Momenteel:** 2 inputs in gebruik (2 kabels met schakelaars)
- **12V DC output aanwezig** (functie onbekend)
- **Netwerk:** PoE, bekabeld ethernet
- **IP:** Onbekend — nog te bepalen via netwerkscan

### 2D — IP040x (Drukknop Interface)
- **Functie:** Koppelt fysieke drukknoppen aan de input kabel
- **Types:**
  - IP0401: 1 NO contact, 1 MAC adres
  - IP0402: 2 NO contacten, MAC adressen
  - IP0404: 4 NO contacten
  - IP0406: 6 NO contacten
- **Aansluiting:** UTP Cat5e (getwist paar, max 200m), schroefklemmen D en M voor databus
- **Max afstand interface → drukknop:** 10 cm
- **Vereist:** Potentiaalvrije contacten
- **In gebruik:** Meerdere interfaces op 2 Cat5 kabels (lus verbroken tijdens werken)

### 2E — IP0000X (IPBox) — TE VERVANGEN
- **Functie:** Gateway/controller die alle IPBuilding componenten beheert
- **IP:** `10.10.1.1` (voorgeprogrammeerd, vaste waarde)
- **Voeding:** 12V DC adapter (230V)
- **Diensten aan boord:**
  - IPBuilding service (beheert IP1100, IP0200, IP0300, IP0600, …)
  - Webserver (mobiele software + instellingen)
  - REST API (externe integratie, poort 30200)
  - Muziek server (audio streaming)
  - Remote server (connectie op afstand)
  - DNS server (unieke webnaam)
- **USB:** Optionele DMX aansturing
- **Status:** Verouderd, duur, kwetsbaar — prioriteit om te vervangen

---

## 3. NETWORK TOPOLOGY

```
Subnet 10.10.1.x (relays)
  10.10.1.1    — IPBox (IP0000X)          [gateway/controller]
  10.10.1.30   — IP200PoE relay controller MAC: 00:24:77:52:AC:BE
  10.10.1.50   — Onbekend device          [gezien in pcap, luistert op UDP/1001]

Subnet 10.10.0.x (dimmers)
  10.10.0.40   — IP0300PoE dimmer controller MAC: 00:24:77:52:9E:A8

IP1100PoE input module — IP onbekend
IP040x drukknop interfaces — geen eigen IP (serieel op Cat5 bus)
```

**Opmerking:** `10.10.1.50` (MAC `00:24:77:52:AD:AA`) verschijnt in pcap als actieve UDP/1001 partner van de IPBox. Mogelijk de IP200PoE relay controller (MAC wijkt licht af van opgegeven waarde — verifiëren).

---

## 4. SYSTEM ARCHITECTURE

### Huidige architectuur (MET IPBox)
```
[Drukknop]
    │ (potentiaalvrij contact)
[IP040x interface] ── Cat5 bus ──► [IP1100PoE input module]
                                          │ UDP/1001 ▲▼
                                    [IP0000X IPBox]   ← REST API (HTTP/30200) ← [Home Assistant]
                                          │ UDP/1001 ▲▼
                              [IP200PoE] + [IP0300PoE]
                                   │ flat cable            │ flat cable
                              [IP0201 relays]        [IP0302 dimmers]
                                   │ 230V                   │ 0-10V
                              [Lichten/apparaten]    [Dimmable lichten]
```

### Beoogde architectuur (ZONDER IPBox)
```
[IP1100PoE] ──── UDP/1001 ────► [Custom Gateway Service]
[IP200PoE]  ──── UDP/1001 ────►     (Python, Raspberry Pi
[IP0300PoE] ──── UDP/1001 ────►      of HA Add-on)
                                         │
                               REST API / MQTT / andere
                                         │
                              [Home Assistant] [Andere domotica]
```

---

## 5. PROTOCOL — IPBOX REST API

**Base URL:** `http://10.10.1.1:30200/api/v1`  
**Authenticatie:** Geen (lokaal netwerk)  
**Format:** JSON

### 5.1 Endpoints (gedocumenteerd en in gebruik)

| Method | Endpoint | Parameters | Beschrijving |
|--------|----------|------------|--------------|
| GET | `/comp/items` | `types` (kommalijst) | Alle devices, optioneel gefilterd op type |
| GET | `/action/action` | `id`, `actionType`, `value` | Stuur commando naar device |

### 5.2 actionType waarden

| actionType | Waarde | Beschrijving |
|------------|--------|--------------|
| `ON` | — | Relay aan |
| `OFF` | 0 | Relay/dimmer uit |
| `DIM` | 0-100 | Dimmer naar waarde |

### 5.3 Device object structuur (JSON)

```json
{
  "ID": 123,
  "Type": 1,
  "Kind": 1,
  "Description": "Woonkamer lamp",
  "Group": "Woonkamer",
  "Value": 0
}
```

### 5.4 Device Types (const.py)

| Constante | Waarde | Beschrijving |
|-----------|--------|--------------|
| TYPE_RELAY | 1 | Relay output (aan/uit) |
| TYPE_DIMMER | 2 | Dimmer (0-100%) |
| TYPE_DMX | 3 | DMX licht |
| TYPE_ENERGY_COUNTER | 40 | Energieteller |
| TYPE_ENERGY_METER | 41 | Energiemeter |
| TYPE_BUTTON | 50 | Drukknop input |
| TYPE_TEMPERATURE | 51 | Temperatuursensor |
| TYPE_DETECTOR | 52 | Detector |
| TYPE_ANALOG_SENSOR | 53 | Analoge sensor |
| TYPE_KMI | 54 | KMI weerstation |
| TYPE_WEATHER_STATION | 55 | Weerstation |
| TYPE_TIME | 56 | Tijdmodule |
| TYPE_LED | 60 | LED strip |
| TYPE_ACCESS_READER | 70 | Toegangslezer |
| TYPE_ACCESS_KEY | 80 | Toegangssleutel |
| TYPE_SPHERE | 100 | Scene/sfeer |
| TYPE_TEMP_SPHERE | 101 | Tijdelijke scene |
| TYPE_PROG | 102 | Programma |
| TYPE_ACCESS_CONTROL | 103 | Toegangscontrole |
| TYPE_SCRIPT | 150 | Script |
| TYPE_REGIME | 200 | Regime |

### 5.5 Device Kinds

| Waarde | Beschrijving |
|--------|--------------|
| 1 | Light (licht) |
| 2 | Socket (stopcontact) |
| 3 | Automation |
| 4 | Lock |
| 5 | Fan |
| 6 | Valve |
| 7 | Temperature |
| 8 | Not Applicable |

---

## 6. PROTOCOL — UDP BINARY (CONTROLLER LEVEL)

> **Status:** Gedeeltelijk gedecodeeerd via pcap analyse. Commandopakketten nog ONBEKEND.

### 6.1 Transport
- **Protocol:** UDP
- **Poort:** 1001 (op de controller)
- **Richting polling:** IPBox → Controller (initiator)
- **Poll interval:** ~2 seconden

### 6.2 Poll pakket (IPBox → Controller)

**Lengte:** 5 bytes  
**Payload (hex):** `49 30 30 30 30`  
**Payload (ASCII):** `I0000`

```
Byte  Waarde  Betekenis
0     0x49    'I' — identifier (IPBuilding?)
1-4   0x30    '0' × 4 — device/channel identifier of fixed padding
```

### 6.3 Status response (Controller → IPBox)

**Lengte:** 13 bytes  
**Payload (hex):** `49 02 52 05 02 04 00 00 00 00 00 45 00`

```
Byte   Hex    ASCII  Vermoedelijke betekenis
0      0x49   'I'    Identifier (IPBuilding)
1      0x02   —      Pakket type of versie?
2      0x52   'R'    'R' = Response?
3      0x05   —      Onbekend
4      0x02   —      Onbekend
5      0x04   —      Status bitfield? (relay standen: 0x04 = relay 3 aan?)
6-10   0x00   —      Nul bytes (padding of uitgebreide status)
11     0x45   'E'    Onbekend ('E' = End? of waarde)
12     0x00   —      Nul
```

**Opmerking:** Byte 5 (0x04) is mogelijk een bitfield voor 8 relay outputs. Bij 8-bit encoding: `0000 0100` = relay 3 actief.

### 6.4 Commandopakketten — ONBEKEND

De commandopakketten (licht aan/uit, dimmen) zijn **nog niet gecaptured**. Dit is de prioriteit voor de volgende stap.

**Hypothese gebaseerd op poll structuur:**
- Zelfde 'I' prefix vermoedelijk
- Channel/device ID in de payload
- Waarde (0x00=uit, 0x64=100%=aan, of 0x01-0x63 voor dimmen)

### 6.5 Pcap bestand

**Bestandsnaam:** `traffic between controller an IPbox.pcapng`  
**Locatie:** `/IPBuilding/` map in Google Drive  
**Inhoud:** Polling verkeer tussen IPBox (10.10.1.1) en controller (10.10.1.50) op UDP/1001. Geen commandopakketten aanwezig in deze capture.

---

## 7. BESTAANDE HA INTEGRATIE

**Repository:** https://github.com/markminnoye/HA-IPBuilding  
**Type:** Home Assistant Custom Component (HACS compatibel)  
**Taal:** Python (asyncio + aiohttp)

### 7.1 Bestanden

| Bestand | Functie |
|---------|---------|
| `api.py` | REST API client (get_devices, set_value) |
| `const.py` | Device type constanten |
| `__init__.py` | Setup, DataUpdateCoordinator (polling 20s) |
| `light.py` | Licht entities (relay + dimmer) |
| `switch.py` | Schakelaar entities |
| `button.py` | Drukknop entities |
| `sensor.py` | Sensor entities |
| `scene.py` | Scene/sfeer entities |
| `config_flow.py` | UI configuratie (host + poort) |

### 7.2 Verbinding parameters

- **Host:** IP adres van de IPBox (default: 10.10.1.1)
- **Poort:** 30200 (DEFAULT_PORT in const.py)
- **Poll interval:** 20 seconden
- **Initieel:** Alle devices ophalen, daarna enkel Type 1,2,3,60 pollen

### 7.3 API client (api.py samenvatting)

```python
# Base URL
http://{host}:{port}/api/v1

# Devices ophalen
GET /comp/items?types=1,2,3,60

# Commando sturen
GET /action/action?id={device_id}&actionType={ON|OFF|DIM}&value={0-100}
```

### 7.4 Wat werkt momenteel

- Ontdekking en controle van relays (aan/uit)
- Ontdekking en controle van dimmers (helderheid)
- Scenes/sferen activeren
- Polling voor state updates

---

## 8. INSTALLATIE SPECIFIEK (MARK)

### 8.1 Actieve componenten

| Component | IP | MAC | Status |
|-----------|-----|-----|--------|
| IP0000X IPBox | 10.10.1.1 | — | Actief, te vervangen |
| IP200PoE relay controller | 10.10.1.30 | 00:24:77:52:AC:BE | Actief |
| IP0300PoE dimmer controller | 10.10.0.40 | 00:24:77:52:9E:A8 | Actief |
| IP1100PoE input module | Onbekend | — | Actief (2 inputs) |

### 8.2 Aangesloten loads

- **Relay controller (IP200PoE):** 3 blokken IP0201, elk 8 outputs → 24 relay kanalen
- **Dimmer controller (IP0300PoE):** 1 blok IP0302 → 4 dimmer kanalen
- **Inputs (IP1100PoE):** 2 Cat5 kabels met schakelaars (lus verbroken tijdens werken)
- **Drukknop interfaces:** Meerdere IP040x op de 2 input kabels

### 8.3 Bijzonderheden

- De schakelaarslus was ooit een gesloten ring maar is verbroken tijdens werkzaamheden
- 2 inputs zijn momenteel in gebruik op de IP1100PoE
- De IPBox dreigt te crashen (verouderde hardware, duur om te vervangen)
- Home Assistant integratie is operationeel via de IPBox REST API

---

## 9. REVERSE ENGINEERING PLAN

### 9.1 Doel

Volledig begrijpen van het UDP/1001 binair protocol zodat we de IPBox kunnen bypassen.

### 9.2 Aanpak — Extra pcap sessies

**Stap 1: Netwerk voorbereiding**
- Wireshark of `tcpdump` draaien op een machine in subnet 10.10.1.x
- Filter: `udp port 1001`

**Stap 2: Acties uitvoeren via IPBox webinterface of REST API**
Volgorde van acties te capteren:
1. Relay aan (`actionType=ON, id=X`)
2. Relay uit (`actionType=OFF, id=X`)
3. Dimmer op 50% (`actionType=DIM, value=50, id=Y`)
4. Dimmer op 100%
5. Dimmer op 0% (uit)
6. Scene activeren
7. Input drukknop indrukken → reactie observeren

**Stap 3: Analyse**
- Vergelijk UDP payloads bij elke actie
- Identificeer: device ID positie, waarde positie, commando type
- Controleer of bitfields of BCD encoding gebruikt wordt
- Zoek naar checksum bytes (vaak laatste byte)

**Stap 4: Decoder schrijven**
- Python script dat payloads decodeert naar leesbare commando's
- Encoder die leesbare commando's omzet naar UDP payloads

### 9.3 tcpdump commando voor capture

```bash
# Op machine in 10.10.1.x subnet
sudo tcpdump -i eth0 -w ipbuilding_commands.pcapng 'udp port 1001'

# Of gefilterd op specifieke controller
sudo tcpdump -i eth0 -w ipbuilding_relay.pcapng 'host 10.10.1.30 and udp port 1001'
```

### 9.4 Hypothesen te verifiëren

| Hypothese | Verificatie |
|-----------|-------------|
| Byte 5 van response = relay bitfield | Schakel relay 1 aan, kijk of bit 0 wijzigt |
| Commando heeft zelfde 'I' prefix | Capture commandopakketten en vergelijk |
| Device ID in bytes 1-2 of 3-4 | Test met verschillende device IDs |
| Checksum aanwezig | Zoek byte die varieert met inhoud |
| IP0300PoE zelfde protocol | Capture dimmer controller apart |

---

## 10. VERVANGINGSPLAN IPBOX

### 10.1 Gekozen architectuur — Custom Gateway Service

Een lichtgewicht Python service die:
- Rechtstreeks praat met alle IPBuilding controllers via UDP/1001
- Een REST API exposed die compatibel is met de bestaande IPBox API (poort 30200)
- Optioneel ook MQTT publiceert voor bredere domotica compatibiliteit
- Draait als Docker container, HA Add-on, of standalone op Raspberry Pi

### 10.2 Fasen

| Fase | Beschrijving | Status |
|------|-------------|--------|
| 1 | Protocol reverse engineering (UDP/1001) | 🔄 Bezig |
| 2 | Python UDP client/server implementatie | ⏳ Wachten op Fase 1 |
| 3 | REST API laag (compatibel met IPBox) | ⏳ Wachten op Fase 2 |
| 4 | Testing + validatie in productie | ⏳ Wachten op Fase 3 |
| 5 | MQTT integratie (optioneel) | ⏳ Later |
| 6 | HA Add-on packaging | ⏳ Later |

### 10.3 Tech stack (voorstel)

```
Python 3.11+
asyncio (UDP socket handling)
aiohttp (REST API server)
pydantic (data validatie)
Docker / HA Add-on manifest
```

### 10.4 Minimale REST API te implementeren

```
GET  /api/v1/comp/items          → alle devices teruggeven
GET  /api/v1/action/action       → commando doorsturen naar controller
```

---

## 11. OPENSTAANDE VRAGEN

| # | Vraag | Prioriteit |
|---|-------|-----------|
| 1 | Volledig UDP commandoprotocol decoderen | 🔴 Hoog |
| 2 | IP adres van IP1100PoE bepalen | 🟡 Middel |
| 3 | Functie van 12V DC output op IP1100PoE en IP0300PoE | 🟢 Laag |
| 4 | Bevestigen dat 10.10.1.50 de IP200PoE is (MAC verschil) | 🟡 Middel |
| 5 | Protocol voor IP1100PoE input events (hoe stuurt module drukknop events?) | 🔴 Hoog |
| 6 | Ondersteunt IPBox WebSocket of events voor realtime updates? | 🟡 Middel |
| 7 | Functie van de 8-kanaals 12VDC output op IP0300PoE | 🟢 Laag |
| 8 | Zijn er meerdere subnets of is 10.10.0.x ook bereikbaar? | 🟡 Middel |
| 9 | Hoe worden scenes/sferen gerepresenteerd op controller niveau? | 🟡 Middel |
| 10 | Maximal aantal devices per controller? | 🟢 Laag |

---

*Document gegenereerd: 2026-05-01 | Versie: 1.0 | Auteur: AI Agent (Claude) op basis van hardware documentatie, pcap analyse en GitHub broncode*
