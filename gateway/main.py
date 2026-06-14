"""Gateway entrypoint -- UDP bus + device registry + REST shim."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from aiohttp import web

from gateway.auto_discovery import DiscoveryOrchestrator
from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadataCache
from gateway.types import DeviceType
from gateway.rest_shim import RESTShim
from gateway.udp_bus import UDPBus
from gateway.gateway_api import GatewayAPI

from gateway import __version__

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

    shim_runner = None
    if cfg.rest_shim_enabled:
        shim = RESTShim(bus, registry, cfg)
        shim_runner = web.AppRunner(shim.app)
        await shim_runner.setup()
        site = web.TCPSite(shim_runner, cfg.rest_host, cfg.rest_port)
        await site.start()
        log.info("REST shim enabled on %s:%d", cfg.rest_host, cfg.rest_port)

    # Build metadata cache and prefetch getSysSet/getButtons before starting API.
    meta_cache = ModuleMetadataCache()
    if cfg.installation:
        try:
            await meta_cache.refresh(cfg.installation, timeout=2.0)
        except Exception:
            log.warning("Module metadata prefetch failed; cache is empty at startup")

    api = GatewayAPI(bus, registry, cfg, metadata_cache=meta_cache)

    # Start runtime auto-discovery orchestrator after API is ready
    orchestrator: DiscoveryOrchestrator | None = None
    if cfg.discovery:
        orchestrator = DiscoveryOrchestrator(
            config=cfg.discovery,
            devices_file=cfg.devices_file,
            broadcast=api._broadcast,
            installation=cfg.installation,
        )
        await orchestrator.start()

    api.set_orchestrator(orchestrator)
    await api.start()

    install_info = ""
    if cfg.installation:
        module_summary = ", ".join(
            f"{mc.type.value}@{mc.ip}" for mc in cfg.installation.modules
        )
        install_info = f"  install={module_summary}"
    log.info(
        "IPBuilding Gateway v%s  rest=%s:%d  shim_enabled=%s  api=%s:%d  poll=%.1fs  simulated=%s%s",
        __version__,
        cfg.rest_host,
        cfg.rest_port,
        cfg.rest_shim_enabled,
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
        if orchestrator:
            await orchestrator.stop()
        if shim_runner:
            await shim_runner.cleanup()
        await api.stop()
        await bus.stop()
        log.info("Gateway stopped")


def main() -> None:
    cfg = GatewayConfig.from_env()
    log_level_name = cfg.log_level.upper() if hasattr(cfg, 'log_level') else 'INFO'
    numeric_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run_gateway(cfg))


if __name__ == "__main__":
    main()