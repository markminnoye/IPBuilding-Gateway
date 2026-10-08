# IPBuilding Gateway Tools

Deze gids is voor iemand die thuis de IPBuilding Gateway in Home Assistant gebruikt.

Je krijgt één bestand: `ipbuilding-gateway-tools.mcpb`.

## Installeren in Claude Desktop

1. Dubbelklik op het bestand. Claude Desktop gaat open en vraagt of je IPBuilding Gateway Tools wil installeren. Bevestig dat.
2. Lukt dubbelklikken niet, open dan Claude Desktop, ga naar **Instellingen → Extensies** en kies het bestand.
3. Het gateway-adres staat al op `homeassistant.local`. Gebruik je dat adres, druk dan meteen op **Save**. Alleen als Home Assistant een ander adres heeft, verander je het veld. Zonder `http://` en zonder poort. Dit is het adres van Home Assistant in je thuisnetwerk, niet een adres van een losse module.

## Nieuwere testversie

Elke testversie heeft een eigen nummer: `0.1.0-rc.1`, daarna `0.1.0-rc.2`, `0.1.0-rc.3`, enzovoort. Dat nummer staat in de naam van het bestand. Staat IPBuilding Gateway Tools er al, dan toont Claude Desktop **Update** in plaats van **Install**. Zo zie je welke build je hebt.

## Schakelaar in Home Assistant

IPBuilding Gateway Tools kan pas meekijken als een schakelaar aan staat.

1. Open Home Assistant.
2. Ga naar **Instellingen → Add-ons → IPBuilding Gateway → Configuratie**.
3. Onder **Debug** zet je de schakelaar aan.
   - Engelse Home Assistant: **Remote debugging and control**
   - Nederlandse Home Assistant: **Debuggen en bedienen op afstand**
4. De add-on start opnieuw. Dat hoort zo.
5. Zolang de schakelaar aan staat, blijft er een melding in Home Assistant staan. Iedereen op je netwerk kan dan het verkeer van je modules meelezen en via de gateway een testpakket sturen. De schakelaar gaat niet vanzelf uit.

## Eerste vraag

Open een chat met IPBuilding Gateway Tools erbij en typ, in je eigen woorden, bijvoorbeeld:

> Een lamp gaat niet uit. Kun je meekijken wat er gebeurt?

De assistent vraagt eerst wat je ziet, in welke ruimte, en of het altijd gebeurt. Daarna kijkt hij of de gateway bereikbaar is. Staat de schakelaar uit, dan vraagt hij je om hem aan te zetten.

## Wat een foutmelding betekent

**"De gateway is niet bereikbaar."**
De add-on draait niet, of het adres in de bundel klopt niet. Kijk of IPBuilding Gateway in Home Assistant aan staat, en of je `homeassistant.local` (of het adres dat jij gebruikt) goed hebt ingevuld.

**"De add-on draait, maar 'Remote debugging and control' staat uit."**
Zet de schakelaar aan op de plek hierboven. Wacht tot de add-on opnieuw is opgestart en stel je vraag opnieuw.

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

Een knopdruk of een lamp die van status verandert kan hij teruglezen uit wat de gateway al heeft doorgegeven. De log van de add-on kan deze versie nog niet meesturen. Dan vraagt de assistent je het tabblad **Log** van IPBuilding Gateway te openen en de relevante regels te plakken.

Een verslag haalt adressen, apparaatnamen en ruimtenamen standaard weg. Alleen als je de ruwe tekst lokaal wil zien, kan de assistent die tonen. Deel die ruwe tekst niet.

## Als je klaar bent

Zet **Remote debugging and control** / **Debuggen en bedienen op afstand** weer uit. De add-on start opnieuw en de melding in Home Assistant verdwijnt.
