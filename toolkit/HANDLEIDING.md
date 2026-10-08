# IPBuilding Gateway Tools

Deze gids is voor iemand die thuis de IPBuilding Gateway in Home Assistant gebruikt.

Je krijgt één bestand: `ipbuilding-gateway-tools.mcpb`.

## Installeren in Claude Desktop

1. Dubbelklik op het bestand. Claude Desktop gaat open en vraagt of je IPBuilding Gateway Tools wil installeren. Bevestig dat.
2. Lukt dubbelklikken niet, open dan Claude Desktop, ga naar **Instellingen → Extensies** en kies het bestand.
3. `homeassistant.local` volstaat meestal. Druk dan meteen op **Save**. De toolkit slaat een adres over dat alleen op de computer van de gateway zelf werkt, en probeert daarna de hostnaam. Vanaf de nieuwe develop-versie van de add-on kondigt de gateway het adres op je thuisnetwerk aan. Alleen als dat niet lukt, vul je bij **Configure** het adres in dat je ook in je browser gebruikt om Home Assistant te openen. Zonder `http://` en zonder poort. Dit is het adres van Home Assistant, niet van een losse module.

## Nieuwere testversie

Elke testversie heeft een eigen nummer: `0.1.0-rc.1`, daarna `0.1.0-rc.2`, `0.1.0-rc.3`, `0.1.0-rc.4`, `0.1.0-rc.5`, `0.1.0-rc.6`, enzovoort. Dat nummer staat in de naam van het bestand. Staat IPBuilding Gateway Tools er al, dan toont Claude Desktop **Update** in plaats van **Install**. Zo zie je welke build je hebt.

## Schakelaar in Home Assistant

Live logs en testpakketten werken pas als een schakelaar aan staat. Een knopdruk en een lamp die van status verandert zie je ook als die schakelaar uit staat.

1. Open Home Assistant.
2. Ga naar **Instellingen → Add-ons → IPBuilding Gateway → Configuratie**.
3. Onder **Debug** zet je de schakelaar aan.
   - Engelse Home Assistant: **Remote control (for debugging)**
   - Nederlandse Home Assistant: **Bediening op afstand (voor debuggen)**
4. De add-on start opnieuw. Dat hoort zo.
5. Zolang de schakelaar aan staat, blijft er een melding in Home Assistant staan. Die zegt: "Bediening op afstand staat aan. IPBuilding Gateway Tools kan live verkeer lezen en commando's naar je modules sturen. Zet het uit in de instellingen van de add-on als het debuggen klaar is." Iedereen op je netwerk kan dan het verkeer van je modules meelezen en via de gateway een testpakket sturen. De schakelaar gaat niet vanzelf uit.

## Eerste vraag

Open een chat met IPBuilding Gateway Tools erbij en typ, in je eigen woorden, bijvoorbeeld:

> Een lamp gaat niet uit. Kun je meekijken wat er gebeurt?

De assistent vraagt eerst wat je ziet, in welke ruimte, en of het altijd gebeurt. Daarna kijkt hij of de gateway bereikbaar is. Staat de schakelaar uit, dan vraagt hij je om hem aan te zetten.

## Wat een foutmelding betekent

**"De gateway is niet bereikbaar."**
Controleer of de add-on IPBuilding Gateway draait en of de schakelaar aan staat. `homeassistant.local` volstaat meestal. Vul bij **Configure** het adres in dat je ook in je browser gebruikt om Home Assistant te openen, zonder `http://` en zonder poort.

**Het gevonden adres werkt alleen op de computer van de gateway zelf.**
De toolkit heeft de gateway gezien, maar dat adres is niet bruikbaar vanaf jouw computer. Hij probeert daarna de hostnaam. Lukt dat niet, vul bij **Configure** het adres in dat je in je browser gebruikt om Home Assistant te openen, bijvoorbeeld `homeassistant.local`, zonder `http://` en zonder poort, en druk op **Save**.

**"De add-on draait, maar 'Remote control (for debugging)' staat uit."**
Zet **Bediening op afstand (voor debuggen)** aan op de plek hierboven. Wacht tot de add-on opnieuw is opgestart en stel je vraag opnieuw.

**"nog niet beschikbaar in deze gateway-versie"**
De add-on draait, maar deze versie kan dat onderdeel nog niet. Je hoeft dan niets anders te controleren. Meekijken naar losse berichten op de modules kan pas na een nieuwere versie van de add-on.

**"Er ging iets mis bij het praten met de gateway."**
Kijk of de add-on nog draait. Blijft de melding, bewaar de tekst en geef die door aan wie de gateway voor je onderhoudt.

**"Het logniveau is te vaak gewijzigd."**
Wacht een minuut. De gateway laat hoogstens 10 wijzigingen per minuut toe.

**"te oud voor live meekijken"**
De add-on draait, maar deze versie kan nog niet live meekijken. Installeer de testversie via het develop-kanaal: Add-onwinkel, rechtsboven de drie puntjes, Repositories, en het adres dat de assistent noemt. De ontwikkelversie heeft `-dev.` in het versienummer. De gewone release is een gewoon nummer zonder `-dev`. Draai niet twee gateways tegelijk.

## Wat de assistent kan

Hij kan opvragen welk kanaal bij welke lamp hoort. Kanalen van een relais of dimmer tellen vanaf 0. Hij kan kijken of de gateway gezond is, een scan naar nieuwe modules starten (hij vraagt eerst), en één lamp schakelen of dimmen (hij vraagt eerst). Een antwoord dat het commando is aangekomen betekent niet dat de module heeft geantwoord. Kijk of de lamp echt veranderde.

Een knopdruk of een lamp die van status verandert kan hij teruglezen uit wat de gateway al heeft doorgegeven, ook als de schakelaar uit staat. Alleen de live logregels vallen dan weg. Kan de gateway logs meesturen en staat de schakelaar aan, dan leest de assistent die. Namen en adressen haalt hij daar standaard uit. Kan deze versie dat niet, dan vraagt hij je het tabblad **Log** van IPBuilding Gateway te openen en de relevante regels te plakken. Zet hij het logniveau tijdelijk hoger, dan zegt hij tot wanneer dat geldt. Daarna valt het vanzelf terug.

Een verslag haalt adressen, apparaatnamen en ruimtenamen standaard weg. De tijden daarin zijn lokale tijd. Alleen als je de ruwe tekst lokaal wil zien, kan de assistent die tonen. Deel die ruwe tekst niet.

Twee soorten modules hebben een stadsnaam: Kessel-Lo en Torhout. Een nieuwe soort krijgt een willekeurige stad, nooit jouw woonplaats en nooit jouw naam.

## Als je klaar bent

Zet **Remote control (for debugging)** / **Bediening op afstand (voor debuggen)** weer uit. De add-on start opnieuw en de melding in Home Assistant verdwijnt.
