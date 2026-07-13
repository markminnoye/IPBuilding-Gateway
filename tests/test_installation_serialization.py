"""Tests for ModuleConfig/ChannelConfig serialization to devices.json.

Runtime-only fields (last_seen, last_seen_source, derived entity id) must
NOT be written to devices.json. The file is meant to be installation-
specific configuration, stable across discovery runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gateway.device_registry import DeviceType
from gateway.installation import ChannelConfig, DetectorConfig, ModuleConfig, PushbuttonConfig


def test_module_to_dict_excludes_runtime_fields() -> None:
    """ModuleConfig.to_dict() never includes last_seen / last_seen_source."""
    mc = ModuleConfig(
        name="IP0200PoE",
        ip="10.10.1.30",
        type=DeviceType.RELAY,
        firmware="5.1",
        model="IP0200PoE",
        mac="00:24:77:52:ac:be",
    )
    # Even when the in-memory fields are set, to_dict() must drop them.
    mc.last_seen = "2026-06-04T18:00:00Z"
    mc.last_seen_source = "arp"

    d = mc.to_dict()
    assert "last_seen" not in d
    assert "last_seen_source" not in d
    assert d["name"] == "IP0200PoE"
    assert d["mac"] == "00:24:77:52:ac:be"


def test_channel_to_dict_excludes_id() -> None:
    """ChannelConfig.to_dict() never includes the derived entity id."""
    ch = ChannelConfig(
        ch=0,
        ipbox_id=547,
        id="10.10.1.30:relay:0",  # derived, must not be serialized
        name="Keuken LED",
        room="Keuken",
        semantic_type="light",
        active=True,
        max_watt=60,
    )
    d = ch.to_dict()
    assert "id" not in d
    assert d["name"] == "Keuken LED"
    assert d["ipbox_id"] == 547


def test_channel_round_trip_strips_id() -> None:
    """Files with an id field load correctly; to_dict() drops it on write."""
    raw = {
        "ch": 0,
        "id": "10.10.1.30:relay:0",  # legacy field, must not round-trip
        "name": "Keuken LED",
        "room": "Keuken",
        "semantic_type": "light",
        "active": True,
        "max_watt": 60,
    }
    ch = ChannelConfig.from_dict(raw)
    assert ch.id == "10.10.1.30:relay:0"  # kept in memory for legacy callers
    d = ch.to_dict()
    assert "id" not in d


def test_module_from_dict_drops_legacy_id_field() -> None:
    """A ``last_seen`` field on a module entry is ignored by from_dict()."""
    raw = {
        "name": "IP0200PoE",
        "ip": "10.10.1.30",
        "type": "relay",
        "firmware": "",
        "model": "IP0200PoE",
        "mac": "00:24:77:52:ac:be",
        "channels": [],
        "last_seen": "2026-06-04T18:00:00Z",
        "last_seen_source": "arp",
    }
    mc = ModuleConfig.from_dict(raw)
    # Runtime fields from disk are intentionally not loaded.
    assert mc.last_seen is None
    assert mc.last_seen_source == ""


def test_written_file_contains_no_runtime_keys(tmp_path: Path) -> None:
    """ModuleConfig.to_dict() output contains no runtime-only keys.

    Defence-in-depth test: any future field name containing ``last_seen``
    or matching the runtime convention should also be excluded.
    """
    forbidden = {"last_seen", "last_seen_source", "id"}
    mc = ModuleConfig(
        name="IP0200PoE",
        ip="10.10.1.30",
        type=DeviceType.RELAY,
        firmware="",
        model="IP0200PoE",
        mac="00:24:77:52:ac:be",
    )
    d = mc.to_dict()
    leaked = forbidden & set(d.keys())
    assert not leaked, f"Runtime fields leaked into to_dict(): {leaked}"

    for ch in [ChannelConfig(ch=0, name="X", room="", semantic_type="light", active=True, max_watt=0)]:
        cd = ch.to_dict()
        leaked_ch = forbidden & set(cd.keys())
        assert not leaked_ch, f"Runtime fields leaked into ChannelConfig.to_dict(): {leaked_ch}"


@pytest.mark.asyncio
async def test_forced_discovery_writes_clean_devices_json(tmp_path: Path) -> None:
    """run_forced_discovery() must not add last_seen / kanaal-id to the file.

    Integration-style test that exercises the same code path as a real
    forced discovery, but mocks the field-bus calls. Verifies the on-disk
    file is the same shape the operator configured in their git working
    tree.
    """
    from gateway.auto_discovery import DiscoveryOrchestrator
    from gateway.config import DiscoveryConfig
    from gateway.discovery import DiscoveredModule

    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({
        "modules": [{
            "name": "IP0200PoE",
            "ip": "10.10.1.30",
            "type": "relay",
            "firmware": "",
            "model": "IP0200PoE",
            "mac": "00:24:77:52:ac:be",
            "channels": [{
                "ch": 0,
                "name": "Keuken LED",
                "room": "Keuken",
                "semantic_type": "light",
                "active": True,
                "max_watt": 60,
            }],
        }]
    }), encoding="utf-8")

    discovery_config = DiscoveryConfig()
    orchestrator = DiscoveryOrchestrator(
        config=discovery_config,
        devices_file=str(devices_file),
        broadcast=lambda event: None,
    )

    discovered = [
        DiscoveredModule(
            ip="10.10.1.30",
            device_type="relay",
            firmware="5.1",
            mac="00:24:77:52:ac:be",
            model="IP0200PoE",
        ),
    ]

    async def _fake_forced():
        return discovered

    with patch.object(orchestrator, "_run_forced_discovery_sync", return_value=discovered):
        await orchestrator.run_forced_discovery()

    written = json.loads(devices_file.read_text(encoding="utf-8"))
    modules = written["modules"]
    assert len(modules) == 1
    mod = modules[0]
    assert "last_seen" not in mod
    assert "last_seen_source" not in mod
    assert mod["mac"] == "00:24:77:52:ac:be"
    assert mod["model"] == "IP0200PoE"

    ch = mod["channels"][0]
    assert "id" not in ch
    assert ch["name"] == "Keuken LED"

    # And no orphan lock file leaked into the working directory.
    assert not (tmp_path / "devices.json.lock").exists()


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
