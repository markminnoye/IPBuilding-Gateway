# Pushbuttons/Detectors Nested Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nest pushbuttons and a detectors placeholder inside their owning `ModuleConfig` in `devices.json` (like `channels[]` already is), instead of a separate top-level `buttons[]` array, so no write-path can ever again silently drop configured buttons.

**Architecture:** Rename `ButtonConfig` → `PushbuttonConfig` and add a `channel` field (from the real `getButtons`/backupConfig `"index"`); add a new minimal `DetectorConfig` placeholder; give `ModuleConfig` `pushbuttons`/`detectors` list fields with type-conditional `to_dict()` (input modules serialize `pushbuttons`+`detectors`, relay/dimmer modules serialize `channels` — never both); make `InstallationConfig._parse()` read the nested arrays and reject the old flat top-level `"buttons"` format with a clear error; update every call site (`device_config.py`, `gateway_api.py`, `module_metadata.py`); ship a one-off migration script for the existing real `devices.json`.

**Tech Stack:** Python 3.14, dataclasses, pytest + pytest-asyncio, aiohttp (test client).

## Global Constraints

- The REST API contract to the HA companion (`device_type: "input"`, `semantic_type: "button"` in `GET`/`PATCH /api/v1/devices` responses) must NOT change — this is an internal storage-format rename only.
- `channel` is populated from discovery/metadata only — never PATCH-editable (`NORTHBOUND_PUSHBUTTON_FIELDS` stays `{name, room, active}`).
- Detectors are a schema placeholder only in this plan: no `device_type`, no API exposure, no UDP protocol decoding.
- No live field-bus calls anywhere in the migration script.
- Every renamed symbol (`ButtonConfig`→`PushbuttonConfig`, `button_by_id`→`pushbutton_by_id`, `button_threshold`→`pushbutton_threshold`, `installation.buttons`→`installation.pushbuttons`, `_buttons_by_id`→`_pushbuttons_by_id`, `apply_button_patch`→`apply_pushbutton_patch`, `validate_button_fields`→`validate_pushbutton_fields`, `NORTHBOUND_BUTTON_FIELDS`→`NORTHBOUND_PUSHBUTTON_FIELDS`, `extract_button_config`→`extract_pushbutton_config`, `extract_buttons_from_getbuttons`→`extract_pushbuttons_from_getbuttons`) must be renamed consistently everywhere it's referenced — grep for the old name after each task to confirm zero stragglers.

Reference spec: [docs/superpowers/specs/2026-07-13-pushbuttons-detectors-nested-schema-design.md](../specs/2026-07-13-pushbuttons-detectors-nested-schema-design.md)

---

### Task 1: `PushbuttonConfig` (renamed from `ButtonConfig`) + new `DetectorConfig`

**Files:**
- Modify: `gateway/installation.py:129-166` (the `ButtonConfig` class)
- Test: `tests/test_installation.py` (new test class at the end of the file)

**Interfaces:**
- Produces: `PushbuttonConfig(id, module_id="", channel=None, name="", room="", active=True, hold_threshold_s=DEFAULT_BUTTON_HOLD_THRESHOLD_S)` with `.to_dict()` (excludes `module_id`, includes `channel` only when not `None`) and `.from_dict(data, module_id="")` (classmethod, takes `module_id` as an explicit parameter — never reads it from `data`, since nesting supplies it going forward).
- Produces: `DetectorConfig(id, name="", room="", active=True)` with `.to_dict()`/`.from_dict(data)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_installation.py`:

```python
from gateway.installation import DetectorConfig, PushbuttonConfig


class TestPushbuttonConfig:
    def test_to_dict_excludes_module_id(self) -> None:
        btn = PushbuttonConfig(
            id="2f8185190000df",
            module_id="00:24:77:52:ad:aa",
            channel=1,
            name="Badkamer knop",
            room="1e verdieping",
            active=True,
            hold_threshold_s=1.5,
        )
        d = btn.to_dict()
        assert "module_id" not in d
        assert d == {
            "id": "2f8185190000df",
            "channel": 1,
            "name": "Badkamer knop",
            "room": "1e verdieping",
            "active": True,
            "hold_threshold_s": 1.5,
        }

    def test_to_dict_omits_channel_when_none(self) -> None:
        btn = PushbuttonConfig(id="abc")
        d = btn.to_dict()
        assert "channel" not in d

    def test_from_dict_takes_module_id_as_argument(self) -> None:
        raw = {
            "id": "2f8185190000df",
            "channel": 1,
            "name": "Badkamer knop",
            "room": "1e verdieping",
            "active": True,
            "hold_threshold_s": 1.5,
        }
        btn = PushbuttonConfig.from_dict(raw, module_id="00:24:77:52:ad:aa")
        assert btn.module_id == "00:24:77:52:ad:aa"
        assert btn.channel == 1
        assert btn.name == "Badkamer knop"

    def test_from_dict_defaults_channel_to_none(self) -> None:
        btn = PushbuttonConfig.from_dict({"id": "abc"}, module_id="mac1")
        assert btn.channel is None


class TestDetectorConfig:
    def test_to_dict_round_trip(self) -> None:
        det = DetectorConfig(id="det1", name="Voordeur", room="Inkomhal", active=False)
        d = det.to_dict()
        assert d == {"id": "det1", "name": "Voordeur", "room": "Inkomhal", "active": False}
        reloaded = DetectorConfig.from_dict(d)
        assert reloaded == det

    def test_from_dict_defaults(self) -> None:
        det = DetectorConfig.from_dict({"id": "det1"})
        assert det.name == ""
        assert det.room == ""
        assert det.active is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installation.py::TestPushbuttonConfig tests/test_installation.py::TestDetectorConfig -v`
