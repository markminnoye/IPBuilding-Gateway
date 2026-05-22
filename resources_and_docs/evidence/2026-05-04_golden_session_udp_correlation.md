# Golden capture — UDP correlation (REST ↔ IPBox → controllers)

## Scope

Doel: volledige golden-run (`relay` → `dimmer` → **scene Keuken UIT `100064`**) koppelen aan **UDP/1001 payloads** vanaf `**10.10.1.1`**, zoals gezien op mirror **IPBox VLAN-been** (operator default **7←15**: US16 bronpoort **15** → dest **7** → Mac `en7`; niet de relay-leg **7←14**).

**Bronnen:**

- `captures/2026-05-04T104550Z_golden-protocol-capture/capture.pcapng`
- `captures/2026-05-04T104550Z_golden-protocol-capture/manifest.jsonl`
- `captures/2026-05-04T104550Z_golden-protocol-capture_udp_ipbox_export.txt` (gegenereerd door `scripts/correlate_capture_session.py`)
- Runbook-kopie in sessiemap: `runbook.yaml` (scene `**100064`**, relay `**547`**, dimmer `**571**` living)

## Capture facts


| Item           | Waarde                                                                                                |
| -------------- | ----------------------------------------------------------------------------------------------------- |
| PCAP frames    | 55                                                                                                    |
| Duur           | ~70,1 s                                                                                               |
| Zichtbare UDP  | Alleen `**10.10.1.1` →** `10.10.1.30` / `.40` / `.50`, dst **UDP 1001**                               |
| Inputs (`.50`) | Doorlopend poll `**I0000`** (~elke 2 s) — achtergrond                                                 |
| Relay (`.30`)  | Families `**S`**, `**T**`, `**C**`, `**P**` (o.a. `S0000`, `T1400`, `C0000`, `P0000`)                 |
| Dimmer (`.40`) | Families `**I9900**`, `**S…**`, `**C…**` (langer ASCII-blok, o.a. `S0501030`, `S0991030`, `C0991030`) |


**Tijdbasis:** `t_rel_s` = seconden sinds **eerste frame** in de pcap (`frame.time_relative`). REST-tijdstippen hieronder als `**Δt_rel`** = seconden na datzelfde eerste frame (afgeleid uit UTC manifest vs eerste-pakkettijd `2026-05-04T10:45:50.965806+00:00`).

## REST → dichtstbijzijnde command-UDP (samenvatting)


| step_id                                     | REST UTC (`rest_action`)           | Δt_rel (s)                | Opmerking / UDP naar `.30` relay                                              | UDP naar `.40` dimmer                              |
| ------------------------------------------- | ---------------------------------- | ------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| `relay_on`                                  | `2026-05-04T10:45:56.832421+00:00` | **~5,87**                 | `**S0000`** @ 5,890 s; daarna `**T1400`** @ 6,310 s                           | —                                                  |
| `relay_off`                                 | `2026-05-04T10:45:59.040478+00:00` | **~8,07**                 | `**C0000`** @ 8,082 s; `**P0000`** @ 8,311 s                                  | `**I9900**` @ 8,373 s                              |
| `dimmer_50`                                 | `2026-05-04T10:46:01.347704+00:00` | **~10,38**                | —                                                                             | `**S0501030`** @ 10,373 s                          |
| `dimmer_100`                                | `2026-05-04T10:46:03.600460+00:00` | **~12,63**                | —                                                                             | `**S0991030`** @ 12,671 s                          |
| `dimmer_off`                                | `2026-05-04T10:46:05.805827+00:00` | **~14,84**                | —                                                                             | `**C0991030`** @ 14,753 s                          |
| `**scene_on`** (`**id=100064**` Keuken UIT) | `2026-05-04T10:46:08.002756+00:00` | **~17,04**                | Burst `**C1600`** → `**C1700`** → `**C0000**` → `**C0200**` @ 17,063–17,342 s | `**C2001001**` @ 17,077 s                          |
| —                                           | (poll cadence)                     | elke ~20 s op `.30`/`.40` | `**P0000**` @ 28,311 s; idem @ 48,314 s / 68,317 s                            | `**I9900**` @ 28,376 s; idem @ 48,380 s / 68,377 s |


**Interpretatie (voorlopig):**

- `**relay_on`**: op relay-pad verschijnen `**S0000`** en `**T1400**` kort na REST.
- `**relay_off**`: `**C0000**` + `**P0000**` op relay; parallel `**I9900**` op dimmer (status/poll-familie, niet per se “gelijk” aan relay-actie).
- **Dimmer-stappen**: duidelijke reeks op `**.40`** — `S0501030` (50%), `S0991030` (100%), `C0991030` (off).
- **Scene `100064`**: geen apart lange `S*` string zoals dimmer in dit venster; sterke burst van `**C*` op relay** en één `**C2001001` op dimmer** binnen **~300 ms** na scene-REST — kandidaat voor “scene uitvoering” op beide benen.

## Ruwe UDP-export (subset — niet-`I0000` naar `.50`)

Zie volledige tabel in `captures/2026-05-04T104550Z_golden-protocol-capture_udp_ipbox_export.txt` (regels met destination `.30` of `.40`).

## Open punten

1. **Geen `udp.payload` richting IPBox** op deze POV (alleen uitgaand vanaf `10.10.1.1`) — zie eerdere analyses over mirror/een richting.
2. **Scene-bytes** (`C2001001`, `C1600`, …) nog niet gemapt op IPBuilding-object-ID **100064** (alleen tijds-correlatie).
3. Herhaalbaarheid: tweede run met zelfde runbook om te zien of byte-patronen **stabiel** zijn op milliseconde-niveau.

## Volgende stap (RE)

- Diff **scene-run** vs **dimmer-only run** op dimmer-payloads (`C2001001` vs `I0154xxx`-familie).
- Bepaal of `**C`*-prefix** een **command klasse** is (scene/programma) vs `**S`* = setpoint** vs `**I9900`** = status tick.