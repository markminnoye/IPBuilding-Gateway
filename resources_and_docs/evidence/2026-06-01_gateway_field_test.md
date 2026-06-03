# Gateway field test evidence (2026-06-01)

**Test:** relay/dimmer/input via open hub (geen IPBox)
**Datum:** 2026-06-01
**Gateway:** `main.py` + `devices.json` + `InstallationConfig` auto-load
**Resultaat:** PASS — alle checks geslaagd

## Netwerk context (belangrijk)

De gateway werd gedraaid vanaf een machine die **niet `10.10.1.1` is** (niet de IPBox). De machine had via routering toegang tot `10.10.1.30/.40/.50` maar `10.10.1.1` (de IPBox) was niet bereikbaar:

```
ping 10.10.1.1   → 100% loss (IPBox niet actief/op dit subnet)
ping 10.10.1.30  → ✅ 0% loss  (relay bereikbaar)
ping 10.10.1.40  → ✅ 0% loss  (dimmer bereikbaar)
ping 10.10.1.50  → ✅ 0% loss  (input bereikbaar)
```

Eerste run (2026-06-01): UniFi mirror **7←15** actief — verkeer zichtbaar op capture-host.

**Her-test zonder mirror (2026-06-02): PASS** — mirror uit; gateway op testhost-IP (niet `10.10.1.1`); modules antwoorden en sturen events naar gateway-IP:

| Check | Result |
|-------|--------|
| Relay ON via REST (`id=547`, `actionType=ON&value=1`) | PASS — UDP reply `I000000100`, state `on` in log |
| Dimmer DIM 50% / 100% (`id=571`) | PASS — `I0154050` / `I0154099` |
| Input drukknop (`10.10.1.50`) | PASS — `press` / `release` events in log (geen mirror-POV) |
| REST `/api/v1/comp/items` | PASS |

Bug gevonden en gefixt: `actionType=ON&value=0` stuurde ten onrechte ON (`rest_shim.py` — conditie `action_type == "ON"` zonder `value > 0`). Na fix: OFF (`C{ch}00`). Her-test OFF/ON aanbevolen na gateway-herstart.

## Test checks

| Check | Result |
|-------|--------|
| `devices.json` laden (auto-default `./devices.json`) | PASS — `install=relay@10.10.1.30, dimmer@10.10.1.40, input@10.10.1.50` |
| Poll naar alle modules | PASS — `P0000`/`I9900`/`I0000` naar `.30`/`.40`/`.50` elke ~2s |
| Dimmer soft-AAN reply (via poll `I9900`) | PASS — `I0154999` → 100% |
| Relay ON/OFF via REST (id 547, Keuken LED) | PASS — `S0303030`/`C0303030` → `I00000100`/`I00000000`; fysiek + state in log |
| Dimmer DIM 50% / DIM 0% via REST (id 571, Woonkamer Dimmer 1) | PASS — `I0154050` (50%) / `I0154000` (0%) |
| Input button events (id 2f8185190000df, 10.10.1.50) | PASS — press + release in log |
| REST `/api/v1/action/action` | PASS — 200 OK, reply parsed |
| REST `/api/v1/comp/items` | PASS — alle 6 devices met correcte state |

## Command/reply voorbeelden

**Relay ON (id 547):**
```
sent_hex: 5330303030   →  S0000100 (ON kanaal 0)
reply:   I00000100     →  relay status ON  (channel 0, state 0100)
```

**Dimmer DIM 50% (id 571):**
```
sent_hex: 5330353031303330  →  S0501030  (DIM 50%, kanaal 0)
reply:   I0154050           →  50% (internal code 050)
```

**Input button press:**
```
B-...E  (press)  →  EVENT  10.10.1.50 button 2f8185190000df: press
B-...E  (release) →  EVENT  10.10.1.50 button 2f8185190000df: release
```

## Open punen

- **Relay status poll (GESLOTEN 2026-06-02):** `I<ch>` poll geeft geen kanaalstatus reply — relay antwoordt met `I000000000` (echo, geen `I<CH><state>`). `P0000` is de enige functionele poll voor relay. Bewijs: `scripts/test_relay_poll.py` + `evidence/2026-06-02_relay_poll_i_ch_test.md`.
- **Bind als `10.10.1.1`**: 2026-06-02 bevestigd dat hub werkt met gateway op ander IP; optioneel nog: expliciet `GATEWAY_BIND_IP=10.10.1.1` + `ping 10.10.1.1` wanneer IPBox uit is.
- **Dimmer channel-awareness**: dimmer store state onder `ch-1` (laatst gezien kanaal); verbetering van kanaaltracking is toekomstig werk.
- **Discovery M4**: zie plan [fase_2_gateway_afronden_204fe6a1.plan.md](../.cursor/plans/fase_2_gateway_afronden_204fe6a1.plan.md)