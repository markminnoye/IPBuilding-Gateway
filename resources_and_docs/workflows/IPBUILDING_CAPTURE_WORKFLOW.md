# IPBuilding Capture Workflow (golden run)

Dit document operationaliseert de reverse-engineering capture-aanpak voor UDP/1001 en fysieke schakelaars, met herbruikbare logging voor latere analyse.

**Waar PCAPs staan:** [CAPTURES.md](../CAPTURES.md) — standaard output `captures/<session>/` (gitignored); referentie-PCAP in `resources_and_docs/pcap_archive/`.

## 0) Vereisten

```bash
python3 -m pip install -r "/Users/markminnoye/git/IPBuilding Gateway/requirements-capture.txt"
```

## 1) Capture-POV: mirror op Ethernet capture-interface

### Actieve modus: UniFi mirror naar capture-Mac (`en7`)

- Mirror op de switchpoort(en) die het relevante verkeer dragen:
  - controllerpoorten op Switch 16: `12` (`10.10.1.40`), `13` (`10.10.1.50`), `14` (`10.10.1.30`)
  - en/of de uplink/poort met de IPBox-stroom die je wil correleren.
- Capture-interface op Mac = de bekabelde aansluiting (printerpoort/VLAN-kant).
- In huidige setup: capture-interface is `en7` (`192.168.1.107`), mirror destination is Switch 16 poort `7`.
- Resultaat: bij correcte mirrorconfiguratie 1 `pcapng` met zowel IPBox↔controller UDP/1001 als eventuele HTTP/REST-stromen die op de mirrored poort zichtbaar zijn.
- **Alleen dimmer `10.10.1.40`:** mirrorbron **poort 12** (niet 11). Voor getimede REST-stappen met UTC-log en optionele `statuses`-snapshots: repo-script `**scripts/dimmer_only_re_stimulus.sh`** (combineer met `dumpcap` op `en7`).

### Aanbevolen standaardspiegel (IPBox / veldbus)

- **Primair voor RE op de IPBox aan de veldbus-kant:** spiegel **bron poort 15 → bestemming poort 7** (hier genoteerd als **`7←15`**). Dat been is het **tweede Ethernet** van de IPBox op het controller-VLAN (`10.10.1.1`); typisch verschijnt daar **UDP/1001** hub ↔ controllers, vaak **bidirectioneel** op `en7` — dit is de POV die je het meest wilt vastleggen in `manifest.jsonl` (mirror + UTC van apply).
- **Alternatief (relay-switchpoort, tweede keus na `7←15`):** **`7←14`** — alleen wanneer je expliciet het pad naar de relay op `10.10.1.30` als bronpoort wilt; minder geschikt als default voor volledige hub-bidirectioneel zicht (zie [2026-05-15_capture_bidirectional_explainer.md](../evidence/2026-05-15_capture_bidirectional_explainer.md)).
- **Niet “alle” IPBox-verkeer:** de unit is **dual-homed**. **REST `:30200`** naar het **thuis-LAN** loopt over het **andere** been (bij jullie veelal US16 **poort 8**). Dat zie je **niet** op een alleen-**7←15**-opname; combineer met een aparte run **7←8** wanneer je REST-bytes op dezelfde switch wilt zien (let op de bekende **poort-8**-risico’s in [CAPTURE_LIVE_STATUS.md](CAPTURE_LIVE_STATUS.md)).
- Zie ook `resources_and_docs/evidence/2026-05-15_capture_bidirectional_explainer.md` (richting-tellingen en POV-matrix).

### Dimmer sweep (per `DIMMER_ID`)

Gebruik **één capture-run per gekozen component-ID** (571 / 572 / 573 — niet meerdere dimmers in dezelfde sweep-run mengen).

- **Mirror:** bestemming blijft doorgaans poort `7` (`en7` op de Mac). Bron kies je naar doel:
  - `**7←15`** — been met IPBox op het controller-VLAN (UDP naar/van `10.10.1.1`), of
  - `**7←12**` — dimmer `10.10.1.40` op Switch 16 (zoals eerdere dimmer-captures). Zie ook `CAPTURE_LIVE_STATUS.md` voor operationele notities.
- **Parallel op `en7`:** `sudo tcpdump` of `dumpcap` met brede UDP-BPF, bijvoorbeeld:

```bash
sudo tcpdump -ni en7 -s0 -U -w "/absolute/path/to/capture.pcapng" 'udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185)'
```

- Start capture **vóór** de eerste REST-actie.
- **Stimulus per dimmer-ID** (één run per commando):

```bash
DIMMER_ID=571 STEP_PAUSE_SEC=22 MANIFEST_PATH="/absolute/path/to/571_dimmer_sweep_manifest.log" bash "/Users/markminnoye/git/IPBuilding Gateway/scripts/dimmer_sweep_stimulus.sh"
DIMMER_ID=572 STEP_PAUSE_SEC=22 MANIFEST_PATH="/absolute/path/to/572_dimmer_sweep_manifest.log" bash "/Users/markminnoye/git/IPBuilding Gateway/scripts/dimmer_sweep_stimulus.sh"
DIMMER_ID=573 STEP_PAUSE_SEC=22 MANIFEST_PATH="/absolute/path/to/573_dimmer_sweep_manifest.log" bash "/Users/markminnoye/git/IPBuilding Gateway/scripts/dimmer_sweep_stimulus.sh"
```

