# Capture Live Status

Last updated: 2026-05-15 (local) — default mirror 7←15 (IPBox veld-been) + eerdere A/B/C-notities

**Canonical status source (actuele source of truth):** `resources_and_docs/RE_STATE.md`  
Gebruik dit document alleen voor operationele capture-details; voor actuele RE-status, verdicts en hypotheses is uitsluitend `RE_STATE.md` leidend.

## Recommended default strategy (status RE)

Gebruik voortaan een **3-laags standaard** voor statusonderzoek:

1. **Baseline run (Run A-profiel):** project-default BPF met vaste stimulus (`547/557/563/570`, OFF->ON->OFF) voor commandocorrelatie.
2. **Breadth run (Run B-profiel):** host-breed filter met `udp/tcp/icmp/arp` in een kort venster om non-UDP en ARP-context te valideren.
3. **Idle baseline (Run C-profiel):** 120-180 s zonder stimuli om pollingcadans te meten en event-surplus tegen af te zetten.

Referentie-artifacts:

- `resources_and_docs/evidence/2026-05-05_push_pull_experiment_contract.md`
- `resources_and_docs/workflows/push_pull_run_a_runbook.yaml`
- `resources_and_docs/workflows/push_pull_run_b_runbook.yaml`
- `resources_and_docs/workflows/push_pull_run_c_idle_runbook.yaml`
- `captures/2026-05-05T080840Z_push-pull-run-a/`
- `captures/2026-05-05T081008Z_push-pull-run-b/`
- `captures/2026-05-05T081148Z_push-pull-run-c-idle/`
- `captures/2026-05-05T082754Z_push-pull-run-a-long-window/`

### Why this is now default

- Idle en active runs tonen een stabiele `I0000` cadence rond ~2.00 s.
- Er is in de nieuwe A/B/C-reeks geen parsebare `relay_status` familie (`I<module><channel><state>`) gezien.
- Tooling is intussen corrected naar direction-aware export + relay reply candidate parsing; "geen status zichtbaar" betekent nu: niet parsebaar binnen deze POV/export, niet automatisch "geen reply op wire".
- ARP in breadth-run B bleek voornamelijk achtergrondverkeer (dominant `10.10.1.1 -> 10.10.1.254`) en niet command-causaal.
- Hierdoor is de beste standaardworkflow: eerst cadence/baseline bewijzen, daarna pas causaliteit claimen.
- Long-window variant (120s post-stimulus) toont nog steeds geen parsebare `relay_status`; vertraagde status buiten kort venster verklaart het dus niet in deze POV.

## Directional validity gate (nieuw, verplicht voor status-verdicts)

Voor runs met statusdoel (relay/dimmer/input) geldt voortaan:

1. Draai altijd `scripts/correlate_capture_session.py <session_dir>`.
2. Controleer `UDP direction summary` in `udp_ipbox_export.txt`.
3. Markeer de run als **invalid for status verdicts** wanneer de verwachte bidirectionele pair(s) niet zichtbaar zijn (bijv. alleen controller->module zonder replyrichting).

Gate-uitkomst:

- **PASS:** verwachte heen- en terugrichting zichtbaar voor relevante hostpair(s); statusclaims mogen verder geëvalueerd worden.
- **FAIL/WARN:** geen verwachte retourrichting zichtbaar; run blijft bruikbaar voor commandocorrelatie, maar niet voor harde statusafwezigheidsclaims.

Historische contra-evidence tegen blanket-claim:

- `captures/2026-05-05T1040Z_user-full-capture/` toont wel bidirectionele UDP/1001 (`10.10.1.1:50446 <-> 10.10.1.50:1001`) plus reply-families (`P000000000`, `I0154999*`, binary `I\x02R...E`).

## Cloud Gateway Ultra — tcpdump (optioneel, thuis-LAN)

Handige referentie voor captures **op de gateway zelf** (SSH `root@<CGW-IP>`), wanneer die op het **thuis-LAN** hangt. Verificatie: **2026-05-04** (ping naar IPBox **REST-host** op een oud segment — `192.168.0.185`; thuis-LAN is thans **`192.168.1.0/24`**, zie `IPBUILDING_KNOWLEDGE.md` §3.0).

