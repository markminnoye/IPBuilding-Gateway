# Dimmer UDP/1001 payload correlation (10.10.1.40)

## Scope

Doel: dimmer-payloads op `10.10.1.40` correleren met getimede IPBox REST-stappen, als volgende stap richting een byteschema.

Bronnen:

- `captures/_subagent_dimmer_20260503T202559Z/dimmer_udp.pcapng`
- `captures/_subagent_dimmer_20260503T202559Z/dimmer_re_manifest.log`
- `captures/2026-05-03T200521Z_dimmer572_mirror12_en7_udp1001.pcapng`
- `scripts/dimmer_only_re_stimulus.sh`

## Capture facts

- Mirror-path: UniFi destination `7` <- source `12` (dimmer `10.10.1.40`).
- In beide dimmer-runs is op UDP/1001 alleen `10.10.1.40 -> 192.168.0.185` zichtbaar.
- Geen `192.168.0.185 -> 10.10.1.40` UDP/1001 op deze capture-POV.

## Run A (staged subagent): manifest-correlatie

Pcap: `captures/_subagent_dimmer_20260503T202559Z/dimmer_udp.pcapng`

- packets: 12
- tijdvenster: `2026-05-03 22:26:14.339810` tot `22:28:16.547260`
- stimulus: OFF -> DIM 30 -> DIM 70 -> DIM 100 -> OFF (22 s tussenstappen)

UDP payloads (ASCII van `udp.payload`):


| frame | t_rel_s | payload_hex        | payload_ascii |
| ----- | ------- | ------------------ | ------------- |
| 1     | 0.000   | `4930313534313030` | `I0154100`    |
| 2     | 2.204   | `4930313534393939` | `I0154999`    |
| 3     | 22.188  | `4930313534393939` | `I0154999`    |
| 4     | 22.839  | `4930313534313330` | `I0154130`    |
| 5     | 42.197  | `4930313534393939` | `I0154999`    |
| 6     | 45.372  | `4930313534313730` | `I0154170`    |
| 7     | 62.201  | `4930313534393939` | `I0154999`    |
| 8     | 68.020  | `4930313534313939` | `I0154199`    |
| 9     | 82.205  | `4930313534393939` | `I0154999`    |
| 10    | 91.215  | `4930313534313030` | `I0154100`    |
| 11    | 102.209 | `4930313534393939` | `I0154999`    |
| 12    | 122.207 | `4930313534393939` | `I0154999`    |


Correlatie met REST (eerste betekenisvolle frame binnen 0-3 s na actie):


| REST UTC             | action  | delta_s | frame | payload_ascii |
| -------------------- | ------- | ------- | ----- | ------------- |
| 2026-05-03T20:26:14Z | OFF     | 0.340   | 1     | `I0154100`    |
| 2026-05-03T20:26:36Z | DIM_30  | 1.179   | 4     | `I0154130`    |
| 2026-05-03T20:26:59Z | DIM_70  | 0.712   | 6     | `I0154170`    |
| 2026-05-03T20:27:22Z | DIM_100 | 0.360   | 8     | `I0154199`    |
| 2026-05-03T20:27:44Z | OFF     | 1.555   | 10    | `I0154100`    |


Opmerking: `I0154999` verschijnt frequent tussen acties en lijkt een idle/poll-statusframe.

## Run B (62 s mirror12)

Pcap: `captures/2026-05-03T200521Z_dimmer572_mirror12_en7_udp1001.pcapng`

- packets total: 150
- UDP/1001 `10.10.1.40 -> 192.168.0.185`: 6 frames


| frame | t_rel_s | payload_ascii |
| ----- | ------- | ------------- |
| 1     | 0.000   | `I0154150`    |
| 2     | 2.305   | `I0154199`    |
| 3     | 4.602   | `I0154100`    |
| 4     | 11.393  | `I0154999`    |
| 5     | 31.388  | `I0154999`    |
| 84    | 51.399  | `I0154999`    |


Run B bevestigt dezelfde familie (`I0154xxx`) als Run A.

## Run C (150 s recapture met bredere BPF)

Pcap: `captures/_dimmer_recap_20260503T203917Z/dimmer_bidir_probe.pcapng`

- BPF: `(host 10.10.1.40 or host 192.168.0.185) and udp port 1001`
- packets total: 12
- stimulus: OFF -> DIM 30 -> DIM 70 -> DIM 100 -> OFF (zelfde script, 22 s tussenstappen)

Richting en payloads:

- `10.10.1.40 -> 192.168.0.185`: 12 frames (`I0154100`, `I0154130`, `I0154170`, `I0154199`, veel `I0154999`)
- `192.168.0.185 -> 10.10.1.40`: **0 frames**

Conclusie Run C: ook met bredere BPF blijft deze mirror-POV unidirectioneel voor UDP/1001.

## Hypotheses (status)

### Confirmed

- **Frame-shape:** UDP payload is 8 ASCII bytes, patroon `I0154xxx`.
- **Direction op deze POV:** alleen `10.10.1.40 -> 192.168.0.185` zichtbaar.
- **Action-correlation:** na DIM/OFF stappen verschijnt binnen ~0.3-1.6 s een corresponderend `I0154...` frame.

### Likely

- Laatste 3 cijfers coderen een dimmerstatus-waarde:
  - OFF -> `100`
  - DIM 30 -> `130`
  - DIM 70 -> `170`
  - DIM 100 -> `199`
  - tussendoor vaak `999` als idle/keepalive/status-onbekend.
- `I0154` is vermoedelijk een vaste prefix met device/family/channel context.

### Unknown

- Of dit payloadtype een **command** of een **status/ack/report** vertegenwoordigt.
- Mapping van `{100,130,170,199,999}` naar fysiek dimniveau (lineair/niet-lineair/offset).
- Betekenis van mogelijke sequence/checksum elders (niet zichtbaar in 8-byte payload).

## Limitations

- Deze capture-opstelling toont geen `192.168.0.185 -> 10.10.1.40` UDP/1001; commandrichting blijft onduidelijk.
- Zonder alternatieve POV of bidirectionele zichtbaarheid kan nog geen volledig wire-command schema voor gateway-emulatie worden geclaimd.

## Next verification

1. Alternatieve capture-POV bepalen (uplink/andere SPAN) om expliciet `192.168.0.185 -> 10.10.1.40` UDP/1001 zichtbaar te maken; met mirror source `12` alleen blijft die richting afwezig.
2. Tweede dimmerkanaal (`id=571`) met hetzelfde stimuluspatroon draaien om te testen of `I0154`-prefix of suffixsystematiek kanaal-afhankelijk is.