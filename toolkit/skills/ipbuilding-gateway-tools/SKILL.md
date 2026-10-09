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

Er is een schakelaar in de add-on. Engelse naam: **Remote control (for debugging)**. Nederlandse naam: **Bediening op afstand (voor debuggen)**.

- **Waar:** Home Assistant → Instellingen → Add-ons → IPBuilding Gateway → Configuratie, onder **Debug**.
- **Wat hij doet:** hij zet live logs, veldbusframes en het sturen van testpakketten open. Knoppen en statuswijzigingen komen ook binnen als de schakelaar uit staat. Alleen de logregels vallen dan weg. Zolang hij aan staat, toont Home Assistant een blijvende melding: "Bediening op afstand staat aan. IPBuilding Gateway Tools kan live verkeer lezen en commando's naar je modules sturen. Zet het uit in de instellingen van de add-on als het debuggen klaar is." Hij blijft aan tot de tester hem zelf uitzet. Er is geen tijdslimiet. Wijzigen herstart de add-on. Iedereen op het netwerk kan dan meelezen en testpakketten sturen.
- **Wanneer je hem voorstelt, uit jezelf, niet pas na een fout:**
  1. **Aan het begin** van elke sessie: roep eerst `connection_status` aan. Voor een knop of een lampstatus hoef je de schakelaar niet aan te zetten: `recent_events` werkt dan ook. Vraag hem aan te zetten als je live logs, veldbusframes of een testpakket nodig hebt (`switch_active` is false, of `remote_debugging` is false). Wacht tot de add-on opnieuw is opgestart en controleer daarna opnieuw.
  2. **Aan het eind** van de sessie: stel voor de schakelaar weer uit te zetten. De melding in Home Assistant verdwijnt nadat de add-on opnieuw is opgestart. Laat hem niet aan staan.
- Kijk per functie in `capability_status`, niet alleen in de lijst `capabilities`. `supported` betekent dat deze gateway-versie het kan. `active` betekent dat het nu werkt. Bij `active: false` geef je `reason` door, in gewone taal. Een naam in `capabilities` terwijl de schakelaar uit staat is dus niet beschikbaar.
- Staat de schakelaar aan, maar is `supported` false, zeg dan eerlijk dat deze gateway-versie die functie nog niet heeft. De schakelaar aanzetten voegt die functie niet toe. In dat geval hoeft de schakelaar niet aan voor die functie.
- Ontbreken `log_stream`, `udp_frame` én `raw_send`, dan is de gateway te oud voor live debugging. Geef de tekst van `connection_status` door: installeer de testversie via het develop-kanaal (Add-onwinkel, drie puntjes, Repositories, `https://github.com/markminnoye/IPBuilding-Gateway#develop`). De ontwikkelversie heeft `-dev.` in het versienummer. Zeg niet dat de verbinding mislukt is. `connected` is true zolang de gateway antwoordt. `missing_capabilities` noemt wat ontbreekt.

## Waar je kijkt

- De gateway van deze add-on spreekt REST en WebSocket op poort 8080 van Home Assistant. De tools praten alleen daarmee.
- Poort 30200 is IpbService op de oude IPBox. Dat is niet deze gateway. Noem die poort niet de gateway-API.
- HTTP rechtstreeks op een module bestaat alleen bij nieuwere modules. Deze tools openen dat niet.
- Gebruik eerst de tools. Home Assistant is een aanvulling (een entiteit, het tabblad Log). Zeg bij elk feit de bron: welke tool, of Home Assistant.
- De bundel zoekt de gateway ook via mDNS (`_ipbgw._tcp.local.`). `homeassistant.local` volstaat meestal. Een loopback-adres uit die aankondiging (het adres van de gateway-computer zelf) wordt overgeslagen. Daarna komt de hostnaam uit mDNS (bijvoorbeeld `ipbgw.local`), en pas daarna het adres uit de bundel. Vanaf de nieuwe develop-versie kondigt de gateway zijn adres op het thuisnetwerk aan. `address_source` is `mdns`, `mdns_hostname`, `config_default` of `manual`. Noem het adres, de bron, en `tried` uit `connection_status`. Zegt `connection_status` dat de gateway niet bereikbaar is, vraag dan of de add-on draait en of de schakelaar aan staat, en laat in **Configure** het adres invullen dat de tester in de browser gebruikt om Home Assistant te openen (zonder `http://` en zonder poort). Noemt de melding een loopback-adres, leg dan hetzelfde uit.

