# Button Event Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give IPBuilding wall buttons a clean, future-proof event taxonomy — Phase 1 adds a `single_press` event (fixing the current broken long-press disambiguation in `button_standard`); Phase 2 adds opt-in `double_press`/`triple_press` with a per-button inter-click window.

**Architecture:** The gateway (low-resource, simple) keeps emitting human-readable raw edges + gestures over the WebSocket (`pressed`/`released`/`single_press`/`long_press`, later `double_press`/`triple_press` with a `count` payload). The HA companion integration maps these to the emerging Matter/HA-standard event types (`press_start`/`press_end`/`long_press_start`/`long_press_end`/`multi_press_end`) in `event_data`, so the gateway never needs to know about Matter. Blueprints consume the friendly names via clean state triggers — no timing logic in YAML.

**Tech Stack:** Python 3.11 (asyncio) gateway, Home Assistant custom integration (Python), HA automation blueprints (YAML). Tests: pytest / pytest-asyncio.

**Two repos:**
- **Gateway** (this repo): `/Users/markminnoye/git/IPBuilding Gateway` — branch off `main`.
- **Companion integration**: `/Users/markminnoye/git/ha-ipbuilding-gateway` — branch off `main`.

**Pre-flight (done by the human, not in this plan):** create a feature branch in *each* repo before starting (e.g. `feat/button-single-press`).

---

## Background & key facts (read before starting)

- The IP1100PoE wire only carries two edges: `press` (0x01) and `release` (0x00). `long_press` is **derived in the gateway** by a per-button asyncio timer armed on press, fired at `hold_threshold_s` (default **1.5 s**, from `getButtons.func2.holdSeconds`). See `gateway/gateway_api.py:563-627` and `gateway/installation.py:120-167`.
- **The bug Phase 1 fixes:** `button_standard.yaml` waits only 600 ms after `press` to disambiguate, but the default long-press threshold is 1.5 s. For default-threshold buttons the 600 ms `wait_for_trigger` times out *before* `long_press` is emitted, so the press-action always runs and the long-press action never fires. Moving disambiguation into the gateway removes this timing race entirely.
- The companion **drops any action not in `_BUTTON_EVENT_TYPES`** (`custom_components/ha_ipbuilding_gateway/event.py:106-113`). New actions MUST be added there or they vanish silently.
- `released` is kept as an always-present raw edge — `button_dim` (flip-on-release) and `button_cover` (release-to-stop) depend on it. We do NOT collapse it into the Matter model on the wire.
- Decided design choices (locked):
  - **#2 naming:** simple names on the wire, Matter/HA mapping in the integration layer.
  - **#3 multi-press:** discrete `double_press`/`triple_press` names (Shelly-style) **plus** a `count` payload field.
  - **#4 timing:** `single_press` fires on `release`. Multi-press is **opt-in per button** so non-multi-press buttons keep firing `single_press` immediately on release forever.

## File Structure

### Phase 1 — Gateway (`/Users/markminnoye/git/IPBuilding Gateway`)
- Modify: `gateway/gateway_api.py` (`_on_button_event` release branch — emit `single_press`)
- Modify: `tests/test_button_timing.py` (assert `single_press` in sequence)
- Modify: `ipbuilding_gateway/config.yaml` (`version`), `ipbuilding_gateway/CHANGELOG.md`

### Phase 1 — Companion (`/Users/markminnoye/git/ha-ipbuilding-gateway`)
- Modify: `custom_components/ha_ipbuilding_gateway/event.py` (`_BUTTON_EVENT_TYPES`, `_ACTION_TO_BUS_EVENT`, standard mapping in `event_data`)
- Modify: `custom_components/ha_ipbuilding_gateway/device_trigger.py` (add `single_pressed` trigger)
- Modify: `custom_components/ha_ipbuilding_gateway/strings.json` + `translations/en.json` (trigger label)
- Modify: `custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_standard.yaml` (rewrite to 2 clean triggers)
- Modify: `tests/test_device_trigger.py`
- Modify: `custom_components/ha_ipbuilding_gateway/manifest.json` (`version`), `CHANGELOG.md`

### Phase 2 — Gateway
- Modify: `gateway/installation.py` (`ButtonConfig`: `multi_press`, `multi_press_window_ms`)
- Modify: `gateway/gateway_api.py` (`_ButtonState`: inter-click fields; release branch: arm inter-click timer; new `_fire_single_or_multi`)
- Modify: `tests/test_button_timing.py`

