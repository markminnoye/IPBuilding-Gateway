# Input Hub Role (Master/Slave) — Add-on Configuration Design

**Date:** 2026-07-14  
**Status:** Approved (brainstorm)  
**Component:** `ipbuilding_gateway/config.yaml`, `gateway/config.py`, `gateway/udp_bus.py`, `gateway/webui.py` (read-only badge)

## Summary

Configure whether input modules (IP1100PoE) run in **slave** or **master/autonomous** mode relative to this gateway via a single add-on option `hub_role`. This is **environment-specific migration/deployment** settings — not stored in `devices.json`.

| `hub_role` | Input mode (manual) | Gateway |
|------------|---------------------|---------|
| `full` (default) | Slave — centrale polls | `I0000` poll + `B-…E` events |
| `actuators_only` | Master — autonomous EEPROM | No input poll, no button events |

Operator changes hub role in **Home Assistant → Settings → Add-ons → IPBuilding Gateway → Configuration**. **Add-on restart required** after change.

## Motivation

### Product goal (migration / dual-hub)

During cutover from IPBox or when an embedded hub coexists, operators need relay/dimmer control via this gateway **without claiming input modules** (no `I0000`, no centrale registration). Physical buttons keep working via EEPROM `func1`/`func2` (master/autonomous path).

### Why not `devices.json`?

`devices.json` is the **installation backup** (names, rooms, channel `active`, semantic types). Hub role is **per deployment**:

- Lab gateway vs production gateway may differ while sharing the same devices export.
- Restoring a production backup must not silently force slave mode on a migration gateway that should stay `actuators_only`.

See `ARCHITECTURE.md` write-policy: northbound fields (`active`, `name`, …) belong in `devices.json`; field-bus participation is deployment config.

### Why not a Web UI write toggle?

The ingress Web UI edits `devices.json` (PATCH devices). Hub role belongs in add-on options. A Web UI toggle would either:

- Write to `devices.json` (wrong layer), or
- Require Supervisor options API + restart (same as HA add-on UI, duplicated UX).

**Web UI shows read-only Slave/Master badge** on input module headers; tooltip points to add-on configuration.

## Background — Master/Slave (IP1100 handleiding + RE)

From install manual and [`IPBUILDING_KNOWLEDGE.md`](../../../resources_and_docs/IPBUILDING_KNOWLEDGE.md) §12.5:

- **Slave:** centrale service software maintains module; green LED **steady**; button events to centrale; scenes/automation via project/HA.
- **Master (autonomous):** centrale absent; green LED **blinking**; basic lighting via EEPROM; scenes, audio, cameras, motion detectors, etc. unavailable.

