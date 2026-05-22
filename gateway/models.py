"""Pydantic models for gateway commands and status."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RelayAction(str, Enum):
    ON = "on"
    OFF = "off"
    PULSE = "pulse"
    TOGGLE = "toggle"


class RelayCommand(BaseModel):
    channel: int = Field(ge=0, le=23)
    action: RelayAction


class DimmerCommand(BaseModel):
    channel: int = Field(ge=0, le=7)
    level: int = Field(ge=0, le=100, description="REST DIM percent 0-100")


class RelayStatus(BaseModel):
    channel: int
    state: Literal["on", "off", "unknown"]
    state_code: str
    module: str | None = None


class DimmerStatus(BaseModel):
    channel: int | None = None
    level_percent: int | None = None
    internal_value_code: str
    device_type: str = "01"
    family_constant: str = "54"


class InputEvent(BaseModel):
    module_id: str | None = None
    channel: int | None = None
    event_type: str = "unknown"
    status_bytes_hex: str | None = None


class DeviceAddress(BaseModel):
    ip: str
    port: int = 1001
