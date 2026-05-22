# Scan Modules — HTTP / WebConfig analyse

**Datum:** 2026-05-17  
**Context:** IPBox WebConfig v1.8.4.3, service 1.8.0.3, centrale `ip2017-814`  
**UI:** `http://192.168.0.185/general/Wizards/Modules/Index`  
**Capture-sessie:** `captures/2026-05-17T210800Z_scan_modules/`

---

## Samenvatting

De wizard **Modules → Start scan** gebruikt **geen** IPBox REST `:30200` en **geen** SignalR-hub voor de scan zelf. De browser doet een **POST** naar een **ASP.NET MVC**-endpoint op de WebConfig-webserver (`/general/...`). SignalR (`loadingHub`) draait parallel alleen voor **loading/progress** in de UI.

Voor de gateway betekent dit: **module discovery is een aparte laag** naast `GET /api/v1/comp/items` (runtime-inventaris van outputs/knoppen).

---

## UI-flow (3 stappen)

| Stap | UI-label | URL / actie |
|------|----------|-------------|
| 1 | SCAN MODULES | `GET /general/Wizards/Modules/Index` → knop **Start scan** |
| 2 | UITGANGEN BENOEMEN / TWEEDE STAP | `GET /general/Wizards/Modules/Step2?ip={ip}&type={type}` |
| 3 | SAMENVATTING | (niet vastgelegd in deze sessie) |

**Module selectie (stap 2, vastgelegd):** klik op relay `10.10.1.30` →  
`GET /general/Wizards/Modules/Step2?ip=10.10.1.30&type=Relais`  
Titel: *Relais stuurmodule* — toont 24 uitgangen (omschrijving + groep), overeenkomend met `comp/items` Type 1 op `10.10.1.30`.

---

## HTTP-endpoints (browser network log)

| Methode | URL | Rol |
|---------|-----|-----|
| **POST** | `/general/Wizards/Modules/ScanForModules` | **Start scan** — discovery; retourneert modulelijst (JSON, schema hieronder afgeleid) |
| GET | `/general/Wizards/Modules/Index` | Wizard stap 1 |
| GET | `/general/Wizards/Modules/Step2?ip=…&type=…` | Wizard stap 2 (configuratie per module) |
| **POST** | `/general/Hardware/Relais/ImportRelayInfo` | Laadt kanaal-/uitganginfo bij openen stap 2 (relay) |
| GET | `/general/signalr/hubs` | Alleen `loadingHub` geregistreerd |
| GET | `/general/signalr/negotiate`, `/start`, `/connect`, `/ping` | SSE-transport voor loading indicator |

**Authenticatie:** `ScanForModules` zonder sessie-cookie → **302** naar `/general/Home/Unauthorized`. Alleen aanroepbaar vanuit ingelogde WebConfig-sessie.

**Niet gebruikt voor scan:** `http://192.168.0.185:30200/api/v1/comp/items` (wel nuttig als **baseline** — zie correlatie).

---

## Scan-resultaat (UI → afgeleid response-model)

Na **Start scan** toonde de UI twee modules:

| IP | MAC (UI-notatie) | MAC (hex) | Firmware | Status in UI |
|----|------------------|-----------|----------|--------------|
| `10.10.1.30` | `0.36.119.82.172.190` | `00:24:77:52:ac:be` | 5.1 | Bestaande |
| `10.10.1.50` | `0.36.119.82.173.170` | `00:24:77:52:ad:aa` | 5.2.4 | Bestaande |

**Niet in scanlijst:** `10.10.1.40` (dimmer) — wél in `comp/items` (4× Type 2) en wél zichtbaar op veldbus UDP/1001 in dezelfde pcap.

**MAC-notatie:** decimale octetten gescheiden door punten; eerste “octet” is soms `0.36` (= bytes `00` en `24`). Omzetting: splits op `.`, interpreteer elk segment als 0–255 → hex MAC.

**Vermoedelijk JSON (te verifiëren met geauthenticeerde POST + response capture):**

```json
[
  {
    "ip": "10.10.1.30",
    "mac": "0.36.119.82.172.190",
    "version": "5.1",
    "type": "Relais",
    "isNew": false
  }
]
```

`type`-waarden gezien: `Relais` (Step2 query). Verwacht ook `Dimmer` / input-type voor IP1100.

---

## Correlatie met REST-inventaris (`comp/items`)

Baseline: `captures/2026-05-17T210800Z_scan_modules/comp_items_baseline.json`

| IP | In scan-UI | In `comp/items` | Types in REST |
|----|------------|-----------------|---------------|
| `10.10.1.30` | Ja | Ja (24 items) | Type 1 (relay outputs) |
| `10.10.1.40` | Nee | Ja (4 items) | Type 2 (dimmer) |
| `10.10.1.50` | Ja | Ja (32 items) | Type 50 (buttons) |

**Interpretatie:**

- **Scan** = fysieke **controllers** op het IPBuilding-VLAN (MAC + firmware + IP).
- **`comp/items`** = logische **projectobjecten** (kanalen, knoppen) die aan die controllers hangen via `IpAddress` + `Port` (1001) + `Protocol` (0).

Gateway-implicatie: implementeer `discover_modules()` (L2/L3/UDP10001) **en** apart `import_project_inventory()` (REST of WebConfig-project-DB).

---

## Implicaties voor IPBox-vervanging

1. **WebConfig API** (poort 80 op thuis-LAN, pad `/general/...`) is nodig voor **provisioning**, niet alleen REST `:30200`.
2. Minimale discovery-API voor parity:
   - `POST /wizard/modules/scan` → lijst `{ip, mac, version, moduleType, isNew}`
   - `GET /wizard/modules/{ip}/channels?type=…` → equivalent van Step2 + ImportRelayInfo
3. **DS-manager-achtige discovery** op de veldbus (zie UDP-doc) moet op de **IPBuilding-NIC** draaien (`10.10.1.1`), niet op het thuis-LAN.
4. Volgende RE-stap: geauthenticeerde capture van **POST ScanForModules response body** + Step2 voor dimmer/input.

---

## Open punten

- Exact JSON-schema van `ScanForModules` (response) en POST-body (leeg vs. parameters).
- Waarom dimmer `.40` niet in scanlijst verschijnt (reeds gekoppeld? ander discovery-pad?).
- Of `ImportRelayInfo` / equivalenten voor dimmer en IP1100 dezelfde structuur gebruiken.
