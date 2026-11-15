---
description: Kalibreer een IP0300PoE dimmerkanaal stap voor stap (dimMin, dimMax, dim_gamma en fade)
argument-hint: [kanaal of ruimte]
---

Start de dimmerkalibratie voor $ARGUMENTS.

Volg de skill `dimmer-kalibratie`:
1. Roep eerst `calibrate_dimmer(mode="status")` aan (met `channel="$ARGUMENTS"` als er een kanaal of ruimte is opgegeven) en toon een overzichtstabel met Kanaal, Ruimte, Uitgang (`<octet>.<blok>.<pin>`), `dimMin`, `dimMax`, `dim_gamma` en `default_fade`.
2. Geef de opname-instructies (kamer verduisteren, camera op indirect verlicht oppervlak, **AE/AF Lock** inschakelen) en leg de sweep voor met `calibrate_dimmer(mode="sweep", channel=..., confirmed=false)`.
3. Start de sweep pas na expliciete bevestiging (`confirmed=true`) terwijl de video opneemt.
4. Analyseer het videobestand met `calibrate_dimmer(mode="analyze", channel=..., video_path=...)` en toon altijd de volledige tabel van alle 16 stappen (`Yavg` en `dY`).
5. Leg het voorstel voor (`calibrate_dimmer(mode="apply", ..., confirmed=false)`) en schrijf pas na bevestiging (`confirmed=true`) weg naar de module en gateway.
