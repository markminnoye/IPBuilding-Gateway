# Veldbus dialect registry (UDP/1001)

Last updated: 2026-08-25

**Doel:** één canonieke lijst van **wire-dialecten** die we op UDP/1001 hebben gezien, met **implementatiestatus** in `gateway/payloads/` (Python) en sync naar embedded (C++ handmatig).

**Regels voor implementatie:**
- Elke dialect-rij heeft een **`dialect_id`** (stabiele naam in code/tests/docs).
- Decoder: **probeer alle bekende patronen**; log `undecoded` alleen als geen enkel patroon matcht.
- **Nooit** lab-dialect overschrijven met Nolf-hypotheses zonder veldvalidatie.
- Raw `state_code` / payload blijft altijd in logs en northbound API.

**Code-locaties:**
| Module | Python | Tests |
|--------|--------|-------|
| Relay | [`gateway/payloads/relay.py`](../../gateway/payloads/relay.py) | [`tests/test_relay_payload.py`](../../tests/test_relay_payload.py) |
| Dimmer | [`gateway/payloads/dimmer.py`](../../gateway/payloads/dimmer.py) | [`tests/test_dimmer_payload.py`](../../tests/test_dimmer_payload.py) |
| Input | [`gateway/payloads/input.py`](../../gateway/payloads/input.py) | — |

---

## Overzicht dialecten

| `dialect_id` | Module / generatie | Richting | Wire-voorbeeld | Status decode | Status encode | Evidence |
|--------------|-------------------|----------|----------------|---------------|---------------|----------|
| `relay.lab.command` | IP200PoE / IP0200PoE (lab ~5.x) | hub→relay | `S0500`, `C0500` | ✅ | ✅ | [2026-05-04](../evidence/2026-05-04_relay_payload_correlation.md) |
| `relay.lab.status_poll` | lab IP0200 | hub→relay poll | `I0500` | ✅ | ✅ | [2026-06-12](../evidence/2026-06-12_ipbox_boot_relay_sweep.md) |
| `relay.lab.status_reply` | lab IP0200 | relay→hub | `I000050100`, `I000050000` | ✅ | — | idem |
| `relay.lab.state_code` | lab IP0200 | in status reply | `0100`=on, `0000`=off | ✅ `relay_state_from_code` | — | idem |
| `relay.nolf.status_poll` | Nolf IP0200 (Diagnostic 03.03) | hub→relay poll | `I0500` (zelfde TX) | ✅ | ✅ | [2026-08-08](../evidence/2026-08-08_jan_nolf_restore_test.md) |
| `relay.nolf.state_code` | Nolf IP0200 | in status reply | `0015`=off, `0115`=on (prefix `00`/`01`) | ✅ sinds gw **1.6.4** | — | [2026-08-24](../evidence/2026-08-24_jan_nolf_field_test.md) |
| `relay.nolf.command_reply` | Nolf IP0200 `.30` | relay→hub na S/C | `C060000000` (9–10 tekens, state uit prefix) | ✅ sinds gw **1.6.5** | — | [2026-08-24](../evidence/2026-08-24_jan_nolf_field_test.md) §4 · [spec](../../docs/superpowers/specs/2026-08-25-nolf-dialect-decode-design.md) |
| `dimmer.lab.hub_command` | IP0300PoE (lab) | hub→dimmer | `S110301030`, `C1991030` | ✅ | ✅ | [2026-05-14 dimmer timeline](../evidence/2026-05-14_dimmer_rest_udp_timeline_writeup.md) |
| `dimmer.lab.status_reply` | lab IP0300 | dimmer→hub | `I0154110`, idle `I0154999` | ✅ family `54` | — | [2026-05-17](../evidence/2026-05-17_dimmer_I0154xxx_full_decode.md) |
| `dimmer.lab.status_poll` | lab + IPBox 03.07 UI | hub→dimmer | `I1000000` (8 bytes) | ✅ TX | ✅ | [2026-08-05](../evidence/2026-08-05_dimmer_I_ch_000000_status_poll.md) |
| `dimmer.lab.idle_keepalive` | lab IP0300 | dimmer→hub | `I9900` → reply `I0154999` | ✅ | ✅ poll TX | idem |
| `dimmer.input.p2p` | IP1100→IP0300 | input→dimmer | `T11001000`, `D11001003` | ✅ observability | ✅ helpers | [2026-06-22](../evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md) |
| `dimmer.nolf.hub_command` | Nolf 8×0-10V `.42` | hub→dimmer | `S1231030`, `C1991030` | ✅ (zelfde als lab) | ✅ | [2026-08-24](../evidence/2026-08-24_jan_nolf_field_test.md) |
| `dimmer.nolf.status_reply` | Nolf 8×0-10V `.42` | dimmer→hub op poll | `I0115184` = ch1 84 % | ✅ sinds gw **1.6.5** (family `15`) | — | [2026-08-24](../evidence/2026-08-24_jan_nolf_field_test.md) §5.2 · [spec](../../docs/superpowers/specs/2026-08-25-nolf-dialect-decode-design.md) |
| `dimmer.nolf.command_echo` | Nolf `.42` | dimmer→hub na S/C | `S1231030` → `S1231030` (letterlijke echo) | ✅ sinds gw **1.6.5** (echo = state-bron) | — | idem §5.3 |
| `dimmer.nolf.idle_keepalive` | Nolf `.42` | dimmer→hub op `I9900` | `I0115000` | ✅ sinds gw **1.6.5** (family-15 sentinel, geen overwrite) | — | idem §5.2 |
| `input.lab.button_event` | IP1100PoE (lab) | input→hub | `B-…E` ASCII | ✅ | — | Sprint 5 |
| `input.nolf.binary` | Nolf `.55` | input→hub | hex `490228…`, `462878…` | ❌ observability only | — | [2026-08-24](../evidence/2026-08-24_jan_nolf_field_test.md) §6 |

