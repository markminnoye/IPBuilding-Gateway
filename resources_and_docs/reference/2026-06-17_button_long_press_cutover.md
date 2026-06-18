# Cutover — Long press, dim-tijdens-hold, IPBox-import

Voor gebruikers die hun IPBox-installatie naar de open gateway + companion
willen overzetten met behoud van drukknop-gedrag inclusief long press en
dim-tijdens-hold.

## Overzicht

```
IPBox (legacy)              Open gateway + companion
─────────────────             ───────────────────────────
Drukknop (fysiek)    ────►  IP1100PoE `B-…E` press/release
UDP/1001 hub         ────►  gateway timing-classificatie
func1/func2 mapping  ────►  import_ipbox_to_ha.py → automations.yaml
Sferen / scenes      ────►  HA-blueprint (dim_button.yaml)
IPBox REST :30200    ────►  gateway /api/v1/ + WebSocket /ws
```

## Volgorde

### 1. Gateway add-on installeren (HA Supervisor)

```text
Settings → Add-ons → Add-on Store → ⋯ → Repositories
→ https://github.com/markminnoye/IPBuilding-Gateway
→ Install "IPBuilding Gateway" → Start
```

Zie `ipbuilding_gateway/DOCS.md` voor add-on config. Standaard staat de
gateway al op de veldbus als `10.10.1.1` zodra de IPBox uit is.

### 2. Companion installeren (HACS)

```text
HACS → Integrations → ⋯ → Custom repositories
→ https://github.com/markminnoye/ipbuilding-gateway-ha
→ Categorie: Integration → Install "IPBuilding Gateway HA"
→ Restart Home Assistant
```

Companion v0.4.0+ is vereist voor long press. De gateway companion uit
HACS detecteert het add-on automatisch via Supervisor.

### 3. Discovery sweep

```text
Instellingen → Apparaten & entiteiten → Integraties
→ IPBuilding Gateway HA → ⋯ → Run discovery sweep
```

Of: `POST http://<gateway>:8080/api/v1/discover` vanuit een REST tool.

### 4. Importscript draaien (eenmalig, op een werkstation)

Vereist: bereik tot `10.10.1.50` (IP1100PoE HTTP) en optioneel tot de
IPBox REST op `:30200`.

```bash
git clone https://github.com/markminnoye/IPBuilding-Gateway
cd IPBuilding-Gateway
python3 scripts/import_ipbox_to_ha.py \
    --ipbox-host 192.168.0.185 \
    --out ./out
```

Output:

```
out/
├── automations.yaml     # import in HA
├── helpers.yaml         # plak in configuration.yaml
├── import_report.md     # lees dit — warnings + niet-converteerbaar
└── checksum.txt         # SHA256 van inputs
```

### 5. Helpers in HA laden

Plak `out/helpers.yaml` in `/config/configuration.yaml` onder de
`input_boolean:` key. Voorbeeld:

```yaml
input_boolean:
  ipb_keuken_knop_1_dim_up:
    name: Keuken knop 1 — dim omhoog
    icon: mdi:arrow-up-bold
```

Restart Home Assistant.

### 6. Automatiseringen importeren

```text
Instellingen → Automatiseringen & scènes → Automatiseringen
→ ⋯ → Automaties importeren → kies out/automations.yaml
```

Elke automation is standaard **disabled**. Schakel ze in na een eerste
testdruk.

### 7. Knop-entities inschakelen

De knop-entities zijn standaard **disabled+hidden** (zoals legacy
HA-IPBuilding). Om ze actief te maken:

```text
Instellingen → Apparaten & entiteiten → Entiteiten
→ filter "event" → selecteer de knop → Inschakelen
```

### 8. Knop-blueprint kiezen

De companion levert vanaf **v0.4.0** vier doelgerichte blueprints.
Kies het patroon dat bij de wandknop past; maak één automatisering per
blueprint, met dezelfde knop als trigger.

| Blueprint | Wanneer te gebruiken |
|-----------|---------------------|
| `button_toggle` | Eén tik op de knop schakelt één lamp / schakelaar, of alle lampen in een ruimte |
| `button_standard` | Korte en/of lange druk, elk met on / off / toggle / scene-activering voor een entity of alle lampen in een ruimte |
| `button_dim` | Korte druk = toggle, hold = dimmen met automatische richting-flip (vereist een `input_boolean` direction helper) |
| `button_cover` | Hold = gordijn/screen open of close, release = stop (en optioneel korte druk) |

