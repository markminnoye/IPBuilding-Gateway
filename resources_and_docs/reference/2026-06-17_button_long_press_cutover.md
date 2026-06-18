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

### 8. Knop-actie opzetten

Vanaf companion **v0.4.0-rc.11** worden er geen packaged blueprints
meer geïnstalleerd in de Blueprint-picker van de operator. Kies één
van de volgende drie paden:

1. **Community-blueprint** (aanbevolen voor de meeste operators).
   Bijvoorbeeld:
   - [Philips Hue Dimmer Switch Ultimate Controller (Z2M)](https://community.home-assistant.io/t/z2m-philips-hue-dimmer-switch-ultimate-controller-device-triggers-double-clicks/977875)
     — ondersteunt onze `press` / `long_press` / `release`-semantiek.
   - [IKEA STYRBAR 4-Button Remote (ZHA / MQTT)](https://gist.github.com/ivvil/08c95674732b51bc4ccf79938471cdc9)
     — per knop configureerbaar.

   Installeer via HACS of `ha_import_blueprint`. Kies de event-entity
   van de fysieke knop als trigger.

2. **Standaard HA-flow**. Maak een automation vanuit het device-scherm
   (`+ Toevoegen aan → Maak automatisering`) of
   `Instellingen → Automatiseringen & scènes → + Maak automatisering
   → Maak nieuwe automatisering`. Trigger: `state` op de event-entity
   met `to: "press"` (en eventueel `to: "long_press"` /
   `to: "release"`). Action: `light.toggle` (korte druk) of
   `repeat: while: trigger.id == "hold"; light.turn_on;
   brightness_step_pct: -10; delay: 200ms` (smooth dim tijdens hold).

3. **YAML-referentie** (geavanceerd). De blueprint-files in de
   companion-repo demonstreren de patronen:
   [`blueprints/automation/ipbuilding_gateway_ha/`](https://github.com/markminnoye/ipbuilding-gateway-ha/tree/main/custom_components/ipbuilding_gateway_ha/blueprints/automation/ipbuilding_gateway_ha/).
   Kopieer de `trigger` en `action` blokken naar `automations.yaml`.

#### Voorbeeld: korte druk → toggle

```yaml
trigger:
  - platform: state
    entity_id: event.2f8185190000df
    to: "press"
    id: press
action:
  - action: homeassistant.toggle
    target:
      entity_id: light.keuken_led
```

#### Voorbeeld: hold → smooth dimmen, release → flip direction

```yaml
trigger:
  - platform: state
    entity_id: event.2f8185190000df
    to: "press"
    id: press
  - platform: state
    entity_id: event.2f8185190000df
    to: "long_press"
    id: hold
  - platform: state
    entity_id: event.2f8185190000df
    to: "release"
    id: release
action:
  - choose:
      - conditions:
          - condition: trigger
            id: press
        sequence:
          - action: light.toggle
            target:
              entity_id: light.keuken_led
      - conditions:
          - condition: trigger
            id: hold
        sequence:
          - variables:
              sign: "{{ 1 if is_state('input_boolean.ipb_keuken_knop_1_dim_up', 'on') else -1 }}"
          - repeat:
              while:
                - condition: trigger
                  id: hold
              sequence:
                - action: light.turn_on
                  target:
                    entity_id: light.keuken_led
                  data:
                    brightness_step_pct: "{{ 5 * sign }}"
                    transition: 0.2
                - delay:
                    milliseconds: 200
      - conditions:
          - condition: trigger
            id: release
        sequence:
          - action: input_boolean.toggle
            target:
              entity_id: input_boolean.ipb_keuken_knop_1_dim_up
```

De `input_boolean` direction helper aanmaken: Instellingen →
Apparaten & services → Helpers → Toggle. **Naam** mag spaties
bevatten; **Entity ID** alleen `a-z`, `0-9` en underscores (anders
krijg je `slugify`-fouten).

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
