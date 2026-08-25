# Sprintplan — Nolf veldbus-dialecten (2026-08-24)

Last updated: 2026-08-24  
**Status:** gepland — handoff voor implementatie-agent  
**Doel:** decoder-gaten dichten voor Jan Nolf's oudere module-generatie zodat **status in HA klopt** na commando's en dimmer-polls.

---

## Context (lees eerst)

| Doc | Rol |
|-----|-----|
| [veldbus_dialect_registry.md](../../resources_and_docs/reference/veldbus_dialect_registry.md) | **Canonieke dialect-tabel** + implementatiestatus |
| [2026-08-24_jan_nolf_field_test.md](../../resources_and_docs/evidence/2026-08-24_jan_nolf_field_test.md) | Veldtest + log-citaties |
| [2026-08-08_jan_nolf_restore_test.md](../../resources_and_docs/evidence/2026-08-08_jan_nolf_restore_test.md) | Eerdere baseline |
| [`gateway/payloads/relay.py`](../../gateway/payloads/relay.py) | Relay decode/encode |
| [`gateway/payloads/dimmer.py`](../../gateway/payloads/dimmer.py) | Dimmer decode/encode |
| [`gateway/device_registry.py`](../../gateway/device_registry.py) | RX → STATE updates |

**Veldtest-logs (repo):**  
`resources_and_docs/evidence/assets/2026-08-24_jan_nolf_dialect_field_test/3059e002_ipbuilding_gateway_2026-08-24T20-35-36.074Z.log`

**Jan's site:** gateway **1.6.4**, companion **1.8.3** (doel), IPBox nog **slave** naast gateway.

---

## Sprintdoel (Definition of Done)

- [ ] **`relay.nolf.command_reply`** gedecodeerd; na S/C commando → `STATE` update in gateway + WS naar companion
- [ ] **`dimmer.nolf.status_reply`** (+ idle `I0115000`) gedecodeerd; status-poll seed brightness/off i.p.v. timeout
- [ ] Unit tests per dialect-id met **raw bytes uit Nolf-log** (golden vectors)
- [ ] Registry + RE_STATE bijgewerkt; elke nieuwe regex gelabeld met `dialect_id` in decode-dict
- [ ] Gateway release **≥1.6.5** (of patch 1.6.4.x) + korte release note voor Jan
- [ ] Veldvalidatie-checklist klaar (Jan hoeft niet in sprint — wel testplan)

**Buiten scope (tenzij expliciet opgenomen na beslissing):**
- `input.nolf.binary` decode
- Companion-wijzigingen (behalve verifiëren dat WS `state` doorgeeft)
- ESP32 firmware sync (wel: note in CHANGELOG embedded repo)
- IPBox master/switch-over (wel: teststap in checklist)

---

## Fase 0 — Beslissingen (eerst, ~30 min)

Deze keuzes bepalen implementatie; **documenteer beslissing** in registry + commit message.

### D0.1 — Relay command-reply patroon

**Observatie:** enige bevestigde sample = `C060000000` (OFF ch6).

| Optie | Beschrijving | Voor | Tegen |
|-------|--------------|------|-------|
| **A (voorkeur)** | Regex `^[SCPT](?P<ch>\d{2})00(?P<state>\d{4})$` → map state via `relay_state_from_code` | Minimale diff; symmetrisch voor S/C | ON-reply nog niet gezien in log |
| B | Alleen `C{ch}00…` + aparte S-regex | Conservatief | Twee paden onderhouden |
| C | Post-command status-poll i.p.v. reply decode | Geen nieuwe regex | Extra bus-verkeer; race met IPBox |

**Actie:** implementeer **A** + unit test voor `C060000000` → off ch6; placeholder test `S06000100` → on (hypothese, mark `@pytest.mark.xfail` tot veldbevestiging).

### D0.2 — Dimmer family `15` structuur

**Observatie:** replies `I0115099`, `I0115184`, `I0115299`, `I0115300`.

