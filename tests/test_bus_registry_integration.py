"""Integration tests: UDPBus poll loop -> DeviceRegistry state tracking."""

import asyncio

import pytest

from gateway.config import GatewayConfig
from gateway.device_registry import (
    ButtonEvent,
    DeviceKey,
    DeviceRegistry,
    DeviceType,
)
from gateway.udp_bus import UDPBus


def _cfg() -> GatewayConfig:
    return GatewayConfig(simulated_mode=True, poll_interval_s=0.05)


def _wired_bus_registry(cfg: GatewayConfig) -> tuple[UDPBus, DeviceRegistry]:
    """Create a bus and registry wired together, matching main.py pattern."""
    bus = UDPBus(cfg)
    reg = DeviceRegistry()
    for module_type, module_ip in cfg.field_modules.items():
        reg.register_module(module_ip, DeviceType(module_type))
    bus.add_listener(reg.handle_packet)
    return bus, reg


@pytest.mark.asyncio
async def test_poll_reply_updates_relay_state():
    """Poll loop sends P0000 to relay; simulated reply updates registry."""
    cfg = _cfg()
    bus, reg = _wired_bus_registry(cfg)

    bus.register_simulated_reply(b"P0000", b"I00000100")

    changes: list[tuple] = []
    reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

    await bus.start()
    await asyncio.sleep(0.12)
    await bus.stop()

    key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
    state = reg.get_relay_state(key)
    assert state is not None
    assert state.state == "on"
    assert len(changes) >= 1
    assert changes[0][2].state == "on"


@pytest.mark.asyncio
async def test_poll_reply_updates_dimmer_state():
    """Poll loop sends I9900 to dimmer; simulated reply updates registry."""
    cfg = _cfg()
    bus, reg = _wired_bus_registry(cfg)

    bus.register_simulated_reply(b"I9900", b"I0154030")

    await bus.start()
    await asyncio.sleep(0.12)
    await bus.stop()

    key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0)
    state = reg.get_dimmer_state(key)
    assert state is not None
    assert state.level_percent == 30


@pytest.mark.asyncio
async def test_command_reply_updates_registry():
    """Explicit command to relay produces a reply that updates registry."""
    cfg = _cfg()
    bus, reg = _wired_bus_registry(cfg)

    bus.register_simulated_reply(b"S0000", b"I00000100")

    await bus.start()
    await bus.send_command("10.10.1.30", b"S0000")
    await asyncio.sleep(0.05)
    await bus.stop()

    key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
    assert reg.get_relay_state(key).state == "on"


@pytest.mark.asyncio
async def test_all_devices_populated_after_poll():
    """After a poll cycle, all_devices should return known devices."""
    cfg = _cfg()
    bus, reg = _wired_bus_registry(cfg)

    bus.register_simulated_reply(b"P0000", b"I00000100")
    bus.register_simulated_reply(b"I9900", b"I0154099")

    await bus.start()
    await asyncio.sleep(0.12)
    await bus.stop()

    devices = reg.all_devices()
    assert len(devices) >= 2
    types = {d["device_type"] for d in devices}
    assert "relay" in types
    assert "dimmer" in types