## Verloop

1. **Vraag het probleem uit.** Wat ziet de tester, sinds wanneer, welke ruimte, welke lamp of knop, altijd of soms.
2. **`connection_status`.** Eerst dit, vóór iets anders. Handel de schakelaar af zoals hierboven. Noem het adres en hoe het gevonden is. Lees `capability_status`: per functie `supported` en `active`, en bij `active: false` de reden. Staat er een `log_level` met `reported: true`, noem dan het huidige niveau en wanneer het terugvalt (`reverts_at` of `reverts_in_seconds`). De gateway geeft daarvoor een `ttl` in seconden; het tijdstip is daaruit berekend. Zegt de tool dat het actuele logniveau en de terugvaltijd niet gemeld zijn, geef die zin dan exact door. Verzin geen niveau, ook geen INFO, en vraag geen niveauwijziging alleen om het te kunnen lezen. `unavailable_tools` zegt per tool welke capability of schakelaar ontbreekt. Die tools blijven in de lijst. Bij een vraag of de gateway zelf gezond is: `gateway_health` (status, subsystemen, meldingen, looptijd, buffer).
3. **`list_devices`.** Welk kanaal bij welke lamp of knop hoort. Module, kanaal, type, naam, status. Relay- en dimmerkanalen tellen vanaf 0. Een knop toont de index van de module. Een knopnaam die anders is dan de lampnaam is normaal: de knopnaam beschrijft vaak waar de knop zit, niet de lamp. Noem dat verschil niet verdacht en geen fout. Vraag de tester hoe hij knoppen noemt en onthoud dat voor de rest van de sessie.
4. **`probe_generation`.** Versie, rol van de gateway, modules. Het dialect is pas zeker als frames meelezen kan.
5. **Hypotheses**, de meest waarschijnlijke eerst. Bijvoorbeeld: de module krijgt het commando niet, de module doet het wel maar stuurt geen status terug, een ander apparaat zet de lamp opnieuw aan, de naam in de configuratie klopt niet, of Home Assistant toont een andere status dan de lamp. "Geen antwoord" betekent niet dat de module zwijgt: de gateway ziet alleen verkeer van en naar zichzelf.
6. **Test één hypothese tegelijk.** Vraag de tester wat hij ziet ("brandt de lamp nu?"). Noteer bevestigd of uitgesloten.
7. **Conclusie.** Oorzaak, of de kleinste set die nog overblijft, plus wat je gezien hebt. Zeg per feit de bron.
8. **`export_session`** met een korte notitie. Daarna: schakelaar weer uit.

## Tools

