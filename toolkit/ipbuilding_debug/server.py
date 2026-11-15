"""stdio MCP server. Logging goes to stderr; stdout is the MCP stream."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from ipbuilding_debug.report import report_send_enabled
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import (
    calibrate_dimmer,
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
    send_report,
)
from ipbuilding_debug.version import __version__

log = logging.getLogger("ipbuilding_debug")


def _strip_skill_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[end + 5 :].lstrip("\n")
    return text


def skill_text() -> str:
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    primary = skills_dir / "ipbuilding-gateway-tools" / "SKILL.md"
    if primary.is_file():
        parts = [primary.read_text(encoding="utf-8")]
        for extra in sorted(skills_dir.glob("*/SKILL.md")):
            if extra.parent.name == "ipbuilding-gateway-tools":
                continue
            body = _strip_skill_frontmatter(extra.read_text(encoding="utf-8")).strip()
            if body:
                parts.append(body)
        return "\n\n".join(parts)
    return (
        "Praat Nederlands met de tester. "
        "Roep eerst connection_status aan. "
        "Staat Remote control (for debugging) uit "
        "(Nederlands: Bediening op afstand (voor debuggen)), "
        "vraag dan om die schakelaar aan te zetten."
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

        In Dutch the switch is Bediening op afstand (voor debuggen). Call this first in every debug session. When remote_debugging is false, tell the tester to turn that switch on, using that exact name. When a capability is missing, say that feature is not in this gateway version yet.
        log_level is optional (INFO or DEBUG) and is only sent when the gateway advertises log_stream.
        """
        result = await connection_status(gateway, log_level=log_level)
        return result.render()

    @mcp.tool(name="gateway_health")
    async def gateway_health_tool() -> str:
        """Read /api/v1/status health: status, subsystems, issues, uptime, and the activiteitenlog.

        Call this when the tester asks whether the gateway itself is healthy.
        """
        return (await gateway_health(gateway)).render()

    @mcp.tool(name="list_devices")
    async def list_devices_tool() -> str:
        """Map each channel to its module, type, name, and state from the live gateway inventory.

        This list (module, channel, button id, name) is the only reliable link between a button or lamp and a physical position. Check an id against this live result, never against an earlier answer or a remembered id. A Home Assistant entity is secondary.
        Relay and dimmer channels count from 0. Button channel is the module index, unchanged.
        Includes last_seen and last_seen_source when the gateway sent them on /modules.
        """
        return (await list_devices(gateway)).render()

    @mcp.tool(name="recent_events")
    async def recent_events_tool(limit: int = 50) -> str:
        """Read state changes and button events already in the activiteitenlog.

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
        fade: int | None = None,
        confirmed: bool = False,
        verify: bool = True,
    ) -> str:
        """These are tools for AI assistants such as Claude. Switch or dim one device.

        A relay takes ON, OFF, PULSE, or TOGGLE. A dimmer takes DIM 0-100, TOGGLE, DIM_START, or DIM_STOP. For a dimmer, ON is sent as DIM 100 and OFF as DIM 0. PULSE is refused for a dimmer. The type comes from list_devices.
        fade is optional, 0-255, for DIM, ON, and OFF. Omit it or use 0 for an instant change. A higher value ramps. A non-integer or a value outside 0-255 is rejected. The module reports the end level before the lamp finishes.
        On a command test, call capture_frames while switching when udp_frame is available, before confirmed=true. Ask what the tester sees at that moment.
        First call with confirmed=false. Only send after an explicit yes and confirmed=true.
        ok true means the gateway sent the command. module_confirmed and confirm_ms say whether the module replied. If those fields are absent, this gateway version does not report them.
        A module reply can be only an echo of the command (Torhout dimmers). An echo proves receipt, not that the lamp moved. verify (default true) therefore reads the live level back from a dimmer after DIM, TOGGLE, and DIM_STOP with the status query I{ch}000000 when raw_send is active. That read changes nothing. readback.level_percent is what the module reports now; matches_request false means the command was probably not carried out. Always still ask the tester what the lamp does.
        """
        return (
            await device_command(
                gateway,
                device_id=device_id,
                action=action,
                value=value,
                fade=fade,
                confirmed=confirmed,
                verify=verify,
            )
        ).render()

    @mcp.tool(name="calibrate_dimmer")
    async def calibrate_dimmer_tool(
        mode: str = "status",
        device_id: str = "",
        module_ip: str = "",
        channel: int | None = None,
        steps: str = "",
        hold_seconds: float = 2.5,
        countdown_seconds: float = 0.0,
        sync_on_seconds: float = 2.0,
        sync_off_seconds: float = 3.0,
        video_path: str = "",
        sweep_log_path: str = "",
        margin_min: int = 1,
        sat_threshold: float = 0.985,
        dim_min: int | None = None,
        dim_max: int | None = None,
        dim_gamma: float | None = None,
        default_fade: int | None = None,
        keep_raw: bool = False,
        confirmed: bool = False,
    ) -> str:
        """Calibrate an IP0300PoE dimmer channel: status, sweep, analyze, or apply.

        Use mode='status' to inspect channels (0..7, cabinet output octet.block.pin,
        module dimMin/dimMax when directly reachable, gateway dim_gamma and default_fade).
        Use mode='sweep' first with confirmed=false to preview timing and camera instructions
        (dark room, SDR 1080p, AE/AF Lock on an indirect surface). Call again with
        confirmed=true only after the tester confirms recording has started. A sweep temporarily
        sets dim_gamma=1.0 (and dimMin=0..100 when module HTTP is reachable), runs an ON/OFF
        sync pulse and percentage steps, writes a sweep log file, and restores prior values.
        Use mode='analyze' with video_path (and sweep_log_path if available) to extract 10 Hz
        luma via ffprobe and compute recommended dimMin, dimMax, and dim_gamma.
        Use mode='apply' first with confirmed=false to preview proposed module dimMin/dimMax
        and gateway dim_gamma/default_fade changes; apply only after explicit tester yes
        with confirmed=true.
        """
        result = await calibrate_dimmer(
            gateway,
            mode=mode,
            device_id=device_id,
            module_ip=module_ip,
            channel=channel,
            steps=steps,
            hold_seconds=hold_seconds,
            countdown_seconds=countdown_seconds,
            sync_on_seconds=sync_on_seconds,
            sync_off_seconds=sync_off_seconds,
            video_path=video_path,
            sweep_log_path=sweep_log_path,
            margin_min=margin_min,
            sat_threshold=sat_threshold,
            dim_min=dim_min,
            dim_max=dim_max,
            dim_gamma=dim_gamma,
            default_fade=default_fade,
            keep_raw=keep_raw,
            confirmed=confirmed,
        )
        return result.render()

    @mcp.prompt(
        name="dimmer-kalibratie",
        title="Dimmer kalibreren",
        description=(
            "Kalibreer een IP0300PoE dimmerkanaal stap voor stap "
            "(status, sweep met video, ffprobe-analyse en opslaan)."
        ),
    )
    def dimmer_kalibratie_prompt(kanaal: str = "") -> str:
        """Start de interactieve dimmerkalibratie voor een dimmerkanaal of ruimte."""
        target = (
            f" voor kanaal of ruimte '{kanaal.strip()}'"
            if kanaal and kanaal.strip()
            else ""
        )
        return (
            f"Start de dimmerkalibratie{target}. "
            "Roep eerst calibrate_dimmer(mode='status') aan om de huidige kanalen, "
            "uitgangen (<octet>.<blok>.<pin>), dimMin, dimMax, dim_gamma en default_fade te tonen. "
            "Begeleid mij daarna stap voor stap volgens de skill dimmer-kalibratie:\n"
            "1. Kamer verduisteren en smartphone-camera richten op een indirect verlicht vlak met AE/AF Lock aan.\n"
            "2. Sweep-voorstel tonen met calibrate_dimmer(mode='sweep', confirmed=false) en pas na mijn ja uitvoeren met confirmed=true.\n"
            "3. De opgenomen video analyseren met calibrate_dimmer(mode='analyze', video_path=...) en de volledige tabel met alle 16 stappen (Luma Yavg en dY) tonen.\n"
            "4. De aanbevolen dimMin, dimMax, dim_gamma en default_fade voorleggen met calibrate_dimmer(mode='apply', confirmed=false) en pas na mijn bevestiging opslaan met confirmed=true."
        )

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
        include_polls: bool = False,
    ) -> str:
        """Collect live field-bus frames from the gateway WebSocket.

        Preferred use, record until done: call with seconds=0 to start listening, then tell the tester to press or switch, wait for the tester to say done (klaar), then call again with seconds=0. The second call returns everything in between, without a time window that can miss the press. You cannot speak while a call with seconds>0 is waiting.
        direction is tx, rx, or both. module and pattern are optional filters (pattern is a plain substring, not a regex).
        Routine polls and keepalives are left out and counted unless include_polls is true.
        Waits at most 30 seconds. If udp_frame is not in /status.capabilities, returns that this is not available in this gateway version yet.
        """
        result = await capture_frames(
            gateway,
            seconds=seconds,
            direction=direction,
            module=module,
            pattern=pattern,
            limit=limit,
            include_polls=include_polls,
        )
        return result.render()

    @mcp.tool(name="send_raw")
    async def send_raw_tool(
        module_ip: str,
        payload_hex: str,
        port: int = 1001,
        window_ms: int = 2000,
        confirmed: bool = False,
    ) -> str:
        """Send one raw field-bus packet through the gateway, then collect replies.

        POST /api/v1/debug/raw-send. Every sent packet and its replies go into the report under Wat getest werd. module_ip is the module IPv4 address. port is optional and must be 1001. payload_hex is 1 to 64 bytes. window_ms is optional, 1 to 3000, default 2000. An empty replies list is success. First call with confirmed=false. Show the tester the module, port, and hex, and ask for an explicit yes. Only then call again with confirmed=true. Never send without that yes. Needs capability raw_send. If that capability is absent, this gateway version does not support it.
        """
        result = await send_raw(
            gateway,
            module_ip=module_ip,
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
        return (await decode_test(payload, gateway)).render()

    @mcp.tool(name="export_session")
    async def export_session_tool(
        note: str = "",
        marker: str = "",
        redact: bool = True,
        feedback: str = "",
        include_events: bool | None = None,
        vermoeden: str = "",
        open_vraag: str = "",
        save_file: bool = True,
    ) -> str:
        """Export a report: rapport, bugrapport, foutmelding, feedback, probleem melden, bug report.

        Use this when someone asks for a report, a bug report, feedback, or to report a problem, in Dutch or English.
        note is the problem description and stays in the summary. feedback is free text about the tool, the skill, tables, or terminology. The latest feedback is kept and shown under heading 6.
        vermoeden is the core suspicion and is shown under Bevindingen. open_vraag is a question for the developers and is shown under Open vragen. Omit either one to keep the last text.
        include_events defaults to true. Pass false to leave events, frames, and logs out of the report. Omit it to keep the last choice.
        save_file (default true) also writes the filtered report as a Markdown file, by default in Downloads, and returns file_path. Give the tester that path and ask them to attach that file unchanged. Never write your own summary report in its place. A raw report (redact=false) is never written to disk.
        Addresses and names are removed by default. Device model codes such as IP0300PoE stay. Pass redact=false only when the tester wants the raw text locally. Tell them not to share that raw text.
        """
        result = await export_session(
            gateway,
            note=note,
            marker=marker,
            redact=redact,
            feedback=feedback,
            include_events=include_events,
            vermoeden=vermoeden,
            open_vraag=open_vraag,
            save_file=save_file,
        )
        return result.render()

    if report_send_enabled():

        @mcp.tool(name="send_report")
        async def send_report_tool(
            confirmed: bool = False,
            korte_fout: str = "",
            feedback: str = "",
            include_events: bool | None = None,
            vermoeden: str = "",
            open_vraag: str = "",
        ) -> str:
            """Send the report: versturen, sturen, doorsturen naar Sonic Rocket, naar Mark, naar de ontwikkelaars, to the developers.

            Use this to send or forward a rapport, bugrapport, foutmelding, or feedback to Sonic Rocket, to Mark, or to the developers.
            feedback, include_events, vermoeden, and open_vraag are optional. Omit them to reuse the last export_session values.
            The first call shows the privacy notice and the report. Nothing is sent. Before asking for yes, say that the tester sends the report and this tool does not.
            Call again with confirmed=true only after an explicit yes. The result shows the report as copyable text, the destination address, and the masked subject. A mailto link is only an extra and may not be clickable. The tester sends the mail.
            Without an intake address the option is unavailable.
            """
            result = await send_report(
                gateway,
                confirmed=confirmed,
                korte_fout=korte_fout,
                feedback=feedback,
                include_events=include_events,
                vermoeden=vermoeden,
                open_vraag=open_vraag,
            )
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
