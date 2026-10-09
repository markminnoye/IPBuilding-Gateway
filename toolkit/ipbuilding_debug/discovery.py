"""Find the gateway on the LAN without trusting a loopback announcement.

The add-on publishes ``_ipbgw._tcp.local.``. A publish address inside
127.0.0.0/8 or ``::1`` is the gateway host itself, not a path from this
computer. Those addresses are skipped. The mDNS hostname is tried next,
then the address configured in the bundle.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass

log = logging.getLogger("ipbuilding_debug.discovery")

SERVICE_TYPE = "_ipbgw._tcp.local."
MDNS_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class MdnsSighting:
    """One browse result. ``hostname`` may end with a dot."""

    hostname: str
    port: int
    addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    host: str
    port: int
    source: str


def is_loopback(value: str) -> bool:
    """True for 127.0.0.0/8, ``::1``, and an IPv4 loopback mapped into IPv6."""
    text = (value or "").strip().strip("[]")
    if not text:
        return False
    try:
        parsed = ipaddress.ip_address(text)
    except ValueError:
        return False
    if parsed.is_loopback:
        return True
    mapped = getattr(parsed, "ipv4_mapped", None)
    return bool(mapped is not None and mapped.is_loopback)


def _hostname(value: str) -> str:
    return (value or "").strip().rstrip(".")


def plan_attempts(
    sighting: MdnsSighting | None,
    configured_host: str,
    configured_port: int,
    configured_source: str,
) -> tuple[list[Candidate], list[str]]:
    """Candidates in try order, plus the loopback addresses that were skipped.

    Order: non-loopback mDNS addresses, the mDNS hostname, then the
    configured bundle address. Duplicates are removed.
    """
    ignored: list[str] = []
    ordered: list[Candidate] = []
    if sighting is not None:
        for raw in sighting.addresses:
            address = (raw or "").strip()
            if not address:
                continue
            if is_loopback(address):
                if address not in ignored:
                    ignored.append(address)
                continue
            ordered.append(Candidate(address, sighting.port or configured_port, "mdns"))
        host = _hostname(sighting.hostname)
        if host and not is_loopback(host):
            ordered.append(Candidate(host, sighting.port or configured_port, "mdns_hostname"))
    configured = (configured_host or "").strip()
    if configured:
        ordered.append(
            Candidate(configured, configured_port, configured_source or "manual")
        )
    seen: set[tuple[str, int]] = set()
    unique: list[Candidate] = []
    for item in ordered:
        key = (item.host, item.port)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique, ignored


def sighting_from_info(info: object) -> MdnsSighting | None:
    """Read hostname, port, and addresses from a zeroconf service info."""
    if info is None:
        return None
    parsed = getattr(info, "parsed_addresses", None)
    addresses: list[str] = []
    if callable(parsed):
        try:
            addresses = [str(item) for item in parsed() if item]
        except Exception:
            addresses = []
    server = getattr(info, "server", "") or ""
    if isinstance(server, bytes):
        server = server.decode("utf-8", "replace")
    port = getattr(info, "port", None)
    try:
        port_i = int(port) if port else 0
    except (TypeError, ValueError):
        port_i = 0
    if not server and not addresses:
        return None
    return MdnsSighting(hostname=str(server), port=port_i, addresses=tuple(addresses))


async def browse_ipbgw(timeout: float = MDNS_TIMEOUT_S) -> MdnsSighting | None:
    """Browse ``_ipbgw._tcp.local.``. Never raises. ``None`` means nothing found."""
    try:
        return await asyncio.wait_for(_browse_once(timeout), timeout + 1.0)
    except Exception:
        log.info("mDNS browse stopped", exc_info=True)
        return None


async def _browse_once(timeout: float) -> MdnsSighting | None:
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

    loop = asyncio.get_running_loop()
    found: list[str] = []
    ready = asyncio.Event()

    class _Listener:
        def add_service(self, _zc: object, _type: str, name: str) -> None:
            found.append(name)
            loop.call_soon_threadsafe(ready.set)

        def update_service(self, _zc: object, _type: str, name: str) -> None:
            if name not in found:
                found.append(name)
            loop.call_soon_threadsafe(ready.set)

        def remove_service(self, _zc: object, _type: str, _name: str) -> None:
            return None

    aiozc = AsyncZeroconf()
    browser = AsyncServiceBrowser(aiozc.zeroconf, SERVICE_TYPE, listener=_Listener())
    try:
        try:
            await asyncio.wait_for(ready.wait(), timeout)
        except asyncio.TimeoutError:
            return None
        await asyncio.sleep(0.2)
        infos: list[MdnsSighting] = []
        for name in list(found):
            try:
                info = await aiozc.async_get_service_info(SERVICE_TYPE, name, timeout=1000)
            except Exception:
                log.info("mDNS record %s could not be read", name, exc_info=True)
                continue
            sighting = sighting_from_info(info)
            if sighting is not None:
                infos.append(sighting)
        return _merge(infos)
    finally:
        try:
            await browser.async_cancel()
        except Exception:
            log.info("mDNS browser cancel failed", exc_info=True)
        try:
            await aiozc.async_close()
        except Exception:
            log.info("mDNS close failed", exc_info=True)


def _merge(items: list[MdnsSighting]) -> MdnsSighting | None:
    if not items:
        return None
    addresses: list[str] = []
    hostname = ""
    port = 0
    for item in items:
        for address in item.addresses:
            if address not in addresses:
                addresses.append(address)
        if item.hostname and not hostname:
            hostname = item.hostname
        if item.port and not port:
            port = item.port
    return MdnsSighting(hostname=hostname, port=port, addresses=tuple(addresses))
