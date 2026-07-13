# devices.json — pushbuttons/detectors genest per module

**Datum:** 2026-07-13
**Type:** Design spec (devices.json-schema + gateway-backend)
**Status:** Approved (2026-07-13)
**Scope:** `gateway/installation.py`, `gateway/device_config.py`, `gateway/gateway_api.py`, `gateway/module_metadata.py`, `gateway/auto_discovery.py`, nieuw migratiescript, bijhorende tests.

---

## 1. Aanleiding

Twee onafhankelijke bevindingen tijdens deze sessie:

1. **Databug:** `run_forced_discovery()` (`POST /api/v1/discover`, [gateway/auto_discovery.py:557](../../gateway/auto_discovery.py)) herschrijft `devices.json` als `{"modules": modules_to_write}` — de top-level `"buttons"`-key ontbreekt volledig. Omdat `InstallationConfig._parse()` een ontbrekende `"buttons"`-key stilzwijgend als lege lijst leest, en `AtomicWriter.write()` een volledige overschrijving doet (geen merge), **wist elke "Discover new modules"-run de volledige geconfigureerde `buttons[]`-array**. Kanaalgegevens van bestaande relay/dimmer-modules blijven wel bewaard (die komen via `mc.to_dict()` mee).
2. **Echte backupConfig-export** (`IP1100PoE-10_10_1_50-20260713.json`, bestandsnaamconventie bevestigt `backupConfig`, zie [IPBUILDING_KNOWLEDGE.md:119](../../resources_and_docs/IPBUILDING_KNOWLEDGE.md)) toont de echte IPBuilding-vocabulaire: een input-module heeft **`pushbuttons[]`** (met `index`, `id`, `descr`, `gr`, `func1`/`func2`) en een aparte, structureel gelijkaardige **`detectors[]`** (leeg in dit huis, aparte `getDetectors`-endpoint, [KNOWLEDGE.md:275](../../resources_and_docs/IPBUILDING_KNOWLEDGE.md)).

Beide bevindingen wijzen naar dezelfde oplossing: knoppen (en detectoren) **nesten binnen hun eigenaar-module**, zoals kanalen dat al doen via `modules[].channels[]`. Dat maakt de hele klasse "vergeten mee te schrijven"-bugs onmogelijk (elke module-serialisatie neemt zijn eigen data automatisch mee), en laat het schema 1:1 mappen op de echte IPBuilding-terminologie voor toekomstige `backupConfig`-import.

## 2. Schema

```json
{
  "modules": [
    {
      "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
      "firmware": "", "model": "", "mac": "00:24:77:52:ad:aa",
      "pushbuttons": [
        {
          "id": "2f8185190000df", "channel": 1,
          "name": "Badkamer knop", "room": "1e verdieping",
          "active": true, "hold_threshold_s": 1.5
        }
      ],
      "detectors": []
    },
    {
      "name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay",
      "firmware": "", "model": "", "mac": "00:24:77:52:ac:be",
      "channels": [
        {"ch": 0, "name": "Keuken LED", "room": "Eetkamer", "semantic_type": "light", "active": true, "max_watt": 60}
      ]
    }
  ]
}
```

**Type-afhankelijke serialisatie:** een module-entry toont ofwel `channels` (relay/dimmer) ofwel `pushbuttons`+`detectors` (input) — nooit een betekenisloze lege array van het andere concept. `ModuleConfig.to_dict()`:

```python
def to_dict(self) -> dict:
    d = {"name": self.name, "ip": self.ip, "type": self.type.value,
         "firmware": self.firmware, "model": self.model, "mac": self.mac}
    if self.type == DeviceType.INPUT:
        d["pushbuttons"] = [b.to_dict() for b in self.pushbuttons]
        d["detectors"] = [x.to_dict() for x in self.detectors]
    else:
        d["channels"] = [c.to_dict() for c in self.channels]
    return d
```
In-memory blijven `mc.channels`/`mc.pushbuttons`/`mc.detectors` gewoon altijd bestaan (dataclass-default `[]`) ongeacht type — enkel de schrijfkant is voorwaardelijk. De parser blijft `.get(key, [])` gebruiken en verandert dus niet door deze keuze.

Geen top-level `"buttons"` meer.

## 3. Dataclasses (`gateway/installation.py`)

- **`ButtonConfig` → `PushbuttonConfig`** (hernoemd voor consistentie met de wire-vocabulaire, nu er ook een `DetectorConfig` bijkomt). Nieuw veld: `channel: int | None = None`, gevuld uit de echte `getButtons`/backupConfig `"index"`. `module_id` blijft bestaan maar wordt voortaan afgeleid uit de nesting-positie tijdens parsen (was via PATCH toch al niet zelfstandig instelbaar).
- **Nieuwe `DetectorConfig`** — bewuste **schema-plaatshouder**: minimale velden (`id`, `name`, `room`, `active`), **geen** device_type, **geen** API-blootstelling, **geen** UDP-protocol-decodering. Er bestaat vandaag geen enkele echte `getDetectors`-sample om een preciezer schema op te baseren; dit is puur zodat een leeg/toekomstig gevuld `detectors[]`-array correct rondtript zonder dataverlies.
- **`ModuleConfig`** krijgt `pushbuttons: list[PushbuttonConfig] = field(default_factory=list)` en `detectors: list[DetectorConfig] = field(default_factory=list)` naast het bestaande `channels`.

