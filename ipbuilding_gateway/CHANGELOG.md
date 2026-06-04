# Changelog

All notable changes to the IPBuilding Gateway add-on are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.0.1] - 2026-06-04

### Added

- Initial alfa release of the open IPBuilding field-bus gateway.
- UDP/1001 field-bus hub replacing the proprietary IPBox role.
- Multi-arch support: aarch64 (HA Green) and amd64.
- WebSocket API on port 8080 for companion integration.
- Optional REST shim on port 30200 (transitie compatibiliteit, default uit).
- Configurable hub IP, poll interval, devices file location.
