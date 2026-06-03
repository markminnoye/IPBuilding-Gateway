# Dimmer reply-decode fix + WebSocket live test (2026-06-03)

**Type:** live veldtest + bugfix + doc-correctie
**Module:** dimmer `10.10.1.40` (IP0300), kanaal 1 = **Bureau** (`ipbox_id` 572, `40.1.2`)
**Gateway:** open hub op deze machine; northbound WebSocket op **poort 9090** (`GATEWAY_API_PORT=9090`)
**Hub `10.10.1.1`:** offline (IPBox uit) — gateway neemt hub-rol over; dimmer bereikbaar (ping OK)

Gerelateerd: [2026-05-17_dimmer_I0154xxx_full_decode.md](2026-05-17_dimmer_I0154xxx_full_decode.md) (canonieke decode, gecorrigeerd), [2026-05-14_dimmer_rest_udp_timeline_writeup.md](2026-05-14_dimmer_rest_udp_timeline_writeup.md) (ground truth).

---

## 1. Aanleiding

WebSocket-test van de gateway met de Bureau-dimmer. De WS-flow werkte end-to-end
(`device_list` → `command` → `command_result` → `state_changed`), maar de log toonde
foute niveaus: een `DIM 30` kwam terug als `level: 130`, daarna `100`.

## 2. Root cause

De dimmer-reply `I0154<C><VV>` werd verkeerd gedecodeerd. De 3 cijfers na `I0154`
zijn **`<kanaal><waarde-code>`**, maar de decoder las ze als één percentage:

- `I0154130` = kanaal `1` + waarde `30` → **30 %**, maar werd `130 %`
- `I0154999` = idle/poll-heartbeat (geen setpoint) → werd `100 %` en overschreef het niveau

De oude lezing klopte alleen toevallig voor **kanaal 0** (`030/099/000`), waar het
leidende kanaalcijfer `0` is.

### Bewijs (drie datapunten, live, ch1)

| WS-commando | reply-code (`internal_value_code`) | `level` vóór fix | `level` ná fix |
|---|---|---|---|
| DIM 30 | `130` | 130 → 100 | **30** |
| DIM 80 | `180` | 180 → 100 | **80** |
| DIM 55 | `155` | 155 → 100 | **55** |
| DIM 0 (OFF) | `100` | (geen `state_changed`) | **off / 0 %** |

Consistent met de REST↔UDP-correlatie van 2026-05-14 (Bureau, id 572):
`OFF→I0154100`, `DIM 30→I0154130`, `DIM 70→I0154170`, `DIM 100→I0154199`, idle `→I0154999`.

## 3. Fix

- **`gateway/payloads/dimmer.py`** — reply gesplitst in `<channel>` (leidend cijfer) +
  `<value_code>` (2 cijfers: `00`=uit, `10..98`=%, `99`=100 %). Code `999` → `dimmer_poll`
  (idle), geen setpoint.
- **`gateway/device_registry.py`** — `_handle_dimmer` gebruikt het gedecodeerde kanaal
  i.p.v. de "laatst-gecommandeerde kanaal"-proxy; idle-heartbeat wordt genegeerd
  (overschrijft niveau niet meer).

## 4. Verificatie

- **Unit/integratie:** `pytest tests/` → **95 passed**. Nieuwe regressietests:
  `I0154130`→ch1/30 %, idle-heartbeat negeert state, kanaal-toewijzing per reply.
- **Live (gefixt):** state_changed toont nu correct `30 / 80 / 55 / 0`; `999`-heartbeats
  laten het niveau staan; `DIM 0` rapporteert `off`.

Gateway-log (na fix, ch1):

```
Dimmer 10.10.1.40 ch1: None -> 30%   (I0154130)
Dimmer 10.10.1.40 ch1: 30 -> 80%     (I0154180)
Dimmer 10.10.1.40 ch1: 80 -> 55%     (I0154155)
Dimmer 10.10.1.40 ch1: 55 -> 0%      (I0154100)
```

## 5. Reproductie

```bash
# Gateway op poort 9090, tegen de echte veldbus
GATEWAY_API_PORT=9090 PYTHONPATH=. .venv/bin/python -m gateway

# WebSocket-client (ws://127.0.0.1:9090/ws):
#   {"type":"command","id":"10.10.1.40:1","action":"DIM","value":30}
# Verwacht: command_result ok=true + state_changed level=30
```

> Achtergrondprocessen met volledige rechten overleven hier niet tussen losse
> shell-calls; draai daarom gateway + client in **één** voorgrondcommando
> (`… python -m gateway > log & GW=$!; sleep 4; python client.py; kill $GW`).

## 6. Bijgewerkte documentatie

- `evidence/2026-05-17_dimmer_I0154xxx_full_decode.md` — reply-structuur, command-tabel,
  value-code-mapping naar `<channel><value_code>`.
- `evidence/2026-05-14_dimmer_rest_udp_timeline_writeup.md` — "kanaal 1 impliciet in prefix" rechtgezet.
- `evidence/2026-05-14_udp_payload_semantics_matrix.md` — `I0154`-rij.
- `IPBUILDING_KNOWLEDGE.md` §6 — geobserveerde dimmer-UDP-vorm.
- `RE_STATE.md` — Sprint 3 dimmer-entry.
- `2026-05-17_ipbuilding_fieldbus_capability_matrix.md` — dimmer status-read rij.
