# Relay poll I<ch> test (2026-06-02)

**Datum:** 2026-06-02
**Doel:** bevestig of relay `10.10.1.30:1001` reageert op `I<ch>` poll met `I<CH><state>` status reply
**Script:** `scripts/test_relay_poll.py`

## Uitvoering

```bash
python3 scripts/test_relay_poll.py --relay 10.10.1.30 --repeat 3
```

Relay bereikbaar: 0% packet loss (ping).

## Resultaten

| Payload | Reply | Timing (ms) | Herhalingen |
|---------|-------|-------------|-------------|
| `P0000` | `P000000000` (pulse echo) | 10.0–24.5 (avg 17.6ms) | 3/3 |
| `I0000` | `I000000000` (unknown/echo) | 9.8–17.4 (avg 11.2ms) | 3/3 |
| `I0010` | `I000000000` (unknown/echo) | 10.5–14.7 (avg 12.7ms) | 3/3 |
| `I0016` | `I000000000` (unknown/echo) | 9.8–10.6 (avg 10.3ms) | 3/3 |
| `I0023` | `I000000000` (unknown/echo) | 10.8–17.4 (avg 13.2ms) | 3/3 |

## Analyse

**`P0000` → `P000000000`:** bevestigd pulse-echo (10-byte fixed width). Dit is het gedrag dat in Sprint 1 is vastgesteld.

**`I<ch>` → `I000000000`:** relay antwoordt met 10-byte echo in `I...` prefix formaat, maar dit is **GEEN kanaalstatus**. Een echte status reply zou zijn `I<CH><state>` (bijv. `I00000100` voor kanaal 0 aan). Het antwoord `I000000000` is waarschijnlijk een "protocol mismatch" / "command not supported" echo — vergelijkbaar met hoe `P0000` → `P000000000` een pulse-bevestiging is maar geen status inhoud.

**Conclusie:** `I<ch>` poll wordt niet ondersteund door de relay als status request. De relay verwacht `P0000` als pulse-poll en `S/C/T/P` als commando's. Status replies (`I<CH><state>`) komen alleen na een `S` (ON) of `C` (OFF) commando.

## Besluit

**Scenario B bevestigd** — `I<ch>` poll geeft geen status reply; `P0000` pulse-echo is de enige poll-respons voor relay.

Geen wijziging aan `_MODULE_POLL["relay"]` in `gateway/udp_bus.py`. `P0000` blijft de baseline poll.

## Bewijs van capture (bestaand)

IPBox idle Run C (2026-05-14, `capture.pcapng` in `captures/2026-05-14T214905Z_push-pull-run-c-idle/`):
- hub `10.10.1.1` → relay `10.10.1.30`: `pJP0000` (met `J`-envelope) herhaaldelijk
- Geen `I<ch>` polls naar relay ooit waargenomen

Dit bevestigt dat IPBox nooit `I<ch>` polls naar relay stuurt — consistent met bovenstaande lab-test.