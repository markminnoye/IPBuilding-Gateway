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
from gateway.ha_discovery import HaDiscoveryAdvertiser, HaDiscoveryConfig
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadataCache
from gateway.state_poll import sweep_relay_states
from gateway.types import DeviceType
from gateway.rest_shim import RESTShim
from gateway.udp_bus import UDPBus
from gateway.gateway_api import GatewayAPI
from gateway.health import GatewayHealthMonitor

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
        # Optional env/lab poll targets (see use_env_defaults / simulated_mode).
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
    health = GatewayHealthMonitor()
    health.set_installation_loaded(cfg.installation is not None)
    if cfg.installation_load_error:
        health.report_issue(
            "installation.load_failed",
            "installation.load_failed",
            "error",
            cfg.installation_load_error,
            {"devices_file": cfg.devices_file},
        )
    meta_cache = ModuleMetadataCache(health=health)
    if cfg.installation:
        try:
            await meta_cache.refresh(
                cfg.installation, timeout=cfg.metadata_timeout_s,
            )
        except Exception:
            log.warning("Module metadata prefetch failed; cache is empty at startup")
        # Seed relay channel state via UDP I<CH>00 status sweep so the first
        # REST/WS snapshot reflects physical relay outputs. Dimmers stay
        # unknown until the first command or spontaneous UDP reply (no on-demand
        # dimmer status poll per RE 2026-06-12).
        try:
            await sweep_relay_states(
                bus,
                registry,
                cfg.installation,
                reply_timeout_ms=cfg.reply_timeout_ms,
            )
        except Exception:
            log.warning(
                "Relay status poll failed; relay channel state may be stale at startup"
            )

    api = GatewayAPI(bus, registry, cfg, metadata_cache=meta_cache, health=health)

    async def _safe_relay_sweep(target_inst: InstallationConfig) -> None:
        try:
            count = await sweep_relay_states(
                bus,
                registry,
                target_inst,
                reply_timeout_ms=cfg.reply_timeout_ms,
            )
            if count:
                await api._broadcast(api._build_snapshot())
        except Exception:
            log.warning(
                "Relay status poll (post-discovery) failed; relay state may be stale"
            )

    async def _safe_meta_refresh(target_inst: InstallationConfig) -> None:
        try:
            await meta_cache.refresh(
                target_inst, timeout=cfg.metadata_timeout_s,
            )
            # Push refreshed device list to WS clients so newly discovered
            # input buttons (getButtons) appear in the companion immediately.
            await api._broadcast(api._build_snapshot())
        except Exception:
            log.warning("Module metadata refresh (post-discovery) failed; cache may be stale")

    def _apply_installation(new_inst: InstallationConfig) -> None:
        """Sync callback invoked by DiscoveryOrchestrator after init-sweep /
        forced discovery. Updates cfg.installation, registers new modules in
        the DeviceRegistry, schedules a metadata refresh and clears the
        'no installation' health flag so the API serves devices immediately.
        """
        cfg.installation = new_inst
        for mc in new_inst.modules:
            registry.register_module(mc.ip, mc.type)
        asyncio.create_task(_safe_relay_sweep(new_inst))
        if meta_cache is not None:
            asyncio.create_task(_safe_meta_refresh(new_inst))
        health.set_installation_loaded(True)
        log.info(
            "run_gateway: applied new installation from discovery (%d modules)",
            len(new_inst.modules),
        )

    # Start runtime auto-discovery orchestrator after API is ready
    orchestrator: DiscoveryOrchestrator | None = None
    if cfg.discovery:
        orchestrator = DiscoveryOrchestrator(
            config=cfg.discovery,
            devices_file=cfg.devices_file,
            broadcast=api._broadcast,
            installation=cfg.installation,
            health=health,
            on_installation_changed=_apply_installation,
        )
        await orchestrator.start()

    api.set_orchestrator(orchestrator)
    await api.start()

    ha_discovery = HaDiscoveryAdvertiser(
        HaDiscoveryConfig.from_gateway_config(cfg),
    )
    await ha_discovery.start()
    if ha_discovery.instance_id:
        health.set_instance_id(ha_discovery.instance_id)

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
        await ha_discovery.stop()
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