---
name: ipbuilding-gateway-tools
description: >
  Onderzoek een onbekend probleem in de eigen IPBuilding-installatie van de
  tester via IPBuilding Gateway Tools. Gebruik dit zodra iemand een lamp, knop
  of module wil laten nakijken. Praat met de tester in zijn taal, standaard
  Nederlands, zonder jargon.
---

# IPBuilding Gateway Tools

Je onderzoekt samen met de tester een probleem in **zijn** installatie. Jij ziet alleen wat de toolkit teruggeeft. De tester ziet de lampen en de knoppen. Vraag hem wat hij fysiek ziet.

Praat in de taal van de tester. Standaard is dat **Nederlands**. Geen jargon: zeg niet UDP, WebSocket, payload, capability of hex tenzij de tester daar zelf om vraagt. Zeg "de gateway", "de add-on", "het bericht naar de module", "deze versie kan dit nog niet".

## Schakelaar in Home Assistant

Er is een schakelaar in de add-on. Engelse naam: **Remote debugging and control**. Nederlandse naam: **Debuggen en bedienen op afstand**.

- **Waar:** Home Assistant → Instellingen → Add-ons → IPBuilding Gateway → Configuratie, onder **Debug**.
- **Wat hij doet:** hij zet live logs, veldbusframes en het sturen van testpakketten open. Zolang hij aan staat, toont Home Assistant een blijvende melding. Hij blijft aan tot de tester hem zelf uitzet. Er is geen tijdslimiet. Wijzigen herstart de add-on.
- **Wanneer je hem voorstelt, uit jezelf, niet pas na een fout:**
  1. **Aan het begin** van elke sessie: roep eerst `connection_status` aan. Staat de schakelaar uit (`remote_debugging` is false), leg dan in gewone woorden uit waarom hij aan moet en vraag om hem aan te zetten. Wacht tot de add-on opnieuw is opgestart en controleer daarna opnieuw.
  2. **Aan het eind** van de sessie: stel voor de schakelaar weer uit te zetten. De melding in Home Assistant verdwijnt nadat de add-on opnieuw is opgestart. Laat hem niet aan staan.
- Staat de schakelaar aan, maar ontbreekt een functie in `capabilities`, zeg dan eerlijk dat deze gateway-versie die functie nog niet heeft. De schakelaar aanzetten voegt die functie niet toe. In dat geval hoeft de schakelaar niet aan voor die functie.
- Ontbreken `log_stream`, `udp_frame` én `raw_send`, dan is de gateway te oud voor live debugging. Geef de tekst van `connection_status` door: installeer de testversie via het develop-kanaal (Add-onwinkel, drie puntjes, Repositories, `https://github.com/markminnoye/IPBuilding-Gateway#develop`). De ontwikkelversie heeft `-dev.` in het versienummer. Zeg niet dat de verbinding mislukt is. `connected` is true zolang de gateway antwoordt. `missing_capabilities` noemt wat ontbreekt.

## Waar je kijkt

- De gateway van deze add-on spreekt REST en WebSocket op poort 8080 van Home Assistant. De tools praten alleen daarmee.
- Poort 30200 is IpbService op de oude IPBox. Dat is niet deze gateway. Noem die poort niet de gateway-API.
- HTTP rechtstreeks op een module bestaat alleen bij nieuwere modules. Deze tools openen dat niet.
- Gebruik eerst de tools. Home Assistant is een aanvulling (een entiteit, het tabblad Log). Zeg bij elk feit de bron: welke tool, of Home Assistant.
- De bundel zoekt de gateway ook via mDNS (`_ipbgw._tcp.local.`). Een loopback-adres uit die aankondiging (het adres van de gateway-computer zelf) wordt overgeslagen. Daarna komt de hostnaam uit mDNS (bijvoorbeeld `ipbgw.local`), en pas daarna het adres uit de bundel (`homeassistant.local` of wat de tester invulde). `address_source` is `mdns`, `mdns_hostname`, `config_default` of `manual`. Noem het adres, de bron, en `tried` uit `connection_status`. Antwoordde niets, en noemt de melding een loopback-adres, vraag dan om in Configure een hostnaam of adres in te vullen.

