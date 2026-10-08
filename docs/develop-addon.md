# Ontwikkelversie van de add-on

Dit is alleen voor je eigen Home Assistant, om de `develop`-tak te proberen.
De gewone installatie voor testers blijft de release.

## De ontwikkelversie toevoegen

1. Ga in Home Assistant naar **Instellingen → Add-ons → Add-onwinkel**.
2. Klik rechtsboven op de drie puntjes en kies **Repositories**.
3. Plak dit adres en voeg het toe:

   `https://github.com/markminnoye/IPBuilding-Gateway#develop`

4. Sluit het venster en ververs de add-onwinkel.
5. Er staat nu een tweede **IPBuilding Gateway** in de lijst. Open die.
   Het versienummer ziet eruit als `1.8.0-dev.3` (er staat `-dev.` in).
   Dat is de ontwikkelversie. De gewone release is een gewoon nummer,
   bijvoorbeeld `1.7.0`, zonder `-dev`.

## Aanzetten

Draai niet twee gateways tegelijk. Die praten allebei met dezelfde modules.

1. Open de **gewone** IPBuilding Gateway en klik op **Stop**.
2. Open in die gewone add-on het paneel **IPBuilding Gateway**.
   Bij **Backup & restore** kies je **Download backup** en bewaar je het bestand.
3. Installeer de ontwikkelversie (de add-on waarvan het nummer `-dev.` bevat)
   en start die.
4. Open het paneel van de ontwikkelversie. Bij **Backup & restore** kies je
   **Restore from backup** en selecteer je het bestand uit stap 2.

Daarna laat Home Assistant bij elke nieuwe ontwikkelversie een update zien.
Staat automatisch updaten aan, dan installeert Home Assistant die zelf en
herstart de add-on.

## Terug naar de gewone release

1. Open de ontwikkelversie en klik op **Stop**.
2. Start de gewone IPBuilding Gateway weer.
3. Staat de lijst met modules leeg, zet dan de backup terug in het paneel
   van de gewone add-on (**Restore from backup**).

De gewone release herken je aan een versienummer zonder `-dev`.
Je hoeft de develop-repository niet te verwijderen. Laat de ontwikkelversie
gewoon uit staan.

## Bediening op afstand (voor debuggen)

Die schakelaar staat bij de add-on die je gebruikt (de gewone of de ontwikkelversie):

**Instellingen → Add-ons → IPBuilding Gateway → Configuratie**

Open de groep **Debug**. De schakelaar heet **Bediening op afstand (voor debuggen)**. In het Engels heet dezelfde schakelaar **Remote control (for debugging)**.

Zet hem alleen aan als je een probleem onderzoekt. Hij laat een hulpprogramma op je netwerk de gateway-logs live meelezen, het logniveau een tijdje hoger zetten, en de veldbusberichten zien die deze gateway zelf verstuurt en ontvangt. Zonder deze schakelaar weigert de gateway dat.

De schakelaar blijft aan tot je hem zelf weer uitzet. Hij gaat niet vanzelf uit.

Zolang hij aan staat, toont Home Assistant een melding. Die zie je bij het belletje, en die blijft staan tot je de schakelaar uitzet. Wijzigen herstart de add-on.