Expected: FAIL — `ImportError: cannot import name 'DetectorConfig'` (and `PushbuttonConfig` doesn't exist yet either).

- [ ] **Step 3: Rename `ButtonConfig` → `PushbuttonConfig`, add `channel`, add `DetectorConfig`**

Replace the current `ButtonConfig` class (`gateway/installation.py:129-166`) with:

```python
@dataclass
class PushbuttonConfig:
    """A single physical pushbutton on an IP1100PoE input module.

    Pushbuttons are not channels — they have no entity_id of the form
    `{module_ip}-{ch}`. They are event sources on a module. The gateway
    uses :attr:`hold_threshold_s` to classify press→release timing into
    ``press`` vs ``long_press`` events; the value is normally seeded from
    ``getButtons.func2.holdSeconds`` on the input module (operator-bevestigd
    2026-06-16: dit is dezelfde drempel die IPBox hanteert).
    """

    id: str  # hardware hex, e.g. "2f8185190000df" (14 lowercase hex chars)
    module_id: str = ""  # parent module MAC — derived from nesting position, never read from the button's own dict
    channel: int | None = None  # physical port index; from getButtons/backupConfig "index"
    name: str = ""  # operator-friendly description, default from getButtons.descr
    room: str = ""  # from getButtons.gr
    active: bool = True
    hold_threshold_s: float = DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json. module_id is implied by nesting, so it is excluded."""
        d: dict = {
            "id": self.id,
            "name": self.name,
            "room": self.room,
            "active": self.active,
            "hold_threshold_s": self.hold_threshold_s,
        }
        if self.channel is not None:
            d["channel"] = self.channel
        return d

    @classmethod
    def from_dict(cls, data: dict, module_id: str = "") -> "PushbuttonConfig":
        return cls(
            id=data["id"],
            module_id=module_id,
            channel=data.get("channel"),
            name=data.get("name", ""),
            room=data.get("room", ""),
            active=data.get("active", True),
            hold_threshold_s=float(
                data.get("hold_threshold_s", DEFAULT_BUTTON_HOLD_THRESHOLD_S)
            ),
        )


@dataclass
class DetectorConfig:
    """A single physical detector on an IP1100PoE input module.

    Schema placeholder only — no runtime behaviour, no UDP protocol
    decoding, not exposed via the REST API. There is no confirmed
    ``getDetectors`` sample to base a richer schema on yet; this exists
    purely so a devices.json ``detectors[]`` array round-trips without
    data loss.
    """

    id: str
    name: str = ""
    room: str = ""
    active: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "room": self.room, "active": self.active}

    @classmethod
    def from_dict(cls, data: dict) -> "DetectorConfig":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            room=data.get("room", ""),
            active=data.get("active", True),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installation.py::TestPushbuttonConfig tests/test_installation.py::TestDetectorConfig -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add gateway/installation.py tests/test_installation.py
git commit -m "refactor: rename ButtonConfig to PushbuttonConfig, add channel field and DetectorConfig placeholder"
```

---

### Task 2: `ModuleConfig` — nested `pushbuttons`/`detectors`, type-conditional serialization

**Files:**
- Modify: `gateway/installation.py:172-221` (the `ModuleConfig` class)
- Test: `tests/test_installation_serialization.py` (new tests appended)

**Interfaces:**
- Consumes: `PushbuttonConfig`, `DetectorConfig` from Task 1.
- Produces: `ModuleConfig(..., pushbuttons: list[PushbuttonConfig] = [], detectors: list[DetectorConfig] = [])`. `to_dict()` returns `channels` key for non-`DeviceType.INPUT` modules, `pushbuttons`+`detectors` keys for `DeviceType.INPUT` modules (never both). `from_dict()` populates `pushbuttons`/`detectors` from nested arrays, passing the module's own `mac` as `module_id` to each `PushbuttonConfig.from_dict()`.

- [ ] **Step 1: Write the failing tests**

First, extend the existing `gateway.installation` import at the top of `tests/test_installation_serialization.py` (currently `from gateway.installation import ChannelConfig, ModuleConfig` at line 17) to also bring in the two new classes:

```python
from gateway.installation import ChannelConfig, DetectorConfig, ModuleConfig, PushbuttonConfig
```

Then append to the file:

```python
def test_relay_module_to_dict_has_channels_not_pushbuttons() -> None:
    mc = ModuleConfig(
        name="IP0200PoE", ip="10.10.1.30", type=DeviceType.RELAY,
        mac="00:24:77:52:ac:be",
        channels=[ChannelConfig(ch=0, name="Keuken LED", room="", semantic_type="light", active=True, max_watt=0)],
    )
    d = mc.to_dict()
    assert "channels" in d
    assert len(d["channels"]) == 1
    assert "pushbuttons" not in d
    assert "detectors" not in d


def test_input_module_to_dict_has_pushbuttons_and_detectors_not_channels() -> None:
    mc = ModuleConfig(
        name="IP1100PoE", ip="10.10.1.50", type=DeviceType.INPUT,
        mac="00:24:77:52:ad:aa",
        pushbuttons=[PushbuttonConfig(id="2f8185190000df", channel=1, name="Badkamer knop")],
        detectors=[DetectorConfig(id="det1", name="Voordeur")],
    )
    d = mc.to_dict()
    assert "channels" not in d
    assert len(d["pushbuttons"]) == 1
    assert d["pushbuttons"][0]["id"] == "2f8185190000df"
    assert len(d["detectors"]) == 1
    assert d["detectors"][0]["id"] == "det1"


def test_input_module_to_dict_empty_pushbuttons_and_detectors() -> None:
    mc = ModuleConfig(name="IP1100PoE", ip="10.10.1.50", type=DeviceType.INPUT, mac="00:24:77:52:ad:aa")
    d = mc.to_dict()
    assert d["pushbuttons"] == []
    assert d["detectors"] == []
    assert "channels" not in d


def test_module_from_dict_parses_nested_pushbuttons_with_module_id() -> None:
    raw = {
        "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
        "mac": "00:24:77:52:ad:aa",
        "pushbuttons": [{"id": "2f8185190000df", "channel": 1, "name": "Badkamer knop"}],
        "detectors": [{"id": "det1", "name": "Voordeur"}],
    }
    mc = ModuleConfig.from_dict(raw)
    assert len(mc.pushbuttons) == 1
    assert mc.pushbuttons[0].module_id == "00:24:77:52:ad:aa"
    assert mc.pushbuttons[0].channel == 1
    assert len(mc.detectors) == 1
    assert mc.detectors[0].id == "det1"


def test_module_from_dict_defaults_pushbuttons_and_detectors_to_empty() -> None:
    raw = {"name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
    mc = ModuleConfig.from_dict(raw)
    assert mc.pushbuttons == []
    assert mc.detectors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installation_serialization.py -v -k "pushbuttons or detectors"`
Expected: FAIL — `TypeError: ModuleConfig.__init__() got an unexpected keyword argument 'pushbuttons'`

- [ ] **Step 3: Implement `ModuleConfig` changes**

Replace `gateway/installation.py:172-221` with:

```python
@dataclass
class ModuleConfig:
    """A single field module (relay/dimmer/input)."""

    name: str
    ip: str
    type: DeviceType
    firmware: str = ""  # read via getSysSet during discovery
    model: str = ""    # factory product label, e.g. "IP200PoE"; optional
    mac: str = ""      # factory MAC (OUI 00:24:77); normalised lowercase
    channels: list[ChannelConfig] = field(default_factory=list)
    pushbuttons: list[PushbuttonConfig] = field(default_factory=list)
    detectors: list[DetectorConfig] = field(default_factory=list)
    # Runtime-only fields — NOT serialized to devices.json
    last_seen: str | None = None       # ISO timestamp of last ARP/HTTP contact
    last_seen_source: str = ""         # "arp" | "http" | "udp"

    @property
    def module_id(self) -> str:
        """Module identifier: normalised MAC. Alias for mac field."""
        return self.mac

    @property
    def ip_decimal(self) -> str:
        """Return the last octet of the IP as an integer (e.g. '30' from '10.10.1.30')."""
        return self.ip.rsplit(".", 1)[-1]

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json, excluding runtime-only fields.

        Type-conditional: an input module's entry shows pushbuttons/detectors
        (never channels); a relay/dimmer module's entry shows channels
        (never pushbuttons/detectors). A module entry only ever carries the
        fields relevant to its own type.
        """
        d: dict = {
            "name": self.name,
            "ip": self.ip,
            "type": self.type.value,
            "firmware": self.firmware,
            "model": self.model,
            "mac": self.mac,
        }
        if self.type == DeviceType.INPUT:
            d["pushbuttons"] = [b.to_dict() for b in self.pushbuttons]
            d["detectors"] = [x.to_dict() for x in self.detectors]
        else:
            d["channels"] = [c.to_dict() for c in self.channels]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleConfig":
        """Reconstruct from a devices.json dict entry, skipping runtime fields."""
        mac = data.get("mac", "")
        mc = cls(
            name=data.get("name", data.get("ip", "")),
            ip=data["ip"],
            type=DeviceType(data["type"]),
            firmware=data.get("firmware", ""),
            model=data.get("model", ""),
            mac=mac,
            channels=[ChannelConfig.from_dict(c) for c in data.get("channels", [])],
        )
        mc.pushbuttons = [
            PushbuttonConfig.from_dict(b, module_id=mac) for b in data.get("pushbuttons", [])
        ]
        mc.detectors = [DetectorConfig.from_dict(x) for x in data.get("detectors", [])]
        return mc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installation_serialization.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones — none of them use `DeviceType.INPUT` so they're unaffected by the type-conditional branch)

- [ ] **Step 5: Commit**

```bash
git add gateway/installation.py tests/test_installation_serialization.py
git commit -m "feat: nest pushbuttons/detectors inside ModuleConfig with type-conditional serialization"
```

---

### Task 3: `InstallationConfig._parse()` — nested parsing + old-format safety-guard

**Files:**
- Modify: `gateway/installation.py:224-464` (the `InstallationConfig` class: field names, `_parse()`, `button_by_id()`, `button_threshold()`)
- Test: `tests/test_installation.py` (new tests)

**Interfaces:**
- Consumes: `PushbuttonConfig`, `DetectorConfig`, `ModuleConfig` from Tasks 1–2.
- Produces: `InstallationConfig.pushbuttons: list[PushbuttonConfig]` (was `.buttons`), `InstallationConfig.pushbutton_by_id(id) -> PushbuttonConfig | None` (was `.button_by_id`), `InstallationConfig.pushbutton_threshold(id) -> float` (was `.button_threshold`). `_parse()` raises `InstallationError` if the raw dict has a top-level `"buttons"` key.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_installation.py`:

```python
class TestNestedPushbuttons:
    def test_parse_reads_nested_pushbuttons(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {
                    "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {"id": "2f8185190000df", "channel": 1, "name": "Badkamer knop", "room": "1e verdieping"}
                    ],
                }
            ]
        }
        p = tmp_path / "nested.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)

        assert len(cfg.pushbuttons) == 1
        btn = cfg.pushbutton_by_id("2f8185190000df")
        assert btn is not None
        assert btn.channel == 1
        assert btn.module_id == "00:24:77:52:ad:aa"

    def test_pushbutton_threshold_default_when_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"modules": []}), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S
        assert cfg.pushbutton_threshold("unknown") == DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def test_old_flat_buttons_format_rejected(self, tmp_path: Path) -> None:
        data = {
            "modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"}],
            "buttons": [{"id": "2f8185190000df", "module_id": "00:24:77:52:ad:aa"}],
        }
        p = tmp_path / "old_format.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="migrate_buttons_to_nested"):
            InstallationConfig.load(p)

    def test_duplicate_pushbutton_id_rejected(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {
                    "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {"id": "2f8185190000df", "name": "A"},
                        {"id": "2f8185190000df", "name": "B"},
                    ],
                }
            ]
        }
        p = tmp_path / "dup.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Duplicate"):
            InstallationConfig.load(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installation.py::TestNestedPushbuttons -v`
Expected: FAIL — `AttributeError: 'InstallationConfig' object has no attribute 'pushbuttons'`

- [ ] **Step 3: Implement `InstallationConfig` changes**

In `gateway/installation.py`, in the `InstallationConfig` dataclass field declarations (currently `gateway/installation.py:228-244`), rename:

```python
    modules: list[ModuleConfig] = field(default_factory=list)
    # Physical pushbuttons (IP1100PoE). Authoritative for hold_threshold_s and
    # event routing. Persisted nested under each input module's
    # "pushbuttons" key (see ModuleConfig.to_dict()).
    pushbuttons: list[PushbuttonConfig] = field(default_factory=list)

    # Derived indices — keyed by ipbox_id (IPBox component ID)
    _ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = field(default_factory=dict)
    # module_ip -> ModuleConfig
    _modules_by_ip: dict[str, ModuleConfig] = field(default_factory=dict)
    # module_id (MAC) -> ModuleConfig
    _modules_by_mac: dict[str, ModuleConfig] = field(default_factory=dict)
    # device_id -> (DeviceType, module_ip, channel)
    _device_id_to_entry: dict[str, tuple[DeviceType, str, int]] = field(default_factory=dict)
    # (DeviceType, module_ip, channel) -> device_id
    _entry_to_device_id: dict[tuple[DeviceType, str, int], str] = field(default_factory=dict)
    # pushbutton hardware id (lowercase) -> PushbuttonConfig
    _pushbuttons_by_id: dict[str, PushbuttonConfig] = field(default_factory=dict)
```

In `_parse()` (`gateway/installation.py:271-394`), replace the module-building loop's channel section end and the separate top-level buttons loop. First, add the old-format guard right after the `seen_device_ids: set[str] = set()` line and before `modules: list[ModuleConfig] = []`:

```python
        if "buttons" in raw:
            raise InstallationError(
                "Old flat devices.json format detected (top-level 'buttons' key). "
                "Run scripts/migrate_buttons_to_nested.py to convert it to "
                "modules[].pushbuttons[] before loading."
            )
```

Then replace the module-construction block (`mc = ModuleConfig(name=..., channels=channels)` through `modules_by_mac[mac_normalised] = mc`, currently `gateway/installation.py:356-368`) with:

```python
            pushbuttons: list[PushbuttonConfig] = []
            for btn_entry in mod.get("pushbuttons", []):
                btn_id = btn_entry.get("id")
                if not btn_id:
                    log.warning("Skipping pushbutton entry without id: %r", btn_entry)
                    continue
                key = btn_id.lower()
                if key in pushbuttons_by_id:
                    raise InstallationError(f"Duplicate pushbutton id {btn_id!r}")
                btn = PushbuttonConfig.from_dict(btn_entry, module_id=mac_normalised)
                pushbuttons.append(btn)
                pushbuttons_by_id[key] = btn

            detectors = [DetectorConfig.from_dict(d) for d in mod.get("detectors", [])]

            mc = ModuleConfig(
                name=mod.get("name", mod_ip),
                ip=mod_ip,
                type=dtype,
                firmware=firmware,
                model=mod.get("model", ""),
                mac=mac_normalised,
                channels=channels,
                pushbuttons=pushbuttons,
                detectors=detectors,
            )
            modules.append(mc)
            modules_by_ip[mod_ip] = mc
            if mac_normalised:
                modules_by_mac[mac_normalised] = mc
```

Add `pushbuttons: list[PushbuttonConfig] = []` and `pushbuttons_by_id: dict[str, PushbuttonConfig] = {}` next to the other accumulator declarations near the top of `_parse()` (alongside `modules_by_ip`/`modules_by_mac`), and delete the old separate top-level buttons-parsing loop (`# Parse top-level "buttons" list...` through `buttons_by_id[key] = btn`, currently `gateway/installation.py:370-385`) entirely — it's replaced by the per-module loop above.

Update the final `inst = cls(...)` construction (currently `gateway/installation.py:387-394`):

```python
        inst = cls(modules=modules, pushbuttons=pushbuttons)
        inst._ipbox_id_to_entry = ipbox_id_to_entry
        inst._modules_by_ip = modules_by_ip
        inst._modules_by_mac = modules_by_mac
        inst._device_id_to_entry = device_id_to_entry
        inst._entry_to_device_id = entry_to_device_id
        inst._pushbuttons_by_id = pushbuttons_by_id
        return inst
```

Finally, rename the two lookup methods (`gateway/installation.py:447-463`):

```python
    def pushbutton_by_id(self, button_id: str) -> PushbuttonConfig | None:
        """Look up a pushbutton by hardware id (case-insensitive). Returns None if unknown."""
        if not button_id:
            return None
        return self._pushbuttons_by_id.get(button_id.lower())

    def pushbutton_threshold(self, button_id: str) -> float:
        """Return the hold threshold (seconds) for a pushbutton.

        Falls back to :data:`DEFAULT_BUTTON_HOLD_THRESHOLD_S` when the
        pushbutton is not (yet) in the installation config. The timing
        detector in gateway_api.py uses this when no override is present.
        """
        btn = self.pushbutton_by_id(button_id)
        if btn is None:
            return DEFAULT_BUTTON_HOLD_THRESHOLD_S
        return btn.hold_threshold_s
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installation.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Confirm no stragglers of the old names**

Run: `grep -rn "ButtonConfig\|\.buttons\b\|_buttons_by_id\|button_by_id\|button_threshold" gateway/installation.py`
Expected: no output (everything renamed). Note `gateway_api.py`/`device_config.py`/`module_metadata.py` still reference the old names at this point — that's Tasks 4–6, don't touch them yet.

- [ ] **Step 6: Commit**

```bash
git add gateway/installation.py tests/test_installation.py
git commit -m "feat: parse nested pushbuttons/detectors per module, reject old flat buttons format"
```

---

### Task 4: `device_config.py` — rename to pushbutton_*, simplify `installation_to_raw_dict()`

**Files:**
- Modify: `gateway/device_config.py` (whole file, it's small)
- Modify: `tests/test_device_config.py` (fixture + assertions)

**Interfaces:**
- Consumes: `InstallationConfig.pushbutton_by_id()` from Task 3.
- Produces: `NORTHBOUND_PUSHBUTTON_FIELDS`, `validate_pushbutton_fields(fields) -> dict`, `apply_pushbutton_patch(installation, button_id, fields) -> None`. `installation_to_raw_dict(installation) -> {"modules": [...]}` (no separate `"buttons"` key — each module's own `to_dict()` already carries its pushbuttons).

- [ ] **Step 1: Write the failing test**

Replace `tests/test_device_config.py` in full:

```python
"""Tests for gateway.device_config — PATCH validation and mutation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    validate_channel_fields,
    validate_pushbutton_fields,
)
from gateway.installation import InstallationConfig


def _sample_installation() -> InstallationConfig:
    return InstallationConfig._parse({
        "modules": [
            {
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [
                    {
                        "ch": 0,
                        "name": "Keuken LED",
                        "room": "Keuken",
                        "semantic_type": "light",
                        "active": True,
                        "max_watt": 60,
                    }
                ],
            },
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "pushbuttons": [
                    {
                        "id": "2f8185190000df",
                        "name": "Badkamer",
                        "room": "1e verdieping",
                        "active": True,
                        "hold_threshold_s": 1.5,
                    }
                ],
            },
        ],
    })


class TestValidateChannelFields:
    def test_valid_fields(self) -> None:
        result = validate_channel_fields(
            {"name": "Lamp", "room": "Hal", "semantic_type": "switch", "active": False, "max_watt": 0}
        )
        assert result == {
            "name": "Lamp",
            "room": "Hal",
            "semantic_type": "switch",
            "active": False,
            "max_watt": 0,
        }

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"ip": "10.10.1.30"})
        assert exc.value.code == "unknown_field"
        assert "ip" in exc.value.details["fields"]

    def test_invalid_semantic_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"semantic_type": "sensor"})
        assert exc.value.code == "validation"

    def test_bad_active_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"active": "yes"})
        assert exc.value.code == "validation"

    def test_bad_max_watt_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"max_watt": -1})
        assert exc.value.code == "validation"


class TestValidatePushbuttonFields:
    def test_valid_fields(self) -> None:
        result = validate_pushbutton_fields({"name": "Knop", "room": "Bad", "active": True})
        assert result == {"name": "Knop", "room": "Bad", "active": True}

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_pushbutton_fields({"hold_threshold_s": 2.0})
        assert exc.value.code == "unknown_field"

    def test_channel_not_patchable(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_pushbutton_fields({"channel": 2})
        assert exc.value.code == "unknown_field"


class TestApplyPatches:
    def test_apply_channel_patch(self) -> None:
        inst = _sample_installation()
        apply_channel_patch(inst, "10.10.1.30", 0, {"room": "Eetkamer", "max_watt": 40})
        ch = inst.module_by_ip("10.10.1.30").channels[0]
        assert ch.room == "Eetkamer"
        assert ch.max_watt == 40
        assert ch.name == "Keuken LED"

    def test_apply_pushbutton_patch(self) -> None:
        inst = _sample_installation()
        apply_pushbutton_patch(inst, "2f8185190000df", {"name": "Douche", "active": False})
        btn = inst.pushbutton_by_id("2f8185190000df")
        assert btn is not None
        assert btn.name == "Douche"
        assert btn.active is False


class TestInstallationToRawDict:
    def test_pushbuttons_preserved_on_channel_patch_round_trip(self, tmp_path: Path) -> None:
        """Regression: channel PATCH serialization must keep the other module's pushbuttons."""
        inst = _sample_installation()
        apply_channel_patch(inst, "10.10.1.30", 0, {"room": "Nieuwe kamer"})

        raw = installation_to_raw_dict(inst)
        assert "buttons" not in raw
        input_module = next(m for m in raw["modules"] if m["type"] == "input")
        assert len(input_module["pushbuttons"]) == 1
        assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
        relay_module = next(m for m in raw["modules"] if m["type"] == "relay")
        assert relay_module["channels"][0]["room"] == "Nieuwe kamer"

        devices_file = tmp_path / "devices.json"
        devices_file.write_text(json.dumps(raw), encoding="utf-8")
        reloaded = InstallationConfig.load(devices_file)
        assert len(reloaded.pushbuttons) == 1
        assert reloaded.module_by_ip("10.10.1.30").channels[0].room == "Nieuwe kamer"

    def test_no_top_level_buttons_key(self) -> None:
        inst = InstallationConfig._parse({"modules": []})
        raw = installation_to_raw_dict(inst)
        assert raw == {"modules": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_pushbutton_patch'`

- [ ] **Step 3: Implement `device_config.py` changes**

Replace `gateway/device_config.py` in full:

```python
"""Northbound field validation and devices.json mutation for PATCH /api/v1/devices.

Pure validation + mutation logic, kept separate from auto_discovery (discovery
scope) and installation.py (parsing/schema only).
"""

from __future__ import annotations

from gateway.installation import InstallationConfig

NORTHBOUND_CHANNEL_FIELDS = {"name", "room", "semantic_type", "active", "max_watt"}
NORTHBOUND_PUSHBUTTON_FIELDS = {"name", "room", "active"}
SEMANTIC_TYPES = {"light", "fan", "cover", "switch", "plug"}


class DeviceConfigError(Exception):
    """Raised when PATCH body validation or mutation fails."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def validate_channel_fields(fields: dict) -> dict:
    """Validate and normalize northbound channel fields from a PATCH body."""
    unknown = set(fields.keys()) - NORTHBOUND_CHANNEL_FIELDS
    if unknown:
        raise DeviceConfigError(
            "unknown_field",
            f"Unknown field(s): {', '.join(sorted(unknown))}",
            {"fields": sorted(unknown)},
        )

    result: dict = {}
    for key, value in fields.items():
        if key == "name":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "name must be a string")
            result["name"] = value
        elif key == "room":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "room must be a string")
            result["room"] = value
        elif key == "semantic_type":
            if not isinstance(value, str) or value not in SEMANTIC_TYPES:
                raise DeviceConfigError(
                    "validation",
                    f"semantic_type must be one of {sorted(SEMANTIC_TYPES)}",
                    {"allowed": sorted(SEMANTIC_TYPES)},
                )
            result["semantic_type"] = value
        elif key == "active":
            if not isinstance(value, bool):
                raise DeviceConfigError("validation", "active must be a boolean")
            result["active"] = value
        elif key == "max_watt":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DeviceConfigError(
                    "validation",
                    "max_watt must be a non-negative integer",
                )
            result["max_watt"] = value
    return result


def validate_pushbutton_fields(fields: dict) -> dict:
    """Validate and normalize northbound pushbutton fields from a PATCH body."""
    unknown = set(fields.keys()) - NORTHBOUND_PUSHBUTTON_FIELDS
    if unknown:
        raise DeviceConfigError(
            "unknown_field",
            f"Unknown field(s): {', '.join(sorted(unknown))}",
            {"fields": sorted(unknown)},
        )

    result: dict = {}
    for key, value in fields.items():
        if key == "name":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "name must be a string")
            result["name"] = value
        elif key == "room":
            if not isinstance(value, str):
                raise DeviceConfigError("validation", "room must be a string")
            result["room"] = value
        elif key == "active":
            if not isinstance(value, bool):
                raise DeviceConfigError("validation", "active must be a boolean")
            result["active"] = value
    return result


def apply_channel_patch(
    installation: InstallationConfig,
    module_ip: str,
    ch: int,
    fields: dict,
) -> None:
    """Apply validated northbound fields to a channel in-memory."""
    mc = installation.module_by_ip(module_ip)
    if mc is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Module {module_ip!r} not found",
            {"module_ip": module_ip},
        )
    ch_cfg = next((c for c in mc.channels if c.ch == ch), None)
    if ch_cfg is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Channel {ch} not found on module {module_ip}",
            {"module_ip": module_ip, "channel": ch},
        )
    for key, value in fields.items():
        setattr(ch_cfg, key, value)


def apply_pushbutton_patch(
    installation: InstallationConfig,
    button_id: str,
    fields: dict,
) -> None:
    """Apply validated northbound fields to a pushbutton in-memory."""
    btn = installation.pushbutton_by_id(button_id)
    if btn is None:
        raise DeviceConfigError(
            "device_not_found",
            f"Pushbutton {button_id!r} not found",
            {"device_id": button_id},
        )
    for key, value in fields.items():
        setattr(btn, key, value)


def installation_to_raw_dict(installation: InstallationConfig) -> dict:
    """Serialize installation to devices.json shape.

    No separate "buttons" key: each module's own to_dict() already carries
    its nested pushbuttons/detectors (or channels), so there is no write
    path left that can independently forget to include them.
    """
    return {
        "modules": [m.to_dict() for m in installation.modules],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_config.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add gateway/device_config.py tests/test_device_config.py
git commit -m "refactor: rename button patch/validate functions to pushbutton, drop separate buttons key from installation_to_raw_dict"
```

---

### Task 5: `gateway_api.py` — rename call sites, add `channel` to API responses

**Files:**
- Modify: `gateway/gateway_api.py:33-45` (imports), `:447` (`_patch_device`), `:465-471` (`_patch_device`), `:716,760-766` (button timing), `:919-949` (`_build_device_list`), `:953-978` (`_device_dict_for_id`)
- Modify: `tests/test_gateway_api_devices_patch.py` (fixtures + assertions)

**Interfaces:**
- Consumes: `pushbutton_by_id`, `pushbutton_threshold`, `apply_pushbutton_patch`, `validate_pushbutton_fields` from Tasks 3–4.
- Produces: `GET`/`PATCH /api/v1/devices/{id}` responses for a pushbutton now include `"channel": <int|None omitted>` alongside the existing `device_type: "input"` / `semantic_type: "button"` (unchanged, per Global Constraints).

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_gateway_api_devices_patch.py` in full (only the button-related names/keys change; channel-patch tests are untouched):

```python
"""Tests for PATCH /api/v1/devices/{device_id}."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway import gateway_api
from gateway.auto_discovery import DiscoveryConfig
from gateway.device_config import DeviceConfigError
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache


def _make_installation(modules: list[dict[str, Any]] | None = None) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules or []})


def _write_devices_file(path: Path, installation: InstallationConfig) -> None:
    from gateway.device_config import installation_to_raw_dict

    path.write_text(json.dumps(installation_to_raw_dict(installation), indent=2), encoding="utf-8")


def _make_api(
    installation: InstallationConfig,
    devices_file: Path,
    discovery: DiscoveryConfig | None = None,
    metadata_cache: gateway_api.ModuleMetadataCache | None = None,
) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.discovery = discovery or DiscoveryConfig(lock_timeout_s=5.0)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(
        bus, reg, cfg, metadata_cache=metadata_cache
    )


@pytest.fixture
def channel_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP0200PoE",
            "ip": "10.10.1.30",
            "type": "relay",
            "mac": "00:24:77:52:ac:be",
            "channels": [
                {
                    "ch": 0,
                    "name": "Keuken LED",
                    "room": "Keuken",
                    "semantic_type": "light",
                    "active": True,
                    "max_watt": 60,
                }
            ],
        }
    ])


@pytest.fixture
def pushbutton_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP1100PoE",
            "ip": "10.10.1.50",
            "type": "input",
            "mac": "00:24:77:52:ad:aa",
            "pushbuttons": [
                {
                    "id": "2f8185190000df",
                    "channel": 1,
                    "name": "Badkamer knop",
                    "room": "1e verdieping",
                    "active": True,
                    "hold_threshold_s": 1.5,
                }
            ],
        }
    ])


class TestPatchDeviceHandler:
    @pytest.mark.asyncio
    async def test_patch_channel_success(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Eetkamer", "max_watt": 40})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with patch.object(api, "_broadcast", new_callable=AsyncMock) as mock_broadcast:
            response = await api._patch_device(request)

        assert response.status == 200
        body = json.loads(response.body)
        assert body["room"] == "Eetkamer"
        assert body["max_watt"] == 40

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert disk["modules"][0]["channels"][0]["room"] == "Eetkamer"
        assert disk["modules"][0]["channels"][0]["max_watt"] == 40
        assert api._cfg.installation.module_by_ip("10.10.1.30").channels[0].room == "Eetkamer"
        mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_pushbutton_success(
        self, tmp_path: Path, pushbutton_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, pushbutton_installation)
        api = _make_api(pushbutton_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "Douche knop", "active": False})
        request.match_info = {"device_id": "2f8185190000df"}

        response = await api._patch_device(request)
        body = json.loads(response.body)

        assert response.status == 200
        assert body["name"] == "Douche knop"
        assert body["active"] is False
        assert body["semantic_type"] == "button"
        assert body["channel"] == 1

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        input_module = next(m for m in disk["modules"] if m["type"] == "input")
        assert input_module["pushbuttons"][0]["name"] == "Douche knop"
        assert input_module["pushbuttons"][0]["active"] is False

    @pytest.mark.asyncio
    async def test_patch_preserves_pushbuttons_when_updating_other_module_channel(
        self, tmp_path: Path
    ) -> None:
        combined = _make_installation([
            {
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [
                    {
                        "ch": 0,
                        "name": "Keuken LED",
                        "room": "Keuken",
                        "semantic_type": "light",
                        "active": True,
                        "max_watt": 60,
                    }
                ],
            },
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "pushbuttons": [
                    {"id": "2f8185190000df", "name": "Badkamer knop", "room": "1e verdieping", "active": True}
                ],
            },
        ])
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, combined)
        api = _make_api(combined, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Hal"})
        request.match_info = {"device_id": "10.10.1.30-0"}
        await api._patch_device(request)

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert "buttons" not in disk
        input_module = next(m for m in disk["modules"] if m["type"] == "input")
        assert len(input_module["pushbuttons"]) == 1
        assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"

    @pytest.mark.asyncio
    async def test_patch_invalid_json(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(side_effect=ValueError("bad json"))
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "invalid_json"

    @pytest.mark.asyncio
    async def test_patch_unknown_field(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"ip": "10.10.1.99"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "unknown_field"

    @pytest.mark.asyncio
    async def test_patch_bad_semantic_type(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"semantic_type": "sensor"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "validation"

    @pytest.mark.asyncio
    async def test_patch_device_not_found(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "X"})
        request.match_info = {"device_id": "10.10.1.99-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_patch_write_locked(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file, DiscoveryConfig(lock_timeout_s=0.3))

        lock_file = tmp_path / "devices.json.lock"
        lock_fd = os.open(str(lock_file), os.O_RDONLY | os.O_CREAT, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            request = MagicMock()
            request.json = AsyncMock(return_value={"room": "Blocked"})
            request.match_info = {"device_id": "10.10.1.30-0"}

            with pytest.raises(gateway_api.ApiError) as exc:
                await api._patch_device(request)
            assert exc.value.status == 503
            assert exc.value.code == "write_locked"
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    @pytest.mark.asyncio
    async def test_patch_route_via_test_client(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)
        api._app = web.Application(middlewares=[api._api_error_middleware])
        api._app.router.add_patch("/api/v1/devices/{device_id}", api._patch_device)

        async with TestClient(TestServer(api._app)) as client:
            resp = await client.patch(
                "/api/v1/devices/10.10.1.30-0",
                json={"room": "Via HTTP"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["room"] == "Via HTTP"
            assert body["schema_version"] == 2


class TestPatchWsBroadcast:
    @pytest.mark.asyncio
    async def test_patch_broadcasts_snapshot(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        broadcast_called = asyncio.Event()
        original_broadcast = api._broadcast

        async def _capture_broadcast(msg: dict) -> None:
            if msg.get("type") == "snapshot":
                broadcast_called.set()
            await original_broadcast(msg)

        with patch.object(api, "_broadcast", side_effect=_capture_broadcast):
            request = MagicMock()
            request.json = AsyncMock(return_value={"room": "WS test"})
            request.match_info = {"device_id": "10.10.1.30-0"}
            await api._patch_device(request)

        await asyncio.wait_for(broadcast_called.wait(), timeout=1.0)


class TestPatchReviewFixes:
    @pytest.mark.asyncio
    async def test_patch_empty_body_rejected(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "empty_body"

    @pytest.mark.asyncio
    async def test_patch_device_not_found_during_write(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Gone"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with patch.object(
            api._writer,
            "read_modify_write",
            side_effect=DeviceConfigError(
                "device_not_found",
                "Channel 0 not found on module 10.10.1.30",
                {"module_ip": "10.10.1.30", "channel": 0},
            ),
        ):
            with pytest.raises(gateway_api.ApiError) as exc:
                await api._patch_device(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_patch_pushbutton_response_overlays_installation_over_meta_cache(
        self, tmp_path: Path, pushbutton_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, pushbutton_installation)
        mac = "00:24:77:52:ad:aa"
        meta_cache = ModuleMetadataCache()
        meta_cache._by_mac[mac] = ModuleMetadata(
            buttons=[
                {
                    "id": "2D2F8185190000DF",
                    "descr": "Stale HTTP name",
                    "gr": "Stale room",
                }
            ]
        )
        api = _make_api(pushbutton_installation, devices_file, metadata_cache=meta_cache)

        request = MagicMock()
        request.json = AsyncMock(
            return_value={"name": "Patched name", "room": "Patched room"}
        )
        request.match_info = {"device_id": "2f8185190000df"}

        with patch.object(api, "_broadcast", new_callable=AsyncMock):
            response = await api._patch_device(request)

        body = json.loads(response.body)
        assert body["name"] == "Patched name"
        assert body["room"] == "Patched room"
        assert body["schema_version"] == 2


class TestUnconfiguredPushbuttonHasChannelFromMeta:
    @pytest.mark.asyncio
    async def test_unconfigured_pushbutton_channel_from_index(self, tmp_path: Path) -> None:
        """A pushbutton only known via getButtons metadata still surfaces 'channel' (from 'index')."""
        installation = _make_installation([
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"}
        ])
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, installation)
        mac = "00:24:77:52:ad:aa"
        meta_cache = ModuleMetadataCache()
        meta_cache._by_mac[mac] = ModuleMetadata(
            buttons=[{"id": "2D2F8185190000DF", "index": 3, "descr": "Bureau L", "gr": "Bureau"}]
        )
        api = _make_api(installation, devices_file, metadata_cache=meta_cache)

        devices = api._build_device_list()
        pushbutton = next(d for d in devices if d["id"] == "2f8185190000df")
        assert pushbutton["channel"] == 3
        assert pushbutton["active"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gateway_api_devices_patch.py -v`
Expected: FAIL — `AttributeError: 'InstallationConfig' object has no attribute 'button_by_id'` (gateway_api.py still calls the old names)

- [ ] **Step 3: Implement `gateway_api.py` changes**

Update the import block (`gateway/gateway_api.py:33-40`):

```python
from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    validate_channel_fields,
    validate_pushbutton_fields,
)
```

In `_patch_device` (`gateway/gateway_api.py:447`), rename:

```python
        button_cfg = installation.pushbutton_by_id(device_id) if channel_entry is None else None
```

Further down in the same method (`gateway/gateway_api.py:463-472`):

```python
        else:
            try:
                validated = validate_pushbutton_fields(body)
            except DeviceConfigError as exc:
                raise ApiError(400, exc.code, exc.message, exc.details)

            def mutate(raw: dict) -> dict:
                inst = InstallationConfig._parse(raw)
                apply_pushbutton_patch(inst, device_id, validated)
                return installation_to_raw_dict(inst)
```

The `_ButtonState`/`_button_threshold` timing helpers (`gateway/gateway_api.py:716,760-766`) keep their own names (they're about press/release timing classification, not the config model) but the one internal call changes:

```python
    def _button_threshold(self, id_hex: str) -> float:
        """Look up the hold threshold for a button id (seconds)."""
        installation = self._cfg.installation
        if installation is None:
            from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S
            return DEFAULT_BUTTON_HOLD_THRESHOLD_S
        return installation.pushbutton_threshold(id_hex)
```

In `_build_device_list()` (`gateway/gateway_api.py:919-949`), replace the whole `if mc.type == DeviceType.INPUT:` block:

```python
            if mc.type == DeviceType.INPUT:
                meta = self._meta_cache.get(mc.mac)
                if meta is not None and meta.buttons:
                    for btn in meta.buttons:
                        raw_id = btn.get("id")
                        if not raw_id:
                            continue
                        device_id = normalize_button_hardware_id(str(raw_id))
                        meta_name = (
                            btn.get("descr")
                            or btn.get("name")
                            or f"Button {device_id}"
                        )
                        meta_room = btn.get("gr") or btn.get("room") or ""
                        cfg_btn = (
                            installation.pushbutton_by_id(device_id)
                            if installation
                            else None
                        )
                        entry: dict[str, Any] = {
                            "id": device_id,
                            "module_id": mc.mac,
                            "module_ip": mc.ip,
                            "name": cfg_btn.name or meta_name if cfg_btn else meta_name,
                            "room": cfg_btn.room if cfg_btn is not None else meta_room,
                            "semantic_type": "button",
                            "device_type": "input",
                            "channel": cfg_btn.channel if cfg_btn is not None else btn.get("index"),
                        }
                        if cfg_btn is not None:
                            entry["active"] = cfg_btn.active
                        devices.append(entry)
```

In `_device_dict_for_id()` (`gateway/gateway_api.py:953-978`):

```python
    def _device_dict_for_id(self, device_id: str) -> dict[str, Any] | None:
        """Return a single device dict (GET/PATCH shape) by device id."""
        for d in self._build_device_list():
            if d["id"] == device_id:
                return d

        installation = self._cfg.installation
        if installation is None:
            return None

        btn = installation.pushbutton_by_id(device_id)
        if btn is None:
            return None

        mc = installation.module_by_mac(btn.module_id)
        entry: dict[str, Any] = {
            "id": btn.id.lower(),
            "module_id": btn.module_id,
            "module_ip": mc.ip if mc is not None else "",
            "name": btn.name or f"Button {btn.id}",
            "room": btn.room,
            "semantic_type": "button",
            "device_type": "input",
            "active": btn.active,
            "channel": btn.channel,
        }
        return entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gateway_api_devices_patch.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Confirm no stragglers in gateway_api.py**

Run: `grep -n "button_by_id\|button_threshold\|apply_button_patch\|validate_button_fields\|ButtonConfig" gateway/gateway_api.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add gateway/gateway_api.py tests/test_gateway_api_devices_patch.py
git commit -m "refactor: rename button call sites to pushbutton, surface channel field in device API responses"
```

---

### Task 6: `module_metadata.py` — rename extraction functions, add `channel` from `index`

**Files:**
- Modify: `gateway/module_metadata.py:246-304`
- Test: `tests/test_module_metadata.py` (new tests appended — this function has zero existing test coverage today)

**Interfaces:**
- Consumes: `PushbuttonConfig` from Task 1.
- Produces: `extract_pushbutton_config(module_id, button_json, default_threshold_s=None) -> PushbuttonConfig` (was `extract_button_config`), `extract_pushbuttons_from_getbuttons(module_id, buttons_json) -> list[PushbuttonConfig]` (was `extract_buttons_from_getbuttons`). `PushbuttonConfig.channel` is populated from `button_json.get("index")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_module_metadata.py`:

```python
from gateway.module_metadata import (
    extract_pushbutton_config,
    extract_pushbuttons_from_getbuttons,
)


class TestExtractPushbuttonConfig:
    def test_extracts_channel_from_index(self) -> None:
        raw = {
            "index": 1, "id": "2D2F8185190000DF", "descr": "Badkamer", "gr": "Badkamer",
            "func1": {"ip": 30, "ch": 12, "outType": 0, "action": 2},
            "func2": {"ip": 30, "ch": 9, "outType": 0, "action": 2},
        }
        btn = extract_pushbutton_config("00:24:77:52:ad:aa", raw)
        assert btn.channel == 1
        assert btn.id == "2f8185190000df"
        assert btn.module_id == "00:24:77:52:ad:aa"
        assert btn.name == "Badkamer"
        assert btn.room == "Badkamer"

    def test_missing_index_leaves_channel_none(self) -> None:
        raw = {"id": "2D2F8185190000DF", "descr": "Badkamer"}
        btn = extract_pushbutton_config("mac1", raw)
        assert btn.channel is None

    def test_missing_id_raises(self) -> None:
        with pytest.raises(ValueError, match="no 'id'"):
            extract_pushbutton_config("mac1", {"descr": "no id"})

    def test_hold_threshold_from_func2(self) -> None:
        raw = {"id": "abc", "func2": {"holdSeconds": 2.5}}
        btn = extract_pushbutton_config("mac1", raw)
        assert btn.hold_threshold_s == 2.5


class TestExtractPushbuttonsFromGetbuttons:
    def test_extracts_multiple_with_channel(self) -> None:
        raw = [
            {"index": 0, "id": "2DE341851900001F", "descr": "Badkamer"},
            {"index": 1, "id": "2DD68C5219000050", "descr": "Slaapkamer"},
        ]
        buttons = extract_pushbuttons_from_getbuttons("mac1", raw)
        assert len(buttons) == 2
        assert buttons[0].channel == 0
        assert buttons[1].channel == 1

    def test_skips_invalid_entries(self, caplog) -> None:
        raw = [{"descr": "no id, invalid"}, {"index": 5, "id": "2Dabc123", "descr": "valid"}]
        buttons = extract_pushbuttons_from_getbuttons("mac1", raw)
        assert len(buttons) == 1
        assert buttons[0].channel == 5
```

`pytest` needs to be imported already at the top of `tests/test_module_metadata.py` for `pytest.raises` — check the existing import block and add `import pytest` only if it's missing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_module_metadata.py -v -k "Pushbutton"`
Expected: FAIL — `ImportError: cannot import name 'extract_pushbutton_config'`

- [ ] **Step 3: Implement `module_metadata.py` changes**

Replace `gateway/module_metadata.py:242-304` (the `# ButtonConfig extraction` section through the end of `extract_buttons_from_getbuttons`) with:

```python
# ---------------------------------------------------------------------------
# PushbuttonConfig extraction
# ---------------------------------------------------------------------------


def extract_pushbutton_config(
    module_id: str,
    button_json: dict[str, Any],
    default_threshold_s: float | None = None,
):
    """Convert a raw getButtons entry into a :class:`PushbuttonConfig`.

    ``channel`` is read from the wire ``"index"`` field. The hold threshold
    is seeded from ``func2.holdSeconds`` when present — this is the same
    drempelwaarde the IPBox hanteert for its long_press detection
    (operator-bevestigd 2026-06-16, IPBUILDING_KNOWLEDGE.md §12.7).
    """
    from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S, PushbuttonConfig

    raw_id = button_json.get("id")
    if not raw_id:
        raise ValueError(f"button entry has no 'id': {button_json!r}")
    btn_id = normalize_button_hardware_id(str(raw_id))

    func2 = button_json.get("func2") or {}
    hold = func2.get("holdSeconds")
    try:
        hold_s = float(hold) if hold is not None else (
            default_threshold_s if default_threshold_s is not None
            else DEFAULT_BUTTON_HOLD_THRESHOLD_S
        )
    except (TypeError, ValueError):
        hold_s = (
            default_threshold_s if default_threshold_s is not None
            else DEFAULT_BUTTON_HOLD_THRESHOLD_S
        )

    return PushbuttonConfig(
        id=btn_id,
        module_id=module_id,
        channel=button_json.get("index"),
        name=button_json.get("descr", "") or button_json.get("name", ""),
        room=button_json.get("gr", "") or button_json.get("room", ""),
        active=True,
        hold_threshold_s=hold_s,
    )


def extract_pushbuttons_from_getbuttons(
    module_id: str, buttons_json: list[dict[str, Any]]
) -> list:
    """Apply :func:`extract_pushbutton_config` to a full getButtons list.

    Skips entries that fail to parse (logged at WARNING); the caller still
    gets a partial list back. Used by the runtime auto-discovery to seed
    missing PushbuttonConfig entries into ``devices.json`` (Fase 8 hook).
    """
    from gateway.installation import PushbuttonConfig

    out: list[PushbuttonConfig] = []
    for entry in buttons_json or []:
        try:
            out.append(extract_pushbutton_config(module_id, entry))
        except ValueError as exc:
            log.warning("Skipping getButtons entry: %s", exc)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_module_metadata.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Confirm no stragglers**

Run: `grep -rn "extract_button_config\|extract_buttons_from_getbuttons\|ButtonConfig" gateway/ tests/`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add gateway/module_metadata.py tests/test_module_metadata.py
git commit -m "refactor: rename extract_button_config to extract_pushbutton_config, populate channel from getButtons index"
```

---

### Task 7: Regression test — discovery preserves nested pushbuttons

**Files:**
- Test: `tests/test_installation_serialization.py` (new test appended — verifies the Task 1–3 side-effect actually fixes the original bug from the spec)

No production code changes in this task — `run_forced_discovery()` in `gateway/auto_discovery.py` needs zero modification, because it already calls `mc.to_dict()` per existing module, and that method now nests pushbuttons automatically (Task 2). This task exists purely to lock in that guarantee with a regression test, so it can never silently regress again.

**Interfaces:**
- Consumes: `DiscoveryOrchestrator.run_forced_discovery()` (unchanged), `ModuleConfig.to_dict()` (Task 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_installation_serialization.py`:

```python
@pytest.mark.asyncio
async def test_forced_discovery_preserves_nested_pushbuttons(tmp_path: Path) -> None:
    """Regression for the original bug: a discovery run must not drop pushbuttons.

    Before the nested-schema change, run_forced_discovery() wrote
    {"modules": modules_to_write} with no "buttons" key at all, silently
    wiping every configured pushbutton on each run. Since pushbuttons are
    now nested inside their module's own to_dict(), this is structurally
    impossible: the module carries its own pushbuttons along.
    """
    from gateway.auto_discovery import DiscoveryOrchestrator
    from gateway.config import DiscoveryConfig
    from gateway.discovery import DiscoveredModule

    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({
        "modules": [
            {
                "name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay",
                "firmware": "", "model": "IP0200PoE", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "Keuken LED", "room": "Keuken",
                              "semantic_type": "light", "active": True, "max_watt": 60}],
            },
            {
                "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
                "firmware": "", "model": "IP1100PoE", "mac": "00:24:77:52:ad:aa",
                "pushbuttons": [
                    {"id": "2f8185190000df", "channel": 1, "name": "Badkamer knop",
                     "room": "1e verdieping", "active": True, "hold_threshold_s": 1.5}
                ],
            },
        ]
    }), encoding="utf-8")

    discovery_config = DiscoveryConfig()
    orchestrator = DiscoveryOrchestrator(
        config=discovery_config,
        devices_file=str(devices_file),
        broadcast=lambda event: None,
    )

    discovered = [
        DiscoveredModule(
            ip="10.10.1.30", device_type="relay", firmware="5.1",
            mac="00:24:77:52:ac:be", model="IP0200PoE",
        ),
        DiscoveredModule(
            ip="10.10.1.50", device_type="input", firmware="5.2",
            mac="00:24:77:52:ad:aa", model="IP1100PoE",
        ),
    ]

    with patch.object(orchestrator, "_run_forced_discovery_sync", return_value=discovered):
        await orchestrator.run_forced_discovery()

    written = json.loads(devices_file.read_text(encoding="utf-8"))
    assert "buttons" not in written
    input_module = next(m for m in written["modules"] if m["type"] == "input")
    assert len(input_module["pushbuttons"]) == 1
    assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
    assert input_module["pushbuttons"][0]["channel"] == 1

    reloaded = InstallationConfig.load(devices_file)
    assert len(reloaded.pushbuttons) == 1
    assert reloaded.pushbutton_by_id("2f8185190000df") is not None
```

Extend the `gateway.installation` import at the top of `tests/test_installation_serialization.py` once more (Task 2 already changed it to `from gateway.installation import ChannelConfig, DetectorConfig, ModuleConfig, PushbuttonConfig`) to also bring in `InstallationConfig`:

```python
from gateway.installation import ChannelConfig, DetectorConfig, InstallationConfig, ModuleConfig, PushbuttonConfig
```

- [ ] **Step 2: Run test to verify it fails on the OLD code**

This step is retroactive verification, not a live red step — Tasks 1–3 already made this pass as a side effect. Instead: run it now to confirm it's green, which proves Tasks 1–3 already fixed the bug.

Run: `pytest tests/test_installation_serialization.py::test_forced_discovery_preserves_nested_pushbuttons -v`
Expected: PASS

- [ ] **Step 3: No implementation step — this task is test-only**

(Intentionally blank — the fix already landed in Tasks 1–3. This step exists in the plan only to document why there is no "step 3 implementation" here.)

- [ ] **Step 4: Run the full test file to make sure nothing else broke**

Run: `pytest tests/test_installation_serialization.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_installation_serialization.py
git commit -m "test: regression — forced discovery preserves nested pushbuttons"
```

---

### Task 8: Migration script for the existing real `devices.json`

**Files:**
- Create: `scripts/migrate_buttons_to_nested.py`
- Test: `tests/test_migrate_buttons_to_nested.py`

**Interfaces:**
- Produces: a CLI script `python scripts/migrate_buttons_to_nested.py <path/to/devices.json>` and an importable `migrate(raw: dict) -> dict` function (pure, no I/O) that the CLI wraps.

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrate_buttons_to_nested.py`:

```python
"""Tests for scripts/migrate_buttons_to_nested.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.migrate_buttons_to_nested import migrate, migrate_file


def test_migrate_moves_flat_buttons_into_matching_module() -> None:
    raw = {
        "modules": [
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"},
            {"name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []},
        ],
        "buttons": [
            {"id": "2f8185190000df", "module_id": "00:24:77:52:ad:aa", "name": "Badkamer knop",
             "room": "1e verdieping", "active": True, "hold_threshold_s": 1.5},
        ],
    }
    result = migrate(raw)

    assert "buttons" not in result
    input_module = next(m for m in result["modules"] if m["mac"] == "00:24:77:52:ad:aa")
    assert len(input_module["pushbuttons"]) == 1
    assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
    assert "module_id" not in input_module["pushbuttons"][0]
    assert input_module["detectors"] == []


def test_migrate_adds_empty_detectors_to_input_modules_without_it() -> None:
    raw = {"modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1"}], "buttons": []}
    result = migrate(raw)
    input_module = result["modules"][0]
    assert input_module["detectors"] == []
    assert input_module["pushbuttons"] == []


def test_migrate_warns_and_skips_orphan_button(caplog) -> None:
    raw = {
        "modules": [{"name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}],
        "buttons": [{"id": "orphan1", "module_id": "nonexistent_mac", "name": "Orphan"}],
    }
    result = migrate(raw)
    assert "buttons" not in result
    relay_module = result["modules"][0]
    assert "pushbuttons" not in relay_module  # relay modules don't get a pushbuttons key
    assert "no matching module" in caplog.text.lower() or "orphan" in caplog.text.lower()


def test_migrate_is_idempotent_when_already_nested() -> None:
    raw = {
        "modules": [
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1",
             "pushbuttons": [{"id": "abc", "name": "X"}], "detectors": []},
        ]
    }
    result = migrate(raw)
    assert result == raw


def test_migrate_file_writes_backup_and_result(tmp_path: Path) -> None:
    devices_file = tmp_path / "devices.json"
    original = {
        "modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1"}],
        "buttons": [{"id": "abc", "module_id": "mac1", "name": "Knop"}],
    }
    devices_file.write_text(json.dumps(original), encoding="utf-8")

    migrate_file(devices_file)

    backup = tmp_path / "devices.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == original

    migrated = json.loads(devices_file.read_text(encoding="utf-8"))
    assert "buttons" not in migrated
    assert migrated["modules"][0]["pushbuttons"][0]["id"] == "abc"


