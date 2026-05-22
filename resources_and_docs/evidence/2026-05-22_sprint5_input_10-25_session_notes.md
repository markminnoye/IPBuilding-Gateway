# Sprint 5 — input mirror session `10:25.pcapng`

Last updated: 2026-05-22

**Capture:** `/Users/markminnoye/Downloads/10:25.pcapng` (archived: `captures/2026-05-22T102500Z_sprint5-manual-10-25/`)

**Mirror:** UniFi **7←13** (source port **13** = IP1100 input `10.10.1.50`)

**Duration:** ~48 s | **UDP/1001 input pairs:** 60 (24 hub→input polls, 24 idle replies, **12 button events**)

## Operator scenario (A/B/C, ~5 s between on/off)

| Button | Intended load | Wire button id (getButtons) | Event times (press / release pairs) |
|--------|---------------|----------------------------|-------------------------------------|
| **A** | Inkom (relais ch10) | `2D2F8185190000DF` — **Woonkamer hal L** (func1 → relay `.30` ch **10**) | ~4.8 s / ~12.1 s |
| **B** | Living (dimmer) | `2DDC5D851900008B` — **Trap R** (func1 → dimmer `.40` ch **0**) | ~14.8 s / ~22.2 s |
| **C** | Traphal (relais ch14) | `2D1E6A85190000AF` — **Trap L** (func1 → relay `.30` ch **14**) | ~30.8 s / ~38.0 s |

Physical labels A/B/C may not match UI names; correlate via **6-byte id core** in the event frame and `getButtons` `id` field (middle bytes).

## Payload families

### Hub→input poll (4 bytes)

- ASCII: `I0000`
- Cadence: ~2 s

### Idle reply (14 bytes)

```
49 02 52 05 02 04 00 00 00 00 00 00 00 45
I  .  R  [status 3B]  [7× pad]            E
```

Unchanged between polls when no button event.

### Button event (13 bytes) — **new**

```
42 2d [id_core 6B] [suffix 1B] 03 [01|00] 00 45
B  -   ...........  .           ^press/release  E
```

| Field | Bytes | Meaning |
|-------|-------|---------|
| Prefix | `B-` (`0x42 0x2d`) | Event (vs idle `I\x02R`) |
| `id_core` | 6 | Matches bytes from `getButtons` `id` (e.g. `2F8185190000`) |
| `id_suffix` | 1 | Last byte of `getButtons` `id` before constant `03` (e.g. `DF`, `8B`, `AF`) |
| Edge | `01` / `00` | **press** / **release** (~200 ms pair per physical action) |
| Suffix | `0x45` (`E`) | End marker (shared with idle family) |

Example press: `422d2f8185190000df03010045`  
Example release: `422d2f8185190000df03000045`

## Cross-capture path (three mirrors)

| Mirror | Sees |
|--------|------|
| 7←14 relais | Hub→relais `Txxxx` / `I000…` ([10:22](2026-05-22T102200Z_sprint5-manual-10-22)) |
| 7←13 input | Input events `B-…E` (this capture) |
| Hub | Processes input → sends relais/dimmer commands (not on module ports) |

## Code

- `gateway/payloads/input.py` — `input_button_event` decode
- `scripts/input_payload_parser.py` — delegates to gateway

## Status

Sprint 5 **input wire format: confirmed** on mirror 7←13. Dimmer command bytes still require hub or dimmer POV for button B effect on `10.10.1.40`.

**Sprint closure:** [2026-05-22_sprint5_input_physical_completion.md](2026-05-22_sprint5_input_physical_completion.md) (all three manual captures, architecture, open logical-flow work).
