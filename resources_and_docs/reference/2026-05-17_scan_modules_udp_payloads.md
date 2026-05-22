# Scan Modules — UDP / L2 veldbus analyse

**Datum:** 2026-05-17  
**Capture:** `captures/2026-05-17T210800Z_scan_modules/capture.pcapng`  
**Duur:** 128 s (2748 frames), interface **en7**, start `2026-05-17 21:06:08`  
**Filter lab:** mirror **7←15** (standaard veldbus-POV; relay/input niet zichtbaar als unicast in deze run)

---

## Samenvatting

Tijdens de scan-sessie zijn **twee discovery-mechanismen** zichtbaar op de mirror:

1. **UDP/10001 broadcast** — herhaalde probe `01 00 00 00` vanaf `10.10.1.1` (IPBox veldbus) naar `255.255.255.255` en **`233.89.188.1`** (~elke **10,5 s**). Geen antwoorden vastgelegd op deze POV.
2. **ARP** — `10.10.1.1` → `10.10.1.254` (**128×**, ~1 Hz) en incidenteel → `10.10.1.40` (4× who-has).

**UDP/1001** (runtime veldbus) toont alleen **normale poll** hub ↔ dimmer `10.10.1.40` (`I0000` / `I0154999`); **geen** extra burst die aan “Start scan” gekoppeld is in deze capture.

**Niet gezien op mirror:** unicast vanaf `10.10.1.30` (relay) of `10.10.1.50` (input) — terwijl de WebConfig-UI die wél als scan-resultaat toont → discovery-antwoord loopt waarschijnlijk **op de IPBox intern** of via een ander pad (UDP 10001 reply niet gemirrord).

---

## UDP poort 10001 — discovery probe (nieuw)

| Veld | Waarde |
|------|--------|
| Bron | `10.10.1.1` (IPBox hub, IPBuilding-VLAN) |
| Doel | `255.255.255.255` **en** `233.89.188.1` |
| Poort | **10001** (UDP) |
| Payload (hex) | `01 00 00 00` (4 bytes, vast) |
| Interval | ~10,5 s (13 rondes in 128 s capture) |
| Ook zichtbaar vanaf | `192.168.1.1`, `192.168.0.1` (andere routers op mirror) |

**Hypothese:** zelfde familie als **DS-manager**-broadcast uit installatiehandleiding (§12.6 knowledge): MAC/IP-koppeling van modules. Type-byte `0x01` = discovery/request; rest nog open.

**Gateway-actie:** luister op `0.0.0.0:10001` op de veldbus-interface; log antwoorden; replay probe en vergelijk met IPBox-gedrag.

---

## UDP poort 1001 — normale poll (geen scan-burst)

| Richting | Frames | Payload (ASCII) | Interval |
|----------|--------|-----------------|----------|
| `10.10.1.1` → `10.10.1.40:1001` | 6 | `I0000` | ~20 s |
| `10.10.1.40` → `10.10.1.1` | 6 | `I0154999` (status reply) | ~14 ms na poll |

Geen verkeer naar `10.10.1.30` of `10.10.1.50` in deze pcap.

---

## ARP-gedrag (IPBox `10.10.1.1`)

| Doel-IP | Who-has count | Opmerking |
|---------|---------------|-----------|
| `10.10.1.254` | 128 | ~1/s, volledige capture-duur |
| `10.10.1.40` | 4 | ~elke 40 s |

Geen ARP who-has naar `.30` of `.50` op deze mirror.

---

## Correlatie scan-UI ↔ capture

| Module (UI) | UDP/1001 in pcap | UDP/10001 reply | ARP |
|-------------|------------------|-----------------|-----|
| `10.10.1.30` relay | Niet gezien | Niet gezien | Niet gezien |
| `10.10.1.50` input | Niet gezien | Niet gezien | Niet gezien |
| `10.10.1.40` dimmer | Poll + reply | Niet gezien | 4× who-has |

Conclusie: **“Start scan” in WebConfig triggert niet zichtbaar een extra UDP/1001-storm** op mirror 7←15; discovery gebruikt vermoedelijk **UDP/10001** (en/of interne IPBox-service) plus projectdatabase voor “Bestaande”.

---

## Aanbevolen her-capture (POV + filters)

```bash
# en7, mirror 7←15 actief
dumpcap -i en7 -f 'host 10.10.1.1 and (udp port 10001 or udp port 1001 or arp)' \
  -w scan_modules_bidir.pcapng
```

Tijdens capture: alleen **Start scan** in UI; noteer timestamp. Daarna:

```bash
tshark -r scan_modules_bidir.pcapng -Y 'udp.port==10001' -T fields \
  -e frame.time_relative -e ip.src -e ip.dst -e udp.payload
```

Optioneel tweede capture op **thuis-LAN** voor `POST ScanForModules` (HTTP), of browser HAR.

---

## Open hypotheses

- Antwoord-payload op UDP **10001** (module → hub) nog niet vastgelegd.
- Betekenis van multicast `233.89.188.1` (IPBuilding-specifiek discovery group).
- Of scan een **volledige subnet-sweep** doet (ARP naar alle `.30`–`.59`) op een NIC die niet gemirrord wordt.
