# IPBuilding Gateway -- Module Resource

A **module** is a physical IPBuilding field-bus controller (relay, dimmer, or input). Modules are identified by their factory MAC address, which never changes even when the IP address is reassigned by DHCP.

## Module vs Device

| Concept | Identifier | Changes with DHCP |
|---------|------------|-------------------|
| **Module** | MAC (`00:24:77:52:ac:be`) | No -- stable forever |
| **Device** (channel) | `{ip}-{ch}` or custom slug | Default slug yes; custom slugs no |

## Network metadata cache

Module network info (`dhcp`, `ip`, `subnet`, `gateway`) is fetched at gateway startup via HTTP `getSysSet` on each module. It is **not** persisted to `devices.json` -- it lives only in memory.

To refresh all modules:

```bash
curl -X POST http://localhost:8080/api/v1/modules/refresh
```

To refresh one module (by MAC):

```bash
curl -X POST http://localhost:8080/api/v1/modules/00:24:77:52:ac:be/refresh
```

## Input modules and `buttons`

For `type=input` modules, the cache also includes `buttons[]` fetched via `getButtons`. This is the **configured button-to-output mapping** stored in the IP1100PoE EEPROM, not live button press state. Live presses arrive as `button_event` on the WebSocket.

## REST endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/modules` | All modules with cached metadata |
| GET | `/api/v1/modules/{module_id}` | Single module by MAC |
| POST | `/api/v1/modules/refresh` | Re-fetch getSysSet/getButtons (all modules) |
| POST | `/api/v1/modules/{module_id}/refresh` | Re-fetch one module by MAC |

See [`rest.md`](rest.md) for full response schemas.

## DHCP IP sync

When a module receives a new IP via DHCP and you run `gateway.discover`, the discovery tool matches on MAC and updates `modules[].ip` in `devices.json`. Default device IDs (`{old_ip}-{ch}`) will then be stale until you re-run discovery and update config. Use custom `id` slugs on channels if you want stable device IDs regardless of IP changes.
