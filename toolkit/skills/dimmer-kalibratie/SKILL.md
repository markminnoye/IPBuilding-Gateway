---
name: dimmer-kalibratie
description: >
  Kalibreer een IP0300PoE dimmerkanaal stap voor stap met de MCP-tool
  calibrate_dimmer (status, sweep, video-analyse met ffprobe luma-meting en
  apply). Gebruik zodra de gebruiker een dimmer wil inregelen of kalibreren
  op ondergrens (dimMin), bovengrens (dimMax), dimcurve (dim_gamma) of
  standaard fadetijd (default_fade).
---

# Dimmer kalibreren (`IP0300PoE`)

Gebruik de MCP-tool `calibrate_dimmer` om de echte fysieke lichtgrenzen en dimcurve van een `IP0300PoE`-kanaal te meten en vast te leggen.

## Principes

- **Modulebereik (`dimMin` .. `dimMax`):** een `IP0300PoE` schaalt busopdrachten `1–100%` lineair naar het bereik `[dimMin .. dimMax]`. Te lage `dimMin` geeft dode stappen onderaan; te hoge `dimMax` geeft een dood plateau bovenaan en vertraagt aan/uit-faden.
- **Perceptuele curve (`dim_gamma`, `1.0 .. 3.5`):** de gateway past per kanaal `dim_gamma` toe zodat lage percentages op een 0–10V LED-driver vloeiend en natuurlijk aanvoelen.
- **Standaard fade (`default_fade`, `0 .. 255`):** elke eenheid op de veldbus is ongeveer `0,1 s` (`0` = meteen, `30` ≈ `3 s`).
- **Veiligheid:** zowel `sweep` als `apply` voeren niets uit zolang `confirmed=false`. Laat eerst het voorstel zien en vraag de tester om bevestiging vóór je `confirmed=true` zet.

## Stappenplan met `calibrate_dimmer`

### 1. Huidige stand en kanalen bekijken (`mode="status"`)

Roep `calibrate_dimmer(mode="status")` aan (optioneel gefilterd op `device_id`, `module_ip` of `channel`, waarbij kanalen vanaf `0` tellen).

- Noteer per kanaal de uitgangscode (`<laatste octet>.<blok>.<pin>`), `dim_gamma`, `default_fade`, en als de module rechtstreeks bereikbaar is ook `descr`, `gr`, `dim_min` en `dim_max`.
- Is directe HTTP naar de module niet bereikbaar vanaf de tool-host, meld dat eerlijk: de sweep en gateway-parameters (`dim_gamma`, `default_fade`) werken dan nog steeds via de gateway, maar voor het schrijven van `dimMin`/`dimMax` op de module zelf is bereikbaarheid tot het modulesubnet nodig.

### 2. Ruimte en smartphonecamera voorbereiden

Geef de tester deze instructies vóór de meting:

1. **Verduister de kamer** (gordijnen/screens dicht, andere lampen uit) zodat omgevingslicht minimaal en constant blijft.
2. **Film indirect:** richt de smartphone op een **indirect verlichte muur, plafond of tafel** — nooit rechtstreeks in de spot of LED-strip, anders clipt de camerasensor.
3. **Vaste camera-instelling:** zet HDR-video bij voorkeur uit (SDR 1080p, 25 of 30 fps), stel kort scherp met lamp op ~50–100% en houd op de muur vast voor **AE/AF Lock** (schuif belichting desnoods iets lager zodat vol licht niet wit uitbrandt).

### 3. Kalibratiesweep uitvoeren (`mode="sweep"`)

1. Roep eerst `calibrate_dimmer(mode="sweep", device_id=..., confirmed=false)` aan om duur, stappen en kamera-instructie te tonen.
2. Zodra de tester de video-opname op de telefoon start en bevestigt, roep opnieuw aan met `confirmed=true` (eventueel met `countdown_seconds=5` als hij nog moet weglopen).
3. De tool zet tijdelijk een lineaire stand (`dim_gamma=1.0`, en `0..100` op de module indien bereikbaar), geeft een **sync-puls** (`100%` aan → `0%` uit voor het donkerniveau), doorloopt de stappen met `fade=0`, herstelt direct alle oorspronkelijke waarden en geeft `sweep_log_path` terug.
4. Laat de tester na de laatste keer uit de video stoppen en naar deze computer overzetten (bijv. AirDrop naar Downloads).

### 4. Video analyseren (`mode="analyze"`)

Roep aan:

```
calibrate_dimmer(
  mode="analyze",
  video_path="<pad naar .MOV/.MP4>",
  sweep_log_path="<pad uit stap 3>"
)
```

De tool gebruikt `ffprobe` (`10 Hz` luma) om automatisch de dalende sync-flank te vinden en per stap `yavg`, relatieve helderheid (`norm_pct`) en status (`OFF` / `ACTIVE` / `SATURATED`) te berekenen.

- Toon **altijd** de volledige staptabel met gemeten ontsteking (`measured_dim_min`) en het voorstel (`recommended_dim_min`, `recommended_dim_max`, `recommended_dim_gamma`) aan de tester.
- Bespreek of een iets ruimere of krappere marge (`margin_min`) gewenst is.

### 5. Instellingen opslaan (`mode="apply"`)

1. Roep eerst `calibrate_dimmer(mode="apply", device_id=..., dim_min=..., dim_max=..., dim_gamma=..., default_fade=..., confirmed=false)` aan.
2. Laat exact zien wat er verandert (oud → nieuw, met behoud van `descr` en `gr` op de module) en vraag een expliciete ja.
3. Sla pas na bevestiging op met `confirmed=true`. De tool verifieert `dimMin`/`dimMax` op de module en past `dim_gamma` / `default_fade` op de gateway aan.

### 6. Visuele proef en identieke kringen

- Laat de tester `1%`, `50%`, `100%` en een fade aan/uit beoordelen (`1%` stabiel aan zonder flikkeren, zichtbaar verschil bovenin tussen `70%` en `100%`).
- Heeft een tweede kanaal exact dezelfde armatuur en driver, stel dan voor om dezelfde gemeten waarden daarop over te nemen (ook eerst met `confirmed=false` voorleggen) en `1%` visueel na te kijken.
