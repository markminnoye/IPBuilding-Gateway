# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