def test_migrate_file_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrate_file(tmp_path / "nonexistent.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrate_buttons_to_nested.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_buttons_to_nested'`

- [ ] **Step 3: Write the migration script**

Create `scripts/migrate_buttons_to_nested.py`:

```python
#!/usr/bin/env python3
"""One-off migration: move devices.json's flat top-level "buttons" array
into modules[].pushbuttons[], and add an empty modules[].detectors[] to
every input module that doesn't already have one.

No field-bus calls — purely a file-format rewrite. Run once, before
upgrading to a gateway version whose InstallationConfig._parse() no
longer accepts the old flat "buttons" format.

Usage:
    python scripts/migrate_buttons_to_nested.py /path/to/devices.json

A backup of the original file is written alongside it as
"devices.json.bak" before any changes are made. Safe to re-run: a file
that has already been migrated (no top-level "buttons" key) is returned
unchanged.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def migrate(raw: dict) -> dict:
    """Pure transform: old flat-buttons dict -> new nested-pushbuttons dict.

    Does not touch disk. ``raw["modules"]`` entries are shallow-copied
    before mutation so the caller's original dict is left untouched.
    """
    modules = [dict(m) for m in raw.get("modules", [])]
    by_mac = {m.get("mac"): m for m in modules if m.get("mac")}

    for module in modules:
        if module.get("type") == "input":
            module.setdefault("pushbuttons", [])
            module.setdefault("detectors", [])

    for btn in raw.get("buttons", []):
        module_id = btn.get("module_id")
        target = by_mac.get(module_id)
        if target is None:
            log.warning(
                "Skipping button %r: no matching module for module_id %r",
                btn.get("id"), module_id,
            )
            continue
        clean_btn = {k: v for k, v in btn.items() if k != "module_id"}
        target.setdefault("pushbuttons", []).append(clean_btn)
        target.setdefault("detectors", [])

    return {"modules": modules}


def migrate_file(path: str | Path) -> None:
    """Migrate a devices.json file in place, with a .bak backup first."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"devices.json not found at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copyfile(path, backup_path)

    migrated = migrate(raw)
    path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
    log.info("Migrated %s (backup at %s)", path, backup_path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/devices.json", file=sys.stderr)
        return 1
    migrate_file(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_migrate_buttons_to_nested.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_buttons_to_nested.py tests/test_migrate_buttons_to_nested.py
git commit -m "feat: add one-off migration script for the flat-to-nested pushbuttons devices.json format"
```

---

### Task 9: Full-suite verification + docs

**Files:**
- Modify: `ipbuilding_gateway/CHANGELOG.md` (append to the existing `## [Unreleased]` section)
- Modify: `ARCHITECTURE.md` (one paragraph in the devices.json schema section — search for the existing northbound field-ownership table)
- Modify: `docs/api/rest.md` (note the new `channel` field on button entries in the `GET`/`PATCH /api/v1/devices` docs)

No test-writing in this task — it is the final verification + documentation pass over everything Tasks 1–8 built.

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -q`
Expected: All tests pass (no failures, no errors). If anything fails, it means a call site was missed — grep for the old symbol names across the whole repo (`ButtonConfig`, `button_by_id`, `button_threshold`, `apply_button_patch`, `validate_button_fields`, `NORTHBOUND_BUTTON_FIELDS`, `extract_button_config`, `extract_buttons_from_getbuttons`, a bare `installation.buttons`) and fix before proceeding.

- [ ] **Step 2: Grep the whole repo for any remaining old symbol names**

Run: `grep -rn "ButtonConfig\b" gateway/ tests/ scripts/ | grep -v PushbuttonConfig`
Expected: no output.

- [ ] **Step 3: Update CHANGELOG.md**

In `ipbuilding_gateway/CHANGELOG.md`, add to the existing `## [Unreleased]` section (create it at the top if a later release has since been added):

```markdown
### Changed
- **devices.json**: pushbuttons (and a new, still-empty detectors placeholder) now live nested inside their owning input module (`modules[].pushbuttons[]`), instead of a separate top-level `buttons[]` array. This fixes a bug where a "Discover new modules" run silently wiped all configured pushbuttons. Existing installations must run `python scripts/migrate_buttons_to_nested.py /path/to/devices.json` once before upgrading — the gateway now refuses to load the old flat format with a clear error pointing at the script.
```

- [ ] **Step 4: Update ARCHITECTURE.md**

Find the northbound field-ownership table / devices.json schema section in `ARCHITECTURE.md` (grep for `channels` to locate it) and add one sentence noting that pushbuttons/detectors are nested per input module the same way channels are nested per relay/dimmer module, with a pointer to the design spec: `docs/superpowers/specs/2026-07-13-pushbuttons-detectors-nested-schema-design.md`.

- [ ] **Step 5: Update docs/api/rest.md**

Find the `GET /api/v1/devices` response example in `docs/api/rest.md` and add `"channel": 1` to the example button entry (if one exists), with a one-line note: "`channel` is read-only (from the module's physical wiring), not PATCH-able."

- [ ] **Step 6: Run the full suite one final time**

Run: `pytest -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add ipbuilding_gateway/CHANGELOG.md ARCHITECTURE.md docs/api/rest.md
git commit -m "docs: pushbuttons/detectors nested schema — changelog, architecture, REST API notes"
```

---

## Self-Review Notes

- **Spec coverage:** §2 (schema) → Tasks 1–3. §3 (dataclasses) → Task 1–2. §4 (parser + safety-guard) → Task 3. §5 (write-path simplification) → Task 4 + Task 7 (regression proof). §6 (API surface, stable companion contract) → Task 5. §7 (migration script) → Task 8. §8 (tests) → woven into every task. §9 (explicit non-scope: no detector runtime/API, no REST contract change, no live index backfill) → respected throughout (detectors never appear in `_build_device_list()`, `device_type`/`semantic_type` values untouched, migration script has zero network calls).
- **Placeholder scan:** no TBD/TODO in any step; every code block is complete, runnable code.
- **Type consistency:** `PushbuttonConfig.channel: int | None` is used consistently as `"channel"` in `to_dict()`, the API response (`entry["channel"]`), and the migration script's untouched pass-through — no naming drift between tasks.
