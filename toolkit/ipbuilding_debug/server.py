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
    export_session,
    probe_generation,
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
        "Staat Remote debugging and control uit, vraag dan om die schakelaar aan te zetten."
    )


def build_server(session: GatewaySession | None = None) -> MCPServer:
    gateway = session or GatewaySession.from_env()

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> Any:
        await gateway.ensure_started()
        try:
            yield gateway
        finally:
            await gateway.stop()

    mcp = MCPServer(
        "ipbuilding-gateway-tools",
        instructions=skill_text(),
        version=__version__,
        lifespan=lifespan,
    )

    @mcp.tool(name="connection_status")
    async def connection_status_tool(log_level: str | None = None) -> str:
        """Check whether the gateway answers, whether Remote debugging and control is on, and which capabilities this version has.

        Call this first in every debug session. When remote_debugging is false, tell the tester to turn the switch on. When a capability is missing, say that feature is not in this gateway version yet.
        log_level is optional (INFO or DEBUG) and is only sent when the gateway advertises log_stream.
        """
        result = await connection_status(gateway, log_level=log_level)
        return result.render()

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
    async def export_session_tool(note: str = "", marker: str = "") -> str:
        """Save a note or marker and export the session buffer for the report.

        The export can contain installation details. Do not publish it until names, room names, and addresses are removed.
        """
        result = await export_session(gateway, note=note, marker=marker)
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
