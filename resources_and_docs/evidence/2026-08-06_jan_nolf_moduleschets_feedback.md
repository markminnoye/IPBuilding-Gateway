# Jan Nolf — moduleschets, WebUI & Diagnostic (2026-08-06)

Last updated: 2026-08-06

**Bron:** Spark mail van Jan Nolf (`jan@nolfvdh.be`)  
- `112173` — tekstantwoord op Mark’s vragen (17:21)  
- `112174` — zelfde thread + bijlagen (“Nu met bijlagen 😉”, 17:22)  
Subject: *RE/FW: integratie IPBuilding in HA — moduleschets, EEPROM’s & WebUI*

**Assets:** [assets/2026-08-06_jan_nolf_moduleschets/](assets/2026-08-06_jan_nolf_moduleschets/)  
OCR-transcripts: `ocr_*.txt` in dezelfde map.

**Vragen van Mark (samenvatting):**
1. Korte kast-/moduleschets (IP, type, #kaarten, roughly wat erop zit)
2. Screenshots gateway WebUI (volledige apparaten-/kanaallijst, incl. inputs)
3. EEPROM/IPA-dump via IP-diagnostic voor `.30` / `.31` / `.32` / `.42` (niet via module-HTTP)

---

## 1. Antwoorden van Jan (tekst)

### 1.1 Moduleschets

| IP | Type (Jan) | Kaarten | Rough inhoud |
|----|------------|---------|--------------|
| `10.10.1.30` | relaisstuur IP0200 | **3×8** | zie Relaisinterfaces-printscreen |
| `10.10.1.31` | relaisstuur IP0200 | **1×8** | **leeg** |
| `10.10.1.32` | relaisstuur IP0200 | **1×8** | zie printscreen; **niet op DIN-foto** (hangt in tuinhuis) |
| `10.10.1.42` | DIM IP0300 | **1×4** | zie Dim interfaces-printscreen |
| `10.10.1.55` | input | **3 buslijnen**: beneden / boven / tuinhuis | zie drukknop-printscreens |

### 1.2 EEPROM / diagnostic

> *“Een eeprom-dump buiten de inputmodule is niet mogelijk. Als ik deze via het diagnostic-programma inlees, dan krijg ik enkel de statusuitgangen.”*

- Input IPA (`.55`) had hij eerder al gestuurd — blijft de enige EEPROM-bron.
- Relays/dimmer: **geen** IPA via Diagnostic Tool; alleen live AAN/UIT / status UI.

### 1.3 Gateway WebUI

Screenshots van gateway **v1.6.0** (instance `1258f4ac408845bc90f66d336842fcf3`) — zie §3.  
**Geen** input-/drukknop-slots zichtbaar in de geleverde WebUI-shots.

---

## 2. Foto `IMG_2763` — oudere installatie

Asset: [IMG_2763.jpeg](assets/2026-08-06_jan_nolf_moduleschets/IMG_2763.jpeg)

DIN-kast (kelder/wijnkelder). Leesbare faceplates:

| Rij | Wat zichtbaar | Interpretatie |
|-----|---------------|---------------|
| Boven | Lange rijen **discrete elektromagnetische relais** (transparante behuizingen) | Expansie-relaiskaarten (past bij Jan’s “3×8” op `.30`), niet de compacte PoE-webmodules van het lab |
| Midden | PCB met spoelen/condensatoren + faceplate **“IPBuilding 8x 0-10 VOLT OUTPUTMODULE”** | Oudere 0-10V-outputmodule (lab-dimmer heet in moderne UI ook “8 × 0-10V”, maar hier aparte faceplate + geen module-HTTP) |
| Onder | **“8 channel INPUT MODULE incl. Autonomy & onlodetection”** + **twee× “24 x OUTPUTMODULE”** | Input + twee 24-kanaals output-controllers in de kast (= waarschijnlijk `.30` en `.31`; `.32` zit elders) |

**Waarom “ouder” (jouw observatie klopt):**

1. **Geen moderne module-webstack** — eerder al: `api.html` / `backupConfig` doen niets op Jan’s modules.
2. **Diagnostic Tool Ver 03.03** + “Relais stuurmodule - Versie: **3.0**” ([diagnostic.png](assets/2026-08-06_jan_nolf_moduleschets/diagnostic.png)) — pre-web, alleen status/bediening.
3. **Fysieke opbouw**: losse relaisrails + aparte 0-10V-faceplate + “Autonomy & onlodetection” op input — typisch Gen-pre-PoE / pre-embedded-HTTP.
4. Config loopt via **IPBuilding desktop** (“hardware configuratie”, XP-era UI), niet via module-browser.

Faceplate-tekst “24 × OUTPUT MODULE” komt ook op moderne IP0200PoE voor ([IPBUILDING_KNOWLEDGE §2A](../IPBUILDING_KNOWLEDGE.md)); de **combinatie** met Diagnostic 3.0 + geen HTTP + discrete relaiskaarten is het sterke signaal voor een oudere generatie.

---

## 3. Gateway WebUI vs IPBuilding-config (gat-analyse)

Gateway add-on **v1.6.0**. Assets:  
[gateway10.10.1.30.png](assets/2026-08-06_jan_nolf_moduleschets/gateway10.10.1.30.png),  
[gateway10.10.1.32_42.png](assets/2026-08-06_jan_nolf_moduleschets/gateway10.10.1.32_42.png).

| Module | In IPBuilding UI | In gateway WebUI | Gat |
|--------|------------------|------------------|-----|
| `.30` relay | **23/24** namen gevuld (rij 17 leeg) | **8** kanalen: 0–3, 6–9 (ch6=`wc`) | mist ~15 actieve + ch4/5 |
| `.31` relay | bestaat (leeg volgens Jan) | **niet** op screenshots | ontbreekt in huidige `devices.json`/UI |
| `.32` relay | 1 kanaal: *TL tuinhuis* | 1 kanaal: `Kanaal 0` | naam/room ontbreekt |
| `.42` dimmer | **4** kanalen: zithoek, lichtstraat, badkamer, slk | **2** kanalen: 0 + 2 | mist ch1 + ch3 |
| `.55` input | ~60 NO-contacten, poort 01/02/03 | **niet zichtbaar** | drukknoppen ontbreken in companion |

Dit verklaart eerdere feedback (Aug 3): “niet alle relaisuitgangen” + “geen drukknoppen” — de gateway-config is een **partiële** restore uit IPA/import, geen volledige installatie-spiegel.

---

## 4. Kanaalnamen uit IPBuilding Relaisinterfaces / Dim

Bron: desktop “IPBuilding hardware configuratie” — OCR + visuele check.  
UI-nummers zijn **1-based**; gateway/UDP gebruiken meestal **0-based** (`UI n` ↔ `ch n-1`).

### 4.1 `10.10.1.30` — Relaisinterfaces

Asset: [10.10.1.30.png](assets/2026-08-06_jan_nolf_moduleschets/10.10.1.30.png)

| UI # | Omschrijving (OCR, licht gecorrigeerd) | Groep |
|------|----------------------------------------|-------|
| 1 | Bediening poort | Poort |
| 2 | Verlichting trap | Verlichting |
| 3 | Verlichting kamer jas | Verlichting |
| 4 | Verlichting kamer i… | Verlichting |
| 5 | Verlichting zolder | Verlichting |
| 6 | Verlichting voordeur kant … | Verlichting |
| 7 | Ledverlichting keuken | Verlichting |
| 8 | Verlichting keuken | Verlichting |
| 9 | Verlichting eetplaats | Verlichting |
| 10 | Verlichting bureau Jan | Verlichting |
| 11 | Verlichting berging | Verlichting |
| 12 | Verlichting kamer 2 | Verlichting |
| 13 | Spotsterras | Verlichting |
| 14 | Verlichting bureau sara | Verlichting |
| 15 | Verlichting toilet | Verlichting |
| 16 | Verlichting voordeur kant L… | Verlichting |
| 17 | *(leeg)* | — |
| 18 | Verlichting keukenpilaar | Verlichting |
| 19 | Wandverlichting boven | Verlichting |
| 20 | Verlichting voordeur buiten | Verlichting |
| 21 | Ventilatie toilet beneden | Ventilatie |
| 22 | Inbouwspot achterdeur | Verlichting |
| 23 | Verstraler oversteek | Verlichting |
| 24 | Verlichting garage | Verlichting |

Gateway ch6=`wc` ↔ waarschijnlijk UI #15 *Verlichting toilet* (of #21 ventilatie) — **mapping bevestigen** bij Jan; 0-based ch6 = UI #7 (ledverlichting keuken) als strikte index. De huidige gateway-namen zijn grotendeels defaults → **niet** 1:1 met Relaisinterfaces.

### 4.2 `10.10.1.32` — Relaisinterfaces

Asset: [10.10.1.32.png](assets/2026-08-06_jan_nolf_moduleschets/10.10.1.32.png)

| UI # | Omschrijving | Groep |
|------|--------------|-------|
| 1 | TL tuinhuis | Verlichting |
| 2–24 | leeg | — |

### 4.3 `10.10.1.42` — Dim interfaces

Asset: [10.10.1.42.png](assets/2026-08-06_jan_nolf_moduleschets/10.10.1.42.png)

| UI # | Omschrijving | Groep |
|------|--------------|-------|
| 1 | zithoek | dim |
| 2 | lichtstraat | dim |
| 3 | badkamer | dim |
| 4 | slk | dim |
| 5–8 | leeg | — |

Past bij Jan’s “1×4”. Gateway mist ch1/ch3 → companion mist minstens *lichtstraat* en *slk*.

### 4.4 `10.10.1.55` — Ingangsmodule (NO contact)

Assets: [input1.png](assets/2026-08-06_jan_nolf_moduleschets/input1.png), [input2.png](assets/2026-08-06_jan_nolf_moduleschets/input2.png), [input3.png](assets/2026-08-06_jan_nolf_moduleschets/input3.png)

- Alle rijen: IP **`10.10.1.55`**
- **Poort 01** ≈ beneden (garage, berging, keuken, living, …)
- **Poort 02** ≈ boven (gang boven, Jens, slk1/slk2, …)
- **Poort 03** ≈ tuinhuis (links/rechts)
- IDs: lange hex-strings (`B01…`) — zelfde familie als eerdere `.55.IPA`

Volledige OCR in `ocr_input{1,2,3}.txt` — bruikbaar voor latere button→entity naming in companion.

---

## 5. Diagnostic Tool (geen EEPROM)

Asset: [diagnostic.png](assets/2026-08-06_jan_nolf_moduleschets/diagnostic.png)

- Titel: **IPBuilding - Diagnostic Tool [Ver: 03.03]**
- Module: `10.10.1.31`
- Kop: **Relais stuurmodule - Versie: 3.0**
- UI: 24× AAN/UIT + Vergr. + Puls — **geen** dump/export-knop zichtbaar

Conclusie: op deze generatie levert Diagnostic alleen live relay-IO; EEPROM-export blijft beperkt tot wat de input-IPA-route eerder gaf.

---

## 6. Implicaties voor gateway / companion

1. **`devices.json` voor Nolf moet 24 kanalen op `.30`** (en placeholder `.31`), 1 op `.32`, 4 op `.42`, plus input `.55` met buttons — huidige WebUI is te dun.
2. **Namen/rooms** kunnen uit Relaisinterfaces / Dim / Ingangsmodule-screenshots (of IPA) worden gevuld — niet uit EEPROM van relays.
3. **Oudere generatie** = geen `backupConfig` HTTP; discovery/HTTP-identify blijft beperkt; vertrouw UDP + handmatige/IPA-config.
4. **Type-hints:** UI #21 *Ventilatie* → `fan`; #1 *Poort* → mogelijk `cover`/`switch`; rest lights. Dimmer-kanalen blijven `light` (dimmable).
5. Volgende stap richting Jan: bevestigen of gateway ch6=`wc` bewust is; `.31` wel/niet in config; input-module in WebUI tonen na restore.

---

## 7. Config gebouwd (2026-08-06)

**Bestand:** [`reference/devices.nolf.json`](../reference/devices.nolf.json)

| Module | Inhoud |
|--------|--------|
| `.30` relay | 24 kanalen (23 active; ch16 ongebruikt) — namen uit Relaisinterfaces |
| `.31` relay | 8 kanalen, alle `active: false` |
| `.32` relay | ch0 *TL tuinhuis* |
| `.42` dimmer | 4 kanalen: zithoek, lichtstraat, badkamer, slaapkamer |
| `.55` input | **60** pushbuttons (NO-contact rijen 1–60 uit screenshots) |

**Inputs:** screenshots tonen rijen **1–60** (niet 42). Bus: poort 01→channel 0 (38), 02→1 (20), 03→2 (2). Alle 16 IPA-wire-IDs matchen een UI-rij; overige 44 IDs afgeleid uit UI-patroon `B01xxxxxx100000yy0p` (+ suffix `30` waar IPA ontbreekt).

**Voor Jan:** Web UI → *Restore from backup* → dit bestand. Daarna companion herladen; knop→actie blijft in HA.

---

## 7. Bestandsindex

| Bestand | Inhoud |
|---------|--------|
| `IMG_2763.jpeg` | DIN-kast foto (oudere hardware) |
| `10.10.1.30.png` | Relaisinterfaces `.30` (24 rijen) |
| `10.10.1.32.png` | Relaisinterfaces `.32` (TL tuinhuis) |
| `10.10.1.42.png` | Dim interfaces `.42` (4 kanalen) |
| `input1.png` / `input2.png` / `input3.png` | Ingangsmodule NO-contacten `.55` |
| `diagnostic.png` | Diagnostic 03.03 op `.31` — geen EEPROM |
| `gateway10.10.1.30.png` | Gateway WebUI `.30` (8 kanalen) |
| `gateway10.10.1.32_42.png` | Gateway WebUI `.32` + `.42` |
| `jan_feedback_112173.txt` | Tekstantwoord Jan |
| `ocr_*.txt` | Tesseract OCR van bovenstaande shots |
