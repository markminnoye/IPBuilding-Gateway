"""stdio MCP server. Logging goes to stderr; stdout is the MCP stream."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import (
    capture_frames,
    connection_status,
    decode_test,
    device_command,
    discover,
    export_session,
    gateway_health,
    list_devices,
    probe_generation,
    read_logs,
    recent_events,
    send_raw,
)
from ipbuilding_debug.version import __version__

log = logging.getLogger("ipbuilding_debug")


def skill_text() -> str:
    path = Path(__file__).resolve().parents[1] / "skills" / "ipbuilding-gateway-tools" / "SKILL.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "Praat Nederlands met de tester. "
        "Roep eerst connection_status aan. "
        "Staat Remote control (for debugging) uit, vraag dan om die schakelaar aan te zetten."
    )


def build_server(session: GatewaySession | None = None) -> MCPServer:
    gateway = session or GatewaySession.from_env()

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> Any:
        # Tools are already registered. Do not wait on mDNS or the gateway here:
        # a discovery or connection error must not hide the tools.
        try:
            yield gateway
        finally:
            try:
                await gateway.stop()
            except Exception:
                log.exception("gateway stop failed")

    mcp = MCPServer(
        "ipbuilding-gateway-tools",
        instructions=skill_text(),
        version=__version__,
        lifespan=lifespan,
    )

    @mcp.tool(name="connection_status")
    async def connection_status_tool(log_level: str | None = None) -> str:
        """Check whether the gateway answers, whether Remote control (for debugging) is on, and which capabilities this version has.

        Call this first in every debug session. When remote_debugging is false, tell the tester to turn the switch on. When a capability is missing, say that feature is not in this gateway version yet.
        log_level is optional (INFO or DEBUG) and is only sent when the gateway advertises log_stream.
        """
        result = await connection_status(gateway, log_level=log_level)
        return result.render()

    @mcp.tool(name="gateway_health")
    async def gateway_health_tool() -> str:
        """Read /api/v1/status health: status, subsystems, issues, uptime, and the local buffer.

        Call this when the tester asks whether the gateway itself is healthy.
        """
        return (await gateway_health(gateway)).render()

    @mcp.tool(name="list_devices")
    async def list_devices_tool() -> str:
        """Map each channel to its module, type, name, and state from the gateway inventory.

        Relay and dimmer channels count from 0. Button channel is the module index, unchanged.
        Includes last_seen and last_seen_source when the gateway sent them on /modules.
        """
        return (await list_devices(gateway)).render()

    @mcp.tool(name="recent_events")
    async def recent_events_tool(limit: int = 50) -> str:
        """Read state changes and button events already in the buffer.

        Use this for questions about button presses and state changes. It does not need udp_frame and it does not read the add-on log.
        """
        return (await recent_events(gateway, limit=limit)).render()

    @mcp.tool(name="read_logs")
    async def read_logs_tool(
        seconds: float = 15,
        since: str = "",
        level: str = "info",
        limit: int = 50,
        redact: bool = True,
    ) -> str:
        """Read gateway log lines from the live log stream.

        Filters by time (since as an ISO timestamp, or the last seconds), minimum level, and limit.
        Names and addresses are removed unless redact is false. Needs capability log_stream. Without it, the tester should open the add-on Log tab.
        """
        result = await read_logs(
            gateway,
            seconds=seconds,
            since=since,
            level=level,
            limit=limit,
            redact=redact,
        )
        return result.render()

    @mcp.tool(name="discover")
    async def discover_tool(confirmed: bool = False) -> str:
        """Ask the gateway to scan for modules, then show the inventory diff.

        First call with confirmed=false and ask the tester. Only call again with confirmed=true after an explicit yes.
        """
        return (await discover(gateway, confirmed=confirmed)).render()

    @mcp.tool(name="device_command")
    async def device_command_tool(
        device_id: str,
        action: str,
        value: int | None = None,
        confirmed: bool = False,
    ) -> str:
        """Switch or dim one device through the gateway command the Home Assistant integration uses.

        action is ON, OFF, PULSE, TOGGLE, DIM, DIM_START, or DIM_STOP. DIM needs value 0-100.
        First call with confirmed=false. Only send after an explicit yes and confirmed=true.
        ok true means the gateway sent the command. module_confirmed and confirm_ms say whether the module replied. If those fields are absent, this gateway version does not report them.
        """
        return (
            await device_command(
                gateway,
                device_id=device_id,
                action=action,
                value=value,
                confirmed=confirmed,
            )
        ).render()

    @mcp.tool(name="probe_generation")
    async def probe_generation_tool() -> str:
        """List gateway version, hub role, and modules from the existing REST API.

        Does not open a field-bus socket. Dialect is only confirmed once udp_frame frames can be captured.
        """
        result = await probe_generation(gateway)
        return result.render()

    @mcp.tool(name="capture_frames")
    async def capture_frames_tool(
        seconds: float = 5,
        direction: str = "both",
        module: str = "",
        pattern: str = "",
        limit: int = 50,
    ) -> str:
        """Collect live field-bus frames from the gateway WebSocket.

        direction is tx, rx, or both. module and pattern are optional filters.
        Waits at most 30 seconds. If udp_frame is not in /status.capabilities, returns that this is not available in this gateway version yet.
        """
        result = await capture_frames(
            gateway,
            seconds=seconds,
            direction=direction,
            module=module,
            pattern=pattern,
            limit=limit,
        )
        return result.render()

    @mcp.tool(name="send_raw")
    async def send_raw_tool(
        target: str,
        payload_hex: str,
        port: int = 1001,
        window_ms: int = 2000,
        confirmed: bool = False,
    ) -> str:
        """Send one raw field-bus packet through the gateway, then collect replies.

        First call with confirmed=false. Show the tester the target, port, and hex, and ask for an explicit yes. Only then call again with confirmed=true. Never send without that yes. Needs capability raw_send.
        """
        result = await send_raw(
            gateway,
            target=target,
            payload_hex=payload_hex,
            port=port,
            window_ms=window_ms,
            confirmed=confirmed,
        )
        return result.render()

    @mcp.tool(name="decode_test")
    async def decode_test_tool(payload: str) -> str:
        """Decode one frame locally with the relay, dimmer, and input decoders.

        payload is hex or a short ASCII token such as S0000. No gateway connection.
        """
        return decode_test(payload).render()

    @mcp.tool(name="export_session")
    async def export_session_tool(
        note: str = "",
        marker: str = "",
        redact: bool = True,
    ) -> str:
        """Export the session buffer for the report. Addresses and names are removed by default.

        Pass redact=false only when the tester wants the raw text locally. Tell them not to share that raw text.
        """
        result = await export_session(gateway, note=note, marker=marker, redact=redact)
        return result.render()

    return mcp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
