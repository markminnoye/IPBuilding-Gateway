# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Version policy

The IPBuilding Gateway add-on and the `ipbuilding-gateway-ha` companion
follow **independent semver**. A bump in one repo does not automatically
mean a bump in the other.

- **Patch (0.3.x)**: cosmetic, no impact on the REST/WS wire.
  Works with all companion versions that support the current wire.
- **Minor (0.x.0)**: new REST endpoints or optional fields in
  existing responses. The older companion keeps working but does not
  see the new fields.
- **Major (x.0.0)**: breaking change. The gateway or companion CHANGELOG
  then includes a `### Breaking:` entry listing incompatible combinations.

Backward compatibility is the norm — an add-on version keeps working
with the current companion until a `### Breaking:` entry says otherwise.

## [Unreleased]

### Changed
- **Web UI: dimmer channels are always lights.** Dimmer rows no longer show a type dropdown — only relay channels can be set to fan, cover, switch, or plug. Uploading or editing `devices.json` normalises dimmer types to light; the API rejects other values on PATCH.

### Fixed
- **Module search no longer duplicates modules without a MAC.** Installations imported from IPA (or other sources with empty `mac`) are matched by IP during a sweep; the gateway backfills the MAC and firmware on the existing entry instead of adding a second module at the same address.

## [1.4.1] - 2026-07-14

### Added
- **Web UI: Port column on input modules.** Pushbuttons show the physical IP1100 input port (0–7) under **Port** instead of **Ch**; relay and dimmer channels keep **Ch**.
- **IPA import for legacy installations.** New workstation script `scripts/import_ipa_to_devices.py` builds an upload-ready `devices.json` from IP1100 autonomy EEPROM (`.IPA`) without live `getButtons`/`getSysSet`. Reference output: `resources_and_docs/reference/devices.ipa-reference.json`.

### Fixed
- **Web UI: wrong module grouping when MAC is empty.** IPA import and other configs without a MAC address assigned `module_id: ""` on every module; the Web UI grouped all channels under the last module (e.g. three× Ch 0 on one dimmer). The API now falls back to IP as the module id until discovery fills in the MAC.

## [1.4.0] - 2026-07-14

### Added
- **Backup & restore in the Web UI.** Download the current `devices.json`, upload a manually edited file (validated before write — an invalid file changes nothing), or reset to an empty installation. New endpoints: `GET /api/v1/devices/export`, `POST /api/v1/devices/import`, `POST /api/v1/devices/reset`.
- **Buttons included in backup after module refresh.** After a metadata refresh (startup, discovery, or **Update** in the Web UI), physical pushbuttons on input modules are persisted in `devices.json`; a downloaded backup then contains the full nested `pushbuttons` list. Discovery writes the correct schema for input modules (`pushbuttons`/`detectors`, not `channels`).

### Fixed
- **Canonical pushbutton ID on module refresh.** Legacy `2D` prefix or mismatched casing in `devices.json` is normalised on merge so buttons do not duplicate and reload does not fail.

## [1.3.1] - 2026-07-13

### Changed
- **Pushbuttons nested per module in `devices.json`** (`modules[].pushbuttons[]`) instead of a separate top-level `buttons` list. Discovery and the Web UI now persist configured buttons reliably.

### Breaking
- **Legacy flat `buttons[]` format in `devices.json` is rejected.** Convert manually edited files with `scripts/migrate_buttons_to_nested.py` before upgrading, or let discovery repopulate.

### Fixed
- Discovery and empty seeds no longer leave a stale top-level `buttons` key behind.

## [1.3.0] - 2026-07-12

### Changed
- **Field-bus poll cadence matches IPBox:** input modules every ~2 s (`I0000`); relay and dimmer every ~20 s (`P0000` / `I9900`). New add-on option `actuator_poll_interval` (default 20).
- **Relay state on startup** now comes from the field bus (per-channel status poll) instead of HTTP on the module. After a restart, relays show the real on/off state in Home Assistant immediately.
- **Dimmers after restart** show `unknown` until the first command or a field-bus change — no longer the stale level from HTTP.