### Phase 2 — Companion
- Modify: `custom_components/ha_ipbuilding_gateway/event.py` (add `double_press`/`triple_press`, pass `count` through)
- Modify: `custom_components/ha_ipbuilding_gateway/device_trigger.py` (add `double_pressed`/`triple_pressed`)
- Modify: `strings.json` + `translations/en.json`
- Create: `custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_multi.yaml`
- Modify: `tests/test_device_trigger.py`
- Version bumps + changelogs (both repos)

---

# PHASE 1 — `single_press` (bugfix)

## Task 1: Gateway emits `single_press` on short release

**Files:**
- Modify: `gateway/gateway_api.py:594-600` (release branch of `_on_button_event`)
- Test: `tests/test_button_timing.py`

- [ ] **Step 1: Write the failing tests**

Add to `class TestButtonStateMachine` in `tests/test_button_timing.py`:

```python
    @pytest.mark.asyncio
    async def test_short_press_emits_single_press_before_release(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.5}
        ])
        api = self._make_capturing_api(inst)

        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")

        actions = [m["action"] for m in api._captured]
        # single_press is emitted on release when no long_press fired,
        # before the raw release edge.
        assert actions == ["press", "single_press", "release"]

    @pytest.mark.asyncio
    async def test_long_press_does_not_emit_single_press(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.5}
        ])
        api = self._make_capturing_api(inst)

        self._press(api, "2f8185190000df")
        self._run_long_press_timer(api, "2f8185190000df")
        self._release(api, "2f8185190000df")

        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "long_press", "release"]
        assert "single_press" not in actions
```

Also update the existing `test_short_press_no_long_press` (currently asserts `["press", "release"]`) to expect `["press", "single_press", "release"]`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py -v -k "single_press or no_long_press"`
Expected: FAIL — `single_press` not present in captured actions.

- [ ] **Step 3: Implement the release branch**

In `gateway/gateway_api.py`, replace the `else: # release` branch (lines 594-600):

```python
        else:  # release
            if state.long_press_handle is not None:
                state.long_press_handle.cancel()
                state.long_press_handle = None
            was_long = state.long_press_fired
            state.press_started_at = None
            state.long_press_fired = False
            # A release with no preceding long_press is a short click.
            # Emit single_press *before* the raw release edge so consumers
            # that key on the gesture see it first; release stays as the
            # always-present raw edge for dim/cover blueprints.
            if not was_long:
                self._broadcast_button(id_hex, "single_press")
            self._broadcast_button(id_hex, "release")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py -v`
Expected: PASS (all, including the updated `test_short_press_no_long_press`).

- [ ] **Step 5: Update the `_on_button_event` docstring**

In `gateway/gateway_api.py:563-571`, append to the docstring:
`On release we cancel the timer; if no long_press fired we emit single_press (the short click), then always emit release.`

- [ ] **Step 6: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add gateway/gateway_api.py tests/test_button_timing.py
git commit -m "feat(gateway): emit single_press on short release"
```

## Task 2: Gateway version bump + changelog

**Files:**
- Modify: `ipbuilding_gateway/config.yaml:version`
- Modify: `ipbuilding_gateway/CHANGELOG.md`

- [ ] **Step 1: Bump version** in `ipbuilding_gateway/config.yaml` from `"1.0.4"` to `"1.1.0"` (minor: new optional wire event, backward-compatible).

- [ ] **Step 2: Add changelog entry** at the top of the version list in `ipbuilding_gateway/CHANGELOG.md`:

```markdown
## 1.1.0

