# IPBuilding System — Knowledge Base

> **Last updated:** 2026-05-22
>
> **Doel:** Gestructureerde kennis voor het reverse-engineeren en vervangen van de IPBox. **Context-tiers (token-besparend):** laad dit bestand **niet** standaard volledig; gebruik de **TOC** en open alleen secties die bij de vraag passen—bijv. §3–4 voor topologie en architectuur, §5 voor REST, §6 voor UDP, §8–9 voor install/RE en capture-setup. Globaal beleid: `AGENTS.md` en `docs/context-policy.md`. PDFs en grote **pcap**’s horen in **T3**: niet in de chat, tenzij je een beperkte slice analyseert.

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
12. [CONFIGURATIEMODEL & CENTRALE EENHEID](#12-configuratiemodel--centrale-eenheid-uit-installatiehandleiding-v60)

---

## 1. PROJECT CONTEXT

**Eigenaar:** Mark Minnoye ([mark@sonicrocket.be](mailto:mark@sonicrocket.be))  
**Doel:** De IPBox (IP0000X) vervangen door een open-source oplossing die:

- Rechtstreeks met IPBuilding controllers communiceert (primair **UDP/1001**; aanvullend o.a. **HTTP/80** op modules waar gedocumenteerd in §2A–C)
- Dezelfde **REST-sematiek** naar clients kan bieden als de IPBox (poort **30200**) — zie §5; dit is te correleren en te modelleren via capture
- Integreert met meerdere domotica systemen (Home Assistant, en anderen)
- Niet afhankelijk is van propriëtaire, verouderde hardware

**Fase 1 (reverse engineering)** is **niet** “alleen UDP”: we moeten het volledige gedrag en de configuratierandvoorwaarden begrijpen. Onderdeel van het latere traject: **provisioning en projectconfiguratie zoals in de IPBox GUI** (mappings, knoppen, outputs, scenes, …) — die stromen en data­modellen moeten apart worden achterhaald en horen **niet** impliciet op te lossen met enkel packet-level UDP-RE.

**Status:** Fase 1 veldbus-wire **afgerond** (relay/dimmer/input); northbound **goedgekeurd** (HA add-on + companion, geen IPBox-REST-clone). Canoniek: [RE_STATE.md](RE_STATE.md). Doc-index: [README.md](README.md).  
**GitHub HA integratie:** [https://github.com/markminnoye/HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding)  
**Fabrikant:** IPBuilding NV, Honderdweg 1, 9230 Wetteren — [www.ipbuilding.com](http://www.ipbuilding.com)

---

## 2. HARDWARE INVENTORY

### 2A — IP200PoE / IP0200PoE (Relay Controller)

- **Functie:** Aansturing van 3 blokken van elk 8 output relays (totaal 24 outputs)
- **Type aangesloten blokken:** IP0201 (elk 8 relays, max 16A/kanaal, 3600W totaal)
- **Verbinding met blokken:** Flat cable per blok (3 aansluitingen)
- **Netwerk:** PoE, bekabeld ethernet
- **IP:** `10.10.1.30`
- **MAC:** `00:24:77:52:AC:BE` *(notatie uit systeem: 0.36.119.82.172.190)*
- **UDP poort:** 1001 (luistert op inkomende polling van IPBox)
- **Naamgeving:** De ingebouwde webinterface toont het moduletype **IP0200PoE** en de titel *24 × OUTPUT MODULE*. In oudere docs en op de IPBox wordt hetzelfde toestel vaak **IP200PoE** genoemd.

#### Embedded webserver (HTTP, poort 80)

Het relay-toestel biedt naast UDP/1001 een **lokale HTTP/1.0**-interface (standaardpoort **80**): status, beheer en een eenvoudige JSON-API. Geobserveerd op `http://10.10.1.30/` (firmware **5.1**).


| Onderdeel  | URL / pad      | Inhoud                                                                                  |
| ---------- | -------------- | --------------------------------------------------------------------------------------- |
| Home       | `/`            | Links naar Status, Edit, System; toont moduletype, *24 × OUTPUT MODULE*, firmwareversie |
| Status-UI  | `/status.html` | Lijst van 24 kanalen; laadt data via `api.html` (zie hieronder)                         |
| Config-UI  | `/edit.html`   | Kanaalomschrijvingen / groepen (via hetzelfde `api.html`-patroon)                       |
| Systeem-UI | `/system.html` | IP/DHCP, security, backup/reset (aanroepen via `api.html`)                              |


**Status als JSON (machineleesbaar):**

- **Request:** `GET /api.html?method=statuses`
- **Response:** JSON-array met **24** objecten, kanaalindex `id` van **0** t/m **23**.


| Veld        | Type / voorbeeld | Betekenis                                                                      |
| ----------- | ---------------- | ------------------------------------------------------------------------------ |
| `id`        | int              | Kanaalindex (0-based), komt overeen met UI-volgnummer − 1                      |
| `descr`     | string           | Omschrijving (project/IPBox; kan speciale tekens bevatten)                     |
| `gr`        | string           | Groepnaam                                                                      |
| `status`    | int              | `0` = uit, `1` = aan                                                           |
| `pulse`     | int              | Pulsduur in firmware-eenheden; de web-UI deelt door **2** om seconden te tonen |
| `lock`      | string (bits)    | Kanaalvergrendeling / onderlinge lock (bitpatroon)                             |
| `lockTimer` | int              | Timer in dezelfde schaal als pulse (UI: `/2` → seconden)                       |


**Aansturing via GET (zelfde host, pad `api.html`):**


| Actie             | Query                              |
| ----------------- | ---------------------------------- |
| Kanaal `N` aan    | `?method=sCh&ch=N`                 |
| Kanaal `N` uit    | `?method=cCh&ch=N`                 |
| Kanaal `N` toggle | `?method=tCh&ch=N`                 |
| Alles aan / uit   | `?method=allOn` / `?method=allOff` |


**Systeem- en config-methodes** (aangeroepen vanuit `system.html` / `edit.html`, eveneens `GET` op `api.html`):

- `getSysSet` — systeeminstellingen uitlezen
- `setIp` — parameters o.a. `dhcp`, `ip`, `subnet`, `gateway`
- `setButton`, `setSecurity` — o.a. `allow` voor HTTP-toegangsbeleid
- `backupConfig`, `resetConfig`, `saveOutput` — backup / fabrieksreset / outputconfig bewaren

**Directe read-only URLs (relay `10.10.1.30`, live geverifieerd op 2026-05-04):**

- `http://10.10.1.30/api.html?method=getSysSet`
  - voorbeeldvelden: `dhcp`, `ip`, `subnet`, `gateway`, `mac`, `button`, `allow`
- `http://10.10.1.30/api.html?method=backupConfig`
  - volledige moduleconfig met o.a. `device.refNr`, `network`, `button`, `channels[]` (kanaalbeschrijvingen en lock/pulse-instellingen)

`**system.html` — backup / restore / reset (IP0200PoE, firmware 5.1)**

Bron: embedded pagina `http://<host>/system.html` + inline JavaScript (geen destructieve acties uitgevoerd bij documentatie; alleen `backupConfig` GET geverifieerd op `10.10.1.30`). `refNr` in de pagina: `**IP0200PoE`**.


| UI-onderdeel                                           | Mechanisme                                                                                                                        | URL / aanroep                                                                                                                                                                                                                                 |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backup** (“Download configuration file from module”) | Eén synchrone XHR                                                                                                                 | `GET /api.html?method=backupConfig` — response body is **één JSON-document**. Voorgestelde bestandsnaam in UI: `IP0200PoE-{ip_met_underscores}-{YYYYMMDD}.json`.                                                                              |
| **Restore** (“Upload configuration file to module”)    | Geen enkele “restore”-URL: de browser leest het backup-JSON lokaal, controleert `device.refNr === "IP0200PoE"`, daarna per kanaal | `GET /api.html?method=saveOutput&ds=<url-encoded descr>&gr=<url-encoded groep>&pulse=<n>&lock=<lock-string>&lockTimer=<n>&ch=<id>` — herhaald voor elk element in `channels[]` (24 kanalen). Daarna: `GET /api.html?method=setButton&status=0 |
| **Reset** (“Reset configuration to default state”)     | Bevestigingspopup, daarna                                                                                                         | `GET /api.html?method=resetConfig` — zelfde tekst als dimmer-UI: default config **behalve** netwerkinstellingen.                                                                                                                              |


**Backup-JSON-structuur** (afgeleid uit `system.html` + live `backupConfig`):

- `device.refNr` — `"IP0200PoE"`.
- `network` — `dhcp`, `ipaddress`, `subnet`, `gateway` (strings in sample).
- `button` — `status`.
- `channels` — array van `{ id, descr, gr, pulse, lock, lockTimer }` (24 entries).

Voorbeeld-response opgeslagen: `captures/http_snapshots/2026-05-03_IP0200PoE_10.10.1.30_backupConfig.json`. **Let op:** in die capture zat minstens één **ASCII-controlteken** in een `descr`-string waardoor strikte JSON-parsers kunnen falen; de module/firmware levert het zo. Voor analyse eventueel controlchars sanitizen of hex inspecteren.

**Beveiliging:** Er is geen login op de homepage; beleid hangt af van de **security**-instelling op `system.html` en van het netwerksegment. **Niet** onbeschermd naar het internet routeren.

**Relevantie:** Tweede datapad naast **UDP/1001** en naast de **IPBox REST API** — handig om relaystatus te vergelijken met UDP-bytes of tijdelijk te sturen tijdens reverse engineering (mits het LAN vertrouwd is).

### 2B — IP0300PoE (Dimmer / 0-10V Controller)

- **Functie:** Aansturing van dimmerblokken (fabrikant o.a. **IP0302**); fysiek **4 kanalen** per blok (20V input, 7W min / 400W max per kanaal, jumper voor inductief/capacitief)
- **Type aangesloten blokken:** IP0302
- **Output types:** 2× connector voor 4 kanalen + 1× connector voor 8 kanalen 12VDC (functie onbekend)
- **Netwerk:** PoE, bekabeld ethernet
- **IP (bekend):** `10.10.1.40` — DHCP-gebaseerd, niet hardcoderen. MAC hieronder.
- **MAC (bekend voor `10.10.1.40`):** `00:24:77:52:9E:A8`
- **UDP poort:** 1001 (vermoedelijk zelfde families als IP200PoE / relay)

#### Geobserveerde UDP-vorm (`10.10.1.40` -> IPBox, lab)

Op mirror-bron `12` (capture op `en7`) zijn bij getimede DIM/OFF-REST-stappen herhaalbare UDP/1001 payloads gezien met vaste 8-byte ASCII-vorm:

- patroon: `I0154<C><VV>` — de 3 cijfers = **`<kanaal><waarde-code>`** (correctie 2026-06-03)
- voorbeelden (kanaal 1, Bureau): `I0154130`=30%, `I0154170`=70%, `I0154199`=100%, `I0154100`=uit; `I0154999`=idle/poll
- waarde-code `<VV>`: `00`=uit, `10..98`=%, `99`=100%; alleen kanaal 0 leek vroeger te kloppen omdat het leidende cijfer dan `0` is
- in deze capture-POV is alleen `10.10.1.40 -> 192.168.0.185` zichtbaar; geen omgekeerde UDP/1001-stroom.

Dit is bruikbaar als **observed payload shape** voor correlatie, maar nog geen volledig command-schema. Zie:
`resources_and_docs/evidence/2026-05-03_dimmer_udp_payload_correlation.md`.

#### Embedded webserver (HTTP, poort 80)

Dezelfde soort embedded UI als de relaymodule: **HTTP/1.0**, homepage met Status / Edit / System, data via `**/api.html`**. Geobserveerd op `**http://10.10.1.40/`** (firmware **5.4**). De titel in de UI is **IP0300PoE** — **8 × 0-10V OUTPUT MODULE** (logische 0-10V-kanalen in software; fysieke bedrading kan beperkter zijn, zie IP0302 hierboven).


| Onderdeel  | URL / pad      | Inhoud                                                                   |
| ---------- | -------------- | ------------------------------------------------------------------------ |
| Home       | `/`            | Links Status, Edit, System; moduletype, kanaalaantal, firmware           |
| Status-UI  | `/status.html` | Per kanaal: aan/uit/toggle, schuifregelaar 0–100%, status via `api.html` |
| Config-UI  | `/edit.html`   | Kanaalomschrijvingen / groepen                                           |
| Systeem-UI | `/system.html` | IP/DHCP, security, backup/reset                                          |


**Status als JSON:**

- **Request:** `GET /api.html?method=statuses`
- **Response (voorbeeld `10.10.1.40`):** JSON-array met **8** objecten, `id` **0** t/m **7** (aantal kanalen kan per firmware/config verschillen).


| Veld     | Betekenis                                                    |
| -------- | ------------------------------------------------------------ |
| `id`     | Kanaalindex (0-based)                                        |
| `descr`  | Omschrijving                                                 |
| `gr`     | Groepnaam                                                    |
| `dimMin` | Minimum helderheid (%) in de module                          |
| `dimMax` | Maximum helderheid (%) in de module                          |
| `status` | Huidige waarde; **0** = uit, anders **1–100** (helderheid %) |


**Aansturing via GET (`api.html`):**


| Actie             | Query                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------- |
| Kanaal `N` aan    | `?method=sCh&ch=N&val=<slider>` — `val` komt uit de UI (zelfde parameter als bij dim) |
| Kanaal `N` uit    | `?method=cCh&ch=N&val=<slider>`                                                       |
| Kanaal `N` toggle | `?method=tCh&ch=N&val=<slider>`                                                       |
| Kanaal `N` dimmen | `?method=dCh&ch=N&val=0..100`                                                         |
| Alles max / uit   | `?method=allOn` / `?method=allOff`                                                    |


*(De UI stuurt bij elke `s`/`c`/`t`/`d`-actie ook `val` mee — de waarde van het schuifveld `valueToDim_N`.)*

**Systeem- en config-methodes** (zelfde patroon als §2A, met kleine naamverschillen):

- `getSysSet`, `setIp`, `setButton`, `setSecurity`, `backupConfig`, `resetConfig`
- Config bewaren: `**saveChannel`** (niet `saveOutput` zoals bij de relaymodule)

`**system.html` — backup / restore / reset (IP0300PoE, firmware 5.4)**

Bron: embedded pagina `http://<host>/system.html` + inline JavaScript (geen destructieve acties uitgevoerd bij documentatie; alleen `backupConfig` GET geverifieerd).


| UI-onderdeel                                           | Mechanisme                                                                                                                            | URL / aanroep                                                                                                                                                                                                        |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backup** (“Download configuration file from module”) | Eén synchrone XHR                                                                                                                     | `GET /api.html?method=backupConfig` — response body is **één JSON-document** (zelfde als wat de browser als `.json` wegschrijft). Voorgestelde bestandsnaam in UI: `IP0300PoE-{ip_met_underscores}-{YYYYMMDD}.json`. |
| **Restore** (“Upload configuration file to module”)    | Geen enkele “restore”-URL: de browser **leest** het backup-JSON lokaal, controleert `device.refNr === "IP0300PoE"`, daarna per kanaal | `GET /api.html?method=saveChannel&ds=<url-encoded descr>&gr=<url-encoded groep>&dimMax=<n>&dimMin=<n>&ch=<id>` — herhaald voor elk element in `channels[]`. Daarna: `GET /api.html?method=setButton&status=0         |
| **Reset** (“Reset configuration to default state”)     | Bevestigingspopup, daarna                                                                                                             | `GET /api.html?method=resetConfig` — tekst in UI: reset naar fabrieksconfig **behalve netwerkinstellingen**.                                                                                                         |


**Backup-JSON-structuur** (observatie op live module):

- `device.refNr` — string, verwacht `"IP0300PoE"` voor restore via deze UI.
- `network` — `dhcp`, `ipaddress`, `subnet`, `gateway` (strings in backup-sample).
- `button` — `status` (`"0"` / `"1"`).
- `channels` — array van `{ id, descr, gr, dimMax, dimMin }` (8 entries op 8-kanaalsmodule).

Voorbeeld-response (let op: kan kamer-/netwerklabels bevatten) opgeslagen in repo: `captures/http_snapshots/2026-05-03_IP0300PoE_10.10.1.40_backupConfig.json`.

**Beveiliging / relevantie:** Zelfde waarschuwing als §2A (geen login op homepage, segmentatie LAN). Nuttig om **UDP/1001**-dimcommando’s te correleren met bekende `status`/`dimMin`/`dimMax`.

### 2C — IP1100PoE (Input Module)

- **Functie:** Inlezen van drukknopschakelaars via Cat5 kabels; koppeling in software naar outputs (relay/dimmer) via `func1` / `func2` per drukknop
- **Aansluitingen:** 8 inputs, telkens 1 paar draden (blauw + wit/blauw van Cat5)
- **Momenteel:** 2 fysieke Cat5-kabels met schakelaars; in de module kunnen daarnaast veel **logische** drukknoppen (IP040x-keten) geconfigureerd staan — zie embedded **getButtons** hieronder
- **12V DC output aanwezig** (functie onbekend)
- **Netwerk:** PoE, bekabeld ethernet
- **IP (installatie Mark):** `10.10.1.50` — **MAC:** `00:24:77:52:AD:AA` (zelfde host als in pcap als UDP/1001-partner van de IPBox; eerdere vermoeden “relay” waren **onjuist**)
- **UDP poort:** 1001 (naar IPBox)

#### Embedded webserver (HTTP, poort 80)

Dezelfde **HTTP/1.0**-stijl als andere controllers: homepage + `api.html`. Geobserveerd op `**http://10.10.1.50/`** (firmware **5.2.4**). UI-titel: **IP1100PoE** — **INPUT MODULE**.


| Onderdeel   | URL / pad           | Inhoud                                                                                                  |
| ----------- | ------------------- | ------------------------------------------------------------------------------------------------------- |
| Home        | `/`                 | Diagnose, Pushbuttons, Detectors, System                                                                |
| Diagnose    | `/diagnose.html`    | Bus-/LED-diagnose, scans (`startScan`, `startScanButton`, `stopScan`, `getItemValue`, `doLedAction`, …) |
| Drukknoppen | `/pushbuttons.html` | Lijst en configuratie drukknoppen (`getButtons`, scan, save/clear)                                      |
| Detectors   | `/detectors.html`   | Detectoren (`getDetectors`, scan, save/clear)                                                           |
| Systeem     | `/system.html`      | IP/DHCP, `setSettings` (o.a. `nrButLines`, `dimSpeed`), security, backup/reset                          |


**Drukknoppen als JSON (machineleesbaar):**

- **Request:** `GET /api.html?method=getButtons`
- **Response:** JSON-array; elk element o.a.:


| Veld             | Betekenis                                                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `index`          | Volgorde in de lijst                                                                                                                                        |
| `id`             | String-ID van het drukknop-/interface-apparaat (hex-achtig)                                                                                                 |
| `descr`          | Omschrijving                                                                                                                                                |
| `gr`             | Groepnaam                                                                                                                                                   |
| `func1`, `func2` | Objecten met doel-output: `ip` (laatste octet van controller-IP, bv. **30** = `10.10.1.30`, **40** = `10.10.1.40`), `ch` (kanaalindex), `outType`, `action`. **`func1` = directe actie bij indrukken; `func2` = tweede functie / long press** (drempel in seconden) — volledig actiemodel (press/long press/release + dim-transitie + e-mail) in §12.7 |


**Overige `api.html`-methodes (GET, selectie):**


| Domein      | Methodes                                                                                                               |
| ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| Drukknoppen | `buttonScan&waitTime=…`, `saveButton` (body/query zoals UI), `clearBut`, `clearAllBut`                                 |
| Detectoren  | `getDetectors`, `detScanToAdd`, `saveDetector`, `clearDet`, `clearAllDet`                                              |
| Diagnose    | `startScan`, `startScanButton`, `stopScan`, `getItemValue&id=…&prefix=L                                                |
| Systeem     | `getSysSet`, `setIp`, `setSettings&nrButLines=…&dimSpeed=…`, `setButton`, `setSecurity`, `backupConfig`, `resetConfig` |


**Beveiliging / relevantie:** Zelfde LAN-waarschuwing als §2A. `**getButtons`** levert een **read-only** beeld van welke inputs naar welke controller/kanaal wijzen — nuttig naast **UDP**-eventreverse engineering en naast de IPBox REST-inventaris.

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
- **Netwerk (twee fysieke Ethernet-poorten):** de IPBox is **dual-homed**. **Eén poort** zit op het **thuis-/default-LAN** (RFC1918, internet-routeerbaar via je router): daar draait de **REST API** en **webinterface** (TCP **30200**). **De andere poort** zit op het **IPBuilding-VLAN** (**`10.10.1.x`**, L3-segment **`10.10.1.0/24`** in deze installatie): daar loopt de **veldbus** (**UDP/1001**) tussen de IPBox en de veldmodules. Zie §3.0 voor het tweeledige topologiebeeld — er is geen apart “lab-netwerk” als derde semantiek; captures verwijzen naar UniFi/spiegel-**POV**, niet naar een extra IP-plan.
- **IP op het IPBuilding-VLAN:** `10.10.1.1` (voorgeprogrammeerd, vaste waarde op dat segment)
- **IP op het thuis-LAN:** binnen **`192.168.1.0/24`** (exact adres uit router/UniFi). Oudere documentatie en pcaps gebruikten **`192.168.0.185`** op een eerder thuis-segment — niet verwarren met het huidige subnet.
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

### 3.0 Twee netwerken (thuis-LAN en IPBuilding-VLAN)

De installatie heeft functioneel **thuis- vs veldbus-segmenten**; in UniFi kunnen dat **meerdere gedefinieerde LAN/VLAN’s** zijn (Default, eventueel **OLD network**, en **IPBuilding**) — zie §3.3. De IPBox is **dual-homed** over minstens twee van die segmenten (REST vs `10.10.1.1`).

1. **Default / thuis-LAN** — het gewone netwerk van de woning: pc’s, telefoons, **Home Assistant**, andere IoT, en verbinding naar **internet**. **Primair subnet in UniFi:** **`192.168.1.0/24`** (controller toont `192.168.1.1/24`). Hier hangt typisch **één Ethernet-poort** van de IPBox wanneer die op **Default** is aangesloten. Clients spreken de IPBox hier aan op **`http://<thuis-IP-van-IPBox>:30200`**. Daarnaast bestaat in deze site nog een apart legacy-LAN **OLD network** (`192.168.0.0/24`, VLAN **3**) — zie §3.3; daar komt o.a. het eerdere **`192.168.0.185`** REST-adres vandaan wanneer die NIC op dat VLAN hangt.

2. **IPBuilding-VLAN** — apart VLAN waar **de IPBuilding-veldbus** voor deze installatie op **`10.10.1.x`** (subnet **`10.10.1.0/24`**) draait: relay, input en de hier gedocumenteerde dimmer op **`.40`** horen thuis in dit segment. Hier hangt de **tweede** Ethernet-poort van de IPBox. De IPBox gebruikt **`10.10.1.1`** als vast hub-IP op dit VLAN voor **UDP/1001** naar/van die modules. **Aanvulling:** in hetzelfde project komt soms nog een dimmercontroller op **`10.10.0.x`** voor (zie §3.1); dat is een ander `/24`-segment, niet het primaire IPBuilding-VLAN **`10.10.1.x`**.

**Implicatie voor RE en captures:** REST-acties lopen L3 naar het **thuis-IP** van de IPBox; UDP/1001 op het veld zie je tussen **`10.10.1.1`** en de controllers. Als een pcap alleen één van beide paden toont, zegt dat iets over **mirror-POV**, niet over “een ander lab-netwerk”.

### 3.1 Logische adressen op het IPBuilding-segment (overzicht)

```
Subnet 10.10.1.x
  10.10.1.1    — IPBox (IP0000X)          [gateway/controller]
  10.10.1.30   — IP200PoE / IP0200PoE relay controller MAC: 00:24:77:52:AC:BE [UDP/1001 + HTTP/80]
  10.10.1.40   — IP0300PoE (8× 0-10V in web-UI) [UDP/1001 + HTTP/80]
  10.10.1.50   — IP1100PoE input module MAC: 00:24:77:52:AD:AA [UDP/1001 + HTTP/80]

Subnet 10.10.0.x (dimmers)
  10.10.1.40   — IP0300PoE dimmer controller MAC: 00:24:77:52:9E:A8 [UDP/1001 + HTTP/80]

IP040x drukknop interfaces — geen eigen IP (serieel op Cat5 bus naar IP1100PoE)
```

### 3.2 UniFi — fysieke switchpoorten (mirror / sniff-voorbereiding)

> **Snapshot:** 2026-05-03, afgelezen uit UniFi Network (site `default`) via client-uplinkvelden (`last_uplink_name`, `last_uplink_mac`, `last_uplink_remote_port`). Poortnummers zijn **UniFi / switch-fysiek** (1-based zoals op het apparaat), niet TCP/UDP-poorten. Na verplaatsen van kabels opnieuw controleren in UniFi.

**Doel:** weten **waar** te mirrorren of span te zetten (switchpoort) en welke **MAC/IP** je op die poort verwacht bij Wireshark/tcpdump.


| UniFi-apparaat          | Switch MAC          | Poort  | Client (UniFi-naam)                      | MAC                 | Laatste IP / VLAN-notitie                                            |
| ----------------------- | ------------------- | ------ | ---------------------------------------- | ------------------- | -------------------------------------------------------------------- |
| **Unify Switch 16**     | `b4:fb:e4:54:83:7c` | **7**  | oki-mc362 (MC362)                        | `00:25:36:1e:5f:55` | `192.168.1.11` (Default); *geplande dev-sniff / gateway-aansluiting* |
| **Unify Switch 16**     | idem                | **12** | IPBuilding 8x 0-10V output module        | `00:24:77:52:9e:a8` | `10.10.1.40` (IPBuilding)                                            |
| **Unify Switch 16**     | idem                | **13** | IPBuilding input module (IP1100PoE)      | `00:24:77:52:ad:aa` | `10.10.1.50` (IPBuilding)                                            |
| **Unify Switch 16**     | idem                | **14** | IPBuilding 24x output module (IP0200PoE) | `00:24:77:52:ac:be` | `10.10.1.30` (IPBuilding)                                            |
| **Cloud Gateway Ultra** | `6c:63:f8:1f:a3:ab` | **4**  | IPB IPBox (REST-kant / thuis-LAN)        | `00:30:18:00:49:3c` | `192.168.0.185` (UniFi-export **2026-05-03**; thuis-LAN is thans **`192.168.1.0/24`** — IP in UniFi herbekijken) |


**Tweede IPBox-unit (productie-MAC, Jetway):** client **IPBuilding box** — MAC `00:30:18:00:49:3b`, laatste bekende IP `10.10.1.1`, VLAN *IPBuilding*, laatste uplink **Unify Switch 16** (zelfde switch MAC). Op het moment van bovenstaande export ontbrak `last_uplink_remote_port` in de controller-clientpayload (oudere `last_seen`); poort in UniFi UI verifiëren onder *Clients / Devices → switch poorten*.

**Sniffing:** mirror de poort die het verkeer bevat dat je nodig hebt: **12–14** = native **IPBuilding** (`10.10.1.x`); **15** = IPBuilding met aangepaste trunk (`forward: customize`), typisch IPBox-veldbus-uplink; **8** = native **OLD network** (`192.168.0.x`) — sluit aan bij UniFi-client **IPB IPBox** op **`192.168.0.185`** (zie §3.3); **7** = **Default** (`192.168.1.x`). Voor IPBox-hub UDP/1001 op `en7` is de **operator-standaard** meestal **bron 15 → bestemming 7** (**`7←15`**); **`7←14`** is alleen een **relay-leg-alternatief** — zie `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md` en `resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md`. Voor `**tcpdump` op de Cloud Gateway** zelf: `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md` → *Cloud Gateway Ultra — tcpdump*.

**Opmerking:** De capture `traffic between controller an IPbox.pcapng` toonde UDP/1001 tussen IPBox en **10.10.1.50** — dat is de **IP1100PoE** (MAC `00:24:77:52:AD:AA`), niet de relay op `.30`.

### 3.3 UniFi Network — live netwerken en poortmapping (MCP)

Agents kunnen de **UniFi Network MCP** (`project-0-IPBuilding Gateway-unifi-network`) gebruiken om actuele **L3-netwerken**, **VLAN-ID’s** en **switch-poortnative VLAN’s** te lezen zonder de UI handmatig te kopiëren. Workflow: `unifi_tool_index` (optioneel `search`/`category`) → `unifi_execute` met o.a. **`unifi_list_networks`**, **`unifi_list_devices`**, **`unifi_get_switch_ports`**, **`unifi_list_clients`**.

**Networks (site `default`, `unifi_list_networks`, 2026-05-14):**

| UniFi-naam   | VLAN tag | IP-subnet (controller) | Relevantie |
| ------------ | -------- | ---------------------- | ------------ |
| **Default** | *(geen apart VLAN in export; primair thuis-LAN)* | `192.168.1.1/24` | Internet aan; DHCP `.6`–`.254` |
| **IPBuilding** | **2** | `10.10.1.1/24` | Veldcontrollers + IPBox-hub `10.10.1.1`; `internet_access_enabled`: **false**; DNS-domain `ipb` |
| **OLD network** | **3** | `192.168.0.1/24` | Legt **legacy `192.168.0.x`** (o.a. eerdere **IPBox REST `192.168.0.185`**) uit; apart corporate VLAN naast Default |

**Unify Switch 16** (`b4:fb:e4:54:83:7c`, management `192.168.1.126` op Default) — **poort overrides** (`unifi_get_switch_ports`, zelfde datum):

| Poort | Native UniFi-netwerk | `forward` (indien gezet) | Typische capture-POV |
| ----- | --------------------- | ------------------------- | ---------------------- |
| **7** | Default (`192.168.1.x`) | `all` | Thuis-LAN / trunk-achtig gedrag; o.a. MC362 |
| **8** | **OLD network** (`192.168.0.x`) | `native` | Past bij UniFi-client **IPB IPBox** MAC `00:30:18:00:49:3c` → **`192.168.0.185`** (laatste `last_seen` in export kan achterlopen) |
| **12–14** | IPBuilding (`10.10.1.x`) | `native` | Dimmer / input / relay |
| **15** | IPBuilding | `customize` | IPBox **veldbus**-been (o.a. golden-runbook mirror-bron) |

Bovenstaande waarden **verouderen** zodra je poortprofielen of kabels wijzigt — altijd even opnieuw via MCP of UniFi UI bevestigen vóór mirror/capture.

---

## 4. SYSTEM ARCHITECTURE

### Huidige architectuur (MET IPBox)

```
[Drukknop]
    │ (potentiaalvrij contact)
[IP040x interface] ── Cat5 bus ──► [IP1100PoE input module]
                                          │ UDP/1001 ▲▼ (IPBuilding-VLAN)
                                    [IP0000X IPBox]   ← REST :30200 (thuis-/default-LAN) ← [Home Assistant]
                                          │ UDP/1001 ▲▼
                              [IP200PoE] + [IP0300PoE]
                                   │ flat cable            │ flat cable
                              [IP0201 relays]        [IP0302 dimmers]
                                   │ 230V                   │ 0-10V
                              [Lichten/apparaten]    [Dimmable lichten]
```

**Opmerking:** De IPBox heeft **twee** netwerkinterfaces: REST/web op het **thuis-LAN**, veldbus op het **IPBuilding-VLAN** (zie §3.0). Relay- (`10.10.1.30`, §2A), dimmer- (**IP0300PoE**, §2B) en inputmodule (**IP1100PoE**, `10.10.1.50`, §2C) exposeeren elk **HTTP/80** (embedded UI + `api.html`). Die stromen staan niet in het diagram maar zijn beschikbaar op het LAN.

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


| Method | Endpoint         | Parameters                  | Beschrijving                              |
| ------ | ---------------- | --------------------------- | ----------------------------------------- |
| GET    | `/comp/items`    | `types` (kommalijst)        | Alle devices, optioneel gefilterd op type |
| GET    | `/action/action` | `id`, `actionType`, `value` | Stuur commando naar device                |


### 5.2 actionType waarden


| actionType | Waarde | Beschrijving       |
| ---------- | ------ | ------------------ |
| `ON`       | —      | Relay aan          |
| `OFF`      | 0      | Relay/dimmer uit   |
| `DIM`      | 0-100  | Dimmer naar waarde |


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


| Constante            | Waarde | Beschrijving           |
| -------------------- | ------ | ---------------------- |
| TYPE_RELAY           | 1      | Relay output (aan/uit) |
| TYPE_DIMMER          | 2      | Dimmer (0-100%)        |
| TYPE_DMX             | 3      | DMX licht              |
| TYPE_ENERGY_COUNTER  | 40     | Energieteller          |
| TYPE_ENERGY_METER    | 41     | Energiemeter           |
| TYPE_BUTTON          | 50     | Drukknop input         |
| TYPE_TEMPERATURE     | 51     | Temperatuursensor      |
| TYPE_DETECTOR        | 52     | Detector               |
| TYPE_ANALOG_SENSOR   | 53     | Analoge sensor         |
| TYPE_KMI             | 54     | KMI weerstation        |
| TYPE_WEATHER_STATION | 55     | Weerstation            |
| TYPE_TIME            | 56     | Tijdmodule             |
| TYPE_LED             | 60     | LED strip              |
| TYPE_ACCESS_READER   | 70     | Toegangslezer          |
| TYPE_ACCESS_KEY      | 80     | Toegangssleutel        |
| TYPE_SPHERE          | 100    | Scene/sfeer            |
| TYPE_TEMP_SPHERE     | 101    | Tijdelijke scene       |
| TYPE_PROG            | 102    | Programma              |
| TYPE_ACCESS_CONTROL  | 103    | Toegangscontrole       |
| TYPE_SCRIPT          | 150    | Script                 |
| TYPE_REGIME          | 200    | Regime                 |


### 5.5 Device Kinds


| Waarde | Beschrijving         |
| ------ | -------------------- |
| 1      | Light (licht)        |
| 2      | Socket (stopcontact) |
| 3      | Automation           |
| 4      | Lock                 |
| 5      | Fan                  |
| 6      | Valve                |
| 7      | Temperature          |
| 8      | Not Applicable       |


### 5.6 IPBox WebConfig — Relay Provisioning via GUI (HAR 2026-05-18)

> **Bron:** `01-36.har` — gebruiker opent relay lijst in IPBox webgui, klikt "bewaar". Bevat volledige XHR-trace.

De webgui (ASP.NET MVC, `jQuery 1.7.1`, `SignalR 2.2.0`) praat **niet** rechtstreeks met de relaymodule, maar met **IPBox MVC-endpoints** op poort **30200** onder `/general/Hardware/Relais/…`. De IPBox fungeert als proxy richting veldmodule.

#### 5.6.1 Relays lijst ophalen (`/general/Hardware/Relais/Index`)

De Index-pagina laadt modulelijst uit de IPBox-state. Geen aparte XHR voor de lijst zelf — de HTML bevat de items inline.

#### 5.6.2 Relay-configuratie ophalen (`ImportRelayInfo`)

```
POST /general/Hardware/Relais/ImportRelayInfo
Body (form): ip=10.10.1.30
```

De IPBox haalt output-configuratie **op van de relay module** (veldbus UDP/1001) en retourneert JSON:

```json
[
  {"id":0,"descr":"Keuken LED [30.1.1]","gr":"Keuken",...},
  {"id":1,"descr":"Patio [30.1.2]","gr":"Buitenverlichting",...},
  ...(24 kanalen, id 0–23)...
  {"id":18,"descr":"Keuken rookmelder [30.3.3]","gr":"Keuken",...},
  {"id":23,"descr":"Keuken Ventilatie [30.3.8]","gr":"Keuken",...}
]
```

**Bekende kanaalmappings (live getest 2026-05-19):**
| Device ID | Beschrijving | Relay kanaal | UDP commando |
|----------|-------------|--------------|--------------|
| 18 | Keuken rookmelder [30.3.3] | 18 | `S1800` / `C1800` |
| 23 | Keuken Ventilatie [30.3.8] | 23 | `S2300` / `C2300` |

*IDs 0–23 in de IPBox REST komen overeen met relay-kanalen 0–23 (24 kanalen, IP0200PoE).*

| Veld       | Betekenis                                  |
| ---------- | ------------------------------------------ |
| `id`       | Kanaalindex (0-based)                      |
| `descr`    | Kanaalomschrijving (projectlabel)          |
| `gr`       | Groepsnaam                                 |
| `status`   | `0` = uit, `1` = aan                       |
| `pulse`    | Pulsduur (firmware-eenheden)               |
| `lock`      | Lock-bitstring (8 ASCII-hex tekens)         |
| `lockTimer` | Lock-timer (minuten)                       |

**Respons:** `200 OK`, `application/json; charset=utf-8`, body ≈ 2663 bytes.

#### 5.6.3 Relay-configuratie bewaren (`UpdateRelay`)

```
POST /general/Hardware/Relais/UpdateRelay
Body (form): ip=10.10.1.30&outputs=[...24 kanalen...]&updateModule=1
```

De `outputs`-parameter bevat een **URL-encoded JSON-array** met per kanaal:

```json
{
  "ID": 547,         // REST comp/item ID (547–570 voor 24 kanalen)
  "CH": 0,           // kanaalindex (0–23)
  "Description": "Keuken LED [30.1.1]",
  "Group": "Keuken",
  "Pulse": 0,
  "Lock": "00000000", // 8-char hex lock-bits
  "LockTimer": 0
}
```

**Mechanisme:** IPBox stuurt via veldbus (UDP/1001) naar `10.10.1.30` — zie `gateway/payloads/relay.py` voor het veldbus-commandoformaat.

#### 5.6.4 Overzicht WebConfig GUI-endpoints (relay)

| Method | Endpoint                              | Body/Params                        | Werking                          |
| ------ | ------------------------------------- | ---------------------------------- | ------------------------------- |
| GET    | `/general/Hardware/Relais/Index`       | —                                  | Pagina met modulelijst (inline)  |
| GET    | `/general/Hardware/Relais/RelayDetail` | `ip=10.10.1.30`                   | Relay-detailpagina laden         |
| POST   | `/general/Hardware/Relais/ImportRelayInfo` | `ip=<module-ip>`                  | Haalt output-config uit module   |
| POST   | `/general/Hardware/Relais/UpdateRelay` | `ip=<module-ip>&outputs=<json>&updateModule=1` | Bewaart output-config naar module |
| POST   | `/general/Hardware/Relais/DeleteRelays` | `ips=<ip1>,<ip2>,…`               | Verwijdert module(s)             |
| GET    | `/general/Hardware/Relais/NewRelay`    | —                                  | Nieuwe relay-module toevoegen    |

**Opmerking:** deze endpoints leven op de **webgui-laag** (`/general/…`), **niet** op de REST API (`/api/v1/…`). De REST API (`/comp/items`, `/action/action`) is het **northbound-protocol** voor Home Assistant en derden. De WebConfig GUI is puur de IPBox-configuratie-interface.

**Signaalroute bij save (volledig pad):**

```
Browser → IPBox :30200 POST /general/Hardware/Relais/UpdateRelay
  → IPBox proxyt naar veldbus → relay 10.10.1.30 UDP/1001
  → relay bevestigt → IPBox retourneert HTML/200 aan browser
```

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

### 6.4 Commandopakketten (Relay → UDP/1001)

**Geverifieerd 2026-05-19 via directe UDP/1001 tests:**

De relay module op `10.10.1.30` verwacht **raw ASCII commando's** op UDP/1001 — geen envelope of prefix-byte.

**Format:** `[SCTP]{channel:02d}00` — 5 bytes ASCII

| Brief | Actie | Voorbeeld |
|-------|-------|-----------|
| `S`   | ON    | `S1800` → kanaal 18 aanzetten |
| `C`   | OFF   | `C1800` → kanaal 18 uitzetten |
| `T`   | TOGGLE| `T1800` → kanaal 18 omzetten |
| `P`   | PULSE | `P1800` → kanaal 18 puls |

**Respons:** statusregel `I000{channel:02d}{state}` bijv. `I000180100` (aan) of `I000180000` (uit).

**Opmerking:** eerdere documentatie hypothetiseerde een `[pfx]J` envelope — die blijkt **niet** te werken op UDP/1001. De module accepteert enkel raw ASCII.

Dimmer- en input-veldbus: zie [2026-05-17_dimmer_I0154xxx_full_decode.md](evidence/2026-05-17_dimmer_I0154xxx_full_decode.md) en [2026-05-17_ip1100_input_payload_decode.md](evidence/2026-05-17_ip1100_input_payload_decode.md) (input events: [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md)). Oudere poll-only pcap §6.5 hieronder blijft historische referentie.

### 6.5 Pcap bestand

**Bestandsnaam:** `traffic between controller an IPbox.pcapng`  
**Locatie:** `/IPBuilding/` map in Google Drive  
**Inhoud:** Polling verkeer tussen IPBox (10.10.1.1) en **IP1100PoE** (`10.10.1.50`) op UDP/1001. Geen commandopakketten aanwezig in deze capture.

### 6.6 Golden capture workflow (2026-05-03)

Voor de commandodecode en fysieke schakelaars wordt nu een vaste captureworkflow gebruikt:

- **Workflow document:** `resources_and_docs/workflows/IPBUILDING_CAPTURE_WORKFLOW.md`
- **Runbook:** `resources_and_docs/workflows/ipbuilding_golden_runbook.yaml`
- **Orchestrator script:** `ipbuilding_capture_run.py`

Belangrijke punten:

- Log zowel **pcap** als **manifest.jsonl** met exact eventtijdstip per REST-call of fysieke druk.
- Gebruik bij voorkeur 1 mirror-POV; anders dual-capture met NTP-kloksync en manifestmarkers.
- Maak per run een sessiemap met minimaal: `capture.pcapng`, `manifest.jsonl`, `inventory_pre.json`, `runbook.yaml`, `run.log`, `README.txt`.

### 6.7 Fysieke schakelaars: scopegrens

Voor reverse engineering van fysieke schakelaars zijn er twee lagen:

1. **Ethernet-laag (wel in pcap):** IP1100PoE ↔ IPBox via UDP/1001, gecorreleerd met `physical_input` manifestevents en `getButtons` snapshots.
2. **IP040x-buslaag (niet in pcap):** databus tussen IP040x en IP1100PoE op Cat5-bekabeling; vereist aparte hardwareanalyse (bijv. logic analyzer) als wire-level decode nodig is.

---

## 7. BESTAANDE HA INTEGRATIE

**Repository:** [https://github.com/markminnoye/HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding)  
**Type:** Home Assistant Custom Component (HACS compatibel)  
**Taal:** Python (asyncio + aiohttp)

### 7.1 Bestanden


| Bestand          | Functie                                    |
| ---------------- | ------------------------------------------ |
| `api.py`         | REST API client (get_devices, set_value)   |
| `const.py`       | Device type constanten                     |
| `__init__.py`    | Setup, DataUpdateCoordinator (polling 20s) |
| `light.py`       | Licht entities (relay + dimmer)            |
| `switch.py`      | Schakelaar entities                        |
| `button.py`      | Drukknop entities                          |
| `sensor.py`      | Sensor entities                            |
| `scene.py`       | Scene/sfeer entities                       |
| `config_flow.py` | UI configuratie (host + poort)             |


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


| Component                             | IP         | MAC               | Status                                                                             |
| ------------------------------------- | ---------- | ----------------- | ---------------------------------------------------------------------------------- |
| IP0000X IPBox                         | 10.10.1.1  | —                 | Actief, te vervangen                                                               |
| IP200PoE / IP0200PoE relay controller | 10.10.1.30 | 00:24:77:52:AC:BE | Actief; HTTP/80 + UDP/1001                                                         |
| IP0300PoE dimmer controller           | 10.10.1.40 | 00:24:77:52:9E:A8 | Actief; HTTP/80 + UDP/1001                                                         |
| IP1100PoE input module                | 10.10.1.50 | 00:24:77:52:AD:AA | Actief; HTTP/80 + UDP/1001; 2 fysieke Cat5-kabels, meerdere logische knoppen in UI |


### 8.2 Aangesloten loads

- **Relay controller (IP200PoE):** 3 blokken IP0201, elk 8 outputs → 24 relay kanalen
- **Dimmer controller (IP0300PoE):** `10.10.1.40` — **8** logische 0-10V-kanalen in de web-UI.
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

**Primair technisch spoor:** het **UDP/1001** binair protocol tussen IPBox en controllers zodanig begrijpen dat een gateway die rol kan overnemen.

**Kader fase 1 (status 2026-05-22):** UDP/1001 **wire** voor relay, dimmer en input (`B-…E`) is afgerond (5-sprint plan + [Sprint 5 completion](evidence/2026-05-22_sprint5_input_physical_completion.md)). Parallel gedocumenteerd: IPBox REST, embedded HTTP (§2A–C), WebConfig wizards ([RE_WIZARDS_PLAN.md](reference/2026-05-17_RE_WIZARDS_PLAN.md)) als **referentie**. **Niet** doel van de eigen gateway: IPBox **sferen/scenes** en knop→actie-projectlogica nabouwen — dat gaat naar **Home Assistant**; de gateway is veldbus-transport (zie §10.5).

### 9.2 Aanpak — Extra pcap sessies

**Stap 1: Netwerk voorbereiding**

- Wireshark of `tcpdump` draaien op een machine in subnet 10.10.1.x
- Filter: `udp port 1001`

**Stap 2: Acties uitvoeren via IPBox webinterface of REST API** (optioneel: relay via **HTTP** §2A — `sCh` / `cCh` / `tCh`; dimmer §2B — `dCh&ch=N&val=…`; input **read-only** §2C — `getButtons`, om UDP te correleren zonder IPBox)
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


| Hypothese                            | Verificatie                                |
| ------------------------------------ | ------------------------------------------ |
| Byte 5 van response = relay bitfield | Schakel relay 1 aan, kijk of bit 0 wijzigt |
| Commando heeft zelfde 'I' prefix     | Capture commandopakketten en vergelijk     |
| Device ID in bytes 1-2 of 3-4        | Test met verschillende device IDs          |
| Checksum aanwezig                    | Zoek byte die varieert met inhoud          |
| IP0300PoE zelfde protocol            | Capture dimmer controller apart            |


---

## 10. VERVANGINGSPLAN IPBOX

> **Richting bijgewerkt 2026-05-17:** einddoel is een **eigen centrale** op de veldbus (UDP/1001), **zonder** IPBox REST `:30200` als product-API. Architectuur centrale + northbound — zie `docs/superpowers/specs/2026-05-18-gateway-architecture-design.md`. IPBox REST in dit document blijft **referentie** voor RE en bestaande HA-IPBuilding.

### 10.1 Doelarchitectuur — eigen centrale (field bus first)

Een lichtgewicht service die:

- Rechtstreeks praat met alle IPBuilding controllers via **UDP/1001**
- De **hub-rol** van de IPBox op `10.10.1.1` overneemt (of parallel start op eigen hardware)
- Northbound exposeert via **nog te kiezen** protocol (MQTT / Matter / …) — **niet** IPBox REST-clone
- Draait als Docker, HA add-on, of standalone (Raspberry Pi / NUC)

### 10.2 Fasen

| Fase | Beschrijving | Status |
| ---- | ------------ | ------ |
| 1 | RE: UDP/1001 wire (relay/dimmer/input) + correlatie | ✅ Afgerond — [RE_STATE.md](RE_STATE.md), Sprint 5 [completion](evidence/2026-05-22_sprint5_input_physical_completion.md) |
| 1b | Optionele RE: IPBox sferen/moods, input project-flow | ⏸️ Uitgesteld — zie §10.6; waarschijnlijk overgeslagen (HA) |
| 2 | Field-bus library (`gateway/payloads`, `udp_bus`) | ✅ Code + tests; service/registry nog open |
| 3 | Architectuur northbound + product | 📄 Goedgekeurd [2026-05-18-gateway-architecture-design.md](../../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md) |
| 4 | Provisioning | ⏳ **In HA/companion** — geen volledige IPBox-projectdatabase in gateway |
| 5 | Productie: HA Add-on + companion + Matter via HA | ⏳ Volgende implementatiefocus |

### 10.3 Tech stack (voorstel)

```
Python 3.11+
asyncio (UDP/1001)
pydantic (modellen)
# northbound TBD: aiomqtt / Matter SDK / HA custom_component
```

### 10.4 IPBox REST (referentie — geen einddoel)

De bestaande IPBox API (`GET /api/v1/comp/items`, `GET /api/v1/action/action`, poort **30200**) wordt gebruikt voor **capture-correlatie** en documentatie. In de repo: `gateway/rest_shim.py` nabootst die API **alleen als transitie-hulp** (legacy HA-IPBuilding); geen product-API — northbound = eigen `gateway_api.py` (zie architectuurdoc 2026-05-18, [README_gateway.md](../README_gateway.md)).

### 10.5 Gateway vs Home Assistant (geen logica in de gateway)

**Beslissing (2026-05-22):** de vervanger van de IPBox op de veldbus is een **transport-hub**:

- Pollen, commando’s (`S`/`C`/`T`/`P`, dimmer-families), input-events (`B-…E`) decoderen en naar de companion sturen.
- **Geen** opslag of uitvoering van IPBox-**sferen**, scenes, timers of “knop X doet Y+Z” in de gateway-container.

**Home Assistant** (`ipbuilding-open`): entiteiten, automations, scenes, Matter-bridge. Fysieke knop → `button`-event of trigger → gebruiker/HA beslist de actie (niet een tweede IPBox-service-DB).

Architectuur: [2026-05-18-gateway-architecture-design.md](../../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Input architectuur (slave vs autonoom): [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md) § Architectuurdoel.

### 10.6 Volgende sprint (uitgesteld) — IPBox sferen / moods

**Referentie-URL (WebConfig, thuis-LAN):** `http://192.168.0.185/general/Configuration/Moods/Index`  
(Vervang host door actueel IPBox-adres uit router/UniFi indien anders.)

**Scope indien ooit RE:** HTTP/HAR + optioneel correlatie met REST `:30200` — **niet** UDP/1001 veldbus. Doel zou migratie-inzicht zijn, geen gateway-feature.

**Waarschijnlijke keuze:** **overslaan** — sferen en vergelijkbare logica in HA; zie `AGENTS.md` § Volgende sprint (uitgesteld).

---

## 12. CONFIGURATIEMODEL & CENTRALE EENHEID (uit installatiehandleiding v6.0)

> Bron: officieel IPBuilding installatiedocument v6.0 (juli 2012). De **Centrale eenheid** (IP0000B / IP0000) is de directe hardware-voorloper van de IPBox. Het configuratiemodel en de IP-ranges zijn ongewijzigd overgenomen.

### 12.1 Standaard IP-adresindeling — volledig schema

| Module type | IP-bereik | Onze installatie |
|---|---|---|
| Relay control modules (IP0200PoE) | **10.10.1.30 → 10.10.1.39** | `.30` |
| Dimmer control modules (IP0300PoE) | **10.10.1.40 → 10.10.1.49** | `.40` |
| Input modules (IP1100PoE) | **10.10.1.50 → 10.10.1.59** | `.50` |
| Camera's | 10.10.1.70 → 10.10.1.79 | — |
| Barix audio modules | 10.10.1.80 → 10.10.1.89 | — |
| Audio switch box | 10.10.1.90 → 10.10.1.94 | — |
| Router | 10.10.1.254 | — |
| Centrale eenheid / **IPBox** | **10.10.1.1** | `10.10.1.1` |

### 12.2 Configuratievelden per relay-uitgang (24 per IP0200PoE)

| Veld | Type | Omschrijving |
|---|---|---|
| Omschrijving | string | Naam (bv. "Sipk Naomi West 'op'") |
| Groep | string | Groeperingsnaam (bv. "Screens 1ste verdiep") |
| ZB | bool | Zichtbaar in gebruikersinterface |
| SPh | bool | Bedienbaar via SmartPhone/app |
| Vergrendel | bool | Interlock voor rolluikparen (enkel onpare+pare: 1&2, 3&4, …) |
| Puls | int (sec) | Pulsduur in seconden (0 = geen puls; voor poortbediening) |
| Status | AAN/UIT | Huidige stand |

De `descr` en `gr` velden in de embedded `api.html` JSON-response komen rechtstreeks uit Omschrijving/Groep. De `lock` en `pulse` velden in de backup-JSON komen uit Vergrendel/Puls.

### 12.3 Configuratievelden per dim-kanaal (8 per IP0300PoE)

| Veld | Type | Omschrijving |
|---|---|---|
| Omschrijving | string | Naam |
| Groep | string | Groeperingsnaam |
| ZB / SPh | bool | Zichtbaar / SmartPhone |
| Niveau % | 0–100 | Huidig dimniveau |
| **Soft AAN %** | 0–100 | Startniveau bij inschakelen (default **15%**) — lamp gaat eerst naar 15%, dan soft omhoog |
| **Soft UIT %** | 0–100 | Niveau waaronder soft-uit begint (default **70%**) — lamp gaat naar 70%, dan soft naar 0% |
| **Snelheid (msec)** | int | Transitietijd dimmen (default **001** msec) |

Soft AAN/UIT en Snelheid worden als EEPROM-data via de diagnose-software naar de dimmodule geschreven (Download/Upload EEPROM functie). Dit verklaart het zachte dimgedrag dat in captures zichtbaar is.

### 12.4 Ingangscomponenten — ID-prefix en veldstructuur

Elk component op de ingangsbus heeft een uniek hardware-ID. De **eerste letter** bepaalt het type:

| Prefix | Type |
|---|---|
| B | Drukknop (button) |
| V | Verklikkerlampje (indicator LED, 12V uitgang) |
| F | Temperatuursensor |
| L | Analoge ingang (0-10V) |
| A | NC-contact (bewegingsmelder, deurcontact, rookmelder) |

Velden per component in de centrale:
- ID Nummer, Omschrijving, Groep, ZB
- IP (ingangsmodule), Poort (01–08 fysieke ingang op IP1100)
- Type (Relais/Dimmer), IP (doelmodule), Uitgang (1–24 / 1–8), Actie (Toggle / All on / All off)

### 12.5 Autonomiemechanisme IP1100 (master/slave)

**Slave mode** (centrale actief): IP1100 LED brandt continu groen → centrale beslist.  
**Master/autonoom mode** (centrale uitgevallen): IP1100 LED knippert groen → werkt op EEPROM-tabel.

Procedure voor flashen autonomietabel:
1. `buttonIP1100.exe` op centrale genereert `.IPA` bestanden per ingangsmodule (bv. `10.10.1.83.IPA`) op basis van de service-software database.
2. IP-diagnostic → verbinden met IP1100 → Autonomie tab → Inlezen → Open .IPA → Versturen.

Autonomietabel bevat per koppeling: drukknop-ID, type (Relais/Dimmer), doelmodule-IP, uitgang, actie.

**Implicatie voor gateway:** de gateway moet de rol van de centrale overnemen; de IP1100 draait dan in slave-mode naar de gateway. De autonomie-EEPROM in de IP1100 blijft als fallback actief bij gateway-uitval.

### 12.6 Softwarelagen op de Centrale eenheid / IPBox

| Laag | Naam | Functie |
|---|---|---|
| Discovery | DS-manager (v3.54) | Broadcast-scan, MAC→IP koppeling, firmware-upgrade |
| Config-engine | Service software | Configuratie-daemon; mag NIET worden afgesloten; beheert koppelingen, EEPROM |
| Gebruikerslaag | UserInterface | Wat de gebruiker/smartphone ziet |
| Diagnose | IP-diagnostic (v04.04) | Per-module testing; **stopt de service software** terwijl het open is |
| Autonomie-tool | buttonIP1100.exe | Genereert .IPA bestanden uit de database |

**Kritieke beperking:** IP-diagnostic en service software kunnen NIET gelijktijdig draaien. Dit suggereert een single-process architectuur in de firmware; de gateway mag dezelfde beperking niet hebben.

Remote toegang: **Radmin Server** op centrale, poort **4899**.

### 12.7 Drukknop-actiemodel: indrukken / ingedrukt houden (long press) / loslaten

> **Kernbevinding (operator-bevestigd, 2026-06-16):** de **long press** is géén apart veldbus-event. De IP1100PoE stuurt op de veldbus enkel **press** (`01`) en **release** (`00`) randen (`B-…E`, Sprint 5 bevestigd — §2C, [completion](evidence/2026-05-22_sprint5_input_physical_completion.md)). De **IPBox-logicalaag derives** "kort vs lang" door de **duur tussen press en release** te meten en te vergelijken met een per-knop ingestelde **drempel in seconden**. Dit beantwoordt RE-vraag uit gateway-issue [#10](https://github.com/markminnoye/IPBuilding-Gateway/issues/10) (stap 2): *"derived by the hub from press→release duration (timing threshold)"*.

In de IPBox WebConfig/service-software is per drukknop het volgende actiemodel instelbaar. Dit is de **referentie** voor wat een gebruiker vandaag van de IPBox verwacht; in onze oplossing hoort deze logica in **Home Assistant** (zie §Implicatie hieronder), niet in de gateway.

**Acties bij het indrukken van de drukknop** (op de `press`-rand)

- **Eerste functie** (directe actie bij indrukken):
  - **Actief** (bool)
  - **Doel** — in IPBuilding via ruimte → device; in onze oplossing een willekeurige entity/target
  - **Actie** — `aan` / `uit` / `toggle`; bij een dimmer-doel ook **dimmen** met **Geleidelijke overgang 1 ms – 250 ms**
  - **Aantal minuten actie aanhouden** (auto-off timer; default *nvt*)
- **Tweede functie** (= **long press** / ingedrukt houden):
  - **Actief** (bool)
  - **Aantal seconden ingedrukt** — drempel: **0,5 · 1 · 1,5 · 2 · 2,5 · 3 · 4 · 5** seconden
  - **Doel**
  - **Actie** — `aan` / `uit` / `toggle`; bij dimmer ook **dimmen** + **Geleidelijke overgang 1 ms – 250 ms**
  - **Aantal minuten actie aanhouden** (default *nvt*)

**Acties bij het loslaten van de drukknop** (op de `release`-rand)

- **Actief** (bool)
- **Doel**
- **Actie** — `aan` / `uit` / `toggle`; bij dimmer ook **dimmen** + **Geleidelijke overgang 1 ms – 250 ms**
- **Aantal minuten actie aanhouden** (default *nvt*)

**E-mail**

- `geen email` **of** een te kiezen **e-mailgroep** (notificatie bij de drukknopactie).

**Afleiding kort vs lang (zoals IPBox het doet):**

1. `press` (`01`) → start timer; voer eventueel **Eerste functie** uit (directe actie).
2. Als `release` (`00`) komt **vóór** de drempel `aantal seconden ingedrukt` → het was een **korte druk** (Eerste functie / release-actie).
3. Als de knop langer ingedrukt blijft dan de drempel → **Tweede functie** (long press) vuurt.
4. `release` → voer eventueel de **release-actie** uit.

**Implicatie voor onze oplossing (gateway + HA):**

- **Geen extra veldbus-RE nodig** voor long-press *detectie*: de wire levert al press/release; de timing-afleiding is een softwarekwestie.
- **Detectie** (press→release-duur → `press` / `long_press` / `release`) hoort in de **gateway** of in **HA**; de gateway forwardt deze acties northbound op WS `button_event` (`docs/api/websocket.md`).
- **Actie-koppeling** (knop → doel/dimwaarde/transitie/auto-off/e-mail) hoort in **Home Assistant** (automations/scenes), conform `ARCHITECTURE.md` — **niet** in de gateway als tweede project-DB.
- Te beslissen met een agent (later): drempel/dim-transitie/auto-off als gateway-config vs. volledig in HA; en of we de IPBox-velden (`func1`/`func2`, dim-transitie, hold-minuten) bij migratie willen importeren.

---

## 11. OPENSTAANDE VRAGEN


| #   | Vraag                                                                     | Prioriteit                                                        |
| --- | ------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| 1   | Volledig UDP commandoprotocol decoderen                                   | — *(relay/dimmer/input wire afgerond 2026-05-22; scenes/autonoom modus open)* |
| 2   | IP1100PoE-adres: `**10.10.1.50**` (embedded HTTP + MAC, zie §2C)          | — *(opgelost)*                                                    |
| 3   | Functie van 12V DC output op IP1100PoE en IP0300PoE                       | 🟢 Laag                                                           |
| 4   | Pcap-UDP-partner **10.10.1.50** = **IP1100PoE**, niet de relay op `.30`   | — *(opgelost)*                                                    |
| 5   | Protocol voor IP1100PoE input events (hoe stuurt module drukknop events?) | — *(wire: `B-…E` naar hub bevestigd 2026-05-22; zie [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md))* |
| 6   | Ondersteunt IPBox WebSocket of events voor realtime updates?              | 🟡 Middel                                                         |
| 7   | Functie van de 8-kanaals 12VDC output op IP0300PoE                        | 🟢 Laag                                                           |
| 8   | Zijn er meerdere subnets of is 10.10.0.x ook bereikbaar?                  | 🟡 Middel                                                         |
| 9   | Hoe worden scenes/sferen in IPBox WebConfig/REST gerepresenteerd?          | ⏸️ Uitgesteld — §10.6; **niet** in gateway — HA scenes |
| 10  | Maximal aantal devices per controller?                                    | 🟢 Laag                                                           |
| 11  | Is wire-level protocol op IP040x↔IP1100 bus nodig (naast Ethernetlaag)?   | 🟡 Middel — aparte scope, niet in standaard LAN-pcap              |
| 12  | Hoe definieert IPBox de actie na `B-…E` (project vs module `func1`)?       | 🟢 Laag voor product — wire + architectuur gedocumenteerd; **eigen gateway:** events naar HA, geen IPBox-project-DB — [completion § Architectuurdoel](2026-05-22_sprint5_input_physical_completion.md#architectuurdoel) |
| 13  | Long press: apart veldbus-event of door hub afgeleid uit press→release-duur? | — *(opgelost 2026-06-16: hub-afgeleid uit timing; geen extra veldbus-RE nodig — zie §12.7 + gateway-issue [#10](https://github.com/markminnoye/IPBuilding-Gateway/issues/10))* |


---

*Document gegenereerd: 2026-05-01 | Bijgewerkt: 2026-05-22 (Fase 1 wire af, gateway=transport, sferen uitgesteld) | Canonieke RE-status: [RE_STATE.md](RE_STATE.md)*