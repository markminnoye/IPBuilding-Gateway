# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Versiebeleid

De IPBuilding Gateway add-on en de `ipbuilding-gateway-ha` companion
volgen **onafhankelijk semver**. Een bump in de ene repo betekent
niet automatisch een bump in de andere.

- **Patch (0.3.x)**: cosmetisch, geen impact op de REST/WS wire.
  Werkt met alle companion-versies die de huidige wire ondersteunen.
- **Minor (0.x.0)**: nieuwe REST endpoints of optionele velden in
  bestaande responses. De oude companion blijft werken, maar ziet
  de nieuwe velden niet.
- **Major (x.0.0)**: breaking change. De gateway- of companion-CHANGELOG
  bevat dan een `### Breaking:` entry die de incompatibele combinaties
  opsomt.

Backward compatibiliteit is de norm — een versie in deze add-on
blijft werken met de huidige companion tot een `### Breaking:`-regel
anders meldt.

## [1.2.4] - 2026-07-01

### Added
- **`README.md` in de add-on folder** — korte About-sectie in de Supervisor UI (store en add-on info), met duidelijke melding dat de **IPBuilding Gateway** companion verplicht is voor HA-entiteiten en een HACS-installatielink via my.home-assistant.io.

## [1.2.3] - 2026-07-01

### Fixed
- **Add-on store-validatie hersteld.** De `watchdog`-URL in `config.yaml` gebruikte per ongeluk `http://[HOST]:[PORT]/health`. De Supervisor verwacht `http://[HOST]:[PORT:8080]/health` (interne containerpoort). Daardoor kon de add-on na een store-refresh verdwijnen uit de catalogus met fouten als *"does not exist in the store"* of *"has no source location"*.

## [1.2.2] - 2026-06-30

### Changed
- **Env-default UDP poll targets (`.30/.40/.50`) zijn niet langer stille fallback** wanneer `devices.json` ontbreekt of ongeldig is. Productie-installaties starten zonder UDP-polling tot discovery `devices.json` vult. Lab/RE: zet add-on optie `use_env_defaults` aan of `GATEWAY_USE_ENV_DEFAULTS=1`; `GATEWAY_SIMULATED=1` gedraagt zich zoals voorheen.
- **Init-sweep bij ongeldig `devices.json`** — parse/validatiefouten (bijv. `type: unknown`) triggeren nu dezelfde startup-sweep als een ontbrekend bestand.
- **Discovery schrijft geen `type: unknown` meer naar `devices.json`.** Ongeïdentificeerde modules (ARP-only of HTTP zonder herkenbare `refNr`) verschijnen via WebSocket `device_added` en in `skipped_unidentified` op `POST /api/v1/discover`, maar blokkeren de loader niet meer. Init-sweep wist een ongeldig bestand naar `{"modules":[]}`.

### Added
- **Diagnostische discovery-logging** — HTTP-identify fouten, onopgeloste moduletypes en `devices.json` reload-fouten verschijnen in de add-on logs.
- **Health issue `installation.load_failed`** wanneer `devices.json` bestaat maar niet geladen kan worden.
- **`refNr`/productnaam prefix-fallback** — varianten zoals `ip0200poe` of `IP0300…` worden herkend als relay/dimmer/input.

## [1.2.1] - 2026-06-23

### Fixed
- **Meer fysieke knoppen worden herkend.** Sommige IP1100PoE-knoppen sturen een ander
  event-type op de veldbus dan de eerder gedocumenteerde variant. De gateway negeerde
  die drukken volledig; ze worden nu als normale press/release doorgegeven aan Home
  Assistant.

## [1.2.0] - 2026-06-23

### Added
- **Downstream `T` / `D` dimmer commands.** `gateway/payloads/dimmer.py` exposes `encode_dim_toggle(channel)`, `encode_dim_start(channel)`, `encode_dim_stop(channel)` for the button/ramp wire dialect (`T<ch>991000`, `D<ch>001003`, `D<ch>001000`). `gateway_api._execute_command` dispatches `TOGGLE`, `DIM_START`, `DIM_STOP` actions on dimmer channels; `TOGGLE` and `DIM_STOP` track the channel for the channel-less reply, `DIM_START` is fire-and-forget. The companion's `button_dim` blueprint (v8) uses these to drive a native ramp instead of the old `brightness_step_pct` loop. Wire-bytes match `resources_and_docs/evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md`. Companion `ha-ipbuilding-gateway` ≥ **1.7.0** consumes the new gateway actions via `ha_ipbuilding_gateway.dim_start` / `dim_stop`.