Wire evidence ([embedded E1.5](https://github.com/markminnoye/matter-esp32-ipbuilding-gateway/blob/development/docs/field-test/evidence/2026-07-11-e1-input-listener.md)): input centrale-claim is **poll-gated** — no `I0000` → no `B-…E` to hub.

**Distinct from channel `active`:** `active: false` on a pushbutton is northbound only (HA entity disabled+hidden); the gateway still polls the input module today. Hub role controls **field-bus participation**.

## Configuration model

### Add-on option (primary)

Nested schema following [Advanced SSH & Web Terminal](https://github.com/hassio-addons/app-ssh) pattern for readable Supervisor UI:

```yaml
options:
  fieldbus:
    poll_interval: 2.0
    actuator_poll_interval: 20.0
    hub_role: full   # full | actuators_only
schema:
  fieldbus:
    poll_interval: float
    actuator_poll_interval: float
    hub_role: list(full|actuators_only)
```

Full config restructure (same change): group existing flat options under `network`, `fieldbus`, `discovery`, `installation`, `logging` with matching nested `schema`.

### Environment mapping

| Surface | Variable |
|---------|----------|
| HA add-on | `options.fieldbus.hub_role` → `run.sh` → `GATEWAY_HUB_ROLE` |
| Standalone / Docker | `GATEWAY_HUB_ROLE=actuators_only` |
| Default | `full` |

### Granularity

**Preset only** — all input modules share the same mode. Sufficient for migration (single IP1100PoE typical). Per-module overrides deferred (issue [#16](https://github.com/markminnoye/IPBuilding-Gateway/issues/16) `managed` per module not used in Python gateway for Gen 1).

### Backward compatibility

`run.sh` reads nested keys first; falls back to legacy flat keys (`hub_ip`, `poll_interval`, …) so existing installs without nested options keep working until operator re-saves configuration.

## Runtime behaviour

### Poll loop (`gateway/udp_bus.py`)

When `hub_role == actuators_only`, skip `I0000` TX to all input module IPs. Relay/dimmer polls unchanged.

### Input events (`gateway/gateway_api.py`)

When `actuators_only`, do not broadcast `button_event` (defense-in-depth if stray packets arrive).

### Northbound snapshot

When `actuators_only`, omit input pushbuttons from `GET /api/v1/devices` and WS snapshot. Companion removes event entities via existing diff logic.

Module entries remain in `GET /api/v1/modules` (metadata unchanged).

### Status API

`GET /api/v1/status` exposes:

```json
{
  "hub_role": "full",
  "input_mode_label": "Slave"
}
```

`input_mode_label` is `"Slave"` for `full`, `"Master"` for `actuators_only` (operator-facing; maps to manual terminology).

## Web UI

On input module headers only:

- **Read-only badge:** `Slave` or `Master` (from status API)
- **No toggle** — removed placeholder Enable control
- **Tooltip:** change via HA add-on Configuration; restart required
- Danger zone copy: use **Active** (not "enable") for per-button northbound

Relay/dimmer module headers: no hub role badge.

## HA Add-on configuration UX

Improvements bundled with this feature:

1. Nested `options` / `schema` groups (network, fieldbus, discovery, installation, logging)
2. Clear `hub_role` enum labels documented in `ipbuilding_gateway/DOCS.md`
3. Migration section: when to use `actuators_only`, expected LED behaviour, restart step

Official reference: [Home Assistant Apps — Configuration](https://developers.home-assistant.io/docs/apps/configuration)

## Operator documentation (mandatory copy)

Long-form operator text lives in three surfaces (see implementation plan). Canonical NL/EN strings:

### HA Configuration UI — `ipbuilding_gateway/translations/nl.yaml`

**Group `fieldbus`:** name `Veld-bus`

**Field `hub_role`:** name `Input-centrale modus`

**Description:**

> Bepaalt hoe IP1100PoE-ingangsmodules zich gedragen ten opzichte van **deze gateway** als centrale op de veldbus.
>
> **Slave (`full`) — standaard**  
> De gateway pollt de ingangsmodule (`I0000`) en ontvangt drukknop-events (`B-…E`). De module gedraagt zich als **slave**: groene LED **brandt continu**, knoppen sturen events naar de centrale. Scenes en automatisering horen in Home Assistant (niet in de gateway).
>
> **Master / autonoom (`actuators_only`) — migratie**  
> De gateway pollt **geen** ingangen en claimt de module niet. De IP1100 valt terug op de **autonomietabel in EEPROM** (zoals wanneer de originele centrale uitvalt): groene LED **knippert**, drukknoppen bedienen basisverlichting lokaal. Scenes, audio, camera’s en bewegingsmelder-logica via de centrale zijn dan **niet** beschikbaar.
>
> Gebruik `actuators_only` tijdens **migratie of dual-hub**: relay/dimmer via deze gateway, terwijl knoppen lokaal blijven werken zonder dat deze gateway de input claimt. **Add-on herstart vereist** na wijziging.

### HA Configuration UI — `ipbuilding_gateway/translations/en.yaml`

Same structure in English (`Field bus`, `Input centrale mode`, Slave/Master paragraphs).

### Add-on docs — `ipbuilding_gateway/DOCS.md`

Section **Input-centrale (master/slave)** with comparison table, migration steps, and distinction from channel `active`.

### Web UI badge tooltip (ingress, EN)

> **Slave:** this gateway polls the input module and receives button events for Home Assistant.  
> **Master:** this gateway does not claim inputs; buttons use EEPROM autonomy (blinking LED).  
> Change via **Settings → Add-ons → IPBuilding Gateway → Configuration** (restart required).

## Out of scope

- `managed` field in `devices.json` (embedded firmware may keep local `managed`; Python gateway uses `hub_role` only)
- Web UI writes hub role
- Per-module hub role in config
- Push/Fetch EEPROM (Fase 8)
- Companion changes (snapshot diff handles entity removal)

## Testing

| Case | Expect |
|------|--------|
| Default `full` | Input poll + button events (unchanged) |
| `actuators_only` | No `I0000`; no WS `button_event`; pushbuttons absent from snapshot |
| Status API | Correct `hub_role` and `input_mode_label` |
| Web UI | Slave/Master badge; no write toggle |
| `run.sh` | Nested + flat fallback |
| devices export | Does not include `hub_role` |

## Acceptance criteria (field)

1. HA add-on Configuration shows nested fieldbus group with `hub_role`
2. After restart with `actuators_only`: no input poll; buttons work locally; input LED blinking
3. After restart with `full`: slave behaviour restored
4. Web UI badge matches effective mode

## Related

- [Issue #16 — hub_role / managed](https://github.com/markminnoye/IPBuilding-Gateway/issues/16) — preset `actuators_only` implemented here; per-module `managed` deferred
- [Sprint 5 input completion](../../../resources_and_docs/evidence/2026-05-22_sprint5_input_physical_completion.md) — slave vs autonomous diagram
- Implementation plan: `.cursor/plans/module_enable_managed_f1bf020f.plan.md` (updated scope)
