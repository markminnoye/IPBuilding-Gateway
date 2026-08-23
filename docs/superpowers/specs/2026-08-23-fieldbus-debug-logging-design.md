# Fieldbus debug logging

**Date:** 2026-08-23  
**Status:** approved for implementation  
**Repos:** IPBuilding Gateway (add-on)  
**Context:** Nolf 2026-08-08 — relay `0015`/`0115` map to HA unknown; dimmer `.42` status poll times out (reply vs silence indistinguishable)

## Problem

Add-on logs cannot answer: did a UDP reply arrive, what bytes were in it, and did `0015` change to `0115` on a switch?

Current behaviour:

- Relay poll **is** logged, including unknown (`STATE … state_code='0015'`).
- Registry does **not** log/broadcast when mapped state stays `unknown` while `state_code` changes.
- UDP bytes that do not decode: silent.
- Dimmer poll: predicate miss → **timeout**, as if nothing arrived.
- Command TX and raw RX: not logged.
- `logging.log_level: debug` already exists (`GATEWAY_LOG_LEVEL`) but does not cover the field bus.

## How Jan enables it

No extra toggle. Existing add-on option only:

1. HA → Add-on IPBuilding Gateway → Configuration → **Logging → Log level = debug**
2. Save + restart the add-on
3. Reproduce (one `0015` relay, one dimmer on/off/dim)
4. Download the log and send it
5. Set log level back to **info** (otherwise the log keeps growing)

`ipbuilding_gateway/config.yaml` → `logging.log_level` → `run.sh` → `GATEWAY_LOG_LEVEL`.

## Goals

1. From add-on logs: reply / no reply / reply we do not recognise.
2. Unknown `state_code` visible without debug (Jan on `info`).
3. Debug shows TX/RX for **status poll, commands, and keepalive ticks**.
4. No new northbound API, no companion change.

## Non-goals

- Mapping `0015`/`0115` to on/off (separate RE/fix).
- Extra add-on option `fieldbus_trace`.
- HTTP `getSysSet` / ARP dumps.
- Re-introducing `POST /api/v1/debug/fieldbus-polling`.

## Keepalives on debug (yes)

Actuator poll is every ~20 s (`P0000` / `I9900`). On Nolf (3 relays + 1 dimmer) that is ~12 actuator echoes/min — fine for a debug session.

**Why log them:** for `.42` the open question is whether the module answers at all. Status poll currently only logs timeout. If keepalive echoes from `.42` arrive (`I9900` / `I0154999`), the module is alive and `I{ch}000000` is the wrong format. If keepalive is also silent: other dialect or bus conflict with IPBox.

One compact DEBUG line per poll tick per module: `TX … keepalive …` and `RX … keepalive …` or `no echo`. Known ASCII, no hex dump.

## Levels

| Level | What is added |
|-------|----------------|
| `info` / `warning` | First unrecognized `state_code` per `(module_ip, channel, code)`; `state_code` change even when mapped state stays `unknown`; seed line includes `state_code` |
| `debug` | Keepalive TX/RX per tick; unmatched RX in a correlate wait window; command TX/RX; undecoded RX from IPs in `devices.json` |

## Payload formatting

Helper `gateway.udp_bus.format_payload(data) -> str`:

- ASCII if printable; else `hex:` + hex.
- Truncate above 64 bytes (`…(+N)`).

## Tests

- `0015` → warning once; seed log contains `state_code=0015`.
- `0015`→`0115` → INFO + STATE callback (mapped stays unknown).
- Dimmer poll unmatched → DEBUG unmatched, then WARNING timeout.
- Keepalive on debug: TX/RX per tick; on info: silent.
- Command timeout stays WARNING.
