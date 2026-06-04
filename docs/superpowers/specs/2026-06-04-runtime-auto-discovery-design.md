# Runtime auto-discovery — design spec

**Datum:** 2026-06-04
**Type:** Design spec (extending Fase 7 / Step 4 — `ARCHITECTURE.md` §4.1)
**Status:** Approved (2026-06-04)
**Scope:** gateway-side only. Companion (`ipbuilding-gateway-ha`) impact is sketched in §10 en blijft een aparte workstream.

---

## 1. Doel

De gateway voert vandaag **geen** runtime auto-discovery. `devices.json` is een statisch artefact dat handmatig via de `gateway.discover` CLI wordt gegenereerd en daarna alleen bij expliciete update wordt vernieuwd. `GATEWAY_AUTO_DISCOVER` in `run.sh` is dode code.

**Doel van deze iteratie:** drie ontdekking-modi achter één enkele gateway-component beschikbaar maken, met een **expliciete write-policy** (noord vs. fysiek vs. netwerk) zodat de gateway de installatieconfig nooit impliciet overschrijft.

| Modus | Trigger | Doel |
|-------|---------|------|
| **Init ARP-sweep** | Wanneer `devices.json` leeg is bij start | Eerste vulling van de installatie vanuit de veldbus |
| **Passieve ARP-monitor** | Continu tijdens runtime (default elke 30 s) | Nieuwe, gewijzigde of verdwenen modules detecteren |
| **Geforceerde discovery** | `POST /api/v1/discover` (REST) of WS-bericht | Operator-actie, negeert de mode-toggles |

**Niet in scope (terug naar backlog):** periodieke ARP-sweep om de 24 u. Wordt later toegevoegd zodra de passieve monitor stabiel is.

---

## 2. Write-policy (3 categorieën)

De gateway mag **nooit** impliciet beslissen om een northbound-veld te schrijven. Drie categorieën met eigen eigenaar:

| Categorie | Velden in `devices.json` | Eigenaar | Gateway-gedrag |
|-----------|--------------------------|----------|----------------|
| **Noordbound (HA-domein)** | `name`, `room`, `active`, `max_watt`, `semantic_type`, kanaal-specs | Companion / gebruiker | Alleen **lezen** |
| **Fysiek (module-EEPROM)** | `backupConfig`-kanalen, button-mapping, autonomy | Module zelf (WebConfig) of gateway op expliciete `POST /api/v1/provision/autonomy` | **Nooit** impliciet schrijven |
| **Netwerk / runtime** | `ip`, `mac`, `firmware`, `last_seen`, `last_seen_source` | Gateway zelf | `ip`/`mac` worden in runtime-registry bijgewerkt; `firmware` wordt naar `devices.json` teruggeschreven wanneer gewijzigd; `last_seen*` is runtime-only |

**Concreet:**

- Een nieuwe module die door de passieve monitor wordt gevonden → **append** aan `devices.json` met `active: false`, `room: "Unconfigured"`, lege `channels: []`. Atomic write met lock.
- Een verdwenen module (geen ARP-hit meer gedurende N polls) → enkel `unreachable: true` in runtime-registry. **Niet** verwijderen uit `devices.json`.
- DHCP-IP-wijziging → match op MAC, update `module.ip` in runtime-registry, emit `device_ip_changed` WS-event. **`devices.json` `ip` blijft initieel** tot de gebruiker expliciet opslaat (zie §6 voor rationale).
- Firmware-wijziging → één regel in `devices.json` bijgewerkt (firmware is objectief, geen split-brain risico).

**Gebruikersverhaal = US-D "Hybrid":** gateway voegt nieuwe modules **toe** aan `devices.json` (init-mode); bestaande modules worden **nooit** verwijderd of overschreven op noordbound-velden.

---

## 3. Alternatieven voor het *runtime* gedeelte (passieve ARP-monitor + atomic write)

Drie invalshoeken voor de ARP-bron, plus een gekozen aanpak voor de atomic write.

### 3.1 ARP-bron — 3 alternatieven

