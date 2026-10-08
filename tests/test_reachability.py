"""Module reply timing and the reachability check.

New examples use the documentation range 192.0.2.0/24 and a locally
administered MAC. Timing is taken from packets the bus already sends;
the poll schedule is not moved.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import ApiError, GatewayAPI
from gateway.installation import InstallationConfig
from gateway.reachability import (
    ReachabilityTracker,
    confirmation_ms,
    reported_fields,
)
from gateway.udp_bus import UDPBus, UDPPacket, poll_payload_for


def _tracker() -> ReachabilityTracker:
    return ReachabilityTracker(
        timeout_s=0.5,
        wall_clock=lambda: "2026-10-08T12:00:00+00:00",
    )


def _packet(src_ip: str, data: bytes, ts: float) -> UDPPacket:
    return UDPPacket(
        data=data,
        src_ip=src_ip,
        src_port=1001,
        dst_ip="192.0.2.1",
        dst_port=1001,
        monotonic_ts=ts,
    )


class TestReachabilityTracker:
    def test_pairs_a_reply_inside_the_window(self) -> None:
        tracker = _tracker()
        tracker.note_send("192.0.2.10", 10.0)
        tracker.note_send("192.0.2.10", 10.1)
        elapsed = tracker.note_reply("192.0.2.10", 10.15)
        view = tracker.view("192.0.2.10")
        assert elapsed == 50
        assert view["last_reply_ms"] == 50
        assert view["avg_reply_ms"] == 50
        assert view["missed_replies"] == 0
        assert view["last_reply_at"] == "2026-10-08T12:00:00+00:00"

    def test_send_outside_the_window_is_a_miss(self) -> None:
        tracker = _tracker()
        tracker.note_send("192.0.2.10", 0.0)
        tracker.note_send("192.0.2.10", 1.0)
        assert tracker.view("192.0.2.10")["missed_replies"] == 1

    def test_late_reply_counts_a_miss_and_still_marks_contact(self) -> None:
        tracker = _tracker()
        tracker.note_send("192.0.2.10", 0.0)
        assert tracker.note_reply("192.0.2.10", 0.8) is None
        view = tracker.view("192.0.2.10")
        assert view["missed_replies"] == 1
        assert view["last_reply_at"] == "2026-10-08T12:00:00+00:00"
        assert view["last_reply_ms"] is None
        assert view["avg_reply_ms"] is None

    def test_timeout_counts_once(self) -> None:
        tracker = _tracker()
        tracker.note_send("192.0.2.10", 0.0)
        tracker.note_timeout("192.0.2.10", 0.2)
        assert tracker.view("192.0.2.10")["missed_replies"] == 0
        tracker.note_timeout("192.0.2.10", 0.5)
        tracker.note_timeout("192.0.2.10", 1.0)
        assert tracker.view("192.0.2.10")["missed_replies"] == 1

    def test_average_uses_the_last_twenty_samples(self) -> None:
        tracker = _tracker()
        for index in range(20):
            tracker.note_send("192.0.2.10", index * 10.0)
            tracker.note_reply("192.0.2.10", index * 10.0 + 0.010)
        tracker.note_send("192.0.2.10", 1000.0)
        tracker.note_reply("192.0.2.10", 1000.030)
        view = tracker.view("192.0.2.10")
        assert view["last_reply_ms"] == 30
        assert view["avg_reply_ms"] == 11

    def test_unknown_module_is_empty(self) -> None:
        view = _tracker().view("192.0.2.10")
        assert view == {
            "last_reply_at": None,
            "last_reply_ms": None,
            "avg_reply_ms": None,
            "missed_replies": 0,
        }

    def test_classify(self) -> None:
        tracker = _tracker()
        assert tracker.classify(None) == "none"
        assert tracker.classify(200) == "ok"
        assert tracker.classify(201) == "slow"


def test_reported_fields_and_confirmation_ms() -> None:
    assert reported_fields(b"I000000100") == {"state": "on"}
    assert reported_fields(b"I0115184") == {"level_percent": 84}
    assert reported_fields(b"not-a-status") is None
    packet = _packet("192.0.2.10", b"I000000100", 1.2)
    assert confirmation_ms(1.0, packet) == 200
    assert confirmation_ms(1.0, MagicMock()) is None
    assert confirmation_ms(1.0, None) is None


def test_poll_payloads() -> None:
    assert poll_payload_for("relay") == b"P0000"
    assert poll_payload_for("dimmer") == b"I9900"
    assert poll_payload_for("input") == b"I0000"
    assert poll_payload_for("other") is None


@pytest.mark.asyncio
async def test_bus_records_a_reply_without_waiting() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
    await bus.send_command("192.0.2.10", b"P0000")
    assert bus.reachability.view("192.0.2.10")["last_reply_at"] is None
    bus._notify_listeners(
        _packet("192.0.2.10", b"P000000000", bus.last_send_ts + 0.030)
    )
    view = bus.reachability.view("192.0.2.10")
    assert view["last_reply_ms"] == 30
    assert view["missed_replies"] == 0


@pytest.mark.asyncio
async def test_fire_and_forget_send_is_not_a_miss() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
    await bus.send_command("192.0.2.20", b"D0001003", expect_reply=False)
    bus._notify_listeners(
        _packet("192.0.2.20", b"I0115184", bus.last_send_ts + 0.8)
    )
    view = bus.reachability.view("192.0.2.20")
    assert view["missed_replies"] == 0
    assert view["last_reply_ms"] is None
    assert view["last_reply_at"] is not None


def _installation() -> InstallationConfig:
    return InstallationConfig._parse({
        "modules": [
            {
                "ip": "192.0.2.10",
                "type": "relay",
                "mac": "02:00:00:00:00:01",
                "channels": [{"ch": 0, "name": "Lamp", "active": True}],
            },
            {
                "ip": "192.0.2.20",
                "type": "dimmer",
                "mac": "02:00:00:00:00:02",
                "channels": [{"ch": 0, "name": "Lamp", "active": True}],
            },
            {
                "ip": "192.0.2.30",
                "type": "input",
                "mac": "02:00:00:00:00:03",
                "channels": [],
            },
        ]
    })


def _api(bus: object, installation: InstallationConfig | None) -> GatewayAPI:
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.expose_inactive_channels = False
    cfg.buttons_via_ha = True
    cfg.claims_input_modules = True
    cfg.hub_role = "slave"
    cfg.input_mode_label = "Slave"
    cfg.multi_press = False
    cfg.multi_press_window_ms = 350
    cfg.reply_timeout_ms = 500
    cfg.remote_debugging = False
    registry = DeviceRegistry()
    if installation is not None:
        for module in installation.modules:
            registry.register_module(module.ip, module.type)
    return GatewayAPI(bus, registry, cfg)


class _Request:
    def __init__(self, body: dict | None = None) -> None:
        self._body = body or {}
        self.match_info: dict[str, str] = {}

    async def json(self) -> dict:
        return self._body


class _WS:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_command_reports_confirmation_and_state() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
    bus.register_simulated_reply(b"S0000", b"I000000100")
    api = _api(bus, _installation())

    result = await api._execute_command("192.0.2.10-0", "ON", None)
    assert result.ok is True
    assert result.error is None
    assert result.module_confirmed is True
    assert result.confirm_ms is not None and result.confirm_ms < 500
    assert result.reported == {"state": "on"}
    assert bus.reachability.view("192.0.2.10")["missed_replies"] == 0

    request = _Request({"action": "ON"})
    request.match_info["device_id"] = "192.0.2.10-0"
    response = await api._post_command(request)  # type: ignore[arg-type]
    body = json.loads(response.text)
    assert response.status == 200
    assert body["ok"] is True
    assert body["schema_version"] == 2
    assert body["module_confirmed"] is True
    assert isinstance(body["confirm_ms"], int)
    assert body["reported"] == {"state": "on"}

    ws = _WS()
    await api._handle_ws_command(
        ws,  # type: ignore[arg-type]
        json.dumps({"type": "command", "id": "192.0.2.10-0", "action": "ON"}),
    )
    assert ws.sent[-1]["type"] == "command_result"
    assert ws.sent[-1]["ok"] is True
    assert ws.sent[-1]["module_confirmed"] is True
    assert ws.sent[-1]["reported"] == {"state": "on"}


@pytest.mark.asyncio
async def test_command_without_reply_is_not_an_error() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=40))
    api = _api(bus, _installation())
    result = await api._execute_command("192.0.2.10-0", "ON", None)
    assert result.ok is True
    assert result.error is None
    assert result.module_confirmed is False
    assert result.confirm_ms is None
    assert result.reported is None
    assert bus.reachability.view("192.0.2.10")["missed_replies"] == 1


@pytest.mark.asyncio
async def test_dim_start_does_not_wait_or_count_a_miss() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=40))
    api = _api(bus, _installation())
    result = await api._execute_command("192.0.2.20-0", "DIM_START", None)
    assert result.ok is True
    assert result.module_confirmed is False
    assert result.confirm_ms is None
    assert result.reported is None
    assert bus.reachability.view("192.0.2.20")["missed_replies"] == 0


@pytest.mark.asyncio
async def test_dimmer_reply_reports_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.gateway_api.time.monotonic", lambda: 5000.0)
    bus = MagicMock()
    bus.last_send_ts = 5000.0
    bus.reachability = ReachabilityTracker(timeout_s=0.5)
    bus.send_command = AsyncMock()
    bus.correlate_reply = AsyncMock(
        return_value=_packet("192.0.2.20", b"I0115184", 5000.080)
    )
    api = _api(bus, _installation())
    result = await api._execute_command("192.0.2.20-0", "DIM", 84)
    assert result.module_confirmed is True
    assert result.confirm_ms == 80
    assert result.reported == {"level_percent": 84}


def test_module_list_includes_reachability() -> None:
    bus = UDPBus(GatewayConfig(simulated_mode=True))
    bus.reachability.note_send("192.0.2.10", 1.0)
    bus.reachability.note_reply("192.0.2.10", 1.018)
    api = _api(bus, _installation())
    listed = {module["id"]: module for module in api._build_module_list()}
    assert listed["02:00:00:00:00:01"]["reachability"]["last_reply_ms"] == 18
    assert listed["02:00:00:00:00:02"]["reachability"]["last_reply_at"] is None
    assert listed["02:00:00:00:00:02"]["reachability"]["missed_replies"] == 0

    plain = _api(MagicMock(), _installation())
    assert plain._build_module_list()[0]["reachability"]["missed_replies"] == 0


@pytest.mark.asyncio
async def test_reachability_check_classifies_and_leaves_poll_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = MagicMock()
    bus.last_send_ts = 1000.0
    bus._next_poll_ts = {"192.0.2.10": 99.0}
    bus.reachability = ReachabilityTracker(timeout_s=0.5)
    sent: list[tuple[str, bytes]] = []

    async def send(module_ip: str, payload: bytes, *args: object, **kwargs: object) -> None:
        sent.append((module_ip, payload))

    async def correlate(*, module_ip: str, after_ts: float, timeout_ms: int) -> UDPPacket | None:
        if module_ip == "192.0.2.10":
            return _packet(module_ip, b"P000000000", 1000.040)
        if module_ip == "192.0.2.20":
            return _packet(module_ip, b"I0154999", 1000.250)
        return None

    bus.send_command = send
    bus.correlate_reply = correlate
    api = _api(bus, _installation())
    api._cfg.claims_input_modules = False
    monkeypatch.setattr("gateway.gateway_api.time.monotonic", lambda: 1000.0)

    response = await api._post_modules_reachability(_Request())  # type: ignore[arg-type]
    body = json.loads(response.text)
    by_id = {item["id"]: item for item in body["modules"]}
    assert body["ok"] is True
    assert body["schema_version"] == 2
    assert by_id["02:00:00:00:00:01"] == {
        "id": "02:00:00:00:00:01",
        "reachability": "ok",
        "reply_ms": 40,
    }
    assert by_id["02:00:00:00:00:02"]["reachability"] == "slow"
    assert by_id["02:00:00:00:00:02"]["reply_ms"] == 250
    assert by_id["02:00:00:00:00:03"] == {
        "id": "02:00:00:00:00:03",
        "reachability": "none",
        "reply_ms": None,
    }
    assert sent == [
        ("192.0.2.10", b"P0000"),
        ("192.0.2.20", b"I9900"),
    ]
    assert bus._next_poll_ts == {"192.0.2.10": 99.0}


@pytest.mark.asyncio
async def test_reachability_check_is_rate_limited() -> None:
    api = _api(MagicMock(), _installation())
    first = await api._post_modules_reachability(_Request())  # type: ignore[arg-type]
    assert first.status == 200
    with pytest.raises(ApiError) as caught:
        await api._post_modules_reachability(_Request())  # type: ignore[arg-type]
    assert caught.value.status == 429
    assert caught.value.code == "reachability_rate_limited"


@pytest.mark.asyncio
async def test_reachability_check_without_installation() -> None:
    api = _api(MagicMock(), None)
    with pytest.raises(ApiError) as caught:
        await api._post_modules_reachability(_Request())  # type: ignore[arg-type]
    assert caught.value.status == 500
    assert caught.value.code == "no_installation"


@pytest.mark.asyncio
async def test_status_advertises_module_reachability() -> None:
    api = _api(MagicMock(), _installation())
    body = json.loads((await api._get_status(MagicMock())).text)
    assert "module_reachability" in body["capabilities"]