### Added
- **HA Supervisor Ingress Web UI:** built-in page to view and edit device names, rooms, and types.
- **Per-module refresh:** refresh metadata for one module (e.g. the button list on an input module) without refreshing the full installation.

### Removed
- HTTP `statuses` hydration on startup (replaced by UDP relay sweep).

## [1.3.0-rc1] - 2026-07-12

### Changed
- **Relay state on startup** now comes from the field bus (per-channel status poll) instead of HTTP on the module. After a restart, relays show the real on/off state in Home Assistant immediately.
- **Dimmers after restart** show `unknown` until the first command or a field-bus change — no longer the stale level from HTTP.

### Removed
- HTTP `statuses` hydration on startup (replaced by UDP relay sweep).

## [1.2.4] - 2026-07-03

### Added
- **`README.md` in the add-on folder** — English About/Features section in the Supervisor UI (store and add-on info), with a clear note that the **IPBuilding Gateway** companion is required for HA entities, a HACS install link via my.home-assistant.io, and a feature list (UDP/1001, northbound API, discovery, health, optional IPBox shim).

### Fixed
- **Memory leak on long-running installs.** RAM usage slowly climbed over several days because poll responses on the field bus were stored without bound. After this update, memory use stabilises again.

## [1.2.3] - 2026-07-01

### Fixed
- **Add-on store validation restored.** The `watchdog` URL in `config.yaml` accidentally used `http://[HOST]:[PORT]/health`. The Supervisor expects `http://[HOST]:[PORT:8080]/health` (internal container port). After a store refresh the add-on could disappear from the catalogue with errors such as *"does not exist in the store"* or *"has no source location"*.

## [1.2.2] - 2026-06-30

### Changed
- **Env-default UDP poll targets (`.30/.40/.50`) are no longer a silent fallback** when `devices.json` is missing or invalid. Production installs start without UDP polling until discovery fills `devices.json`. Lab/RE: enable add-on option `use_env_defaults` or `GATEWAY_USE_ENV_DEFAULTS=1`; `GATEWAY_SIMULATED=1` behaves as before.
- **Init-sweep on invalid `devices.json`** — parse/validation errors (e.g. `type: unknown`) now trigger the same startup sweep as a missing file.
- **Discovery no longer writes `type: unknown` to `devices.json`.** Unidentified modules (ARP-only or HTTP without a recognisable `refNr`) appear via WebSocket `device_added` and in `skipped_unidentified` on `POST /api/v1/discover`, but no longer block the loader. Init-sweep resets an invalid file to `{"modules":[]}`.

### Added
- **Diagnostic discovery logging** — HTTP identify errors, unresolved module types, and `devices.json` reload failures appear in the add-on logs.
- **Health issue `installation.load_failed`** when `devices.json` exists but cannot be loaded.
- **`refNr`/product name prefix fallback** — variants such as `ip0200poe` or `IP0300…` are recognised as relay/dimmer/input.

## [1.2.1] - 2026-06-23

### Fixed
- **More physical buttons are recognised.** Some IP1100PoE buttons send a different
  event type on the field bus than the previously documented variant. The gateway
  ignored those presses entirely; they are now forwarded to Home Assistant as normal
  press/release events.

## [1.2.0] - 2026-06-23

### Added
- **Downstream `T` / `D` dimmer commands.** `gateway/payloads/dimmer.py` exposes `encode_dim_toggle(channel)`, `encode_dim_start(channel)`, `encode_dim_stop(channel)` for the button/ramp wire dialect (`T<ch>991000`, `D<ch>001003`, `D<ch>001000`). `gateway_api._execute_command` dispatches `TOGGLE`, `DIM_START`, `DIM_STOP` actions on dimmer channels; `TOGGLE` and `DIM_STOP` track the channel for the channel-less reply, `DIM_START` is fire-and-forget. The companion's `button_dim` blueprint (v8) uses these to drive a native ramp instead of the old `brightness_step_pct` loop. Wire-bytes match `resources_and_docs/evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md`. Companion `ha-ipbuilding-gateway` ≥ **1.7.0** consumes the new gateway actions via `ha_ipbuilding_gateway.dim_start` / `dim_stop`.

