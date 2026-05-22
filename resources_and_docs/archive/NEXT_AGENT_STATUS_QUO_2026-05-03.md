# Status Quo Handoff for Next Agent (2026-05-03)

> Canonieke actuele RE-status staat uitsluitend in `resources_and_docs/RE_STATE.md` (source of truth).  
> Dit handoff-document is geen actuele statusbron; het blijft een historical snapshot + evidence pointers (append-only referentie).

## Executive conclusion

- Relay-path reverse engineering has meaningful signal and repeatable UDP/1001 payload patterns.
- **State correction:** eerdere analyse was deels te narrow; direction-aware export en relay reply candidate parsing bestaan nu en moeten als baseline tooling gebruikt worden.
- **Current state:** captures werken doorgaans; analysepipeline is gecorrigeerd; semantiek van meerdere reply payload families blijft open.
- **Update:** With mirror **7←12**, a **62s** `en7` capture recorded **150** frames including **6×** UDP/1001 from `10.10.1.40`→`192.168.0.185` during REST `id=572` (see `captures/2026-05-03T200521Z_dimmer572_mirror12_cycle_notes.md`).
- **Staged subagent run (zelfde avond):** mirror **7←12**, **150 s** `dumpcap`, daarna `scripts/dimmer_only_re_stimulus.sh` (OFF → DIM 30/70/100 → OFF, **22 s** tussen stappen). **12** UDP/1001-pakketten, allemaal **`10.10.1.40` → `192.168.0.185`**. Manifest + `tshark`-tijden sluiten aan bij de REST-stappen; HTTP-`statuses` toont Bureau-kanaal (`id` 1) oplopend **0 → 2 → 33 → 70** na DIM 30/70/100.
- **Hex-correlatie nu uitgeschreven:** zie `resources_and_docs/evidence/2026-05-03_dimmer_udp_payload_correlation.md` (patroon `I0154xxx`; o.a. `100/130/170/199/999` suffixes in responsframes).
- A temporary network regression on `10.10.1.40` occurred during earlier UniFi mirror experiments and was restored.
- **Late-night network incident + recovery:** IPBox (`192.168.0.185`, MAC `00:30:18:00:49:3c`) werd "onvindbaar" nadat die op US16 poort 8 stond terwijl die poort op `op_mode=mirror` bleef. Herstel is uitgevoerd door poort 8 terug op `op_mode=switch`, `forward=native` te zetten. Ping + REST (`/api/v1/comp/items`) werkten daarna opnieuw.
- **CGW capture trial result:** eerste capturebestand (`captures/2026-05-03T214724Z_cgw_bidir_udp1001.pcap`) bevat **0 packets** (lege pcap, 24 bytes), dus nog geen bruikbare bidirectionele UDP/1001-data vanaf CGW-POV.

## What is validated

1. Full orchestrator run succeeded:
   - `captures/2026-05-03T192700Z_golden-protocol-capture/`
   - Required artifacts exist (`capture.pcapng`, `manifest.jsonl`, `run.log`, snapshots).
2. Relay (`10.10.1.30`) mirrored stream is visible and useful:
   - payload family repeatedly observed: `I001001000`, `I000100000`, `P000000000`.
3. Current dimmer controller reachability:
   - `10.10.1.40` responds again to ping and `http://10.10.1.40/api.html?method=statuses`.

## What is not validated

- Volledige commandrichting voor dimmers: op huidige mirror-POV is nog steeds geen `192.168.0.185 -> 10.10.1.40` UDP/1001 zichtbaar.
- Mac-originated UDP injection visibility on the current mirror vantage remains inconclusive.
- Betrouwbare capture vanaf CGW (`tcpdump -i any`) is nog niet bevestigd; eerste test leverde lege pcap op.

## Current network state to keep

- Switch: `Unify Switch 16` (`b4:fb:e4:54:83:7c`)
- **Operator-canon (mirror):** standaard **`7←15`** (IPBox veld-been / hub); **`7←14`** alleen **secondair** voor relay-switchpoort-POV — zie [CAPTURE_LIVE_STATUS.md](../workflows/CAPTURE_LIVE_STATUS.md) en [2026-05-14_relay_run_a_operational_playbook.md](../workflows/2026-05-14_relay_run_a_operational_playbook.md). *(Historische snapshot 2026-05-03: dest `7`, bron `14` relay-pad — niet meer als primaire leidraad lezen.)*
- IPBuilding native-profile intent restored on ports `12`, `13`, `14`
- **Belangrijk:** laat poort `8` (IPBox) in normale switch/access-mode; nooit als mirror-bron laten staan als de IPBox in dienst moet blijven.
- Do not leave experimental mirror overrides active after tests.

## High-risk lesson learned

- UniFi mirror override semantics are easy to misapply.
- Partial/incorrect override sets can break VLAN/native forwarding behavior and temporarily make `10.10.1.40` unreachable.
- Always do preview first, then apply, then immediate reachability check.

## Recommended next action

1. **Topologie eerst valideren:** bevestig fysiek/logisch waar de IPBox nu hangt (user note: "geen IPBOX meer aan de cloud gateway"), en check dat `192.168.0.185:30200` stabiel bereikbaar blijft tijdens captures.
2. **CGW live sanity-check vóór file capture:** op CGW eerst zonder `-w` draaien (`tcpdump -ni any "udp port 1001 and (host 10.10.1.40 or host 192.168.0.185)"`) en pas bij zichtbare live frames opslaan naar `/tmp/*.pcap`.
3. Herhaal dimmer-stimulus (`id=572`) tijdens CGW-capture; verifieer daarna direction counts met `tshark` (verwacht beide richtingen als POV correct is).
4. Zodra bidirectioneel bevestigd is, herhaal op dimmerkanaal `id=571` om kanaalafhankelijkheid van `I0154xxx` te toetsen.

**Lokale artefacten (map `captures/` staat in `.gitignore`; pad geldt op de machine waar de run draaide):** `captures/_subagent_dimmer_20260503T202559Z/dimmer_udp.pcapng`, `dimmer_re_manifest.log`, **`RUN_REPORT.md`** (samenvatting + `tshark` + manifest-kop), plus recapture `captures/_dimmer_recap_20260503T203917Z/dimmer_bidir_probe.pcapng` (ook unidirectioneel `10.10.1.40 -> 192.168.0.185`).

**Completed guarded dimmer cycle (mirror 12):** `captures/2026-05-03T210500Z_port_overrides_snapshot_pre_dimmer12_mirror.json`, pcap `captures/2026-05-03T200521Z_dimmer572_mirror12_en7_udp1001.pcapng`, notes `captures/2026-05-03T200521Z_dimmer572_mirror12_cycle_notes.md`. Earlier mistaken **7←11** attempt: `captures/2026-05-03T200500Z_guarded_dimmer_mirror_cycle_notes.md`.

## Files to read first

- `resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md`
- `captures/2026-05-03T192700Z_golden_protocol_capture_notes.md`
- `captures/2026-05-03T192700Z_rest_step_payload_correlation.md`
- `captures/2026-05-03T194100Z_unifi_mcp_dimmer_mirror_attempt_notes.md`
