# RE_WIZARDS — Configuratie-stack analyse (22:52)

**Capture:** `22-52.har` + `22:52.pcapng` (1048 pakketten, ~47s, en7 VLAN-mirror)  
**Sessie:** IPBox WebConfig "Instellingen" → navigatie door alle config-secties  
**Datum:** 2026-05-17

---

## 1. HAR — Gepagineerde Configuratie-URLs

De HAR bevat **9 pagina's** (page timings in ms):

| # | URL | Laad-duur | Route |
|---|-----|-----------|-------|
| 1 | `/general/Configuration/Output/Index` | 108 ms | Uitgangen |
| 2 | `/general/Configuration/Pushbuttons/Index` | 392 ms | Drukknoppen |
| 3 | `/general/Configuration/Moods/Index` | 338 ms | Sferen |
| 4 | `/general/Configuration/Detectors/Index` | 5686 ms | Detectoren |
| 5 | `/general/Configuration/Programmations/Index` | 6847 ms | Programmeerbaar |
| 6 | `/general/Configuration/Mail/Index` | 1219 ms | Mail/notificatie |
| 7 | `/general/Configuration/TouchLayout/Index` | 6816 ms | Touch-panel layout |
| 8 | `/general/Configuration/Output/Index` | 121 ms | (terug naar Uitgangen) |
| 9 | `/general/Configuration/Output/Usages` | 168 ms | Uitgangen → Gebruik |

**Belangrijk:** dit is puur navigatie-page loads — geen POST requests in de hele HAR. Geen `ScanForModules`, geen `UpdateRelay`, geen `Import*` calls. De URL `Output/Usages` is een sub-pagina binnen Configuratie (geen API-endpoint).

---

## 2. Veldbus correlatie (pcap)

| IPs in capture | Verkeer |
|---------------|---------|
| `10.10.1.1` → `10.10.1.50` | 24 pakketten UDP/1001 — `FIND` (0x4930) naar input |
| `10.10.1.1` → `10.10.1.40` | 3 pakketten UDP/1001 — dimmer poll |
| `10.10.1.1` → `10.10.1.30` | 3 pakketten UDP/1001 — relay poll |
| UDP/10001 | 0 pakketten |

**Conversatie-overzicht (relevant):**

```
10.10.1.1 ↔ 10.10.1.50   48 frames (24 rx + 24 tx)  2976 bytes  duur: 46s
10.10.1.1 ↔ 10.10.1.40    6 frames (3 rx + 3 tx)     372 bytes  duur: 40s
10.10.1.1 ↔ 10.10.1.30    6 frames (3 rx + 3 tx)     372 bytes  duur: 40s
```

**Conclusie:** tijdens de navigatie door Configuratie-pagina's poll de IPBox:
- De **input** (`10.10.1.50`) het meest actief — 24x bidirectional UDP/1001, payload `FIND` (0x4930)
- **Dimmers** en **relays** nauwelijks actief — slechts 3 pakketten elk

Dit wijst op **input-polling** door de IPBox als achtergrond-taak, niet direct getriggerd door Configuratie-pagina navigatie. De `FIND` opcode naar `10.10.1.50` is consistent met de discovery/keepalive die we eerder zagen (frame 19 in 22:38 capture: `49 30 30 30 30`).

---

## 3. HAR-vs-pcap correlatie matrix

| Configuratie-pagina | HAR-verkeer | Veldbus-activiteit | Opmerking |
|--------------------|-------------|-------------------|-----------|
| **Output/Index** (Uitgangen) | GET HTML + assets (108ms) | Input poll only | Geen direct relais-verkeer |
| **Pushbuttons/Index** (Drukknoppen) | GET HTML + assets (392ms) | Input poll | Zelfde als hierboven |
| **Mood/Index** (Sferen) | GET HTML + assets (338ms) | Input poll | Zelfde als hierboven |
| **Detectors/Index** | GET HTML + assets (5686ms) | Input poll | Langzaam — veel data |
| **Programmations/Index** | GET HTML + assets (6847ms) | Input poll | Langzaamste pagina |
| **Mail/Index** | GET HTML + assets (1219ms) | Input poll | - |
| **TouchLayout/Index** | GET HTML + assets (6816ms) | Input poll | - |
| **Output/Usages** | GET (168ms) | Input poll | Sub-pagina, 44× herhaald door HAR |