## [1.1.1] - 2026-06-22

### Fixed
- `single_press` wordt niet meer dubbel uitgestuurd wanneer een duplicate of
  wees-release frame binnenkomt (geen actief ingedrukte knop). Alleen echte
  korte indrukken genereren een `single_press`; overtollige release-frames
  leiden nog uitsluitend tot een `released` event. Voorkomt ongewenste dubbele
  schakelacties bij gebruik met HA-automations.

## [1.1.0] - 2026-06-21

### Added
- Buttons emit a new `single_press` event on the WebSocket when a press is
  released without crossing the long-press threshold. The raw `pressed`/
  `released` edges and `long_press` are unchanged. `single_press` is only
  synthesised for a real short press — a release with no active press
  (duplicate or orphan release frame) forwards just the raw `release`.
  Companion ≥ 1.3.0 maps this to the HA-standard `press_end`.

## [1.0.4] - 2026-06-19

### Added
- **Discovery TXT record schema v2.** `_build_txt_properties` zendt nu expliciet `host`, `port`, `sw` (alias van `version`) en `mac` naast de bestaande velden. Companion v1.2.2+ gebruikt deze velden om meerdere gateways van elkaar te onderscheiden.
- **`instance_id` in HassIO discovery payload.** De Supervisor `/supervisor/discovery` POST bevat nu `instance_id` in `config`, zodat de companion dezelfde unieke ID kan gebruiken als voor zeroconf discovery.

## [1.0.3] - 2026-06-19

### Removed
- **Tijdelijke fb376d debug-file logging uit HassIO discovery.** De `_start_hassio` en `_hassio_announce_once` methodes schreven tijdens de diagnose van het 1.0.1 discovery-probleem gestructureerde events naar `/config/debug-fb376d.log`. Die zijn niet meer nodig; de reguliere `HassIO discovery announced: uuid=…` info-log en waarschuwingen op POST-fouten blijven.

### Changed
- `ipbuilding_gateway/config.yaml` `options:` en `schema:` secties in dezelfde volgorde gezet (Network / API → Hub / field bus → Discovery → Logging). Cosmetisch; geen impact op wire, defaults of schema-validatie.

## [1.0.2] - 2026-06-19

### Added
- **Diagnostische logging** bij Supervisor discovery-registratie bij opstarten, zodat te verifiëren is of de gateway correct wordt aangeboden aan Home Assistant.

## [1.0.1] - 2026-06-19

### Fixed
- **Add-on verschijnt nu automatisch in Home Assistant → Devices & Services → Discovered** wanneer de companion geïnstalleerd is. De HassIO-discovery-call naar `http://supervisor/discovery` werd door Supervisor geweigerd omdat de add-on de `hassio_api` permissie miste; daardoor kreeg de add-on geen `SUPERVISOR_TOKEN` en werd de discovery-stap in stilte overgeslagen. De `discovery:` service key (`ha_ipbuilding_gateway`) was al aanwezig; alleen de permissie ontbrak. Geen wijziging aan de REST/WS wire of `devices.json`.

## [1.0.0] - 2026-06-19

### Breaking
- **HA integration domain hernoemd** van `ipbuilding_gateway_ha` naar `ha_ipbuilding_gateway`, in lockstep met companion `ha-ipbuilding-gateway` v1.0.0. De add-on `discovery:` key, `gateway/ha_discovery.py` service-payload en `scripts/import_ipbox_to_ha.py` event types gebruiken nu overal de nieuwe domeinnaam. **Oudere add-on versies (< 1.0.0) blijven werken met de oude `ipbuilding_gateway_ha` discovery key**; de nieuwe add-on + nieuwe companion (≥ 1.0.0) gebruiken de nieuwe. Het oude/nieuwe-paar is incompatibel als de versies uit sync zijn (oude add-on + nieuwe companion: Supervisor discovery faalt, handmatige config-flow werkt nog; nieuwe add-on + oude companion: Supervisor discovery faalt). **Geen impact** op REST/WS wire-format of `devices.json`. Operators die de Supervisor discovery gebruiken: update add-on en companion in dezelfde HA-sessie.

