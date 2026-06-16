"""Tests for gateway.discovery — standalone field module discovery CLI."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from gateway.discovery import (
    MODULE_IP_RANGE,
    DiscoveredModule,
    IpChange,
    apply_backup_config,
    build_devices_json_draft,
    channels_from_backup_config,
    detect_mac_ip_changes,
    device_type_from_fields,
    device_type_from_ref_nr,
    http_identify_module,
    normalize_mac,
    parse_arp_table,
    parse_backup_config_body,
    parse_get_sysset_body,
    parse_udp10001_reply,
    resolve_module_model,
    sweep_arp_range,
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
    # maar is altijd berekend als '10.10.1.30-0' voor ch 0 (type niet in de ID)
    assert make_entity_id(relay["ip"], 0) == "10.10.1.30-0"


# ---------------------------------------------------------------------------
# normalize_mac
# ---------------------------------------------------------------------------

def test_normalize_mac_macos_single_digit():
    assert normalize_mac("0:24:77:52:ac:be") == "00:24:77:52:ac:be"


def test_normalize_mac_linux_standard():
    assert normalize_mac("00:24:77:52:ac:be") == "00:24:77:52:ac:be"


def test_normalize_mac_dash_separated():
    assert normalize_mac("00-24-77-52-ac-be") == "00:24:77:52:ac:be"


def test_normalize_mac_uppercase():
    assert normalize_mac("00:24:77:52:AC:BE") == "00:24:77:52:ac:be"


# ---------------------------------------------------------------------------
# detect_mac_ip_changes
# ---------------------------------------------------------------------------

def test_detect_mac_ip_changes_reports_dhcp_move(tmp_path):
    baseline_json = tmp_path / "devices.json"
    baseline_json.write_text(
        '{"modules":[{"ip":"10.10.1.30","type":"relay","mac":"00:24:77:52:ac:be","channels":[]}]}',
        encoding="utf-8",
    )
    from gateway.installation import InstallationConfig
    baseline = InstallationConfig.load(baseline_json)
    discovered = [
        DiscoveredModule(ip="10.10.1.35", device_type="relay", mac="00:24:77:52:ac:be"),
    ]
    changes = detect_mac_ip_changes(discovered, baseline)
    assert changes == [
        IpChange(mac="00:24:77:52:ac:be", old_ip="10.10.1.30", new_ip="10.10.1.35"),
    ]


def test_detect_mac_ip_changes_empty_when_ip_unchanged(tmp_path):
    baseline_json = tmp_path / "devices.json"
    baseline_json.write_text(
        '{"modules":[{"ip":"10.10.1.30","type":"relay","mac":"00:24:77:52:ac:be","channels":[]}]}',
        encoding="utf-8",
    )
    from gateway.installation import InstallationConfig
    baseline = InstallationConfig.load(baseline_json)
    discovered = [
        DiscoveredModule(ip="10.10.1.30", device_type="relay", mac="00:24:77:52:ac:be"),
    ]
    assert detect_mac_ip_changes(discovered, baseline) == []


def test_detect_mac_ip_changes_skips_modules_without_mac(tmp_path):
    baseline_json = tmp_path / "devices.json"
    baseline_json.write_text('{"modules":[]}', encoding="utf-8")
    from gateway.installation import InstallationConfig
    baseline = InstallationConfig.load(baseline_json)
    discovered = [DiscoveredModule(ip="10.10.1.30", device_type="relay", mac="")]
    assert detect_mac_ip_changes(discovered, baseline) == []


def test_detect_mac_ip_changes_empty_when_no_baseline():
    discovered = [DiscoveredModule(ip="10.10.1.35", device_type="relay", mac="00:24:77:52:ac:be")]
    assert detect_mac_ip_changes(discovered, None) == []


# ---------------------------------------------------------------------------
# parse_arp_table — darwin
# ---------------------------------------------------------------------------

DARWIN_ARP_OUTPUT = """\
? (10.10.1.30) at 0:24:77:52:ac:be on en7 ifaddr [ethernet]
? (10.10.1.40) at 0:24:77:52:9e:a8 on en7 ifaddr [ethernet]
? (10.10.1.50) at 0:24:77:52:ad:aa on en7 ifaddr [ethernet]
? (10.10.1.1) at 00:30:18:ab:cd:ef on en7 ifaddr [ethernet]
? (192.168.1.1) at bc:30:5b:e2:8f:01 on en0 ifaddr [ethernet]
"""


def test_parse_arp_table_darwin_returns_all_complete_entries():
    """parse_arp_table returns ALL complete ARP entries on subnet (no OUI filter here)."""
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.check_output", return_value=DARWIN_ARP_OUTPUT):
        result = parse_arp_table("10.10.1")
    # Returns all 4 entries on 10.10.1.x including hub; OUI filtering is done by sweep_arp_range
    assert len(result) == 4
    ips = {ip for ip, _ in result}
    assert ips == {"10.10.1.30", "10.10.1.40", "10.10.1.50", "10.10.1.1"}


def test_parse_arp_table_darwin_excludes_incomplete_entries():
    darwin_with_incomplete = DARWIN_ARP_OUTPUT + "? (10.10.1.99) at (incomplete) on en7\n"
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.check_output", return_value=darwin_with_incomplete):
        result = parse_arp_table("10.10.1")
    ips = {ip for ip, _ in result}
    assert "10.10.1.99" not in ips


# ---------------------------------------------------------------------------
# parse_arp_table — linux
# ---------------------------------------------------------------------------

LINUX_ARP_OUTPUT = """\
IP address       HW type     Flags       HW address            Mask     Device
10.10.1.30       0x1         0x2         00:24:77:52:ac:be     *        eth0
10.10.1.40       0x1         0x2         00:24:77:52:9e:a8     *        eth0
10.10.1.50       0x1         0x2         00:24:77:52:ad:aa     *        eth0
10.10.1.1        0x1         0x2         00:30:18:ab:cd:ef     *        eth0
192.168.1.1      0x1         0x2         bc:30:5b:e2:8f:01     *        eth0
"""


def test_parse_arp_table_linux_returns_all_complete_entries():
    """parse_arp_table returns ALL complete ARP entries on subnet (no OUI filter here)."""
    with patch("platform.system", return_value="Linux"), \
         patch("builtins.open", mock_open(read_data=LINUX_ARP_OUTPUT)):
        result = parse_arp_table("10.10.1")
    assert len(result) == 4
    ips = {ip for ip, _ in result}
    assert ips == {"10.10.1.30", "10.10.1.40", "10.10.1.50", "10.10.1.1"}


def test_parse_arp_table_linux_excludes_incomplete_entries():
    linux_with_incomplete = LINUX_ARP_OUTPUT + "10.10.1.99       0x1         0x0         00:24:77:52:00:00     *        eth0\n"
    with patch("platform.system", return_value="Linux"), \
         patch("builtins.open", mock_open(read_data=linux_with_incomplete)):
        result = parse_arp_table("10.10.1")
    ips = {ip for ip, _ in result}
    assert "10.10.1.99" not in ips


# ---------------------------------------------------------------------------
# parse_get_sysset_body — JSON response (live format from .30)
# ---------------------------------------------------------------------------

# Live getSysSet on 2026-06-03 (no devtype/name — type via backupConfig refNr)
LIVE_SYSSET_JSON = (
    '{"dhcp":"0","ip":"10.10.1.30","subnet":"255.255.255.0",'
    '"gateway":"10.10.1.254","mac":"0.36.119.82.172.190",'
    '"button":"1","allow":"1"}'
)

# Legacy fixture when firmware exposes getSysSet "name"
LIVE_JSON_WITH_NAME = (
    '{"ip": "10.10.1.30", '
    '"mac": "0.36.119.82.172.190", '
    '"name": "IP200PoE", '
    '"installed": "true"}'
)


def test_parse_get_sysset_body_json_returns_fields():
    result = parse_get_sysset_body(LIVE_SYSSET_JSON)
    assert result.get("ip") == "10.10.1.30"
    assert result.get("mac") == "0.36.119.82.172.190"
    assert "name" not in result


def test_parse_get_sysset_body_json_mac_decimal_to_hex():
    """MAC in decimal-dot notation must be parseable as a field."""
    result = parse_get_sysset_body(LIVE_SYSSET_JSON)
    mac_raw = result.get("mac", "")
    assert "." in mac_raw
    parts = mac_raw.split(".")
    assert len(parts) == 6
    hex_mac = ":".join(f"{int(p):02x}" for p in parts)
    assert hex_mac == "00:24:77:52:ac:be"


# ---------------------------------------------------------------------------
# http_identify_module — JSON response (no devtype)
# ---------------------------------------------------------------------------

def _mock_http_session(bodies: dict[str, str]) -> MagicMock:
    """Mock aiohttp session; map method name → response body."""
    def make_resp(body: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=body)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    def get_side_effect(url: str, **kwargs: object) -> MagicMock:
        for method, body in bodies.items():
            if f"method={method}" in url:
                return make_resp(body)
        raise AssertionError(f"unexpected URL: {url}")

    mock_sess = MagicMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=False)
    mock_sess.get = MagicMock(side_effect=get_side_effect)
    return mock_sess


@pytest.mark.asyncio
async def test_http_identify_module_live_sysset_plus_backup_config():
    """Live getSysSet lacks name/devtype; backupConfig refNr + channels fill the gap."""
    mock_sess = _mock_http_session({
        "getSysSet": LIVE_SYSSET_JSON,
        "backupConfig": RELAY_BACKUP_JSON,
    })
    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module("10.10.1.30")

    assert result is not None
    assert result.ip == "10.10.1.30"
    assert result.model == "IP0200PoE"
    assert result.device_type == "relay"
    assert result.mac == "00:24:77:52:ac:be"
    assert len(result.channels) == 1
    assert result.channels[0]["name"] == "Keuken LED"


@pytest.mark.asyncio
async def test_http_identify_module_json_name_without_backup():
    """When getSysSet includes name, type resolves without backupConfig."""
    mock_sess = _mock_http_session({"getSysSet": LIVE_JSON_WITH_NAME})
    with patch("gateway.discovery.aiohttp.ClientSession", return_value=mock_sess):
        result = await http_identify_module(
            "10.10.1.30", use_backup_config=False,
        )

    assert result is not None
    assert result.model == "IP200PoE"
    assert result.device_type == "relay"
    assert result.channels == []


# ---------------------------------------------------------------------------
# -----------------------------------------------------------------------
# device_type_from_fields - type resolution cascade
# -----------------------------------------------------------------------

def test_device_type_from_fields_devtype_wins():
    """devtype field takes precedence over model name."""
    fields = {"devtype": "2", "name": "IP0300PoE"}
    assert device_type_from_fields(fields) == "dimmer"


def test_device_type_from_fields_devtype_unknown_code():
    fields = {"devtype": "99"}
    assert device_type_from_fields(fields) == "unknown_99"


def test_device_type_from_fields_model_fallback():
    fields = {"name": "IP200PoE"}
    assert device_type_from_fields(fields) == "relay"
    fields = {"name": "IP0300PoE"}
    assert device_type_from_fields(fields) == "dimmer"
    fields = {"name": "IP1100PoE"}
    assert device_type_from_fields(fields) == "input"


def test_device_type_from_fields_ip0200poe():
    """IP0200PoE (alternate naming) maps to relay."""
    fields = {"name": "IP0200PoE"}
    assert device_type_from_fields(fields) == "relay"


def test_device_type_from_fields_unknown():
    fields = {"name": "SomeUnknownModule"}
    assert device_type_from_fields(fields) == "unknown"


def test_device_type_from_fields_empty():
    assert device_type_from_fields({}) == "unknown"


def test_device_type_from_fields_butlines_input():
    fields = {"ip": "10.10.1.50", "butLines": "4", "dimSpeed": "003"}
    assert device_type_from_fields(fields) == "input"


def test_device_type_from_ref_nr():
    assert device_type_from_ref_nr("IP0200PoE") == "relay"
    assert device_type_from_ref_nr("IP0300PoE") == "dimmer"
    assert device_type_from_ref_nr("IP1100PoE") == "input"
    assert device_type_from_ref_nr("Unknown") == "unknown"


RELAY_BACKUP_JSON = json.dumps({
    "device": {"refNr": "IP0200PoE"},
    "network": {"ipaddress": "10.10.1.30"},
    "channels": [
        {"id": 0, "descr": "Keuken LED", "gr": "Keuken", "pulse": 0},
        {"id": 1, "descr": "", "gr": "", "pulse": 0},
    ],
})


def test_parse_backup_config_body_relay():
    data = parse_backup_config_body(RELAY_BACKUP_JSON)
    assert data is not None
    assert data["device"]["refNr"] == "IP0200PoE"


def test_channels_from_backup_config_skips_empty_slots():
    data = parse_backup_config_body(RELAY_BACKUP_JSON)
    channels = channels_from_backup_config(data)
    assert len(channels) == 1
    assert channels[0]["ch"] == 0
    assert channels[0]["name"] == "Keuken LED"
    assert channels[0]["room"] == "Keuken"
    assert channels[0]["active"] is True
    assert channels[0]["semantic_type"] == "light"
    assert channels[0]["max_watt"] == 60  # relay default


def test_channels_from_backup_config_dimmer_max_watt():
    dimmer_json = json.dumps({
        "device": {"refNr": "IP0300PoE"},
        "channels": [{"id": 0, "descr": "Living", "gr": "Gelijkvloers"}],
    })
    data = parse_backup_config_body(dimmer_json)
    channels = channels_from_backup_config(data, module_type="dimmer")
    assert channels[0]["max_watt"] == 200


def test_channels_from_backup_config_relay_max_watt():
    channels = channels_from_backup_config(
        parse_backup_config_body(RELAY_BACKUP_JSON), module_type="relay",
    )
    assert channels[0]["max_watt"] == 60


def test_apply_backup_config_sets_model_and_channels():
    mod = DiscoveredModule(ip="10.10.1.30", device_type="unknown")
    apply_backup_config(mod, parse_backup_config_body(RELAY_BACKUP_JSON))
    assert mod.model == "IP0200PoE"
    assert mod.device_type == "relay"
    assert len(mod.channels) == 1


# -----------------------------------------------------------------------
# build_devices_json_draft - model + name defaults
# -----------------------------------------------------------------------

def test_build_devices_json_draft_includes_backup_channels():
    modules = [
        DiscoveredModule(
            ip="10.10.1.30",
            device_type="relay",
            model="IP0200PoE",
            channels=[{"ch": 0, "name": "Keuken LED", "room": "Keuken"}],
        ),
    ]
    draft = build_devices_json_draft(modules)
    assert draft["modules"][0]["channels"][0]["name"] == "Keuken LED"


def test_build_devices_json_draft_has_model_and_type():
    modules = [
        DiscoveredModule(ip="10.10.1.30", device_type="relay", firmware="5.1",
                         mac="00:24:77:52:ac:be", model="IP200PoE"),
        DiscoveredModule(ip="10.10.1.40", device_type="dimmer", firmware="5.4",
                         mac="00:24:77:52:9e:a8", model="IP0300PoE"),
        DiscoveredModule(ip="10.10.1.50", device_type="input", firmware="5.2.4",
                         mac="00:24:77:52:ad:aa", model="IP1100PoE"),
    ]
    draft = build_devices_json_draft(modules)
    relay = next(m for m in draft["modules"] if m["ip"] == "10.10.1.30")
    assert relay["model"] == "IP200PoE"
    assert relay["type"] == "relay"
    assert relay["name"] == "IP200PoE"

    dimmer = next(m for m in draft["modules"] if m["ip"] == "10.10.1.40")
    assert dimmer["model"] == "IP0300PoE"
    assert dimmer["type"] == "dimmer"

    inp = next(m for m in draft["modules"] if m["ip"] == "10.10.1.50")
    assert inp["model"] == "IP1100PoE"
    assert inp["type"] == "input"


def test_build_devices_json_draft_name_falls_back_to_ip():
    """When model is empty, name falls back to the canonical SKU for the type."""
    modules = [
        DiscoveredModule(ip="10.10.1.30", device_type="relay", firmware="",
                         mac="00:24:77:52:ac:be", model=""),
    ]
    draft = build_devices_json_draft(modules)
    entry = draft["modules"][0]
    assert entry["name"] == "IP0200PoE"
    assert entry["model"] == "IP0200PoE"


def test_build_devices_json_draft_input_module_backfills_ip1100():
    """Input module with no model resolves to IP1100PoE (regression: IP was leaking)."""
    modules = [
        DiscoveredModule(ip="10.10.1.50", device_type="input", firmware="",
                         mac="00:24:77:52:ad:aa", model=""),
    ]
    draft = build_devices_json_draft(modules)
    entry = draft["modules"][0]
    assert entry["name"] == "IP1100PoE"
    assert entry["model"] == "IP1100PoE"


def test_resolve_module_model_uses_canonical_sku():
    assert resolve_module_model("", "relay") == "IP0200PoE"
    assert resolve_module_model("", "dimmer") == "IP0300PoE"
    assert resolve_module_model("", "input") == "IP1100PoE"
    # Preserves factory product label (e.g. legacy IP200PoE).
    assert resolve_module_model("IP200PoE", "relay") == "IP200PoE"
    # Empty model and unknown type: no fallback available.
    assert resolve_module_model("", "unknown") == ""


# sweep_arp_range — mocked ping + arp
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sweep_arp_range_returns_field_modules():
    """sweep_arp_range must find .30 .40 .50 from ARP table."""
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.check_output", return_value=DARWIN_ARP_OUTPUT):
        result = await sweep_arp_range("10.10.1", range(30, 60))

    assert len(result) == 3
    ips = {m.ip for m in result}
    assert ips == {"10.10.1.30", "10.10.1.40", "10.10.1.50"}
    for m in result:
        assert m.mac.startswith("00:24:77")


@pytest.mark.asyncio
async def test_sweep_arp_range_empty_on_no_field_modules():
    no_modules = "? (192.168.1.1) at bc:30:5b:e2:8f:01 on en0\n"
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.check_output", return_value=no_modules):
        result = await sweep_arp_range("192.168.1", range(1, 255))
    assert result == []
