"""Tests for gateway_api.py module endpoints and snapshot shape."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway import gateway_api
from gateway.device_registry import DeviceRegistry, DeviceType
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache


def _make_installation(modules: list[dict[str, Any]]) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules})


def _make_registry(installation: InstallationConfig) -> DeviceRegistry:
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    return reg


def _make_api(installation: InstallationConfig, cache: ModuleMetadataCache | None = None):
    """Return a GatewayAPI instance with mocked bus and config."""
    from gateway.gateway_api import GatewayAPI

    bus = MagicMock()
    reg = _make_registry(installation)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080

    return GatewayAPI(bus, reg, cfg, metadata_cache=cache)


class TestBuildModuleList:
    def test_static_fields_present(self) -> None:
        inst = _make_installation([
            {
                "name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "model": "IP0200PoE",
                "firmware": "5.1", "channels": [],
            }
        ])
        api = _make_api(inst)
        modules = api._build_module_list()

        assert len(modules) == 1
        m = modules[0]
        assert m["id"] == "00:24:77:52:ac:be"
        assert m["mac"] == "00:24:77:52:ac:be"
        assert m["ip"] == "10.10.1.30"
        assert m["type"] == "relay"
        assert m["firmware"] == "5.1"
        assert m["model"] == "IP0200PoE"
        # No cache -- empty network
        assert m["network"] == {}

    def test_empty_model_resolves_to_canonical_sku(self) -> None:
        """An empty model in devices.json is enriched to the type's canonical SKU."""
        inst = _make_installation([
            {
                "name": "10.10.1.50", "ip": "10.10.1.50", "type": "input",
                "mac": "00:24:77:52:ad:aa", "model": "",
                "firmware": "", "channels": [],
            }
        ])
        api = _make_api(inst)
        m = api._build_module_list()[0]
        assert m["model"] == "IP1100PoE"
        # Name comes from devices.json (gateway does not rewrite it here;
        # the companion treats IP placeholder names as auto-discovery
        # defaults and falls back to the type label).
        assert m["name"] == "10.10.1.50"

    def test_cached_network_fields_merged(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "channels": [],
            }
        ])
        cache = ModuleMetadataCache()
        meta = ModuleMetadata(
            network={"dhcp": "0", "ip": "10.10.1.30", "subnet": "255.255.255.0", "gateway": "10.10.1.1"},
            button="0",
            allow="",
            fetched_at="2026-06-03T18:00:00Z",
        )
        cache._by_mac["00:24:77:52:ac:be"] = meta

        api = _make_api(inst, cache=cache)
        modules = api._build_module_list()
        m = modules[0]
        assert m["network"]["ip"] == "10.10.1.30"
        assert m["network"]["dhcp"] == "0"
        assert m["button"] == "0"
        assert m["fetched_at"] == "2026-06-03T18:00:00Z"

    def test_empty_installation_returns_empty_list(self) -> None:
        inst = _make_installation([])
        api = _make_api(inst)
        assert api._build_module_list() == []