### Removed
- **Runtime endpoint `POST /api/v1/debug/fieldbus-polling`** en het bijbehorende `fieldbus` blok uit `/api/v1/status` (`polling_enabled`, `poll_interval_s`). De gateway heeft geen runtime-toggle voor de field-bus polling meer; de companion `Fieldbus polling (debug)` switch is eveneens verwijderd.

### Notes
- **Versiebeleid wijziging** — de add-on bereikt `1.0.0` bij deze breaking rename. Hierna volgt de add-on onafhankelijk semver van de companion: patch-level bumps in één repo betekenen niet automatisch een bump in de andere. Backward compatibiliteit blijft de norm tot een `### Breaking:` regel anders meldt.

## [0.4.3] - 2026-06-18

### Fixed
- **Correcte lichtstatus direct na een herstart.** Vóór deze versie toonde Home Assistant alle lampen als "uit" tot de eerste UDP-commando binnenkwam — de gateway had nog geen idee van de echte kanaalstand. Bij het opstarten haalt de gateway nu de live kanaalstatus op van elke relay- en dimmermodule via hun ingebouwde webinterface, zodat de eerste snapshot in Home Assistant direct de juiste aan/uit-stand laat zien. Dimmers die nog geen status hebben gerapporteerd tonen nu "Onbekend" in plaats van "uit", en inactieve kanalen worden correct als uitgeschakeld gemarkeerd.

## [0.4.2] - 2026-06-18

### Added
- **Debug toggle for the field-bus polling loop.** New endpoint `POST /api/v1/debug/fieldbus-polling` lets an operator stop the periodic UDP/1001 keep-alive polls at runtime (without restarting the bus). The poll loop keeps running on its normal cadence, so flipping the flag back on resumes polling almost immediately. The status payload now reports a top-level `fieldbus` block with the current `polling_enabled` and `poll_interval_s`, and the `fieldbus` subsystem goes to `degraded` while polling is off — surfaced as a `fieldbus.polling_disabled` warning in `/api/v1/status`. **Requires companion v0.4.2+** to expose the matching "Veldbus polling (debug)" switch in Home Assistant; older companions ignore the new endpoint.

### Changed
- **Classified button events appear in the add-on log.** `press`, `long_press` and `release` are now logged at INFO level (`gateway.gateway_api BUTTON <id>: <action>`) on the moment they are broadcast over WebSocket. Wire-level edges stay visible via `gateway.device_registry`. No new REST endpoint, no wire change.

## [0.4.1] - 2026-06-18

### Fixed
- **Fresh add-on installs now auto-populate `devices.json` on first start**, even when `auto_discover_on_start` is off. Modules and channels appear in the companion without a manual discovery sweep.

## [0.4.0] - 2026-06-17

### Added
- **Long press on IP1100PoE wall switches.** The gateway measures how long a physical button stays pressed and broadcasts a `long_press` event over WebSocket as soon as the threshold is reached (default 1.5 s — the same value as IPBox `holdSeconds`). Short presses remain `press`; releasing sends `release`. **Requires companion v0.4.0+** to use long press in Home Assistant.
- **Button metadata read from the module itself.** On startup and discovery, the gateway reads `getButtons` from IP1100PoE modules and fills in the button name, room and hold threshold. This metadata is surfaced through `/api/v1/devices` and the WebSocket snapshot.
- **IPBox → Home Assistant import script.** New utility `scripts/import_ipbox_to_ha.py` (run on your workstation, not inside the add-on) reads IP1100PoE `getButtons` and optionally the IPBox REST `/comp/items`, then writes ready-to-import `automations.yaml`, `helpers.yaml`, `import_report.md` and `checksum.txt` for migrating button→action mappings including dim-while-hold. Idempotent: re-running with the same source is a no-op. See the cutover guide at `resources_and_docs/reference/2026-06-17_button_long_press_cutover.md`.
- **API schema version 2.** Successful REST responses and the WebSocket `snapshot` now include `schema_version: 2`. Additive — older clients ignore unknown fields.

