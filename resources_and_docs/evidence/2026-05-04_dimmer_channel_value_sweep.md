# Dimmer channel/value sweep matrix (2026-05-04)

**Doel:** per dimmer component-ID en sweep-stap de bijhorende UDP/1001 payload vastleggen, zodat kanaal-ID en helderheidswaarde uit elkaar getrokken kunnen worden.

## Scope van de sweep

Gebruik `scripts/dimmer_sweep_stimulus.sh` per losse run met:

- `ON` (`value=1`)
- `OFF` (`value=0`)
- `DIM` `100` tot `10` in stappen van `10`
- finale `OFF` (`value=0`)

## Channel mapping context (IP0300)

Referentie uit `resources_and_docs/reference/device-inventory-local-ipbox.md` en lokale IP0300-config.


| Comp ID         | Kanaal (hypothese) | Context                                                 |
| --------------- | ------------------ | ------------------------------------------------------- |
| 571             | ch0                | IP0300 output 1 (`40.1.1`, living)                      |
| 572             | ch1                | IP0300 output 2 (`40.1.2`, bureau)                      |
| 573             | ch2                | IP0300 output 3 (keuken)                                |
| 574 (optioneel) | ch3                | IP0300 output 4 (alleen als aanwezig in jouw inventory) |


> Bevestig mapping steeds met jouw actuele inventory export; labels kunnen per installatie verschillen.

## Matrix template: comp-id x step x payload

Vul deze tabel na capture/correlatie. Houd per stap minstens frame-tijd, payload (hex/ASCII) en observaties bij.


| Comp ID   | Step      | `value` | Frame time (UTC) | UDP payload (hex/ASCII) | Notes |
| --------- | --------- | ------- | ---------------- | ----------------------- | ----- |
| 571       | ON        | 1       |                  |                         |       |
| 571       | OFF       | 0       |                  |                         |       |
| 571       | DIM       | 100     |                  |                         |       |
| 571       | DIM       | 90      |                  |                         |       |
| 571       | DIM       | 80      |                  |                         |       |
| 571       | DIM       | 70      |                  |                         |       |
| 571       | DIM       | 60      |                  |                         |       |
| 571       | DIM       | 50      |                  |                         |       |
| 571       | DIM       | 40      |                  |                         |       |
| 571       | DIM       | 30      |                  |                         |       |
| 571       | DIM       | 20      |                  |                         |       |
| 571       | DIM       | 10      |                  |                         |       |
| 571       | OFF_FINAL | 0       |                  |                         |       |
| 572       | ON        | 1       |                  |                         |       |
| 572       | OFF       | 0       |                  |                         |       |
| 572       | DIM       | 100     |                  |                         |       |
| ...       | ...       | ...     |                  |                         |       |
| 573       | OFF_FINAL | 0       |                  |                         |       |
| 574 (opt) | OFF_FINAL | 0       |                  |                         |       |


## Hypotheses

- **H1 — Kanaalvelden:** byte-posities die veranderen tussen 571/572/573(/574), maar stabiel blijven binnen één sweep van dezelfde comp-ID.
- **H2 — Waardevelden:** byte-posities die monotone trend tonen bij `DIM 100 -> 10`.
- **H3 — ON/OFF semantics:** ON/OFF gebruikt mogelijk ander frame-type of extra vlag in vergelijking met DIM.
- **H4 — Poll vs command:** sommige frames blijven constant (poll/telemetry) en moeten uit de command-candidates gefilterd worden.

## Validatie met captures

1. Start capture vóór stimulus en noteer `MANIFEST_PATH`.
2. Gebruik UTC regels uit `dimmer_sweep_manifest.log` om rond elk event UDP/1001-frames te isoleren.
3. Exporteer velden met `tshark` en vergelijk payload-diffs per stap en per comp-ID.
4. Markeer alleen hypotheses als "bevestigd" wanneer hetzelfde patroon in minstens twee aparte runs terugkomt.