| # | Aanpak | Voordelen | Nadelen |
|---|--------|-----------|---------|
| **A1** | `subprocess.check_output(["arp", "-an"])` | Cross-platform (macOS, Linux, BSD); eenvoudig; herbruikt bestaande `parse_arp_table` uit `gateway/discovery.py` | Spawn per poll (~30 s); regex op stdout; afhankelijk van `arp`-binary in PATH; rolt onnodig over het hele systeem |
| **A2** | Directe read van `/proc/net/arp` (Linux-only) | Geen spawn; één file-read; al geïmplementeerd in `gateway/discovery.py` voor Linux | Linux-only; moet macOS-pad behouden voor ontwikkelaars; geen event-stream (poll-only) |
| **A3** | Netlink socket via `pyroute2` of `python-netlink` | Kernel-events (`RTM_NEWNEIGH`, `RTM_DELNEIGH`); geen polling; zeer efficiënt | Extra dependency; Linux-only; leercurve; op ESP32 (C++) sowieso andere aanpak; voor onze polling-cadans van 30 s overkill |

**Aanbeveling: A2 met macOS-vangnet (effectief A1+A2).**

- Primaire code-pad leest `/proc/net/arp` rechtstreeks; al geïmplementeerd in `gateway/discovery.py` `parse_arp_table()`.
- Op macOS (ontwikkelaar) valt het terug op `subprocess.check_output(["arp", "-an"])` — zelfde regex als vandaag, geen extra dependency.
- A3 (netlink) heeft geen nut bij 30 s polling-cadans en voegt een dependency toe die op RPi 3 al zwaar kan zijn.
- ESP32 (Deployment C) gebruikt sowieso lwIP `etharp_query()` per richtingsverkeer; valt buiten deze Python-spec.

### 3.2 Atomic write — gekozen aanpak

`tempfile` + `os.replace` + `fcntl.flock`:

1. Schrijf naar `<file>.tmp` in dezelfde directory.
2. `fsync()` op de file-descriptor.
3. `os.replace(tmp, final)` — atomaire rename op POSIX.
4. Optioneel: lock-acquire via `fcntl.flock(LOCK_EX)` op een sidecar-lock-file (`.lock`) zodat de companion niet halverwege een write leest.

**Reden:** `os.replace` is de standaard Python atomic-rename; werkt op alle doelplatformen (HA add-on = Linux, RPi = Linux, dev = macOS). `fcntl.flock` is POSIX-only; macOS heeft `flock` ook. Beide primitives zijn stdlib.

**Concurrency:** de companion leest `devices.json` *nooit* rechtstreeks; alle reads gaan via REST/WS (`/api/v1/devices`, `/api/v1/modules`). Het lock is dus alleen bedoeld om een *gateway-interne* race te voorkomen (bv. init-sweep + passieve monitor kort na elkaar). Exclusieve flock op `.lock` is ruim voldoende.

---

## 4. Architectuur (component-diagram)

```
                ┌──────────────────────────────────────────────────────┐
                │                   ipbuilding-gateway                 │
                │                                                      │
  POST /disc.   │   ┌────────────────┐    ┌──────────────────────────┐  │
  ────────────► │   │ DiscoveryState │◄───┤ gateway/auto_discovery.py│  │
  WS disc. msg  │   │ (dataclass)    │    │   - ArpMonitor           │  │
                │   └────────────────┘    │   - DiscoveryOrchestrator│  │
                │           │             │   - AtomicWriter         │  │
                │           ▼             └──────────┬───────────────┘  │
                │   ┌────────────────┐               │                  │
                │   │ Installation-  │◄──────────────┤                  │
                │   │ Config (in-mem │                │                  │
                │   │  + reload)     │                │                  │
                │   └───────┬────────┘                │                  │
                │           │                         │                  │
                │           ▼                         ▼                  │
                │   ┌────────────────┐      ┌──────────────────────┐    │
                │   │  devices.json  │      │ gateway/discovery.py │    │
                │   │  (atomic w/lock)│     │   parse_arp_table()  │    │
                │   └────────────────┘      │   discover_modules() │    │
                │                            └──────────────────────┘    │
                │                                    │                  │
                │                                    ▼                  │
                │                          ┌──────────────────────┐    │
                │                          │ ModuleMetadataCache  │    │
                │                          │ (HTTP getSysSet)     │    │
                │                          └──────────────────────┘    │
                └──────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                ┌──────────────────────────┐
                                │ WebSocket broadcast:     │
                                │  - device_added          │
                                │  - device_removed        │
                                │  - device_ip_changed     │
                                │  - device_firmware_changed│
                                └──────────────────────────┘
```

