# Dimmer `I0154xxx` full decode (Sprint Dimmer)

Last updated: 2026-06-03 (channel-prefix correction)

**Evidence:** `/Users/markminnoye/Downloads/01:01.pcapng` (Sprint 3, mirror 7←12, 2161 frames, 100s), `captures/2026-05-04T122545Z_dimmer_sweep_571_572_573/`, [2026-05-04_dimmer_channel_value_sweep.md](2026-05-04_dimmer_channel_value_sweep.md).

## Bidirectional check

| Endpoint | Tx | Rx | Verdict |
|----------|----|----|---------|
| `10.10.1.40:1001` | 11 | 11 | PASS (bidirectional) |

Reply latency hub→dimmer command → dimmer reply: **~11–25 ms** (well under 500 ms gate).

## Reply structure: `I0154<C><VV>` (8-byte ASCII)

```
I  01  54  C VV
│  │   │   │ └── value-code (2 digits): 00 = off, 10..98 = that %, 99 = 100%
│  │   │   └──── channel digit (0–7), matches the commanded channel
│  │   └──────── dimmer family constant (always "54" in captures)
│  └──────────── device type (01 = IP0300 dimmer module)
└─────────────── status/reply prefix (same as relay status family)
```

**Corrected 2026-06-03 (live test, Bureau dimmer ch1):** the 3 digits after
`I0154` are **`<channel><value_code>`**, *not* a single 0–100 value-code. The
earlier reading (all 3 digits = value-code) only matched for **channel 0**
(`030`, `070`, `099`, `000`), where the leading channel digit is `0` and the
integer happens to equal the percent. For **channel 1** (Bureau, comp 572) the
replies are `130 / 170 / 199 / 100` = channel `1` + value `30 / 70 / 99 / 00`.
Decoding `130` as `130 %` was a bug; the correct level is `30 %` on channel 1.

The all-nines code `I0154999` is an **idle/poll heartbeat** — it carries no
channel and no setpoint and must not overwrite a channel level.

Ground truth: 2026-05-14 REST↔UDP correlation for the Bureau dimmer —
`OFF→I0154100`, `DIM 30→I0154130`, `DIM 70→I0154170`, `DIM 100→I0154199`,
idle `→I0154999` ([2026-05-14_dimmer_rest_udp_timeline_writeup.md](2026-05-14_dimmer_rest_udp_timeline_writeup.md)).

## Hub→dimmer command shape (no `J` separator)

Dimmer uses **compound first byte** (channel + direction encoded), unlike relay `[pfx]J<cmd>`:

| Wire (hex→ASCII) | REST / meaning | Reply | Reply = `<ch><val>` |
|------------------|----------------|-------|----------------------|
| `I9900` | idle poll | (none in burst) | — |
| `S0301030` | DIM 30%, ch 0 | `I0154030` | ch 0 + `30` |
| `S0701030` | DIM 70%, ch 0 | `I0154070` | ch 0 + `70` |
| `S0991030` | DIM 100%, ch 0 | `I0154099` | ch 0 + `99` |
| `C0991030` | OFF, ch 0 | `I0154000` | ch 0 + `00` |
| `S1501030` | DIM 50%, ch 1 | `I0154150` | ch 1 + `50` |
| `C1991030` | OFF, ch 1 | `I0154100` | ch 1 + `00` |

Proto-map v0.2 (hub command): `<S|C><channel><value_code>1030`

- `S` = set/dim, `C` = cut/off
- `<channel>` = single digit channel index (0–7 per IP0300)
- `<value_code>` = `10`–`90` for DIM 10–90%, `99` for DIM 100%

## Reply value-code ↔ REST DIM mapping

Reply code = `<channel digit><2-digit value-code>`. The value-code uses the
same scheme as the command: `00` = off, `10`–`98` = that percent, `99` = 100%.

| Reply code | Channel | Value-code | REST DIM % | Notes |
|------------|---------|------------|------------|-------|
| `000` | 0 | `00` | OFF (0) | After `C0…` command |
| `030` | 0 | `30` | 30 | ch 0 |
| `070` | 0 | `70` | 70 | ch 0 |
| `099` | 0 | `99` | 100 | ch 0, full |
| `100` | 1 | `00` | OFF (0) | After `C1…` — **not** "DIM 100" |
| `130` | 1 | `30` | 30 | Bureau (comp 572) |
| `150` | 1 | `50` | 50 | `S1501030` → `I0154150` |
| `170` | 1 | `70` | 70 | Bureau |
| `199` | 1 | `99` | 100 | Bureau, full |
| `999` | — | — | poll/idle | Idle heartbeat — no channel/setpoint |

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