### Management / SSH

- De CGW reageert op **meer dan één** LAN-adres in dit lab (typisch **`192.168.0.1`** en **`192.168.1.1`**) — het is **dezelfde** machine; kies het adres dat vanaf je netwerk routeert.
- Inloggen: `ssh root@<CGW-IP>` (zoals geconfigureerd op de gateway).

### Interfaces (`ip -br link` op CGW)

- **`br0`**: bridge voor het 192.168.0.x-segment; hier zie je **LAN-verkeer** dat over de bridge gaat.
- **`eth0` … `eth3` @ `switch0`**: de **vier ingebouwde Ethernet-poorten** van de CGW. **Fysieke poortnummers op het kastje komen niet 1:1 overeen met `eth4` in Linux** — `eth4` is een aparte interface (niet de “vierde” LAN-poort in die naamgeving).
- **Lab-IPBox** (IP `192.168.0.185`, kabel op **UniFi “poort 4”** naar CGW): op deze setup kwam verkeer zichtbaar op **`eth2`** en op **`br0`**. Op **`eth3`** werd in dezelfde test **niets** gevangen voor die host — altijd even **per poort verifiëren** na een verhuizing van kabels.

### Welke `-i` gebruiken?

| Doel | Interface |
|------|-----------|
| Minimale ruis, alleen de kabel naar de IPBox | `eth2` (op basis van bovenstaande verificatie; herbekijk na rewiring) |
| Breed zicht op hetzelfde LAN-segment | `br0` |
| Niet blind `eth3`/`eth4` aannemen voor “poort 4” | — |

### Commando’s

Live test (geen bestand), UDP/1001:

```bash
tcpdump -ni eth2 -s0 'udp port 1001'
# of
tcpdump -ni br0 -s0 'host 192.168.0.185 and udp port 1001'
```

Capture wegschrijven:

```bash
tcpdump -ni eth2 -s0 -U -w /tmp/ipbuilding_cgw_eth2_udp1001.pcapng 'udp port 1001'
```

Daarna bijv. naar je Mac: `scp root@<CGW-IP>:/tmp/ipbuilding_cgw_eth2_udp1001.pcapng .`

### Beperking (topologie)

Verkeer tussen **twee hosts achter dezelfde downstream switch** (bijv. alleen tussen controllers op **Switch 16**) gaat **niet** over de CGW. Dan zie je op `eth2`/`br0` **geen** UDP/1001 — daarvoor blijft **mirroring op de US16** of capture op een andere POV nodig. Wel zichtbaar op de CGW: verkeer waar de IPBox (`192.168.0.185`) **zelf** partij is (REST/UDP naar/van de IPBox).

### Eerdere mislukte CGW-pcap

Lege of bijna lege pcap’s ontstonden o.a. door **verkeerde interface-keuze** (`any` zonder frames, of een `ethN` zonder de IPBox-kabel). Eerst **`tcpdump` zonder `-w`** tot er live regels lopen, dan pas `-w`.

---

## Latest verified network/mirror state

- Capture interface for this setup is `en7`.
- **Aanbevolen standaard voor IPBox / UDP op het veld-VLAN:** UniFi Switch 16 mirror **bestemming `7` ← bron `15`** (**`7←15`**): het been met **`10.10.1.1`** (tweede NIC van de IPBox). Geeft typisch de meest complete **bidirectionele** UDP/1001 zichtbaarheid voor hub-gedrag; leg dit vast in elk manifest. Zie [IPBUILDING_CAPTURE_WORKFLOW.md](IPBUILDING_CAPTURE_WORKFLOW.md) (sectie “Aanbevolen standaardspiegel”).
- **Optioneel / specifiek (bovenop standaard `7←15`):** **`7←14`** = relay-switchpoort (`10.10.1.30`) alleen wanneer je die POV bewust kiest i.p.v. het IPBox-been; **`7←12`** = dimmer-only (`10.10.1.40` — **niet** poort `11`). UniFi-poortnummers altijd even verifiëren (`unifi_get_switch_ports` / stats).
- IPBuilding controller reachability is restored:
  - `10.10.1.40` reachable again (ping + HTTP `api.html?method=statuses`).
  - `10.10.1.30` path remains visible on mirrored UDP/1001 captures.