**Nieuwe module:** `gateway/auto_discovery.py` — bevat `ArpMonitor` (passieve polling-loop) en `DiscoveryOrchestrator` (roept `gateway.discovery.discover_modules` aan en schrijft resultaten via `AtomicWriter`).

**Geen wijzigingen aan:** `gateway/udp_bus.py`, `gateway/device_registry.py`, `gateway/udp_listener`. De auto-discovery levert **alleen** discovery-events; bestaande runtime-paden worden met rust gelaten.

---

## 5. Componenten

### 5.1 `gateway/auto_discovery.py` (nieuw)

| Klasse / functie | Verantwoordelijkheid |
|------------------|---------------------|
| `ArpMonitor` | Periodiek ARP-tabel lezen, diff berekenen t.o.v. vorig snapshot, events emittten |
| `DiscoveryOrchestrator` | Coördineert: roept `gateway.discovery.discover_modules` aan, schrijft `devices.json` via `AtomicWriter`, broadcast WS-events |
| `AtomicWriter` | `tempfile` + `os.replace` + `fcntl.flock` wrapper |
| `DiscoveryConfig` | Dataclass met `subnet`, `range_start`, `range_end`, `arp_poll_interval_s`, `passive_arp_monitor`, `auto_discover_on_start`, `http_timeout` |
| `DiscoveryState` | Runtime-only dataclass met `last_seen_at: datetime`, `last_seen_source: str` per module-MAC (Shelly-pattern) |

### 5.2 `ModuleConfig` (uitbreiding in `gateway/installation.py`)

Twee nieuwe velden op `ModuleConfig` (geen breaking change — defaults leeg):

```python
last_seen: datetime | None = None
last_seen_source: str = ""  # "arp" | "http" | "udp" | ""
```

Worden **niet** geperst in `devices.json` (runtime-only). Serialisatie/deserialisatie laat ze weg.

### 5.3 Nieuwe dataclass `DiscoveryState`

```python
@dataclass
class DiscoveryState:
    last_seen_at: datetime | None = None
    last_seen_source: str = ""  # "arp" | "http" | "udp"
    is_reachable: bool = True
    consecutive_misses: int = 0  # # polls without ARP hit
```

Lijst: `dict[mac_normalised, DiscoveryState]`. **Apart** van `InstallationConfig`; leeft naast `DeviceRegistry` in `main.py`.

### 5.4 Event payloads (WS)

| Type | Wanneer | Velden |
|------|---------|--------|
| `device_added` | Nieuwe module gevonden door init of passieve monitor | `id` (MAC), `ip`, `type`, `model`, `firmware`, `mac` |
| `device_removed` | Module N polls niet gezien (N=3 default) | `id` (MAC), `last_seen` |
| `device_ip_changed` | DHCP-wijziging gedetecteerd (ARP-hit op ander IP voor bekende MAC) | `id` (MAC), `old_ip`, `new_ip` |
| `device_firmware_changed` | `firmware` verschilt van `devices.json` na identify | `id` (MAC), `old_firmware`, `new_firmware` |
| `discovery_completed` | Na `POST /api/v1/discover` of init-sweep | `added: [mac…]`, `changed: [mac…]`, `removed: [mac…]`, `duration_ms: int` |

Velden zijn bewust compact; clients doen een `GET /api/v1/modules` voor details.

---

## 6. Data flow

### 6.1 Startup — `run_gateway()` in `main.py`

```
1. GatewayConfig.from_env() — leest devices.json
2. Bestaat devices.json OF bevat het ≥1 module?
   ├─ NEE → trigger init ARP-sweep (zie 6.2); geen runtime registry nog
   └─ JA → laad InstallationConfig zoals nu
3. Bouw DeviceRegistry, registreer modules
4. Bouw ModuleMetadataCache (prefetch)
5. Bouw GatewayAPI
6. NIEUW: Bouw DiscoveryOrchestrator(config, installation, registry, api)
7. NIEUW: orchestrator.start() → ArpMonitor begint passieve loop
8. await stop_event
```

### 6.2 Init ARP-sweep (eenmalig bij lege config)

