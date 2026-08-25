# Jan Nolf — veldtest dialect (2026-08-24)

Last updated: 2026-08-25 (§5.1 kanaalcorrectie, §8 checklist 1.6.5 OPEN)

**Bron:** Spark mail Jan Nolf (`jan@nolfvdh.be`), thread *integratie IPBuilding in HA — moduleschets, EEPROM’s & WebUI*

| Mail ID | Tijd | Inhoud |
|---------|------|--------|
| 115145 | 07:45 | Update 1.6.4 nog niet in add-on store |
| 115351 | 22:32 | **1.6.4 OK** — dimmers werken; status Onbekend + korte log |
| 115352 | 22:38 | Debug-log + relais: lamp aan, HA-status blijft uit |

**Assets:** [assets/2026-08-24_jan_nolf_dialect_field_test/](assets/2026-08-24_jan_nolf_dialect_field_test/)

| Bestand | Inhoud |
|---------|--------|
| `3059e002_ipbuilding_gateway_2026-08-24T20-31-29.427Z.log` | Post-install fragment (info) |
| `3059e002_ipbuilding_gateway_2026-08-24T20-35-36.074Z.log` | **Debug-sessie** (22:34–22:35) — primair bewijs |

**Dialect-registry (canoniek):** [veldbus_dialect_registry.md](../reference/veldbus_dialect_registry.md)  
**Decode-spec (1.6.5):** [2026-08-25-nolf-dialect-decode-design.md](../../docs/superpowers/specs/2026-08-25-nolf-dialect-decode-design.md)  
**Sprintplan:** [2026-08-24-nolf-dialect-sprint-plan.md](../../docs/superpowers/plans/2026-08-24-nolf-dialect-sprint-plan.md)

**Voorafgaand:** [2026-08-08_jan_nolf_restore_test.md](2026-08-08_jan_nolf_restore_test.md)

---

## 1. Samenvatting Jan

| Observatie | Status |
|------------|--------|
| Gateway **1.6.4** na herinstallatie | ✅ |
| Dimmers zichtbaar + bedienbaar | ✅ (grote vooruitgang t.o.v. 8 aug) |
| Dimmer **status** in HA | ❌ Onbekend |
| Relais bedienen | ✅ |
| Relais **status na toggle** | ❌ lamp verandert, HA niet |
| IPBox | Nog aan (`hub_role=slave` in log) |

---

## 2. Omgeving (log 22:34)

```
IPBuilding Gateway v1.6.4
hub_role=slave
GATEWAY_LOG_LEVEL=debug  (tijdens testsessie)
install=relay@10.10.1.30, relay@10.10.1.31, relay@10.10.1.32,
        dimmer@10.10.1.42, input@10.10.1.55
```

---

## 3. Relais `.30` — startup status-poll (1.6.4 prefix-fix **werkt**)

Gateway seed na boot (debug-log `22:34:22–25`):

| state_code | Decode 1.6.4 | Voorbeelden kanalen |
|------------|--------------|---------------------|
| `0015` | **off** | ch1 trap, ch3–5, ch12–15, ch17–18, ch20–22 |
| `0115` | **on** | ch2, ch6 keuken LED, ch7, ch23 |
| `0100` | **on** | ch8 eetplaats, ch10, ch19 |
| `0000` | **off** | ch9 bureau Jan, ch11, ch32 ch0 |

→ Als HA nog **Onbekend** toont voor relais: suspect **companion/entity-sync**, niet startup-decode. Dimmer-entities blijven Onbekend door open dimmer-decode (§5).

---

## 4. Relais `.30` — command-reply dialect **`relay.nolf.command_reply`** (OPEN)

Jan (mail 115352): status stond op **uit**, na bediening **brandde lamp**, HA bleef **uit**.

Log (ch6 = Ledverlichting keuken):

```
22:34:44  TX  command OFF  C0600
22:34:44  RX  C060000000           → undecoded
22:34:57  TX  command OFF  C0600    (herhaald)
22:34:57  RX  C060000000           → undecoded
```