## [1.1.1] - 2026-06-22

### Fixed
- `single_press` is no longer emitted twice when a duplicate or orphan release
  frame arrives (no active press). Only genuine short presses generate a
  `single_press`; surplus release frames still produce only a `released` event.
  Prevents unwanted double switch actions when used with HA automations.

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
- **Discovery TXT record schema v2.** `_build_txt_properties` now sends explicit `host`, `port`, `sw` (alias of `version`) and `mac` alongside the existing fields. Companion v1.2.2+ uses these fields to distinguish multiple gateways.
- **`instance_id` in HassIO discovery payload.** The Supervisor `/supervisor/discovery` POST now includes `instance_id` in `config`, so the companion can use the same unique ID as for zeroconf discovery.

## [1.0.3] - 2026-06-19

### Removed
- **Temporary fb376d debug-file logging from HassIO discovery.** During diagnosis of the 1.0.1 discovery issue, `_start_hassio` and `_hassio_announce_once` wrote structured events to `/config/debug-fb376d.log`. That is no longer needed; the regular `HassIO discovery announced: uuid=…` info log and warnings on POST failures remain.

### Changed
- `ipbuilding_gateway/config.yaml` `options:` and `schema:` sections reordered to match (Network / API → Hub / field bus → Discovery → Logging). Cosmetic; no impact on wire, defaults or schema validation.

## [1.0.2] - 2026-06-19

### Added
- **Diagnostic logging** on Supervisor discovery registration at startup, so it can be verified that the gateway is offered correctly to Home Assistant.

## [1.0.1] - 2026-06-19

### Fixed
- **Add-on now appears automatically in Home Assistant → Devices & Services → Discovered** when the companion is installed. The HassIO discovery call to `http://supervisor/discovery` was rejected by the Supervisor because the add-on lacked the `hassio_api` permission; the add-on received no `SUPERVISOR_TOKEN` and the discovery step was silently skipped. The `discovery:` service key (`ha_ipbuilding_gateway`) was already present; only the permission was missing. No change to the REST/WS wire or `devices.json`.

## [1.0.0] - 2026-06-19

### Breaking
- **HA integration domain renamed** from `ipbuilding_gateway_ha` to `ha_ipbuilding_gateway`, in lockstep with companion `ha-ipbuilding-gateway` v1.0.0. The add-on `discovery:` key, `gateway/ha_discovery.py` service payload and `scripts/import_ipbox_to_ha.py` event types now all use the new domain name. **Older add-on versions (< 1.0.0) keep working with the old `ipbuilding_gateway_ha` discovery key**; the new add-on + new companion (≥ 1.0.0) use the new one. The old/new pair is incompatible when versions are out of sync (old add-on + new companion: Supervisor discovery fails, manual config flow still works; new add-on + old companion: Supervisor discovery fails). **No impact** on REST/WS wire format or `devices.json`. Operators using Supervisor discovery: update add-on and companion in the same HA session.

### Removed
- **Runtime endpoint `POST /api/v1/debug/fieldbus-polling`** and the associated `fieldbus` block from `/api/v1/status` (`polling_enabled`, `poll_interval_s`). The gateway no longer has a runtime toggle for field-bus polling; the companion "Fieldbus polling (debug)" switch was removed as well.

### Notes
- **Version policy change** — the add-on reaches `1.0.0` with this breaking rename. After this, the add-on follows independent semver from the companion: patch-level bumps in one repo do not automatically bump the other. Backward compatibility remains the norm until a `### Breaking:` entry says otherwise.

## [0.4.3] - 2026-06-18

