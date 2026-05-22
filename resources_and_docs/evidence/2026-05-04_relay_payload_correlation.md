# Relay payload correlation (2026-05-04)

> Canonieke actuele RE-status: `resources_and_docs/RE_STATE.md` (dit document is evidence/deep-dive).

## Scope

Doel: relay-payloads op `10.10.1.30` correleren met IPBox REST-stappen en hypotheses afronden voor commando-opbouw.

## Module HTTP endpoints (live geverifieerd)

Op `10.10.1.30`:

- `http://10.10.1.30/api.html?method=getSysSet`
- `http://10.10.1.30/api.html?method=backupConfig`

Beide endpoints reageren live en zijn nuttig om kanaalconfiguratie te kruisen met UDP-observaties.

## Capture facts

- Mirror-path: UniFi destination `7` <- source `15` (IPBox IPBuilding-segment) of `14` (Relay).
- Nieuwe gerichte run: `captures/2026-05-04T175906Z_relay_sweep_547_557_563_retry/`
- REST-calls voor `547`, `557`, `563` gaven allemaal `HTTP:200`.

## Correlation Matrix (retry run 547/557/563)


| REST UTC             | Action | ID  | UDP Payload (ASCII, IPBox -> 10.10.1.30) | Parsed Action | Channel candidate |
| -------------------- | ------ | --- | ---------------------------------------- | ------------- | ----------------- |
| 2026-05-04T17:59:08Z | ON     | 547 | `S0000`                                  | on            | 0                 |
| 2026-05-04T17:59:16Z | OFF    | 547 | `C0000`                                  | off           | 0                 |
| 2026-05-04T17:59:29Z | ON     | 557 | `S1000`                                  | on            | 10                |
| 2026-05-04T17:59:37Z | OFF    | 557 | `C1000`                                  | off           | 10                |
| 2026-05-04T17:59:49Z | ON     | 563 | `S1600`                                  | on            | 16                |
| 2026-05-04T17:59:57Z | OFF    | 563 | `C1600`                                  | off           | 16                |


Achtergrondframe in alle runs: `P0000`.

## Relay Payload Patterns (v0.1 -> v0.2)


| Pattern     | Action                     | Status                                                       |
| ----------- | -------------------------- | ------------------------------------------------------------ |
| `S<CH>00`   | ON command                 | **Confirmed**                                                |
| `C<CH>00`   | OFF command                | **Confirmed**                                                |
| `P0000`     | pulse/idle/background      | **Confirmed aanwezig**, semantiek deels open                 |
| `T<CH>00`   | toggle command             | **Seen eerder**, nog niet in laatste gerichte run getriggerd |
| `I<digits>` | status/poll van controller | **Parsed in golden run** (module/channel/state velden)       |


## Afgeronde hypotheses

- **H1 (commando-type):** `S` = ON en `C` = OFF voor relaycommando’s. **Confirmed**.
- **H2 (kanaalcodering):** `<CH>` in `S<CH>00`/`C<CH>00` encodeert relaykanaal. **Confirmed** voor kanalen `0`, `10`, `16`.
- **H3 (ID->kanaal):** voor geteste IDs geldt `channel = ID - 547` (`547->0`, `548->1`, `557->10`, `563->16`, `570->23`). **Confirmed** op lage, midden- en hoge kanaalindexen van deze module.
- **H4 (statusstring):** `I`-frames volgen `I<module:3><channel:2><state:4>`, met `module=000`, `state_code=0100` (ON) en `0000` (OFF). **Confirmed voor OFF/ON-quartetten** op alle geïnventariseerde `I#########`-frames; extra quartets **niet waargenomen** (zie onder).

### Validatiecheck (automatisch)

Parser- en mappingcheck uitgevoerd op retry-captures:


| ID  | Payload           | Parsed channel | `ID - 547` | Match |
| --- | ----------------- | -------------- | ---------- | ----- |
| 547 | `S0000` / `C0000` | 0              | 0          | yes   |
| 557 | `S1000` / `C1000` | 10             | 10         | yes   |
| 563 | `S1600` / `C1600` | 16             | 16         | yes   |


