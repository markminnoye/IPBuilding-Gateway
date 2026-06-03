# Discovery config review — scratch overwrite

**Datum:** 2026-06-03
**Type:** Design spec (scratch-test)

## Doel

`devices.json` volledig vervangen met output van ARP/HTTP discovery. Bewijzen dat gateway + companion werken met puur discovery-gebaseerde config — geen IPBox, geen legacy, geen merge.

## Conventie bestandsnamen

| Bestand | Rol |
|---------|-----|
| `devices.discovered.json` | Ruwe discovery-output (draft, lokaal artefact, niet committen) |
| `devices.json` | Operationele config — **volledig overschreven** door `devices.discovered.json` na review |

## Geen merge

De oude `devices.json` (6 kanalen, `ipbox_id`, `description`/`group`) wordt **volledig vervangen**. Geen diff, geen behoud van velden, geen vergelijking met IPBox WebConfig. Alleen de 28 kanalen uit discovery worden meegenomen.

## Review-checklist per kanaal

Per kanaal in `devices.discovered.json`:

```
name         — uit backupConfig; encoding fix waar nodig
room         — uit backupConfig
semantic_type — light (default); fan voor ventilatie kanalen
max_watt     — indicatief (~200 dimmer, ~60 relay/ventilator) — niet blokkerend
active       — true (alle 28 kanalen)
```

**Niet toevoegen:**
- `ipbox_id` — niet nodig voor open gateway product-API (entity-ID = `10.10.1.30-0`)
- `description` / `group` — oude velden; niet naar nieuwe config meenemen
- `id` (custom) — valt terug op `{ip}-{ch}` via `make_entity_id()`

## Bekende review-items

| Kanaal | Actie |
|--------|-------|
| relay ch 15 | encoding `¿` → juiste tekst |
| relay ch 9 | `semantic_type: fan` (ventilatie) |
| dimmer ch 3 | label `40.1.4` / room `Vrij` — check of placeholder behouden |
| dimmer ch 2 | `Keuken main` — check naam |

## Schema (ARCHITECTURE.md §5)

```jsonc
{
  "modules": [
    {
      "ip": "10.10.1.30",
      "type": "relay",
      "model": "IP0200PoE",    // uit getSysSet
      "mac": "00:24:77:52:ac:be",
      "firmware": "5.1",
      "channels": [
        {
          "ch": 0,
          "name": "Keuken LED",
          "room": "Keuken",
          "semantic_type": "light",
          "active": true,
          "max_watt": 60
        }
        // ... 23 meer relay kanalen
      ]
    },
    {
      "ip": "10.10.1.40",
      "type": "dimmer",
      "model": "IP0300PoE",
      "mac": "00:24:77:52:9e:a8",
      "firmware": "5.4",
      "channels": [
        // ... 4 dimmer kanalen
      ]
    },
    {
      "ip": "10.10.1.50",
      "type": "input",
      "model": "IP1100PoE",
      "mac": "00:24:77:52:ad:aa",
      "firmware": "5.2.4",
      "channels": []
    }
  ]
}
```

## Success criteria

1. `InstallationConfig.load("devices.json")` slaagt zonder errors
2. Precies **28 actieve kanalen** (`active: true`)
3. Gateway WebSocket `snapshot` toont 28 devices (was `device_list` — deprecated)
4. HA companion maakt entiteiten aan met discovery-namen (entity-IDs = `10.10.1.30-0` etc.)
5. Relay/dimmer command + `state_changed` werkt end-to-end

## Buiten scope

- REST-shim `:30200` / `ipbox_id`
- IPBox WebConfig import (`discover_from_ipbox.py`)
- HA add-on packaging
- Automatische merge-tool

## Review/goedkeuring

Dit document dient als checklists参考 voor de handmatige review. Goedkeuring betekent: `devices.discovered.json` is gecontroleerd en klaar om `devices.json` te overschrijven.