### Changed
- **REST errors use real HTTP status codes** (400, 404, 422, 500, …) with a structured body `{"error": "<code>", "message": "...", "details": {...}}`. Custom clients that assumed HTTP 200 for every response (the old `{ok: false}` pattern) need to be updated. URL paths are unchanged.
- **Version in logs, Supervisor and `/api/v1/status`** now comes directly from `ipbuilding_gateway/config.yaml`. No more separate build stamp — what you see in Supervisor is what the gateway reports.

### Fixed
- **IP1100PoE buttons are active immediately after install.** Since 0.3.6 the gateway sent `active: false` for input buttons, forcing you to enable them by hand. That field is now intentionally absent; the companion treats absence as enabled. Buttons you deliberately disabled before stay disabled.
- **Button-ID matching is no longer case-sensitive.** Different capitalisations of the same hardware ID (e.g. from the field bus vs. getButtons) no longer cause missed events.
- **Button timers survive a gateway restart more reliably** thanks to correct asyncio-loop handling in the event callback.

### Notes
- **IPBox → open-gateway upgrade path:** install add-on v0.4.0, companion v0.4.0+, run a discovery sweep, run the import script, follow the cutover guide. Scenes and moods stay in Home Assistant — not in the gateway.
- **Companion is a separate release** (repo `ipbuilding-gateway-ha`). Long press only works when both sides are up to date.

## [0.3.8] - 2026-06-16

### Fixed
- **Init-sweep crashte op `AttributeError: 'DiscoveryOrchestrator' object has no attribute '_state'`.** De 0.3.7-fix om runtime-velden uit `devices.json` te houden introduceerde een verwijzing naar `self._state[dm.mac]` in `_run_init_sweep`, maar `_state` is een attribuut van `ArpMonitor`, niet van de orchestrator. De regel is verwijderd; `_run_init_sweep` schrijft alleen naar `devices.json` en houdt geen eigen runtime-state bij. Companion-side niets gewijzigd.

## [0.3.7] - 2026-06-16

### Fixed
- **`devices.json` blijft stabiel tussen discovery-runs.** De runtime-velden `last_seen` en `last_seen_source` werden door `auto_discovery` stiekem toegevoegd aan het weggeschreven bestand, tegen de conventie in (`ModuleConfig.to_dict()` documenteerde al "NOT serialized to devices.json"). Idem voor `ChannelConfig.to_dict()` dat het derived entity-`id` meeschreef. Drie aanroepplekken in `auto_discovery.py` zijn geschoond; `ChannelConfig.to_dict()` schrijft het `id`-veld niet meer terug. Het bestand bevat nu puur installatie-specifieke data (naam, kamer, `active`, model, MAC) en verandert niet meer bij elke `POST /api/v1/discover`.
- **Lock-bestand (`devices.json.lock`) wordt opgeruimd.** `AtomicWriter` hield een advisory lock op een `.lock`-file. Bij crash of test-onderbreking bleef die als untracked artefact in de working tree staan. `try/finally` ruimt het bestand nu altijd op, ook op exception-paden.

## [0.3.6] - 2026-06-16

### Changed
- **IP1100PoE-knoppen starten uitgeschakeld** in Home Assistant. Na discovery verschijnen ze onder niet-ingeschakelde entiteiten zodat je zelf kiest welke knoppen je activeert.

## [0.3.5] - 2026-06-16

### Changed
- **Supervisor now auto-updates the add-on** (`auto_update: true`). Future 0.3.x patch releases roll out without an operator action; the v0.3.3 image was already published but kept running v0.3.1 because this flag was off.

## [0.3.4] - 2026-06-16

### Fixed
- **`devices.json` is now saved where you can see it.** Discovery and forced scans write to `/config/devices.json`, which maps to the add-on folder under **Samba / SSH** (`addon_configs/.../devices.json`). Earlier releases wrote to the internal `/data` volume only, so the file looked missing even when discovery succeeded. Existing installs are migrated automatically on start.
- **Startup log and API version** now match the add-on version in Supervisor (single source: `config.yaml`).

### Changed
- Add-on requests **`addon_config:rw`** so the gateway can write installatieconfig next to your other add-on files.