### Added
- Buttons emit a new `single_press` event on the WebSocket when a press is
  released without crossing the long-press threshold. The raw `pressed`/
  `released` edges and `long_press` are unchanged. Companion ≥ 1.3.0 maps
  this to the HA-standard `press_end`.
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add ipbuilding_gateway/config.yaml ipbuilding_gateway/CHANGELOG.md
git commit -m "release: gateway v1.1.0 — single_press event"
```

## Task 3: Companion accepts `single_press` and maps to HA standard

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/event.py:41,46-50,114-118`
- Test: `tests/test_device_trigger.py` (or a new `tests/test_event_actions.py`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_event_actions.py`:

```python
"""Phase 1: the EventEntity accepts single_press and tags the HA-standard type."""
from custom_components.ha_ipbuilding_gateway import event as ev


def test_single_press_is_a_known_event_type():
    assert "single_press" in ev._BUTTON_EVENT_TYPES


def test_single_press_maps_to_bus_event():
    assert ev._ACTION_TO_BUS_EVENT["single_press"] == "button_single_pressed"


def test_standard_event_type_mapping():
    assert ev._STANDARD_EVENT_TYPE["single_press"] == "press_end"
    assert ev._STANDARD_EVENT_TYPE["long_press"] == "long_press_start"
    assert ev._STANDARD_EVENT_TYPE["release"] == "long_press_end"
    assert ev._STANDARD_EVENT_TYPE["press"] == "press_start"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_event_actions.py -v`
Expected: FAIL — `single_press` not in `_BUTTON_EVENT_TYPES`; `_STANDARD_EVENT_TYPE` undefined.

- [ ] **Step 3: Add `single_press` and the standard mapping** in `event.py`

Line 41 — add `single_press`:

```python
_BUTTON_EVENT_TYPES = ["press", "single_press", "long_press", "release"]
```

Lines 46-50 — add the bus-event mapping:

```python
_ACTION_TO_BUS_EVENT: dict[str, str] = {
    "press": "button_pressed",
    "single_press": "button_single_pressed",
    "long_press": "button_long_pressed",
    "release": "button_released",
}
```

After `_ACTION_TO_BUS_EVENT`, add the Matter/HA-standard mapping (decision #2 — mapping lives in the integration, not the gateway):

```python
# Map our friendly wire actions to the emerging HA/Matter standard button
# event types (architecture discussion #1377). Exposed in event_data as
# ``standard_event_type`` so automations can be written against the standard
# without the gateway needing to know about Matter.
_STANDARD_EVENT_TYPE: dict[str, str] = {
    "press": "press_start",
    "single_press": "press_end",
    "long_press": "long_press_start",
    "release": "long_press_end",
}
```

- [ ] **Step 4: Include the standard type in event_data**

In `_handle_button_event` (lines 114-118), extend `event_data`:

```python
            event_data = {
                "hardware_id": self._hardware_id,
                "action": action,
            }
            standard = _STANDARD_EVENT_TYPE.get(action)
            if standard is not None:
                event_data["standard_event_type"] = standard
            self._trigger_event(action, event_data)
            self.async_write_ha_state()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_event_actions.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/event.py tests/test_event_actions.py
git commit -m "feat(event): accept single_press, tag HA-standard event type"
```

## Task 4: Companion device trigger for `single_pressed`

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/device_trigger.py:30-48`
- Modify: `custom_components/ha_ipbuilding_gateway/strings.json`, `translations/en.json`
- Test: `tests/test_device_trigger.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_device_trigger.py`:

```python
def test_single_pressed_trigger_type_registered():
    from custom_components.ha_ipbuilding_gateway import device_trigger as dt
    assert "single_pressed" in dt.TRIGGER_TYPES
    assert dt._TRIGGER_TYPE_TO_EVENT["single_pressed"] == dt.EVENT_BUTTON_SINGLE_PRESSED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_device_trigger.py -v -k single_pressed`
Expected: FAIL — `single_pressed` not in `TRIGGER_TYPES`.

- [ ] **Step 3: Add the trigger type and event mapping** in `device_trigger.py`

Lines 30-37:

```python
TRIGGER_TYPE_PRESSED = "pressed"
TRIGGER_TYPE_SINGLE_PRESSED = "single_pressed"
TRIGGER_TYPE_LONG_PRESSED = "long_pressed"
TRIGGER_TYPE_RELEASED = "released"
TRIGGER_TYPES = {
    TRIGGER_TYPE_PRESSED,
    TRIGGER_TYPE_SINGLE_PRESSED,
    TRIGGER_TYPE_LONG_PRESSED,
    TRIGGER_TYPE_RELEASED,
}
```

Lines 40-48:

```python
EVENT_BUTTON_PRESSED = f"{DOMAIN}.button_pressed"
EVENT_BUTTON_SINGLE_PRESSED = f"{DOMAIN}.button_single_pressed"
EVENT_BUTTON_LONG_PRESSED = f"{DOMAIN}.button_long_pressed"
EVENT_BUTTON_RELEASED = f"{DOMAIN}.button_released"

_TRIGGER_TYPE_TO_EVENT: dict[str, str] = {
    TRIGGER_TYPE_PRESSED: EVENT_BUTTON_PRESSED,
    TRIGGER_TYPE_SINGLE_PRESSED: EVENT_BUTTON_SINGLE_PRESSED,
    TRIGGER_TYPE_LONG_PRESSED: EVENT_BUTTON_LONG_PRESSED,
    TRIGGER_TYPE_RELEASED: EVENT_BUTTON_RELEASED,
}
```

- [ ] **Step 4: Add the trigger label** to `strings.json` and `translations/en.json`

Under `device_automation.trigger_type`, add (matching the existing key style):

```json
"single_pressed": "{entity_name} single pressed"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_device_trigger.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/device_trigger.py \
        custom_components/ha_ipbuilding_gateway/strings.json \
        custom_components/ha_ipbuilding_gateway/translations/en.json \
        tests/test_device_trigger.py
git commit -m "feat(device_trigger): add single_pressed trigger"
```

## Task 5: Rewrite `button_standard.yaml` to two clean triggers

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_standard.yaml`

- [ ] **Step 1: Replace the trigger + action sections**

Replace the `trigger:` and `action:` blocks (current lines 76-124) with — note the header comment version bump to `# ipbuilding_blueprint_version: 7`:

```yaml
mode: single

trigger:
  # The gateway now classifies the press: single_press fires on the
  # release of a short tap, long_press fires at the hold threshold while
  # still held. They are mutually exclusive, so no wait/timeout is needed.
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "single_press"
    not_from:
      - unavailable
      - unknown
    id: short
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "long_press"
    not_from:
      - unavailable
      - unknown
    id: long

action:
  - choose:
      - conditions:
          - condition: trigger
            id: long
        sequence: !input long_press_action
    default: !input press_action
```

- [ ] **Step 2: Update the blueprint description**

In the `description:` (lines 4-24) remove the entire `wait_for_trigger`/600 ms/`~1,5 s` explanation (it no longer applies) and replace with:

```
Press-vs-long-press is decided in the gateway: a short tap emits
single_press on release, a hold emits long_press at the threshold.
The two are mutually exclusive, so this blueprint just maps each to a
full action sequence — no timing logic. Leave the long-press actions
empty to react to short presses only.
```

Also bump the leading `**Blueprint-versie: 6.**` to `**Blueprint-versie: 7.**`.

- [ ] **Step 3: Manual verification (documented, run by human after install)**

After installing companion ≥ 1.3.0 + gateway ≥ 1.1.0 and reloading the blueprint:
1. Short-tap a mapped button → only the press action runs.
2. Hold the same button past the threshold → only the long-press action runs.
Expected: never both; long press now works even on default-threshold (1.5 s) buttons.

- [ ] **Step 4: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_standard.yaml
git commit -m "feat(blueprint): button_standard uses single_press/long_press triggers (v7)"
```

## Task 6: Companion version bump + changelog

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/manifest.json:version`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump** `manifest.json` version from `"1.2.2"` to `"1.3.0"`.

- [ ] **Step 2: Add changelog entry** at the top of `CHANGELOG.md`:

```markdown
## 1.3.0

### Added
- `single_press` button event + `single_pressed` device trigger.
- Button events now carry `standard_event_type` in event_data, mapping to
  the HA/Matter standard (press_start/press_end/long_press_start/long_press_end).

### Changed
- `button_standard` blueprint (v7) now triggers on `single_press`/`long_press`
  directly — removes the 600 ms `wait_for_trigger` race that broke long press
  on default-threshold (1.5 s) buttons. Requires gateway ≥ 1.1.0.
```

- [ ] **Step 3: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/manifest.json CHANGELOG.md
git commit -m "release: companion v1.3.0 — single_press + button_standard v7"
```

## Phase 1 gate

- [ ] Gateway: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/ -q` → all pass.
- [ ] Companion: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/ -q` → all pass.
- [ ] Manual: short/long press verified on a real default-threshold button (Task 5 Step 3).
- [ ] Backward-compat: existing automations using `press`/`pressed` still fire (those events are unchanged).

---

# PHASE 2 — `double_press` / `triple_press` (opt-in, inter-click window)

> Phase 2 is additive and must not change behaviour for buttons that do not opt in. Default per-button: `multi_press = false` → identical to Phase 1 (immediate `single_press` on release).

## Task 7: Per-button multi-press config

**Files:**
- Modify: `gateway/installation.py:126-167` (`ButtonConfig`)
- Test: `tests/test_button_timing.py` (`class TestButtonThreshold` area)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_button_timing.py`:

```python
class TestMultiPressConfig:
    def test_multi_press_defaults_off(self) -> None:
        inst = _make_installation([{"id": "2f8185190000df"}])
        btn = inst.button_by_id("2f8185190000df")
        assert btn.multi_press is False
        assert btn.multi_press_window_ms == 350

    def test_multi_press_from_config(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "multi_press": True, "multi_press_window_ms": 250}
        ])
        btn = inst.button_by_id("2f8185190000df")
        assert btn.multi_press is True
        assert btn.multi_press_window_ms == 250
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py::TestMultiPressConfig -v`
Expected: FAIL — `ButtonConfig` has no `multi_press`.

- [ ] **Step 3: Add fields to `ButtonConfig`**

After `hold_threshold_s` (line 143) add:

```python
    multi_press: bool = False
    multi_press_window_ms: int = 350
```

In `to_dict` (lines 145-154) add:

```python
            "multi_press": self.multi_press,
            "multi_press_window_ms": self.multi_press_window_ms,
```

In `from_dict` (lines 156-167) add:

```python
            multi_press=data.get("multi_press", False),
            multi_press_window_ms=int(data.get("multi_press_window_ms", 350)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py::TestMultiPressConfig -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add gateway/installation.py tests/test_button_timing.py
git commit -m "feat(gateway): per-button multi_press config"
```

## Task 8: Gateway inter-click state machine

**Files:**
- Modify: `gateway/gateway_api.py:49-62` (`_ButtonState`), `:594-609` (release + new callback)
- Test: `tests/test_button_timing.py`

- [ ] **Step 1: Write the failing tests**

Add to `class TestButtonStateMachine` a helper and tests. The inter-click timer is fired manually (same pattern as `_run_long_press_timer`):

```python
    def _run_multi_timer(self, api, id_hex: str) -> None:
        """Manually fire the inter-click window expiry callback."""
        api._fire_single_or_multi(id_hex)

    @pytest.mark.asyncio
    async def test_multi_press_disabled_emits_single_immediately(self) -> None:
        inst = _make_installation([{"id": "2f8185190000df", "multi_press": False}])
        api = self._make_capturing_api(inst)
        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "single_press", "release"]

    @pytest.mark.asyncio
    async def test_multi_press_single_after_window(self) -> None:
        inst = _make_installation([{"id": "2f8185190000df", "multi_press": True}])
        api = self._make_capturing_api(inst)
        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        # No single_press yet — waiting for a possible second click.
        assert [m["action"] for m in api._captured] == ["press", "release"]
        self._run_multi_timer(api, "2f8185190000df")
        emitted = [m for m in api._captured if m["action"] == "single_press"]
        assert emitted and emitted[-1]["count"] == 1

    @pytest.mark.asyncio
    async def test_multi_press_double(self) -> None:
        inst = _make_installation([{"id": "2f8185190000df", "multi_press": True}])
        api = self._make_capturing_api(inst)
        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        self._press(api, "2f8185190000df")   # second click within window
        self._release(api, "2f8185190000df")
        self._run_multi_timer(api, "2f8185190000df")
        emitted = [m for m in api._captured if m["action"] in ("single_press", "double_press", "triple_press")]
        assert emitted[-1]["action"] == "double_press"
        assert emitted[-1]["count"] == 2

    @pytest.mark.asyncio
    async def test_multi_press_long_press_bypasses_window(self) -> None:
        inst = _make_installation([{"id": "2f8185190000df", "multi_press": True, "hold_threshold_s": 0.1}])
        api = self._make_capturing_api(inst)
        self._press(api, "2f8185190000df")
        self._run_long_press_timer(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "long_press", "release"]
        assert all(a not in ("single_press", "double_press") for a in actions)
```

Note: `_broadcast_button` in the capture helper currently takes `(id_hex, action)`. Phase 2 adds an optional `count`. Update the test capture helper `_capture` signature in `_make_capturing_api` to accept it:

```python
        def _capture(self_api, id_hex: str, action: str, count: int | None = None) -> None:
            entry = {"id": id_hex, "action": action}
            if count is not None:
                entry["count"] = count
            api._captured.append(entry)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py -v -k "multi_press"`
Expected: FAIL — `_fire_single_or_multi` undefined; counts absent.

- [ ] **Step 3: Extend `_ButtonState`**

In `gateway/gateway_api.py` `_ButtonState` (lines 49-62) add:

```python
    click_count: int = 0
    multi_handle: asyncio.TimerHandle | None = None
```

- [ ] **Step 4: Add `_broadcast_button` count support**

Change `_broadcast_button` (lines 611-619) to accept an optional count:

```python
    def _broadcast_button(self, id_hex: str, action: str, count: int | None = None) -> None:
        """Send a button_event to all WS clients. Coroutine, scheduled."""
        log.info("BUTTON %s: %s%s", id_hex, action, f" x{count}" if count else "")
        msg: dict[str, Any] = {
            "type": "button_event",
            "id": id_hex,
            "action": action,
        }
        if count is not None:
            msg["count"] = count
        asyncio.create_task(self._broadcast(msg))
```

- [ ] **Step 5: Rewrite the release branch + add the window callback**

Replace the `else: # release` branch with:

```python
        else:  # release
            if state.long_press_handle is not None:
                state.long_press_handle.cancel()
                state.long_press_handle = None
            was_long = state.long_press_fired
            state.press_started_at = None
            state.long_press_fired = False
            if was_long:
                # A hold never participates in multi-press; reset and emit
                # only the raw release edge (long_press already fired).
                state.click_count = 0
                if state.multi_handle is not None:
                    state.multi_handle.cancel()
                    state.multi_handle = None
                self._broadcast_button(id_hex, "release")
                return
            btn = self._button_config(id_hex)
            if btn is None or not btn.multi_press:
                # Opt-out path (Phase 1 behaviour): immediate single_press.
                self._broadcast_button(id_hex, "single_press")
                self._broadcast_button(id_hex, "release")
                return
            # Multi-press path: count this click and (re)arm the window.
            state.click_count += 1
            if state.multi_handle is not None:
                state.multi_handle.cancel()
            loop = asyncio.get_running_loop()
            state.multi_handle = loop.call_later(
                btn.multi_press_window_ms / 1000.0,
                self._fire_single_or_multi,
                id_hex,
            )
            self._broadcast_button(id_hex, "release")
```

Add the new callback after `_fire_long_press` (after line 609):

```python
    _MULTI_ACTION = {1: "single_press", 2: "double_press", 3: "triple_press"}

    def _fire_single_or_multi(self, id_hex: str) -> None:
        """Inter-click window expired: emit single/double/triple_press."""
        state = self._button_state.get(id_hex)
        if state is None or state.click_count == 0:
            return
        count = state.click_count
        state.click_count = 0
        state.multi_handle = None
        # Counts above 3 cap at triple_press but report the true count.
        action = self._MULTI_ACTION.get(count, "triple_press")
        self._broadcast_button(id_hex, action, count=count)
```

Add the `_button_config` helper next to `_button_threshold` (after line 627):

```python
    def _button_config(self, id_hex: str):
        """Return the ButtonConfig for a button id, or None."""
        installation = self._cfg.installation
        if installation is None:
            return None
        return installation.button_by_id(id_hex)
```

Also extend the `press` branch: a fresh press while a multi-press window is open must NOT reset `click_count` (it's the second/third click). The existing press branch (lines 580-593) cancels `long_press_handle` and resets `long_press_fired` — that is fine; it must NOT touch `click_count` or `multi_handle`. Confirm no new code needed there beyond leaving `click_count` alone.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd "/Users/markminnoye/git/IPBuilding Gateway" && python -m pytest tests/test_button_timing.py -v`
Expected: PASS (all, including Phase 1 tests — opt-out path unchanged).

- [ ] **Step 7: Commit**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add gateway/gateway_api.py tests/test_button_timing.py
git commit -m "feat(gateway): opt-in double/triple press via inter-click window"
```

## Task 9: Companion accepts `double_press`/`triple_press` + count

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/event.py`
- Test: `tests/test_event_actions.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_event_actions.py`:

```python
def test_multi_press_event_types_known():
    assert "double_press" in ev._BUTTON_EVENT_TYPES
    assert "triple_press" in ev._BUTTON_EVENT_TYPES


def test_multi_press_standard_mapping():
    assert ev._STANDARD_EVENT_TYPE["double_press"] == "multi_press_end"
    assert ev._STANDARD_EVENT_TYPE["triple_press"] == "multi_press_end"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_event_actions.py -v -k multi`
Expected: FAIL.

- [ ] **Step 3: Add the event types, bus events, standard mapping, and count passthrough** in `event.py`

`_BUTTON_EVENT_TYPES`:

```python
_BUTTON_EVENT_TYPES = [
    "press", "single_press", "double_press", "triple_press",
    "long_press", "release",
]
```

`_ACTION_TO_BUS_EVENT` — add:

```python
    "double_press": "button_double_pressed",
    "triple_press": "button_triple_pressed",
```

`_STANDARD_EVENT_TYPE` — add:

```python
    "double_press": "multi_press_end",
    "triple_press": "multi_press_end",
```

In `_handle_button_event`, after the `standard_event_type` block, pass `count` through when the gateway sent it:

```python
            count = data.get("count")
            if count is not None:
                event_data["count"] = count
```

(`data` is the coordinator payload; the gateway adds `count` for multi-press frames — see gateway Task 8 Step 4.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_event_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/event.py tests/test_event_actions.py
git commit -m "feat(event): accept double/triple_press with count"
```

## Task 10: Companion device triggers for double/triple

**Files:**
- Modify: `custom_components/ha_ipbuilding_gateway/device_trigger.py`
- Modify: `strings.json`, `translations/en.json`
- Test: `tests/test_device_trigger.py`

- [ ] **Step 1: Write the failing test**

```python
def test_multi_press_trigger_types_registered():
    from custom_components.ha_ipbuilding_gateway import device_trigger as dt
    assert "double_pressed" in dt.TRIGGER_TYPES
    assert "triple_pressed" in dt.TRIGGER_TYPES
    assert dt._TRIGGER_TYPE_TO_EVENT["double_pressed"] == dt.EVENT_BUTTON_DOUBLE_PRESSED
    assert dt._TRIGGER_TYPE_TO_EVENT["triple_pressed"] == dt.EVENT_BUTTON_TRIPLE_PRESSED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_device_trigger.py -v -k multi_press`
Expected: FAIL.

- [ ] **Step 3: Add the trigger types, events, and mapping** in `device_trigger.py`

Add constants:

```python
TRIGGER_TYPE_DOUBLE_PRESSED = "double_pressed"
TRIGGER_TYPE_TRIPLE_PRESSED = "triple_pressed"
```

Add to `TRIGGER_TYPES` set, add:

```python
EVENT_BUTTON_DOUBLE_PRESSED = f"{DOMAIN}.button_double_pressed"
EVENT_BUTTON_TRIPLE_PRESSED = f"{DOMAIN}.button_triple_pressed"
```

Add to `_TRIGGER_TYPE_TO_EVENT`:

```python
    TRIGGER_TYPE_DOUBLE_PRESSED: EVENT_BUTTON_DOUBLE_PRESSED,
    TRIGGER_TYPE_TRIPLE_PRESSED: EVENT_BUTTON_TRIPLE_PRESSED,
```

- [ ] **Step 4: Add labels** to `strings.json` and `translations/en.json`:

```json
"double_pressed": "{entity_name} double pressed",
"triple_pressed": "{entity_name} triple pressed"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/markminnoye/git/ha-ipbuilding-gateway && python -m pytest tests/test_device_trigger.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/device_trigger.py \
        custom_components/ha_ipbuilding_gateway/strings.json \
        custom_components/ha_ipbuilding_gateway/translations/en.json \
        tests/test_device_trigger.py
git commit -m "feat(device_trigger): add double/triple_pressed triggers"
```

## Task 11: `button_multi.yaml` blueprint

**Files:**
- Create: `custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_multi.yaml`

- [ ] **Step 1: Create the blueprint**

```yaml
# ipbuilding_blueprint_version: 1
blueprint:
  name: IPBuilding wandknop — enkel/dubbel/lang
  description: >
    **Blueprint-versie: 1.** Maps single, double, triple and long press of
    an IPBuilding IP1100PoE wall button to separate action sequences.
    Requires the button to have multi-press enabled in the gateway
    (devices.json: `multi_press: true`). Note: enabling multi-press delays
    the single-press action by the inter-click window (default 350 ms).
    Leave any action empty to ignore that gesture.
  domain: automation
  source_url: https://github.com/markminnoye/ha-ipbuilding-gateway/blob/main/custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_multi.yaml
  input:
    button_entity:
      name: Knop
      selector:
        entity:
          filter:
            - domain: event
              integration: ha_ipbuilding_gateway
    single_action:
      name: Actie bij enkele druk
      default: []
      selector:
        action:
    double_action:
      name: Actie bij dubbele druk
      default: []
      selector:
        action:
    triple_action:
      name: Actie bij driedubbele druk
      default: []
      selector:
        action:
    long_action:
      name: Actie bij lange druk
      default: []
      selector:
        action:

mode: single

trigger:
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "single_press"
    not_from: [unavailable, unknown]
    id: single
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "double_press"
    not_from: [unavailable, unknown]
    id: double
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "triple_press"
    not_from: [unavailable, unknown]
    id: triple
  - platform: state
    entity_id: !input button_entity
    attribute: event_type
    to: "long_press"
    not_from: [unavailable, unknown]
    id: long

action:
  - choose:
      - conditions: [{condition: trigger, id: single}]
        sequence: !input single_action
      - conditions: [{condition: trigger, id: double}]
        sequence: !input double_action
      - conditions: [{condition: trigger, id: triple}]
        sequence: !input triple_action
      - conditions: [{condition: trigger, id: long}]
        sequence: !input long_action
```

- [ ] **Step 2: Manual verification (documented, run by human)**

Set `multi_press: true` for one test button in `devices.json`, restart the gateway, install the blueprint, then verify single/double/triple/long each fire only their own action.

- [ ] **Step 3: Commit**

```bash
cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_multi.yaml
git commit -m "feat(blueprint): add button_multi (single/double/triple/long)"
```

## Task 12: Version bumps + changelogs (Phase 2)

**Files:**
- `ipbuilding_gateway/config.yaml`, `ipbuilding_gateway/CHANGELOG.md`
- `custom_components/ha_ipbuilding_gateway/manifest.json`, `CHANGELOG.md`

- [ ] **Step 1: Gateway** → `config.yaml` `1.1.0` → `1.2.0`; changelog:

```markdown
## 1.2.0

### Added
- Opt-in `double_press`/`triple_press` events (per-button `multi_press` in
  devices.json). Multi-press frames carry a `count` field. Buttons without
  `multi_press` are unchanged (immediate single_press on release).
```

- [ ] **Step 2: Companion** → `manifest.json` `1.3.0` → `1.4.0`; changelog:

```markdown
## 1.4.0

### Added
- `double_press`/`triple_press` events + device triggers (with `count` in
  event_data, mapped to HA-standard `multi_press_end`).
- New `button_multi` blueprint for single/double/triple/long mapping.
  Requires gateway ≥ 1.2.0 and per-button `multi_press: true`.
```

- [ ] **Step 3: Commit (both repos)**

```bash
cd "/Users/markminnoye/git/IPBuilding Gateway"
git add ipbuilding_gateway/config.yaml ipbuilding_gateway/CHANGELOG.md
git commit -m "release: gateway v1.2.0 — double/triple press"

cd /Users/markminnoye/git/ha-ipbuilding-gateway
git add custom_components/ha_ipbuilding_gateway/manifest.json CHANGELOG.md
git commit -m "release: companion v1.4.0 — multi-press + button_multi blueprint"
```

## Phase 2 gate

- [ ] Both test suites green.
- [ ] A `multi_press: false` button behaves exactly as Phase 1 (immediate single_press) — verified by `test_multi_press_disabled_emits_single_immediately`.
- [ ] A `multi_press: true` button delays single_press by the window and fires double/triple correctly.
- [ ] Long press still bypasses the multi-press window.

---

## Notes / open decisions for the implementer

- **Counts > 3:** `_fire_single_or_multi` caps the action name at `triple_press` but reports the true `count`. If quadruple+ is ever needed, add `quadruple_press` to all three layers; the `count` field already carries the truth.
- **`standard_event_type` consumption:** Phase 1 only *exposes* the standard mapping in event_data; no blueprint consumes it yet. If/when HA ships the standardized generic button triggers (architecture #1377), revisit whether to expose them as first-class device triggers.
- **No gateway dependency on Matter:** the wire protocol stays friendly-named; all standard mapping is companion-side (decision #2).
