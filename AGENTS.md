# IPBuilding — Project Brief voor Claude Code

## WAT DIT PROJECT IS

We reverse-engineeren het propriëtaire UDP-protocol waarmee de IPBuilding controllers communiceren, om daarna de IPBox (IP0000X) te kunnen vervangen door een open-source oplossing die integreert met Home Assistant en andere domotica systemen.

**Volledige technische kennis:** zie `resources_and_docs/IPBUILDING_KNOWLEDGE.md`.

---

## HUIDIGE STATUS

- [x] Hardware en netwerktopologie gedocumenteerd
- [x] IPBox REST API volledig gedocumenteerd (zie sectie 5 van knowledge doc)
- [x] UDP/1001 polling protocol gedeeltelijk gedecodeeerd (poll + status response)
- [ ] **VOLGENDE STAP: UDP commandopakketten reverse-engineeren**
- [ ] Custom gateway service bouwen

---

## ONMIDDELLIJKE TAAK

Schrijf een Python script (`ipbuilding_probe.py`) dat op de Mac van de gebruiker draait en:

1. REST API commando's stuurt naar de IPBox (10.10.1.1:30200) met precieze timestamps
2. Tegelijk UDP/1001 verkeer captureert via `tcpdump` of `scapy`
3. Commando's en paketten correleert op timestamp
4. Output geeft die toont welke UDP bytes er veranderen bij elk commando

**Doel:** Achterhalen hoe relay aan/uit, dimmer en scene commando's er op UDP niveau uitzien.

### Script vereisten
- Draait met `sudo python3 ipbuilding_probe.py` op macOS
- Gebruikt `aiohttp` voor REST calls, `scapy` of `subprocess+tcpdump` voor capture
- Logt naar stdout EN naar `probe_output.log`
- Pakt systematisch: relay aan → relay uit → dimmer 50% → dimmer 100% → dimmer uit → scene
- Wacht 2s tussen commando's (polling interval van IPBox)

---

## NETWERK (PRODUCTIE)

| Device | IP | Poort | Protocol |
|--------|-----|-------|---------|
| IPBox | 10.10.1.1 | 30200 | REST/HTTP |
| IP200PoE (relays) | 10.10.1.30 | 1001 | UDP binair |
| IP0300PoE (dimmers) | 10.10.0.40 | 1001 | UDP binair |
| IP1100PoE (inputs) | onbekend | 1001 | UDP binair |

---

## BESTAANDE CODE

**HA integratie:** https://github.com/markminnoye/HA-IPBuilding  
Bevat werkende REST API client in `custom_components/ipbuilding/api.py` — herbruikbaar als referentie.

**REST API aanroep voorbeeld:**
```python
# Devices ophalen
GET http://10.10.1.1:30200/api/v1/comp/items

# Relay aan
GET http://10.10.1.1:30200/api/v1/action/action?id=5&actionType=ON&value=1

# Dimmer op 50%
GET http://10.10.1.1:30200/api/v1/action/action?id=12&actionType=DIM&value=50
```

---

## GEWENSTE EINDOPLOSSING

Een Python service (geen IPBox nodig) die:
- Rechtstreeks praat met controllers via UDP/1001
- REST API aanbiedt compatibel met de IPBox (poort 30200) → bestaande HA integratie blijft werken
- Draait als Docker container of HA Add-on

---

## BESTANDEN IN DEZE MAP

| Bestand | Inhoud |
|---------|--------|
| `AGENTS.md` | Project brief en huidige taken (ook voor Cursor) |
| `resources_and_docs/IPBUILDING_KNOWLEDGE.md` | Volledige technische kennis (hardware, protocollen, installatie) |
| `resources_and_docs/IP0000X-IPBox.pdf` | Fabrikantsdocumentatie IPBox |
| `resources_and_docs/IP040x - drukknopinterface1.pdf` | Fabrikantsdocumentatie drukknop interfaces |
| `resources_and_docs/traffic between controller an IPbox.pcapng` | Wireshark capture van UDP polling verkeer |