Extra validatierun: `captures/2026-05-04T181533Z_relay_sweep_548_570_validation/`


| ID  | Payload           | Parsed channel | `ID - 547` | Match |
| --- | ----------------- | -------------- | ---------- | ----- |
| 548 | `S0100` / `C0100` | 1              | 1          | yes   |
| 570 | `S2300` / `C2300` | 23             | 23         | yes   |


### Relay status decode (golden run)

Herberekend met bijgewerkte parser/correlatie op:
`captures/2026-05-03T192700Z_golden-protocol-capture/udp_ipbox_export.txt`

Waargenomen `relay_status` records (subset):

- channel `0`: `on (0100)` en `off (0000)` beide gezien
- channels `2,5,8,10,11,12,13,14,17,18,20,22,23`: `on (0100)` gezien

Dit past bij scene-achtige burst waarin meerdere relaykanalen kort na elkaar status `on` melden.

## Relay status decode run (2026-05-04, OFF→ON→OFF)

**Sessie:** `captures/2026-05-04T184657Z_relay-status-decode/`  
**Runbook:** `resources_and_docs/workflows/relay_status_decode_runbook.yaml`  
**BPF:** `udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)`


| Stap       | IDs                | REST                                         |
| ---------- | ------------------ | -------------------------------------------- |
| OFF→ON→OFF | 547, 557, 563, 570 | Alle calls `response_status: 200` (manifest) |


**UDP-bevinding:** enkel verkeer **10.10.1.1 →** `.30` / `.40` / `.50` (commando’s `S`/`C`/`P` naar relay). **Geen** frames `10.10.1.30 → 10.10.1.1` of andere relay-antwoordrichting in deze pcap → `Relay status summary (parsed)` is leeg voor deze sessie. Dit is een **mirror/zichtbaarheidslimiet**, geen tegenspraak met H4.

Gecorrigeerde commando’s (ASCII naar `10.10.1.30`): `C0000`/`S0000` (kanaal 0), `C1000`/`S1000` (10), `C1600`/`S1600` (16), `C2300`/`S2300` (23) — matcht **H3** (`channel = ID - 547`).

## Relay status decode rerun (2026-05-05, OFF→ON→OFF)

**Sessie:** `scripts/captures/2026-05-05T072540Z_relay-status-decode/`  
**Runbook:** `resources_and_docs/workflows/relay_status_decode_runbook.yaml`  
**BPF:** `udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)`


| Stap       | IDs                | REST                                         |
| ---------- | ------------------ | -------------------------------------------- |
| OFF→ON→OFF | 547, 557, 563, 570 | Alle calls `response_status: 200` (manifest) |


**UDP-bevinding (identiek):** opnieuw alleen verkeer `10.10.1.1 -> 10.10.1.30` voor relay-commando's (`C0000/S0000`, `C1000/S1000`, `C1600/S1600`, `C2300/S2300`) en geen `relay_status` records in deze mirror-sessie. Dit bevestigt de eerdere interpretatie als zichtbaarheid/segmentpad-limiet voor statusframes in dit capturepunt.

## State_code → betekenis (evidence-backed)


| state_code        | Betekenis           | Confidence                     | Evidence                                                                                                                            |
| ----------------- | ------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `0100`            | Relaykanaal **ON**  | **Confirmed**                  | 15× in `2026-05-03T192700Z` golden pcap (`I000xx0100` payloads); correlatie-export relay status summary                             |
| `0000`            | Relaykanaal **OFF** | **Confirmed**                  | `I000000000` (ch 0 off) zelfde capture                                                                                              |
| *(ander quartet)* | —                   | **Unconfirmed / not observed** | Volledige UDP/1001 scan van golden `2026-05-03` en nieuwe status-run `2026-05-04`: **geen** andere state-quartets dan `0000`/`0100` |


### Niet-gemapte payload (open)


