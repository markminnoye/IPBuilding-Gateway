# Dimmer button-ramp protocol — downstream control + companion wiring

Date: 2026-06-22
Status: approved (design), ready for implementation plan
Base branch: `develop` (gateway), `feature/blueprints` (companion)

## Background

A second dimmer wire dialect was reverse-engineered from
`~/Downloads/capture dimmer.pcapng`: the IP1100PoE input module commands the
IP0300PoE dimmer **peer-to-peer** (UDP/1001), bypassing the hub. It carries a
toggle and a *hold-to-dim* ramp that the existing absolute `S…1030` dialect
cannot express.

Wire contract (8-byte ASCII, grammar `<prefix><channel><value><suffix4>`):

| Frame | Meaning | Reply |
|---|---|---|
| `T<ch>991000` | toggle (short press) | `I0154<ch><vv>` |
| `D<ch>001003` | dim-hold **start** | (none) |
| `D<ch>001000` | dim-hold **stop** | `I0154<ch><vv>` (final level) |

Key finding (capture-confirmed): two byte-identical `D…1003` holds ramped
**up then down** — the **dimmer module owns ramp direction** and auto-reverses
on each successive hold. HA needs no direction state.

The capture had no gateway present, so the modules talked to each other. With
the gateway acting as hub (`10.10.1.1`), the input and dimmer modules converse
with the gateway instead, so the gateway both receives the button events and
sends the dimmer commands. The dimmer accepts `T`/`D` from the hub IP.

Evidence: `resources_and_docs/evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md`.

## Why this matters

The current companion `button_dim.yaml` (v7) implements hold-to-dim the **old
way**: a `repeat` loop firing `light.turn_on brightness_step_pct` every ~200 ms
(a flood of `S…1030` frames), plus a `direction_helper` (`input_boolean`) to
track up/down and `numeric_state` endpoint triggers to flip at 0%/100%.

The native `T`/`D` protocol **replaces all of it**: one frame to start the ramp,
one to stop it; the module ramps and reverses itself. This removes the helper,
the loop, the endpoint detection, and the step/interval inputs.

## Current state (already done — do not rebuild)

- **Gateway `develop`**: `single_press`/`long_press`/`release` classification
  (feature/button-event-taxonomy, merged); `T`/`D` **decode** for observability
  (`_INPUT_TOGGLE_RE`, `_INPUT_DIM_START_RE`, `_INPUT_DIM_STOP_RE` in
  `gateway/payloads/dimmer.py`); the evidence doc.
- **Companion `feature/blueprints` (v1.6.0)**: `single_press`/`long_press`/
  `release` device triggers and event entities; `button_dim.yaml` (v7) and
  `button_standard.yaml` blueprint scaffolding.

## Goals

1. Gateway can **send** `T`/`D` frames on operator command (downstream).
2. Companion exposes `dim_start`/`dim_stop` so a button maps
   `single_press → toggle`, `long_press → dim_start`, `release → dim_stop`.
3. The dim-during-hold path needs **no helper, no loop, no state machine** in HA.

## Non-goals

- No change to the absolute `S…1030` / `C…1030` path (slider/scene still use `DIM`).
- No new upstream decode (already on develop; the gateway is the hub, so it does
  not normally see p2p frames live — state comes from `I0154…` replies + polling).
- No migration note for the dropped `direction_helper` (per owner: users just
  delete their input_boolean).

## Design

### Data flow

```
Knop (IP1100 .50) ──press/release──► Gateway .1
   Gateway classifies: single_press | long_press | release  (WS /ws button_event)
        ▼
   HA companion blueprint v8
     single_press → light.toggle   (existing companion light path)
     long_press   → ipb.dim_start  → Gateway DIM_START  → D{ch}001003 ─┐ module ramps
     release      → ipb.dim_stop   → Gateway DIM_STOP   → D{ch}001000 ─┘ + auto-reverses
   dimmer reply  I0154{ch}{vv} ─► state in HA
```

### 1. Gateway — `gateway/payloads/dimmer.py` (encoders)

Add, next to the existing decode and `encode_dim_command`/`encode_dim_off`:

```
encode_dim_toggle(channel) -> b"T{channel}991000"
encode_dim_start(channel)  -> b"D{channel}001003"
encode_dim_stop(channel)   -> b"D{channel}001000"
```