class TestBuildDeviceList:
    def test_firmware_not_in_device(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [{"ch": 0, "name": "Keuken LED", "room": "Keuken", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 1
        d = devices[0]
        assert "firmware" not in d, "firmware must not appear on device"

    def test_module_id_and_channel_on_device(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 5, "name": "Test", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        d = devices[0]
        assert d["module_id"] == "00:24:77:52:ac:be"
        assert d["module_ip"] == "10.10.1.30"
        assert d["channel"] == 5

    def test_inactive_channel_included_with_active_false(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "Active", "active": True, "max_watt": 60},
                    {"ch": 1, "name": "Inactive", "active": False, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 2
        by_ch = {d["channel"]: d for d in devices}
        assert by_ch[0]["active"] is True
        assert by_ch[1]["active"] is False
        assert by_ch[1]["state"] == "inactive"
        assert by_ch[1]["current_watt"] == 0

    def test_inactive_channel_state_is_inactive_not_unknown(self) -> None:
        """Channels with active: false must report state='inactive', not 'unknown'.

        Guards the semantic split introduced for operator/debug clarity:
        "inactive" = disabled in devices.json (not wired), "unknown" = no
        recent fieldbus response on an active channel.
        """
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "Keuken LED", "active": False, "max_watt": 60},
                    {"ch": 1, "name": "Patio", "active": True, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        by_id = {d["id"]: d for d in devices}

        inactive = by_id["10.10.1.30-0"]
        assert inactive["active"] is False
        assert inactive["state"] == "inactive"
        assert inactive["current_watt"] == 0
        assert "level" not in inactive  # dimmer-velden leak niet door

        active = by_id["10.10.1.30-1"]
        assert active["active"] is True
        # Actieve channels mogen nooit "inactive" rapporteren.
        assert active["state"] != "inactive"
        assert active["state"] in ("on", "off", "unknown")

    def test_active_channel_unknown_state_unaffected(self) -> None:
        """Actieve channels zonder registry-state behouden 'unknown' (timeout).

        Beschermt tegen het per ongeluk overschrijven van "geen veldbus-respons"
        met "inactive".
        """
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "X", "active": True, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 1
        assert devices[0]["active"] is True
        # Geen registry-state → fallback "unknown", NIET "inactive".
        assert devices[0]["state"] == "unknown"

    def test_dimmer_no_registry_state_is_unknown(self) -> None:
        """Dimmer channels zonder registry-state rapporteren 'unknown' (geen
        "off"). Voorkomt dat de companion de lamp ten onrechte als uit toont
        vlak na een gateway-herstart (dimmer heeft geen on-demand statuspoll).
        """
        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [
                    {"ch": 0, "name": "Bureau", "active": True, "max_watt": 200},
                ],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 1
        d = devices[0]
        assert d["active"] is True
        assert d["state"] == "unknown"
        assert d["level"] is None
        assert d["current_watt"] == 0

    def test_dimmer_with_zero_level_is_off(self) -> None:
        """Dimmer met level=0 (uit) moet 'off' rapporteren, niet 'unknown'."""
        from gateway.device_registry import DeviceKey, DimmerState

        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [
                    {"ch": 0, "name": "Bureau", "active": True, "max_watt": 200},
                ],
            }
        ])
        api = _make_api(inst)
        api._registry.seed_dimmer_state(
            DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0), 0
        )

        devices = api._build_device_list()
        d = devices[0]
        assert d["state"] == "off"
        assert d["level"] == 0
        assert d["current_watt"] == 0

    def test_input_module_buttons_in_device_list(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa",
                "channels": [],
            }
        ])
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            buttons=[
                {
                    "index": 0,
                    "id": "2D2F8185190000DF",
                    "descr": "Badkamer knop",
                    "gr": "1e verdieping",
                }
            ]
        )
        api = _make_api(inst, cache=cache)
        devices = api._build_device_list()
        assert len(devices) == 1
        btn = devices[0]
        assert btn["id"] == "2f8185190000df"
        assert btn["device_type"] == "input"
        assert btn["semantic_type"] == "button"
        assert btn["module_id"] == "00:24:77:52:ad:aa"
        assert btn["module_ip"] == "10.10.1.50"
        assert btn["name"] == "Badkamer knop"
        assert btn["room"] == "1e verdieping"
        # 'active' is intentionally omitted for input-buttons so the
        # companion treats them as enabled-by-default.
        assert "active" not in btn

    def test_input_module_without_cached_buttons_no_device_entries(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa",
                "channels": [],
            }
        ])
        api = _make_api(inst)  # no cache
        assert api._build_device_list() == []

    def test_input_button_omits_active_field(self) -> None:
        """Regression: input-buttons must NOT carry an 'active' key in
        _build_device_list so the companion treats them as
        enabled-by-default.
        """
        inst = _make_installation([
            {
                "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa",
                "channels": [],
            }
        ])
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            buttons=[
                {"index": 0, "id": "2DCAFEBABE000001", "descr": "Test", "gr": "T"}
            ]
        )
        api = _make_api(inst, cache=cache)
        devices = api._build_device_list()
        assert len(devices) == 1
        assert "active" not in devices[0]


