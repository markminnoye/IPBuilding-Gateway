"""Shared types for the gateway package — no internal gateway imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceType(str, Enum):
    RELAY = "relay"
    DIMMER = "dimmer"
    INPUT = "input"


@dataclass(frozen=True)
class DeviceKey:
    """Unique identifier for a device channel on the bus."""

    device_type: DeviceType
    module_ip: str
    channel: int