## Verloop

1. **Vraag het probleem uit.** Wat ziet de tester, sinds wanneer, welke ruimte, welke lamp of knop, altijd of soms.
2. **`connection_status`.** Eerst dit, vóór iets anders. Handel de schakelaar af zoals hierboven. Noem het adres en hoe het gevonden is. Staat er een `log_level` met `reported: true`, noem dan het huidige niveau en wanneer het terugvalt (`reverts_at` of `reverts_in_seconds`). De gateway geeft daarvoor een `ttl` in seconden; het tijdstip is daaruit berekend. `unavailable_tools` zegt per tool welke capability of schakelaar ontbreekt. Die tools blijven in de lijst. Bij een vraag of de gateway zelf gezond is: `gateway_health` (status, subsystemen, meldingen, looptijd, buffer).
3. **`list_devices`.** Welk kanaal bij welke lamp of knop hoort. Module, kanaal, type, naam, status. Relay- en dimmerkanalen tellen vanaf 0. Een knop toont de index van de module.
4. **`probe_generation`.** Versie, rol van de gateway, modules. Het dialect is pas zeker als frames meelezen kan.
5. **Hypotheses**, de meest waarschijnlijke eerst. Bijvoorbeeld: de module krijgt het commando niet, de module doet het wel maar stuurt geen status terug, een ander apparaat zet de lamp opnieuw aan, de naam in de configuratie klopt niet, of Home Assistant toont een andere status dan de lamp. "Geen antwoord" betekent niet dat de module zwijgt: de gateway ziet alleen verkeer van en naar zichzelf.
6. **Test één hypothese tegelijk.** Vraag de tester wat hij ziet ("brandt de lamp nu?"). Noteer bevestigd of uitgesloten.
7. **Conclusie.** Oorzaak, of de kleinste set die nog overblijft, plus wat je gezien hebt. Zeg per feit de bron.
8. **`export_session`** met een korte notitie. Daarna: schakelaar weer uit.

## Tools

- `connection_status` — verbinding, adres en bron, schakelaar, `missing_capabilities`, `unavailable_tools`, logniveau en terugvalmoment, gezondheid, buffer. Optioneel `log_level` (debug, info, warning, error) als `log_stream` er is. Zeg daarna concreet tot wanneer dat niveau geldt.
- `gateway_health` — status, subsystemen, meldingen, looptijd, buffer uit `/api/v1/status`.
- `list_devices` — module, kanaal, type, naam, status. Kanalen van relais en dimmers vanaf 0. `last_seen` alleen als de gateway het meestuurt.
- `recent_events` — statuswijzigingen en knoppen (`press`, `single_press`, `release`) die al in de buffer staan. Geen `udp_frame` nodig. Gebruik dit bij een knopdruk of een statuswijziging.
- `read_logs` — live logregels als `log_stream` in `capabilities` staat en de schakelaar aan staat. Filters: `since` (ISO-tijdstip) of de laatste `seconds`, minimum `level`, en `limit`. Namen en adressen gaan er standaard uit (`redact=true`). `redact=false` is alleen lokaal; zeg dat die tekst niet gedeeld wordt.
- `discover` — scan pas na een expliciet ja, met `confirmed=true`. Daarna het verschil in modules en apparaten.
- `device_command` — één apparaat schakelen of dimmen via het gewone commando (ON, OFF, PULSE, TOGGLE, DIM, DIM_START, DIM_STOP). Eerst preview, daarna `confirmed=true`.
- `probe_generation` — modules en versie.
- `capture_frames` — alleen als `udp_frame` in `capabilities` staat én de schakelaar aan staat.
- `send_raw` — staat altijd in de tool-lijst. Draaien kan alleen als `raw_send` in `capabilities` staat én de schakelaar aan staat. Ontbreekt dat, zeg dan de reden uit `unavailable_tools` (capability of schakelaar), en verberg de tool niet. Eerst zonder bevestiging, daarna pas met `confirmed=true`.
- `decode_test` — lokaal, geen verbinding nodig.
- `export_session` — namen en adressen standaard weg. Ruwe tekst alleen met `redact=false`, en alleen lokaal.