class TestBuildSnapshot:
    def test_snapshot_has_type_and_both_arrays(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "Light", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        snapshot = api._build_snapshot()
        assert snapshot["type"] == "snapshot"
        assert "modules" in snapshot
        assert "devices" in snapshot
        assert isinstance(snapshot["modules"], list)
        assert isinstance(snapshot["devices"], list)

    def test_snapshot_module_ids_match_device_module_ids(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "L1", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        snapshot = api._build_snapshot()
        module_ids = {m["id"] for m in snapshot["modules"]}
        device_module_ids = {d["module_id"] for d in snapshot["devices"]}
        assert device_module_ids <= module_ids, "all device.module_id values must appear in modules list"

    def test_snapshot_includes_inactive_devices(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "Active", "active": True, "max_watt": 60},
                    {"ch": 1, "name": "Inactive", "active": False, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)
        snapshot = api._build_snapshot()
        assert len(snapshot["devices"]) == 2
        assert {d["channel"] for d in snapshot["devices"]} == {0, 1}


class TestExecuteCommandInactive:
    """Inactive channels must reject commands and not send UDP."""

    @pytest.mark.asyncio
    async def test_inactive_relay_command_rejected(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "A", "active": True, "max_watt": 60},
                    {"ch": 1, "name": "B", "active": False, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)

        ok, error = await api._execute_command("10.10.1.30-1", "ON", None)
        assert ok is False
        assert error == "channel inactive"
        api._bus.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_inactive_dimmer_command_rejected(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [{"ch": 0, "name": "X", "active": False, "max_watt": 200}],
            }
        ])
        api = _make_api(inst)

        ok, error = await api._execute_command("10.10.1.40-0", "DIM", 50)
        assert ok is False
        assert error == "channel inactive"
        api._bus.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_relay_command_passes_guard(self) -> None:
        """Sanity check: guard must not over-reject. End-to-end reply is not
        asserted (bus is a MagicMock); the relevant assertion is that the
        command reaches the bus when the channel is active."""
        import asyncio
        from gateway.device_registry import DeviceKey, RelayState

        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "A", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        # Pre-seed a state reply so correlate_reply returns it.
        api._bus.last_send_ts = 0.0
        reply_future: asyncio.Future = asyncio.Future()
        reply_future.set_result(RelayState(state="on"))
        api._bus.correlate_reply = MagicMock(return_value=reply_future)  # type: ignore[assignment]
        send_future: asyncio.Future = asyncio.Future()
        send_future.set_result(None)
        api._bus.send_command.return_value = send_future

        ok, error = await api._execute_command("10.10.1.30-0", "ON", None)
        assert error is None
        assert ok is True
        api._bus.send_command.assert_called_once()