| Optie | `{ccc}` interpretatie | Voor | Tegen |
|-------|----------------------|------|-------|
| **A (voorkeur)** | Zelfde als lab: `{ch:1d}{vv:2d}` na `I0115` | Hergebruik `_value_code_to_percent` | `99`-semantiek onbevestigd |
| B | `{vvv:3d}` absolute 0–100 | Simpel | Botst met ch-digit in `184`/`299` |
| C | Alleen command-reply na DIM, geen poll | Minder RE | Status blijft Onbekend na reboot |

**Actie:** implementeer **A**; log raw + decoded level; vraag Jan fysieke validatie ch1 (Lichtstraat?) na fix.

### D0.3 — Poll/reply correlatie

Log toont `unmatched reply from 10.10.1.42 during wait` — reply komt binnen maar matcher faalt.

| Optie | Beschrijving |
|-------|--------------|
| **A (voorkeur)** | Fix decode eerst; als timeouts blijven → `udp_bus` wait-window onderzoeken |
| B | Direct wait-window vergroten | Maskeert echte problemen |

### D0.4 — Dual-hub testvolgorde

| Volgorde | Beschrijving |
|----------|--------------|
| **1** | Decoder fix + Jan test **met IPBox erin** (huidige situatie) |
| **2** | Jan test **ethernet IPBox eruit** → bevestig `hub_role=master` + knoppen |

Documenteer in release note: relay status na commando kan in slave-modus nog deels naar IPBox gaan.

### D0.5 — Dialect-id in code

| Optie | Beschrijving |
|-------|--------------|
| **A (voorkeur)** | Elke `decode_*_payload` return dict krijgt `"dialect_id": "relay.nolf.command_reply"` |
| B | Alleen comments | Minder traceerbaar in logs |

**Beslissing vastleggen:** korte sectie onderaan registry + in PR beschrijving.

---

## Fase 1 — Relay implementatie

**Bestand:** `gateway/payloads/relay.py`

1. Voeg `_RELAY_NOLF_CMD_REPLY_RE` toe (zie D0.1-A).
2. In `decode_relay_payload`: match **na** command TX regex, **vóór** return None.
3. Return:
   ```python
   {
       "dialect_id": "relay.nolf.command_reply",
       "family": "relay_command_reply",
       "action": "off" | "on" | ...,
       "channel": int,
       "state_code": str,
       "state": relay_state_from_code(state_code),
       "raw": text,
   }
   ```
4. **`device_registry.py`:** route `relay_command_reply` → zelfde STATE update als status reply.
5. **`gateway_api.py` / command path:** bevestig dat command RX listener `device_registry.handle_rx` aanroept (debug-log toont al RX — alleen decode mist).

**Tests:** `tests/test_relay_payload.py`

```python
# Golden vectors from Nolf log 2026-08-24
("C060000000", {"dialect_id": "relay.nolf.command_reply", "channel": 6, "state": "off", ...})
# Lab regressie ongewijzigd
("I000060100", {"dialect_id": "relay.lab.status_reply", ...})
```

---

## Fase 2 — Dimmer implementatie

**Bestand:** `gateway/payloads/dimmer.py`

1. Voeg `_DIMMER_NOLF_REPLY_RE = ^I01(?P<family>15)(?P<value_code>\d{3})$` toe.
2. Parse `{value_code}` als `{ch}{vv}` (mirror lab logic).
3. Behandel `099`/`999`-achtige codes:
   - **Voorstel:** `99` → idle/unknown level (geen STATE overwrite) OF 100% — **beslissing D0.2**;
   - idle keepalive `I0115000`: family `dimmer.nolf.idle_keepalive`, geen channel state.
4. **`state_poll.py`:** dimmer poll seed gebruikt `decode_dimmer_status` — zou moeten werken zodra decode fixed is.
5. Optioneel: `_DIMMER_REPLY_RE` family group veralgemenen naar `(54|15)` met expliciete `dialect_id`.

**Tests:** `tests/test_dimmer_payload.py`

```python
("I0115184", {"dialect_id": "dimmer.nolf.status_reply", "channel": 1, "level_percent": 84, ...})
("I0115300", {"dialect_id": "dimmer.nolf.status_reply", "channel": 3, "level_percent": 0, ...})
("I0115000", {"dialect_id": "dimmer.nolf.idle_keepalive", ...})
# Lab regressie
("I0154110", {"dialect_id": "dimmer.lab.status_reply", ...})
```

---

