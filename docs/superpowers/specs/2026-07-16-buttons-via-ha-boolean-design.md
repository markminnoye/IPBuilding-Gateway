# Buttons via Home Assistant (boolean) — Design

**Date:** 2026-07-16  
**Status:** Approved  
**Component:** `ipbuilding_gateway/config.yaml`, `run.sh`, translations, `gateway/config.py`, status API, DOCS

## Summary

Replace add-on option `fieldbus.hub_role` (`slave` | `master`) with a customer-facing boolean **`fieldbus.buttons_via_ha`** (default `true`). Internally the gateway stores a bool; Slave/Master labels remain on status and the Web UI badge for IP1100 manual familiarity. LED meaning stays documented in the option description and DOCS.

## Motivation

Operators confused `hub_role: slave` (module POV) with “buttons disabled”. Framing the choice as “wall buttons via Home Assistant” matches the product: default on = events in HA; off = local EEPROM pairings during migration.

## Decisions

| Topic | Choice |
|-------|--------|
| Operator UX | Boolean “Drukknoppen via Home Assistant” / “Wall buttons via Home Assistant” |
| Default | `true` (buttons via HA) |
| Internal model | `GatewayConfig.buttons_via_ha: bool` — no string `hub_role` field |
| Status / Web UI badge | Keep derived `hub_role` + `input_mode_label` (Slave/Master) |
| LED copy | Short in Supervisor description; full table in DOCS |
| Legacy | Map `hub_role` / `GATEWAY_HUB_ROLE` at startup |

## Behaviour

| `buttons_via_ha` | Field bus | HA buttons | Module LED |
|------------------|-----------|------------|------------|
| `true` (default) | `I0000` poll, `button_event`, pushbuttons in snapshot | Present | Steady (= slave) |
| `false` | No input poll; suppress events; omit pushbuttons | Absent | Blinking (= master) |

Relays/dimmers unchanged. Channel `active` remains northbound-only.

## Mapping

- `buttons_via_ha=true` → derived `hub_role="slave"`, `input_mode_label="Slave"`, `claims_input_modules=True`
- `buttons_via_ha=false` → derived `hub_role="master"`, `input_mode_label="Master"`, `claims_input_modules=False`

## Configuration

### Add-on

```yaml
options:
  fieldbus:
    buttons_via_ha: true
schema:
  fieldbus:
    buttons_via_ha: bool
```

### Environment

- Primary: `GATEWAY_BUTTONS_VIA_HA` (`1`/`0`/`true`/`false`/`yes`)
- Fallback: `GATEWAY_HUB_ROLE` (`slave`→true, `master`→false); unknown → true + warning
- `run.sh` resolves nested/flat `buttons_via_ha` first, else legacy `hub_role`

## Status API

`GET /api/v1/status` (and WS `gateway_status` / snapshot) includes:

- `buttons_via_ha` (bool) — primary
- `hub_role`, `input_mode_label` — derived, for badge and older clients

## Out of scope

- Version bump / GitHub release
- Companion changes
- Renaming Web UI badge away from Slave/Master
- Per-module overrides

## Acceptance

1. Fresh install: option on → buttons in HA when gateway polls.
2. Option off + restart → no button entities/events; relays/dimmers OK.
3. Upgrade from `hub_role: master` without re-save → effective `buttons_via_ha=false`.
4. Status shows `buttons_via_ha` + derived Slave/Master; Web UI badge matches.
5. Unit and add-on config tests green.