| ASCII        | Richting (golden 2026-05-03)   | Notitie                                                                                                                                                             |
| ------------ | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P000000000` | relay → hub of relay → IPBox thuis-IP | **Gemapt (2026-05-15):** fixed-width echo van hub→relay `P0000` wanneer retourpad zichtbaar is; zie addendum hieronder. |


## Tooling note

`scripts/correlate_capture_session.py` gebruikt nu `ip.addr==…` (bidirectioneel) + `192.168.0.185`, zodat relay→home-LAN UDP zoals in golden `2026-05-03` in de export blijft.

## POV A/B execution + decision (2026-05-05)

Doel van deze extra run: dezelfde OFF→ON→OFF-stimulus op IDs `547/557/563/570` twee keer uitvoeren met brede UDP-BPF en output vergelijken voor `relay_command` vs `relay_status` zichtbaarheid.

**Sessies:**

- POV-A: `captures/2026-05-05T073648Z_relay-status-decode-pov-a/`
- POV-B: `captures/2026-05-05T073728Z_relay-status-decode-pov-b/`
- Runbooks: `resources_and_docs/workflows/relay_status_decode_runbook_pov_a.yaml` en `resources_and_docs/workflows/relay_status_decode_runbook_pov_b.yaml`
- BPF in beide runs: `udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)`


| Metric                                                        | POV-A                          | POV-B                   |
| ------------------------------------------------------------- | ------------------------------ | ----------------------- |
| REST actions 547/557/563/570 OFF→ON→OFF                       | 12/12 `HTTP 200`               | 12/12 `HTTP 200`        |
| Parsed `relay_command` rows                                   | 14                             | 13                      |
| Parsed `relay_status` rows (`I<module><channel><state_code>`) | 0                              | 0                       |
| Distinct command channels seen                                | 0, 10, 11, 16, 23              | 0, 10, 16, 23           |
| Notable extra                                                 | `T1100` toggle frame seen once | geen extra toggle-frame |


**Interpretatie:** beide POV-runs tonen commandoframes consistent voor doelkanalen (`0/10/16/23`), maar geen parsebare relay-statusframes. POV-B heeft iets schoner signaal (geen spontane `T1100`) en is daardoor praktischer als standaard baseline voor command-validatie.

### Gekozen standaard POV

**Standaard POV voor vervolgvalidatie:** **POV-B** (`relay-status-decode-pov-b`) als default capture-profiel op `en7` met brede UDP-BPF, omdat deze run dezelfde commandocorrelatie levert met minder bijruis.

**Belangrijk:** dit lost status-zichtbaarheid nog niet op. Voor echte status-validatie blijft een extra gate nodig: pas run als "status-valid" markeren wanneer minstens één relay-antwoordrichting (`relay_status`) zichtbaar is in `udp_ipbox_export.txt`; zo niet, run herhalen met expliciete mirror-portcontrole.

## Push-vs-pull status onderzoek (A/B/C, 2026-05-05)

Doel van deze reeks: bepalen of zichtbare status rond relay-acties (`547/557/563/570`, OFF->ON->OFF) eventgedreven push is of primair op pollingcadans meeloopt.

Sessies:

- Run A (project-default BPF): `captures/2026-05-05T080840Z_push-pull-run-a/`
- Run B (host breadth incl. ARP/TCP/ICMP): `captures/2026-05-05T081008Z_push-pull-run-b/`
- Run C (idle, geen stimulus): `captures/2026-05-05T081148Z_push-pull-run-c-idle/`
- Analyse-export: `captures/2026-05-05_push_pull_analysis_summary.json`

### Comparison table (A/B/C)


| Metric                                       | Run A                             | Run B                             | Run C                     |
| -------------------------------------------- | --------------------------------- | --------------------------------- | ------------------------- |
| REST events                                  | 12                                | 12                                | 0                         |
| `relay_command` zichtbaar                    | ja (kanalen 0/10/16/23 + `P0000`) | ja (kanalen 0/10/16/23 + `P0000`) | alleen periodieke `P0000` |
| `relay_status` (`I<module><channel><state>`) | 0                                 | 0                                 | 0                         |
| `I0000` count                                | 42                                | 47                                | 77                        |
| `I0000` median gap                           | 2.003 s                           | 2.001 s                           | 2.002 s                   |
| Delay `t0 -> volgende I0000` median          | 1.133 s                           | 0.931 s                           | n.v.t.                    |
| ARP frames                                   | 0                                 | 100                               | 0                         |
| TCP/30200 frames in pcap                     | 0                                 | 0                                 | 0                         |
| ICMP frames in pcap                          | 0                                 | 0                                 | 0                         |


### Evidence-driven interpretatie

- **H1 periodic baseline (poll/sync): Confirmed (high).**  
In idle (Run C) blijft `I0000` quasi-stationair rond 2.00 s inter-arrival, zonder stimuli.
- **H2 command-correlated surplus: Rejected (medium).**  
Tijdens actieve runs verschuift de volgende `I0000` na `t0` binnen ongeveer 0.06-1.95 s, maar dit past binnen dezelfde 2 s baselinefase; geen extra statusfamilie of burst boven baseline.
- **H3 hybrid: Inconclusive/low.**  
Commandoframes (`S/C/P`) zijn duidelijk, maar er is geen onafhankelijke statusfamilie (`relay_status`) die een extra pushpad bevestigt.

### ARP-classificatie

- **Run B ARP patroon is overwegend periodiek/achtergrond en niet command-causaal.**
- Verdeling: `95x` `10.10.1.1 -> 10.10.1.254`, plus een klein aantal `10.10.1.1 -> 10.10.1.30/.50/.40`.
- ARP events liggen herhaald in vaste offsets rond veel `t0`-momenten (typisch rond -4.5..-0.5 s), wat beter past bij doorlopende neighbour refresh dan bij command-triggered status.
- Classificatie: **incidental** (geen causale claim).

### Long-window confirmatierun (2026-05-05)

Om delayed status buiten het standaard post-settle venster uit te sluiten is een extra variant uitgevoerd met identieke stimulus en BPF, maar met langere post-settle:

- Sessie: `captures/2026-05-05T082754Z_push-pull-run-a-long-window/`
- Runbook: `resources_and_docs/workflows/push_pull_run_a_long_window_runbook.yaml`
- `settle_after_steps_seconds`: **120s**

Resultaat:

- `relay_status` summary blijft leeg (`0` parsebare `I<module><channel><state>` records).
- `I0000`-cadans blijft doorlopen op ~2s, ook ver na laatste `t0`.
- `P0000`/`I9900` blijven periodiek zichtbaar in dezelfde achtergrondfamilies.

Conclusie update:

- Afwezigheid van relay-status in deze POV is **niet** verklaard door een te kort post-window; het blijft primair een zichtbaarheid/return-path-POV issue.

### Tooling correction (2026-05-05, manual Wireshark capture)

Nieuwe handmatige capture (`/Users/markminnoye/Downloads/full_capture_wireshark.pcapng`) met dezelfde POV toonde wel bidirectionele UDP/1001 flows. Dit wees op een analysezichtbaarheidsprobleem in plaats van puur capture-POV.

Doorgevoerde correcties:

- `scripts/correlate_capture_session.py` exporteert nu ook `src/sport` naast `dst/dport`.
- Nieuwe sectie `UDP direction summary` toegevoegd aan `udp_ipbox_export.txt`.
- Unparsed-overzicht groepeert nu op `src/sport -> dst/dport` (niet alleen `dst`).
- `scripts/relay_payload_parser.py` herkent `P000000000` als `relay_reply_candidate` (proto_map v0.3; `hub_command_ascii` / `pulse_channel` wanneer suffix negen nullen is).

Bevestiging op opnieuw geanalyseerde manual capture:

- Symmetrische pollingrichting zichtbaar (`10.10.1.1 <-> 10.10.1.50`, 17/17 frames).
- Relay response candidate zichtbaar (`10.10.1.30 -> 10.10.1.1`, `P000000000`).
- Dimmer response payload zichtbaar (`10.10.1.40 -> 10.10.1.1`, `I0154999`).

Interpretatie:

- Eerdere conclusies over "geen antwoord zichtbaar" waren deels beïnvloed door te smalle export/parsing.
- Status-onderzoek moet voortaan eerst een directionele gate passeren (`UDP direction summary`) vooraleer hypothese-verdicts te trekken.

### Open questions

1. Welke mirror source-poort levert in de huidige fysieke patching consequent relay-antwoordrichting op? Standaard-aanname is **`7←15`** (hub); test **`7←14`** alleen wanneer relay-poort-specifieke POV nodig is.
2. Is de afwezigheid van `relay_status` timing-gerelateerd (te korte post-settle) of puur POV/mirror-path?
3. Moet de orchestrator automatisch falen/warnen wanneer `relay_status summary` leeg blijft tijdens een status-doelrun?

## Artifacts

- `scripts/relay_payload_parser.py`
- `scripts/analyze_relay_reply_candidate_timing.py`
- `captures/2026-05-04T175906Z_relay_sweep_547_557_563_retry/`
- `captures/2026-05-04T184657Z_relay-status-decode/` (+ `udp_ipbox_export.txt`)
- `scripts/captures/2026-05-05T072540Z_relay-status-decode/` (+ `udp_ipbox_export.txt`)
- `captures/2026-05-03T192700Z_golden-protocol-capture/udp_ipbox_export.txt` (regenerated)
- `captures/2026-05-05T073648Z_relay-status-decode-pov-a/` (+ `udp_ipbox_export.txt`)
- `captures/2026-05-05T073728Z_relay-status-decode-pov-b/` (+ `udp_ipbox_export.txt`)
- `resources_and_docs/workflows/relay_status_decode_runbook_pov_a.yaml`
- `resources_and_docs/workflows/relay_status_decode_runbook_pov_b.yaml`
- `resources_and_docs/evidence/2026-05-05_push_pull_experiment_contract.md`
- `resources_and_docs/workflows/push_pull_run_a_runbook.yaml`
- `resources_and_docs/workflows/push_pull_run_b_runbook.yaml`
- `resources_and_docs/workflows/push_pull_run_c_idle_runbook.yaml`
- `captures/2026-05-05T080840Z_push-pull-run-a/` (+ `manifest.jsonl`, `udp_ipbox_export.txt`)
- `captures/2026-05-05T081008Z_push-pull-run-b/` (+ `manifest.jsonl`, `udp_ipbox_export.txt`)
- `captures/2026-05-05T081148Z_push-pull-run-c-idle/` (+ `manifest.jsonl`, `udp_ipbox_export.txt`)
- `captures/2026-05-05_push_pull_analysis_summary.json`
- `captures/2026-05-05_push_pull_followup_unknown_clusters.md`
- `captures/2026-05-05T082754Z_push-pull-run-a-long-window/` (+ `manifest.jsonl`, `udp_ipbox_export.txt`)
- `resources_and_docs/workflows/push_pull_run_a_long_window_runbook.yaml`
- `captures/2026-05-05T1040Z_user-full-capture/` (+ `capture.pcapng`, regenerated `udp_ipbox_export.txt`)

## Addendum — historical rerun with direction-aware pipeline (2026-05-05)

Doel van deze addendum: blanket-claims over "geen bidirectioneel verkeer" vervangen door sessie-specifieke evidence op geregenereerde exports (`scripts/correlate_capture_session.py` + relay reply candidate parser).

### Evidence matrix (sessies met `capture.pcapng` + `manifest.jsonl`)

| Session | Bidirectional UDP/1001 observed? | Key src<->dst pairs (count) | Notable reply families |
| --- | --- | --- | --- |
| `2026-05-03T192700Z_golden-protocol-capture` | no | `10.10.1.30:1001 -> 192.168.0.185:50445` (20) | `relay_reply_candidate` (`P000000000`) x4; `relay_status` x16 |
| `2026-05-04T103852Z_golden-protocol-capture` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (38), `10.10.1.1:50445 -> 10.10.1.30:1001` (21) | geen reply-family hit in deze POV |
| `2026-05-04T104550Z_golden-protocol-capture` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (36), `10.10.1.1:50445 -> 10.10.1.30:1001` (11) | geen reply-family hit in deze POV |
| `2026-05-04T163323Z_relay-re-run` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (16) | geen reply-family hit in deze POV |
| `2026-05-04T184657Z_relay-status-decode` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (20), `10.10.1.1:50445 -> 10.10.1.30:1001` (14) | geen reply-family hit in deze POV |
| `2026-05-05T073648Z_relay-status-decode-pov-a` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (17), `10.10.1.1:50445 -> 10.10.1.30:1001` (14) | geen reply-family hit in deze POV |
| `2026-05-05T073728Z_relay-status-decode-pov-b` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (17), `10.10.1.1:50445 -> 10.10.1.30:1001` (13) | geen reply-family hit in deze POV |
| `2026-05-05T080840Z_push-pull-run-a` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (42), `10.10.1.1:50445 -> 10.10.1.30:1001` (17) | geen reply-family hit in deze POV |
| `2026-05-05T081008Z_push-pull-run-b` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (47), `10.10.1.1:50445 -> 10.10.1.30:1001` (16) | geen reply-family hit in deze POV |
| `2026-05-05T081148Z_push-pull-run-c-idle` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (77), `10.10.1.1:50445 -> 10.10.1.30:1001` (8) | geen reply-family hit in deze POV |
| `2026-05-05T082754Z_push-pull-run-a-long-window` | no | `10.10.1.1:50446 -> 10.10.1.50:1001` (96), `10.10.1.1:50445 -> 10.10.1.30:1001` (22) | geen reply-family hit in deze POV |
| `2026-05-05T1040Z_user-full-capture` | yes | `10.10.1.1:50446 -> 10.10.1.50:1001` (17) and `10.10.1.50:1001 -> 10.10.1.1:50446` (17) | `relay_reply_candidate` (`P000000000`) x2, `I0154999*` zichtbaar, binary `I\x02R...E` zichtbaar |

### Scope-corrected claim

- Correct is: meerdere sessies blijven unidirectioneel in de zichtbare POV/export, **maar niet alle**.
- Expliciete tegenexample: `2026-05-05T1040Z_user-full-capture` toont bidirectionele UDP/1001 + reply families.
- Daarom is "geen bidirectioneel verkeer waargenomen" enkel geldig als **run-specifieke** observatie, niet als globale conclusie.

### Addendum — `P000000000` semantics (2026-05-15)

**Conclusie (confidence: high):** `P000000000` is het **relay→hub** (of relay→IPBox thuisbeen) **antwoord** op de hub→relay **pulse** `P0000`: dezelfde semantiek (kanaal 0 pulse), in een **10-tekens ASCII** framing (`P` + negen cijfers; waargenomen steeds `000000000`).

**Timing-evidence (bidirectionele export, PASS gate):** sessie `captures/2026-05-05T1040Z_user-full-capture/` — twee keer `10.10.1.1:50445 → 10.10.1.30:1001` met payload `P0000`, telkens gevolgd door `10.10.1.30:1001 → 10.10.1.1:50445` met `P000000000` binnen **~1.8–2.0 ms** (median ~1.9 ms). Reproduceerbaar met:

```bash
python3 scripts/analyze_relay_reply_candidate_timing.py \
  captures/2026-05-05T1040Z_user-full-capture/udp_ipbox_export.txt
```

**Contrasterende POV:** idle Run C (`captures/2026-05-05T081148Z_push-pull-run-c-idle/`) toont wél herhaalde hub→relay `P0000`, maar **geen** `P000000000` in de export — consistent met ontbrekend relay→hub zicht (WARN gate), niet met “geen antwoord op de bus”.

**Golden (`2026-05-03T192700Z_golden-protocol-capture`):** vier maal `P000000000` naar `192.168.0.185:50445` op ~20 s cadans; **geen** `10.10.1.1 → 10.10.1.30` rijen in dezelfde export → timing t.o.v. hub `P0000` is daar **niet meetbaar**; het patroon blijft verenigbaar met dezelfde echo op een ander L3-pad zodra de hub-pulse off-mirror loopt.

**Tooling:** [`scripts/analyze_relay_reply_candidate_timing.py`](../scripts/analyze_relay_reply_candidate_timing.py) (`--self-test`); parservelden in [`scripts/relay_payload_parser.py`](../scripts/relay_payload_parser.py) (`proto_map` v0.3, `hub_command_ascii` / `pulse_channel` voor het alle-null suffix).