- `connection_status` — verbinding, adres en bron, schakelaar, `capability_status` (`supported` tegenover `active`), `missing_capabilities`, `unavailable_tools`, logniveau en terugvalmoment, gezondheid, buffer. Optioneel `log_level` (debug, info, warning, error) als `log_stream` actief is. Zeg daarna concreet tot wanneer dat niveau geldt.
- `gateway_health` — status, subsystemen, meldingen, looptijd, buffer uit `/api/v1/status`.
- `list_devices` — module, kanaal, type, naam, status. Kanalen van relais en dimmers vanaf 0. `last_seen` alleen als de gateway het meestuurt. Per module staat `reachability` (laatste antwoord, gemiddelde, gemiste antwoorden) als de gateway dat object meestuurt. Ontbreekt het object, zeg dan dat bereikbaarheid niet beschikbaar is in deze gatewayversie. Dat is geen capability. `last_seen` is iets anders: wanneer de module via het netwerk gezien is, niet hoe snel ze antwoordde.
- `recent_events` — statuswijzigingen en knoppen (`press`, `single_press`, `release`) die al in de buffer staan. Geen `udp_frame` nodig. Gebruik dit bij een knopdruk of een statuswijziging.
- `read_logs` — live logregels als `log_stream` in `capabilities` staat en de schakelaar aan staat. Filters: `since` (ISO-tijdstip) of de laatste `seconds`, minimum `level`, en `limit`. Namen en adressen gaan er standaard uit (`redact=true`). `redact=false` is alleen lokaal; zeg dat die tekst niet gedeeld wordt.
- `discover` — scan pas na een expliciet ja, met `confirmed=true`. Daarna het verschil in modules en apparaten.
- `device_command` — één apparaat schakelen of dimmen via het gewone commando (ON, OFF, PULSE, TOGGLE, DIM, DIM_START, DIM_STOP). Eerst preview, daarna `confirmed=true`. Na het versturen: `module_confirmed` en `confirm_ms`. `true` betekent dat de module antwoordde, met de tijd in milliseconden. `false` betekent dat ze niet antwoordde. `reported` is de status of het niveau uit dat antwoord, als de gateway het kon lezen. DIM_START wacht niet, dus `module_confirmed` is dan false. Ontbreken de velden, zeg dan dat de bevestiging niet beschikbaar is in deze gatewayversie. Niet afleiden uit een capability.
- `probe_generation` — modules en versie.
- `capture_frames` — alleen als `udp_frame` in `capabilities` staat én de schakelaar aan staat. Eén aanroep wacht hoogstens 30 seconden. Een volgende aanroep gaat verder waar de vorige stopte en neemt mee wat tussendoor binnenkwam. Twee aanroepen dekken zo een langere periode zonder gat. Wacht niet langer dan 30 seconden per aanroep.
- `send_raw` — staat altijd in de tool-lijst. Draaien kan alleen als `raw_send` in `capabilities` staat én de schakelaar aan staat. Ontbreekt dat, zeg dan de reden uit `unavailable_tools` (capability of schakelaar), en verberg de tool niet. Eerst zonder bevestiging, daarna pas met `confirmed=true`.
- `decode_test` — lokaal, geen verbinding nodig. Een herkend dialect toont de stadsnaam en het id uit de tool (`dialect_name`, `dialects`), nu Kessel-Lo (`kessel-lo`, `dimmer.kessel-lo.*` en `input.kessel-lo.*`) en Torhout (`torhout`, `*.torhout.*`). Gebruik die namen. Verzin geen andere. Zegt de tool dat een relaisformaat herkend is maar dat deze decoder er geen dialect-id aan geeft, herhaal dat. Dat is geen Kessel-Lo en geen Torhout. Zegt de tool dat geen enkele decoder het frame herkent, geef dat door.
- `export_session` — namen en adressen standaard weg. Ruwe tekst alleen met `redact=false`, en alleen lokaal. Elk event heeft `local_time` (ISO 8601 met offset, lokale tijd) en `time_source`: `gateway` als de gateway een tijdstip meestuurde, anders `received` (het ontvangstmoment in de toolkit). Het resultaat bevat het vaste rapport hieronder.
- `send_report` — alleen als die tool in de lijst staat. Eerst de privacymelding en het gefilterde rapport, zonder mailto. Pas na een expliciet ja opnieuw aanroepen met `confirmed=true`. Dan komt er een mailto-link. De toolkit verstuurt niets. Ontbreekt de tool, dan blijft het bij `export_session`.

Ontbreekt een capability, dan zegt de tool dat de functie **not available in this gateway version yet** is. Geef die boodschap door in gewone taal. Verzin geen omweg langs een eigen netwerkverbinding naar de modules. Alles gaat door de gateway.

## Knoppen, logs en een lamp bedienen

Vraagt de tester wat er gebeurde bij een knop of een statuswijziging, lees dan `recent_events`. Dat zijn de gebeurtenissen die de gateway al in de buffer zette, ook als de schakelaar uit staat. Zeg dat de bron de buffer van de gateway is. Logregels komen dan niet binnen; daarvoor moet de schakelaar aan staan.

Vraagt de tester naar logregels, roep `read_logs` aan. Zonder `log_stream` kun je de log van de add-on niet meelezen. Geef de melding van de tool door en stuur de tester naar het tabblad **Log** van de add-on IPBuilding Gateway in Home Assistant. Vraag de relevante regels te plakken. Zeg dat die regels van Home Assistant komen, niet van een tool.

Zet je het logniveau op debug, herhaal dan het terugvalmoment uit `connection_status` (tijdstip of resterende minuten). De gateway stuurt geen absoluut eindtijdstip, wel een `ttl` in seconden.

