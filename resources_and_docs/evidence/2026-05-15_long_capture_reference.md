# Reference capture: `long_capture.pcapng` (bidirectionele veldbus)

## Locatie in repo

- **Bestand:** [pcap_archive/long_capture.pcapng](pcap_archive/long_capture.pcapng)  
- **Bron:** operator-export (oorspronkelijk onder `Downloads/long_capture.pcapng`), in repo gezet voor reproduceerbare analyse.  
- **Git:** expliciet toegestaan via `.gitignore`-uitzondering (`!resources_and_docs/pcap_archive/long_capture.pcapng`).

## Capture-context (operator)

- **Interface:** `en7` (USB Ethernet op Mac, zie pcap-interface metadata).  
- **Mirror (operator):** UniFi **bron 15 → bestemming 7** (IPBox `10.10.1.1`-been naar capture-NIC). Niet af te leiden uit het pcap-bestand zelf; vastgelegd voor interpretatie.  
- **REST in deze file:** geen IPBuilding-orchestrator-`manifest.jsonl` bij dit bestand — dit is een **standalone** `dumpcap`/Wireshark-opname, geen `ipbuilding_capture_run.py`-sessiemap.

## Samenvatting (metingen, read-only)

| Metriek | Waarde |
|--------|--------|
| Frames totaal | **4879** |
| Duur | **~264,1 s** |
| UDP poort **1001** | **334** frames |
| Hub ↔ inputs `10.10.1.1` ↔ `10.10.1.50` | **132** elk (bidirectioneel) |
| Hub ↔ relay `10.10.1.1` ↔ `10.10.1.30` | **22** elk (bidirectioneel) |
| Hub ↔ dimmer `10.10.1.1` ↔ `10.10.1.40` | **13** elk (bidirectioneel) |

**Observatie:** in deze opname zit **wél** UDP/1001 van **relay → hub** (`ip.src==10.10.1.30`). Dat contrasteert met de korte georkestreerde sessies onder `captures/` waar die richting **0** frames telde — zie [2026-05-15_capture_bidirectional_explainer.md](2026-05-15_capture_bidirectional_explainer.md) (oorzaak: wat op `en7` arriveerde, niet BPF/correlate).

### Payload-hoogtepunten (uit eerdere analyse)

- **Relay:** hub stuurt o.a. `P0000`, `C0000`/`S0000`, `C1000`/`S1000`, `C1600`/`S1600`; relay antwoordt met langere **`I…` / `P…`-achtige** ASCII-hex reeksen.  
- **Dimmer:** periodiek hub `I9900`-achtig patroon (`4939393030`), dimmer o.a. `I0154999` (`4930313534393939`).  
- **Inputs (.50):** veel `I0000` plus **binary** statusframes (niet volledig ASCII).

## Handige commando’s

```bash
# Pakketten en duur
capinfos -c -I resources_and_docs/pcap_archive/long_capture.pcapng

# UDP/1001 per src→dst
tshark -r resources_and_docs/pcap_archive/long_capture.pcapng -Y "udp.port==1001" \
  -T fields -e ip.src -e ip.dst | sort | uniq -c | sort -rn

# Bewijs relay→hub (telt frames van de relay)
tshark -r resources_and_docs/pcap_archive/long_capture.pcapng \
  -Y "udp.port==1001 && ip.src==10.10.1.30" | wc -l
```

## Correlatie-script

`scripts/correlate_capture_session.py` verwacht een **sessiemap** met `capture.pcapng` **én** `manifest.jsonl`. Voor dit standalone-bestand: kopieer naar een tijdelijke map, voeg een minimale `manifest.jsonl` toe, of gebruik bovenstaande `tshark`-workflow.

## Gerelateerde docs

- [2026-05-15_capture_bidirectional_explainer.md](2026-05-15_capture_bidirectional_explainer.md)  
- [RE_STATE.md](../RE_STATE.md)  
- [CAPTURE_LIVE_STATUS.md](../workflows/CAPTURE_LIVE_STATUS.md)  