The `99`/`00` value field is a fixed placeholder in this dialect (the module
ignores it for ramp; toggle uses last-level memory). Document the suffix split
in the docstring: `…30` = absolute/REST path, `…00`/`…03` = button/ramp path.
Export the three encoders from `gateway/payloads/__init__.py`.

### 2. Gateway — `gateway_api.py` (dispatch)

In `_dispatch_command`, extend the `DeviceType.DIMMER` branch:

- `DIM` → `encode_dim_command` / `encode_dim_off` (unchanged)
- `TOGGLE` → `encode_dim_toggle(channel)`
- `DIM_START` → `encode_dim_start(channel)`
- `DIM_STOP` → `encode_dim_stop(channel)`

`TOGGLE`/`DIM_STOP` produce an `I0154…` reply → call `track_dimmer_channel` for
them (as `DIM` already does) so the channel-less reply lands on the right key.
`DIM_START` has no reply — send without awaiting correlation. Add the new dimmer
actions to whatever `valid_actions` the API advertises for a dimmer (today a
single list at `gateway_api.py:423`): `TOGGLE`, `DIM_START`, `DIM_STOP` join `DIM`.
`TOGGLE` is added for API parity / native-toggle availability; the companion
does not have to route through it (see §3).

### 3. Companion — services (`ha-ipbuilding-gateway`)

No `services.yaml` exists yet — add one. Two new entity-targeted services:

- `ha_ipbuilding_gateway.dim_start` (target: light entity) → gateway action `DIM_START`
- `ha_ipbuilding_gateway.dim_stop`  (target: light entity) → gateway action `DIM_STOP`

Toggle stays on the standard `light.toggle` (the existing companion light path
already turns the dimmer on/off) — no new wiring, no native-`TOGGLE` routing in
the light platform. Register the two services through the same gateway-client /
action path the light platform already uses; add `strings.json` +
`translations/{nl,en}.json` entries.

### 4. Companion — `button_dim.yaml` v8

Rewrite to the native ramp. **Remove** inputs `direction_helper`,
`dim_step_pct`, `dim_interval_ms`, `dim_boundary_pct` and the repeat-loop /
endpoint-trigger / direction-flip logic. Keep `button_entity` + `target_light`.

```
single_press → light.toggle(target_light)
long_press   → ha_ipbuilding_gateway.dim_start(target_light)
release(from long_press) → ha_ipbuilding_gateway.dim_stop(target_light)
```

Keep the existing trigger guard that a short-tap `release` does not fire the
hold path. Bump `ipbuilding_blueprint_version` and the description.

### 5. Documentation

- `gateway/payloads/dimmer.py` docstring: note the new encoders + suffix split.
- Gateway `ipbuilding_gateway/CHANGELOG.md`: downstream `T`/`D` support.
- Companion `DOCS.md` + the cutover reference
  (`resources_and_docs/reference/2026-06-17_button_long_press_cutover.md`):
  replace dim-loop/helper instructions with the native dim_start/dim_stop path.
- `resources_and_docs/IPBUILDING_KNOWLEDGE.md` §6.6: cross-link the downstream
  encoders to the existing evidence doc.

## Branch strategy

- Gateway work branches off **`develop`** (has single_press + p2p decode). The
  current worktree is off `main`; **step 0 is to rebase the feature branch onto
  `develop`** before any code.
- Companion work branches off **`feature/blueprints`**.
- Two repos, two PRs; the companion v8 blueprint depends on the gateway
  `DIM_START`/`DIM_STOP` actions, so land/release the gateway change first.

## Testing

- **Encoders**: assert exact wire bytes against the capture
  (`T1991000`, `D1001003`, `D1001000`) for representative channels.
- **Dispatch**: each new dimmer action emits the right payload on the bus;
  `DIM_START` does not await a reply; `track_dimmer_channel` called for
  `TOGGLE`/`DIM_STOP`.
- **Companion**: service handlers call the gateway action API with the right
  action + entity; blueprint validates (no removed inputs referenced).
- Manual: `single_press`/`long_press`/`release` on a real button drives
  toggle/ramp/stop end-to-end; `I0154…` reply updates HA state.

## Risks / open items

- Live confirmation that `DIM_START`/`DIM_STOP` from the hub IP behave identically
  to the captured p2p frames (owner expects yes; verify on hardware).
- Ramp speed is the module's internal `dimSpeed`; not tunable from this path
  (acceptable — matches native IPBox behaviour).