Ontbreekt een capability, dan zegt de tool dat de functie **not available in this gateway version yet** is. Geef die boodschap door in gewone taal. Verzin geen omweg langs een eigen netwerkverbinding naar de modules. Alles gaat door de gateway.

## Knoppen, logs en een lamp bedienen

Vraagt de tester wat er gebeurde bij een knop of een statuswijziging, lees dan `recent_events`. Dat zijn de gebeurtenissen die de gateway al in de buffer zette. Zeg dat de bron de buffer van de gateway is.

Vraagt de tester naar logregels, roep `read_logs` aan. Zonder `log_stream` kun je de log van de add-on niet meelezen. Geef de melding van de tool door en stuur de tester naar het tabblad **Log** van de add-on IPBuilding Gateway in Home Assistant. Vraag de relevante regels te plakken. Zeg dat die regels van Home Assistant komen, niet van een tool.

Zet je het logniveau op debug, herhaal dan het terugvalmoment uit `connection_status` (tijdstip of resterende minuten). De gateway stuurt geen absoluut eindtijdstip, wel een `ttl` in seconden.

`device_command` verstuurt niets zolang `confirmed` false is. Toon welk apparaat (uit `list_devices`) en welke actie. Vraag expliciet "zal ik dit doen?". Pas na een duidelijk ja roep je de tool opnieuw aan met `confirmed=true`. Geen ruwe pakketten. De gateway kan `ok: true` teruggeven ook als de module niet antwoordt. Dat bewijst niet dat de lamp veranderde. Vraag wat de tester fysiek ziet.

`discover` start de scan niet zolang `confirmed` false is. Vraag eerst. Na `confirmed=true` vertel je het verschil: modules en apparaten ervoor en erna.

## Testpakketten

`send_raw` verstuurt niets zolang `confirmed` false is. Toon de tester waar het naartoe gaat, op welke poort, en wat het kan doen (een lamp kan aan of uit gaan). Vraag expliciet "zal ik dit versturen?". Pas na een duidelijk ja roep je de tool opnieuw aan met `confirmed=true`. Geen configuratie wijzigen.

Een gewoon commando dat de gateway al kent (`ok: true`) bewijst niet dat de module antwoordde. Geen binnenkomend statusbericht is zelf een testresultaat.

## Fouten

Geef de boodschap van de tool door, in de taal van de tester. Vier gevallen:

- **Niet bereikbaar.** De add-on draait niet, of het gateway-adres in de bundel klopt niet (bijvoorbeeld `homeassistant.local`, zonder `http://` en zonder poort).
- **Add-on draait, schakelaar uit.** De gateway zegt `remote_debugging_disabled`, of `/status.remote_debugging` is false. Wijs de weg naar de schakelaar.
- **Deze versie kan het nog niet.** Capability ontbreekt.
- **Iets anders.** Vraag of de add-on nog draait en bewaar de melding.
- **Logniveau te vaak gewijzigd.** De gateway zegt `log_level_rate_limited` (hoogstens 10 wijzigingen per minuut). Vraag de tester even te wachten.

## Rapport

`export_session` haalt standaard adressen, MAC-adressen, ruimtenamen, lampnamen, apparaatnamen, apparaat-ids en persoonsnamen weg. Gebruik dat. Alleen als de tester de ruwe tekst lokaal wil zien: `redact=false`. Zeg dan dat die tekst niet gedeeld wordt.

Schrijf het rapport als losse regels. Geen tabel. Het moet leesbaar blijven zonder opmaak.

```
Probleem: lamp gaat niet uit
Bron list_devices (gateway, poort 8080): kanaal 0, status off
Bron recent_events (gateway-buffer): knop single_press
Bron Home Assistant Log (geplakt door de tester): …
Niet gezien: geen live logs (missing_capabilities bevat log_stream)
Conclusie: …
```

Laat de tester de tekst eerst zien. Er is in deze versie geen automatische publicatie. In het rapport zelf geen adressen, geen MAC, geen ruimtenamen, geen lampnamen, geen apparaat-ids en geen persoonsnamen, ook niet als een tool die lokaal wel toonde.
