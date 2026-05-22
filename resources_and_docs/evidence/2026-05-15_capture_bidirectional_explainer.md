# Waarom sommige `en7`-captures geen relay→hub UDP tonen (objectieve check)

## Wat we gemeten hebben (**Wireshark MCP** en tshark op de **ruwe** pcap, niet op `udp_ipbox_export.txt`)

Tel UDP/1001 met **bron `10.10.1.30`** (relay stuurt naar hub):

| Sessie-pcap | Frames `ip.src==10.10.1.30` && `udp.port==1001` |
|-------------|--------------------------------------------------|
| `captures/2026-05-14T214007Z_push-pull-run-a-quiet-evening/capture.pcapng` | **0** |
| `captures/2026-05-14T214905Z_push-pull-run-c-idle/capture.pcapng` | **0** |
| `captures/2026-05-14T220000Z_push-pull-run-a-quiet-evening/capture.pcapng` | **0** |

Tel hub→relay (`10.10.1.1` → `10.10.1.30`): in diezelfde files **wel** 8–13 frames.

**Conclusie:** in deze opnames zat **letterlijk geen** UDP/1001 van de relay naar de hub in het bestand. `scripts/correlate_capture_session.py` kan zulke frames niet “wegsnijden” als ze er niet zijn — de gate **WARN** volgt dus uit de **pcap-inhoud**, niet uit een verkeerde correlate-filter.

## BPF van de orchestrator sluit relay→hub niet uit

Runbook-BPF gebruikt o.a. `udp and (host 10.10.1.1 or host 10.10.1.30 or …)`. Een pakket **`10.10.1.30` → `10.10.1.1`** voldoet aan `host 10.10.1.30` en `host 10.10.1.1` en zou worden opgenomen **als** het op `en7` aankomt. Zie `ipbuilding_capture_run.py` (`dumpcap … -f '<bpf>'`).

## Vergelijking met referentie-`long_capture.pcapng` (in repo)

Canoniek pad: [pcap_archive/long_capture.pcapng](pcap_archive/long_capture.pcapng) — documentatie: [2026-05-15_long_capture_reference.md](2026-05-15_long_capture_reference.md).

Daarin: UDP/1001 **twee richtingen** `10.10.1.1` ↔ `10.10.1.30` (en ↔ `.40`, ↔ `.50`) — dat is **wél** bidirectioneel in het bestand zelf.

## Wat dat betekent voor “zelfde mirror 15→7”

Als de spiegel **exact** dezelfde UniFi-configuratie was op twee momenten, zou je **verwachten** dat vergelijkbare relay-conversaties ook in de korte pcaps verschijnen. Dat ze **0×** `10.10.1.30`→`10.10.1.1` tonen, wijst praktisch op één van:

1. **Toch een ander effectief pad / mirror-state** tussen de runs (UI vs werkelijkheid, tussenstap apply, andere bron, rollback, tweede sessie korter venster, enz.) — zonder UniFi-export op elk moment niet te bewijzen vanuit de repo.
2. **Zeldzamer**: relay antwoordt alleen onder omstandigheden die in het lange venster wél voorkwamen maar in het korte REST-venster niet (minder plausibel bij periodieke `P`/poll), of timing buiten het venster.

## Aanbevolen sanity-check na elke capture

**Wireshark MCP (aanbevolen):**
```python
wireshark_stats_endpoints("/pad/naar/capture.pcapng", type="udp")
# Controlleer dat Rx Packets > 0 voor relay (10.10.1.30:1001) en/of dimmer/input
```

**tshark (alleen als MCP niet beschikbaar — let op filter):**
```bash
# Gebruik ip.addr (NIET ip.src) om beide richtingen te vangen:
tshark -r captures/<SESSION>/capture.pcapng -Y "udp.port==1001 && ip.addr==10.10.1.30" | wc -l
```

Is de Rx count **> 0**, dan zit bidirectionele relay-traffic **in de pcap** en kan de gate **PASS** worden (mits ook de hub-kant zichtbaar is). Is het **0**, dan is de opname **op zich** geen bewijs voor relay→hub — ongeacht mirror-label in documentatie.

## Operator-notitie

