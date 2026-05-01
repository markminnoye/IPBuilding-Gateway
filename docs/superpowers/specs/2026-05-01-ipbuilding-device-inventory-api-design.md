# IPBuilding — Device-inventaris via IPBox REST API

**Datum:** 2026-05-01  
**Status:** Ontwerp (goedgekeurd in brainstorm)  
**Doel:** Beschrijven welke REST-aanroepen en velden nodig zijn om later een document met alle toestel-**ID**’s, **Type**’s en interpretatie te bouwen — één algemene referentie (volledige inventaris) en één scope voor de huidige Home Assistant-setup.

---

## 1. Scope van dit document

Dit bestand is de **contractlaag**: welke HTTP-endpoints en JSON-velden je gebruikt om een inventaris op te bouwen. Het bevat **geen** UDP-beschrijving en geen export van concrete toestellen; die snapshot volgt in een apart inventarisdocument (handmatig of via script).

Twee gebruikscontexten:

| Context | Doel | Aanroep |
|--------|------|---------|
| **Algemeen** | Documentatie voor elke IPBox-installatie: alles wat de API teruggeeft qua componenten | `GET /api/v1/comp/items` **zonder** queryparameter `types`, tenzij de fabrikant/firmware een volledige expliciete lijst vereist — zie §3.1. |
| **Setup (Mark / HA-equivalent)** | Subset zoals de huidige HA-integratie pollt | `GET /api/v1/comp/items?types=1,2,3,60` |

---

## 2. Basis-URL en authenticatie

- **Base URL:** `http://<ipbox-host>:<poort>/api/v1`  
  Standaard lab: host `10.10.1.1`, poort `30200`.
- **Authenticatie:** geen (lokaal netwerk), tenzij later anders geconfigureerd.

---

## 3. Endpoint: componentenlijst (inventaris)

### 3.1 `GET /comp/items`

**Volledige paden:** `GET /api/v1/comp/items` en optioneel `GET /api/v1/comp/items?types=<kommalijst>`.

| Parameter | Verplicht | Betekenis |
|-----------|-----------|-----------|
| `types` | Nee | Kommagescheiden lijst van numerieke **Type**-codes (integers). Ontbreken van de parameter betekent in de praktijk vaak “alle types”; dit is **installatie-afhankelijk** — bij twijfel één keer vergelijken op jouw IPBox: response zonder `types` vs. met een expliciete lijst van alle bekende types uit de knowledge base. |

**Succes:** HTTP 200, body typisch een **JSON-array** van device-objecten.

**Operationeel:** netwerkfouten, timeouts en HTTP 4xx/5xx als fouten behandelen; lege array `[]` is een geldige response (geen matching componenten of lege installatie).

### 3.2 Velden in het device-object (minimum voor inventaris)

Minimaal te documenteren en te exporteren in het latere inventarisdocument:

| Veld | Rol |
|------|-----|
| `ID` | **Canonieke toestel-ID** voor acties en kruisverwijzing (o.a. `GET /action/action?id=…`). |
| `Type` | Hoofdtype (relay, dimmer, knop, scene, …) — numerieke code; mapping naar naam in §5. |
| `Kind` | Subcategorie / gebruik (licht, stopcontact, …) — numerieke code; mapping in §6. |
| `Description` | Mensleesbare naam (aanbevolen in export). |
| `Group` | Groep/ruimte-indicatie indien aanwezig (aanbevolen in export). |
| `Value` | Huidige waarde/stand waar van toepassing (nuttig voor snapshot, niet strikt nodig voor “ID + type”). |

Aanvullende velden die de IPBox teruggeeft, mogen in een export worden meegenomen zonder dit ontwerp te wijzigen.

---

## 4. Endpoint: acties (niet voor inventaris)

### 4.1 `GET /action/action`

Parameters: `id`, `actionType`, `value` (zoals gedocumenteerd in `resources_and_docs/IPBUILDING_KNOWLEDGE.md`).

**Gebruik:** aansturing en eventuele **handmatige validatie** (“juiste ID reageert”). Dit endpoint levert **geen** volledige lijst van toestellen; het hoort niet in het inventarisatie-pad behalve als optionele verificatiestap in een latere workflow.

---

## 5. Mapping: `Type` (numeriek → naam)

De authoritative tabel staat in **`resources_and_docs/IPBUILDING_KNOWLEDGE.md`** (sectie *Device Types* / HA `const.py`). Bij het schrijven van het inventarisdocument: altijd **zowel** het numerieke **Type** als de **naam** opnemen (of een vaste kolom “type_name” afgeleid van die tabel).

Bekende codes (samenvatting — bij discrepantie wint de knowledge base):

| Waarde | Naam (kort) |
|--------|----------------|
| 1 | Relay |
| 2 | Dimmer |
| 3 | DMX |
| 40 | Energieteller |
| 41 | Energiemeter |
| 50 | Drukknop |
| 51 | Temperatuur |
| 52 | Detector |
| 53 | Analoge sensor |
| 54 | KMI |
| 55 | Weerstation |
| 56 | Tijdmodule |
| 60 | LED strip |
| 70 | Toegangslezer |
| 80 | Toegangssleutel |
| 100 | Scene / sfeer |
| 101 | Tijdelijke scene |
| 102 | Programma |
| 103 | Toegangscontrole |
| 150 | Script |
| 200 | Regime |

---

## 6. Mapping: `Kind` (numeriek → naam)

Zie **`IPBUILDING_KNOWLEDGE.md`** (*Device Kinds*). Kort:

| Waarde | Beschrijving |
|--------|----------------|
| 1 | Light |
| 2 | Socket |
| 3 | Automation |
| 4 | Lock |
| 5 | Fan |
| 6 | Valve |
| 7 | Temperature |
| 8 | Not applicable |

---

## 7. Koppeling naar het latere inventarisdocument

1. **Algemene documentatie:** snapshot of tabel gegenereerd met aanroep **zonder** `types` (of equivalent “alle types” na verificatie op firmware), plus kolommen `ID`, `Type`, `type_name`, `Kind`, `kind_name`, `Description`, `Group`.
2. **Setup-documentatie (Mark):** zelfde velden, gefilterd met `types=1,2,3,60`, of één volledige export met extra kolom **`in_ha_scope`** (`true` als `Type` in `{1,2,3,60}`).

Geen extra REST-endpoints aangenomen tot die eventueel in captures of fabrikantdocs verschijnen.

---

## 8. Zelfcheck (placeholders & scope)

- Geen open “TBD” voor kern-API: `GET /comp/items` is voldoende voor ID + Type + Kind.
- Enige nuance: gedrag **zonder** `types` is firmware-afhankelijk — expliciet onder §3.1 vermeld.
- Scope: alleen IPBox REST voor inventarisatie; UDP en gateway buiten dit document.