## [0.3.3] - 2026-06-16

### Changed
- **Module names are now consistent across all three field modules.** The gateway fills in the canonical hardware SKU (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) when `devices.json` carries an empty `model` or an IP-based `name`, so the companion's onboarding "Apparaat-info" always shows the SKU as title and the role label (Relay / Dimmer / Input) as the device name. The companion also treats module IP addresses as auto-discovery placeholders and never leaks them into the operator-facing name.

## [0.3.2] - 2026-06-16

### Fixed
- **Discovery failed in the add-on container** because the slim Docker image did not include the `ping` binary used for ARP-first field-bus scans (`POST /api/v1/discover`). The image now installs `iputils-ping`.
- **Linux ping timeout** during discovery used the wrong flag/units (`-W` with milliseconds); sweeps could hang for minutes on silent hosts. Linux now uses `-w` with a seconds deadline.

## [0.3.1] - 2026-06-16

### Fixed
- **Image was missing the `zeroconf` package at runtime**, even though the source-of-truth `requirements-gateway.txt` listed it. The build context picked up a stale copy at `ipbuilding_gateway/requirements-gateway.txt` that pre-dated this release. The build was technically successful — the image just did not contain the dependency. `prepare-build.sh` now syncs the requirements file alongside `gateway/`, so the add-on copy is regenerated on every CI run.

### Notes
- **No operator action required beyond updating.** The fix only affects the build, not the gateway's runtime behaviour. After updating the add-on in Supervisor, the new image starts cleanly and all 0.3.0 features (Zeroconf broadcast, Supervisor discovery, configurable metadata timeout) work as documented.
- **Companion also bumped to 0.3.1** for lockstep versioning. The companion code itself is unchanged from 0.3.0.

## [0.3.0] - 2026-06-16

Bundle release: everything since **0.1.0** (and fixes that were only
documented under 0.1.1–0.1.4) ships in this version. Intermediate
0.1.x tags were not published as separate Docker images — upgrade
straight to **0.3.0** together with companion **v0.3.0**.

### Added
- The add-on now appears automatically in **Settings → Devices & Services → Discovered** when the companion is installed, so you can add the integration with one click instead of typing host and port.
- **Gateway health reporting:** `GET /api/v1/status` exposes overall health (`ok` / `degraded` / `unhealthy`), version, uptime, subsystem state, and plain-language issue messages. The companion can show a diagnostic status sensor and react to changes over WebSocket. The Supervisor watchdog `GET /health` uses the same health enum.
- A new add-on option **`metadata_timeout_s`** (default 5 s) for module metadata requests (`getSysSet` / `getButtons`) on slow or busy VLANs.
- Inactive channels (`active: false`) are exposed to the companion as disabled, hidden entities — enable them from **Settings → Devices & Services** when wiring is finished (introduced in 0.1.0, still part of this bundle).

### Changed
- WebSocket keep-alive interval is 60 seconds (was 30 s), so the companion stays connected quietly during normal operation.
- The add-on and companion are released in lockstep at the same version number.

### Fixed
- **First-run discovery:** devices found during the initial field-bus scan appear in Home Assistant immediately, without restarting the gateway.
- **Module metadata on startup:** the default metadata timeout is more forgiving when the gateway is also running ARP sweep and Supervisor discovery in parallel; HTTP refresh to the three modules runs in a bounded order so one module is no longer dropped on most boots.
- **mDNS discovery:** service name is now `_ipbgw._tcp.local.` (was `_ipbuilding-gateway._tcp.local.`). The old name was rejected by strict mDNS validators, so standalone gateways never appeared on the LAN for auto-detect.
- Inactive channels report state **`inactive`** instead of **`unknown`**, so you can tell “not wired yet” from “no field-bus response”.
- Clearer warnings when module metadata HTTP requests fail (empty error lines at startup are gone).
- Gateway shutdown completes cleanly even when the HTTP runner hits non-timeout errors or a slow WebSocket client is still connected.
- Commands to an inactive channel are rejected instead of driving the field bus.

### Notes
- Install **add-on v0.3.0** and **companion v0.3.0** together. Older companions still work via manual host/port, but not the new Discovered flow.
- If you are on **0.1.0** or **0.1.2** (last published 0.1.x image), this is the single upgrade step — no need to install 0.1.3 or 0.1.4 separately.

