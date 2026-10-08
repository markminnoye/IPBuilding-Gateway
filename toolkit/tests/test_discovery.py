"""mDNS address order. Loopback from an announcement is never dialed."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import pytest

from ipbuilding_debug.discovery import (
    MdnsSighting,
    is_loopback,
    plan_attempts,
)
from ipbuilding_debug.server import build_server
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import connection_status


def _loopback() -> str:
    return str(ipaddress.IPv4Address(0x7F000001))


def _lan() -> str:
    return ".".join(str(part) for part in (192, 0, 2, 10))


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_plan_skips_loopback_then_hostname_then_configured() -> None:
    loopback = _loopback()
    mapped = str(ipaddress.IPv6Address((0xFFFF << 32) | 0x7F000001))
    candidates, ignored = plan_attempts(
        MdnsSighting(
            hostname="ipbgw.local.",
            port=8080,
            addresses=(loopback, mapped, _lan()),
        ),
        "homeassistant.local",
        8080,
        "config_default",
    )
    assert is_loopback(loopback)
    assert is_loopback(str(ipaddress.IPv6Address(1)))
    assert is_loopback(mapped)
    assert not is_loopback("homeassistant.local")
    assert not is_loopback("ipbgw.local")
    assert ignored == [loopback, mapped]
    assert [(item.host, item.source) for item in candidates] == [
        (_lan(), "mdns"),
        ("ipbgw.local", "mdns_hostname"),
        ("homeassistant.local", "config_default"),
    ]


def test_plan_without_a_sighting_keeps_the_configured_address() -> None:
    candidates, ignored = plan_attempts(None, "homeassistant.local", 8080, "manual")
    assert ignored == []
    assert [(item.host, item.source) for item in candidates] == [
        ("homeassistant.local", "manual")
    ]


@pytest.mark.asyncio
async def test_resolve_prefers_a_non_loopback_mdns_address() -> None:
    loopback = _loopback()
    lan = _lan()

    async def browser() -> MdnsSighting:
        return MdnsSighting(
            hostname="ipbgw.local.",
            port=8080,
            addresses=(loopback, lan),
        )

    session = GatewaySession(
        "homeassistant.local",
        address_source="config_default",
        discover_mdns=True,
        mdns_browser=browser,
        mdns_timeout=0.2,
    )

    async def probe(candidate: object) -> bool:
        return getattr(candidate, "source", "") == "mdns"

    session._probe = probe  # type: ignore[method-assign]
    await session.resolve()
    assert session.host == lan
    assert session.address_source == "mdns"
    assert loopback in session.mdns_loopback
    assert all(item.get("host") != loopback or item.get("result") == "skipped_loopback" for item in session.tried)
    chosen = [item for item in session.tried if item.get("result") == "chosen"]
    assert chosen == [{"host": lan, "port": 8080, "source": "mdns", "result": "chosen"}]


@pytest.mark.asyncio
async def test_mdns_loopback_falls_through_to_the_configured_host() -> None:
    from fake_gateway import FakeGateway

    loopback = _loopback()
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    await gateway.start()

    async def browser() -> MdnsSighting:
        return MdnsSighting(hostname="ipbgw.local.", port=8080, addresses=(loopback,))

    session = GatewaySession(
        f"localhost:{gateway.port}",
        address_source="config_default",
        discover_mdns=True,
        mdns_browser=browser,
        mdns_timeout=0.2,
        backoff_start=0.05,
    )
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["connected"] is True
    assert result.data["address"] == "localhost"
    assert result.data["address_source"] == "config_default"
    assert loopback in result.data["mdns_loopback"]
    skipped = [item for item in result.data["tried"] if item.get("host") == loopback]
    assert skipped
    assert all(item.get("result") == "skipped_loopback" for item in skipped)
    assert "ipbgw.local" in {item.get("host") for item in result.data["tried"]}


@pytest.mark.asyncio
async def test_mdns_loopback_and_unreachable_explains_what_was_tried() -> None:
    loopback = _loopback()

    async def browser() -> MdnsSighting:
        return MdnsSighting(hostname="ipbgw.local.", port=8080, addresses=(loopback,))

    session = GatewaySession(
        f"localhost:{_closed_port()}",
        address_source="config_default",
        discover_mdns=True,
        mdns_browser=browser,
        mdns_timeout=0.2,
        backoff_start=30,
        backoff_max=30,
    )
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
    assert result.data["connected"] is False
    assert result.data["kind"] == "unreachable"
    assert "loopback" in result.message
    assert "overgeslagen" in result.message
    assert "ipbgw.local" in result.message
    assert "Configure" in result.message
    assert "homeassistant.local" in result.message
    assert loopback in result.message


@pytest.mark.asyncio
async def test_browse_failure_at_startup_still_lists_tools() -> None:
    async def browser() -> MdnsSighting:
        raise OSError("browse failed")

    session = GatewaySession(
        f"127.0.0.1:{_closed_port()}",
        discover_mdns=True,
        mdns_browser=browser,
        mdns_timeout=0.2,
        backoff_start=30,
        backoff_max=30,
    )
    server = build_server(session)
    try:
        async with server.settings.lifespan(server):
            names = [tool.name for tool in await server.list_tools()]
            assert "connection_status" in names
            assert "send_raw" in names
            assert "read_logs" in names
            result = await connection_status(session)
    finally:
        await session.stop()
    assert result.data["connected"] is False
    assert result.data["kind"] == "unreachable"


@pytest.mark.asyncio
async def test_lifespan_does_not_wait_on_a_hanging_browse() -> None:
    async def browser() -> MdnsSighting | None:
        await asyncio.Event().wait()
        return None

    session = GatewaySession(
        "homeassistant.local",
        discover_mdns=True,
        mdns_browser=browser,
        mdns_timeout=30,
    )
    server = build_server(session)
    try:
        async with asyncio.timeout(1):
            async with server.settings.lifespan(server):
                names = [tool.name for tool in await server.list_tools()]
    finally:
        await session.stop()
    assert "connection_status" in names
    assert "send_raw" in names
    assert "read_logs" in names
