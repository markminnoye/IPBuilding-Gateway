# UDP/10001 Discovery Spike — Evidence

**Datum:** 2026-06-02  
**Doel:** valideren of veldmodules antwoorden op UDP/10001 probe `01 00 00 00` en GO-A/GO-B bepalen voor `gateway/discovery.py`.  
**Tool:** `scripts/udp10001_listen.py`

---

## Context

- RE-hypothese: IPBox/hub stuurt periodiek probes op UDP/10001 naar `233.89.188.1` en `255.255.255.255`.
- Te valideren: module→hub replies zichtbaar vanaf huidige POV.

---

## Testomgeving

| Parameter | Waarde |
|-----------|--------|
| Interface | `en7` (IPBuilding VLAN) |
| Host-IP | `10.10.1.1/24` (`ifconfig en7`) |
| Route-check | `255.255.255.255` + `233.89.188.1` via `en7` |
| Socket-bind | `lsof -iUDP:10001` toont listener op UDP/10001 |
| Captures | `/Users/markminnoye/Downloads/10-51.pcapng`, `/Users/markminnoye/Downloads/10-59.pcapng` |

---

## Fase 1 — Passief (IPBox aan)

Command:

```bash
sudo PYTHONPATH=. python3 scripts/udp10001_listen.py --duration 60
```

Resultaat: **0 replies** van modules op UDP/10001.

---

## Fase 2 — Actieve probe (handmatig)

Command:

```bash
sudo PYTHONPATH=. python3 scripts/udp10001_listen.py --send-probe --duration 60
```

Resultaat: **0 replies** van modules op UDP/10001.

Extra validatie met `tcpdump` bevestigt dat handmatige probes effectief vertrekken vanaf `10.10.1.1:10001` naar:
- `233.89.188.1:10001`
- `255.255.255.255:10001`

---

## Capture-observaties

- In beide captures zijn probe-frames zichtbaar met payload `01000000`.
- Er zijn **geen** zichtbare module→hub UDP/10001 reply-frames.
- **Nuance:** `10.10.1.2` stuurde ook periodieke probes parallel aan de handmatige probe; dit verklaart extra probe-frames maar verandert de conclusie niet.

---

## Verdict

| Scenario | Resultaat |
|----------|-----------|
| Fase 1 (passief) | ✅ 0 replies |
| Fase 2 (actieve probe) | ✅ 0 replies |

- [ ] **GO-A** — UDP probe primair
- [x] **GO-B** — HTTP-sweep primair, UDP best-effort/optioneel

**Conclusie:** voor `gateway/discovery.py` blijft HTTP-sweep de primaire discovery-route. UDP/10001 blijft optioneel/secundair.

---

## Impact op matrix

Geen inhoudelijke wijziging nodig aan `resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md` (status blijft: discovery gedocumenteerd, geen zichtbare replies op huidige POV).
