IPBuilding Gateway Tools zijn hulpmiddelen voor AI-assistenten zoals Claude: ze helpen je samen met een assistent problemen in je IPBuilding-installatie te vinden. Wat jullie vinden, kun je als rapport naar Sonic Rocket sturen.

Persoonsgegevens, zoals adressen en namen van lampen en ruimtes, worden standaard weggefilterd uit het rapport.

Je hebt IPBuilding Gateway 1.8.0 in Home Assistant nodig, en Claude Desktop.

Om mee te kijken zet je in de gateway "Bediening op afstand (voor debuggen)" aan. Als je klaar bent, zet je het weer uit.

## Installeren

Download `ipbuilding-gateway-tools.mcpb` en dubbelklik het bestand. Dat is de download. Alleen daarmee kun je een rapport sturen. Claude Desktop vraagt of je IPBuilding Gateway Tools wil installeren. Kies **Install**. Staat de plug-in er al, dan staat er **Update**.

`homeassistant.local` volstaat meestal. Druk dan op **Save**.

Zegt de assistent dat de gateway niet bereikbaar is, controleer dan of de add-on draait en of de schakelaar aan staat. Vul bij **Configure** het adres in dat je ook in je browser gebruikt om Home Assistant te openen, zonder `http://` en zonder poort.

## IPBuilding Gateway Tools

Met deze plug-in krijgt Claude toegang tot je IPBuilding Gateway om je installatie te testen en te debuggen. Claude kan commando's uitvoeren en de resultaten ervan terugkrijgen als feedback.

**Meekijken aanzetten**

Claude kan pas meekijken als een schakelaar aan staat.

1. Ga in Home Assistant naar Instellingen → Add-ons → IPBuilding Gateway → Configuratie.
2. Zet onder Debug de schakelaar **Bediening op afstand (voor debuggen)** aan (Engels: *Remote control (for debugging)*).
3. De add-on start even opnieuw. Dat hoort zo.

Let op: zolang de schakelaar aan staat, kan iedereen op je thuisnetwerk meelezen met je modules en testpakketjes sturen. De schakelaar gaat niet vanzelf uit.

**Voorbeelden van vragen**

Je mag gewoon in je eigen woorden vragen. Claude vraagt altijd eerst bevestiging voordat er iets geschakeld of verstuurd wordt.

*Je installatie in kaart brengen*
- "Met welke gateway ben je verbonden, en wat kun je allemaal?"
- "Welke modules heb ik, en welke lampen, dimmers en knoppen hangen eraan?"
- "Zoek opnieuw naar modules en vertel me wat er veranderd is."
- "Antwoorden al mijn modules? Is er een die traag of niet reageert?"
- "Welke taal (dialect) spreken mijn modules?"

*Testen en meekijken*
- "Ik druk zo op een knop. Vertel me wat de gateway ziet, met module en kanaal."
- "Zet de lamp in de keuken aan en controleer of de module dat bevestigt."
- "Dim de lamp boven de tafel naar 30% en daarna weer uit."
- "Toon de logs van de laatste minuut. Zie je fouten of waarschuwingen?"

*Een probleem uitzoeken*
- "Het licht in de living gaat soms niet uit. Help me uitzoeken waarom."
- "Een knop in de gang reageert niet altijd. Wat zie je gebeuren als ik druk?"
- "Een dimmer doet raar. Kijk mee terwijl ik hem bedien."

*Feedback geven*
- "Maak een rapport van deze sessie, zonder adressen of namen erin."
- "Wat werkte vandaag niet, en wat zou de gateway beter moeten doen?"

**Klaar?**

Zet de schakelaar weer uit. De add-on start opnieuw en de melding in Home Assistant verdwijnt. Stuur het rapport naar ons, zodat we de software kunnen verbeteren.

## Voor ontwikkelaars (Claude Code)

Pak de zip `ipbuilding-gateway-tools-claude-code` uit. Ga in de map staan waar de uitgepakte map `ipbuilding-gateway-tools` in staat, en voer dit uit: `claude plugin install ipbuilding-gateway-tools --marketplace ./ipbuilding-gateway-tools`.

Vanuit de repository op GitHub: `claude plugin install ipbuilding-gateway-tools --marketplace markminnoye/IPBuilding-Gateway`. De plug-in blijft in `toolkit/`.

Een rapport sturen kan daar niet.