---

## Ack-model per generatie (2026-08-25)

Het grootste verschil tussen de lab- en de Nolf-modules zit niet in de commando's — die zijn identiek — maar in **hoe de module een commando bevestigt**.

| | Lab (relay fw ~5.1, dimmer fw 5.4) | Nolf (oudere generatie) |
|---|---|---|
| Relay na `S`/`C` | **statusframe** `I0000{ch}{state}` | **echo + state** `C{ch}00{state}` (`C0600` → `C060000000`) |
| Dimmer na `S…1030`/`C…1030` | **statusframe** `I0154{ch}{vv}` | **letterlijke echo** (`S1231030` → `S1231030`), **geen** statusframe |
| Dimmer op poll `I{ch}000000` | `I0154{ch}{vv}` | `I0115{ch}{vv}` (family `15`) |
| Dimmer op keepalive `I9900` | `I0154999` (all-nines sentinel) | `I0115000` |

**Bewijs lab:** DIM 50 % → `I0154050`, DIM 100 % → `I0154099` met de gateway zelf als hub ([2026-06-01 veldtest](../evidence/2026-06-01_gateway_field_test.md) § Command/reply); Sprint 3 pcap `01:01.pcapng` toont 11 Tx / 11 Rx op `10.10.1.40` zonder enkele teruggestuurde `S…1030`.

**Bewijs Nolf:** debug-log 2026-08-24 regels 273–292 — vier DIM-commando's, elke keer exact dezelfde bytes terug van `10.10.1.42`, en in dat hele venster **geen** `undecoded RX from 10.10.1.42` (elke `I0115…` werd elders in dezelfde log wél zo gelogd). Afwezigheid van die regels is het bewijs dat er géén statusframe volgde.

**Implicatie voor de gateway (1.6.5):** op Nolf-modules is er na een commando niets te decoderen behalve de echo. De echo seedt `STATE` (`relay.nolf.command_reply` / `dimmer.nolf.command_echo`); de 20 s actuator-poll corrigeert een echo die fysiek niet is uitgevoerd. Veldvalidatie bij Jan blijft open ([evidence §8](../evidence/2026-08-24_jan_nolf_field_test.md)).