### Fixed
- **Correct light state immediately after restart.** Before this version, Home Assistant showed all lights as "off" until the first UDP command arrived — the gateway had no idea of the real channel state. On startup the gateway now fetches live channel status from each relay and dimmer module via their built-in web interface, so the first snapshot in Home Assistant shows the correct on/off state. Dimmers that have not yet reported status show "Unknown" instead of "off", and inactive channels are correctly marked as disabled.

## [0.4.2] - 2026-06-18

### Added
- **Debug toggle for the field-bus polling loop.** New endpoint `POST /api/v1/debug/fieldbus-polling` lets an operator stop the periodic UDP/1001 keep-alive polls at runtime (without restarting the bus). The poll loop keeps running on its normal cadence, so flipping the flag back on resumes polling almost immediately. The status payload now reports a top-level `fieldbus` block with the current `polling_enabled` and `poll_interval_s`, and the `fieldbus` subsystem goes to `degraded` while polling is off — surfaced as a `fieldbus.polling_disabled` warning in `/api/v1/status`. **Requires companion v0.4.2+** to expose the matching "Fieldbus polling (debug)" switch in Home Assistant; older companions ignore the new endpoint.

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
- **Init-sweep crashed with `AttributeError: 'DiscoveryOrchestrator' object has no attribute '_state'`.** The 0.3.7 fix to keep runtime fields out of `devices.json` introduced a reference to `self._state[dm.mac]` in `_run_init_sweep`, but `_state` is an attribute of `ArpMonitor`, not the orchestrator. The line was removed; `_run_init_sweep` only writes to `devices.json` and no longer maintains its own runtime state. No companion-side changes.

## [0.3.7] - 2026-06-16

### Fixed
- **`devices.json` stays stable between discovery runs.** Runtime fields `last_seen` and `last_seen_source` were silently added to the written file by `auto_discovery`, against convention (`ModuleConfig.to_dict()` already documented "NOT serialized to devices.json"). Same for `ChannelConfig.to_dict()` writing back the derived entity `id`. Three call sites in `auto_discovery.py` were cleaned up; `ChannelConfig.to_dict()` no longer writes the `id` field. The file now contains purely installation-specific data (name, room, `active`, model, MAC) and no longer changes on every `POST /api/v1/discover`.
- **Lock file (`devices.json.lock`) is cleaned up.** `AtomicWriter` held an advisory lock on a `.lock` file. After a crash or interrupted test it remained as an untracked artefact in the working tree. `try/finally` now always removes the file, including on exception paths.

## [0.3.6] - 2026-06-16

### Changed
- **IP1100PoE buttons start disabled** in Home Assistant. After discovery they appear under disabled entities so you choose which buttons to activate.

## [0.3.5] - 2026-06-16

### Changed
- **Supervisor now auto-updates the add-on** (`auto_update: true`). Future 0.3.x patch releases roll out without an operator action; the v0.3.3 image was already published but kept running v0.3.1 because this flag was off.

## [0.3.4] - 2026-06-16

### Fixed
- **`devices.json` is now saved where you can see it.** Discovery and forced scans write to `/config/devices.json`, which maps to the add-on folder under **Samba / SSH** (`addon_configs/.../devices.json`). Earlier releases wrote to the internal `/data` volume only, so the file looked missing even when discovery succeeded. Existing installs are migrated automatically on start.
- **Startup log and API version** now match the add-on version in Supervisor (single source: `config.yaml`).

### Changed
- Add-on requests **`addon_config:rw`** so the gateway can write installation config next to your other add-on files.

## [0.3.3] - 2026-06-16

### Changed
- **Module names are now consistent across all three field modules.** The gateway fills in the canonical hardware SKU (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) when `devices.json` carries an empty `model` or an IP-based `name`, so the companion's onboarding device info always shows the SKU as title and the role label (Relay / Dimmer / Input) as the device name. The companion also treats module IP addresses as auto-discovery placeholders and never leaks them into the operator-facing name.

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