## Fase 3 — Integratie & observability

1. **Debug logging:** bij succesvolle Nolf-decode één regel INFO: `decoded {dialect_id} from {ip}: {raw}`.
2. **Undecoded counter:** als `I0115…` na fix nog undecoded → bug, niet hardware.
3. **Companion check (read-only):** bevestig dat `state: off/on` en `brightness` uit WS correct naar entities gaan — geen code change verwacht.
4. **Embedded sync:** port regex + tests naar `matter-esp32-ipbuilding-gateway/main/veldbus/payloads/` (handmatige sync policy A4).

---

## Fase 4 — Release & Jan testplan

### Release

- Bump gateway add-on → **1.6.5** (CHANGELOG entry: Nolf dialect support)
- Release note (NL, kort) met:
  - wat fixed is (relais status na schakelen; dimmer status)
  - wat Jan moet doen (update, HA restart, optioneel debug opnieuw)

### Jan checklist (mail-template)

1. Update gateway naar 1.6.5; companion ≥1.8.3; **HA herstarten**
2. **Relais:** kies ch9 (bureau Jan) — toggle in HA; bevestig state volgt lamp
3. **Dimmer:** kies ch1 Lichtstraat — 50% slider; bevestig percentage in HA
4. Optioneel: log **debug** 2 min, terug naar **info**
5. Als OK: IPBox ethernet eruit, herhaal 2–3

---

## Taakverdeling (suggestie)

| # | Taak | Bestand(en) | Schatting |
|---|------|-------------|-----------|
| 1 | Beslissingen D0.1–D0.5 vastleggen | registry | 30 min |
| 2 | Relay Nolf command-reply decode | `relay.py`, `device_registry.py` | 2 u |
| 3 | Relay unit tests + lab regressie | `test_relay_payload.py` | 1 u |
| 4 | Dimmer family-15 decode | `dimmer.py` | 2 u |
| 5 | Dimmer unit tests + lab regressie | `test_dimmer_payload.py` | 1 u |
| 6 | Integratie smoke (local/sim) | `pytest`, optional mock UDP | 1 u |
| 7 | Docs: registry status ✅, RE_STATE, README index | docs | 30 min |
| 8 | Release 1.6.5 + Jan mail | CHANGELOG, config.yaml | 30 min |
| 9 | (Optioneel) ESP32 payload sync | embedded repo | 2 u |

**Totaal:** ~1–1.5 dev-dag exclusief veldtest Jan.

---

## Risico's

| Risico | Mitigatie |
|--------|-----------|
| ON-reply `S06000100` verkeerd | xfail test; veldcheck Jan |
| `99` op Nolf ≠ lab semantiek | log + Jan validatie; makkelijk aanpasbaar in `_value_code_to_percent` |
| IPBox vangt replies af in slave | test zonder IPBox; documenteer in release note |
| Prefix `0015`=off fysisch fout | Jan bevestigt 3 kanalen; flip mapping indien nodig (1 regel) |

---

## Agent handoff checklist

Start hier morgen:

- [ ] Lees [veldbus_dialect_registry.md](../../resources_and_docs/reference/veldbus_dialect_registry.md) volledig
- [ ] Open debug-log in assets; grep `undecoded`, `command`, `status-poll`
- [ ] Run bestaande tests: `pytest tests/test_relay_payload.py tests/test_dimmer_payload.py`
- [ ] Neem **Fase 0 beslissingen** (defaults hierboven tenzij tegensprekend bewijs)
- [ ] Implementeer Fase 1 → 2 → 3 in volgorde; geen companion-wijzigingen zonder bewijs
- [ ] Update registry `Status decode` kolom per dialect-id
- [ ] Laat `2026-08-24_jan_nolf_field_test.md` §8 open tot Jan antwoordt

**Niet doen zonder overleg:**
- Input binary decode
- Hub master forceren in config
- REST-shim / IPBox parity

---

## Gerelateerde issues / vervolg

- Jan wil IPBox eruit → na decoder-fix + actieve hub-test: knoppen→HA automations
- [ha-ipbuilding-gateway#4](https://github.com/markminnoye/ha-ipbuilding-gateway/issues/4) knoppen entities
- Embedded E1 payload drift — sync na merge gateway
