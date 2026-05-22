# IP1100 input module UDP/1001 payload decode (Sprint Input)

Last updated: 2026-05-22

**Evidence:** `captures/sprint4_pov_comparison_20260517T012600Z/pov_a_7x15.pcapng` (mirror 7←15, 39× input↔hub pairs), `captures/2026-05-05T1040Z_user-full-capture/`, [RE_WIZARDS Configuration stack analysis](../reference/2026-05-17_RE_WIZARDS_Configuration_stack_analysis.md).

## Bidirectional check (POV-A)

| Endpoint | Direction | Count (approx) |
|----------|-----------|----------------|
| `10.10.1.1 → 10.10.1.50` | hub poll | 39 |
| `10.10.1.50 → 10.10.1.1` | input reply | 39 |

## Hub→input poll: `I0000`

| Field | Value |
|-------|-------|
| ASCII | `I0000` |
| Hex | `49 30 30 30` |
| Length | 4 bytes |
| Cadence | ~2 s (same order of magnitude as relay `I0000` idle poll) |
| Direction | `10.10.1.1` → `10.10.1.50` |

**Note:** Documented elsewhere as `FIND` (0x494630); in ASCII captures the visible form is **`I0000`** (four ASCII chars). Treat as **input poll / keepalive**, not a button-event.

## Input→hub reply: binary `I\x02R…E` family

Fixed **14-byte** payload observed on every poll response in POV-A:

```
Hex:  49 02 52 05 02 04 00 00 00 00 00 00 00 45
      I  .  R  .  .  .  [8× zero pad]         E
```

| Offset | Byte | Interpretation | Confidence |
|--------|------|----------------|------------|
| 0 | `0x49` (`I`) | Frame prefix (shared with relay/dimmer `I` family) | confirmed |
| 1 | `0x02` | Sub-type / protocol version marker | confirmed (constant in POV-A) |
| 2 | `0x52` (`R`) | Likely "Reply" or module-ready marker | hypothesis |
| 3–5 | `05 02 04` | Status / port bitmap — unchanged in idle poll | hypothesis |
| 6–12 | `00…00` (7 bytes) | Padding / unused | confirmed |
| 13 | `0x45` (`E`) | End marker | confirmed |

**Idle behaviour:** In POV-A (relay REST stimulus only, no physical button press), **every** poll gets the **same** 14-byte reply.

## Input→hub button event: `B-…E` family (13 bytes) — Sprint 5 confirmed

**Evidence:** `10:25.pcapng` / `captures/2026-05-22T102500Z_sprint5-manual-10-25/` (mirror **7←13**, physical presses).

```
Hex:  42 2d [id_core ×6] [id_tail ×2] 03 [01|00] 00 45
      B  -  ...........  ..          press/release  E
```

| Field | Meaning | Confidence |
|-------|---------|------------|
| `B-` | Event frame (not idle `I\x02R`) | confirmed |
| `id_core` + `id_tail` | Embed `getButtons` hardware `id` (8 hex chars) | confirmed |
| `03` + `01`/`00` | Press vs release edge | confirmed |
| `E` | End marker | confirmed |

Each physical press typically emits **press then release** ~200 ms apart. Session notes: [2026-05-22_sprint5_input_10-25_session_notes.md](2026-05-22_sprint5_input_10-25_session_notes.md).

## Correlation with `getButtons`

From [IPBUILDING_KNOWLEDGE.md](IPBUILDING_KNOWLEDGE.md) §2C / §12.4:

- Logical buttons use hardware IDs with prefix `B` (button), `V` (LED), etc.
- Wire event carries **embedded hardware `id`** (6+1 bytes), not the full REST entity id.
- Event `id_core`/`id_suffix` match substrings of `getButtons[].id` (e.g. `2D2F8185190000DF` → core `2f8185190000`, suffix `df`).
- `func1`/`func2` on the module (`ip` = last octet, `ch` = channel) describe **local** targets; IPBox project logic that turns a press into hub commands is **not** on this wire — see below.

## End-to-end flow (slave mode) — wire vs logic

**Architectuurdoel:** in slave-modus meldt de input alleen *welke knop* (`B-…E`); de **hub beslist** welke uitgangen/dimmers/scenes (en eventueel meer) worden aangestuurd. Zie mermaid + tabel in [2026-05-22_sprint5_input_physical_completion.md § Architectuurdoel](2026-05-22_sprint5_input_physical_completion.md#architectuurdoel).

**Confirmed on Ethernet (Sprint 5):**

1. Hub `10.10.1.1` polls input `10.10.1.50` with `I0000` (~2 s).
2. On press: input sends `B-…E` **only** to `10.10.1.1`.
3. Hub sends relay/dimmer commands (`T`/`S`/`C`/dimmer families) to `.30` / `.40` — visible on hub or relay/dimmer mirror, **not** on input port mirror.

**Deferred (define later):**

- Exact **centrale** mapping `B-…E` → actielijst (IPBox WebConfig, comp/items, scenes, `FlashAutonomyToModule`).
- **Autonomous** path (centrale down): module EEPROM may command `.30`/`.40` directly — not captured on wire.

Master write-up: [2026-05-22_sprint5_input_physical_completion.md](2026-05-22_sprint5_input_physical_completion.md).

## Centrale IP on the input module

- Module HTTP `getSysSet` / `backupConfig`: `network.gateway` = **`10.10.1.254`** (router), **no** field `10.10.1.1`.
- Traffic none the less uses **`10.10.1.1`** as hub UDP peer → likely **fixed convention** and/or **address learned from poll source** (latter not wire-proven).

## Parser references

- `scripts/input_payload_parser.py` — poll, idle reply, button event
- `gateway/payloads/input.py` — encode poll + decode all three families