## Run result (uitgevoerd)

Sessie uitgevoerd op `2026-05-04T122545Z_dimmer_sweep_571_572_573` met:

- mirror/capture op `en7`
- BPF: `udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)`
- aparte sweep-run per `DIMMER_ID` (`571`, `572`, `573`)

### Samenvatting van onderscheidende payloads naar `10.10.1.40`

| Comp ID | Poll/idle | DIM 10..90 patroon | DIM 100 patroon | OFF patroon |
| --- | --- | --- | --- | --- |
| 571 | `I9900` | `S0101030` .. `S0901030` | `S0991030` | `C0991030` |
| 572 | `I9900` | `S1101030` .. `S1901030` | `S1991030` | `C1991030` |
| 573 | `I9900` | `S2101030` .. `S2901030` | `S2991030` | `C2991030` |

### Eerste interpretatie

- Het cijfer direct na `S`/`C` lijkt het kanaal te coderen:
  - `0` voor `571`, `1` voor `572`, `2` voor `573`.
- Waarde-code lijkt in het middenblok te zitten:
  - `...10...` t/m `...90...` voor `DIM 10..90`,
  - `...99...` voor `DIM 100`.
- `C*`-frames verschijnen bij OFF; `S*`-frames bij DIM.
- `I9900` komt frequent terug als achtergrond/poll-frame en is geen directe setpoint-wijziging.

### Uitgevoerde artefacten

- `captures/2026-05-04T122545Z_dimmer_sweep_571_572_573/571_capture.pcapng`
- `captures/2026-05-04T122545Z_dimmer_sweep_571_572_573/572_capture.pcapng`
- `captures/2026-05-04T122545Z_dimmer_sweep_571_572_573/573_capture.pcapng`
- bijhorende manifests/logs in dezelfde map

## Proto-map v0.1 (werkhypothese)

Op basis van 571/572/573 ziet het command-frame voor dimmer-sets er voorlopig zo uit:

`<prefix><channel><value_code>1030`

Waarbij:

- `<prefix>`:
  - `S` = set/dim-actie
  - `C` = cut/off-actie
  - `I` = poll/idle/status (`I9900`)
- `<channel>`:
  - `0` voor comp 571
  - `1` voor comp 572
  - `2` voor comp 573
- `<value_code>`:
  - `10..90` voor DIM 10..90
  - `99` voor DIM 100

Voorbeelden:

- `S0501030` = kanaal 0, DIM 50
- `S1901030` = kanaal 1, DIM 90
- `S2991030` = kanaal 2, DIM 100
- `C0991030` / `C1991030` / `C2991030` = OFF per kanaal

### Nog te bevestigen

- Of kanaal `3` (comp 574) exact `S3..1030` / `C3..1030` volgt.
- Of suffix `1030` constant blijft voor alle dimmerkanalen/firmwarevarianten.

### Parser tool (v0.1)

Gebruik `scripts/dimmer_payload_parser.py` om payload-ASCII meteen naar velden te mappen:

```bash
python3 scripts/dimmer_payload_parser.py S0501030 C1991030 I9900
```

Output bevat o.a. `action`, `channel`, `value_code`, `value_percent`.

`scripts/correlate_capture_session.py` neemt deze parser nu ook automatisch mee en schrijft een extra kolom `payload_parse` in `udp_ipbox_export.txt`.

### Relay parser integration

De relay-parser (`scripts/relay_payload_parser.py`) is eveneens geïntegreerd in de correlatie-script. Deze herkent patronen zoals `S0000` (ON), `C0000` (OFF), `T1400` (Toggle) en status-frames zoals `I000120100`.

Voorbeelden van relay-parsing:
- `S0000` -> `{"action": "on", "digits": "0000"}`
- `C1600` -> `{"action": "off", "digits": "1600"}`
- `I000120100` -> `{"action": "status", "digits": "000120100"}`