## [0.1.4] - 2026-06-16

> Included in **[0.3.0]** above.

### Fixed
- Devices discovered at startup now appear in Home Assistant immediately,
  without having to restart the gateway. Previously, after a clean install
  or a first-run field-bus scan, the device list was empty until you
  restarted the gateway.

## [0.1.3] - 2026-06-15

> Included in **[0.3.0]** above.

### Fixed
- Gateway shutdown no longer leaves the aiohttp runner in a half-initialised
  state when `runner.cleanup()` raises something other than a timeout (for
  example, an `OSError` while closing a socket). The `self._runner` and
  `self._site` references are now cleared in a `finally` block, and the
  exception is logged as a warning. Previously the uncaught exception
  would skip the registry-callback unregistration and the final
  "GatewayAPI stopped" log line.

## [0.1.2] - 2026-06-15

> Included in **[0.3.0]** above.

### Fixed
- `HTTP getSysSet` and `HTTP getButtons` warnings now include the exception
  class and a `repr()` of the exception object, so you can see **why** the
  request failed. Previously some aiohttp / `OSError` exceptions have an
  empty `str()`, which produced bare `failed:` lines with no diagnostic
  information (visible at gateway startup with no useful pointer to the
  underlying cause, e.g. container can't reach the field-bus subnet).

## [0.1.1] - 2026-06-14

> Included in **[0.3.0]** above.

### Fixed
- Inactive channels in the device list now report their state as `inactive`
  instead of `unknown`, so you can tell apart "channel not wired up yet"
  from "no recent response from the field bus" when troubleshooting.

## [0.1.0] - 2026-06-14

> Superseded by **[0.3.0]** for upgrades; kept for history.

### Added
- Channels that are wired up but not yet in use (`active: false`) are now
  reported to the companion so they appear in Home Assistant as disabled,
  hidden entities. Enable them from Settings → Devices & Services when the
  wiring is finished. Previously these channels were hidden from the API
  entirely.

### Changed
- WebSocket keep-alive interval raised to 60 seconds. This stops the companion
  from reconnecting every 30 seconds and keeps the Home Assistant log quiet
  during normal operation.

### Fixed
- Commands sent to an inactive channel are now rejected instead of driving the
  field bus, so a manually enabled entity can't switch a not-yet-wired relay or
  dimmer.
- Gateway shutdown no longer hangs when a slow WebSocket client is connected.

## [0.0.5] - 2026-06-05

### Fixed
- Gateway no longer fails to start when runtime auto-discovery is enabled.
- Forced module discovery now reliably delivers its results to the companion and other connected clients.

## [0.0.4] - 2026-06-04

### Added
- **Runtime auto-discovery**: the gateway finds IPBuilding modules on your network automatically. Newly seen modules are added to `devices.json` (disabled by default) and announced to the companion over WebSocket.
- 7 new options in the add-on configuration to control discovery range, polling interval, and behaviour.

### Changed
- Default discovery range is now the full `10.10.1.0/24` subnet instead of a fixed `30–59` window.

### Removed
- The undocumented `GATEWAY_AUTO_DISCOVER` environment variable has been removed; use the corresponding add-on option instead.

## [0.0.3] - 2026-06-04

### Fixed
- Add-on container failed to start due to a missing executable bit on the entrypoint script.

## [0.0.2] - 2026-06-04

### Fixed
- Add-on failed to register with the Home Assistant Supervisor because the watchdog URL did not match the expected format.

### Added
- A health endpoint on the gateway API, used by the Supervisor to monitor the add-on.

## [0.0.1] - 2026-06-04

### Added
- Initial alfa release of the open IPBuilding field-bus gateway.
- Direct replacement for the proprietary IPBox hub: speaks UDP/1001 to relay, dimmer, and input modules.
- Runs on Home Assistant Green (aarch64) and standard Linux servers (amd64).
- WebSocket API on port 8080 for the Home Assistant companion integration.
- Optional legacy REST shim on port 30200 (off by default) for the existing IPBuilding integration.
- Configurable hub IP, poll interval, and devices file location.
