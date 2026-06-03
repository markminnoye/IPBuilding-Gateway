"""Gateway entrypoint -- UDP bus + device registry + REST shim."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiohttp import web

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadataCache
from gateway.types import DeviceType
from gateway.rest_shim import RESTShim
from gateway.udp_bus import UDPBus
from gateway.gateway_api import GatewayAPI

log = logging.getLogger(__name__)


async def run_gateway(config: GatewayConfig | None = None) -> None:
    cfg = config or GatewayConfig.from_env()

    registry = DeviceRegistry()

    if cfg.installation:
        # Register each module from devices.json
        for mc in cfg.installation.modules:
            registry.register_module(mc.ip, mc.type)
    else:
        # Fall back to env-derived field_modules
        for module_type, module_ip in cfg.field_modules.items():
            try:
                dtype = DeviceType(module_type)
            except ValueError:
                log.warning("Unknown module type %r at %s — skipped", module_type, module_ip)
                continue
            registry.register_module(module_ip, dtype)

    registry.on_state_changed(
        lambda key, old, new: log.info("STATE  %s ch%d: %s → %s", key.module_ip, key.channel, old, new)
    )
    registry.on_button_event(
        lambda key, evt: log.info("EVENT  %s button %s: %s", key.module_ip, evt.id_hex, evt.action)
    )

    bus = UDPBus(cfg)
    bus.add_listener(registry.handle_packet)
    await bus.start()

    shim = RESTShim(bus, registry, cfg)
    runner = web.AppRunner(shim.app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.rest_host, cfg.rest_port)
    await site.start()

    # Build metadata cache and prefetch getSysSet/getButtons before starting API.
    meta_cache = ModuleMetadataCache()
    if cfg.installation:
        try:
            await meta_cache.refresh(cfg.installation, timeout=2.0)
        except Exception:
            log.warning("Module metadata prefetch failed; cache is empty at startup")

    api = GatewayAPI(bus, registry, cfg, metadata_cache=meta_cache)
    await api.start()

    install_info = ""
    if cfg.installation:
        module_summary = ", ".join(
            f"{mc.type.value}@{mc.ip}" for mc in cfg.installation.modules
        )
        install_info = f"  install={module_summary}"
    log.info(
        "IPBuilding Gateway started  rest=%s:%d  api=%s:%d  poll=%.1fs  simulated=%s%s",
        cfg.rest_host,
        cfg.rest_port,
        cfg.api_host,
        cfg.api_port,
        cfg.poll_interval_s,
        cfg.simulated_mode,
        install_info,
    )

    stop_event = asyncio.Event()

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    else:
        signal.signal(signal.SIGINT, lambda *_: stop_event.set)

    try:
        await stop_event.wait()
    finally:
        log.info("Shutting down…")
        await runner.cleanup()
        await api.stop()
        await bus.stop()
        log.info("Gateway stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()