- **Permissies na `sudo`:** als capture-bestanden als root zijn aangemaakt, herstel eigenaarschap direct na de run:

```bash
sudo chown -R "$USER":"$(id -gn)" "/absolute/path/to/session_dir"
```

**Correlatie na afloop:** `scripts/correlate_capture_session.py` verwacht een orchestrator-sessiemap met o.a. `manifest.jsonl` (JSON-events per regel). De sweep schrijft alleen een **platte tekstregel** per actie (`UTC actie URL`). Voor sweep-only runs: gebruik de UTC-tijdstempels uit dat log en zoek de bijbehorende frames in Wireshark/tshark, bijvoorbeeld:

```bash
tshark -r "/pad/naar/capture.pcapng" -Y "udp.port==1001" -T fields -e frame.time -e frame.number -e ip.src -e ip.dst -e data
```

Handmatig paren: manifestregel ↔ `frame.time` (UTC) in de pcap. Wil je later geautomatiseerde correlate, voer dan een golden `ipbuilding_capture_run.py`-sessie uit of converteer events naar hetzelfde `manifest.jsonl`-formaat als de orchestrator.

## 2) MacBook networking: WiFi + Ethernet (aanbevolen in deze setup)

- Je mag WiFi actief houden voor AI/Internet en tegelijk captures doen op Ethernet.
- Capture blijft **expliciet op `en7`** (interface-gebonden), onafhankelijk van default route.
- Voor consistentie:
  - forceer altijd `--interface en7` bij captures,
  - verifieer per run dat `udp/1001` zichtbaar is in de eerste 20-30 seconden.

## 3) Sessiemap-contract (verplicht)

Gebruik per run een aparte map:

```text
captures/<UTC_TIMESTAMP>_<run_name>/
  capture.pcapng
  manifest.jsonl
  inventory_pre.json
  runbook.yaml
  ip1100_getbuttons_pre.json
  ip1100_getbuttons_post.json
  run.log
  README.txt
  exports/
    conversations.txt
    udp_stream_index.txt
```

Minimaal verplicht voor elke run: `capture.pcapng`, `manifest.jsonl`, `inventory_pre.json`, `runbook.yaml`, `run.log`, `README.txt`.

## 4) Golden run volgorde

Startcommando:

```bash
sudo python3 "/Users/markminnoye/git/IPBuilding Gateway/ipbuilding_capture_run.py" --interface en7 --runbook "/Users/markminnoye/git/IPBuilding Gateway/resources_and_docs/workflows/ipbuilding_golden_runbook.yaml" --output-root "/Users/markminnoye/git/IPBuilding Gateway/captures"
```

1. Start capture.
2. Snapshot inventaris (`/api/v1/comp/items`) en save als `inventory_pre.json`.
3. Snapshot IP1100 knoppenmapping (`/api.html?method=getButtons`) en save als `ip1100_getbuttons_pre.json`.
4. Voer output-REST-sequentie uit (relay/dimmer/scene).
5. Voer fysieke drukknoppenblok uit (manifest event per knopdruk, 3-5s stilte tussen drukken).
6. Optioneel post-snapshot `getButtons`.
7. Stop capture en laat extra 20-30s rust-window voor pollingframes.

## 5) Post-capture analyse (**Wireshark MCP** — aanbevolen)

**Capteer altijd met `wireshark_capture` (MCP) of `dumpcap`/`tcpdump`; analyseer met `wireshark_stats_endpoints` / `wireshark_list_ips` / hex dumps via Wireshark MCP of `tshark -x`. Vermijd enkelvoudige `ip.src==X` filters bij bidirectionele checks — gebruik `ip.addr==X` of vergelijk endpoints-statistieken.**

Voorbeeld-endpoints-check na elke capture:

```bash
# Wireshark MCP: endpoints en UDP-statistieken
wireshark_stats_endpoints(pcap_file, type="udp")
# en wireshark_stats_endpoints(pcap_file, type="ip") voor IP-overzicht
```

Voorbeeld hex-dump voor UDP/1001:

```bash
# tshark hex dump (tshark -x) voor payload-analyse
tshark -r "/pad/naar/capture.pcapng" -Y "udp.port==1001" -x
```

Aanbevolen workflow:

- Open `manifest.jsonl` en noteer event timestamps.
- Filter in Wireshark op `udp.port == 1001 && ip.addr == 10.10.1.50` voor fysieke input-correlatie.
- Vergelijk payloads rond `physical_input` events en koppel met `getButtons`-snapshot.

## 6) Scope-grens: Ethernet vs buslaag

- **Ethernet-scope (in dit workflow):** IPBox↔controllers verkeer (UDP/1001, REST/HTTP).
- **Niet in Ethernet-PCAP:** de Cat5-bus tussen IP040x en IP1100 intern.
- Voor wire-level busanalyse is aparte hardwareanalyse nodig (logic analyzer / fysieke meetpunten), los van dit capture-runbook.

