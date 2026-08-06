# Jan Nolf — IPBuilding 03.07 debug log (Action ↔ IP)

Last updated: 2026-08-05

**Bron:** screenshot van Jan Nolf’s debug-procedure in **IPBuilding 03.07**  
(venster `10.10.1.1 - Full Control`, hub hostname `ip2010-167`).  
Asset: [assets/2026-08-05_jan_nolf_ipbuilding_03.07_debug_log.png](assets/2026-08-05_jan_nolf_ipbuilding_03.07_debug_log.png)

**Context UI (rechterpaneel):**
- Hub: `10.10.1.1` / `ip2010-167` — Running
- Scanning input module: `10.10.1.55` -OK-
- Controle output modules: `10.10.1.32`
- Controle dim modules: `10.10.1.42`
- Master-mode, regime **Aanwezig**
- Non-Action rijen in venster: `Verif` → `Time prog data!`; `Analog` ID `9999` → `W:100`

Dit is **geen** pcap — alleen wat de IPBox-app als uitgaande **Action** logt. Wire-bytes zijn niet onafhankelijk bevestigd.

---

## 1. ID-kolom = kanaal (niet “5 protocol-acties”)

In dit venster is **Function=`Action`** steeds dezelfde operatie: een **per-kanaal status-/controle-query** (`I…`).  
De kolom **ID** is het **kanaalnummer**; de kolom **Action** is de UDP-payload (ASCII), afgeleid van dat kanaal + moduletype.

### 1.1 ID → Action (protocol-mapping)

| ID | Relay (.30/.31/.32) Action | Dimmer (.42) Action | Onze kennis |
|----|----------------------------|---------------------|-------------|
| 0 | `I0000` | `I0000000` | Relay: `encode_relay_status_poll(0)`. Dimmer: `encode_dimmer_status_poll(0)` |
| 1 | `I0100` | `I1000000` | idem ch 1 |
| 2 | `I0200` | `I2000000` | idem ch 2 |
| 3 | `I0300` | — (niet in venster) | relay ch 3 |
| 4 | `I0400` | — | relay ch 4 (alleen `.32`) |
| 5 | `I0500` | — | relay ch 5 (alleen `.32`) |

**Regel (bijna altijd):**
- Relay: `Action == f"I{ID:02d}00"` (5 bytes) — bevestigd cold-boot sweep / `state_poll.py`
- Dimmer: `Action == f"I{ID}000000"` (8 bytes) — in library als `encode_dimmer_status_poll`

**Telling:** er zijn **6 unieke IDs** (0–5), niet 5. Unieke Action-*strings*: **9** (`I0000`…`I0500` + drie dimmer-varianten). Dat zijn **geen** vijf verschillende protocol-verbs (geen `S`/`C`/`T`/`P`/`DIM` hier).

### 1.2 Wat “5 acties” wél kan zijn (andere UI-meter)

Rechterpaneel:
- **Uit te voeren acties relais: 3**
- **Uit te voeren acties dim: 2**

Som = **5** — dat is de **logic-queue** (pending uitvoeringen), *niet* de Action-kolom in de log. In dit screenshot-fragment verschijnen die pending acties **niet** als `S`/`C`/`T`/`…1030`-regels; we zien alleen de controle-sweep.

### 1.3 Per-module kanaalbereik in dit venster

| Module-IP | Type | IDs gezien | Action-patronen |
|-----------|------|------------|-----------------|
| `10.10.1.30` | relay | 0–3 | `I0000`…`I0300` |
| `10.10.1.31` | relay | 0–2 | `I0000`…`I0200` |
| `10.10.1.32` | relay | 0–5 | `I0000`…`I0500` |
| `10.10.1.42` | dimmer | 0–2 | `I0000000` / `I1000000` / `I2000000` |

**Installatie Nolf ≠ lab-referentie:** relays `.30`/`.31`/`.32`, dimmer `.42`, input `.55`. Lab: typisch `.30` / `.40` / `.50`.

Cadence (~1 s, modules interleaved) = **controle-/sweep-loop**, niet steady-state keepalive (~20 s `P0000`/`I9900`).

**Anomalie ID↔Action:** rij 1621 — ID=`1`, Action=`I0000` (breekt de regel hierboven).

**Live bevestigd 2026-08-05:** `I{ch}000000` → `I0154{ch}{vv}` op lab-dimmer `.40` — zie [2026-08-05_dimmer_I_ch_000000_status_poll.md](2026-08-05_dimmer_I_ch_000000_status_poll.md).

---


## 2. Volledige Action-rijen (transcriptie screenshot)