**Bevinding:** Nolf IP0200 antwoordt op commando met **`C{ch}00{state:04d}`** (10 ASCII), niet met lab-formaat **`I0000{ch}{state}`**.

**Huidige code:** `decode_relay_payload()` matcht alleen 5-byte commands (`C0600`) en I-prefixed status — **geen** 10-byte command-reply.

**Gevolg:** geen `STATE`-update → companion/HA blijft op oude waarde → toggle onbruikbaar.

**Dialect-id:** `relay.nolf.command_reply` — zie [registry § Relay](../reference/veldbus_dialect_registry.md#relay--detail).

---

## 5. Dimmer `.42` — status-reply dialect **`dimmer.nolf.status_reply`** (OPEN)

### 5.1 Commando's werken (lab hub-dialect)

```
22:34:35  TX  DIM  S1231030   →  RX  S1231030    (ch1 Lichtstraat → 23 %)
22:34:36  TX  DIM  S1471030   →  RX  S1471030    (ch1 → 47 %)
22:34:39  TX  DIM  S1471030   →  RX  S1471030    (ch1 → 47 %, herhaald)
22:34:41  TX  DIM  C1991030   →  RX  C1991030    (ch1 uit)
```

→ **`dimmer.nolf.hub_command`** = zelfde encode als lab; Jan bevestigt "dimmers werken".

**Correctie op een eerdere lezing:** het formaat is `<S|C><ch><vv>1030`, dus dit is telkens **kanaal 1** op 23 % / 47 % / uit — niet ch2/ch4/ch9. Dat sluit aan op de poll van 22:34:26, die ch1 op 84 % zette: Jan speelde met de Lichtstraat.

### 5.2 Status-poll: module antwoordt, verkeerde family

```
TX  I0000000  →  RX  I0115099   (unmatched / undecoded)
TX  I1000000  →  RX  I0115184
TX  I2000000  →  RX  I0115299
TX  I3000000  →  RX  I0115300
```

Lab verwacht **`I0154{ch}{vv}`** (family **`54`**).  
Nolf stuurt **`I0115{ccc}`** (family **`15`**).

Keepalive (niet poll): `I0115000` i.p.v. lab `I0154999` / poll `I9900`.

**Huidige code:** `_DIMMER_REPLY_RE` vereist family `54` → alles `I0115…` = undecoded → poll timeout → geen brightness in registry → HA **Onbekend**.

**Dialect-id:** `dimmer.nolf.status_reply` + `dimmer.nolf.idle_keepalive`.

### 5.3 Ack na commando = **echo**, geen statusframe (nieuw 2026-08-25)

De RX-regels in §5.1 zijn geen statusreply maar de **letterlijk teruggestuurde commandobytes**. In het lab antwoordt de dimmer op `S0501030` met `I0154050` — een echt statusframe (bewijs: [2026-06-01 veldtest](2026-06-01_gateway_field_test.md) § Command/reply, met de gateway zelf als hub; en Sprint 3 pcap `01:01.pcapng`, 11 Tx / 11 Rx op `10.10.1.40` zonder één teruggestuurde `S…1030`).

Dat er bij Jan géén statusframe volgde, blijkt uit wat ontbreekt: tussen 22:34:35 en 22:34:41 staat in de debug-log geen enkele `undecoded RX from 10.10.1.42`, terwijl elke `I0115…` elders in diezelfde log wél zo gelogd werd (polls 22:34:25–27, keepalives 22:34:21/42 en 22:35:02).

De echo verdwijnt vandaag geruisloos omdat `decode_dimmer_payload` hem netjes herkent als `dimmer_command` — dus geen "undecoded" — terwijl `DeviceRegistry._handle_dimmer` alleen op `dimmer_status_reply` reageert.

**Gevolg voor de fix:** op deze modulegeneratie is de echo de enige directe feedback na bediening. Wil de HA-status meteen kloppen, dan moet de echo de state seeden (`S1231030` = ch1 → 23 %); anders blijft het wachten op de volgende pollronde. Zelfde patroon als bij de relay in §4, waar de echo het state-quartet meekrijgt.

**Dialect-id:** `dimmer.nolf.command_echo` — zie [registry § Ack-model](../reference/veldbus_dialect_registry.md#ack-model-per-generatie-2026-08-25).

---

## 6. Input `.55`

Alleen binary hex in debug-log (`490228…`, `462878…`) — geen `B-…E`.  
Verwacht op oudere generatie. Knoppen uit **`devices.nolf.json`**, niet UDP-decode.

---

## 7. Vergelijking 8 aug → 24 aug

| Issue | 8 aug (1.6.2) | 24 aug (1.6.4) |
|-------|---------------|----------------|
| Relais startup `0015`/`0115` | unknown in HA | ✅ off/on in gateway |
| Relais na commando | geen update | ❌ ack `C06…` undecoded |
| Dimmer commando | faalde / timeout | ✅ werkt |
| Dimmer status poll | geen reply | reply **`I0115…`** maar undecoded |
| Debug TX/RX logging | nee | ✅ (1.6.3+) |

---

## 8. Open validatie bij Jan (gateway 1.6.5)

**Status: OPEN** tot Jan antwoordt. Decoder-wijzigingen staan in 1.6.5; deze sectie sluit niet eerder.

### Release note (NL)

Relaisstatus volgt nu direct na schakelen. Dimmerstatus en helderheid komen door op de oudere 0-10V-module.

**Slave-modus:** zolang de IPBox nog op de veldbus staat, kunnen replies deels naar de IPBox gaan in plaats van naar de gateway. Test daarom eerst mét IPBox, daarna met ethernet eruit.

### Twee oorzaken

De debug-log van 24 aug bevat Jan's "lamp aan / HA uit" **niet** als ON-commando — alleen twee keer OFF op ch6, terwijl de startup-poll ch6 als aan seedde. Echo-decode lost dat HA-verschil niet vanzelf op. Vandaar stap 5: gateway naast HA leggen.

### Checklist

1. Update gateway naar **1.6.5**; companion ≥1.8.3; **Home Assistant herstarten**.
2. **Relais ch9** (Verlichting bureau Jan): in HA **AAN**, daarna **UIT**. Bevestig dat de HA-status de lamp volgt. Dit levert ook het ontbrekende `S09…`-echo-sample (quartet-layout).
3. **Dimmer ch1 Lichtstraat:** slider op **50 %**. Bevestig dat het percentage in HA verschijnt (niet Onbekend).
4. **Zithoek (dimmer ch0) tijdens keepalive:** kijk of die lamp **brandt** terwijl de gateway idle/keepalive draait (geen slider). Dat beslecht of `I0115000` een idle-sentinel is of "ch0 uit".
5. **Diagnose gateway vs HA** — vlak na het schakelen de stand in de gateway zelf (`GET /api/v1/devices` of de Web UI) naast de HA-entity leggen:
   - Gateway klopt, HA niet → companion / entity-sync.
   - Gateway ook fout → decode (of reply naar IPBox in slave-modus).
   - Zonder deze stap levert "werkt niet" geen richting op.
6. Optioneel: logniveau **debug** ±2 min, daarna terug naar **info**.
7. Daarna: **IPBox-ethernet eruit**, herhaal stappen 2–4 (en 5 bij twijfel).

Oude vragen die blijven meelopen: prefix `0015`=off / `0115`=on fysiek op 3–4 relaiskanaalen.

---

## 9. Log-index (debug-sessie)

| Tijd | Regel-type | Betekenis |
|------|------------|-----------|
| 22:34:19 | restart | debug logging aan |
| 22:34:21–25 | `state_poll` | relay seed 22 kanalen |
| 22:34:25–27 | `state_poll` | dimmer poll timeouts |
| 22:34:35–41 | `gateway_api` DIM | dimmer commando's ch1 — echo-ack, geen statusframe (§5.3) |
| 22:34:44, 57 | `gateway_api` OFF | relay ch6 undecoded ack |
| 22:35:19 | shutdown | einde sessie |
