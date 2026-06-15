# Gateway status API — design (issue #14)

**Date:** 2026-06-15  
**Status:** Approved (scope B)  
**Repos:** IPBuilding Gateway + ipbuilding-gateway-ha

## Goal

Pollable gateway health (`GET /api/v1/status`, `GET /health`) plus WebSocket push (`gateway_status`) when aggregate status or open issues change. Companion MVP: Tier-1 hub `sw_version`, status sensor, discover sweep button.

## Status vocabulary

Aggregate and subsystem `status`: `ok` | `degraded` | `unhealthy` (readable variant of IETF pass/warn/fail).

Per-issue `level`: `warning` | `error`.

Colors are GUI-only (HA translations, icons, Lovelace `state_color`).

## Endpoints

| Endpoint | Payload |
|----------|---------|
| `GET /health` | `{ "status", "version" }` — Supervisor liveness |
| `GET /api/v1/status` | Full snapshot + `actions` |
| WS `gateway_status` | Same as status body (no `actions`) |
| WS `snapshot.gateway_status` | Embedded on connect |

Push when aggregate `status` or open `issues[].id` set changes.

## Issue sources (MVP)

- `installation.missing` — no devices.json
- `module_metadata.{method}.{ip}` — HTTP getSysSet/getButtons failure
- `discovery.unreachable.{mac}` — ARP monitor device_removed

## Companion

- REST fetch on setup for `version` / `sw_version`
- `IPBuildingGatewayStatusSensor` — state = API `status`
- `IPBuildingDiscoverButton` — `POST /api/v1/discover`

## Out of scope

HA repair flows, full 3-tier `via_device` chain (ipbuilding-gateway-ha#3).
