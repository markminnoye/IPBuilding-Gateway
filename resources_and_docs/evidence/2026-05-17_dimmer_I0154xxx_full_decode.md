# Dimmer `I0154xxx` full decode (Sprint Dimmer)

Last updated: 2026-05-17

**Evidence:** `/Users/markminnoye/Downloads/01:01.pcapng` (Sprint 3, mirror 7←12, 2161 frames, 100s), `captures/2026-05-04T122545Z_dimmer_sweep_571_572_573/`, [2026-05-04_dimmer_channel_value_sweep.md](2026-05-04_dimmer_channel_value_sweep.md).

## Bidirectional check

| Endpoint | Tx | Rx | Verdict |
|----------|----|----|---------|
| `10.10.1.40:1001` | 11 | 11 | PASS (bidirectional) |

Reply latency hub→dimmer command → dimmer reply: **~11–25 ms** (well under 500 ms gate).

## Reply structure: `I0154xxx` (8-byte ASCII)

```
I  01  54  xxx
│  │   │   └── internal value-code (3 digits)
│  │   └────── dimmer family constant (always "54" in captures)
│  └────────── device type (01 = IP0300 dimmer module)
└───────────── status/reply prefix (same as relay status family)
```

**Confirmed:** suffix `xxx` is an **internal value-code**, not a direct 0–100% PWM level. REST `DIM 30` correlates with wire `I0154030`; REST `DIM 99` with `I0154099`.

## Hub→dimmer command shape (no `J` separator)

Dimmer uses **compound first byte** (channel + direction encoded), unlike relay `[pfx]J<cmd>`:

| Wire (hex→ASCII) | REST / meaning | Reply |
|------------------|----------------|-------|
| `I9900` | idle poll | (none in burst) |
| `S0301030` | DIM 30%, ch 03 | `I0154030` |
| `S0701030` | DIM 70%, ch 07 | `I0154070` |
| `S0991030` | DIM 99%, ch 09 | `I0154099` |
| `C0991030` | OFF, ch 09 | `I0154000` |
| `S1501030` | DIM 50%, ch 15 | `I0154150` |
| `C1991030` | OFF, ch 19 | `I0154100` |

Proto-map v0.2 (hub command): `<S|C><channel><value_code>1030`

- `S` = set/dim, `C` = cut/off
- `<channel>` = single digit channel index (0–7 per IP0300)
- `<value_code>` = `10`–`90` for DIM 10–90%, `99` for DIM 100%

## Value-code ↔ REST DIM mapping

| Value-code | REST DIM % | Notes |
|------------|------------|-------|
| `000` | OFF | After `C*` command |
| `030` | 30 | Direct mapping in Sprint 3 capture |
| `070` | 70 | Direct mapping |
| `099` | 99 | Direct mapping (not 100 — use `100` code below) |
| `100` | 100 | Seen as `I0154100` after high DIM |
| `150` | 50 | `S1501030` → `I0154150` |
| `999` | poll/idle | Background `I9900` family |

## Soft AAN / Soft UIT calibration (§12.3)

From [IPBUILDING_KNOWLEDGE.md](IPBUILDING_KNOWLEDGE.md) §12.3:

- **Soft AAN** default 15%: lamp ramps to 15% first, then soft-up to target.
- **Soft UIT** default 70%: lamp ramps to 70%, then soft-down to 0%.

**Implication:** commanding REST `DIM 1%` may produce physical ~15% before ramping; wire value-code reflects **commanded setpoint**, not instantaneous PWM. Gateway must apply EEPROM `dimMin`/`dimMax` when translating user-facing %.

## Open questions

- Exact PWM timing curve vs value-code (needs `api.html?method=statuses` correlate when IPBox live).
- Whether all 8 channels (571–578) use identical `I01` + `54` prefix (only ch 0–2 seen in sweep pcaps).

## Parser references

- `scripts/dimmer_payload_parser.py` — hub commands `S*`/`C*`/`I9900`
- `gateway/payloads/dimmer.py` — gateway encoder/decoder including `I0154xxx`