De oude naam `IPBuilding button — toggle + dim during hold` (`dim_button.yaml`)
blijft nog één release als stub bestaan voor bestaande automatiseringen.
Maak nieuwe automatiseringen vanuit de nieuwe blueprint-namen; de stub
vuurt een `persistent_notification` af zodra hij nog wordt gebruikt.

#### Voorbeeld dim-flow (was stap 8)

Kies `button_dim.yaml`. Voorbeeld-instellingen voor een keuken-knop:

| Input | Waarde (voorbeeld) |
|-------|---------------------|
| Naam automatisering | `Keuken wandknop → Keuken LED` |
| Knop | `event.2f8185190000df` |
| Ruimte | `Keuken` |
| Lamp | `light.keuken_led` |
| Dim-richting helper | `input_boolean.ipb_keuken_knop_1_dim_up` |
| Dim-stap % | `5` |
| Dim-interval (ms) | `200` |
| Dim-grens % | `50` |

De helper aanmaken: Instellingen → Apparaten & services → Helpers →
Toggle. **Naam** mag spaties bevatten; **Entity ID** alleen `a-z`,
`0-9` en underscores (anders krijg je `slugify`-fouten).

### 9. Live-test

1. Lamp aan, brightness 50%.
2. Korte druk → lamp toggle (uit).
3. Korte druk → lamp aan.
4. Hold → `long_pressed` → lamp dimt omhoog in stapjes.
5. Release → `released` → loop stopt, helper flip naar "down".
6. Hold opnieuw → lamp dimt omlaag.
7. Bij 1% of 100% → automatische flip van richting.

### 10. IPBox uitschakelen

Pas nadat alle stappen 1-9 succesvol zijn verlopen:

1. IPBox voeding loskoppelen van het veldbus (UDP/1001 stopt).
2. Gateway neemt de hub-rol over op `10.10.1.1` (of een ander vrij IP
   binnen de IPBuilding-VLAN, afhankelijk van je netwerkconfig).
3. Modules reageren nu op de gateway in plaats van de IPBox.
4. IPBox kan op het thuis-LAN blijven voor archief-doeleinden (REST
   `:30200` blijft werken) of volledig verwijderd worden.

## Wat wordt gemigreerd en wat niet

| IPBox-functie | Migratie | Opmerking |
|---------------|-----------|-----------|
| func1 (korte druk) | ✅ automations.yaml | 1-op-1 mapping |
| func2 (long press) | ✅ automations.yaml | Dim-loop blueprint in HA |
| release-actie | ✅ automations.yaml | |
| emailGroup | ❌ handmatig | HA `notify:` helper of mobiele app |
| Sferen / moods | ❌ niet via import | HA-native scenes, losse stap |
| Multi-actie regels (1 knop → N outputs) | ❌ niet via import | Zie `ARCHITECTURE.md` |
| Thresholds (func2.holdSeconds) | ✅ automatisch | Uit `getButtons` naar gateway `ButtonConfig` |
| Hold-minuten (auto-off) | ✅ als `delay` in YAML | |

## Rollback

Mocht iets niet werken:

1. Gateway stoppen (Add-on → Stop).
2. IPBox voeding herstellen — modules reageren weer op IPBox.
3. IPBox-projectconfig is niet aangetast door het importscript (read-only
   ten opzichte van IPBox).
4. Helpers en automations in HA uitschakelen of verwijderen.

## Probleemoplossing

| Symptoom | Oorzaak / oplossing |
|----------|---------------------|
| Geen knop-entities in HA | Knop nog niet ontdekt → run discovery sweep. Of: getButtons niet opgehaald → `POST /api/v1/modules/refresh`. |
| Drukken geeft geen event | Knop-entity niet ingeschakeld (zie stap 7) of IP1100PoE niet bereikbaar. |
| Long press vuurt nooit | Drempel te hoog: zet `hold_threshold_s` lager in `devices.json` (`buttons` key) of via de `getButtons` API. |
| Release vuurt nooit | Wire-frame mist — controleer mirror POV of laat gateway-logs zien. |
| Helper wordt overschreven door importscript | Bedoeld gedrag voor nieuwe buttons. Bestaande helpers met conflict worden gelogd in `import_report.md`, niet overschreven. |
| Companion kan gateway niet vinden na IPBox-uit | Companion v0.3.10+ heeft Supervisor auto-detection. Handmatig: configuratie-entry met host = gateway add-on host. |
