"""Field-bus state poll — seed device registry on startup.

Relay modules expose live channel state via on-demand UDP status reads
``I<CH>00`` → ``I000<CH><state>`` (IPBox cold-boot sweep, RE 2026-06-12).
Dimmer modules have no working on-demand status poll; they stay unknown
until the first command or spontaneous UDP reply.

Called once at gateway startup (and after discovery populates devices.json)
so the first REST/WS snapshot reflects real relay channel state.  No
callbacks are fired: state-changed subscribers are wired in later when the
gateway API is created.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.payloads.relay import decode_relay_payload, encode_relay_status_poll
from gateway.types import DeviceKey, DeviceType
from gateway.udp_bus import UDPBus

log = logging.getLogger(__name__)


def _relay_status_predicate(
    expected_channel: int,
) -> Callable[[bytes], bool]:
    """Return a predicate matching relay_status for one channel."""

    def _match(data: bytes) -> bool:
        parsed = decode_relay_payload(data)
        if not parsed or parsed.get("family") != "relay_status":
            return False
        return parsed.get("channel") == expected_channel

    return _match


async def sweep_relay_states(
    bus: UDPBus,
    registry: DeviceRegistry,
    installation: InstallationConfig,
    *,
    inter_query_delay_s: float = 0.09,
    reply_timeout_ms: int | None = None,
) -> int:
    """Poll relay channel state over UDP and seed the registry.

    Sends ``I<CH>00`` for each **active** relay channel in
    ``devices.json``.  Inactive slots are skipped.  Failures are logged at WARNING and treated as zero
    for that channel — a stale empty registry is preferable to a startup
    crash.

    Returns the total number of channels seeded.
    """
    updated = 0
    relay_modules = [
        mc for mc in installation.modules if mc.type == DeviceType.RELAY
    ]
    if not relay_modules:
        return 0

    for mc in relay_modules:
        for ch in mc.channels:
            if not ch.active:
                continue
            channel = ch.ch
            payload = encode_relay_status_poll(channel)
            after_ts = time.monotonic()
            try:
                await bus.send_command(mc.ip, payload)
                pkt = await bus.correlate_reply(
                    module_ip=mc.ip,
                    after_ts=after_ts,
                    timeout_ms=reply_timeout_ms,
                    predicate=_relay_status_predicate(channel),
                )
            except Exception:
                log.warning(
                    "Relay status poll %s ch%d failed",
                    mc.ip,
                    channel,
                    exc_info=True,
                )
                if inter_query_delay_s > 0:
                    await asyncio.sleep(inter_query_delay_s)
                continue

            if pkt is None:
                log.warning(
                    "Relay status poll %s ch%d: no reply within timeout",
                    mc.ip,
                    channel,
                )
                if inter_query_delay_s > 0:
                    await asyncio.sleep(inter_query_delay_s)
                continue

            parsed = decode_relay_payload(pkt.data)
            if not parsed or parsed.get("family") != "relay_status":
                log.warning(
                    "Relay status poll %s ch%d: unexpected reply %r",
                    mc.ip,
                    channel,
                    pkt.data,
                )
                if inter_query_delay_s > 0:
                    await asyncio.sleep(inter_query_delay_s)
                continue

            key = DeviceKey(DeviceType.RELAY, mc.ip, channel)
            registry.seed_relay_state(
                key,
                parsed["state"],
                parsed.get("state_code", ""),
            )
            updated += 1
            log.info(
                "Relay status poll %s ch%d: seeded %s",
                mc.ip,
                channel,
                parsed["state"],
            )

            if inter_query_delay_s > 0:
                await asyncio.sleep(inter_query_delay_s)

    if updated:
        log.info("Registry seeded from relay status poll (%d channel updates)", updated)
    return updated