class TestDimmerDownstreamCommands:
    """Button / ramp wire dialect on dimmer channels.

    The IP0300PoE accepts the new TOGGLE / DIM_START / DIM_STOP actions in
    addition to the absolute DIM path. TOGGLE and DIM_STOP produce a status
    reply that must land on the right channel key; DIM_START is
    fire-and-forget.
    """

    @pytest.mark.asyncio
    async def test_dim_toggle_sends_t_frame_and_tracks_channel(self) -> None:
        """TOGGLE → ``T<ch>991000``; ``track_dimmer_channel`` called."""
        import asyncio
        from gateway.device_registry import DeviceKey, DimmerState

        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [{"ch": 1, "name": "Bureau", "active": True, "max_watt": 100}],
            }
        ])
        api = _make_api(inst)
        api._bus.last_send_ts = 0.0
        reply_future: asyncio.Future = asyncio.Future()
        reply_future.set_result(DimmerState(level_percent=42))
        api._bus.correlate_reply = MagicMock(return_value=reply_future)
        send_future: asyncio.Future = asyncio.Future()
        send_future.set_result(None)
        api._bus.send_command.return_value = send_future

        ok, error = await api._execute_command("10.10.1.40-1", "TOGGLE", None)
        assert ok is True
        assert error is None
        api._bus.send_command.assert_called_once_with(
            "10.10.1.40", b"T1991000"
        )

    @pytest.mark.asyncio
    async def test_dim_start_sends_d_start_no_reply(self) -> None:
        """DIM_START → ``D<ch>001003``; no correlate_reply awaited."""
        import asyncio

        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [{"ch": 0, "name": "Bureau", "active": True, "max_watt": 100}],
            }
        ])
        api = _make_api(inst)
        api._bus.last_send_ts = 0.0
        send_future: asyncio.Future = asyncio.Future()
        send_future.set_result(None)
        api._bus.send_command.return_value = send_future

        ok, error = await api._execute_command("10.10.1.40-0", "DIM_START", None)
        assert ok is True
        assert error is None
        api._bus.send_command.assert_called_once_with(
            "10.10.1.40", b"D0001003"
        )
        api._bus.correlate_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_dim_stop_sends_d_stop_and_tracks_channel(self) -> None:
        """DIM_STOP → ``D<ch>001000``; reply awaited, channel tracked."""
        import asyncio
        from gateway.device_registry import DeviceKey, DimmerState

        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [{"ch": 0, "name": "Bureau", "active": True, "max_watt": 100}],
            }
        ])
        api = _make_api(inst)
        api._bus.last_send_ts = 0.0
        reply_future: asyncio.Future = asyncio.Future()
        reply_future.set_result(DimmerState(level_percent=70))
        api._bus.correlate_reply = MagicMock(return_value=reply_future)
        send_future: asyncio.Future = asyncio.Future()
        send_future.set_result(None)
        api._bus.send_command.return_value = send_future

        ok, error = await api._execute_command("10.10.1.40-0", "DIM_STOP", None)
        assert ok is True
        assert error is None
        api._bus.send_command.assert_called_once_with(
            "10.10.1.40", b"D0001000"
        )
        api._bus.correlate_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_dimmer_action_rejected(self) -> None:
        """Unknown dimmer actions return a typed error (no UDP sent)."""
        inst = _make_installation([
            {
                "ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8",
                "channels": [{"ch": 0, "name": "Bureau", "active": True, "max_watt": 100}],
            }
        ])
        api = _make_api(inst)

        ok, error = await api._execute_command("10.10.1.40-0", "PULSE", None)
        assert ok is False
        assert "unsupported dimmer action" in (error or "")
        api._bus.send_command.assert_not_called()


class TestStateChangedInactive:
    """state_changed for inactive channels must be suppressed."""

    def test_inactive_relay_state_changed_is_none(self) -> None:
        from gateway.device_registry import DeviceKey, RelayState

        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 3, "name": "Wire-it", "active": False, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 3)
        msg = api._build_state_changed(key, RelayState(state="on"))
        assert msg is None


class TestLastSeenFields:
    """Module resource includes last_seen / last_seen_source runtime fields."""

    def test_module_list_includes_last_seen_when_set(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [],
            }
        ])
        # Set runtime-only fields on the ModuleConfig
        inst.modules[0].last_seen = "2026-06-04T18:00:00Z"
        inst.modules[0].last_seen_source = "arp"

        api = _make_api(inst)
        modules = api._build_module_list()

        assert len(modules) == 1
        assert modules[0]["last_seen"] == "2026-06-04T18:00:00Z"
        assert modules[0]["last_seen_source"] == "arp"

    def test_module_list_excludes_last_seen_when_not_set(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [],
            }
        ])
        # last_seen is None by default
        api = _make_api(inst)
        modules = api._build_module_list()

        assert "last_seen" not in modules[0]
        assert "last_seen_source" not in modules[0]


