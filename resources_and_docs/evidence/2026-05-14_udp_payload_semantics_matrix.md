# UDP/1001 payload semantics matrix (compact)

Last updated: 2026-05-22 (local)
Canonieke RE-index: [RE_STATE.md](../RE_STATE.md). Detailbewijs: gelinkte evidence per rij.

| Family / pattern | Context (module / path) | Direction notes | Label | Evidence pointer |
| ---------------- | ------------------------- | ----------------- | ----- | ------------------ |
| `S<CH>00` | Relay command ON (logische kern) | Parser moet optionele `[pfx]J`-wrapper strippen; op draad vaak 7 bytes | **confirmed** (kern) | [2026-05-04_relay_payload_correlation.md](2026-05-04_relay_payload_correlation.md), `/tmp/rest_stimulus_capture_20260516.pcapng` |
| `C<CH>00` | Relay command OFF (logische kern) | Zelfde framing als `S`; voorbeeld `}JC0000` = `}`+`J`+`C0000` | **confirmed** (kern) | same |
| `<pfx>J` + `S\|C\|P…` | Hub→relay wire envelope | `[1 byte prefix]` + literal `J` (0x4a) + bekende 5-char kern; UDP payload len typ. 13 (8 bytes data incl. null pad) | **confirmed** (shape + REST timing) | `/tmp/rest_stimulus_capture_20260516.pcapng` (2026-05-16) |
| `pJP0000` | Hub→relay pulse op draad | **`p` + `J` + `P0000`** — niet relay→hub; eerdere reply-claim **ingetrokken** | **confirmed** (hub→relay) | idle captures 2026-05-16 + REST capture |
| `mJS0000` / `}JC0000` / … | REST-gestuurde relay OFF/ON | `m`/`}`/`g`/`w` + `J` + `S0000`/`C0000`/…; gekoppeld aan IDs 547/557/563 | **confirmed** (REST-correlatie) | `/tmp/rest_stimulus_capture_20260516.pcapng` |
| `T<CH>00` | Relay toggle | Seen historically, not last focused sweep | **hypothesis** | [2026-05-04_relay_payload_correlation.md](2026-05-04_relay_payload_correlation.md) |
| `P0000` | Hub→relay pulse channel 0 (logische kern) | Op draad vaak `pJP0000`; niet verwarren met `P000000000` | **confirmed** | same |
| `P000000000` | Relay→hub (or relay→IPBox home leg) fixed-width echo of `P0000` | Sub-5 ms after hub `P0000` when return path visible; **niet** hetzelfde als `pJP0000` op draad | **high** (timing + framing) | same (addendum 2026-05-15), [scripts/analyze_relay_reply_candidate_timing.py](../scripts/analyze_relay_reply_candidate_timing.py) |
| Prefix byte (`m`/`}`/`g`/`w`/`p`) | Voor `J` in hub→relay frames | Zie `<pfx>J` prefix mapping rij | **confirmed** (via Sprint 2) | `/Users/markminnoye/Downloads/00:55.pcapng` |
| `I0000` cadence ~2s | Idle / poll baseline | Separating poll vs command-triggered still open globally | **confirmed** (cadence), **hypothesis** (strict causality) | [CAPTURE_LIVE_STATUS.md](../workflows/CAPTURE_LIVE_STATUS.md) |
| `I<CH><state>` (10-byte) | Relay→hub status na ON/OFF | **GESLAAGD 2026-05-17**: `I00000100`/`00000000` (ch 0), `I00100100`/`00100000` (ch 10), `I00160100`/`00160000` (ch 16), `I00230100`/`00230000` (ch 23); 13 reply frames in 87s capture; structuur `[I][channel=2][state=4]` | **confirmed** (hard, 2026-05-17) | `/Users/markminnoye/Downloads/capture_00:48.pcapng` |
| `P000000000` | Relay→hub pulse echo | **GESLAAGD 2026-05-17**: frames 11/1221/1597 in `capture_00:48.pcapng`; ~2ms na hub `P0000`; 10-byte fixed width | **confirmed** (2026-05-17 upgrade) | `capture_00:48.pcapng` |
| `I#########` relay status | Parsed `relay_status` (module/channel/state) | Visible in some POVs; Sprint 1 2026-05-17 bevestigt relay→hub `I<CH><state>`; POV-limited voor sommige runs | **confirmed** (parser + hard validation) | [2026-05-04_relay_payload_correlation.md](2026-05-04_relay_payload_correlation.md), `capture_00:48.pcapng` |
| `[pfx]J` + `S\|C\|P…` | Hub→relay wire envelope | `[1 byte prefix]` + literal `J` (0x4a) + bekende 5-char kern; UDP payload len typ. 13 | **confirmed** (shape + REST timing) | `/tmp/rest_stimulus_capture_20260516.pcapng` (2026-05-16) |
| `<pfx>J` prefix mapping | Hub→relay prefix-byte per commando-type | `p` (0x70) → `P0000` idle pulse; `m` (0x6d) → `S<CH>00` ON; `}` (0x7d) → `C<CH>00` OFF; `g` (0x67) → `S1600` ON; `w` (0x77) → `C1600` OFF; `v` (0x76) → `C1700` OFF (nieuw); `{` (0x7b) → `C0200` OFF (nieuw); `J` (0x4a) is separator; prefix-byte is transmission-sequence marker, niet puur commando-type | **confirmed** (2026-05-17) | `/Users/markminnoye/Downloads/00:55.pcapng` |
| `I0154xxx` (8-byte ASCII) | Dimmer→hub status reply | `I` + `01` (device) + `54` (family) + `xxx` (value-code); `030`/`070`/`099`/`000`/`100`/`150` bevestigd | **confirmed** | [2026-05-17_dimmer_I0154xxx_full_decode.md](2026-05-17_dimmer_I0154xxx_full_decode.md), `01:01.pcapng` |
| `S<ch><val>1030` / `C<ch><val>1030` | Hub→dimmer command | Geen `J`-separator; `S`=dim, `C`=off; value-code `10`–`90`, `99`=100% | **confirmed** | [2026-05-04_dimmer_channel_value_sweep.md](2026-05-04_dimmer_channel_value_sweep.md) |
| `I9900` | Dimmer idle poll | Hub→dimmer background | **confirmed** | dimmer sweep |
| `I0000` | Input hub poll | Hub→`10.10.1.50` ~2s cadence | **confirmed** | [2026-05-17_ip1100_input_payload_decode.md](2026-05-17_ip1100_input_payload_decode.md) |
| `I\x02R…E` (14-byte) | Input→hub idle reply | Constant between polls when no press | **confirmed** | `pov_a_7x15.pcapng`, Sprint 5 `10:25` |
| `B-…E` (13-byte) | Input→hub button event | `B-` + 6-byte id + suffix + `03` + `01`/`00` press/release + `E` | **confirmed** | [2026-05-22_sprint5_input_physical_completion.md](2026-05-22_sprint5_input_physical_completion.md) |

## How to use this matrix

- Treat **confirmed** as safe for parser and correlation scaffolding.
- Treat **hypothesis** as requiring extra evidence or a **PASS** `STATUS_VERDICT_GATE` from [scripts/correlate_capture_session.py](scripts/correlate_capture_session.py) before wire-absence claims.
