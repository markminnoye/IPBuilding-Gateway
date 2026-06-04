# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.0.4] - 2026-06-04

### Added
- **Runtime auto-discovery** (init-sweep + passive ARP monitor + forced REST):
  - Init-sweep populates `devices.json` with `active: false` entries when the file is empty on first start.
  - Passive ARP monitor polls the kernel ARP table every 30 s (configurable), emitting `device_added`, `device_removed`, and `device_ip_changed` WebSocket events.
  - Forced discovery via `POST /api/v1/discover` runs ARP-sweep + HTTP getSysSet regardless of toggles; updates firmware in `devices.json`.
  - `last_seen` / `last_seen_source` added to module resource (runtime-only, not persisted to `devices.json`).
  - `device_added`, `device_removed`, `device_ip_changed`, `device_firmware_changed` WebSocket event types.
- 7 new HA add-on config options: `discovery_subnet`, `discovery_range_start`, `discovery_range_end`, `auto_discover_on_start`, `passive_arp_monitor`, `arp_poll_interval_s`, `http_timeout_s`.

### Removed
- `GATEWAY_AUTO_DISCOVER` env-var (dead alias; replaced by `GATEWAY_AUTO_DISCOVER_ON_START` + `GATEWAY_DISCOVERY_*`).

### Changed
- Bumped HA add-on schema version to `0.0.4`.

## [0.0.3] - 2026-06-04

### Fixed
- Container failed to start with `exec: "./run.sh": permission denied` (v0.0.2). The git index had `run.sh` stored as `100644` (not executable), so the Docker COPY layer lacked the executable bit. Marked `run.sh` executable in the index, added explicit `RUN chmod +x ./run.sh` in the Dockerfile as a defence-in-depth, and removed `--no-preserve=mode,ownership` from `prepare-build.sh` so staged files keep their modes.

## [0.0.2] - 2026-06-04

### Fixed
- `watchdog: application` was rejected by HA Supervisor (expected URL `http://[HOST]:[PORT:8080]/health`). Replaced with valid watchdog URL pointing at the gateway's new `GET /health` endpoint.

### Added
- `GET /health` endpoint on the gateway API (returns `{"status": "ok"}`) — used as Supervisor watchdog target.

## [0.0.1] - 2026-06-04

### Added

- Initial alfa release of the open IPBuilding field-bus gateway.
- UDP/1001 field-bus hub replacing the proprietary IPBox role.
- Multi-arch support: aarch64 (HA Green) and amd64.
- WebSocket API on port 8080 for companion integration.
- Optional REST shim on port 30200 (transitie compatibiliteit, default uit).
- Configurable hub IP, poll interval, devices file location.
