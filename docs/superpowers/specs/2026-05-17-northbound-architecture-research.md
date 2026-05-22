# Northbound architecture research — eigen centrale (geen IPBox-REST)

> **Superseded:** canoniek architectuurplan staat in **[2026-05-18-gateway-architecture-design.md](2026-05-18-gateway-architecture-design.md)**. Dit bestand blijft als achtergrond/notities uit de eerste ronde.

Last updated: 2026-05-17

## Context

**Doel:** de propriëtaire IPBox vervangen door een **eigen open centrale** die de veldbus (UDP/1001) beheert.

**Niet het doel:** de IPBox REST API op poort `:30200` nabootsen. De bestaande HA-integratie ([HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding)) is referentie voor *gedrag*, geen verplicht northbound-contract.

**Status northbound:** **besloten** — Aanpak C (HA add-on + companion); zie [2026-05-18-gateway-architecture-design.md](2026-05-18-gateway-architecture-design.md).

## Twee lagen (gescheiden houden)

| Laag | Status | Repo |
|------|--------|------|
| **Field bus** — UDP/1001, payload encode/decode | Fase 1 RE **voltooid** (2026-05-22) | `gateway/payloads/`, `RE_STATE.md` |
| **Northbound** — hoe clients (HA, andere) de centrale aanspreken | **Besloten** (2026-05-18 doc) | Dit document = achtergrond |

De experimentele `gateway/rest_api.py` is **alleen** nuttig voor RE-correlatie (REST-stimulus tijdens captures), niet als eindproduct.

## Opties om te vergelijken

### A — MQTT (broker-centrisch)

**Voorbeeld:** Home Assistant via MQTT discovery (`homeassistant`/`discovery`), topics per device.

| Criterium | Inschatting |
|-----------|-------------|
| HA-integratie | Zeer volwassen; veel voorbeelden |
| Discovery | Via MQTT discovery JSON — zelf te modelleren |
| Input events (knoppen) | Pub/sub past goed bij events |
| Latency | Meestal voldoende voor licht/relay |
| Provisioning | Apart config-model (YAML/DB), niet in MQTT zelf |
| Matter-bridge | Niet native; aparte bridge nodig |

### B — Matter (standaard smart-home)

**Voorbeeld:** centrale als Matter bridge/controller; HA Matter-integratie.

| Criterium | Inschatting |
|-----------|-------------|
| HA-integratie | Matter-integratie in HA; vendor-ecosysteem |
| Discovery | Commissioning-flow; complexer dan MQTT |
| Input events | Mogelijk via Matter switches/sensors — mapping nodig |
| Latency | Doorgaans goed |
| Provisioning | Commissioning + fabric; zwaarder voor custom veldbus |
| Vendor lock-in | Standaard, maar certificatie/complexiteit |

### C — Direct HA custom integration (Python)

**Voorbeeld:** nieuwe `custom_components/ipbuilding_open` die UDP/1001 zelf doet of via lokale API.

| Criterium | Inschatting |
|-----------|-------------|
| HA-integratie | Volledige controle; meer onderhoud |
| Discovery | Zelf via `config_flow` |
| Andere clients | Alleen HA tenzij je ook MQTT/Matter toevoegt |

### D — Hybride (aanbevolen te onderzoeken)

Interne service met:

- **UDP/1001 core** (vast)
- **MQTT** voor HA + automatisering
- Optioneel **Matter** later voor bredere interoperabiliteit

## Vragen voor architect-sessie

1. Moet de centrale **alleen** HA bedienen, of ook andere systemen (Apple Home, Google, …)?
2. Is **commissioning** (Matter) acceptabel vs. **YAML/config file** (MQTT-achtig)?
3. Waar leeft **configuratie** (knoppen → relay/dimmer mapping): in centrale, in HA, of beide?
4. **Failover:** IP1100 autonomie-EEPROM bij uitval centrale — moet northbound dat kunnen “overschrijven” na herstel?
5. **Hardware target:** Raspberry Pi, NUC, Docker op HA host, dedicated VLAN NIC?

## Wat Fase 1 RE al oplevert (northbound-agnostisch)

- Relay ON/OFF/pulse + status replies
- Dimmer DIM/OFF + `I0154xxx` status
- Input poll + idle reply (events: Sprint 5)
- Geen scene-protocol, geen volledige provisioning-API

Zie [2026-05-17_ipbuilding_fieldbus_capability_matrix.md](../../resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md) (veldbus-capabilities, geen IPBox-parity).

## Beslissing (2026-05-18)

| Beslissing | Keuze | Datum | Notities |
|------------|-------|-------|----------|
| Northbound primair | WebSocket (JSON) | 2026-05-18 | Aanpak C — add-on exposeert WS-endpoint |
| Northbound secundair | REST `/api/v1/` + tijdelijke IPBox-shim `:30200` | 2026-05-18 | Shim alleen voor transitieperiode |
| Config model | YAML in add-on config (controller IPs, poorten) | 2026-05-18 | HA Supervisor beheert lifecycle |
| HA-integratiepad | Companion custom component (`ipbuilding-open`) via HACS | 2026-05-18 | Vervangt `HA-IPBuilding` volledig; auto-discovery via Supervisor |
| Apple/Google Home | Via HA ingebouwde Matter bridge | 2026-05-18 | Geen eigen Matter implementatie nodig |

**Volledige architectuurspec:** `docs/superpowers/specs/2026-05-18-gateway-architecture-design.md`