Alle huidige verwijzingen naar `ButtonConfig` (in `gateway_api.py`, `device_config.py`, `module_metadata.py`, tests) hernoemen mee naar `PushbuttonConfig`, voor volledige consistentie: `apply_button_patch`→`apply_pushbutton_patch`, `validate_button_fields`→`validate_pushbutton_fields`, `NORTHBOUND_BUTTON_FIELDS`→`NORTHBOUND_PUSHBUTTON_FIELDS`, `button_by_id`→`pushbutton_by_id`, `button_threshold`→`pushbutton_threshold`, `installation.buttons`→`installation.pushbuttons`, `_buttons_by_id`→`_pushbuttons_by_id`. Geen functioneel verschil, enkel naamgeving.

## 4. Parser + veiligheidsnet (`InstallationConfig._parse()`)

Leest `pushbuttons`/`detectors` voortaan uit `mod.get("pushbuttons", [])`/`mod.get("detectors", [])` binnen de module-loop (i.p.v. een aparte top-level `"buttons"`-loop). `installation.pushbuttons`/`_pushbuttons_by_id` worden op dezelfde manier opgebouwd als vandaag, enkel de bron verandert. Detectoren krijgen geen vergelijkbare vlakke index/lookup — ze worden enkel bewaard binnen hun module, conform de "schema-plaatshouder, geen runtime-gedrag"-afspraak.

**Veiligheidsnet:** treft `_parse()` nog een top-level `"buttons"`-key aan, dan gooit het een duidelijke `InstallationError` ("oud plat formaat gedetecteerd — run `scripts/migrate_buttons_to_nested.py` om te converteren naar `modules[].pushbuttons[]`") in plaats van de data stilzwijgend te laten vallen.

## 5. Schrijf-paden

`installation_to_raw_dict()` (`device_config.py`) wordt `{"modules": [m.to_dict() for m in installation.modules]}` — geen aparte buttons-regel meer. `run_forced_discovery()` (`auto_discovery.py`) hoeft **niets** te wijzigen aan zijn schrijf-payload-constructie: omdat het al `mc.to_dict()` per bestaande module gebruikt, komen genest pushbuttons/detectors vanzelf mee. De databug uit §1 verdwijnt hierdoor structureel.

## 6. API-oppervlak (`GET`/`PATCH /api/v1/devices`) — **stabiel voor de companion**

**Belangrijke afbakening:** deze hernoeming is een **interne opslag-wijziging**. De REST-response naar de HA-companion toe blijft `device_type: "input"` / `semantic_type: "button"` gebruiken zoals vandaag — dat wijzigen zou een breaking change zijn voor de al-gedeployde companion-integratie en is hier niet aan de orde.

Enige toevoeging: `_build_device_list()`/`_device_dict_for_id()` (`gateway_api.py`) zetten `entry["channel"]` voor knoppen, gevuld uit `cfg_btn.channel` (geconfigureerde knop) of rechtstreeks `btn.get("index")` (nog-niet-geconfigureerde knop uit de metadata-cache). `NORTHBOUND_PUSHBUTTON_FIELDS` blijft `{name, room, active}` — `channel` is een fysiek-bedradingsfeit, niet PATCH-baar (zelfde logica als `ch` bij relais). Zichtbaar in de webUI via de al-bestaande "Ch"-kolom.

Detectoren krijgen **geen** entry in `_build_device_list()` — ze zijn niet zichtbaar/bewerkbaar via de API in deze wijziging.

## 7. Migratiescript

Nieuw `scripts/migrate_buttons_to_nested.py`:
- Leest het bestand met kale `json.load()` (niet via `InstallationConfig`, die het oude formaat nu net weigert).
- Maakt eerst een `.bak`-kopie van het originele bestand.
- Verplaatst elke top-level `buttons[]`-entry naar de bijhorende module se `pushbuttons[]` op basis van `module_id` ↔ `mac`-match; waarschuwt en slaat over bij een niet-matchende `module_id` (orphan-guard).
- Voegt `"detectors": []` toe aan elke input-module-entry die dat nog niet heeft.
- **Geen live veldbus-call** — `channel` blijft `null` voor bestaande knoppen tot een volgende "Refresh known modules" of PATCH het invult.
- Idempotent: no-op als er geen top-level `"buttons"`-key meer aanwezig is.

## 8. Tests

- Bestaande buttons-tests (`test_installation.py`, `test_device_config.py`, `test_gateway_api_devices_patch.py`, `test_auto_discovery.py`) aangepast naar het geneste `pushbuttons`-formaat en hernoemde symbolen.
- Nieuw: parser weigert oud plat formaat met duidelijke `InstallationError`.
- Nieuw: migratiescript zet correct om + idempotentie-test.
- Nieuw: `channel`/`index` komt door tot in de API-response, voor zowel geconfigureerde als niet-geconfigureerde knoppen.
- Nieuw (regressie voor de oorspronkelijke bug): `run_forced_discovery()` behoudt `pushbuttons[]` na een discovery-run op een installatie die al knoppen had.

## 9. Expliciet buiten scope

- Detector-runtime-gedrag: geen `device_type`, geen UDP-protocol-decodering, geen API-blootstelling — er bestaat nog geen enkele RE-kennis over het detector-protocol.
- Wijzigingen aan de REST-API-contractwaarden (`device_type`/`semantic_type`) richting de companion.
- Live backfill van het `channel`-veld voor bestaande knoppen tijdens migratie.
