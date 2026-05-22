"""Gateway configuration from environment or defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GatewayConfig:
    hub_ip: str = "10.10.1.1"
    hub_port: int = 1001
    rest_host: str = "0.0.0.0"
    rest_port: int = 30200
    bind_ip: str = "0.0.0.0"
    reply_timeout_ms: int = 500
    simulated_mode: bool = False
    field_modules: dict[str, str] = field(
        default_factory=lambda: {
            "relay": "10.10.1.30",
            "dimmer": "10.10.1.40",
            "input": "10.10.1.50",
        }
    )

    @classmethod
    def from_env(cls) -> GatewayConfig:
        modules = {
            "relay": os.getenv("GATEWAY_RELAY_IP", "10.10.1.30"),
            "dimmer": os.getenv("GATEWAY_DIMMER_IP", "10.10.1.40"),
            "input": os.getenv("GATEWAY_INPUT_IP", "10.10.1.50"),
        }
        return cls(
            hub_ip=os.getenv("GATEWAY_HUB_IP", "10.10.1.1"),
            hub_port=int(os.getenv("GATEWAY_HUB_PORT", "1001")),
            rest_host=os.getenv("GATEWAY_REST_HOST", "0.0.0.0"),
            rest_port=int(os.getenv("GATEWAY_REST_PORT", "30200")),
            bind_ip=os.getenv("GATEWAY_BIND_IP", "0.0.0.0"),
            reply_timeout_ms=int(os.getenv("GATEWAY_REPLY_TIMEOUT_MS", "500")),
            simulated_mode=os.getenv("GATEWAY_SIMULATED", "").lower() in ("1", "true", "yes"),
            field_modules=modules,
        )
