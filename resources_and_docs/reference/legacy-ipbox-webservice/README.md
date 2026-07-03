# Legacy IPBuilding centrale — mobile webservice (`actions.php`)

**Bronbestand:** [`actions.php`](actions.php)  
**Provenance:** oorspronkelijk via e-mail (2026-05); **veldbevestigd 2026-07-03** op een oudere **Centrale eenheid** (IP0000, voorganger van IPBox) op `10.10.1.1`. Byte-identiek aan het archief in deze map.

**Analyse:** [`../2026-06-01_legacy_webservice_protocol_analysis.md`](../2026-06-01_legacy_webservice_protocol_analysis.md)  
**Kennisbank:** [`../../IPBUILDING_KNOWLEDGE.md`](../../IPBUILDING_KNOWLEDGE.md) §12.1.1

## Wat dit is

Server-side PHP (Windows, IIS/Apache) — AJAX-backend van de **mobiele webinterface** op:

```
http://10.10.1.1/mobile/
http://10.10.1.1/mobile/core/actions.php?methode=…
```

Architectuur:

```
Browser → actions.php (PHP)
            ├─ MS Access (ipcom.mdb, DMX.mdb, RADIO.mdb) — config & UI-data
            └─ TCP SocketHandler "webservice" → ipcom-service → UDP/1001 modules
```

## Voorbeeld — licht toggle

```
GET /mobile/core/actions.php?methode=protocolToggleItem&ip=10.10.1.32&ch=00
```

PHP stuurt intern `TGL;10.10.1.32-00` naar de `ipcom`-service (TCP), die het vertaalt naar veldbus-commando's.

## Status

**Referentiebron**, geen wire-bewijs. TCP-mnemonics (`TGL`, `CLR`, `DIM`, …) zijn de applicatielaag boven UDP/1001; zie analyse-doc voor RE-vergelijking.
