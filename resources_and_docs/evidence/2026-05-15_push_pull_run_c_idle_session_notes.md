# Push/pull Run C — idle/poll venster (sessienotities)

**Datum lokaal:** 2026-05-15 (capture-map UTC-prefix `2026-05-14T214905Z`)

## Sessie

- **Map:** `captures/2026-05-14T214905Z_push-pull-run-c-idle/`
- **Runbook:** [push_pull_run_c_idle_runbook.yaml](push_pull_run_c_idle_runbook.yaml) — alleen `inventory_snapshot`, daarna **150 s** idle (`settle_after_steps_seconds`), **geen** relay-REST-stimulus.
- **REST:** inventory naar `http://192.168.0.185:30200/api/v1` (zie `manifest.jsonl`).

## PCAP / correlate

- `capinfos`: **98 packets**
- **UDP direction summary (top):** `10.10.1.1:50446 → 10.10.1.50:1001` (78×), `10.10.1.1:50445 → 10.10.1.30:1001` (8×), `10.10.1.1:50447 → 10.10.1.40:1001` (8×); plus **4×** `10.10.1.1:61581 → 239.255.255.250:3702` (WS-Discovery SOAP op UDP — staat in **Unparsed** export).
- **Relay command summary:** `P0000` **pulse** kanaal **0** — **8×** (achtergrond / hub→relay zonder bijbehorende Run A OFF→ON→OFF in deze sessie).
- **Relay status (parsed):** geen records in export.
- **STATUS_VERDICT_GATE: WARN** (zelfde POV-limiet: geen `10.10.1.30 → 10.10.1.1` in filterexport).

## Interpretatie (kort)

- `I0000`-cadans naar **10.10.1.50** domineren — past bij **idle/poll-baseline** uit eerdere A/B/C-contractdocumentatie ([CAPTURE_LIVE_STATUS.md](../workflows/CAPTURE_LIVE_STATUS.md), [2026-05-05_push_pull_experiment_contract.md](2026-05-05_push_pull_experiment_contract.md)).
- Hub→relay **P0000** blijft zichtbaar zonder expliciete REST-acties in dit venster; nuttig als referentie tegenover command-gedreven runs (quiet-evening / Run A).

## Herhalen

```bash
./scripts/relay_run_c_idle_capture.sh
# of:
.venv/bin/python ipbuilding_capture_run.py --runbook resources_and_docs/workflows/push_pull_run_c_idle_runbook.yaml --interface en7 --non-interactive
```

Zelfde mirror-POV als relay-testen: **standaard `7←15`** (IPBox-been); **`7←14`** alleen als je expliciet de relay-switchpoort wilt spiegelen. Na afloop mirror terugzetten indien nodig.

## Sessie 2 (herhaal — operator mirror)

- **Map:** `captures/2026-05-14T220109Z_push-pull-run-c-idle/`
- `capinfos`: **94 packets**; **STATUS_VERDICT_GATE: WARN**
- Zie `udp_ipbox_export.txt` in die map voor richting-samenvatting (vergelijkbaar met sessie hierboven; klein verschil in packetcount door tijdvenster/achtergrond).