### Next capture prep — IPBox op **Switch 16** (gepland / lab)

**Topologie (2026-05-04):**

- IPBox **niet** meer op de **CGW**; terug op **US16 poort 8** (typisch **OLD / 192.168.0.185**-been voor REST naar `30200` — na verhuizing in UniFi controleren).
- **Tweede** ethernet IPBox op **US16 poort 15**, IP **`10.10.1.1`** (IPBuilding-segment; controllers `10.10.1.x` op **12 / 13 / 14** blijven relevant).

**Dual-homed risico:** twee paden naar dezelfde IPBox — zorg dat je **REST/stimulus** bewust naar **één** adres gaat (`192.168.0.185` vs `10.10.1.1`) en noteer welke je gebruikt in het manifest, anders is tijd-correlatie en route-analyse verwarrend.

**Spiegel-sessies (één per run; bestemming blijft `7` = Mac `en7` in eerdere setup):**

| Run | Mirror | Zicht op |
|-----|--------|----------|
| A | **7←8** | Verkeer op het been naar **poort 8** (o.a. REST/UDP naar `192.168.0.185` als die op dit VLAN zit). |
| B | **7←15** | Verkeer op het **10.10.1.x**-been (o.a. UDP naar/van `10.10.1.1`). |
| C | **7←12** | Dimmer-controller `10.10.1.40` (zoals bewezen eerdere dimmer-capture). |
| D | **7←14** | Relay-module `10.10.1.30` — **secondair** / relay-switchpoort-POV (niet de workflow-standaard; zie **B** voor hub-default). |

**Let op poort 8:** eerder brak **verkeerde mirror** op de IPBox-poort de bereikbaarheid — altijd **preview** in UniFi/MCP, daarna **apply**, direct **ping + REST** testen. Na de run mirror terugzetten naar je normale profiel (vaak **`7←15`** voor hub/standaard; **`7←14`** alleen als je expliciet de relay-access-poort wilt spiegelen).

**Mac / opname:**

1. `dumpcap` **vóór** mirror wijzigen of direct na apply; interface **`en7`** (of actuele sniff-NIC).
2. Eerste keer: **breed** opnemen (geen BPF, of alleen `udp port 1001` als je al zicht hebt), **`capinfos`** → packets > 0.
3. Stimulus: vaste intervallen (bv. `scripts/dimmer_only_re_stimulus.sh` of `ipbuilding_capture_run.py`) + **UTC-manifest**.

**Analyse:** post-filter in `tshark`/Wireshark (`udp.port==1001`, `ip.addr==…`); payload-diff tussen opeenvolgende stappen.

---

## Latest capture runs (from `captures/`)

### Successful / usable

- `2026-05-03T192700Z_golden-protocol-capture/`
  - Full orchestrator run succeeded (`capture.pcapng`, `manifest.jsonl`, `run.log`, snapshots, `runbook.yaml`).
  - 20 UDP packets in capture; stream observed as `10.10.1.30:1001 -> 192.168.0.185:50445`.
- `2026-05-03T192700Z_rest_step_payload_correlation.md`
  - REST step to UDP payload correlation extracted from the golden run.
- `2026-05-03T191638Z_relay557_120s_udp_only_notes.md`
  - 120s relay-focused run with stable payload-family observations (`I001001000`, `I000100000`, `P000000000`).
- `2026-05-03T185416Z_relay557_physical_only_notes.md`
  - Physical-only run confirms same payload family as REST runs for relay 557.
- `2026-05-03T183030Z_relay_ab_test_report.md`
  - A/B report: filtered host-pair path shows UDP/1001 as primary visible command-effect stream.
