# Dimmer REST ↔ UDP/1001 timeline write-up (consolidated)

Last updated: 2026-05-14  
Bron-pcaps en manifests staan typisch onder `captures/` (lokaal, vaak `.gitignore`). Dit document vat de **reeds beschreven** correlaties samen als één leesbare tijdlijn.

## Capture context

- **Controller:** `10.10.1.40` (dimmer / Bureau-kanaal in eerdere runs).
- **Mirror:** destination **7** ← source **12** (dimmer switchpoort — niet **11**).
- **Zichtbare UDP-richting:** in de gedocumenteerde POVs vooral **`10.10.1.40` → `192.168.0.185`** (home-been IPBox); terug **`192.168.0.185` → `10.10.1.40`** niet gezien op mirror 12 / `en7` exports.
- **Payload-familie:** 8 ASCII bytes `I0154xxx` (kanaal `1` impliciet in prefix `I0154`).

## Run A — staged subagent (`dimmer_udp.pcapng`)

Stimulus: OFF → DIM 30 → DIM 70 → DIM 100 → OFF (22 s tussen stappen).  
Eerste betekenisvol frame binnen ~0–3 s na REST (zie brondoc voor exacte epoch-koppeling):

| REST (UTC)     | REST actie | Δt naar frame | payload_ascii |
| -------------- | ---------- | ------------- | ------------- |
| 20:26:14Z      | OFF        | ~0.34 s       | `I0154100`    |
| 20:26:36Z      | DIM 30     | ~1.18 s       | `I0154130`    |
| 20:26:59Z      | DIM 70     | ~0.71 s       | `I0154170`    |
| 20:27:22Z      | DIM 100    | ~0.36 s       | `I0154199`    |
| 20:27:44Z      | OFF        | ~1.56 s       | `I0154100`    |

Tussendoor veel `I0154999` — waarschijnlijk idle/poll; niet per REST-stap uniek.

## Run B — 62 s mirror12 (`dimmer572_mirror12_en7_udp1001.pcapng`)

REST-cyclus DIM 50 → 100 → OFF op **`id=572`**; **6** UDP/1001 frames `10.10.1.40`→`192.168.0.185` in 150 totale frames:

| t_rel_s | payload_ascii |
| ------- | ------------- |
| 0.000   | `I0154150`    |
| 2.305   | `I0154199`    |
| 4.602   | `I0154100`    |
| 11.393  | `I0154999`    |
| 31.388  | `I0154999`    |
| 51.399  | `I0154999`    |

Zelfde familie als Run A; exacte 1:1 REST-stap mapping voor Run B staat in de brondoc voor detailtiming.

## Run C — bidirectional probe

Zelfde stimulus; BPF `(host 10.10.1.40 or host 192.168.0.185) and udp port 1001`.  
Resultaat: **12** frames `10.10.1.40`→`192.168.0.185`, **0** terug. Conclusie: op deze POV blijft UDP/1001 unidirectioneel.

## Optionele her-run (niet automatisch uitgevoerd in repo)

1. UniFi **7←12**, daarna `dumpcap` op `en7` met `host 10.10.1.40 and udp port 1001`.
2. `./scripts/dimmer_only_re_stimulus.sh` (default 22 s tussen stappen).
3. `python3 scripts/correlate_capture_session.py <session> --verdict-profile dimmer --rest-ip <jouw-ipbox-host>`
4. Mirror terug naar **`7←15`** (standaard hub) of **`7←14`** (relay-poort-POV) indien nodig.

## Bronnen

- [2026-05-03_dimmer_udp_payload_correlation.md](2026-05-03_dimmer_udp_payload_correlation.md) — volledige tabellen en hypotheses.
- [CAPTURE_LIVE_STATUS.md](../workflows/CAPTURE_LIVE_STATUS.md) — mirrorpoorten en aanbevolen vervolgstap.