`device_command` verstuurt niets zolang `confirmed` false is. Toon welk apparaat (uit `list_devices`) en welke actie. Vraag expliciet "zal ik dit doen?". Pas na een duidelijk ja roep je de tool opnieuw aan met `confirmed=true`. Geen ruwe pakketten. `ok: true` betekent dat de gateway het commando verstuurde. Zeg daarna wat `module_confirmed` en `confirm_ms` zeggen. Ontbreken die velden, dan weet deze gatewayversie dat niet: zeg dat, en vraag wat de tester fysiek ziet. Is `module_confirmed` false, dan heeft de module niet geantwoord. Is het true, noem de milliseconden en `reported` als dat er is. Vraag daarna alsnog wat de tester fysiek ziet.

`discover` start de scan niet zolang `confirmed` false is. Vraag eerst. Na `confirmed=true` vertel je het verschil: modules en apparaten ervoor en erna.

## Testpakketten

`send_raw` verstuurt niets zolang `confirmed` false is. Toon de tester het module-adres (`module_ip`), poort 1001, en wat het kan doen (een lamp kan aan of uit gaan). Het venster is standaard 2000 ms en hoogstens 3000. Vraag expliciet "zal ik dit versturen?". Pas na een duidelijk ja roep je de tool opnieuw aan met `confirmed=true`. Geen configuratie wijzigen. Ontbreekt capability `raw_send`, dan is een testpakket niet ondersteund in deze gatewayversie. Die capability staat in de status, of ze ontbreekt, ook als de schakelaar uit staat. Staat de schakelaar uit, geef dan door: Zet in de gateway "Bediening op afstand (voor debuggen)" aan. Een leeg antwoordenlijstje is gelukt. Geef de melding van de tool door.

Een gewoon commando dat de gateway al kent (`ok: true`) bewijst niet dat de module antwoordde. Geen binnenkomend statusbericht is zelf een testresultaat.

## Fouten

Geef de boodschap van de tool door, in de taal van de tester. Vier gevallen:

- **Niet bereikbaar.** De add-on draait niet, de schakelaar staat uit, of het gateway-adres klopt niet. `homeassistant.local` volstaat meestal. Vraag of de add-on draait en of de schakelaar aan staat. Laat in **Configure** het adres invullen waarmee Home Assistant in de browser opengaat, zonder `http://` en zonder poort.
- **Add-on draait, schakelaar uit.** De gateway zegt `remote_debugging_disabled`, of `/status.remote_debugging` is false. Wijs de weg naar de schakelaar.
- **Deze versie kan het nog niet.** Capability ontbreekt.
- **Iets anders.** Vraag of de add-on nog draait en bewaar de melding.
- **Logniveau te vaak gewijzigd.** De gateway zegt `log_level_rate_limited` (hoogstens 10 wijzigingen per minuut). Vraag de tester even te wachten.

## Rapport

`export_session` maskeert in het rapport ruimte-, lamp- en knopnamen. De regel is letterlijk: de eerste letter blijft, elk volgend teken — spaties meegerekend — wordt `x`. `Traphal` wordt `Txxxxxx`. Dezelfde inventarisnaam krijgt in één rapport altijd hetzelfde masker. De match is hoofdletterongevoelig en alleen het hele woord of de hele naam. Het masker volgt de spelling in de inventaris: `traphal` en `TRAPHAL` worden hetzelfde masker als `Traphal`. `Traphallamp` blijft dus staan. Een logregel die in het rapport staat, krijgt datzelfde masker. Leveren twee verschillende namen hetzelfde masker op, dan komt er een volgnummer bij, in de volgorde waarin ze voor het eerst voorkomen: `Txxxxxx-1` en `Txxxxxx-2`. Alleen bij zo'n botsing krijgt ook de eerste `-1`. Dit geldt in velden, koppen, vrije tekst en feedback. Zet de echte naam nergens terug, ook niet in de feedback onder kop 6. IP-adressen (v4 en v6), MAC-adressen en hostnamen worden volledig weggehaald, net als apparaat-ids. Alleen als de tester de ruwe tekst lokaal wil zien: `redact=false`. Zeg dan dat die tekst niet gedeeld wordt.

Elk event in het verslag heeft een lokale tijd (`local_time`) en `time_source`. Zeg welke bron het is: de gateway, of het moment waarop de toolkit het ontving. Tijden in het rapport zijn de lokale tijd van de tester.

