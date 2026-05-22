# IPBox REST API — test- en aanroepmatrix (agents)

Dit document somt **alle in dit project bekende HTTP-aanroepen** naar de IPBox op, zodat agents weten welke checks ze kunnen doen. De IPBox biedt **geen** aparte “delay”- of “timer”-endpoint: pauzes gebeuren **aan de client** (script, shell, HA).

**Bronnen:** `resources_and_docs/IPBUILDING_KNOWLEDGE.md` (fabrikant-niveau), HA-integratie `[api.py](https://github.com/markminnoye/HA-IPBuilding/blob/main/custom_components/ipbuilding/api.py)` + platforms (scene, button, light, switch).

**Placeholders**


| Symbool  | Voorbeeld                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------- |
| `{BASE}` | `http://<ipbox-op-192.168.1.0/24>:30200/api/v1` (thuis-LAN) of `http://10.10.1.1:30200/api/v1` (zelfde unit, veldbus-NIC — zie knowledge). Archiefvoorbeeld op ander segment: `http://192.168.0.185:30200/api/v1`. |
| `{ID}`   | Numeriek **device-ID** uit `GET …/comp/items` (veld `ID`).                                      |


Alle calls hieronder zijn `**GET`** (geen request-body).

---

## 1. Read-only: inventaris en status


| #   | Doel                                    | Aanroep                                               |
| --- | --------------------------------------- | ----------------------------------------------------- |
| R1  | Alle componenten (volledige inventaris) | `{BASE}/comp/items`                                   |
| R2  | Alleen outputs + LED/DMX zoals HA pollt | `{BASE}/comp/items?types=1,2,3,60`                    |
| R3  | Alleen relays                           | `{BASE}/comp/items?types=1`                           |
| R4  | Alleen dimmers                          | `{BASE}/comp/items?types=2`                           |
| R5  | Alleen DMX                              | `{BASE}/comp/items?types=3`                           |
| R6  | Alleen LED-strips                       | `{BASE}/comp/items?types=60`                          |
| R7  | Alleen scenes (sferen)                  | `{BASE}/comp/items?types=100`                         |
| R8  | Alleen tijdelijke scenes                | `{BASE}/comp/items?types=101`                         |
| R9  | Alleen drukknoppen (input)              | `{BASE}/comp/items?types=50`                          |
| R10 | Combinatie (vrij)                       | `{BASE}/comp/items?types=1,2` (komma’s, geen spaties) |


**Testtip:** na een actie (sectie 2) opnieuw **R1** of **R2** doen en het object met hetzelfde `{ID}` vergelijken (`Value` / `Status` — welke velden de IPBox vult, kan per firmware verschillen).

---

## 2. Acties: `GET …/action/action`

**Queryparameters (altijd):** `id`, `actionType`, `value` (integer; voor `ON` gebruikt HA `**value=1`**).


| #   | `actionType` | `value`   | Typisch **Type** (`ID` uit inventaris)          | Gebruik / test                                                                                    |
| --- | ------------ | --------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A1  | `ON`         | `1`       | **1** Relay (ook schakelaar / ventiel / …)      | Relay aan; HA gebruikt dit ook voor **niet-licht**-relays.                                        |
| A2  | `OFF`        | `0`       | **1** Relay                                     | Relay uit.                                                                                        |
| A3  | `DIM`        | `1`–`100` | **2** Dimmer                                    | Helderheid % (HA schaalt HA-helderheid 0–255 naar 0–100).                                         |
| A4  | `OFF`        | `0`       | **2** Dimmer                                    | Dimmer uit.                                                                                       |
| A5  | `ON`         | `1`       | **100** Scene (sfeer), **101** tijdelijke scene | Scene activeren (zelfde patroon als HA `scene.py`).                                               |
| A6  | `ON`         | `1`       | **50** Drukknop                                 | “Virtuele druk” / trigger (zelfde patroon als HA `button.py`; voorzichtig testen).                |
| A7  | `DIM`        | `1`–`100` | **3** DMX, **60** LED                           | HA pollt deze types; aanname: zelfde `DIM`/`OFF`-patroon als dimmer — **verifiëren op hardware**. |
| A8  | `OFF`        | `0`       | **3**, **60**                                   | Uit / minimum — verifiëren op hardware.                                                           |