---

## 4. Nieuwe bevindingen t.o.v. vorige wizards-sessie

### 4.1 Configuration vs. Wizards
De **Wizards** (RE_WIZARDS_PLAN) en **Configuration** zijn **twee verschillende menu-takken**:

| Tak | URL-prefix | Doel |
|-----|-----------|------|
| **Wizards** | `/general/Wizards/...` | Initiële setup (modules scannen, kanaalnamen bewaren) |
| **Configuration** | `/general/Configuration/...` | Dagelijks beheer (uitgangen, drukknoppen, sferen, etc.) |

### 4.2 Output/Usages — 44× identical requests
De `Output/Usages` pagina is **44× identiek** gerequest in de HAR — waarschijnlijk een `setInterval` in de UI die de "Usages" data periodiek refresh (vergelijkbaar met de `PressButton` polling in de vorige wizards-sessie).

### 4.3 Input polling pattern
`10.10.1.1` → `10.10.1.50` met `FIND` (0x4930) opcode, bidirectioneel. Dit bevestigt dat de input module actief wordt gepolled door de IPBox. Geen `api.html` verkeer (direct naar module) in deze sessie — de data komt via de IPBox WebConfig, niet direct via HTTP naar de module.

### 4.4 Page timing as情报
- `Output/Index` (108ms) en `Pushbuttons/Index` (392ms) laden snel → weinig data
- `Detectors/Index` (5686ms) en `Programmations/Index` (6847ms) laden traag → veel data/tabellen
- `TouchLayout/Index` (6816ms) → complex UI element

---

## 5. Ontbrekende data voor volledig beeld

De HAR bevat **uitsluitend GET requests** — geen POST, geen API calls naar `:30200`. Om de volledige Configuration-flow te begrijpen (编剧: welke data wordt geladen voor elke pagina, welke wijzigingen kunnen worden bewaard), heb je nodig:

1. **HAR met interactie** — navigeer naar een specifieke output/drukknop/mood en bewaar wijzigingen → zie welke POST/put calls er worden gedaan
2. **Parallel pcap** — de huidige pcap toont alleen input-polling (UDP/1001); voor Output/Dimmer-pagina's verwacht je meer verkeer naar `10.10.1.30` (relay) en `10.10.1.40` (dimmer)
3. **Usages data** — de 44× `Output/Usages` requests bevatten waarschijnlijk XHR/fetch calls waarvan de response data interesting is (welke kanalen gebruiken welke uitgangen)

---

## 6. Vergelijking Wizard vs. Configuration

| Aspect | Wizards | Configuration |
|--------|---------|----------------|
| Menu locatie | "Wizards" tab | "Instellingen" tab (vermoedelijk) |
| Flow | Scan → Step2 → Step3 | Index → Detail/Usages |
| HTTP methodes | POST + GET | Uitsluitend GET (in deze capture) |
| Veldbus | Geen meetbare activiteit | Input actief gepolled (UDP/1001) |
| Data opslag | naar modules via `api.html` + naar IPBox | naar IPBox (vermoedelijk REST of direct) |

---

## 7. Volgende stappen

1. **Configuration/Output/Usages** — capture een sessie waar je daadwerkelijk een output/groep wijzigt → zie welke POST er wordt gedaan (verwacht: `UpdateRelay` of `UpdateDim`类似的)
2. **Configuration/Pushbuttons** — idem voor drukknoppen
3. **Configuration/Moods** — sfeer-wijzigingen vastleggen
4. **Parallel pcap** — let op de **UDP/1001双向** conversatie wanneer je een Dimmer pagina opent (verwacht meer `10.10.1.1 ↔ 10.10.1.40` verkeer)
5. **Page timing** — de lange load times van Detectors/Programmations/TouchLayout (~6-7s) wijzen mogelijk op zware data-transfer; cross-reference met `comp/items` REST API