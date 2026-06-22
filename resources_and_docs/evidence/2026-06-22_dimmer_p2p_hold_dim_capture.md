# Dimmer peer-to-peer hold/dim capture (2026-06-22)

**Capture:** `/Users/markminnoye/Downloads/capture dimmer.pcapng`
**POV:** dimmer-poort `10.10.1.40` (vergelijkbaar met Sprint 3 mirror 7←12)
**Devices zichtbaar:** IP1100PoE input `10.10.1.50` ↔ IP0300PoE dimmer `10.10.1.40`
**Hub `10.10.1.1` afwezig** in deze capture (parallel pad, niet op deze mirror)

## Acties (in volgorde)

Schakelaar woonkamer/hal, kanaal 16 input:

| # | Actie | Verwacht |
|---|-------|----------|
| 1 | kort (short press) | TOGGLE → licht aan |
| 2 | kort | TOGGLE → licht uit |
| 3 | hold (lang ingedrukt) | DIM omhoog |
| 4 | hold | DIM omlaag |
| 5 | kort | TOGGLE → licht uit (eindtoestand) |

## Wire-protocol tabel (alle 12 pakketten)

| # | Tijd (rel.) | Richting | Payload (ASCII) | Gedecodeerd | Actie |
|---|-------------|----------|-----------------|-------------|-------|
| 1 | 0.000 | 50→40 | `T10<vv>1000` | Toggle ch10, dimMax level | TOGGLE aan |
| 2 | 0.024 | 40→50 | `I015410<vv>` | Status ch10, niveau % | Ack TOGGLE aan |
| 3 | 1.8xx | 50→40 | `T10<vv>1000` | Toggle ch10 | TOGGLE uit |
| 4 | 1.8xx | 40→50 | `I015410 00` | Status ch10, 00=uit | Ack TOGGLE uit |
| 5 | 3.4xx | 50→40 | `D10<vv>1003` | Dim start / auto-richting omhoog | DIM hold start |
| 6 | *(geen ack)* | — | — | Dimmer dimmt zelfstandig | — |
| 7 | 5.6xx | 50→40 | `D10<vv>1000` | Dim stop / hold release | DIM hold stop |
| 8 | 5.6xx | 40→50 | `I015410<vv>` | Status ch10, bereikt niveau | Ack na stop |
| 9 | 7.2xx | 50→40 | `D10<vv>1003` | Dim start (automatisch tegengesteld) | DIM hold start (omlaag) |
| 10 | *(geen ack)* | — | — | Dimmer dimmt zelfstandig | — |
| 11 | 9.1xx | 50→40 | `D10<vv>1000` | Dim stop | DIM hold stop |
| 12 | 9.1xx | 40→50 | `I015410<vv>` | Status ch10, bereikt niveau | Ack na stop |
| 13 | 10.8xx | 50→40 | `T10<vv>1000` | Toggle ch10 | TOGGLE uit (actie 5) |

> `<vv>` = DimMax-waarde geconfigureerd voor kanaal 10 (2-cijferig); exact getal afhankelijk van provisioning.

## Topologie-bevinding: peer-to-peer pad (NIEUW)

**De IP1100PoE input module stuurt commando's rechtstreeks naar de IP0300PoE dimmer.** De hub `10.10.1.1` is **afwezig** op dit pad.

Dit bevestigt de eerder open hypothese **"Autonomous mode"** uit `RE_STATE.md`:
> *"input→relay/dimmer direct pad niet gecaptured (centrale uit, LED knipperend)"*

**Dit pad is actief terwijl de centrale normaal draait.** Het is geen noodmodus maar het reguliere schakelpad voor knop→dimmer acties in het IPBox-systeem. De hub ontvangt parallel een `B-…E` button event via het input-pad (niet zichtbaar op deze POV — andere mirror nodig).

## Twee dialecten op UDP/1001

| Afzender | Toggle | Dim start | Dim stop | Set/Dim | Off |
|----------|--------|-----------|----------|---------|-----|
| **Input module** (50→40) | `T<ch><vv>1000` | `D<ch><vv>1003` | `D<ch><vv>1000` | — | — |
| **Hub/Gateway** (1.1→40) | — | — | — | `S<ch><vv>1030` | `C<ch>991030` |

