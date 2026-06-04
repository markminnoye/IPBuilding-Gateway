"""Tests for scripts/discover_from_ipbox.py — IPBox WebConfig migrate-script.

Mirrors the real flow on WebConfig v1.8.4.3 / ASP.NET MVC 4.0:

1. ``POST /general/Wizards/Modules/ScanForModules`` returns ``[]`` immediately
   (data is pushed later via SignalR ``loadingHub``); we POST it for
   compatibility but ignore the body.
2. Per-IP ``Import*`` POSTs read the populated project-DB. Empty/404 ⇒ no
   module at that IP.
3. The discovered modules are assembled into ``devices.json`` with
   ``ipbox_id`` (not ``id``) per channel.
"""

import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from scripts.discover_from_ipbox import (
    build_devices_json,
    probe_module,
    scan_modules,
)

RELAY_RESPONSE = [
    {"id": 547, "CH": 0,  "Description": "Keuken LED [30.1.1]", "Group": "Keuken",           "Pulse": 0, "Lock": "00000000", "LockTimer": 0},
    {"id": 557, "CH": 10, "Description": "Patio [30.1.2]",       "Group": "Buitenverlichting", "Pulse": 0, "Lock": "00000000", "LockTimer": 0},
]
DIMMER_RESPONSE = [
    {"id": 571, "CH": 0, "Description": "Woonkamer Dimmer 1", "Group": "Woonkamer", "DimMax": "70", "DimMin": "20"},
    {"id": 572, "CH": 1, "Description": "Woonkamer Dimmer 2", "Group": "Woonkamer", "DimMax": "70", "DimMin": "20"},
]
INPUT_RESPONSE = [
    {"ID": 900, "CH": 0, "Description": "Voordeur", "Group": "Gelijkvloers"},
    {"ID": 901, "CH": 1, "Description": "Keuken",   "Group": "Keuken"},
]

BASE = "http://192.168.0.185"
COOKIE = "ASP.NET_SessionId=test123"


@pytest.mark.asyncio
async def test_scan_modules_empty_on_recent_firmware():
    """ScanForModules returns [] on current firmware; we still POST it."""
    with aioresponses() as m:
        m.post(
            f"{BASE}/general/Wizards/Modules/ScanForModules",
            payload=[],
        )
        result = await scan_modules(BASE, COOKIE)
    assert result == []


@pytest.mark.asyncio
async def test_scan_modules_legacy_firmware_returns_modules():
    """Oudere installaties: response bevat de moduledata (we gebruiken 'm niet)."""
    legacy = [
        {"IP": "10.10.1.30", "Mac": "0.36.119.82.172.190", "Type": "Relais", "Version": "5.1"},
    ]
    with aioresponses() as m:
        m.post(
            f"{BASE}/general/Wizards/Modules/ScanForModules",
            payload=legacy,
        )
        result = await scan_modules(BASE, COOKIE)
    assert len(result) == 1
    assert result[0]["IP"] == "10.10.1.30"


@pytest.mark.asyncio
async def test_probe_module_relay():
    """probe_module hits ImportRelayInfo and returns a relay entry."""
    with aioresponses() as m:
        m.post(
            f"{BASE}/general/Hardware/Relais/ImportRelayInfo",
            payload=RELAY_RESPONSE,
        )
        result = await probe_module(BASE, COOKIE, "10.10.1.30")
    assert result is not None
    assert result["ip"] == "10.10.1.30"
    assert result["type"] == "relay"
    assert len(result["channels"]) == 2
    assert result["channels"][0]["id"] == 547
    assert result["channels"][0]["CH"] == 0


@pytest.mark.asyncio
async def test_probe_module_dimmer():
    """probe_module hits ImportDimInfo after ImportRelayInfo returned empty."""
    with aioresponses() as m:
        m.post(
            f"{BASE}/general/Hardware/Relais/ImportRelayInfo",
            payload=[],
        )
        m.post(
            f"{BASE}/general/Hardware/Dim/ImportDimInfo",
            payload=DIMMER_RESPONSE,
        )
        result = await probe_module(BASE, COOKIE, "10.10.1.40")
    assert result is not None
    assert result["type"] == "dimmer"
    assert result["channels"][0]["id"] == 571


@pytest.mark.asyncio
async def test_probe_module_input():
    """probe_module hits ImportInputInfo for the input module."""
    with aioresponses() as m:
        m.post(
            f"{BASE}/general/Hardware/Relais/ImportRelayInfo",
            payload=[],
        )
        m.post(
            f"{BASE}/general/Hardware/Dim/ImportDimInfo",
            payload=[],
        )
        m.post(
            f"{BASE}/general/Hardware/Input/ImportInputInfo",
            payload=INPUT_RESPONSE,
        )
        result = await probe_module(BASE, COOKIE, "10.10.1.50")
    assert result is not None
    assert result["type"] == "input"
    assert len(result["channels"]) == 2


@pytest.mark.asyncio
async def test_probe_module_returns_none_when_empty():
    """Geen enkele Import* heeft data → module bestaat niet (of project-DB leeg)."""
    with aioresponses() as m:
        m.post(f"{BASE}/general/Hardware/Relais/ImportRelayInfo", payload=[])
        m.post(f"{BASE}/general/Hardware/Dim/ImportDimInfo", payload=[])
        m.post(f"{BASE}/general/Hardware/Input/ImportInputInfo", payload=[])
        result = await probe_module(BASE, COOKIE, "10.10.1.99")
    assert result is None


@pytest.mark.asyncio
async def test_build_devices_json_uses_ipbox_id():
    """IPBox IDs worden opgeslagen als ipbox_id, niet als id."""
    discovered = [
        {"ip": "10.10.1.30", "type": "relay", "channels": RELAY_RESPONSE, "mac": "", "firmware": ""},
        {"ip": "10.10.1.40", "type": "dimmer", "channels": DIMMER_RESPONSE, "mac": "", "firmware": ""},
        {"ip": "10.10.1.50", "type": "input", "channels": INPUT_RESPONSE, "mac": "", "firmware": ""},
    ]
    result = await build_devices_json(discovered)
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
    # Input-kanaal heeft geen ipbox_id (Import*-schema onbekend); we bewaren
    # enkel het kanaalnummer.
    assert input_mod["channels"][0]["ch"] == 0
    assert "ipbox_id" not in input_mod["channels"][0]


@pytest.mark.asyncio
async def test_build_validates_via_installation_config(tmp_path: Path):
    """Output moet inlaadbaar zijn via InstallationConfig.load() en ipbox_id lookup werken."""
    from gateway.installation import InstallationConfig

    discovered = [
        {"ip": "10.10.1.30", "type": "relay", "channels": RELAY_RESPONSE, "mac": "", "firmware": ""},
        {"ip": "10.10.1.40", "type": "dimmer", "channels": DIMMER_RESPONSE, "mac": "", "firmware": ""},
    ]
    result = await build_devices_json(discovered)
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(result), encoding="utf-8")
    cfg = InstallationConfig.load(p)

    assert cfg.ipbox_id_to_channel(547) is not None
    assert cfg.ipbox_id_to_channel(547)[0].value == "relay"
    assert cfg.ipbox_id_to_channel(571)[0].value == "dimmer"
    # entity_id is altijd afleidbaar, niet opgeslagen; type zit NIET in het ID
    # (server-side opgezocht via module_by_ip — anti-spoofing)
    assert cfg.make_entity_id("10.10.1.30", 0) == "10.10.1.30-0"