```
1. orchestrator._initial_sweep()
2.   arp_candidates = await sweep_arp_range(subnet, range, ...)
3.   identified = await asyncio.gather(*[
4.       http_identify_module(c.ip, timeout=http_timeout) for c in arp_candidates
5.   ])
6.   modules = [DiscoveredModule(...) for c, i in zip(arp_candidates, identified) if i]
7.   draft = build_devices_json_draft(modules)
8.   atomic_write(devices_file, draft)  # LOCK_EX
9.   installation.reload()               # herlaad in-memory indices
10.  registry.register_module(...)
11.  broadcast({type: "discovery_completed", added: [mac…]})
```

Fouten worden gelogd maar blokkeren de gateway-start **niet** — als init faalt blijft de gateway draaien zonder modules en kan de gebruiker `/api/v1/discover` aanroepen.

### 6.3 Runtime — passieve ARP-monitor

```
elke arp_poll_interval_s (default 30):
1. arp_table = read_arp_table(subnet)         # /proc/net/arp of arp -an
2. previous = self._last_snapshot
3. current = {mac: ip for (ip, mac) in arp_table if is_field_module_mac(mac)}
4. for each (mac, ip) in current not in previous → device_added (new MAC) of device_ip_changed
5. for each (mac, ip) in previous not in current → state[m].consecutive_misses += 1
                                                          if >= 3 → device_removed
6. for each unchanged → state[m].last_seen_at = now; last_seen_source = "arp"
7. self._last_snapshot = current
8. # Geen write naar devices.json hier — alleen runtime-state + WS-events
```

### 6.4 Runtime — HTTP identify na ARP-detectie

Wanneer de ARP-monitor een **nieuwe** MAC ziet (of een IP-wijziging):

```
async def _http_identify(mac, ip):
    module = await http_identify_module(ip, timeout=config.http_timeout)
    if module is None: log warning; return
    # module.mac is al bekend (komt uit ARP)
    # Type/firmware worden opgehaald
    if not installation.module_by_mac(mac):
        # nieuwe module → append
        AtomicWriter.add_module(devices_file, module)
        installation.reload()
        broadcast({type: "device_added", ...})
    else:
        existing = installation.module_by_mac(mac)
        if existing.firmware != module.firmware:
            AtomicWriter.update_firmware(devices_file, mac, module.firmware)
            installation.reload()
            broadcast({type: "device_firmware_changed", ...})
        # IP-wijziging: enkel in runtime-registry, geen devices.json-write
        if existing.ip != module.ip:
            runtime_state[mac].ip = module.ip
            broadcast({type: "device_ip_changed", ...})
```

### 6.5 Geforceerde discovery (`POST /api/v1/discover`)

```
1. POST /api/v1/discover → orchestrator.run_forced_discovery()
2. modules = await discover_modules(subnet, range, arp_first=True)
3. for each discovered module:
     a. mac = module.mac
     b. if not installation.module_by_mac(mac):
          AtomicWriter.add_module(devices_file, module)
     c. else:
          # IP-change / firmware-change pad zoals in 6.4
4. installation.reload()
5. broadcast({type: "discovery_completed", ...})
6. return {ok: true, added: [...], changed: [...], removed: [...]}
```

Idempotent: een module die al bekend is wordt niet dubbel toegevoegd. Geen mac/IP-conflicttolerantie op dit niveau — dubbele MAC is een config-fout en wordt door `InstallationConfig._parse` al geweigerd.

### 6.6 IP-range change door gebruiker

Geen auto-re-sweep. De gebruiker moet ofwel:

- `devices.json` wissen en herstarten (init-trigger), of
- `POST /api/v1/discover` aanroepen (forced).

**Edge case:** als `hub_ip` buiten `discovery_subnet` ligt, logt de gateway bij start:

```
WARNING: hub_ip 10.10.2.1 is outside discovery_subnet 10.10.1.0/24
         — ARP-monitor zal deze module niet vinden.
```

Geen auto-actie (user-explicit per designbeslissing).

---

## 7. Error handling

