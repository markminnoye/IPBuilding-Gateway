"""Tests for gateway.discovery — standalone field module discovery CLI."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.discovery import (
    MODULE_IP_RANGE,
    DiscoveredModule,
    build_devices_json_draft,
    http_identify_module,
    parse_udp10001_reply,
    sweep_http_range,
)


# ---------------------------------------------------------------------------
# parse_udp10001_reply
# ---------------------------------------------------------------------------

def test_parse_udp10001_reply_non_probe_payload_returns_module():
    """Any non-probe, non-empty payload is treated as a presence signal."""
    payload = b"\x02\x01\x00\x24\x77\x52\xac\xbe"
    result = parse_udp10001_reply("10.10.1.30", payload)
    assert result is not None
    assert result.ip == "10.10.1.30"


def test_parse_udp10001_reply_returns_none_on_probe_echo():
    """Own probe echoed back must be ignored."""
    result = parse_udp10001_reply("10.10.1.30", b"\x01\x00\x00\x00")
    assert result is None


def test_parse_udp10001_reply_returns_none_on_too_short():
    result = parse_udp10001_reply("10.10.1.30", b"\x01")
    assert result is None


# ---------------------------------------------------------------------------
# http_identify_module
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_identify_module_relay():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value=(
        "method=getSysSet\r\n"
        "devtype=1\r\n"
        "firm=5.1\r\n"
        "ip=10.10.1.30\r\n"
    ))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_sess = MagicMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=False)
    mock_sess.get = MagicMock(return_value=mock_resp)

    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module("10.10.1.30")

    assert result is not None
    assert result.ip == "10.10.1.30"
    assert result.device_type == "relay"
    assert result.firmware == "5.1"


@pytest.mark.asyncio
async def test_http_identify_module_dimmer():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="devtype=2\r\nfirm=5.4\r\n")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_sess = MagicMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=False)
    mock_sess.get = MagicMock(return_value=mock_resp)

    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module("10.10.1.40")

    assert result is not None
    assert result.device_type == "dimmer"


@pytest.mark.asyncio
async def test_http_identify_module_unreachable():
    import aiohttp

    mock_sess = MagicMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=False)
    mock_sess.get = MagicMock(
        side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError())
    )

    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module("10.10.1.99")

    assert result is None


@pytest.mark.asyncio
async def test_http_identify_module_404():
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_sess = MagicMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=False)
    mock_sess.get = MagicMock(return_value=mock_resp)

    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module("10.10.1.99")

    assert result is None


# ---------------------------------------------------------------------------
# build_devices_json_draft
# ---------------------------------------------------------------------------

def test_build_devices_json_draft_no_ipbox_id():
    """Gateway CLI output bevat nooit een ipbox_id — geen IPBox data beschikbaar."""
    modules = [
        DiscoveredModule(ip="10.10.1.30", device_type="relay",  firmware="5.1",   mac="00:24:77:52:ac:be"),
        DiscoveredModule(ip="10.10.1.40", device_type="dimmer", firmware="5.4",   mac="00:24:77:52:9e:a8"),
        DiscoveredModule(ip="10.10.1.50", device_type="input",  firmware="5.2.4", mac="00:24:77:52:ad:aa"),
    ]
    draft = build_devices_json_draft(modules)
    assert len(draft["modules"]) == 3

    relay = next(m for m in draft["modules"] if m["ip"] == "10.10.1.30")
    assert relay["type"] == "relay"
    assert relay["channels"] == []   # geen kanalen zonder IPBox

    for mod in draft["modules"]:
        for ch in mod.get("channels", []):
            assert "ipbox_id" not in ch  # nooit IPBox IDs in CLI output
            assert "id" not in ch


def test_build_devices_json_draft_loads_via_installation_config(tmp_path: Path):
    """Draft (no channels) must load without error via InstallationConfig."""
    from gateway.installation import InstallationConfig

    modules = [
        DiscoveredModule(ip="10.10.1.30", device_type="relay", firmware="5.1", mac=""),
        DiscoveredModule(ip="10.10.1.50", device_type="input", firmware="5.2", mac=""),
    ]
    draft = build_devices_json_draft(modules)
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(draft), encoding="utf-8")
    cfg = InstallationConfig.load(p)
    assert cfg.module_by_ip("10.10.1.30") is not None
    assert cfg.module_by_ip("10.10.1.50") is not None
    assert cfg.all_ipbox_ids() == []  # geen legacy IDs in CLI output


def test_build_devices_json_draft_entity_id_derivable():
    """entity_id is nooit opgeslagen maar altijd afleidbaar van (ip, type, ch)."""
    from gateway.installation import make_entity_id

    modules = [DiscoveredModule(ip="10.10.1.30", device_type="relay", firmware="5.1")]
    draft = build_devices_json_draft(modules)
    relay = draft["modules"][0]
    # entity_id veld bestaat NIET in de output (wordt on-the-fly afgeleid)
    assert "entity_id" not in relay
    # maar is altijd berekend als '10.10.1.30:relay:0' voor ch 0 etc.
    assert make_entity_id(relay["ip"], relay["type"], 0) == "10.10.1.30:relay:0"
