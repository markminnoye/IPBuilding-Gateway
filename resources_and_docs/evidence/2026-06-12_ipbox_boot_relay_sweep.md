# IPBox boot sequence + relay status sweep (2026-06-12)

Last updated: 2026-06-12

**Captures:**
- `captures/2026-06-12_IPBOX_BOOT.pcapng` — mirror op **relay-poort** (`10.10.1.30`), cold boot van de IPBox. Toont de boot-sweep.
- `captures/2026-06-12_IPBOX_POWER_ON_AND_OFF.pcapng` — mirror op **IPBox-poort** (`192.168.0.185`), power-on → ~1 min → power-off. Toont steady-state poll van alle 3 modules + dual-NIC-identiteit + shutdown.

---

## 1. NIEUW: cold-boot relay status-sweep `I<CH>00` → `I000<CH><state>`

Bij een **koude start** leest de IPBox de actuele stand van elke geconfigureerde relay-uitgang uit via een sweep — één query per kanaal — vóór hij overgaat op de `P0000`-keepalive. Dit is **niet** eerder gevangen (alle vorige captures waren steady-state/idle).

Uit `2026-06-12_IPBOX_BOOT.pcapng`, `192.168.0.185` → `10.10.1.30:1001` (t≈72 s, ~90 ms tussen queries):

| Query (IPBox→relay) | Reply (relay→IPBox) | Kanaal | State |
|---|---|---|---|
| `I1700` | `I000170000` | 17 | UIT |
| `I1800` | `I000180100` | 18 | **AAN** |
| `I1900` | `I000190000` | 19 | UIT |
| `I2000` | `I000200000` | 20 | UIT |
| `I2100` | `I000210000` | 21 | UIT |
| `I2200` | `I000220000` | 22 | UIT |
| `I2300` | `I000230100` | 23 | **AAN** |

Daarna: `P0000` → `P000000000` elke 20 s (keepalive), geen verdere I-queries.

### Reproductie (2026-06-12, `2026-06-12_IPBOX_POWER_ON_AND_OFF_DUAL_NETWORK.pcapng`)
Zelfde sweep opnieuw gevangen bij een volgende cold boot, dit keer **kanalen 16–23** (8 in plaats van 7 — kanaal 16 was in de eerste capture vermoedelijk gemist doordat de capture net te laat startte). Query-interval ~90 ms, identiek formaat `I<CH>00`→`I000<CH><state>`; status op dat moment: alleen 18 en 23 AAN, de rest UIT — consistent met de eerste boot. Bevestigt dat de sweep **reproduceerbaar** is bij elke cold boot van de relay-outputs 16–23 (de in dit project geconfigureerde range).

**Formaat:**
- Query = `I` + `<CH,2 cijfers>` + `00` (5 bytes ASCII). Kanaal staat in de **eerste twee cijfers**.
- Reply = `I000` + `<CH,2 cijfers>` + `<VVVV>` (10 bytes ASCII), `VVVV=0100` = AAN, `0000` = UIT.

De sweep dekte alleen kanalen **17–23** (de in dit project geconfigureerde uitgangen van deze relay), niet 0–23. De gateway moet dus sweepen over de outputs die in zijn eigen config staan.

### Corrigeert 2026-06-02 relay-poll-test
[2026-06-02_relay_poll_i_ch_test.md](2026-06-02_relay_poll_i_ch_test.md) concludeerde "`I<ch>` poll geeft enkel `I000000000` echo, geen status". Die test gebruikte echter formaat **`I00<ch>`** (`I0010`/`I0016`/`I0023` = kanaalveld `"00"` + genegeerde suffix), dus de module rapporteerde steeds kanaal 00 (uit) = `I000000000`. Met het **juiste** formaat `I<CH>00` levert de relay wél echte per-kanaal-status — bewezen door het boot-gedrag van de IPBox zelf. De conclusie "IPBox stuurt nooit `I<ch>` naar relay" gold enkel voor idle/steady-state; bij **cold boot** doet hij het wel.

**Implementatie-impact:** `gateway/udp_bus.py:20-21` (`_POLL_RELAY = b"P0000"` met comment "I<ch> returns echo") is achterhaald. De gateway kan/should bij startup een `I<CH>00`-sweep doen over de geconfigureerde relay-outputs om de begintoestand te lezen. De decoder `gateway/payloads/relay.py` (`I000<CH><state>`, `relay_status`-family) ondersteunt de reply al.

---

## 2. Steady-state poll-schema (alle 3 moduletypes)

Uit `2026-06-12_IPBOX_POWER_ON_AND_OFF.pcapng` (poller = `192.168.0.185`, eigen bronpoort per module):

