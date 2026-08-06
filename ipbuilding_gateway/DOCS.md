# IPBuilding Gateway — Home Assistant Add-on

Open veldbus-hub voor IPBuilding relais, dimmers en drukknoppen via **UDP/1001**.
Dit vervangt de propriëtaire IPBox op de veldbus en voedt de companion
[**IPBuilding Gateway HA**](https://github.com/markminnoye/ha-ipbuilding-gateway)
via WebSocket (`8080`) en optioneel REST (`30200` shim).

> **Zonder companion geen HA-entiteiten.** Deze add-on alleen levert de gateway;
> lichten/schakelaars/sensoren komen pas via de companion-integratie. Zie
> [README.md](README.md) voor de korte intro en HACS-link; versies lopen
> onafhankelijk — zie de
> [companion releases](https://github.com/markminnoye/ha-ipbuilding-gateway/releases).

> **Voor add-on-ontwikkelaars:** het manifest-formaat (`config.yaml`), Supervisor
> communicatie, watchdog, `host_network`, `privileged`, publicatie en security
> van deze add-on volgen de officiële Home Assistant Apps developer docs:
> <https://developers.home-assistant.io/docs/apps/>

## Features

- **UDP/1001 veldbus** — praat rechtstreeks met IP0200PoE, IP0300PoE en IP1100PoE
- **WebSocket + REST northbound API** — productie-protocol op `8080`
- **Auto-discovery** — runtime init-sweep (vult `devices.json` met `active: false`), passieve ARP-monitor (30 s interval, detecteert nieuwe/verwijderde modules), geforceerde discovery via `POST /api/v1/discover`
- **IPBox migratie-shim** — REST compatibiliteit op `30200` (opt-in)
- **Supervisor integratie** — add-on beheer, auto-update, logs

---

## Installation

### 1. Add repository

[![Add Repository](./assets/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway)

Of handmatig: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
```
https://github.com/markminnoye/IPBuilding-Gateway
```

### 2. Install add-on

**Add-on Store** → zoek **"IPBuilding Gateway"** → **Install**

### 3. Configure

Kopieer `devices.json` naar de add-on config folder via **Samba** of **SSH**:

```
/addon_configs/<repo-hash>_ipbuilding_gateway/devices.json
```

Het `<repo-hash>` is zichtbaar in de add-on info panel.

#### Generate devices.json (fresh install)

```bash
cd /path/to/IPBuilding-Gateway
PYTHONPATH=. python -m gateway.discover --range-start 30 --range-end 59
cp devices.discovered.json devices.json
```

#### Generate devices.json (migrating from IPBox)

```bash
IPBOX_WEB_HOST=http://192.168.0.185 \
IPBOX_SESSION_COOKIE="ASP.NET_SessionId=<cookie>" \
python scripts/discover_from_ipbox.py
```

> **Let op:** dit pad is voor **andere eigenaren** met een oudere IPBox/centrale
> waarvan de WebConfig de modules kent. Op de huidige IPBox (WebConfig v1.8.4.3,
> ASP.NET MVC 4.0) antwoordt `ScanForModules` met een **lege array** — de
> scan-resultaten worden pas daarna asynchroon via SignalR `loadingHub` naar
> de browser gestuurd. Als het script eindigt met `0 modules` of een lege
> `devices.json`: open `http://<ipbox>/general/Wizards/Modules/Index` in een
> browser, klik **"Start scan"**, wijs minimaal één module toe, en draai
> daarna dit script opnieuw. Voor je eigen installatie is
> `python -m gateway.discover` (zie hierboven) het productiepad.

### 4. Start

**Settings → Add-ons → IPBuilding Gateway → Start**

Bekijk logs voor de opstartstatus:
```
[run.sh] GATEWAY_BUTTONS_VIA_HA=1
[run.sh] GATEWAY_BIND_IP=0.0.0.0
[run.sh] GATEWAY_MULTI_PRESS=0
[run.sh] GATEWAY_MULTI_PRESS_WINDOW_MS=350
[run.sh] GATEWAY_DEVICES_FILE=/config/devices.json
```

---

## Configuration

Opties staan gegroepeerd in **Settings → Add-ons → IPBuilding Gateway → Configuration** (nested schema), met **Installatie** als eerste groep.

| Option (nested) | Default | Description |
|-----------------|---------|-------------|
| `installation.expose_inactive_channels` | `false` | Toon ongebruikte relay-/dimmer-kanalen (`active: false`). Standaard uit — de Web UI toont altijd alle kanalen. |
| `installation.multi_press` | `false` | Herken dubbele en driedubbele druk op alle wandknoppen. Het Multi-press venster bepaalt hoe lang klikken bij elkaar horen. Add-on herstarten na wijziging. |
| `installation.multi_press_window_ms` | `350` | Tijd (ms) waarbinnen een tweede of derde klik bij de vorige hoort. Standaard 350. Add-on herstarten na wijziging. |
| `installation.devices_file` | `/config/devices.json` | Pad naar het installatieconfigbestand (Samba: `addon_configs/.../devices.json`) |
| `fieldbus.buttons_via_ha` | `true` | Drukknoppen via Home Assistant (aan) of lokaal op de ingangsmodule (uit). Zie hieronder. |
| `fieldbus.poll_interval` | `2.0` | Hoe vaak (s) de gateway de ingangsmodule bevraagt — alleen relevant als `buttons_via_ha` aan staat |
| `fieldbus.actuator_poll_interval` | `20.0` | Hoe vaak (s) de gateway relais- en dimmermodules bevraagt om ze online te houden |
| `network.bind_ip` | `0.0.0.0` | Op welk IP de gateway naar veldbusmodules luistert. Standaard alle interfaces; bijv. `10.10.1.1` voor alleen de veldbus-interface |
| `network.rest_shim_enabled` | `false` | IPBox REST-compatibiliteit op poort `30200` (tijdelijk tijdens migratie; standaard uit) |
| `network.http_timeout_s` | `2.0` | Maximale wachttijd (s) bij het herkennen van modules tijdens discovery |
| `network.metadata_timeout_s` | `5.0` | Maximale wachttijd (s) bij het ophalen van modulegegevens. Verhoog bij trage VLAN |
| `discovery.discovery_subnet` | `10.10.1` | Subnet (/24) waarop modules worden gezocht |
| `discovery.discovery_range_start` | `0` | Eerste hostnummer in het scanbereik (0 = hele /24) |
| `discovery.discovery_range_end` | `254` | Laatste hostnummer in het scanbereik |
| `discovery.auto_discover_on_start` | `false` | Zoek modules bij add-on start. Ontbrekend of ongeldig `devices.json` triggert altijd een scan |
| `discovery.passive_arp_monitor` | `true` | Detecteer nieuwe/verdwenen modules via netwerkverkeer (zonder broadcast-scan) |
| `discovery.arp_poll_interval_s` | `30.0` | Hoe vaak (s) de passieve monitor het netwerk bekijkt |
| `discovery.use_env_defaults` | `false` | Lab/test: vaste `.30/.40/.50` IPs als `devices.json` ontbreekt. Productie: uit laten |
| `logging.log_level` | `info` | Logniveau: `debug`, `info`, `warning`, `error` |

De API/web-UI-poort (`8080`) en de IPBox REST-compatibiliteitspoort (`30200`) liggen vast en staan **niet** in deze tabel — ze staan onder Supervisor’s eigen **Network**-sectie op de add-on info-pagina (zie [Ports](#ports)).

Oude flat keys (zonder groepering) blijven werken tot je de configuratie opnieuw opslaat.

### Drukknoppen via Home Assistant

Of de IP1100PoE-drukknoppen events naar **Home Assistant** sturen, stel je in met **`fieldbus.buttons_via_ha`** (standaard aan).

| Optie | Config | LED op module | Wie stuurt knoppen aan? | Wanneer kiezen |
|-------|--------|---------------|-------------------------|----------------|
| **Aan** | `fieldbus.buttons_via_ha: true` | Groen **continu** (= slave) | Gateway → events → **Home Assistant** | Standaard: knop-events naar HA (aan/uit, scene, automation, …) |
| **Uit** | `fieldbus.buttons_via_ha: false` | Groen **knipperend** (= master) | **Ingangsmodule** zelf (eigen opgeslagen koppelingen) | Knoppen lokaal houden (bijv. tijdens migratie); geen knop-events naar HA |

**Fallback:** als de gateway uitvalt of geen verbinding heeft, neemt de ingangsmodule het over volgens zijn eigen opgeslagen koppelingen (niet noodzakelijk hetzelfde als in Home Assistant). De gateway schrijft die module-configuratie nog niet weg. Bij knoppen via HA blijft de configuratie op de module als noodvoorziening actief.

**Tijdelijk knoppen lokaal houden:**

1. Zet `fieldbus.buttons_via_ha` **uit**.
2. **Herstart** de add-on.
3. Controleer op de IP1100: LED knippert groen; knoppen bedienen verlichting volgens de module-configuratie.
4. Relais en dimmers blijven beschikbaar in de companion.
5. Na cutover: zet weer **aan** en herstart — LED brandt continu; knop-events komen in Home Assistant.

**LED (IP1100-handleiding):** continu groen = module in **slave** (centrale/HA); knipperend = **master** (lokaal). De Web UI-badge toont nog Slave/Master; de Configuration-optie spreekt over knoppen via HA.

**Verschil met kanaal `active`:** `active: false` op een drukknop schakelt alleen de northbound/HA-entity uit; bij knoppen via HA pollt de gateway de input-module nog steeds. `buttons_via_ha` bepaalt of **deze gateway** de veldbus-claim voor ingangen overneemt.

Uitgebreide uitleg staat ook in de Configuration-UI (translations) en in de add-on docs tab.

---

## Network

** Vereiste:** HA moet de veldbus-modules (`10.10.1.30/40/50`) kunnen bereiken met een **source IP in `10.10.1.x`**.

| Methode | Wanneer |
|--------|---------|
| **VLAN trunk op één NIC** (aanbevolen HA Green) | Native = thuisnetwerk, getagd = IPBuilding VLAN |
| **Extra NIC** op veldbus-segment | vast `10.10.1.x` adres |

Check of VLAN correct is:

```bash
ip addr show eth0.2
ping -c1 10.10.1.30
ping -c1 10.10.1.40
ping -c1 10.10.1.50
```

---

## Ports

| Poort | Protocol | Gebruik |
|-------|----------|---------|
| `8080` | HTTP + WebSocket | Northbound API — companion, apps, Node-RED. Vast, niet configureerbaar (`host_network: true` maakt Supervisor's eigen poort-remapping irrelevant). |
| `30200` | HTTP REST | IPBox compatibiliteits Shim — **uitgeschakeld tenzij `network.rest_shim_enabled: true`** |

Beide poorten staan met een korte omschrijving onder Supervisor's eigen **Network**-sectie op de add-on info-pagina (via `translations/{taal}.yaml` → top-level `network:` key), naast deze tabel.

---

## Troubleshooting

### Add-on start niet

```
Settings → Add-ons → IPBuilding Gateway → Logs
```

Zoek naar `[run.sh]` — als die ontbreekt is `devices.json` niet geladen.

### Companion vindt de add-on niet

- Add-on moet **draaien** (niet enkel geïnstalleerd)
- Companion en add-on hoeven niet dezelfde versie te hebben — beide volgen onafhankelijk semver. Controleer [de companion releases](https://github.com/markminnoye/ha-ipbuilding-gateway/releases) en [de add-on releases](https://github.com/markminnoye/IPBuilding-Gateway/releases) voor de meest recente versies.
- Check **Settings → Devices & Services → Discovered** (niet alleen “Add integration”)
- De northbound API luistert altijd op poort `8080` (vast, niet configureerbaar)
- Supervisor discovery vereist HA OS / Supervised; op standalone gateway gebruikt de companion mDNS (`_ipbgw._tcp.local.`)

### Geen entities met namen — "10.10.1.30:0"

`devices.json` ontbreekt of is incompleet. Genereer opnieuw met de discovery CLI.

### Companion ziet "unconfigured" entities

Nieuwe modules die via de passieve ARP-monitor worden gevonden worden in `devices.json` geschreven met `active: false` en `room: "Unconfigured"`. De companion toont deze entities als "unconfigured". Om ze te activeren:

1. **Option A (handmatig):** bewerk `devices.json` via Samba/SFTP — zet `active: true` en vul `name`/`room` in.
2. **Option B (API):** roep `POST /api/v1/discover` aan — doet een volledige HTTP-identificatie; firmware-updates worden weggeschreven maar naam/kamer niet automatisch.
3. **Option C (toekomstig companion-workstream):** companion leert `active: false` / `room: "Unconfigured"` herkennen en toont een "Configureer" UI in HA.

UDP polling werkt niet

- `host_network: true` is vereist — check `config.yaml`
- HA heeft een **IP adres op `10.10.1.x`** nodig
- Inter-VLAN routing vanuit thuisnetwerk (zonder eigen `10.10.1.x` op HA) is **niet voldoende** voor UDP replies

---

## Architectuur

```
IPBuilding veldbus (UDP/1001 · 10.10.1.x)
  ├── IP0200PoE relay   → 10.10.1.30
  ├── IP0300PoE dimmer  → 10.10.1.40
  └── IP1100PoE input   → 10.10.1.50

              ↓ UDP/1001 (host_network: true)

         ipbuilding_gateway (HA Add-on)
         ├── REST :30200   (shim, opt-in)
         └── REST :8080 + WebSocket /ws  ←── ipbuilding-gateway-ha
```

---

## Companion (Home Assistant integration)

Install **[ipbuilding-gateway-ha](https://github.com/markminnoye/ha-ipbuilding-gateway)**
— any recent release. Versies lopen onafhankelijk van deze add-on; zie de
[companion releases](https://github.com/markminnoye/ha-ipbuilding-gateway/releases)
voor de meest recente versie.

1. **HACS** → Custom repository → `https://github.com/markminnoye/ha-ipbuilding-gateway`
2. Install **IPBuilding Gateway HA** and restart Home Assistant
3. With the add-on **running**, open **Settings → Devices & Services → Discovered**
   and add the integration (Supervisor discovery — no host/port needed)

Full companion docs: [README](https://github.com/markminnoye/ha-ipbuilding-gateway/blob/main/README.md)
· Add-on docs (this file) · [API reference](../docs/api/)