**Niet gedocumenteerd in dit project:** andere `actionType`-strings (bv. toggles, regime, programma’s) via REST. Gebruik die alleen voor bewuste reverse-engineering, niet als “stabiele” agent-test.

**Voorbeeld-URL’s (lokaal, fictieve IDs):**

```http
GET http://192.168.0.185:30200/api/v1/action/action?id=547&actionType=ON&value=1
GET http://192.168.0.185:30200/api/v1/action/action?id=547&actionType=OFF&value=0
GET http://192.168.0.185:30200/api/v1/action/action?id=571&actionType=DIM&value=50
GET http://192.168.0.185:30200/api/v1/action/action?id=100064&actionType=ON&value=1
GET http://192.168.0.185:30200/api/v1/action/action?id=600&actionType=ON&value=1
```

Vervang `id=` door echte **ID**’s uit `resources_and_docs/reference/device-inventory-local-ipbox.md` of een verse `comp/items`-response.

---

## 3. Delay, timing, polling (geen REST-endpoint)


| #   | Patroon                                                                | Opmerking                                                                                                                                            |
| --- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1  | `**sleep 2`** (shell) of `asyncio.sleep(2)` tussen twee `action`-calls | IPBox/controller polling ~**2 s** in docs; kortere interval kan commando’s “op elkaar” stapelen of UDP lastiger correleren.                          |
| T2  | `**sleep 20`** tussen inventaris-samples                               | HA default coordinator-interval is **20 s**; nuttig om statusverschil te zien zonder spam.                                                           |
| T3  | Eén actie → **R1/R2** → diff JSON                                      | Regressietest “werkt output”.                                                                                                                        |
| T4  | Actie A → delay → Actie B → delay → **R1**                             | Sequentie (bv. scene + relay).                                                                                                                       |
| T5  | `**STEP_PAUSE_SEC=22`** (of hoger) tussen dimmer-`action`-calls        | Langere interval dan T1: beter te correleren met **~20 s** UDP-poll-ritme op mirror **12** (`10.10.1.40`); zie `scripts/dimmer_only_re_stimulus.sh`. |


---

## 4. Voorgestelde testsequenties (copy-paste idee)

Gebruik echte `{ID}`’s uit je inventaris. `curl -sS` aanbevolen.

1. **Relay toggle:** A1 → T1 → A2 → T1 → **R3** (controleer `Value`/`Status` voor dat ID).
2. **Dimmer-ladder:** A3 `value=25` → T1 → A3 `value=50` → T1 → A3 `value=100` → T1 → A4 → **R4**.
3. **Scene:** A5 met een scene-**ID** → T1 → **R7** (of R1) en eventueel gerelateerde outputs.
4. **Drukknop (voorzichtig):** A6 met button-**ID** — kan geautomatiseerde acties in IPBuilding triggeren; alleen in lab met bekende effecten.
5. **Alleen lezen / geen side-effects:** R1 t/m R10 zonder sectie 2.
6. **Dimmer UDP/1001 RE (gestuurd):** zet UniFi mirror **7←12**, start `dumpcap` op `en7` (`host 10.10.1.40 and udp port 1001`), voer `scripts/dimmer_only_re_stimulus.sh` uit (`MANIFEST_PATH` naar je sessiemap); daarna pcap + manifest samen analyseren.

---

## 5. Grenzen

- **Eén REST-laag:** alleen `/comp/items` en `/action/action` zijn hier beschreven.  
- **Geen TLS** in standaard lab-doc (plain HTTP op poort **30200**).  
- **Foutafhandeling:** `curl -f` faalt op HTTP ≥400; in scripts `response.raise_for_status()` (zoals HA).

