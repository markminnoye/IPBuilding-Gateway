"""Raw field-bus send behind remote debugging."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from gateway.config import DiscoveryConfig, GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import ApiError, GatewayAPI
from gateway.installation import InstallationConfig
from gateway.raw_send import SendPolicy
from gateway.types import DeviceKey, DeviceType
from gateway.udp_bus import UDPBus, UDPPacket


def _installation() -> InstallationConfig:
    return InstallationConfig._parse(
        {
            "modules": [
                {
                    "name": "Relay",
                    "ip": "192.0.2.10",
                    "type": "relay",
                    "mac": "02:00:00:00:00:01",
                    "channels": [
                        {"ch": 3, "name": "Lamp", "active": True, "max_watt": 10}
                    ],
                }
            ]
        }
    )


def _config(**kwargs: Any) -> GatewayConfig:
    return GatewayConfig(
        devices_file="/tmp/ipbuilding-raw-send-devices.json",
        installation=_installation(),
        discovery=DiscoveryConfig(subnet="192.0.2"),
        hub_port=1001,
        simulated_mode=True,
        **kwargs,
    )


class _Bus:
    def __init__(self, replies: list[UDPPacket] | None = None) -> None:
        self.sent: list[tuple[Any, ...]] = []
        self.held: list[tuple[str, float]] = []
        self.released: list[str] = []
        self.replies = replies or []
        self.truncated = False

    def hold_status(self, module_ip: str, until: float) -> None:
        self.held.append((module_ip, until))

    def release_hold(self, module_ip: str) -> None:
        self.released.append(module_ip)

    async def send_command(self, module_ip: str, payload: bytes, port: int, **kwargs: Any) -> None:
        self.sent.append((module_ip, payload, port, kwargs.get("expect_reply")))

    async def collect_replies(self, **kwargs: Any) -> tuple[list[UDPPacket], bool]:
        return self.replies, self.truncated


class _Request:
    def __init__(self, body: dict[str, Any], remote: str = "192.0.2.8") -> None:
        self._body = body
        self.remote = remote

    async def json(self) -> dict[str, Any]:
        return self._body


def _api(bus: _Bus, *, remote_debugging: bool) -> GatewayAPI:
    cfg = _config(remote_debugging=remote_debugging)
    return GatewayAPI(bus, DeviceRegistry(), cfg)  # type: ignore[arg-type]


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "module_ip": "192.0.2.10",
        "payload_hex": "5030303030",
        "window_ms": 50,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_raw_send_refused_when_remote_debugging_is_off() -> None:
    bus = _Bus()
    api = _api(bus, remote_debugging=False)
    with pytest.raises(ApiError) as caught:
        await api._post_debug_raw_send(_Request(_body()))  # type: ignore[arg-type]
    assert caught.value.status == 403
    assert caught.value.code == "remote_debugging_disabled"
    assert bus.sent == []


@pytest.mark.asyncio
async def test_raw_send_returns_sent_bytes_and_replies() -> None:
    reply = UDPPacket(
        data=b"I000030100",
        src_ip="192.0.2.10",
        src_port=1001,
        dst_ip="192.0.2.1",
        dst_port=1001,
        monotonic_ts=1000.04,
    )
    bus = _Bus([reply])
    api = _api(bus, remote_debugging=True)
    api._raw_send._monotonic = lambda: 1000.0  # type: ignore[method-assign]
    response = await api._post_debug_raw_send(_Request(_body()))  # type: ignore[arg-type]
    body = json.loads(response.text)
    assert body["ok"] is True
    assert body["schema_version"] == 2
    assert body["sent_hex"] == "5030303030"
    assert body["module_ip"] == "192.0.2.10"
    assert body["port"] == 1001
    assert body["window_ms"] == 50
    assert body["replies"] == [{"hex": b"I000030100".hex(), "delay_ms": 40}]
    assert body["truncated"] is False
    assert bus.sent == [("192.0.2.10", b"P0000", 1001, False)]
    assert bus.held and bus.held[0][0] == "192.0.2.10"


@pytest.mark.asyncio
async def test_raw_send_rejects_outside_allowlist_oversized_and_rate() -> None:
    api = _api(_Bus(), remote_debugging=True)
    with pytest.raises(ApiError) as outside:
        await api._post_debug_raw_send(  # type: ignore[arg-type]
            _Request(_body(module_ip="198.51.100.10"))
        )
    assert outside.value.status == 422
    assert outside.value.code == "target_not_allowed"

    with pytest.raises(ApiError) as huge:
        await api._post_debug_raw_send(  # type: ignore[arg-type]
            _Request(_body(payload_hex="aa" * 65))
        )
    assert huge.value.code == "payload_too_large"

    with pytest.raises(ApiError) as port:
        await api._post_debug_raw_send(  # type: ignore[arg-type]
            _Request(_body(port=9))
        )
    assert port.value.code == "invalid_port"

    clock = {"now": 5000.0}
    api._raw_send._monotonic = lambda: clock["now"]  # type: ignore[method-assign]
    for _ in range(5):
        await api._post_debug_raw_send(_Request(_body()))  # type: ignore[arg-type]
    with pytest.raises(ApiError) as limited:
        await api._post_debug_raw_send(_Request(_body()))  # type: ignore[arg-type]
    assert limited.value.status == 429
    assert limited.value.code == "raw_send_rate_limited"


@pytest.mark.asyncio
async def test_subnet_host_is_allowed_when_not_in_the_installation() -> None:
    api = _api(_Bus(), remote_debugging=True)
    response = await api._post_debug_raw_send(  # type: ignore[arg-type]
        _Request(_body(module_ip="192.0.2.40"))
    )
    assert json.loads(response.text)["module_ip"] == "192.0.2.40"


@pytest.mark.asyncio
async def test_websocket_raw_send_uses_the_same_refusal() -> None:
    api = _api(_Bus(), remote_debugging=False)
    sent: list[dict[str, Any]] = []

    class _Ws:
        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    await api._handle_ws_command(
        _Ws(),  # type: ignore[arg-type]
        json.dumps({"type": "raw_send", "module_ip": "192.0.2.10", "payload_hex": "50"}),
    )
    assert sent[0]["error"] == "remote_debugging_disabled"
    assert sent[0]["type"] == "error"


@pytest.mark.asyncio
async def test_status_advertises_raw_send() -> None:
    api = _api(_Bus(), remote_debugging=False)
    body = json.loads((await api._get_status(None)).text)  # type: ignore[arg-type]
    assert body["capabilities"] == ["log_stream", "udp_frame", "raw_send"]


def test_policy_uses_known_modules_and_subnet() -> None:
    api = _api(_Bus(), remote_debugging=True)
    policy = api._raw_send_policy()
    assert isinstance(policy, SendPolicy)
    assert "192.0.2.10" in policy.known_ips
    assert policy.subnet == "192.0.2"
    assert policy.hub_port == 1001


@pytest.mark.asyncio
async def test_hold_skips_poll_and_status_then_normal_control_works() -> None:
    cfg = _config()
    bus = UDPBus(cfg)
    registry = DeviceRegistry()
    registry.register_module("192.0.2.10", DeviceType.RELAY)
    bus.add_listener(registry.handle_packet)
    bus.register_simulated_reply(b"PING", b"I000030100")
    key = DeviceKey(DeviceType.RELAY, "192.0.2.10", 3)

    bus.hold_status("192.0.2.10", time.monotonic() + 5)
    await bus.send_command("192.0.2.10", b"PING", expect_reply=False)
    assert registry.get_relay_state(key) is None

    calls: list[str] = []

    async def _keepalive(module_ip: str, payload: bytes) -> None:
        calls.append(module_ip)

    bus._send_keepalive = _keepalive  # type: ignore[method-assign]
    await bus._poll_due_modules(time.monotonic())
    assert calls == []

    bus.release_hold("192.0.2.10")
    await bus.send_command("192.0.2.10", b"PING", expect_reply=False)
    assert registry.get_relay_state(key) is not None
    assert registry.get_relay_state(key).state == "on"


@pytest.mark.asyncio
async def test_collect_replies_caps_the_window() -> None:
    bus = UDPBus(_config())
    early = UDPPacket(b"early", "192.0.2.10", 1001, "192.0.2.1", 1001, 1.0)
    first = UDPPacket(b"one", "192.0.2.10", 1001, "192.0.2.1", 1001, 2.0)
    second = UDPPacket(b"two", "192.0.2.10", 1001, "192.0.2.1", 1001, 2.1)
    other = UDPPacket(b"nope", "192.0.2.20", 1001, "192.0.2.1", 1001, 2.2)
    bus._notify_listeners(early)
    bus._notify_listeners(first)
    bus._notify_listeners(second)
    bus._notify_listeners(other)
    found, truncated = await bus.collect_replies(
        module_ip="192.0.2.10",
        after_ts=2.0,
        timeout_ms=20,
        limit=1,
    )
    assert [pkt.data for pkt in found] == [b"one"]
    assert truncated is True


def test_input_channel_31_is_listed_when_the_button_is_active() -> None:
    """The device list does not skip channel 31. A hole is a missing button."""
    buttons = []
    for channel in range(33):
        buttons.append(
            {
                "id": f"{channel:08x}",
                "channel": channel,
                "name": f"Button {channel}",
                "active": channel != 31,
            }
        )
    buttons.append(
        {
            "id": "00000031",
            "channel": 31,
            "name": "Button 31",
            "active": True,
        }
    )
    installation = InstallationConfig._parse(
        {
            "modules": [
                {
                    "name": "Input",
                    "ip": "192.0.2.50",
                    "type": "input",
                    "mac": "02:00:00:00:00:32",
                    "pushbuttons": buttons,
                }
            ]
        }
    )
    api = GatewayAPI(
        _Bus(),  # type: ignore[arg-type]
        DeviceRegistry(),
        GatewayConfig(
            devices_file="/tmp/ipbuilding-raw-send-devices.json",
            installation=installation,
            buttons_via_ha=True,
        ),
    )
    listed = {
        device["channel"]
        for device in api._build_device_list()
        if device["device_type"] == "input"
    }
    assert 31 in listed
    assert listed == set(range(33))

    hidden = InstallationConfig._parse(
        {
            "modules": [
                {
                    "name": "Input",
                    "ip": "192.0.2.50",
                    "type": "input",
                    "mac": "02:00:00:00:00:32",
                    "pushbuttons": [
                        {
                            "id": f"{channel:08x}",
                            "channel": channel,
                            "name": f"Button {channel}",
                            "active": channel != 31,
                        }
                        for channel in list(range(31)) + [32]
                    ]
                    + [
                        {
                            "id": "00000031",
                            "channel": 31,
                            "name": "Button 31",
                            "active": False,
                        }
                    ],
                }
            ]
        }
    )
    hidden_api = GatewayAPI(
        _Bus(),  # type: ignore[arg-type]
        DeviceRegistry(),
        GatewayConfig(
            devices_file="/tmp/ipbuilding-raw-send-devices.json",
            installation=hidden,
            buttons_via_ha=True,
        ),
    )
    hidden_channels = {
        device["channel"]
        for device in hidden_api._build_device_list()
        if device["device_type"] == "input"
    }
    assert hidden_channels == set(range(31)) | {32}
    shown = {
        device["channel"]
        for device in hidden_api._build_device_list(include_inactive=True)
        if device["device_type"] == "input"
    }
    assert 31 in shown