| Scenario | Gedrag |
|----------|--------|
| `/proc/net/arp` niet leesbaar (Linux perm) | Eén poll overslaan, log WARNING, doorgaan. Na 3 opeenvolgende missers log ERROR. Geen crash. |
| `arp -an` faalt op macOS | Idem; sub-process error wordt opgevangen door `parse_arp_table`. |
| `AtomicWriter` lock kan niet verworven worden (`.lock` in gebruik) | Wacht max 5 s met retry; daarna ERROR log + sla de write over. Volgende poll probeert opnieuw. Geen dataverlies want de oude `devices.json` blijft staan. |
| `devices.json` corrupt geraakt tijdens atomic write (bv. disk vol tijdens `fsync`) | De `.tmp` blijft achter; `os.replace` is atomair dus de oude file is intact. Volgende init probeert het opnieuw. |
| Init-sweep levert 0 modules | Gateway draait door zonder modules; WARNING log; `discovery_completed` event met `added: []`. |
| HTTP `getSysSet` time-out tijdens init of forced | Module wordt in `devices.json` opgenomen met `firmware: ""` en `model: ""`; latere identify kan dit aanvullen. |
| Dubbele MAC in `devices.json` (split-brain na hand-edit) | `InstallationConfig._parse` weigert al; gateway valt terug op env-defaults (waarschuwing in `config.py`). |
| `hub_ip` buiten `discovery_subnet` | Eén WARNING bij start; geen verdere actie. |
| Companion op ander netwerk (geen fieldbus-zicht) | Geen impact — companion is alleen WS/REST-client. Discovery is gateway-zijde. |

**Locking-strategie:**

- `AtomicWriter` opent `<file>.lock` met `O_CREAT | O_RDWR`, doet `fcntl.flock(fd, LOCK_EX)`.
- Timeout 15 s; daarna exceptie.
- De runtime-registry gebruikt **geen** file-lock (in-memory asyncio.Lock is voldoende).

---

## 8. Testing strategy

### 8.1 Unit tests (nieuw bestand: `tests/test_auto_discovery.py`)

- **`ArpMonitor.test_read_arp_table_linux_fixture`** — virtuele `/proc/net/arp` via `tmp_path`; monkeypatch `open` om het fixture te lezen. Verifieer `(ip, mac)` paren.
- **`ArpMonitor.test_read_arp_table_darwin_fallback`** — mock `subprocess.check_output` met fake `arp -an` output. Verifieer macOS-pad.
- **`ArpMonitor.test_diff_new_module_emits_event`** — eerste snapshot leeg, tweede snapshot bevat 1 nieuwe MAC; verifieer `device_added` event.
- **`ArpMonitor.test_diff_removed_after_n_misses`** — module 3 polls niet gezien → `device_removed` event.
- **`ArpMonitor.test_diff_ip_change_emits_event`** — zelfde MAC, ander IP tussen 2 polls → `device_ip_changed` event.
- **`DiscoveryOrchestrator.test_init_sweep_writes_devices_json`** — mock `sweep_arp_range` + `http_identify_module`; verifieer dat `AtomicWriter` is aangeroepen met de juiste dict.
- **`DiscoveryOrchestrator.test_init_sweep_idempotent`** — bestaande `devices.json` met 1 module; init-sweep vindt dezelfde module; geen duplicaat, geen firmware-write (firmware ongewijzigd).
- **`DiscoveryOrchestrator.test_forced_discovery_returns_summary`** — aanroep van `run_forced_discovery()` met mock-discoverers; verifieer return shape `{added, changed, removed, duration_ms}`.
- **`AtomicWriter.test_atomic_write_replaces_file`** — happy path; verifieer dat `.tmp` niet achterblijft.
- **`AtomicWriter.test_atomic_write_lock_contention`** — tweede writer met `LOCK_EX | LOCK_NB` krijgt `BlockingIOError`; AtomicWriter logt en skip.
- **`AtomicWriter.test_corrupt_tmp_does_not_affect_existing`** — force `OSError` tijdens fsync; verifieer dat originele `devices.json` intact is.
- **`DiscoveryState.test_shelly_pattern_fields`** — module zonder `last_seen` krijgt default; na eerste ARP-hit wordt `last_seen_at` gezet en `last_seen_source = "arp"`.

### 8.2 Integratietest (uitbreiding `tests/test_gateway_api_modules.py`)

- **`test_post_discover_endpoint`** — start `GatewayAPI` met mock `DiscoveryOrchestrator`; `POST /api/v1/discover`; verifieer response shape.
- **`test_post_discover_emits_ws_event`** — open WS-connectie; roep `POST /api/v1/discover` aan; verifieer dat WS-client het `discovery_completed` event ontvangt.
- **`test_ws_discover_message`** — verstuur `{"type": "discover"}` over WS; verwacht zelfde gedrag als REST.

### 8.3 Regressie

