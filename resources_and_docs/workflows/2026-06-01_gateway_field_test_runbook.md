# Gateway field test runbook (2026-06-01)

**Doel:** valideer dat de open hub (`gateway/main.py`) werkt als vervanger van IPBox op `10.10.1.1` — poll naar alle drie modules, relay/dimmer command, input button events, geen IPBox nodig.

**Referentie:** [README_gateway.md](../../README_gateway.md), [architectuurdoc](../../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md)

---

## Voorwaarden (checklist voor start)

- [ ] Testhost heeft **`10.10.1.1`** op het IPBuilding-VLAN
- [ ] IPBox hub is **uit** of de tweede NIC is niet als `10.10.1.1` actief (geen conflict)
- [ ] Modules bereikbaar: `10.10.1.30` (relay), `10.10.1.40` (dimmer), `10.10.1.50` (input)
- [ ] `devices.json` aanwezig in de werkmap (met jouw installatie-IDs: 547/557/563/570, 571/572)
- [ ] UniFi mirror **7←15** actief voor pcap-debug (optioneel maar aanbevolen)
- [ ] Mirror **uit** voor hub-validatie (PASS 2026-06-02: modules replyen/events naar gateway-IP zonder mirror-POV)
- [ ] Geen `GATEWAY_SIMULATED=1` — echte UDP
- [ ] `PYTHONPATH=.` beschikbaar in de shell

---

## Stap 0 — Baseline pcap (optioneel maar aanbevolen)

Start tcpdump als je UniFi-mirror hebt:

```bash
# macOS requires sudo for raw capture; of course on the field bus host you may not need it
sudo tcpdump -i en7 -w /tmp/gateway_field_test_$(date +%H%M%S).pcapng host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50
```

---

## Stap 1 — Gateway starten

```bash
cd /path/to/IPBuilding\ Gateway
PYTHONPATH=. python -m gateway
```

**Verwachte output (ongeveer):**

```
HH:MM:SS INFO  gateway  IPBuilding Gateway started  rest=0.0.0.0:30200  poll=2.0s  simulated=False  install=relay@10.10.1.30, dimmer@10.10.1.40, input@10.10.1.50
```

(De `install=…` regel verschijnt alleen als `devices.json` is geladen; als die ontbreekt zie je alleen de basis-log.)

---

## Stap 2 — Poll controleren

Na ~2 seconden verschijnen polls in de log (of in pcap):

| Bestemming | Payload | Verwacht |
|-----------|---------|---------|
| `10.10.1.30` (relay) | `P0000` | Elke ~2s herhaald |
| `10.10.1.40` (dimmer) | `I9900` | Elke ~2s herhaald |
| `10.10.1.50` (input) | `I0000` | Elke ~2s herhaald |

**Pass/Fail:** als je geen polls ziet naar alle drie modules → STOP, eerst netwerk controleren.

Als je pcap actief hebt: filter `udp port 1001` en bevestig dat hub `10.10.1.1` de drie payloads verstuurt.

---

## Stap 3 — Relay ON/OFF via REST-shim

In een **tweede terminal** (of curl):

```bash
# Relay kanaal 0 aan (id 547)
curl "http://localhost:30200/api/v1/action/action?id=547&actionType=ON&value=1"

# verwacht: {"ok": true, "id": 547, ...}

# Relay kanaal 0 uit
curl "http://localhost:30200/api/v1/action/action?id=547&actionType=OFF&value=0"

# verwacht: {"ok": true, "id": 547, ...}
```

**Verwachte log in gateway-terminal:**

```
STATE  10.10.1.30 ch0: unknown → on
STATE  10.10.1.30 ch0: on → off
```

**Pass/Fail:** fysieke relay schakelt + state in log klopt.

---

## Stap 4 — Dimmer DIM via REST-shim

```bash
# Dimmer kanaal 0 aan 50% (id 571)
curl "http://localhost:30200/api/v1/action/action?id=571&actionType=DIM&value=50"

# Dimmer uit (value=0)
curl "http://localhost:30200/api/v1/action/action?id=571&actionType=DIM&value=0"
```

**Verwachte log:**

```
Dimmer 10.10.1.40 ch-1: None -> 50%
Dimmer 10.10.1.40 ch-1: 50% -> 0%
```

(Channel toont `ch-1` totdat dimmer channel-awareness is verbeterd — dat is bekend, geen probleem.)

---

## Stap 5 — Input button event

Druk op een bekende knop op `10.10.1.50`.

**Verwachte log:**

```
EVENT  10.10.1.50 button <id_hex>: press
EVENT  10.10.1.50 button <id_hex>: release
```

`<id_hex>` is de hex-ID van de knop (bijv. `0A` of `B`... zie RE Sprint 5 docs in `evidence/`).

---

## Stap 6 — Stabiliteit (5 minuten)

Laat de gateway 5 minuten draaien zonder interactie.

**Pass:** geen crash, polls blijven lopen, log gaat door.

---

## Stap 7 — Comp items endpoint

```bash
curl "http://localhost:30200/api/v1/comp/items" | python3 -m json.tool
```

**Verwachte output:** JSON-array met relay en dimmer items, hun huidige state.

---

## Pass/Fail samenvatting

| Check | Pass-criterium |
|-------|----------------|
| Poll zichtbaar | Ja, naar `10.10.1.30`, `.40`, `.50` |
| Relay ON/OFF | Fysiek + state in log klopt |
| Dimmer DIM 50%/0% | Fysiek + dimmer state in log klopt |
| Input button event | Minstens één `B-…E` press/release in log |
| Stabiliteit 5 min | Geen crash, polls lopen door |
| Geen IPBox nodig | Gateway alleen als hub |
| REST `/api/v1/comp/items` | Geeft relay/dimmer items met state terug |

---

## Na de test

**Bewijs verzamelen (optioneel):**

```bash
# Stop tcpdump als je hebt opgenomen
# Noteer Session ID / timestamp / mirror-POV in evidence
echo "Gateway veldtest 2026-06-01 — PASS/FAIL" > resources_and_docs/evidence/2026-06-01_gateway_field_test.md
```

Sla een kort bestand op in `resources_and_docs/evidence/` met datum, mirror-POV, pass/fail per check, en link naar pcap als je die hebt.

---

## Troubleshooting

| Symptoom | Kijk |
|----------|------|
| Geen polls naar modules | Host heeft `10.10.1.1`? Modules bereikbaar vanuit deze host? |
| Relay ON geeft 404 | Check of `devices.json` correct geladen is (log toont `install=relay@10.10.1.30, …`) |
| Geen input events | Knop heeft `B-…E` prefix nodig; check [Sprint 5 docs](../evidence/2026-05-22_sprint5_input_physical_completion.md) |
| Gateway crasht | Check Python imports: `PYTHONPATH=.` nodig? Heeft pytest-asyncio invloed? |