| Module | IP | Query | Interval | Reply |
|---|---|---|---|---|
| Input | `.50` | `I0000` | **~2 s** | binair `49 02 52 05 02 04 00×6 45` (`I`…`E`), live input-bitmap; idle = alles UIT |
| Dimmer | `.40` | `I9900` | ~20 s | `I0154999` (idle/poll, geen setpoint) — zie [2026-05-17_dimmer_I0154xxx_full_decode.md](2026-05-17_dimmer_I0154xxx_full_decode.md) |
| Relay | `.30` | `P0000` | ~20 s | `P000000000` (keepalive) |

Geen per-kanaal sweep voor dimmer of input; enkel de relay krijgt de sweep, en enkel bij cold boot.

**Input-bitmap byte-count:** deze capture toont **13 bytes** (6 nul-bytes), 82/82 identiek. [2026-05-17_ip1100_input_payload_decode.md](2026-05-17_ip1100_input_payload_decode.md) documenteert **14 bytes** (7 nul-bytes) in POV-A. Eén byte verschil — te reconciliëren (firmware/POV of telfout in oudere doc). Structuur verder identiek: `I` + `02 52 05 02 04` (constante header) + nul-bytes (input-state) + `E`.

---

## 3. IPBox-identiteit: één Windows-PC met twee NIC's

De IPBox is **één fysiek apparaat**: een Windows-10 embedded-PC, NetBIOS-hostname **`IP2017-814`**, MAC-OUI `00:30:18` (Jetway). Twee NIC's registreren **beide** de naam `IP2017-814`:
- `192.168.0.185` — draagt de module-polling (gerouteerd naar 10.10.1.x) + cloud.
- `10.10.1.1` — IPBuilding-VLAN, Windows-discovery (SSDP/NBNS/WSD/LLMNR).

Bevestigt de "dual-homed" notities in [RE_STATE.md](../RE_STATE.md) / IPBUILDING_KNOWLEDGE.md §3.0, en voegt de OS/host-identiteit toe. Extra waargenomen IPBox-verkeer: HTTPS naar **Azure** (172.187.86.x, 20.42.73.26), **No-IP dynamic DNS** (`dynupdate.noip.com` → remote-access-mechanisme), Windows-telemetrie (msftncsi / vortex-win / wns).

Intern probeert `192.168.0.185` continu TCP naar `10.10.1.1:1024/1025` (vermoedelijk config/app-kanaal tussen de twee helften) — in deze capture **host-unreachable** (router-ICMP type 3/1), dus inhoud niet waargenomen. Kandidaat-kanaal voor config-sync; vereist capture met beide zijden bereikbaar.

### Poging tot simultane dual-network capture (2026-06-12, `..._DUAL_NETWORK.pcapng`)
Bedoeld om beide NIC's (`192.168.0.185` + `10.10.1.1`) tegelijk te vangen. Resultaat: **`10.10.1.1` komt nul keer voor** in deze capture (nul IP-pakketten, geen ARP, geen NBNS) — ondanks 3624 VLAN-getagde frames (VLAN 1 = internet/thuis-verkeer, VLAN 3 = modules, geen VLAN met `10.10.1.1`). Wel een sterke extra aanwijzing voor de "één toestel, twee NIC's"-hypothese: `.185` draagt hier MAC `00:30:18:00:49:3c`, één hoger dan de eerder waargenomen `10.10.1.1`-MAC `00:30:18:00:49:3b` — opeenvolgende MAC's, typisch voor twee NIC's op hetzelfde moederbord. De TCP-pogingen naar `10.10.1.1:1024/1025` waren dan ook afwezig (want de host was niet op dit segment zichtbaar). **Openstaand:** de mirror/SPAN-configuratie vangt blijkbaar niet beide netwerksegmenten tegelijk; om dit definitief te bevestigen is een capture-opzet nodig die expliciet de poort/VLAN van de `10.10.1.1`-NIC mirrort tijdens dezelfde boot als de module-poort.

---

## 4. Shutdown-gedrag

Bij uitschakelen stuurt de IPBox **geen** afmeld-/goodbye-bericht naar de modules. De polling loopt door en **stopt abrupt** (laatste input-poll t≈227 s, daarna stilte). Modules detecteren een uitgevallen IPBox enkel aan het wegvallen van de keepalive/poll.

---

## 5. Config vs. state — input-mapping zit NIET in de poll

De binaire `.50`-poll rapporteert **live input-state** (welke ingang actief is), **niet** de configuratie (welke actie/doelmodule/uitgang per knop). Die mapping zit in:
- de **EEPROM-autonomietabel** (`.IPA`) van de IP1100, geflasht via `buttonIP1100.exe` (autonome/master-modus), en
- het **IPBox-project** (slave-modus).

Zie [project_config_datamodel] (per-ingangscomponent: ID/Poort/Type/Uitgang/Actie) en de open unknown "Input logical flow" in [RE_STATE.md](../RE_STATE.md). Om de config uit te lezen is een EEPROM-download / WebConfig `ImportInfo` nodig, niet de UDP-statuspoll.