---

## Relay — detail

### `relay.lab.*` (lab IP0200PoE, fw ~5.x)

| Aspect | Formaat |
|--------|---------|
| Command TX | `[S\|C\|T\|P]{ch:02d}00` (5 ASCII) |
| Status poll TX | `I{ch:02d}00` |
| Status reply RX | `I0000{ch:02d}{state:04d}` — korte vorm `I{ch:04d}{state:04d}` ook gezien |
| State quartet | `0100` = on, `0000` = off |
| Command reply RX (lab) | **`I0000{ch}{0100\|0000}`** na S/C (niet C-prefixed echo) |

**Implementatie:** `decode_relay_payload()` — regex `_RELAY_CMD_RE`, `_RELAY_STATUS_RE`, `_RELAY_STATUS_SHORT_RE`.  
**State mapping:** `relay_state_from_code()` — exact `0100`/`0000` vroeger; sinds 1.6.4 ook prefix `01xx`/`00xx`.

### `relay.nolf.state_code` (Nolf IP0200, Diagnostic 03.03)

| Aspect | Formaat |
|--------|---------|
| Status poll TX | **zelfde** als lab: `I{ch:02d}00` |
| Status reply RX | `I0000{ch:02d}{state:04d}` — **zelfde frame** als lab |
| State quartet | **`0015`** ≈ off, **`0115`** ≈ on (prefix-hypothese; fysiek nog deels open) |
| Dual encoding | Startup-poll: `0015`/`0115`; sommige kanalen ook `0100`/`0000` op poll |

**Implementatie (1.6.4):** `relay_state_from_code()` — `state_code.startswith("00")` → off, `"01"` → on.  
**Niet geïmplementeerd:** aparte dialect-id in code (alleen gedrag); overweeg expliciete `dialect_id` in decode-result voor logging.

### `relay.nolf.command_reply` (Nolf IP0200 — **1.6.5**)

Gezien in debug-log 2026-08-24 na OFF naar ch6:

```
TX  C0600
RX  C060000000
```

**Vastgelegd (D0.1, lengte-correctie t.o.v. sprint H1):** regex `^(?P<prefix>[SCT])(?P<channel>\d{2})(?P<tail>\d{6,7})$` — **9 of 10 tekens**. Sprint-default was exact 10 tekens met `00` + quartet; die layout is niet te pinnen (`C060000000` leest op elke kandidaat-positie `0000`).

| Aspect | Formaat |
|--------|---------|
| Prefix | `S` → on, `C` → off, `T` → geen state |
| `P` | **uitgesloten** — keepalive `P000000000` zou anders ch0 elke ronde op uit forceren |
| `state_code` | `""` in het decode-resultaat; registry behoudt het laatst gepolde quartet |
| `tail` / `raw` | blijven in resultaat en log |

**Tweede collisie:** `T11001000` (input→dimmer p2p, 9 tekens) matcht deze regex. Onschadelijk zolang `decode_relay_payload` alleen voor relay-IP's draait — routing-garantie, geen eigenschap van de regex.

**Implementatie:** `_RELAY_NOLF_CMD_REPLY_RE` in `relay.py`, ná command/status/pulse-regexes; `family: relay_command_reply`; `dialect_id: relay.nolf.command_reply`.

---

## Dimmer — detail

### `dimmer.lab.*` (lab IP0300PoE `.40`)

| Aspect | Formaat |
|--------|---------|
| Hub command | `[S\|C]{ch}{vv}1030` — `vv`=00 off, 10–98 %, 99=100% |
| Status reply | `I0154{ch}{vv}` — 8 bytes; family constant **`54`** |
| Idle | poll `I9900` → `I0154999` |
| Status poll | `I{ch}000000` (8 bytes) → `I0154{ch}{vv}` |

