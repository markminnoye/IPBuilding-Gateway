"""Gateway entrypoint — UDP bus + REST API."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from gateway.config import GatewayConfig
from gateway.rest_api import RESTApp
from gateway.udp_bus import UDPBus

log = logging.getLogger(__name__)


async def run_gateway(config: GatewayConfig | None = None) -> None:
    cfg = config or GatewayConfig.from_env()
    bus = UDPBus(cfg)
    await bus.start()

    rest = RESTApp(bus, cfg)
    runner = web.AppRunner(rest.app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.rest_host, cfg.rest_port)
    await site.start()
    log.info(
        "IPBuilding field-bus dev server (experimental REST) %s:%s simulated=%s",
        cfg.rest_host,
        cfg.rest_port,
        cfg.simulated_mode,
    )

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bus.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()
