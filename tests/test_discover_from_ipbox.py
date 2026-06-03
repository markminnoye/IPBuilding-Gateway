"""Tests for scripts/discover_from_ipbox.py — IPBox WebConfig migrate-script."""

import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from scripts.discover_from_ipbox import (
    TYPE_MAP,
    build_devices_json,
    import_dimmer_channels,
    import_relay_channels,
    mac_decimal_to_hex,
    scan_modules,
)

SCAN_RESPONSE = [
    {"IP": "10.10.1.30", "Mac": "0.36.119.82.172.190", "IsNew": False, "Type": "Relais", "Version": "5.1"},
    {"IP": "10.10.1.40", "Mac": "0.36.119.82.158.168", "IsNew": False, "Type": "Dim",    "Version": "5.4"},
    {"IP": "10.10.1.50", "Mac": "0.36.119.82.173.170", "IsNew": False, "Type": "Input",  "Version": "5.2.4"},
]
RELAY_RESPONSE = [
    {"id": 547, "CH": 0,  "Description": "Keuken LED [30.1.1]", "Group": "Keuken",           "Pulse": 0, "Lock": "00000000", "LockTimer": 0},
    {"id": 557, "CH": 10, "Description": "Patio [30.1.2]",       "Group": "Buitenverlichting", "Pulse": 0, "Lock": "00000000", "LockTimer": 0},
]
DIMMER_RESPONSE = [
    {"id": 571, "CH": 0, "Description": "Woonkamer Dimmer 1", "Group": "Woonkamer", "DimMax": "70", "DimMin": "20"},
    {"id": 572, "CH": 1, "Description": "Woonkamer Dimmer 2", "Group": "Woonkamer", "DimMax": "70", "DimMin": "20"},
]
BASE = "http://192.168.0.185"
COOKIE = "ASP.NET_SessionId=test123"


def test_mac_decimal_to_hex():
    assert mac_decimal_to_hex("0.36.119.82.172.190") == "00:24:77:52:ac:be"
    assert mac_decimal_to_hex("0.36.119.82.158.168") == "00:24:77:52:9e:a8"


def test_type_map_covers_all_known():
    assert TYPE_MAP["Relais"] == "relay"
    assert TYPE_MAP["Dim"] == "dimmer"
    assert TYPE_MAP["Input"] == "input"


@pytest.mark.asyncio
async def test_scan_modules():
    with aioresponses() as m:
        m.post(f"{BASE}/general/Wizards/Modules/ScanForModules", payload=SCAN_RESPONSE)
        result = await scan_modules(BASE, COOKIE)
    assert len(result) == 3
    assert result[0]["IP"] == "10.10.1.30"


@pytest.mark.asyncio
async def test_import_relay_channels():
    with aioresponses() as m:
        m.post(f"{BASE}/general/Hardware/Relais/ImportRelayInfo", payload=RELAY_RESPONSE)
        channels = await import_relay_channels(BASE, COOKIE, "10.10.1.30")
    assert channels[0]["id"] == 547
    assert channels[0]["CH"] == 0


@pytest.mark.asyncio
async def test_import_dimmer_channels():
    with aioresponses() as m:
        m.post(f"{BASE}/general/Hardware/Dim/ImportDimInfo", payload=DIMMER_RESPONSE)
        channels = await import_dimmer_channels(BASE, COOKIE, "10.10.1.40")
    assert channels[0]["id"] == 571


@pytest.mark.asyncio
async def test_build_devices_json_uses_ipbox_id():
    """IPBox IDs worden opgeslagen als ipbox_id, niet als id."""
    result = await build_devices_json(
        modules=SCAN_RESPONSE,
        relay_channels={"10.10.1.30": RELAY_RESPONSE},
        dimmer_channels={"10.10.1.40": DIMMER_RESPONSE},
    )
    assert len(result["modules"]) == 3

    relay = next(m for m in result["modules"] if m["ip"] == "10.10.1.30")
    assert relay["type"] == "relay"
    ch0 = relay["channels"][0]
    assert ch0["ch"] == 0
    assert ch0["ipbox_id"] == 547        # IPBox ID bewaard als ipbox_id
    assert "id" not in ch0               # geen 'id' veld
    assert ch0["description"] == "Keuken LED [30.1.1]"
    assert ch0["group"] == "Keuken"

    dimmer = next(m for m in result["modules"] if m["ip"] == "10.10.1.40")
    assert dimmer["channels"][0]["ipbox_id"] == 571

    input_mod = next(m for m in result["modules"] if m["ip"] == "10.10.1.50")
    assert input_mod["channels"] == []   # input: geen kanalen via ImportInfo


@pytest.mark.asyncio
async def test_build_validates_via_installation_config(tmp_path: Path):
    """Output moet inlaadbaar zijn via InstallationConfig.load() en ipbox_id lookup werken."""
    from gateway.installation import InstallationConfig

    result = await build_devices_json(
        modules=SCAN_RESPONSE,
        relay_channels={"10.10.1.30": RELAY_RESPONSE},
        dimmer_channels={"10.10.1.40": DIMMER_RESPONSE},
    )
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(result), encoding="utf-8")
    cfg = InstallationConfig.load(p)

    assert cfg.ipbox_id_to_channel(547) is not None
    assert cfg.ipbox_id_to_channel(547)[0].value == "relay"
    assert cfg.ipbox_id_to_channel(571)[0].value == "dimmer"
    # entity_id is altijd afleidbaar, niet opgeslagen; type zit NIET in het ID
    # (server-side opgezocht via module_by_ip — anti-spoofing)
    assert cfg.make_entity_id("10.10.1.30", 0) == "10.10.1.30:0"
