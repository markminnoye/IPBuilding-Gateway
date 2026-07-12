"""Tests for gateway.state_poll — UDP relay status sweep at startup."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.payloads.relay import encode_relay_status_poll
from gateway.state_poll import sweep_relay_states
from gateway.types import DeviceType
from gateway.udp_bus import UDPBus


def _make_installation(modules: list[dict[str, Any]]) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules})


class TestEncodeRelayStatusPoll:
    def test_channel_zero(self) -> None:
        assert encode_relay_status_poll(0) == b"I0000"

    def test_channel_eighteen(self) -> None:
        assert encode_relay_status_poll(18) == b"I1800"

    def test_channel_twenty_three(self) -> None:
        assert encode_relay_status_poll(23) == b"I2300"


class TestSweepRelayStates:
    @pytest.mark.asyncio
    async def test_no_relay_modules_returns_zero(self) -> None:
        registry = DeviceRegistry()
        bus = UDPBus(GatewayConfig(simulated_mode=True))
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.50",
                    "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "channels": [],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_seeds_single_channel_without_callbacks(self) -> None:
        registry = DeviceRegistry()
        cb = MagicMock()
        registry.on_state_changed(cb)
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I1800", b"I000180100")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 18, "name": "Test", "active": True, "max_watt": 60},
                    ],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 1
            key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 18)
            rs = registry.get_relay_state(key)
            assert rs is not None
            assert rs.state == "on"
            assert rs.state_code == "0100"
            cb.assert_not_called()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_timeout_leaves_channel_unknown(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=50))
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 5, "name": "Timeout", "active": True, "max_watt": 60},
                    ],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0, reply_timeout_ms=50,
            )
            assert result == 0
            key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 5)
            assert registry.get_relay_state(key) is None
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_multi_channel_sweep(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I1700", b"I000170000")
        bus.register_simulated_reply(b"I1800", b"I000180100")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 17, "name": "A", "active": True, "max_watt": 60},
                        {"ch": 18, "name": "B", "active": True, "max_watt": 60},
                    ],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 2
            rs17 = registry.get_relay_state(
                DeviceKey(DeviceType.RELAY, "10.10.1.30", 17),
            )
            rs18 = registry.get_relay_state(
                DeviceKey(DeviceType.RELAY, "10.10.1.30", 18),
            )
            assert rs17 is not None and rs17.state == "off"
            assert rs18 is not None and rs18.state == "on"
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_wrong_channel_reply_not_accepted(self) -> None:
        """Reply for a different channel must not seed the queried channel."""
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=50))
        # Query I1800 but simulated reply is for channel 19 only.
        bus.register_simulated_reply(b"I1800", b"I000190100")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 18, "name": "Mismatch", "active": True, "max_watt": 60},
                    ],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0, reply_timeout_ms=50,
            )
            assert result == 0
            assert registry.get_relay_state(
                DeviceKey(DeviceType.RELAY, "10.10.1.30", 18),
            ) is None
        finally:
            await bus.stop()
