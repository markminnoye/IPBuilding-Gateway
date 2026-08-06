"""Tests for gateway.state_poll — UDP actuator status sweeps at startup."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.payloads.dimmer import encode_dimmer_status_poll
from gateway.payloads.relay import encode_relay_status_poll
from gateway.state_poll import sweep_dimmer_states, sweep_relay_states
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
    async def test_skips_inactive_channels(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I0000", b"I000000100")
        bus.register_simulated_reply(b"I0100", b"I000100100")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 0, "name": "Active", "active": True, "max_watt": 60},
                        {"ch": 1, "name": "Ch 1", "active": False, "max_watt": 60},
                    ],
                },
            ])
            result = await sweep_relay_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 1
            assert registry.get_relay_state(
                DeviceKey(DeviceType.RELAY, "10.10.1.30", 0),
            ) is not None
            assert registry.get_relay_state(
                DeviceKey(DeviceType.RELAY, "10.10.1.30", 1),
            ) is None
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


class TestEncodeDimmerStatusPoll:
    def test_channel_zero(self) -> None:
        assert encode_dimmer_status_poll(0) == b"I0000000"

    def test_channel_two(self) -> None:
        assert encode_dimmer_status_poll(2) == b"I2000000"


class TestSweepDimmerStates:
    @pytest.mark.asyncio
    async def test_no_dimmer_modules_returns_zero(self) -> None:
        registry = DeviceRegistry()
        bus = UDPBus(GatewayConfig(simulated_mode=True))
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [],
                },
            ])
            result = await sweep_dimmer_states(
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
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I2000000", b"I0154299")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:ad:01",
                    "channels": [
                        {"ch": 2, "name": "Test", "active": True, "max_watt": 100},
                    ],
                },
            ])
            result = await sweep_dimmer_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 1
            key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 2)
            ds = registry.get_dimmer_state(key)
            assert ds is not None
            assert ds.level_percent == 100
            assert ds.internal_value_code == "299"
            cb.assert_not_called()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_timeout_leaves_channel_unknown(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=50))
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:ad:01",
                    "channels": [
                        {"ch": 1, "name": "Timeout", "active": True, "max_watt": 100},
                    ],
                },
            ])
            result = await sweep_dimmer_states(
                bus, registry, inst, inter_query_delay_s=0, reply_timeout_ms=50,
            )
            assert result == 0
            key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1)
            assert registry.get_dimmer_state(key) is None
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_multi_channel_sweep(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I0000000", b"I0154000")
        bus.register_simulated_reply(b"I2000000", b"I0154299")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:ad:01",
                    "channels": [
                        {"ch": 0, "name": "A", "active": True, "max_watt": 100},
                        {"ch": 2, "name": "B", "active": True, "max_watt": 100},
                    ],
                },
            ])
            result = await sweep_dimmer_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 2
            ds0 = registry.get_dimmer_state(
                DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0),
            )
            ds2 = registry.get_dimmer_state(
                DeviceKey(DeviceType.DIMMER, "10.10.1.40", 2),
            )
            assert ds0 is not None and ds0.level_percent == 0
            assert ds2 is not None and ds2.level_percent == 100
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_skips_inactive_channels(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=500))
        bus.register_simulated_reply(b"I0000000", b"I0154000")
        bus.register_simulated_reply(b"I1000000", b"I0154150")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:ad:01",
                    "channels": [
                        {"ch": 0, "name": "Active", "active": True, "max_watt": 100},
                        {"ch": 1, "name": "Ch 1", "active": False, "max_watt": 100},
                    ],
                },
            ])
            result = await sweep_dimmer_states(
                bus, registry, inst, inter_query_delay_s=0,
            )
            assert result == 1
            assert registry.get_dimmer_state(
                DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0),
            ) is not None
            assert registry.get_dimmer_state(
                DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1),
            ) is None
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_wrong_channel_reply_not_accepted(self) -> None:
        """Reply for a different channel must not seed the queried channel."""
        registry = DeviceRegistry()
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        bus = UDPBus(GatewayConfig(simulated_mode=True, reply_timeout_ms=50))
        # Query I1000000 but simulated reply is for channel 0 only.
        bus.register_simulated_reply(b"I1000000", b"I0154000")
        await bus.start()
        try:
            inst = _make_installation([
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:ad:01",
                    "channels": [
                        {"ch": 1, "name": "Mismatch", "active": True, "max_watt": 100},
                    ],
                },
            ])
            result = await sweep_dimmer_states(
                bus, registry, inst, inter_query_delay_s=0, reply_timeout_ms=50,
            )
            assert result == 0
            assert registry.get_dimmer_state(
                DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1),
            ) is None
        finally:
            await bus.stop()