Spiegel **15 → 7** (IPBox-been) is de operator-canon voor bidirectionele hub-zichtbaarheid; repo-playbooks en capture-workflow gebruiken dit nu als **standaard**. **`7←14`** blijft een **bewust alternatief** voor relay-switchpoort-POV — leg in manifest + notities altijd vast wat je echt in UniFi hebt gezet.

---

## Geïmplementeerde tooling (debugplan en7)

### Fase 1 — tabellen zonder handwerk

[`scripts/udp1001_bidir_counts.py`](../scripts/udp1001_bidir_counts.py) telt op de **ruwe** pcap hub↔relay en dimmer↔home/hub (standaard-IPs via flags). Voorbeelden:

```bash
python3 scripts/udp1001_bidir_counts.py captures/<SESSION>/capture.pcapng
python3 scripts/udp1001_bidir_counts.py --session captures/<SESSION> --rest-ip 192.168.1.42
```

### Fase 2 — BPF rooktest (operator)

[`scripts/en7_bpf_smoke_capture.sh`](../scripts/en7_bpf_smoke_capture.sh): korte `dumpcap` op `en7` met **alleen** `udp port 1001` (geen hostfilter). Daarna opnieuw `udp1001_bidir_counts.py` op het bestand.

### Fase 4 — correlate gate (CI-lokaal)

Minimale synthetische sessie (2 UDP/1001 frames hub↔relay) staat onder `tests/fixtures/minimal_udp1001_session/`. Regenereren:

```bash
python3 scripts/generate_minimal_correlate_session.py
python3 scripts/correlate_capture_session.py tests/fixtures/minimal_udp1001_session --verdict-profile relay
```

Verwachte stdout-regel: `STATUS_VERDICT_GATE: PASS` (bewijs dat de gate bidirectioneel UDP ziet wanneer de pcap beide richtingen bevat).

---

## Live UniFi-check (voorbeeld 2026-05-15)

`unifi_get_switch_ports` op **Unify Switch 16** (`device_mac` `b4:fb:e4:54:83:7c`) toonde o.a.:

- **Poort 7** (`en7` capture-Mac): `op_mode: mirror`, **`mirror_port_idx: 15`** — effectieve SPAN-bron is het been op **poort 15** (IPBox `10.10.1.1`-segment), niet poort 14.
- Poorten **8, 12, 13, 14, 15** staan in normale switch-modus behalve de mirror-override op 7.

Gebruik dit soort export **op capture-start** in je manifest (UTC + mirrorbron + REST-doel-IP) om documentatie en werkelijkheid gelijk te trekken.

---

## POV-matrix (zelfde stimulus; tel beide richtingen na elke pcap)

| Mirror (dest ← src) | Verwacht zicht (kort) | Typische bidirectionele UDP/1001? |
|---------------------|------------------------|-----------------------------------|
| **7 ← 15** | Verkeer op IPBox **VLAN-been** (`10.10.1.1`) | Beste kandidaat als replies over hetzelfde fysieke been lopen. |
| **7 ← 14** | Relay-poort (`10.10.1.30`) | Vaak rijk aan hub→relay; relay→hub kan **ontbreken** in de pcap (pad/SPAN). |
| **7 ← 12** | Dimmer-poort (`10.10.1.40`) | Vaak zichtbaar naar thuis-IPBox-been; terug-UDP vaak afwezig op deze POV. |
| **7 ← 8** | Oud/thuis-been IPBox (indien daar gespiegeld) | Alleen met voorzichtigheid (connectivity-risico); zie CAPTURE_LIVE_STATUS. |

Stappen na elke wijziging: `udp1001_bidir_counts.py` → `correlate_capture_session.py` → noteer **PASS/WARN** naast run-doel (command vs status-claim).

---

## Fase 5 — als alle US16-mirrors een richting missen

- **Cloud Gateway Ultra** (`tcpdump` op `eth2` / `br0`): nuttig wanneer de IPBox **zelf** partij is op dat segment; **niet** voor louter switch-lokaal verkeer tussen controllers zonder hub-pad over CGW (`resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md`, sectie CGW).
- **Uplink / tweede SPAN-POV**: overwegen als metingen aantonen dat **replies een ander fysiek pad** nemen dan requests — dan is “half” op `en7` verwacht gedrag, geen defect van de Mac-interface.
