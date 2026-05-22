# Relay quiet-evening capture — sessienotities (2026-05-14)

## Sessie A (lege pcap — mirror nog niet / verkeerde POV)

- **Map:** `captures/2026-05-14T213152Z_push-pull-run-a-quiet-evening/`
- **Runbook:** [push_pull_run_a_quiet_evening.yaml](push_pull_run_a_quiet_evening.yaml)
- `capinfos`: **0 packets**; correlate: **STATUS_VERDICT_GATE: WARN**, geen UDP-regels.

## Sessie B (mirror actief — bruikbare UDP)

- **Map:** `captures/2026-05-14T214007Z_push-pull-run-a-quiet-evening/`
- **Runbook:** zelfde quiet-evening (IDs **547, 557, 563**)
- **REST-basis:** `http://192.168.0.185:30200/api/v1` — alle negen stappen HTTP 200 (`run.log` / `manifest.jsonl`)

### PCAP / export

- `capinfos`: **49 packets**
- UDP-richting (samenvatting): dominant `10.10.1.1:50445 → 10.10.1.30:1001` (relay-commando’s) en `10.10.1.1:50446 → 10.10.1.50:1001` (`I0000` poll-cadans); ook `10.10.1.1:50447 → 10.10.1.40:1001` (`I9900`)
- Zichtbare relay-command frames o.a. `C0000`, `S0000`, `C1000`, `P0000`, en stappen voor kanaal **16** (`C1600`/`S1600` in export — zie volledige tabel in `udp_ipbox_export.txt`)
- **Relay command summary (parsed):** o.a. `off`/`on` kanalen **0, 10, 16** — in lijn met IDs 547/557/563 (`channel = ID - 547`)
- **Relay status summary:** geen parseerbare `relay_status` in deze export
- **STATUS_VERDICT_GATE: WARN** — geen **terug**richting `10.10.1.30 → 10.10.1.1` (of naar `192.168.0.185`) in de gefilterde export; command-correlatie is wél zinvol, harde “geen reply”-claims niet.

### Conclusie sessie B

Met mirror naar **en7** is **UDP/1001 veldbusverkeer** nu zichtbaar; quiet-evening-runbook levert reproduceerbare REST + pcap voor relay **547/557/563**.

## Sessie C (herhaal — operator mirror / port capture)

- **Map:** `captures/2026-05-14T220000Z_push-pull-run-a-quiet-evening/`
- **PCAP:** **48 packets**; correlate **STATUS_VERDICT_GATE: WARN**
- **Relay command summary (parsed):** zelfde patroon als sessie B (`off`/`on` kanalen 0, 10, 16; `P0000` pulse); geen unparsed WS-Discovery in deze export (verschil t.o.v. sommige andere pcaps).

## Python-omgeving (PEP 668)

Scripts gebruiken `.venv/bin/python` indien aanwezig; anders `python3 -m venv .venv` + `pip install -r requirements-capture.txt`.
