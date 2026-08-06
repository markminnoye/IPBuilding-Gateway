# Learn-on-press: onbekende knoppen

**Status:** approved for implementation  
**Date:** 2026-08-06  
**Repos:** IPBuilding Gateway (northbound) + ha-ipbuilding-gateway (companion)

## Problem

A physical press (`B-…E` → WS `button_event`) for a hardware id not yet in
`devices.json` is decoded and broadcast by the gateway, but the companion has
no `event.*` entity / listener for that id — the press is silently ignored.

Separately, the devices snapshot listed buttons primarily from the live
`getButtons` HTTP cache. A button known only on disk (or missing from EEPROM
after a refresh) could disappear from HA while still existing in
`devices.json`.

## Goals

- Gateway is the source of truth for which buttons exist (autonomous hub).
- On first unknown press: persist a stub, notify all northbound clients, then
  emit the normal `button_event` so the first press is usable.
- Same protocol for HA companion today and Matter / other clients later.
- Soft retention: never auto-delete pushbuttons from `devices.json` when they
  are absent from `getButtons`.
- Keep sync with EEPROM simple: existing `or`-merge; empty stub names get
  filled when `getButtons` later knows the button.

## Non-goals

- Writing button bindings / `saveAutonomy` to EEPROM (Fase 8).
- Matter-bridge implementation (protocol readiness only).
- Placeholder-name detection in sync.
- Companion-only learning / PATCH-back as the primary learn path.

## Responsibilities

| Layer | Does | Does not |
|-------|------|----------|
| Gateway | Persist stub; `device_added` + `button_event`; snapshot from `pushbuttons[]`; `getButtons` enrichment | HA notifications; scenes |
| Companion | Create `EventEntity` on button `device_added`; route `button_event`; persistent notification | Persist learn state as sole writer |
| IP1100 | Wire events + optional EEPROM metadata | Canonical hub button inventory |

## ID mapping

Canonical key: normalized hardware id — 14 lowercase hex characters
(`normalize_button_hardware_id`). Wire / WS use this form; `getButtons` may
prefix `2D` — stripped before compare. Module IP is not a key (DHCP).

## Data flow

1. `_on_button_event` receives press/release with hardware id + module IP.
2. If id already in `installation.pushbuttons` → existing classification /
   broadcast.
3. Else if parent input module is known by IP:
   - Guard with in-memory `_learning_button_ids`.
   - Append `PushbuttonConfig(id, module_id=mac, name="", room="", active=True)`
     via `AtomicWriter.read_modify_write`; reload installation.
   - Broadcast `device_added` (button shape).
   - Continue with normal `button_event` classification.
4. Else (unknown module): log; do not persist (module discovery remains ARP).

### `device_added` (button)

```json
{
  "type": "device_added",
  "semantic_type": "button",
  "id": "2f8185190000df",
  "module_id": "00:24:77:…",
  "module_ip": "10.10.1.50",
  "device_type": "input",
  "name": "",
  "room": "",
  "active": true,
  "channel": null
}
```

Module-discovery `device_added` (no `semantic_type: "button"`) stays unchanged.

## Snapshot

`_build_device_list` iterates `mc.pushbuttons` for input modules. Empty
`name`/`room`/`channel` may be enriched from cached `getButtons` for the same
id. Display fallback `Button {id}` is northbound-only (not written to disk).

Startup continues to call `persist_pushbuttons_from_cache()` so EEPROM-known
buttons are seeded onto disk before clients rely on the snapshot.

## Companion

- On `device_added` with `semantic_type == "button"`: add device immediately
  (no 2s snapshot debounce), create event entity, show persistent notification
  (rename / assign area).
- `button_event` routing unchanged once the listener exists.

## Testing

- Learn writes one stub; second press does not double-write.
- Emit order: `device_added` then `button_event`.
- Snapshot includes disk-only buttons without meta cache.
- Sync fills empty stub name from `getButtons`.
- Companion: button `device_added` → platform add + notification.