**Implementatie:** `_DIMMER_REPLY_RE = ^I01(?P<family>54|15)(?P<value_code>\d{3})$` — family `54` = `dimmer.lab.status_reply`.

### `dimmer.nolf.*` (Nolf 8×0-10V faceplate `.42`)

| Aspect | Formaat |
|--------|---------|
| Hub command | **Zelfde** lab hub-dialect (`S…1030`, `C…1030`) — **werkt in veld** |
| Status poll TX | **Zelfde** `I{ch}000000` |
| Status reply RX | **`I0115{ccc}`** — family constant **`15`** i.p.v. `54` |
| Ack na commando | **letterlijke echo**, géén statusframe — zie § Ack-model |
| Idle keepalive | `I0115000` (niet `I0154999`) |

Voorbeelden uit log 2026-08-24 (poll ch0–3):

| Poll TX | Reply RX | Lezing volgens lab-schema `{ch}{vv}` |
|---------|----------|--------------------------------------|
| `I0000000` | `I0115099` | ch0 (Zithoek), vv=`99` → 100 % |
| `I1000000` | `I0115184` | ch1 (Lichtstraat), vv=`84` → 84 % |
| `I2000000` | `I0115299` | ch2 (Badkamer), vv=`99` → 100 % |
| `I3000000` | `I0115300` | ch3 (Slaapkamer), vv=`00` → uit |

**Waarde-code `99` = 100 % (besloten 2026-08-25).** Er is **geen** bewijs dat Nolf hier van lab afwijkt. Het lab-schema is ground-truth gecorreleerd tegen REST (`DIM 100 → I0154199`, `OFF → I0154100`) in [2026-05-17 full decode](../evidence/2026-05-17_dimmer_I0154xxx_full_decode.md); `00` is daar al de uit-code, dus `99` kan niet óók uit betekenen. Ondersteunend voor Nolf: de poll gaf ch1 = 84 %, waarna Jan precies dát kanaal naar 23 %, 47 % en uit dimt — consistent met een brandende lamp op 84 %. De module accepteert bovendien exact het lab-commandodialect.

**Beslissingen (D0.2 / D0.2b / D0.3, 1.6.5):**
1. `{ccc}` = `{ch}{vv}` zoals lab, andere family-byte — **ja**.
2. `I0115000` is **idle-sentinel** voor family `15` (D0.2b), net als `999` bij family `54`: geen channel/level, geen state-overwrite. Family-gescoped: een globale `000`-sentinel zou lab `I0154000` (ch0 uit) breken. Jan bevestigt met de Zithoek-lamp (ch0) tijdens keepalive — veldvraag blijft open tot hij antwoordt.
3. ~~Poll-matcher / `udp_bus` wait-window?~~ — **nee** (D0.3): `_dimmer_status_predicate` faalde uitsluitend omdat family `15` niet decodeerde.

**Command-echo (D0.1-analogon):** letterlijke `S…1030` / `C…1030` van een dimmer-IP is state-bron (`dimmer.nolf.command_echo`). Prefix `C` → `level_percent: 0` (niet 100: `encode_dim_off` stuurt placeholder `99`).

**Implementatie:** `_DIMMER_REPLY_RE` family `(54|15)`; idle `000` alleen bij family `15`; registry behandelt `dimmer_command` van een dimmer-IP als STATE.

---

## Input — detail

### `input.nolf.binary` (Nolf `.55`, geen module-HTTP)

Debug-log toont herhaaldelijk:

```
undecoded RX from 10.10.1.55: hex:49022800000000000000000045
undecoded RX from 10.10.1.55: hex:462878d7af0200005406a50145
```

**Status:** buiten scope sprint tenzij knoppen-overname (actieve hub) prioriteit krijgt. Knoppen komen nu uit `devices.nolf.json` (config), niet uit module-UDP.

---

## Vastgelegde D0-beslissingen (2026-08-25, gateway 1.6.5)