- `2026-05-03T200521Z_dimmer572_mirror12_en7_udp1001.pcapng` + `2026-05-03T200521Z_dimmer572_mirror12_cycle_notes.md`
  - Mirror **7←12** (dimmer `10.10.1.40`); **62s** `dumpcap` on `en7`; REST `id=572` DIM50→100→OFF; rollback daarna naar **`7←15`** (tegenwoordig standaard) of **`7←14`** (relay-POV); **150** frames total, **6×** UDP/1001 `10.10.1.40`→`192.168.0.185` (16-byte payload, sample `I0154150…`).
- `2026-05-05T073648Z_relay-status-decode-pov-a/` + `2026-05-05T073728Z_relay-status-decode-pov-b/`
  - Twee vergelijkbare OFF→ON→OFF sessies (`547,557,563,570`) met brede UDP-BPF via orchestrator.
  - Beide runs: alle REST-calls `200`, relay-command correlatie aanwezig, maar **geen parsebare relay_status frames**.
  - POV-B gaf schonere command-stream (geen extra `T1100` in deze sample) en is nu gekozen als **standaard command-validatie POV**.

### Failed / incomplete / low-confidence

- `2026-05-03T194100Z_unifi_mcp_dimmer_mirror_attempt_notes.md`
  - Dimmer mirror attempts via UniFi MCP did not produce usable dimmer packets on `en7` (run used **wrong mirror source port 11**; **`10.10.1.40` is on port 12** — notes file corrected with erratum).
  - During iterative mirror edits, `10.10.1.40` became temporarily unreachable (now recovered).
- `20260503T192214Z__udp_sendtest_highport.pcapng`
  - Mac-originated UDP injection test not directly visible on mirrored stream.
- `step2_smoke_udp1001_2026-05-03_1724.pcapng` and `step3_trigger_udp1001_2026-05-03_1725.pcapng`
  - Single-packet captures; insufficient for robust correlation.

## Current blockers

- Dimmer **UDP command correlation** to REST steps not yet written up (pcap exists; six IPBox-bound poll-sized frames in first 62s window).
- Mirror on this topology appears sensitive; wrong override combinations can disrupt reachability.
- Mac-originated traffic is not consistently represented on current mirror view.

## Decision log (factual)

- Relay path (`10.10.1.30`) remains the richest command-effect baseline; dimmer path is now **observable** on `en7` when mirror source is **12** (not 11).
- Full orchestrator run is now complete and can be used as baseline evidence set.
- UniFi MCP mirror semantics are error-prone; preserve/restore full port intent when testing.
- Connectivity incident on `10.10.1.40` was caused during mirror experiments and then restored.
- Nieuwe POV-A/B reruns (2026-05-05) bevestigen dat commandocorrelatie stabiel is, maar status-zichtbaarheid nog POV/mirror-gevoelig blijft.
- Standaard gezet op **POV-B** voor command-validatie; status-validatie vereist extra gate: minstens één `relay_status` record in export.
- Operator-keuze **2026-05-15:** primaire mirror voor IPBox-veldbus-RE = **`7←15`** (bron 15 → bestemming 7); zie [IPBUILDING_CAPTURE_WORKFLOW.md](IPBUILDING_CAPTURE_WORKFLOW.md) en [2026-05-15_capture_bidirectional_explainer.md](../evidence/2026-05-15_capture_bidirectional_explainer.md).

## Explicit next recommended step

1. Correlate REST timestamps with UDP/1001 in `2026-05-03T200521Z_dimmer572_mirror12_en7_udp1001.pcapng` (write-up like `2026-05-03T192700Z_rest_step_payload_correlation.md`).
2. Nieuwe staged run: UniFi **7←12**, `dumpcap` op `en7` met `host 10.10.1.40 and udp port 1001`, daarna `scripts/dimmer_only_re_stimulus.sh` (default **22 s** tussen OFF/DIM 30/70/100/OFF; `dimmer_re_manifest.log` voor tijd-correlatie). Zet mirror daarna terug naar **`7←15`** (standaard hub) of **`7←14`** (relay-poort) volgens je profiel.