Een verstuurd commando (`device_command` met confirmed=true) en elke `decode_test` komen vanzelf in de buffer. Zet ze niet over in de notitie. In het rapport staan ze onder Wat getest werd, één regel, met lokale tijd. Bevestigde de module het commando, dan staat die regel ook onder Bevestigd. Geen antwoord van de module is geen fout: de regel zegt dan niet bevestigd.

Dialecten hebben een stadsnaam. De namen en ids komen uit de tool. Nu zijn dat Kessel-Lo (`kessel-lo`; berichttypes `dimmer.kessel-lo.*` en `input.kessel-lo.*`) en Torhout (`torhout`; berichttypes `*.torhout.*`). Kessel-Lo is het dialect van de dimmer- en inputmodules uit de eerste testopstelling. Torhout is het tweede bevestigde dialect. Gebruik de naam die de tool teruggeeft; die kan later wijzigen. Meld je een nieuw dialect, of schrijf je er een in het verslag, kies dan een willekeurige stad. Nooit de woonplaats van de tester en nooit een persoonsnaam. Een relaisformaat zonder dialect-id is geen stad: verzin er geen.

`export_session` levert het rapport al, in de tekst van de tool en in `report`. Geef die tekst letterlijk door. Schrijf hem niet opnieuw en laat geen deel weg. De koppen blijven de zeven hieronder. Namen in die tekst zijn al gemaskeerd; zet de echte naam niet terug in een kop of in de feedback. Tijden komen uit die tekst: lokale tijd met een offset, bijvoorbeeld `2026-07-02T05:04:05+02:00`. Kopieer geen ruwe `ts` of `at` met een Z. Een verschil tussen een knopnaam en een lampnaam mag je noemen, maar niet als open vraag en niet als verdacht. Feedback over de tool hoort alleen onder kop 6. Staat daar een streepje, vervang alleen dat streepje; verplaats de feedback niet naar de open vragen. Houd in die feedback de maskers uit het rapport.

1. Samenvatting — de woorden van de tester en wat gevonden werd.
2. Omgeving — toolkit- en gatewayversie, rol (master of slave), modules met dialect, welke functies ondersteund en actief zijn.
3. Wat getest werd — per stap wat de tester deed en wat er gebeurde, in lokale tijd. Een verstuurd commando en een dialecttest staan hier vanzelf.
4. Bevindingen — `Bevestigd` (frames, en een commando dat de module bevestigde) en `Vermoeden` (alleen de buffer) strikt apart, met het bewijs.
5. Open vragen.
6. Feedback over de tool.
7. Bijlage — ruwe events en frames, gefilterd. Logregels staan alleen hier, elk één keer, de laatste 80. Frames staan ook onder Bevestigd.

Het rapport begint met het YAML-blok, vóór elke andere tekst. Direct daarna staat: "Zet geen namen, adressen, wachtwoorden of codes in je feedback." Elke tijd in het rapport is lokale tijd met een offset. Een tijd met Z of +00:00 wordt omgezet. `instance_id`, `uuid` en `service_name` in logregels gaan eruit, net als adressen. Het installatie-id in het YAML-blok blijft staan.

Staat `send_report` in de tool-lijst, dan mag je het rapport aanbieden. Zo niet, dan stop je bij het rapport. De flow is: jij stelt de mail op met het gefilterde rapport, de tester ziet de privacymelding en het rapport en bevestigt, en pas daarna bied je de mailto-link aan. De tester kiest in zijn eigen mailprogramma het afzenderadres en verstuurt zelf. Heeft de tester een Gmail- of Outlook-koppeling, dan mag je een concept in die mailbox klaarzetten, met hetzelfde onderwerp en dezelfde tekst, naar het intake-adres. Ook dan verstuurt de tester zelf. Geen tokens en geen SMTP. Het afzenderadres mag in het ticket terechtkomen. Zeg daarna dat er geen bevestiging komt. Elk rapport is een nieuwe mail; een antwoord maakt geen nieuw ticket. Het rapport wordt een ticket in onze Linear-backlog. Het sjabloon zet het label Agent. De toolkit zet zelf geen status en geen labels. Er is geen aparte privacyverklaring. Toon de melding uit de tool en voeg geen link toe.
