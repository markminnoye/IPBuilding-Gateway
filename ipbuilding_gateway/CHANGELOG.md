# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions are kept in lockstep with the `ipbuilding-gateway-ha` companion
so an add-on + companion upgrade can be tracked as a single number.

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
