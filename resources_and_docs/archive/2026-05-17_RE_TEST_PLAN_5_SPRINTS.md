# IPBuilding Protocol RE — 5-Sprint Test Plan

> **Status: CLOSED (2026-05-22)** — Alle sprints geslaagd. Canonieke status: [RE_STATE.md](../RE_STATE.md). Volgende: Gateway Fase 2 — [architectuurdoc](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md).

**Doel (historisch):** Fase 1 reverse engineering van UDP/1001 voltooien zodat de gateway-implementatie kan starten.

**Werkwijze:** Wireshark MCP voor alle captures (`wireshark_capture` + `wireshark_stats_endpoints`). `ip.src==X` filters **vermijden** — altijd `ip.addr==X` of endpoints gebruiken. Tooling: zie `AGENTS.md`.

**Hard requirement per sprint:** `wireshark_stats_endpoints(type="udp")` toont **Rx > 0** voor alle devicepairs voordat een sprint als geslaagd geldt.

---

## Sprint 1 — Relay bidirectionaliteit (60s actief)

**Hypothesis:** relay→hub replies zijn zichtbaar in een voldoende lange actieve capture met goede mirror-POV.

### Setup

- **Mirror:** `7←15` (IPBox hub-been, standaard)
- **Capture:** `dumpcap` 60s, `udp port 1001`, geen hostfilter
- **Stimulus:** REST `192.168.0.185:30200` → relay IDs `547/557/563/570` OFF→ON→OFF met ~3s pauzes
- **Duur:** ~60s capture + ~20s pauze na laatste stimulus = ~80s totaal

### Stappen

1. Start capture: `wireshark_capture(interface="en7", output_file="/tmp/sprint1_relay_bidir.pcapng", duration_seconds=60, capture_filter="udp port 1001")`
2. Wacht 5s rust
3. REST 547 ON/OFF (elk ~3s apart)
4. REST 557 ON/OFF (elk ~3s apart)
5. REST 563 ON/OFF (elk ~3s apart)
6. REST 570 ON/OFF (elk ~3s apart)
7. Wacht 20s extra
8. Stop capture

### Criteria voor geslaagd

- `wireshark_stats_endpoints("sprint1_relay_bidir.pcapng", type="udp")` toont **Rx > 0** voor `10.10.1.30:1001`
- Relay reply payload families zichtbaar (`P000000000` of andere)
- `tshark -x` hex dump toont relay→hub payloads > 0
- `STATUS_VERDICT_GATE: PASS` in `correlate_capture_session.py` output

### Bewijs te verzamelen

- `pcap` + `wireshark_stats_endpoints` screenshot
- `tshark -x` hex van relay→hub frames
- Relatieve timing t.o.v. laatste hub→relay `P0000` (ms resolution)

### Risico's en mitigatie

| Risico | Mitigatie |
|--------|-----------|
| Mirror niet actief | Vooraf check: `ping 10.10.1.30` + `wireshark_list_interfaces` |
| POV toch te smal | Herhaal met `7←14` (relay-poort) als alternatief |

---

## Sprint 2 — Prefix-byte semantiek

**Hypothesis:** het eerste byte vóór `J` (`m`/`}`/`g`/`w`/`p`) is niet willekeurig maar correleert met command-type (S/C/P) en mogelijk met UDP-sequentie of lengte.

### Setup

- **Mirror:** `7←15` (of `7←14` als Sprint 1 bevestigt dat replies beter zichtbaar zijn via relay-poort)
- **Capture:** 30s, `udp port 1001`
- **Stimulus:** aparte REST-calls voor elk command-type:
  1. `547 ON` (S-type)
  2. `547 OFF` (C-type)
  3. Idle 15s (P-type pulse)
  4. `557 ON` (S-type, ander kanaal)
  5. `563 ON` (S-type, kanaal 16)
  6. Scene `100064 ON` (ter referentie)
  7. Dimmer `571 DIM 50` (ter referentie)

### Verwachte mapping opbouwen

| REST | Verwachte wire payload | Prefix-byte |
|------|-----------------------|-------------|
| relay ON (S) | `[pfx]JS<CH>00` | ? |
| relay OFF (C) | `[pfx]JC<CH>00` | ? |
| idle pulse | `[pfx]JP0000` | `p` (al gezien) |
| dimmer DIM | `[pfx]JI<CH><val>` | ? |
| scene | anders? | ? |

### Stappen

1. Start capture 30s
2. Wacht 3s → RELAY ON (S)
3. Wacht 5s → RELAY OFF (C)
4. Wacht 10s → dimmer DIM 50
5. Wacht 10s → dimmer OFF
6. Wacht 5s → scene trigger
7. Wacht 5s → stop capture

### Criteria voor geslaagd

- Minimaal 5 verschillende frames met uiteenlopende prefixes vastgelegd
- Elke REST-actie heeft een correleerbare wire-frame binnen 500ms
- Pattern matrix gevuld: `S` → prefix?, `C` → prefix?, `P` → `p` (confirmed)

### Bewijs te verzamelen

- Frame-tabel: timestamp | REST actie | prefix | kern
- Hypothese: `S` altijd `m` of `g`? `C` altijd `}` of `w`?

---

## Sprint 3 — Dimmer volledige correlatie

**Hypothesis:** dimmer volgt zelfde `[pfx]J`-framing als relay; `I0154xxx` replies correleren met DIM-stappen (0→30→70→100→OFF) en zijn zichtbaar op `7←12`.

