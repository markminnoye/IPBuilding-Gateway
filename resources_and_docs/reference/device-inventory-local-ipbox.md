# IPBuilding — device-inventaris (lokaal)

**Gegenereerd:** 2026-05-01 22:16 UTC  
**IPBox:** `192.168.0.185:30200` *(snapshot van de meting; thuis-LAN is thans **`192.168.1.0/24`** — gebruik het actuele IPBox-adres op dat segment voor nieuwe calls)*
**Bron:** `GET /api/v1/comp/items` (geen `types`-filter).

**Aantal componenten:** 81

**Kolommen:** `Type` / `Kind` = numerieke codes uit de API; type-namen volgen `resources_and_docs/IPBUILDING_KNOWLEDGE.md`. **HA-scope** = `ja` als `Type` in `1, 2, 3, 60` (zelfde pollset als HA-integratie).

| ID | Type | Type (naam) | Kind | Kind (naam) | HA-scope | Description | Group | Value |
|---:|-----:|-------------|-----:|-------------|:--------:|-------------|-------|-------|
| 1 | 56 | Time module | 0 | — | neen | Ipbuilding Time | Time (groep-ID 2) |  |
| 3 | 54 | KMI | 0 | — | neen | Kmi | KMI (groep-ID 1) | {"Act":0,"Max":0,"Min":0,"Pre":0} |
| 50 | 200 | Regime | 0 | — | neen | Presence | Regime (groep-ID 14) |  |
| 51 | 200 | Regime | 0 | — | neen | Absence | Regime (groep-ID 14) |  |
| 52 | 200 | Regime | 0 | — | neen | Holiday | Regime (groep-ID 14) |  |
| 100 | 102 | Program | 0 | — | neen | Vuurtoren aan als het donker word | Gelijkvloers (groep-ID 6) |  |
| 101 | 102 | Program | 0 | — | neen | Vuurtoren uit als het licht wordt | Sfeer (groep-ID 15) |  |
| 102 | 102 | Program | 0 | — | neen | Patio aan als het donker wordt | Gelijkvloers (groep-ID 6) |  |
| 103 | 102 | Program | 0 | — | neen | Patio uit als het licht wordt | Gelijkvloers (groep-ID 6) |  |
| 104 | 102 | Program | 0 | — | neen | Achterdeur Licht uit als het licht wordt | Gelijkvloers (groep-ID 6) |  |
| 105 | 102 | Program | 0 | — | neen | Achterdeur Licht aan als het donker wordt | Gelijkvloers (groep-ID 6) |  |
| 547 | 1 | Relay | 1 | Light | ja | Keuken LED [30.1.1] | Keuken (groep-ID 4) |  |
| 548 | 1 | Relay | 1 | Light | ja | Patio [30.1.2] | Buitenverlichting (groep-ID 5) |  |
| 549 | 1 | Relay | 1 | Light | ja | Achterdeur Licht [30.1.3] | Buitenverlichting (groep-ID 5) |  |
| 550 | 1 | Relay | 3 | Automation | ja | Straatkant OP | Gelijkvloers (groep-ID 6) |  |
| 551 | 1 | Relay | 3 | Automation | ja | Straatkant NEER | Gelijkvloers (groep-ID 6) |  |
| 552 | 1 | Relay | 1 | Light | ja | Buiten [30.1.6] | Buitenverlichting (groep-ID 5) |  |
| 553 | 1 | Relay | 3 | Automation | ja | Tuinkant OP [30.1.7] | Gelijkvloers (groep-ID 6) |  |
| 554 | 1 | Relay | 3 | Automation | ja | Tuinkant NEER [30.1.8] | Gelijkvloers (groep-ID 6) |  |
| 555 | 1 | Relay | 1 | Light | ja | Vuurtoren [30.2.1] | Gelijkvloers (groep-ID 6) |  |
| 556 | 1 | Relay | 5 | Fan | ja | Badkamer ventilatie [30.2.2] | 1e verdieping (groep-ID 7) |  |
| 557 | 1 | Relay | 1 | Light | ja | Inkom [30.2.3] | Gelijkvloers (groep-ID 6) |  |
| 558 | 1 | Relay | 1 | Light | ja | Slaapkamer achteraan [30.2.4] | 1e verdieping (groep-ID 7) |  |
| 559 | 1 | Relay | 1 | Light | ja | Badkamer [30.2.5] | 1e verdieping (groep-ID 7) |  |
| 560 | 1 | Relay | 1 | Light | ja | Slaapkamer vooraan [30.2.6] | 1e verdieping (groep-ID 7) |  |
| 561 | 1 | Relay | 1 | Light | ja | Traphal [30.2.7] | Hal (groep-ID 8) |  |
| 562 | 1 | Relay | 1 | Light | ja | Traphal ¿rookmelder? [30.2.8] | 1e verdieping (groep-ID 7) |  |
| 563 | 1 | Relay | 1 | Light | ja | Keuken Eettafel [30.3.1] | Keuken (groep-ID 4) |  |
| 564 | 1 | Relay | 1 | Light | ja | Keuken Kookeiland [30.3.2] | Keuken (groep-ID 4) |  |
| 565 | 1 | Relay | 6 | Valve | ja | Keuken rookmelder [30.3.3] | Keuken (groep-ID 4) |  |
| 566 | 1 | Relay | 1 | Light | ja | Speelkamer Boven LED [30.3.4] | 2e verdieping (groep-ID 9) |  |
| 567 | 1 | Relay | 1 | Light | ja | Speelkamer Boven [30.3.5] | 2e verdieping (groep-ID 9) |  |
| 568 | 1 | Relay | 1 | Light | ja | 2e SlpK R [30.3.6] | 2e verdieping (groep-ID 9) |  |
| 569 | 1 | Relay | 1 | Light | ja | 2e SlpK L [30.3.7] | 2e verdieping (groep-ID 9) |  |
| 570 | 1 | Relay | 5 | Fan | ja | Keuken Ventilatie [30.3.8] | Keuken (groep-ID 4) |  |
| 571 | 2 | Dimmer | 1 | Light | ja | Living [40.1.1] | Gelijkvloers (groep-ID 6) |  |
| 572 | 2 | Dimmer | 1 | Light | ja | Bureau [40.1.2] | Gelijkvloers (groep-ID 6) |  |
| 573 | 2 | Dimmer | 1 | Light | ja | Keuken main | Keuken (groep-ID 4) |  |
| 574 | 2 | Dimmer | 0 | — | ja | 40.1.4 | Vrij (groep-ID 10) |  |
| 586 | 50 | Button | 0 | — | neen | Keuken 1 | Keuken (groep-ID 4) |  |
| 587 | 50 | Button | 0 | — | neen | Keuken 2 | Keuken (groep-ID 4) |  |
| 588 | 50 | Button | 0 | — | neen | Keuken 3 | Keuken (groep-ID 4) |  |
| 589 | 50 | Button | 0 | — | neen | Keuken 4 | Keuken (groep-ID 4) |  |
| 590 | 50 | Button | 0 | — | neen | Woonkamer hal L | Woonkamer (groep-ID 11) |  |
| 591 | 50 | Button | 0 | — | neen | Woonkamer Hal M | Living (groep-ID 12) |  |
| 592 | 50 | Button | 0 | — | neen | Woonkamer Hal R | Woonkamer (groep-ID 11) |  |
| 593 | 50 | Button | 0 | — | neen | Woonkamer patio L | Woonkamer (groep-ID 11) |  |
| 594 | 50 | Button | 0 | — | neen | Woonkamer patio M | Living (groep-ID 12) |  |
| 595 | 50 | Button | 0 | — | neen | Woonkamer patio R | Woonkamer (groep-ID 11) |  |
| 596 | 50 | Button | 0 | — | neen | Gordijn OP | Woonkamer (groep-ID 11) |  |
| 597 | 50 | Button | 0 | — | neen | Gordijn NEER | Woonkamer (groep-ID 11) |  |
| 598 | 50 | Button | 0 | — | neen | Inkom L | Hal (groep-ID 8) |  |
| 599 | 50 | Button | 0 | — | neen | Inkom R | Hal (groep-ID 8) |  |
| 600 | 50 | Button | 0 | — | neen | Trap L | Hal (groep-ID 8) |  |
| 601 | 50 | Button | 0 | — | neen | Trap R | Hal (groep-ID 8) |  |
| 602 | 50 | Button | 0 | — | neen | 1e gang | 1e verdieping (groep-ID 7) |  |
| 603 | 50 | Button | 0 | — | neen | Slaapkamer vooraan | 1e Verdieping (groep-ID 13) |  |
| 604 | 50 | Button | 0 | — | neen | Slaapkamer achteraan | 1e Verdieping (groep-ID 13) |  |
| 605 | 50 | Button | 0 | — | neen | Badkamer | 1e verdieping (groep-ID 7) |  |
| 606 | 50 | Button | 0 | — | neen | 2e gang L | 2e verdieping (groep-ID 9) |  |
| 607 | 50 | Button | 0 | — | neen | 2e gang R | 2e verdieping (groep-ID 9) |  |
| 608 | 50 | Button | 0 | — | neen | Speelkamer L | 2e verdieping (groep-ID 9) |  |
| 609 | 50 | Button | 0 | — | neen | Speelkamer R | 2e verdieping (groep-ID 9) |  |
| 610 | 50 | Button | 0 | — | neen | Slaapkamer Kinderen R | 2e verdieping (groep-ID 9) |  |
| 611 | 50 | Button | 0 | — | neen | Slaapkamer kinderen L | 2e verdieping (groep-ID 9) |  |
| 612 | 50 | Button | 0 | — | neen |  Bureau L | Gelijkvloers (groep-ID 6) |  |
| 613 | 50 | Button | 0 | — | neen |  Bureau OP | Gelijkvloers (groep-ID 6) |  |
| 614 | 50 | Button | 0 | — | neen |  Bureau NEER | Gelijkvloers (groep-ID 6) |  |
| 615 | 50 | Button | 0 | — | neen | Toilet rechts | Keuken (groep-ID 4) |  |
| 616 | 50 | Button | 0 | — | neen | Toilet midden | Keuken (groep-ID 4) |  |
| 617 | 50 | Button | 0 | — | neen | Toilet links | Keuken (groep-ID 4) |  |
| 100061 | 100 | Scene / sphere | 1 | Light | neen | Alle Verlichting AAN | Sferen (groep-ID 16) |  |
| 100062 | 100 | Scene / sphere | 1 | Light | neen | Alle Verlichtig UIT | Sferen (groep-ID 16) |  |
| 100063 | 100 | Scene / sphere | 1 | Light | neen | Gaan Slapen | Sferen (groep-ID 16) |  |
| 100064 | 100 | Scene / sphere | 3 | Automation | neen | Keuken UIT | Sferen (groep-ID 16) |  |
| 100065 | 100 | Scene / sphere | 3 | Automation | neen | Gelijkvloers en Keuken UIT | Sferen (groep-ID 16) |  |
| 100066 | 100 | Scene / sphere | 1 | Light | neen | TV sfeer | Sferen (groep-ID 16) |  |
| 100067 | 100 | Scene / sphere | 3 | Automation | neen | Keuken gedimd | Sferen (groep-ID 16) |  |
| 100069 | 100 | Scene / sphere | 3 | Automation | neen | Alle schakelaars AAN  | Sferen (groep-ID 16) |  |
| 100070 | 100 | Scene / sphere | 1 | Light | neen | Alle Schakelaars UIT | Sferen (groep-ID 16) |  |
| 100072 | 100 | Scene / sphere | 5 | Fan | neen | Buitenverlichting TOGGLE | Buitenverlichting (groep-ID 5) |  |

## Aansturing en API-tests

**Volledige matrix** (alle `comp/items`-varianten, `action`-combinaties, delay/polling-patronen, testsequenties):  
→ [`IPBOX_REST_API_TEST_CALLS.md`](IPBOX_REST_API_TEST_CALLS.md)

**Snelle voorbeelden (lokaal, ID’s uit deze tabel):**

- Relay **Keuken LED** (`547`):  
  `http://192.168.0.185:30200/api/v1/action/action?id=547&actionType=ON&value=1` / `…&actionType=OFF&value=0`
- Dimmer **Living** (`571`):  
  `…&actionType=DIM&value=50` / `…&value=100` / `…&actionType=OFF&value=0`

Tussen acties: **~2 s wachten** aan clientzijde (geen REST-“delay”); zie testdocument.

## Types in deze response

1 = Relay, 2 = Dimmer, 50 = Button, 54 = KMI, 56 = Time module, 100 = Scene / sphere, 102 = Program, 200 = Regime