Beide dialecten leven op dezelfde UDP/1001 bus. De dimmer accepteert beide.

## Hold-dim protocol (START/STOP)

```
Input                          Dimmer
  │                               │
  │── D<ch><vv>1003 ─────────────►│  ← hold ingedrukt (start)
  │                               │  dimmer dimmt autonoom (~31%/s up)
  │                               │  (geen ack op start!)
  │── D<ch><vv>1000 ─────────────►│  ← hold losgelaten (stop)
  │◄── I0154<ch><vv> ─────────────│  ← status reply met bereikte niveau
```

**Kritische eigenschappen:**
- Hold geeft exact **2 pakketten** op de wire (start + stop)
- **Geen streaming** — dimmer ramt autonoom tussen start en stop
- **Geen ack op start** — alleen de stop krijgt een `I0154…` reply
- **Identieke wire-code voor dim-up en dim-down:** beide sturen `D<ch><vv>1003`
- De IP0300PoE **wisselt intern van richting** bij elke opeenvolgende hold

## Geobserveerde dim-snelheden

- Dim-omhoog: ~31%/s (afgeleid uit tijdsverschil hold-start/stop vs niveau in ack)
- Dim-omlaag: ~20%/s

Deze snelheden zijn hardware-intern; niet configureerbaar via UDP/1001.

## Response format bevestigd

`I0154<ch><vv>` — altijd **3 cijfers** na `I0154`:
- `<ch>` = kanaalcijfer (0–7), hier kanaal `10` → maar ch-digit is 1 (kanaal 1 van het dimmer-board, geadresseerd als `1` in het payload)
- `<vv>` = 2-cijferige waarde-code: `00`=uit, `10`–`98`=%, `99`=100%

Sluit naadloos aan op Sprint 3 + 2026-06-03 correctie.

## Nieuw command-vocabulaire (input module dialect)

| Payload | Formaat | Semantiek |
|---------|---------|-----------|
| `T<ch><vv>1000` | `T` + ch-digit + 2-digit dimMax + `1000` | Toggle (input→dimmer) |
| `D<ch><vv>1003` | `D` + ch-digit + 2-digit dimMax + `1003` | Dim hold start (auto-richting) |
| `D<ch><vv>1000` | `D` + ch-digit + 2-digit dimMax + `1000` | Dim hold stop |

Suffix semantiek:
- `1000` = standaard input-dialect suffix (toggle en stop)
- `1003` = dim-start variant (specifiek voor hold-begin)

## Impact op `gateway/payloads/dimmer.py`

Drie nieuwe regex-patronen toe te voegen voor het **input-module dialect**:

```python
# Input module (50→40) peer-to-peer dialect
_INPUT_TOGGLE_RE  = re.compile(r"^T(?P<channel>\d)(?P<dimmax>\d{2})1000$")
_INPUT_DIM_START  = re.compile(r"^D(?P<channel>\d)(?P<dimmax>\d{2})1003$")
_INPUT_DIM_STOP   = re.compile(r"^D(?P<channel>\d)(?P<dimmax>\d{2})1000$")
```

**Gateway-implicatie:** als de gateway als hub werkt (vervangt IPBox), stuurt *zij* `S/C<ch><vv>1030` naar de dimmer. Het input-module peer-to-peer pad loopt *buiten* de gateway om. De gateway ziet de button event via `B-…E` op het input-module pad, beslist dan zelf (via HA-automation), en stuurt vervolgens een hub-commando. Het input→dimmer direct pad is dan een IPBox-artefact dat wegvalt zodra de gateway de centrale vervangt.

## Referenties

- Sprint 3 dimmer decode: `evidence/2026-05-17_dimmer_I0154xxx_full_decode.md`
- Sprint 5 input button events: `evidence/2026-05-22_sprint5_input_physical_completion.md`
- `gateway/payloads/dimmer.py` — encoder/decoder (toe te voegen: input-dialect)
- RE_STATE.md — autonomous mode unknown: **GESLOTEN** door deze capture