### Setup

- **Mirror:** `7←12` (dimmer `10.10.1.40`) — bewezen eerder, maar nu met `[pfx]J`-kennis
- **Capture:** 90s, `udp port 1001`
- **Stimulus:** dimmer IDs `571/572` OFF→DIM30→DIM70→DIM100→OFF

### Stappen

1. Start capture
2. DIM 571 30% → wacht 10s
3. DIM 571 70% → wacht 10s
4. DIM 571 100% → wacht 10s
5. DIM 571 OFF → wacht 10s
6. Herhaal voor dimmer `572`
7. Wacht 20s rust
8. Stop capture

### Criteria voor geslaagd

- Alle dimmer frames in `wireshark_stats_endpoints` (type="udp") tonen Rx > 0
- `I0154xxx` payload families correleren met DIM-level stappen
- Timestamp van dimmer reply vs REST DIM-call < 500ms

### Bewijs te verzamelen

- Frame-tabel per dimmer-ID: timestamp | DIM level | wire payload
- Hex van I0154xxx frames voor semantische analyse (suffix betekenis)

---

## Sprint 4 — POV-vergelijking (3 mirrors)

**Hypothesis:** verschillende mirror-bronnen tonen verschillende subsets van het bidirectionele verkeer; combinatie geeft volledig beeld.

### Setup

- **Drie captures**, identieke stimulus:
  - A: `7←15` (IPBox hub / veldbus been)
  - B: `7←14` (relay-switchpoort)
  - C: `7←12` (dimmer-poort)
- **Stimulus:** zelfde als Sprint 1 (relay 547/557/563/570 ON/OFF)
- **Duur:** ~45s per capture, direct na elkaar

### Stappen per capture

1. Start capture A (45s)
2. Rust 5s
3. Relay 547 ON/OFF
4. Rust 5s
5. Relay 557 ON/OFF
6. Rust 5s
7. Relay 563 ON/OFF
8. Rust 15s
9. Stop
10. Herhaal voor B en C

### Criteria voor geslaagd

- Alle 3 captures tonen relay→hub Rx > 0 (als Sprint 1 geslaagd is)
- Vergelijkende tabel: welke POV toont welke reply-families?
- Minimale set POV's bepaald voor toekomstige captures (wat is *nodig* vs *voldoende*?)

### Bewijs te verzamelen

- Vergelijkingstabel: mirror | relay→hub count | dimmer→hub count | input→hub count
- Aanbeveling: welke mirror als standaard voor welk doel

---

## Sprint 5 — Fysieke input + gateway-validatie

**Status (2026-05-22):** GESLAAGD — wire payloads + `getButtons` correlatie. Completion doc: [2026-05-22_sprint5_input_physical_completion.md](../evidence/2026-05-22_sprint5_input_physical_completion.md). Logische centrale-flow: **open** (later).

**Hypothesis:** fysieke druk op IP1100-knopen genereert herkenbare wire-payloads; gateway kan dit reproduceren.

### Setup

- **Mirror:** `7←15` (brede hub-POV)
- **Capture:** 90s, `udp port 1001`
- **Stimulus:**
  - Fysieke druk op bekende knopen (Keuken, Inkom, Woonkamer — zie `ip1100_getbuttons_pre.json`)
  - Gecombineerd met REST relay ON/OFF als referentie

### Stappen

1. Start capture
2. Snapshot `getButtons` via `http://10.10.1.50/api.html?method=getButtons` → `ip1100_buttons_pre.json`
3. Druk fysieke knop A (kort)
4. REST relay ON
5. Druk fysieke knop B (kort)
6. REST relay OFF
7. Druk fysieke knop C (kort)
8. Snapshot `getButtons` → `ip1100_buttons_post.json`
9. Wacht 20s
10. Stop capture

### Criteria voor geslaagd

- Wire payloads voor fysieke druk geïdentificeerd (binary `I\x02...E` families)
- `getButtons` pre/post verschil correleert met wire-events
- Gateway-implementatie hypothese: als IPBox een `scene`-trigger stuurt, volgt zelfde framing als relay-commando's

### Bewijs te verzamelen

- Frame-tabel: timestamp | fysieke actie | wire payload | `getButtons` veld
- Check: is er een `P0000` van hub voorafgaand aan fysieke druk-reply?

---

## Algemene regels

1. **Tool:** altijd `wireshark_capture` (MCP) voor captures; `wireshark_stats_endpoints` voor bidirectionele check
2. **Manifest:** noteer mirror-config + UTC + REST-IP in `README.txt` per capture
3. **Hex:** altijd `tshark -x` voor payload-analyse; `ip.src` filters vermijden
4. **Gateway-immunity:** als een capture 0× relay→hub toont, is dat een POV-limiet — niet een protocolfeit
5. **Afsluiten sprint:** na elke sprint: `RE_STATE.md` bijwerken, beslissing vastleggen (herhalen/doorgaan/STOP)

## Prioriteitsvolgorde

```
Sprint 1 → Sprint 2 → Sprint 3 → Sprint 4 → Sprint 5
```

Sprint 4 (POV-vergelijking) gaat pas na Sprint 1+2+3 als de basis-framing en reply-zichtbaarheid bevestigd zijn.

---

*Generated: 2026-05-17. Update telkens `RE_STATE.md` na afloop van elke sprint.*