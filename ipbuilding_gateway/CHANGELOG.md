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
