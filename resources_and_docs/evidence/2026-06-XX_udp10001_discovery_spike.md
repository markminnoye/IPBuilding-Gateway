# UDP/10001 Discovery Spike — Evidence

**Datum:** 2026-06-XX  
**Doel:** bevestigen of veldmodules antwoorden op UDP/10001 probe `01 00 00 00`  
**Tool:** `scripts/udp10001_listen.py`  
**RE-context:** zie [2026-05-17_scan_modules_udp_payloads.md](../reference/2026-05-17_scan_modules_udp_payloads.md) — IPBox stuurt probe ~elke 10,5 s; geen module-replies op mirror 7←15 waargenomen.

---

## Testomgeving

| Parameter | Waarde |
|-----------|--------|
| Interface | `en7` (IPBuilding VLAN) |
| Mirror | 7←15 aan / uit |
| IPBox actief | ja / nee |
| Gateway als `10.10.1.1` | ja / nee |

---

## Fase 1 — Passieve capture (IPBox draait)

```
# Voer uit:
sudo python scripts/udp10001_listen.py --duration 60
```

**Output:**

*(plak hier de volledige output van het script)*

---

## Fase 2 — Actieve probe (IPBox uit, gateway op 10.10.1.1)

```
# Voer uit:
sudo python scripts/udp10001_listen.py --send-probe --duration 60
```

**Output:**

*(plak hier de volledige output van het script)*

---

## Payload-analyse (bij ontvangen antwoorden)

| Byte offset | Waarde (hex) | Hypothese |
|-------------|--------------|-----------|
| 0 | `0x??` | Reply type (vs probe `0x01`) |
| 1–6 | `??:??:??:??:??:??` | Module MAC? |
| 7 | `0x??` | Device type code? |

**Correlatie met bekende MACs:**

| IP | MAC | Payload match |
|----|-----|---------------|
| `10.10.1.30` | `00:24:77:52:ac:be` | ? |
| `10.10.1.40` | `00:24:77:52:9e:a8` | ? |
| `10.10.1.50` | `00:24:77:52:ad:aa` | ? |

---

## Verdict

| Scenario | Resultaat |
|----------|-----------|
| Fase 1 (passief, IPBox) | ☐ Replies gezien / ☐ Geen replies |
| Fase 2 (actief, gateway) | ☐ Replies gezien / ☐ Geen replies |

**Go/no-go voor Task 3 (`gateway/discovery.py`):**

- [ ] **GO-A** — Replies bevestigd: UDP/10001 probe primair in gateway CLI
- [ ] **GO-B** — Geen replies: HTTP-sweep primair; UDP als optionele extra stap

---

## Impact op fieldbus matrix

Regel `Module discovery (UDP/10001)` in [`2026-05-17_ipbuilding_fieldbus_capability_matrix.md`](../2026-05-17_ipbuilding_fieldbus_capability_matrix.md):

Huidige status: *"Documented, no mirror replies"*  
Bijwerken alleen als verdict afwijkt van GO-B.