Canonieke spec: [2026-08-25-nolf-dialect-decode-design.md](../../docs/superpowers/specs/2026-08-25-nolf-dialect-decode-design.md). Sprintplan-default voor D0.1 is **vervangen**.

| Id | Beslissing |
|----|------------|
| **D0.1** | Regex `^(?P<prefix>[SCT])(?P<channel>\d{2})(?P<tail>\d{6,7})$` (9 of 10 tekens). **`P` uitgesloten** (keepalive-collision `P000000000` = ch0 uit). **`state` uit de prefix** (`S` on / `C` off / `T` geen state), niet uit een quartet. `tail` + `raw` blijven. Geen xfail voor hypothetische `S06000100`. |
| **D0.2** | `99` = 100 %, conform lab [full decode](../evidence/2026-05-17_dimmer_I0154xxx_full_decode.md) regel 71. |
| **D0.2b** | `I0115000` = idle-sentinel **alleen** family `15` (zoals `999` bij `54`); geen state-overwrite. Onderbouwing: poll ch0 = `099` vs keepalive `000` seconden later. |
| **D0.3** | Geen `udp_bus`-wijziging. Predicate faalde omdat family `15` niet decodeerde. |
| **D0.4** | Eerst testen mét IPBox, daarna ethernet eruit. |
| **D0.5** | Elke decode-return krijgt `dialect_id`. |
| **Scope** | Alleen Python-gateway. ESP32-port ná Jan's veldvalidatie. |

**P-collision (lengte-correctie):** een 10-teken-patroon dat `P` meeneemt matcht de pulse-echo `P000000000` en zou ch0 elke keepalive-ronde op uit zetten. Vandaar prefix `[SCT]` en 9–10 tekens i.p.v. het sprint-H1-patroon `[SCPT]{ch}00{state:04d}`.

---

## Dual-hub (`hub_role=slave`)

Jan's installatie draait met **IPBox nog op de veldbus** (`hub_role=slave` in elke log). Effecten:

| Symptoom | Verklaring |
|----------|------------|
| Status na commando ontbreekt | Decode 1.6.5 dekt de echo; in slave-modus kunnen replies **nog** deels naar de IPBox gaan |
| Dimmer poll `unmatched reply` | Family `15` decodeert sinds 1.6.5; resterende unmatched = wait-window of dual-hub |
| Knoppen leren | Vereist gateway **master** |

**Veldvalidatie:** na decoder-fix opnieuw testen **met IPBox ethernet eruit** (Jan heeft dit eerder gedaan).

---

## Versie-geschiedenis decoder-fixes

| Gateway | Wijziging |
|---------|-----------|
| ≤1.6.2 | `0015`/`0115` → `unknown` in HA |
| 1.6.4 | `relay_state_from_code`: prefix `00xx`/`01xx` |
| **1.6.5** | `relay.nolf.command_reply` (state uit prefix, 9–10 tekens, geen `P`) + `dimmer.nolf.status_reply` (family `15`) + `dimmer.nolf.idle_keepalive` (`000`) + `dimmer.nolf.command_echo` → STATE; OFF-echo `level_percent` 0 i.p.v. 100 |

---

## Gerelateerde docs

- Spec 1.6.5: [2026-08-25-nolf-dialect-decode-design.md](../../docs/superpowers/specs/2026-08-25-nolf-dialect-decode-design.md)
- Veldtest 2026-08-24: [2026-08-24_jan_nolf_field_test.md](../evidence/2026-08-24_jan_nolf_field_test.md) (§8 checklist OPEN)
- Sprintplan: [2026-08-24-nolf-dialect-sprint-plan.md](../../docs/superpowers/plans/2026-08-24-nolf-dialect-sprint-plan.md)
- Nolf installatie: [2026-08-06_jan_nolf_moduleschets_feedback.md](../evidence/2026-08-06_jan_nolf_moduleschets_feedback.md)
- Config: [devices.nolf.json](devices.nolf.json)