| # | Tijd | ID | IP | Action |
|---|------|----|----|--------|
| 1596 | 20:53:14 | 0 | 10.10.1.31 | `I0000` |
| 1597 | 20:53:15 | 3 | 10.10.1.32 | `I0300` |
| 1598 | 20:53:16 | 0 | 10.10.1.30 | `I0000` |
| 1599 | 20:53:17 | 0 | 10.10.1.42 | `I0000000` |
| 1600 | 20:53:17 | 1 | 10.10.1.31 | `I0100` |
| 1601 | 20:53:18 | 1 | 10.10.1.30 | `I0100` |
| 1602 | 20:53:19 | 1 | 10.10.1.42 | `I1000000` |
| 1603 | 20:53:20 | 2 | 10.10.1.31 | `I0200` |
| 1605 | 20:53:21 | 4 | 10.10.1.32 | `I0400` |
| 1606 | 20:53:22 | 2 | 10.10.1.30 | `I0200` |
| 1607 | 20:53:22 | 2 | 10.10.1.42 | `I2000000` |
| 1608 | 20:53:23 | 0 | 10.10.1.31 | `I0000` |
| 1609 | 20:53:24 | 5 | 10.10.1.32 | `I0500` |
| 1610 | 20:53:25 | 0 | 10.10.1.30 | `I0000` |
| 1611 | 20:53:26 | 0 | 10.10.1.42 | `I0000000` |
| 1612 | 20:53:27 | 1 | 10.10.1.31 | `I0100` |
| 1613 | 20:53:28 | 0 | 10.10.1.32 | `I0000` |
| 1614 | 20:53:29 | 1 | 10.10.1.30 | `I0100` |
| 1615 | 20:53:30 | 1 | 10.10.1.42 | `I1000000` |
| 1616 | 20:53:31 | 2 | 10.10.1.31 | `I0200` |
| 1617 | 20:53:32 | 1 | 10.10.1.32 | `I0100` |
| 1618 | 20:53:33 | 0 | 10.10.1.42 | `I0000000` |
| 1619 | 20:53:33 | 0 | 10.10.1.31 | `I0000` |
| 1620 | 20:53:34 | 0 | 10.10.1.32 | `I0000` |
| 1621 | 20:53:35 | 1 | 10.10.1.30 | `I0000` |
| 1622 | 20:53:37 | 1 | 10.10.1.32 | `I0100` |
| 1623 | 20:53:38 | 2 | 10.10.1.30 | `I0200` |
| 1624 | 20:53:40 | 1 | 10.10.1.42 | `I1000000` |
| 1625 | 20:53:40 | 1 | 10.10.1.31 | `I0100` |
| 1626 | 20:53:40 | 2 | 10.10.1.32 | `I0200` |
| 1628 | 20:53:41 | 3 | 10.10.1.30 | `I0300` |
| 1629 | 20:53:42 | 2 | 10.10.1.42 | `I2000000` |
| 1630 | 20:53:43 | 0 | 10.10.1.31 | `I0000` |

**Anomalie:** rij 1621 — ID=`1` maar Action=`I0000` (elders is ID consistent met kanaal in de payload). Mogelijk UI/log-glitch of andere semantiek van ID; niet overinterpreteren zonder pcap.

---

## 3. Match tegen `gateway/payloads/`

### Relay — **match** (`I<CH>00`)

Formaat in log: `I` + 2-cijfer kanaal + `00` (5 ASCII bytes).

| Log | Library |
|-----|---------|
| `I0000` / `I0100` / … / `I0500` | `encode_relay_status_poll(ch)` → `f"I{ch:02d}00"` in [`gateway/payloads/relay.py`](../../../gateway/payloads/relay.py) |
| Gebruikt door | `gateway/state_poll.py` (startup sweep) |

Dit is **dezelfde** cold-boot / on-demand status-query als in [2026-06-12_ipbox_boot_relay_sweep.md](2026-06-12_ipbox_boot_relay_sweep.md).  
Steady-state keepalive blijft `P0000` (`udp_bus.py`) — die komt in dit screenshot-venster **niet** voor.

**Let op:** `I0000` op een relay-IP is **kanaal-0 statuspoll**, niet de input-keepalive (`encode_input_poll()` → ook `I0000`, maar naar input-IP). Zelfde bytes, andere module.

### Dimmer — **match** (`I{ch}000000`)

| Log | Library |
|-----|---------|
| `I0000000` / `I1000000` / `I2000000` | `encode_dimmer_status_poll(ch)` → `f"I{ch}000000"` |
| Gebruikt door | `gateway/state_poll.py` (`sweep_dimmer_states`) |
| Reply | bestaand `I0154{ch}{vv}` |

Live bevestigd 2026-08-05 op lab `.40`: [2026-08-05_dimmer_I_ch_000000_status_poll.md](2026-08-05_dimmer_I_ch_000000_status_poll.md).  
`I9900` blijft steady-state idle keepalive (geen setpoint).

### Input — **niet zichtbaar in Action-kolom**

Rechterpaneel scant `10.10.1.55`, maar in dit scrollvenster geen Action naar `.55`. Input-poll in library: `I0000` → [`gateway/payloads/input.py`](../../../gateway/payloads/input.py).

### Commando’s S/C/T/P — **afwezig** in dit fragment

Geen ON/OFF/DIM/toggle in de Action-kolom; puur controle/query-achtige `I…`-strings.

---

## 4. Library-checklist (kort)

| Wire / log | In library? | Waar |
|------------|-------------|------|
| Relay status query `I<CH>00` | ✅ | `relay.encode_relay_status_poll` |
| Relay keepalive `P0000` | ✅ | `udp_bus` (niet in dit scherm) |
| Dimmer idle `I9900` | ✅ | `dimmer` / `udp_bus` (niet in dit scherm) |
| Dimmer `I{ch}000000` | ✅ | `dimmer.encode_dimmer_status_poll` + `state_poll.sweep_dimmer_states` |
| Input poll `I0000` | ✅ | `input.encode_input_poll` (andere IP) |

---

## 5. Vervolg

1. ~~Reply op `I{ch}000000`~~ — gedaan (lab `.40`, 2026-08-05): `I0154{ch}{vv}`.
2. ~~Encoder + `state_poll`~~ — gedaan (`encode_dimmer_status_poll` / `sweep_dimmer_states`).
3. Optioneel: PCAP tijdens Nolf debug-sessie om UI-Action = wire te bevestigen op zijn installatie (`.42`).