Bestaande **155 tests** moeten ongewijzigd blijven passeren. Geen wijzigingen aan `gateway/installation.py`-parsing van `ModuleConfig` (alleen twee nieuwe optionele velden met defaults). `DeviceRegistry`, `UDPBus`, `gateway_api.py`-core paden onaangeraakt.

Specifiek te verifiëren:

- `tests/test_installation.py` — `ModuleConfig`-defaults bevatten `last_seen=None, last_seen_source=""` zonder impact.
- `tests/test_discovery.py` — `parse_arp_table` blijft ongewijzigd.
- `tests/test_gateway_api.py` + `test_gateway_api_modules.py` — geen router-wijzigingen buiten `POST /api/v1/discover`.

---

## 9. Configuration changes

### 9.1 `ipbuilding_gateway/config.yaml` (HA add-on schema)

Nieuwe opties onder `options:` (defaults geven backwards-compatible gedrag):

```yaml
options:
  hub_ip: 10.10.1.1
  poll_interval: 2.0
  api_port: 8080
  rest_shim_enabled: false
  log_level: info
  devices_file: /data/devices.json
  # NIEUW — runtime auto-discovery
  discovery_subnet: 10.10.1          # eerste 3 octetten
  discovery_range_start: 0           # default 0 ipv 30; ARP-sweep over hele /24 indien geactiveerd
  discovery_range_end: 254
  auto_discover_on_start: false      # expliciet false; init-trigger doet het alsnog bij lege config
  passive_arp_monitor: true          # default aan
  arp_poll_interval_s: 30            # default 30 s
  http_timeout_s: 2.0                # identify timeout

schema:
  hub_ip: str
  poll_interval: float
  api_port: port
  rest_shim_enabled: bool
  log_level: list(debug|info|warning|error)
  devices_file: str
  discovery_subnet: str
  discovery_range_start: int(0,254)
  discovery_range_end: int(0,254)
  auto_discover_on_start: bool
  passive_arp_monitor: bool
  arp_poll_interval_s: int(5,3600)
  http_timeout_s: float
```

### 9.2 `ipbuilding_gateway/run.sh` (env-vars)

Vertaalslag `options.json` → env-vars. `GATEWAY_AUTO_DISCOVER` (vandaag dode `0`) wordt vervangen door `GATEWAY_AUTO_DISCOVER_ON_START`; de andere velden krijgen eigen `GATEWAY_DISCOVERY_*` env-vars.

```bash
export GATEWAY_DISCOVERY_SUBNET
GATEWAY_DISCOVERY_SUBNET=$(json_str_or "discovery_subnet" "10.10.1")

export GATEWAY_DISCOVERY_RANGE_START
GATEWAY_DISCOVERY_RANGE_START=$(json_int_or "discovery_range_start" "0")

export GATEWAY_DISCOVERY_RANGE_END
GATEWAY_DISCOVERY_RANGE_END=$(json_int_or "discovery_range_end" "254")

export GATEWAY_AUTO_DISCOVER_ON_START
GATEWAY_AUTO_DISCOVER_ON_START=$(json_bool "auto_discover_on_start")

export GATEWAY_PASSIVE_ARP_MONITOR
GATEWAY_PASSIVE_ARP_MONITOR=$(json_bool "passive_arp_monitor")

export GATEWAY_ARP_POLL_INTERVAL_S
GATEWAY_ARP_POLL_INTERVAL_S=$(json_int_or "arp_poll_interval_s" "30")

export GATEWAY_DISCOVERY_HTTP_TIMEOUT
GATEWAY_DISCOVERY_HTTP_TIMEOUT=$(json_str_or "http_timeout_s" "2.0")
```

### 9.3 `gateway/config.py`

`GatewayConfig` krijgt een geneste `DiscoveryConfig`-dataclass (zie §5.1) met `from_env()`-parsing. Backwards-compat: ontbrekende env-vars → defaults uit §9.1.