class TestGatewayStatus:
    """Health and status REST endpoints."""

    @pytest.mark.asyncio
    async def test_health_returns_status_and_version(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        response = await api._get_health(MagicMock())
        body = json.loads(response.text)
        assert body["status"] == "ok"
        assert "version" in body
        assert "issues" not in body

    @pytest.mark.asyncio
    async def test_status_returns_full_snapshot(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        response = await api._get_status(MagicMock())
        body = json.loads(response.text)
        assert body["status"] == "ok"
        assert "subsystems" in body
        assert "issues" in body
        assert "actions" in body
        assert "uptime_seconds" in body

    def test_snapshot_includes_gateway_status(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        snap = api._build_snapshot()
        assert "gateway_status" in snap
        assert snap["gateway_status"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_status_degraded_when_issue_reported(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        api._health.report_issue(
            "module_metadata.getSysSet.10.10.1.30",
            "module_metadata.http_failed",
            "warning",
            "HTTP getSysSet 10.10.1.30 failed",
            {"ip": "10.10.1.30", "method": "getSysSet"},
        )
        response = await api._get_status(MagicMock())
        body = json.loads(response.text)
        assert body["status"] == "degraded"
        assert len(body["issues"]) == 1


class TestDiscoveryEndpoint:

    @pytest.mark.asyncio
    async def test_discover_returns_503_when_no_orchestrator(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        # No orchestrator set — handler raises ApiError which the
        # api_error_middleware translates to a typed 503 response.
        request = MagicMock()
        request.match_info = {}
        with pytest.raises(gateway_api.ApiError) as exc_info:
            await api._post_discover(request)
        assert exc_info.value.status == 503
        assert exc_info.value.code == "orchestrator_unavailable"

        # Verify middleware produces the expected JSON shape.
        err = exc_info.value
        response = gateway_api._json_error(err)
        assert response.status == 503
        body = json.loads(response.body)
        assert body == {
            "error": "orchestrator_unavailable",
            "message": "Discovery orchestrator not available",
        }


class TestModuleRefreshOne:
    """POST /api/v1/modules/{module_id}/refresh — single-module metadata refresh."""

    @pytest.mark.asyncio
    async def test_module_refresh_one_calls_cache_and_broadcasts(self) -> None:
        inst = _make_installation([
            {
                "name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "model": "IP0200PoE",
                "firmware": "5.1", "channels": [],
            }
        ])
        api = _make_api(inst)
        api._meta_cache.refresh_one = AsyncMock(return_value=None)  # type: ignore[assignment]

        with patch("asyncio.create_task") as create_task:
            request = MagicMock()
            request.match_info = {"module_id": "00:24:77:52:ac:be"}
            response = await api._post_module_refresh(request)

        assert response.status == 200
        body = json.loads(response.text)
        assert body["id"] == "00:24:77:52:ac:be"
        assert body["schema_version"] == 2
        api._meta_cache.refresh_one.assert_awaited_once()
        assert create_task.called

    @pytest.mark.asyncio
    async def test_module_refresh_unknown_mac_returns_404(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        request = MagicMock()
        request.match_info = {"module_id": "00:24:77:00:00:00"}

        with pytest.raises(gateway_api.ApiError) as exc_info:
            await api._post_module_refresh(request)
        assert exc_info.value.status == 404
        assert exc_info.value.code == "module_not_found"


class TestModulesRefreshBroadcast:
    """POST /api/v1/modules/refresh must broadcast a new snapshot to WS clients.

    Companion side (issue #4 acceptance criterion): newly discovered input
    buttons should appear in the EventEntity list without a manual reload.
    """

    @pytest.mark.asyncio
    async def test_modules_refresh_schedules_snapshot_broadcast(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa", "channels": []}
        ])
        api = _make_api(inst)
        api._meta_cache.refresh = AsyncMock(return_value=None)  # type: ignore[assignment]

        with patch("asyncio.create_task") as create_task:
            response = await api._post_modules_refresh(MagicMock())

        assert response.status == 200
        # Snapshot broadcast must be scheduled (snapshot of the latest
        # module + device list) so connected WS clients see the refreshed
        # input buttons without a manual reload.
        assert create_task.called, "modules/refresh must schedule a snapshot broadcast"
        msg = create_task.call_args.args[0]
        # The coroutine wraps self._broadcast(self._build_snapshot()); the
        # exact coroutine object isn't easy to introspect, so check that
        # create_task was called at all and the response was a 200.
        assert msg is not None
