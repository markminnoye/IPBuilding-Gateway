# Dimmer on-demand status poll `I{ch}000000` — CONFIRMED (2026-08-05)

Last updated: 2026-08-05

**Context:** Jan Nolf’s IPBuilding 03.07 debug-log toont hub→dimmer Actions  
`I0000000` / `I1000000` / `I2000000` ([2026-08-05_jan_nolf_ipbuilding_03.07_debug_actions.md](2026-08-05_jan_nolf_ipbuilding_03.07_debug_actions.md)).  
Dat 8-byte formaat zat **niet** in `gateway/payloads/dimmer.py`. Eerdere lab-test  
([2026-06-12_dimmer_status_poll_hypotheses_refuted.md](2026-06-12_dimmer_status_poll_hypotheses_refuted.md))  
verwierp alleen `I<CH>00` (5 bytes) en `I9900` — **niet** `I{ch}000000`.

**Live test:** 2026-08-05, UDP/1001 vanaf thuis-LAN naar lab-dimmer `10.10.1.40:1001`.  
Script: [`scripts/test_dimmer_status_poll.py`](../../scripts/test_dimmer_status_poll.py).

---

## Resultaat — HYPOTHESE BEVESTIGD

Query `I{ch}000000` (8 ASCII bytes) → reply `I0154{ch}{vv}` met **echt per-kanaal niveau**.

| Query | Reply | Decode |
|-------|-------|--------|
| `I0000000` | `I0154000` | ch0 → **0%** (off) |
| `I1000000` | `I0154100` | ch1 → **0%** |
| `I2000000` | `I0154299` | ch2 → **100%** |
| `I3000000` | `I0154300` | ch3 → 0% |
| `I4000000` | `I0154400` | ch4 → 0% |
| `I5000000` | `I0154500` | ch5 → 0% |
| `I6000000` | `I0154600` | ch6 → 0% |
| `I7000000` | `I0154700` | ch7 → 0% |

- 3× herhaald per kanaal → **stabiel** (geen mixed replies).
- Latency typisch ~8–50 ms.
- **Kanaalselectie bewezen:** ch2 = 100% terwijl ch0/1/3–7 = off — onmogelijk als de module altijd ch0 zou echoën.

### Baselines (ongewijzigd t.o.v. 2026-06-12)

| Query | Reply | Betekenis |
|-------|-------|-----------|
| `I9900` | `I0154999` | idle/poll heartbeat — **geen** setpoint |
| `I0000` / `I0100` / `I0200` (5 bytes) | steeds `I0154000` | H1 blijft: **geen** kanaalselectie op 5-byte `I<CH>00` |

### Extra probes

| Query | Len | Reply | Notitie |
|-------|-----|-------|---------|
| `I000000` | 7 | `I0154000` | valt terug op ch0 |
| `I00000000` | 9 | `I0154000` | idem |
| `I9000000` | 8 | `I0154900` | “ch9” → value 00 (geen echte dimmer-ch) |
| `I9900000` | 8 | `I0154999` | zelfde idle als `I9900` |

---

## Correctie op eerdere conclusie

| Claim (2026-06-12) | Status na 2026-08-05 |
|--------------------|----------------------|
| Dimmer heeft **geen** on-demand per-kanaal statuspoll | **ACHTERHAALD** — wel via `I{ch}000000` |
| `I<CH>00` selecteert geen kanaal | blijft **juist** (5-byte formaat) |
| `I9900` is pure liveness | blijft **juist** |

**Formaat:**
- Query = `I` + `<ch,1 digit 0–7>` + `000000` (8 bytes ASCII)
- Reply = bestaand `I0154<ch><vv>` (decoder in `gateway/payloads/dimmer.py` al OK)

---

## Impact gateway

- Startup / on-demand dimmer state-read is **mogelijk** (analoog aan relay `I<CH>00` sweep).
- **Geïmplementeerd:** `encode_dimmer_status_poll` in `gateway/payloads/dimmer.py` + `sweep_dimmer_states` in `gateway/state_poll.py` (startup + post-discovery).
- Steady-state keepalive blijft `I9900`; status-sweep apart bij boot / discover.