**Mapping:** de `DiscoveryConfig`-velden worden in YAML en env-vars **flat** geëxposeerd (omdat HA Supervisor's options.json en `os.environ` geen geneste keys ondersteunen). `DiscoveryConfig.from_env()` leest alle `GATEWAY_DISCOVERY_*` en `GATEWAY_AUTO_DISCOVER_ON_START` env-vars en groepeert ze in de dataclass.

---

## 10. WebSocket / REST API additions

### 10.1 Nieuwe REST endpoint

| Methode | Pad | Doel | Response |
|---------|-----|------|----------|
| `POST` | `/api/v1/discover` | Geforceerde discovery (companion of operator) | `{"ok": true, "added": [mac…], "changed": [mac…], "removed": [mac…], "duration_ms": 1234}` |

`added`/`changed`/`removed` zijn lijsten van MAC-strings. Voor details kan de client `GET /api/v1/modules` opnieuw aanroepen.

**Edge case:** discovery duurt typisch 5–30 s (HTTP identify). De endpoint blokkeert tot klaar; geen async-job.

### 10.2 Nieuwe WS-events (gateway → client)

| Type | Velden |
|------|--------|
| `device_added` | `id` (MAC), `ip`, `type`, `model`, `firmware`, `mac` |
| `device_removed` | `id` (MAC), `last_seen` (ISO 8601 of null) |
| `device_ip_changed` | `id` (MAC), `old_ip`, `new_ip` |
| `device_firmware_changed` | `id` (MAC), `old_firmware`, `new_firmware` |
| `discovery_completed` | `added: [mac…]`, `changed: [mac…]`, `removed: [mac…]`, `duration_ms: int`, `trigger: "init" \| "passive" \| "forced"` |

Alle events zijn **fire-and-forget**; geen ack van client verwacht. Sequence numbering wordt **niet** toegevoegd in v1 (kan later).

### 10.3 Nieuwe WS-bericht (client → gateway)

| Type | Velden | Effect |
|------|--------|--------|
| `discover` | (geen) | Idem aan `POST /api/v1/discover`; antwoord komt als `discovery_completed` event. |

### 10.4 Snapshot-uitbreiding

`/ws` snapshot voegt toe aan `modules[]` (per module):

```json
{
  "id": "00:24:77:52:ac:be",
  ...,
  "last_seen": "2026-06-04T18:00:00Z",
  "last_seen_source": "arp",
  "is_reachable": true
}
```

Runtime-only; niet in `devices.json` geperst.

---

## 11. Companion impact (`ipbuilding-gateway-ha`) — **separate workstream**

De companion hoeft voor deze iteratie **niets** te doen om correct te blijven draaien. Optioneel kan hij wel reageren op de nieuwe events:

| Event | Companion-actie (optioneel, v2) |
|-------|----------------------------------|
| `device_added` | Nieuwe HA-entity aanmaken met `active: false` (default uit config); notify via persistent notification "New module discovered: <name> — please configure" |
| `device_removed` | HA-entity `unavailable` markeren (niet verwijderen — user kan ze herstellen) |
| `device_ip_changed` | Entity-ID up-to-date houden; optioneel: rename in HA als IP in entity-ID zat (doorgaans niet, want entity-ID = `module_ip-channel`) |
| `device_firmware_changed` | Attribuut `firmware` op device updaten |

**Nieuwe service(s) in v2 (optioneel, niet in scope hier):**

- `ipbuilding.discover` — wrapper rond `POST /api/v1/discover`, voor HA-automations / dashboard-knop.

**Nieuwe entities in v2 (optioneel):**

- `binary_sensor.ipbuilding_discovery_active` (monitor-loopt of niet)

Deze impact wordt in een aparte iteratie na deze spec uitgewerkt.

---

## 12. Resolved (2026-06-04)

Tijdens het ontwerp zijn de volgende punten naar boven gekomen en zijn **resolved op 2026-06-04**:

| # | Vraag | Antwoord |
|---|-------|----------|
| 1 | discovery_range_start default | 0 (volledige /24 sweep bij init) |
| 2 | N polls voor "removed" | 3 (~90 s bij 30 s interval) |
| 3 | hub_ip buiten discovery_subnet policy | WARNING-only, geen auto-actie |
| 4 | Lock-timeout AtomicWriter | 15 s (RPi SD-kaart robuust) |
| 5 | HTTP getSysSet voor bestaande modules tijdens passieve monitor | Nee — backlog-item |
| 6 | GATEWAY_AUTO_DISCOVER env-var | Verwijderen (geen alias, breaking change) |

Design goedgekeurd door Mark Minnoye, 2026-06-04.

---

## 13. Wijzigingen per bestand (samenvatting)

| Bestand | Wijziging | Risico |
|---------|-----------|--------|
| `gateway/auto_discovery.py` | **Nieuw** — `ArpMonitor`, `DiscoveryOrchestrator`, `AtomicWriter`, `DiscoveryConfig`, `DiscoveryState` | Laag — puur nieuw |
| `gateway/installation.py` | `ModuleConfig` + 2 velden (`last_seen`, `last_seen_source`) met defaults; serialisatie laat ze weg | Laag — additief, defaults veilig |
| `gateway/config.py` | `DiscoveryConfig` (nested in `GatewayConfig`); `from_env()` leest `GATEWAY_DISCOVERY_*` | Laag — additief |
| `gateway/gateway_api.py` | Router: `POST /api/v1/discover`; WS: nieuwe event-types; `_build_module_list` voegt `last_seen*` toe | Medium — uitbreiding; tests verifiëren |
| `gateway/main.py` | `DiscoveryOrchestrator` start na `GatewayAPI`; `orchestrator.stop()` in `finally` | Laag |
| `ipbuilding_gateway/run.sh` | 7 nieuwe env-vars vertaalslag | Laag |
| `ipbuilding_gateway/config.yaml` | 7 nieuwe options + 7 nieuwe schema-regels | Laag |
| `ipbuilding_gateway/DOCS.md` | Tabel met nieuwe opties + nieuwe endpoint docs | Laag |
| `ARCHITECTURE.md` | §4.1 uitbreiden met runtime-monitor + write-policy | Laag — docs |
| `tests/test_auto_discovery.py` | **Nieuw** — 12+ unit tests | — |
| `tests/test_gateway_api_modules.py` | Uitbreiding — 3 integratietests | Laag |
| `docs/api/rest.md` | `POST /api/v1/discover` toevoegen | Laag |
| `docs/api/websocket.md` | 5 nieuwe event-types + `discover` client-bericht | Laag |

**Buiten scope (expliciet):**

- Companion `ipbuilding-gateway-ha` aanpassingen (v2-workstream).
- Periodieke 24h ARP-sweep (backlog).
- Netlink / `pyroute2` event-stream (backlog, alleen als 30 s polling onvoldoende blijkt).
- DHCP-server-API (we lezen enkel, schrijven niet naar de module).

---

## 14. Validatie

```bash
# Unit
PYTHONPATH=. pytest tests/test_auto_discovery.py -v

# Integratie (bestaand + nieuw)
PYTHONPATH=. pytest tests/test_gateway_api_modules.py -v

# Volledige regressie (155 tests)
PYTHONPATH=. pytest -q

# Manual: start gateway met lege devices.json
rm /data/devices.json
python3 -m gateway
# Verwacht: log "init ARP-sweep starting"; daarna devices.json gevuld;
#          WS-snapshot bevat modules met last_seen + last_seen_source.

# Manual: forced discovery
curl -X POST http://localhost:8080/api/v1/discover
# Verwacht: JSON met added/changed/removed.

# Manual: WS event observer
python3 -c "
import asyncio, aiohttp, json
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect('http://localhost:8080/ws') as ws:
            async for msg in ws:
                print(msg.json())
asyncio.run(main())
"
# Toggle een module aan/uit; verwacht device_added/removed events.
```

**Acceptance criteria:**

1. Init-sweep bij lege `devices.json` vult het bestand met `active: false, room: "Unconfigured"`.
2. Passieve monitor detecteert een nieuwe module binnen `2 × arp_poll_interval_s` (default 60 s) en emit `device_added` over WS.
3. DHCP-IP-wijziging van een bekende module emit `device_ip_changed` zonder `devices.json` te wijzigen.
4. Firmware-wijziging van een bekende module updatet `devices.json` (één regel) en emit `device_firmware_changed`.
5. `POST /api/v1/discover` werkt ongeacht de toggles `passive_arp_monitor` / `auto_discover_on_start`.
6. Alle 155+ bestaande tests blijven groen.
7. Geen `devices.json`-write gebeurt zonder LOCK_EX op `.lock`.

---

## 15. Niet in scope (herhaling)

- Companion (`ipbuilding-gateway-ha`) — aparte workstream.
- Periodieke 24h ARP-sweep.
- Netlink event-stream.
- Auto-configureren van `name`/`room` op discovery (user-explicit via companion).
- ESP32 (Deployment C) — andere implementatie, niet geraakt door deze spec.
- REST shim `:30200` (apart traject, aan het uitfaseren).
