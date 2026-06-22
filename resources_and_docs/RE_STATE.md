# RE State (canonical)

Last updated: 2026-06-02 (local)

Compacte source of truth voor actuele reverse-engineeringstatus; detailbewijs blijft in de gelinkte evidence.

**Fase 1 (veldbus-RE + `gateway/payloads/`): afgesloten 2026-05-22.** Implementatie: Gateway Fase 2 — zie roadmap in [2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Index: [README.md](README.md). PCAP-locaties: [CAPTURES.md](CAPTURES.md).

**Payload-semantiek (compact matrix):** [2026-05-14_udp_payload_semantics_matrix.md](evidence/2026-05-14_udp_payload_semantics_matrix.md)

**RE Wizards (WebConfig provisioning, URL-kaart):** [2026-05-17_RE_WIZARDS_PLAN.md](reference/2026-05-17_RE_WIZARDS_PLAN.md)

## Validated facts

- De capture-orchestratie levert bruikbare artifacts (`capture.pcapng`, `manifest.jsonl`, `run.log`) in geslaagde runs. Evidence: `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md`.
- Relay OFF/ON-correlatie is reproduceerbaar voor o.a. `547/557/563/570` met verwachte command-payloadfamilies. Evidence: `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md`.
- Analyse is direction-aware gemaakt (`src/sport -> dst/dport` + summary), waardoor eerdere te nauwe conclusies gecorrigeerd zijn. Evidence: `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md`.
- Bidirectionele UDP/1001-zichtbaarheid is ten minste in een volledige sessie bevestigd (niet alle POV-runs tonen dit). Evidence: `captures/2026-05-05T1040Z_user-full-capture/`.
- Quiet-evening relay-sessie (echte UDP): o.a. `captures/2026-05-14T214007Z_push-pull-run-a-quiet-evening/` (~49 frames) en herhaal `captures/2026-05-14T220000Z_push-pull-run-a-quiet-evening/` (~48 frames); REST `547/557/563` gecorreleerd met hub→relay `C/S`-payloads op kanalen 0/10/16; export `STATUS_VERDICT_GATE: WARN` (geen return path in export). Evidence: `resources_and_docs/evidence/2026-05-14_relay_quiet_evening_session_notes.md`.
- Run C idle venster (geen relay-stimulus): o.a. `captures/2026-05-14T214905Z_push-pull-run-c-idle/` (~98 frames) en herhaal `captures/2026-05-14T220109Z_push-pull-run-c-idle/` (~94 frames); dominant `I0000` naar `10.10.1.50`, hub→relay `P0000` pulses; `STATUS_VERDICT_GATE: WARN`. Evidence: `resources_and_docs/evidence/2026-05-15_push_pull_run_c_idle_session_notes.md`.
- **`P000000000` (`relay_reply_candidate`):** relay→hub (of relay→IPBox thuisbeen) **fixed-width echo** van hub→relay pulse `P0000`; in `captures/2026-05-05T1040Z_user-full-capture/` ~1.8–2.0 ms na `P0000` wanneer retourrichting zichtbaar is. Tooling: `scripts/analyze_relay_reply_candidate_timing.py`. Evidence: `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md` (addendum 2026-05-15).
- **Relay command set (2026-05-19, volledig bevestigd):** alle 4 commando's live getest op kanaal 18 en 23: `Sxxxx` = ON (`I000xxxx100`), `Cxxxx` = OFF (`I000xxxx000`), `Txxxx` = TOGGLE, `Pxxxx` = PULSE (`P000000000` echo). Geen `[pfx]J` envelope — raw ASCII. Respons altijd `I000{channel}{state}` behalve PULSE. Evidence: directe Python UDP test vandaag.
- **Tooling-bijwerking (2026-05-16):** `wireshark_stats_endpoints` (MCP) is de **standaard check** voor bidirectionele UDP; vermijd `ip.src==X` filters — die laten replies ten onrechte weg. Zie `AGENTS.md`, `workflows/IPBUILDING_CAPTURE_WORKFLOW.md`, `scripts/relay_run_a_mirror_preflight.sh`.
- **Run A her-test (2026-05-14T230235Z_push-pull-run-a):** orchestrator op `en7`, REST naar `192.168.0.185` OK; ruwe pcap `udp1001_bidir_counts.py`: **16×** `10.10.1.1→10.10.1.30`, **0×** `10.10.1.30→10.10.1.1`; `tshark … ip.src==10.10.1.30` → **0** frames; `STATUS_VERDICT_GATE: WARN` (zelfde POV-patroon als eerdere quiet-evening/idle-runs). Operator: mirror **7←15** actief verifiëren vóór herhaling.
- **Sprint 1 GESLAAGD (2026-05-17):** user-capture `capture_00:48.pcapng` (Wireshark MCP, 1732 frames, 87s) toont **13× relay→hub** reply op `10.10.1.30:1001` → `10.10.1.1:50445`, Rx>0 bevestigd via `wireshark_stats_endpoints`. Payloads: `P000000000` (pulse echo ~2ms na hub pulse) + **`I<channel><state>`** (10-byte relay status replies: `I00000100`/OFF, `I00100100`/OFF, `I00160100`/OFF, `I00230100`/OFF voor kanalen 0/10/16/23). Correlatie met REST timestamps: relay ON→OFF correspondeert met `I<CH>0100` → `I<CH>0000` binnen ~4-5s na elke REST-call. Dit bevestigt dat relay→hub reply afhankelijk is van voldoende lange capture + goede mirror-POV. Evidence: `/Users/markminnoye/Downloads/capture_00:48.pcapng`.
- **Sprint 4 GESLAAGD (2026-05-17):** POV-vergelijking over 3 UniFi mirror-configuraties, identieke relay-stimulus (547/557/563 OFF→ON→OFF). Captures: `captures/sprint4_pov_comparison_20260517T012600Z/`.

  | POV | Mirror | Relay Rx | Dimmer Rx | Input Rx | Conclusie |
  |-----|--------|----------|-----------|----------|-----------|
  | A | 7←15 (IPBox hub/veldbus) | 13 | 4 | 39 | **nodig + voldoende** — alle apparaten zichtbaar |
  | B | 7←14 (relay-poort 10.10.1.30) | 13 | 0 | 0 | alleen relay-verkeer zichtbaar |
  | C | 7←12 (dimmer-poort 10.10.1.40) | 0 | 6 | 0 | alleen dimmer-verkeer zichtbaar |

  **Aanbeveling standaard-POV: 7←15** is de enige die alle field bus-apparaten toont. POV B/C limiteren zichtbaarheid tot hun respectievelijke poort-apparaat en zijn niet geschikt voor algemeen gebruik. Evidence: `captures/sprint4_pov_comparison_20260517T012600Z/pov_{a,b,c}_7x{15,14,12}.pcapng`.

- **Sprint 3 GESLAAGD (2026-05-17):** capture `01:01.pcapng` (2161 frames, 100s, mirror `7←12`, dimmer `10.10.1.40`). Hard requirement Rx>0 voor alle devicepairs — bevestigd voor `10.10.1.50` (50/50), `10.10.1.40` (11/11), `10.10.1.30` (7/7). Dimmer gebruikt **geen `J`-separator**; hub→dimmer prefix-byte is een compound (0x35/0x43/0x53/0x4b/0x53/0x53/0x43/0x4b/0x53/0x43) dat kanaal+richting combineert. Hub→dimmer command: `S0301030` = DIM 30% kanaal 0; `S0991030` = DIM 100% kanaal 0; `C0991030` = OFF kanaal 0. Dimmer→hub reply: **`I0154<C><VV>`** — vast `I01` prefix (device type dimmer), `54` constant (dimmer family), gevolgd door **`<C>` kanaalcijfer + `<VV>` waarde-code**. **Correctie 2026-06-03 (live test Bureau ch1):** de 3 cijfers na `I0154` zijn `<kanaal><waarde-code>`, niet één waarde-code — dat leek enkel te kloppen voor kanaal 0 (`030/099/000`). Kanaal 1: `I0154130`=30%, `I0154199`=100%, `I0154100`=uit; `I0154999`=idle/poll (geen setpoint). Waarde-code `00`=uit, `10..98`=%, `99`=100%. Decode van `130` als 130% was een bug (gefixt in `gateway/payloads/dimmer.py`; live geverifieerd via WebSocket — [2026-06-03_dimmer_decode_fix_websocket_test.md](evidence/2026-06-03_dimmer_decode_fix_websocket_test.md)). Soft-AAN (default 15%) en soft-UIT (default 70%) uit §12.3 kalibreren de fysieke output t.o.v. het setpoint. Reply timing: 24.7ms na hub→dimmer frame (< 500ms). Evidence: `/Users/markminnoye/Downloads/01:01.pcapng`.
- **Scan Modules wizard (2026-05-17):** WebConfig **POST** `/general/Wizards/Modules/ScanForModules` (sessie vereist, lege request body) retourneert `application/json` met array van modules: `IP`, `Mac` (dec. bytes), `IsNew`, `Type`, `Version`. Bevestigde response: relay `10.10.1.30` (fw 5.1), dimmer `10.10.1.40` (fw 5.4), input `10.10.1.50` (fw 5.2.4). Alle drie in scan; dimmer ontbrak in eerdere capture. Stap 2: `GET Step2?ip=…&type=Relais|Dim` + **POST** `…/ImportRelayInfo|ImportDimInfo`. Veld-bus capture (`captures/2026-05-17T210800Z_scan_modules/`): **UDP/10001** probe `01000000` van `10.10.1.1` naar `255.255.255.255` + `233.89.188.1` (~10,5 s); geen 10001-replies op mirror. Overzicht + roadmap: [2026-05-17_RE_WIZARDS_PLAN.md](reference/2026-05-17_RE_WIZARDS_PLAN.md).
- **IPBox WebConfig relay provisioning (2026-05-18):** HAR `01-36.har` + pcap `01:36.pcapng`. `POST /general/Hardware/Relais/ImportRelayInfo` body: `ip=10.10.1.30` — retourneert JSON-array van 24 kanalen (`id/descr/gr/status/pulse/lock/lockTimer`). `POST /general/Hardware/Relais/UpdateRelay` body: `ip=10.10.1.30&outputs=[{ID,CH,Description,Group,Pulse,Lock,LockTimer},…]&updateModule=1` — 24 kanalen, `ID` = REST comp/item ID (547–570). **Geen directe HTTP naar relaymodule** vanuit browser; IPBox proxyt naar veldbus UDP/1001. HTML-index bevat modulelijst inline. Bevestigt dat WebConfig-GUI-laag (`/general/Hardware/Relais/…`) en REST-API-laag (`/api/v1/…`) **twee aparte lagen** zijn. Documentatie: IPBUILDING_KNOWLEDGE.md §5.6. Evidence: `01-36.har` entries 5797 + 6136.
- **Step3 kanaalnaam-save (2026-05-17):** "Bewaar"-knop in Step3 (relay `10.10.1.30`) triggert **24 parallelle HTTP GETs** naar `10.10.1.30/api.html?method=saveOutput` — één per kanaal. Elk request bevat `ds` (display naam `Keuken LED [30.1.1]`), `gr` (groep), `pulse`, `lock` (8-char hex lock-bits), `lockTimer` (minuten), `ch` (index). **Geen** POST naar IPBox; geen UDP-burst. Bevestigd in pcap `captures/RE_WIZARDS_2026-05-17T214000Z_step3_save/21:40.pcapng` (1245 pakketten, 37s). HAR `21-40.har` had preserve-log uit → geen POSTs zichtbaar.
- **UpdateRelay / ImportRelayInfo (2026-05-17):** Complete wizard flow vastgelegd (preserve-log aan, `captures/RE_WIZARDS_2026-05-17T214900Z_full/`). `POST /general/Hardware/Relais/ImportRelayInfo` body: `ip=10.10.1.30`. `POST /general/Hardware/Relais/UpdateRelay` body: `ip=10.10.1.30&outputs=[{ID, CH, Description, Group, Pulse, Lock, LockTimer},…]` (24 kanalen). `ID` = REST comp/item ID (547–570). `POST ScanForModules` request body is **leeg**; response is JSON 190 bytes (HAR miste de body). `UpdateRelay` is het eigenlijke save-mechanisme richting IPBox (niet de `api.html` GETs — die zijn client-side preview).
- **Dimmer wizard (2026-05-17):** `POST /general/Hardware/Dim/ImportDimInfo` body: `ip=10.10.1.40`. `POST /general/Hardware/Dim/UpdateDim` body: `ip=10.10.1.40&outputs=[{ID, CH, Description, Group, DimMax, DimMin},…]` (8 kanalen, IDs 571–578). `DimMin`/`DimMax` = dimmer-grenzen in %. `api.html?method=saveChannel` = client-side HTTP GET per kanaal naar `10.10.1.40` (parallel aan relay's `saveOutput`). Captures: `captures/RE_WIZARDS_2026-05-17T215100Z_dimmer/` (529 pakketten, 18s).
- **Discovery mechanisme (2026-05-17):** IPBox gebruikt twee discovery-kanalen op de veldbus: (1) **UDP/10001** broadcast `01000000` naar `255.255.255.255` + `233.89.188.1` (~10,5s interval), (2) **WS-Discovery `Resolve`** (SOAP/UDP multicast) naar `239.255.255.250:698` — beide krijgen geen zichtbare reply van modules op mirror 7←15. Modules antwoorden via **UDP/1001** (relay: `P<CH>` echo, input: status reply, dimmer: poll). WS-Discovery URN in probes: `0dcdd209-7281-4b83-b920-59707060a3c5`. Evidence: dimmer pcap frames 457/458/466/467.
- **Sprint Dimmer GESLAAGD (2026-05-17, offline):** volledige `I0154xxx` decode + value-code mapping; hub commands `S/C<ch><val>1030`. Evidence: [2026-05-17_dimmer_I0154xxx_full_decode.md](evidence/2026-05-17_dimmer_I0154xxx_full_decode.md), `gateway/payloads/dimmer.py`.
- **Sprint Input GESLAAGD (2026-05-17, offline):** hub poll `I0000`; idle reply `I\x02R…E` 14-byte constant in POV-A. Evidence: [2026-05-17_ip1100_input_payload_decode.md](evidence/2026-05-17_ip1100_input_payload_decode.md), `scripts/input_payload_parser.py`.
- **Sprint 5 GESLAAGD (2026-05-22, fysieke input):** mirror **7←13** (`10:25.pcapng`): **12×** `B-…E` button events (press/release ~200 ms); poll `I0000` ~2 s; idle 14-byte reply unchanged. Button `id` op wire = substring van `getButtons` hardware-`id`. **Pad:** input→hub `10.10.1.1` alleen; hub→relais/dimmer op aparte mirror (**7←14** in `10:22.pcapng`). **Logische flow** (IPBox project → actie) **niet** gedecodeerd — later; module `func1`/`func2` + WebConfig wizards als referentie. Centrale-IP: niet in module HTTP-export; conventie **`10.10.1.1`**. Evidence: [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md), [2026-05-22_sprint5_input_10-25_session_notes.md](evidence/2026-05-22_sprint5_input_10-25_session_notes.md), `gateway/payloads/input.py`.
- **Gateway Fase 2 (2026-06-01, code):** `gateway/udp_bus.py` poll-loop, `device_registry.py`, `rest_shim.py` (IPBox `:30200` transitie, geen product-API), `main.py` entrypoint; `rest_api.py` = alias. Open: `devices.json` in config, veldtest als hub `10.10.1.1`, `gateway_api.py`, add-on + companion. Architectuur: [2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md). Evidence: [README_gateway.md](../README_gateway.md), [field bus matrix](2026-05-17_ipbuilding_fieldbus_capability_matrix.md).
- **Relay poll `I<ch>` (2026-06-02, lab):** `I0000`/`I0010`/`I0016`/`I0023` → altijd `I000000000` (10-byte echo, geen `I<CH><state>`). `P0000` → `P000000000` (pulse keep-alive). IPBox idle Run C: hub→relay alleen `pJP0000`, nooit `I<ch>`. **Geen** wijziging `_MODULE_POLL["relay"]`. Status `I<CH><state>` alleen na `S`/`C` (Sprint 1). Evidence: [2026-06-02_relay_poll_i_ch_test.md](evidence/2026-06-02_relay_poll_i_ch_test.md), `scripts/test_relay_poll.py`.
- **Input→dimmer peer-to-peer pad (2026-06-22, dimmer-poort capture):** IP1100PoE (`10.10.1.50`) stuurt commando's **rechtstreeks** naar IP0300PoE (`10.10.1.40`) — hub `10.10.1.1` afwezig op dit pad. **Sluit de "Autonomous mode" hypothese** uit `Unknowns/open hypotheses`: dit is het reguliere schakelpad tijdens normaal IPBox-bedrijf, niet een noodmodus. Nieuw command-vocabulaire (input-module dialect, **twee dialecten op UDP/1001**): `T<ch><vv>1000` = toggle, `D<ch><vv>1003` = dim hold start (auto-richting, geen ack!), `D<ch><vv>1000` = dim hold stop (ack `I0154<ch><vv>`). Hold = **start/stop protocol**: dimmer dimmt autonoom tussen de twee pakketten (~31%/s up, ~20%/s down); identieke wire-code voor dim-up en dim-down (IP0300 wisselt intern van richting). Hub-dialect ongewijzigd: `S<ch><vv>1030` / `C<ch>991030`. Evidence: [2026-06-22_dimmer_p2p_hold_dim_capture.md](evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md), `/Users/markminnoye/Downloads/capture dimmer.pcapng` (12 frames, POV dimmer-poort).

## Field bus readiness (northbound-agnostisch)

Zie [2026-05-17_ipbuilding_fieldbus_capability_matrix.md](2026-05-17_ipbuilding_fieldbus_capability_matrix.md). Relay + dimmer + **input button events** op UDP/1001 zijn **wire-confirmed**; **button→actie mapping** (centrale config) en scenes nog niet. **Northbound:** zie [2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md).

## Unknowns/open hypotheses

- **Prefix-byte volledige semantiek:** relay gebruikt raw ASCII (geen envelope); prefix-byte hypothese is achterhaald. Dimmer prefix-byte (compound, Sprint 3) blijft open.
- Andere `P` + negen-cijfer-patterns (niet alleen `…000000000`) zijn op de bus nog niet waargenomen; semantiek blijft open **tot** er een voorbeeld is.
- Scheiding tussen poll-baseline en command-triggered updates is nog niet hard gevalideerd over alle payloadfamilies. Evidence: `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md`.
- **Scan Modules:** UDP/10001 **antwoord**-payloads; dimmer `.40` soms ontbrekend in scan-UI; of scan een ARP-sweep doet over `.30`–`.59` op niet-gemirrord pad.
- **Discovery:** UDP/10001 en WS-Discovery (UDP/698) both get no visible module replies on mirror 7←15 — replies mogelijk via intern IPBox-pad.
- **Step3 save:** exact POST-body naar `api.html?method=saveOutput` (nog) niet bevestigd — pcap toont enkel de URL-query-string per kanaal; HTTP POST-variant (als die bestaat) is onbekend.
- **Scan Modules:** exact JSON response van `POST ScanForModules` — HAR miste de body ondanks `Content-Length: 190`; response semantiek (module lijst met IP/MAC/type/version/isNew) is afgeleid maar niet hard bevestigd.
- **Input logical flow:** exacte mapping knop-ID → actielijst op centrale (IPBox-project; architectuurdoel: logica in HA). Wire: [2026-05-22_sprint5_input_physical_completion.md](evidence/2026-05-22_sprint5_input_physical_completion.md).
- **Input centrale IP:** geen configureerbaar hub-IP in `getSysSet`/`backupConfig`; hardcoded `10.10.1.1` vs learned-from-poll niet wire-bewezen.
- ~~**Autonomous mode:** input→relay/dimmer direct pad niet gecaptured (centrale uit, LED knipperend).~~ **GESLOTEN 2026-06-22:** input→dimmer peer-to-peer pad bevestigd in `capture dimmer.pcapng`; dit is het **reguliere schakelpad** (niet een noodmodus). Zie [2026-06-22_dimmer_p2p_hold_dim_capture.md](evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md).

## Current risks/observability limits

- Mirror/POV bepaalt wat zichtbaar is op de field bus; **standaard 7←15 is nodig én voldoende** voor volledige bidirectionele zichtbaarheid van alle apparaten (relay/dimmer/input). POV B (7←14) toont alleen relay, POV C (7←12) toont alleen dimmer — niet geschikt voor algemeen gebruik.
- Zonder expliciete direction-check ontstaat regressierisico naar fout-negatieve "geen reply"-conclusies. Evidence: `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md`.
- Dual-homed padkeuze (**thuis-IP van de IPBox voor REST** vs **`10.10.1.1` op het IPBuilding-VLAN voor UDP/1001**) kan correlatie vertroebelen als de runcontext niet expliciet vastligt. Evidence: `resources_and_docs/IPBUILDING_KNOWLEDGE.md` §3.0.

## Next 3 actions (post–Fase 2)

1. **`gateway_api.py`** — WebSocket `/ws` + REST `/api/v1/`; zie [ARCHITECTURE.md](../ARCHITECTURE.md).
2. **Companion / HA add-on** — `ipbuilding-open` entiteiten + automations (knop→actie niet in gateway).
3. Optioneel RE (uitgesteld): IPBox sferen, Scan Modules UDP 10001 antwoorden — laag-prioriteit.

## Evidence pointers

- `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md`
- `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md`
- `resources_and_docs/IPBUILDING_KNOWLEDGE.md`
- `resources_and_docs/archive/NEXT_AGENT_STATUS_QUO_2026-05-03.md` (historische handoffcontext)
- `resources_and_docs/evidence/2026-05-14_udp_payload_semantics_matrix.md`
- `resources_and_docs/workflows/2026-05-14_relay_run_a_operational_playbook.md`
- `resources_and_docs/evidence/2026-05-14_relay_quiet_evening_session_notes.md`
- `resources_and_docs/evidence/2026-05-15_push_pull_run_c_idle_session_notes.md`
- `resources_and_docs/evidence/2026-05-15_long_capture_reference.md`
- `resources_and_docs/evidence/2026-05-15_capture_bidirectional_explainer.md`
- `scripts/relay_run_a_mirror_preflight.sh`
- `scripts/prepare_local_push_pull_run_a_runbook.py`
- `scripts/verify_capture_session_gate.sh`
- `captures/2026-05-14T230235Z_push-pull-run-a/` (Run A retest; gate WARN)
- `/tmp/wireshark_mcp_stimulus_test.pcapng` (2026-05-16 idle; hub→relay `pJP0000`)
- `/tmp/wireshark_mcp_pJP0000_confirm.pcapng` (2026-05-16 idle confirm)
- `/tmp/rest_stimulus_capture_20260516.pcapng` (2026-05-16 REST 547/557/563 + `[pfx]J` framing)
- `/Users/markminnoye/Downloads/capture_00:48.pcapng` (2026-05-17 Sprint 1 GESLAAGD; 1732 frames, 13× relay→hub reply, `I<CH><state>` bevestigd)
- `/Users/markminnoye/Downloads/00:55.pcapng` (2026-05-17 Sprint 2 GESLAAGD; 2164 frames, 15× relay→hub reply, prefix-byte mapping volledig)
- `/Users/markminnoye/Downloads/01:01.pcapng` (2026-05-17 Sprint 3 GESLAAGD; 2161 frames, bidirectioneel, dimmer I0154xxx semantiek decoded)
- `captures/sprint4_pov_comparison_20260517T012600Z/` (2026-05-17 Sprint 4 GESLAAGD; POV-vergelijking A=7←15, B=7←14, C=7←12, relay 547/557/563 OFF→ON→OFF, standaard-POV 7←15 aanbevolen)
- `captures/2026-05-17T210800Z_scan_modules/` (2026-05-17 Scan Modules wizard; UDP/10001 discovery probe + HTTP analyse docs)
- `captures/RE_WIZARDS_2026-05-17T214000Z_step3_save/` (2026-05-17 Step3 kanaalnaam-save; 37s pcap)
- `captures/RE_WIZARDS_2026-05-17T214900Z_full/` (2026-05-17 Full wizard; 46s pcap + HAR, alle POSTs)
- `captures/RE_WIZARDS_2026-05-17T215100Z_dimmer/` (2026-05-17 Dimmer wizard; 18s pcap + HAR, 8 kanalen)
- `resources_and_docs/reference/2026-05-17_RE_WIZARDS_PLAN.md` (RE Wizards — WebConfig `/general/Wizards/...`, URL-kaart, gateway-parity)
- `resources_and_docs/reference/2026-05-17_scan_modules_http_analysis.md`
- `resources_and_docs/reference/2026-05-17_scan_modules_udp_payloads.md`
- `resources_and_docs/evidence/2026-05-17_dimmer_I0154xxx_full_decode.md`
- `resources_and_docs/evidence/2026-05-17_ip1100_input_payload_decode.md`
- `resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md`
- `docs/superpowers/specs/2026-05-18-gateway-architecture-design.md`
- `gateway/` (Fase 1 codecs + Fase 2 hub: `udp_bus`, `device_registry`, `rest_shim`; zie README_gateway.md)
- `scripts/input_payload_parser.py`
- `resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md`
- `resources_and_docs/evidence/2026-05-22_sprint5_input_10-25_session_notes.md`
- `resources_and_docs/evidence/2026-06-02_relay_poll_i_ch_test.md` (relay `I<ch>` poll negative; `P0000` baseline confirmed)
- `scripts/test_relay_poll.py`
- `resources_and_docs/reference/2026-06-01_legacy_webservice_protocol_analysis.md` (legacy IPBox webservice `actions.php`; TCP-mnemonics `TGL/CLR/DIM/SET/INF/TAF/TAN` ↔ veldbus `C/T/I/S`; bevestigt `ipcom` als vertaallaag, sferen=centrale-logica, `<pfx>J`/`END` = transport-artefact; bron in `reference/legacy-ipbox-webservice/actions.php`)
- `/Users/markminnoye/Downloads/10:25.pcapng` (Sprint 5 input; mirror 7←13)
- `/Users/markminnoye/Downloads/10:22.pcapng` (Sprint 5 relais leg; mirror 7←14)
- `/Users/markminnoye/Downloads/capture dimmer.pcapng` (2026-06-22 dimmer P2P; POV dimmer-poort; 12 frames; input→dimmer `T/D1003/D1000` + hold-dim start/stop protocol)
