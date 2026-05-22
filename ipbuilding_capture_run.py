#!/usr/bin/env python3
"""Run reproducible IPBuilding protocol capture sessions.

This script orchestrates:
- packet capture (dumpcap preferred, tcpdump fallback),
- manifest logging (JSONL),
- REST actions against the IPBox API,
- optional HTTP snapshots (for example IP1100 getButtons),
- optional interactive physical-input markers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shlex
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import yaml


LOGGER = logging.getLogger("ipbuilding_capture_run")

# Default BPF when runbook omits capture.bpf_filter: all UDP involving IPBox / controllers /
# home REST IP (any port — avoids missing non-1001 replies); plus REST and embedded HTTP.
# Thuis-LAN is documented as 192.168.1.0/24 — replace 192.168.0.185 with your IPBox host on that
# subnet (or override via runbook capture.bpf_filter / --capture-filter).
DEFAULT_CAPTURE_BPF = (
    "udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 "
    "or host 192.168.0.185) or tcp port 30200 or "
    "(tcp port 80 and (host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50))"
)


@dataclass
class CaptureProcess:
    process: subprocess.Popen[str]
    command: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_logging(log_path: Path, verbose: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def load_runbook(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Runbook root must be a mapping.")
    return data


def render_placeholders(value: str, settings: dict[str, Any]) -> str:
    out = value
    for key, raw in settings.items():
        placeholder = "{" + key + "}"
        if placeholder in out:
            out = out.replace(placeholder, str(raw))
    return out


def make_session_dir(base_dir: Path, run_name: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    session_dir = base_dir / f"{timestamp}_{run_name}"
    session_dir.mkdir(parents=True, exist_ok=False)
    (session_dir / "exports").mkdir(parents=True, exist_ok=True)
    return session_dir


def save_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def choose_capture_command(interface: str, bpf_filter: str, output_pcap: Path) -> list[str]:
    if shutil.which("dumpcap"):
        return [
            "dumpcap",
            "-i",
            interface,
            "-w",
            str(output_pcap),
            "-f",
            bpf_filter,
        ]
    if shutil.which("tcpdump"):
        return [
            "tcpdump",
            "-i",
            interface,
            "-s",
            "0",
            "-U",
            "-n",
            "-w",
            str(output_pcap),
            bpf_filter,
        ]
    raise RuntimeError("Neither dumpcap nor tcpdump is available in PATH.")


def start_capture(interface: str, bpf_filter: str, output_pcap: Path) -> CaptureProcess:
    command = choose_capture_command(interface, bpf_filter, output_pcap)
    LOGGER.info("Starting capture: %s", " ".join(shlex.quote(part) for part in command))
    process = subprocess.Popen(  # noqa: S603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.0)
    if process.poll() is not None:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"Capture process exited early (code={process.returncode}): {stderr}")
    return CaptureProcess(process=process, command=command)


def stop_capture(capture: CaptureProcess) -> None:
    process = capture.process
    if process.poll() is not None:
        LOGGER.warning("Capture already stopped with exit code %s", process.returncode)
        return
    LOGGER.info("Stopping capture process (pid=%s)", process.pid)
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)
    stderr = process.stderr.read() if process.stderr else ""
    if stderr.strip():
        LOGGER.debug("Capture stderr:\n%s", stderr.strip())
    LOGGER.info("Capture stopped with exit code %s", process.returncode)


def append_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    payload.setdefault("t_utc", utc_now_iso())
    payload.setdefault("t_monotonic", time.monotonic())
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


async def http_get_json(session: aiohttp.ClientSession, url: str) -> Any:
    async with session.get(url) as response:
        body_text = await response.text()
        response.raise_for_status()
    try:
        return json.loads(body_text)
    except json.JSONDecodeError:
        return {"raw_text": body_text}


async def run_inventory_snapshot(
    session: aiohttp.ClientSession,
    settings: dict[str, Any],
    outputs: dict[str, Any],
    session_dir: Path,
    manifest_path: Path,
    step: dict[str, Any],
) -> None:
    ipbox_base_url = settings.get("ipbox_base_url")
    if not ipbox_base_url:
        raise ValueError("settings.ipbox_base_url is required for inventory_snapshot.")
    url = f"{ipbox_base_url.rstrip('/')}/comp/items"
    data = await http_get_json(session, url)
    out_name = outputs.get("save_inventory_pre_as", "inventory_pre.json")
    out_path = session_dir / out_name
    save_json(out_path, data)
    append_manifest(
        manifest_path,
        {
            "event": "inventory_snapshot",
            "step_id": step.get("step_id"),
            "url": url,
            "saved_to": str(out_path),
        },
    )
    LOGGER.info("Inventory snapshot saved: %s", out_path)


async def run_http_snapshot(
    session: aiohttp.ClientSession,
    settings: dict[str, Any],
    session_dir: Path,
    manifest_path: Path,
    step: dict[str, Any],
) -> None:
    raw_url = str(step["url"])
    url = render_placeholders(raw_url, settings)
    data = await http_get_json(session, url)
    save_as = step.get("save_as")
    if not save_as:
        raise ValueError("http_snapshot step requires save_as.")
    out_path = session_dir / str(save_as)
    save_json(out_path, data)
    append_manifest(
        manifest_path,
        {
            "event": "http_snapshot",
            "step_id": step.get("step_id"),
            "url": url,
            "saved_to": str(out_path),
        },
    )
    LOGGER.info("HTTP snapshot saved: %s", out_path)


async def run_rest_action(
    session: aiohttp.ClientSession,
    settings: dict[str, Any],
    manifest_path: Path,
    step: dict[str, Any],
) -> None:
    ipbox_base_url = settings.get("ipbox_base_url")
    if not ipbox_base_url:
        raise ValueError("settings.ipbox_base_url is required for rest_action.")

    action_id = int(step["id"])
    action_type = str(step["action_type"])
    value = int(step["value"])
    url = (
        f"{ipbox_base_url.rstrip('/')}/action/action?"
        f"id={action_id}&actionType={action_type}&value={value}"
    )
    async with session.get(url) as response:
        body_text = await response.text()
        response.raise_for_status()
    append_manifest(
        manifest_path,
        {
            "event": "rest_action",
            "step_id": step.get("step_id"),
            "description": step.get("description"),
            "url": url,
            "response_status": response.status,
            "response_preview": body_text[:500],
        },
    )
    LOGGER.info("REST action sent: %s", url)


async def run_physical_input(
    manifest_path: Path,
    step: dict[str, Any],
    non_interactive: bool,
) -> None:
    prompt = step.get("prompt") or (
        f"Voer fysieke actie uit: {step.get('label', step.get('step_id', 'unknown'))}. "
        "Druk daarna ENTER."
    )
    if non_interactive:
        LOGGER.info("NON-INTERACTIVE physical marker: %s", prompt)
    else:
        await asyncio.to_thread(input, prompt + " ")

    append_manifest(
        manifest_path,
        {
            "event": "physical_input",
            "step_id": step.get("step_id"),
            "description": step.get("description"),
            "label": step.get("label"),
            "expected_cable": step.get("expected_cable"),
            "note": step.get("note"),
        },
    )
    LOGGER.info("Physical input marker logged for step_id=%s", step.get("step_id"))


async def run_steps(
    runbook: dict[str, Any],
    session_dir: Path,
    manifest_path: Path,
    non_interactive: bool,
) -> None:
    settings = runbook.get("settings", {})
    outputs = runbook.get("outputs", {})
    steps = runbook.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("runbook.steps must be a list.")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"Step {index} is not a mapping.")
            step_type = step.get("type")
            step_id = step.get("step_id", f"step_{index}")
            description = step.get("description", "")
            LOGGER.info("Running step %s (%s): %s", index, step_type, step_id)
            if description:
                LOGGER.info("Step description: %s", description)

            append_manifest(
                manifest_path,
                {
                    "event": "step_start",
                    "step_id": step_id,
                    "step_type": step_type,
                    "description": description,
                },
            )

            if step_type == "inventory_snapshot":
                await run_inventory_snapshot(session, settings, outputs, session_dir, manifest_path, step)
            elif step_type == "http_snapshot":
                await run_http_snapshot(session, settings, session_dir, manifest_path, step)
            elif step_type == "rest_action":
                await run_rest_action(session, settings, manifest_path, step)
            elif step_type == "physical_input":
                await run_physical_input(manifest_path, step, non_interactive=non_interactive)
            else:
                raise ValueError(f"Unsupported step type: {step_type}")

            append_manifest(
                manifest_path,
                {
                    "event": "step_done",
                    "step_id": step_id,
                    "step_type": step_type,
                },
            )

            wait_after = float(step.get("wait_after_seconds", 0))
            if wait_after > 0:
                LOGGER.info("Waiting %.1f seconds after step %s", wait_after, step_id)
                await asyncio.sleep(wait_after)


def write_session_readme(path: Path, interface: str, bpf_filter: str, runbook_path: Path) -> None:
    text = "\n".join(
        [
            "IPBuilding capture session",
            f"generated_utc={utc_now_iso()}",
            f"capture_interface={interface}",
            f"capture_filter={bpf_filter}",
            f"runbook_source={runbook_path}",
            "files:",
            "- capture.pcapng",
            "- manifest.jsonl",
            "- inventory_pre.json (if runbook includes inventory_snapshot)",
            "- ip1100_getbuttons_pre/post.json (if runbook includes http_snapshot steps)",
            "- run.log",
            "",
            "note: keep pcap files outside git unless using LFS.",
        ]
    )
    save_text(path, text + "\n")


async def run(args: argparse.Namespace) -> int:
    runbook = load_runbook(Path(args.runbook))
    settings = runbook.get("settings", {})
    capture_settings = settings.get("capture", {})
    run_name = str(settings.get("run_name", "capture-run"))
    session_dir = make_session_dir(Path(args.output_root), run_name)

    runbook_copy = session_dir / "runbook.yaml"
    save_text(runbook_copy, Path(args.runbook).read_text(encoding="utf-8"))

    log_path = session_dir / "run.log"
    configure_logging(log_path=log_path, verbose=args.verbose)
    LOGGER.info("Session directory: %s", session_dir)

    interface = args.interface or capture_settings.get("interface")
    if not interface:
        raise ValueError("Capture interface is required (--interface or settings.capture.interface).")
    bpf_filter = args.capture_filter or capture_settings.get("bpf_filter", DEFAULT_CAPTURE_BPF)

    pcap_path = session_dir / "capture.pcapng"
    manifest_path = session_dir / "manifest.jsonl"
    manifest_path.touch()

    write_session_readme(
        path=session_dir / "README.txt",
        interface=str(interface),
        bpf_filter=str(bpf_filter),
        runbook_path=Path(args.runbook),
    )

    append_manifest(
        manifest_path,
        {
            "event": "session_start",
            "run_name": run_name,
            "session_dir": str(session_dir),
            "interface": interface,
            "capture_filter": bpf_filter,
        },
    )

    settle_before = float(capture_settings.get("settle_before_steps_seconds", 0))
    settle_after = float(capture_settings.get("settle_after_steps_seconds", 0))

    capture = start_capture(interface=str(interface), bpf_filter=str(bpf_filter), output_pcap=pcap_path)
    try:
        if settle_before > 0:
            LOGGER.info("Settling %.1f seconds before first step", settle_before)
            await asyncio.sleep(settle_before)
        await run_steps(runbook=runbook, session_dir=session_dir, manifest_path=manifest_path, non_interactive=args.non_interactive)
        if settle_after > 0:
            LOGGER.info("Settling %.1f seconds after last step", settle_after)
            await asyncio.sleep(settle_after)
    finally:
        stop_capture(capture)

    append_manifest(
        manifest_path,
        {
            "event": "session_done",
            "pcap": str(pcap_path),
            "run_log": str(log_path),
        },
    )
    LOGGER.info("Session complete. PCAP: %s", pcap_path)
    correlate_extra = settings.get("correlate_extra_args")
    extra_argv: list[str] = []
    if isinstance(correlate_extra, list):
        extra_argv = [str(x) for x in correlate_extra]
    maybe_correlate_session(session_dir, skip=args.no_correlate, extra_argv=extra_argv)
    return 0


def maybe_correlate_session(session_dir: Path, *, skip: bool, extra_argv: list[str] | None = None) -> None:
    """After capture, run scripts/correlate_capture_session.py if tshark is available."""
    if skip:
        return
    if not shutil.which("tshark"):
        LOGGER.warning("tshark not in PATH; skipping post-session UDP export.")
        return
    script = Path(__file__).resolve().parent / "scripts" / "correlate_capture_session.py"
    if not script.is_file():
        LOGGER.warning("Missing %s; skipping UDP export.", script)
        return
    argv_tail = list(extra_argv or [])
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(session_dir), *argv_tail],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        out_path = session_dir / "udp_ipbox_export.txt"
        if proc.stdout.strip():
            LOGGER.info("correlate_capture_session stdout:\n%s", proc.stdout.strip())
        if proc.returncode == 0 and out_path.is_file():
            LOGGER.info("UDP export written: %s", out_path)
        elif proc.stderr:
            LOGGER.warning("correlate_capture_session exit %s: %s", proc.returncode, proc.stderr.strip())
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Post-session correlation failed: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IPBuilding protocol capture orchestrator.")
    parser.add_argument(
        "--runbook",
        default="resources_and_docs/workflows/ipbuilding_golden_runbook.yaml",
        help="Path to YAML runbook.",
    )
    parser.add_argument(
        "--output-root",
        default="captures",
        help="Root directory where per-session folders are created.",
    )
    parser.add_argument(
        "--interface",
        default=None,
        help="Capture interface override (for example en7).",
    )
    parser.add_argument(
        "--capture-filter",
        default=None,
        help="BPF capture filter override (default: all UDP for IPBox/controller/home IPs, plus TCP 30200/80 to modules).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not block on input() for physical_input steps; only log markers.",
    )
    parser.add_argument(
        "--no-correlate",
        action="store_true",
        help="Skip automatic tshark UDP export (udp_ipbox_export.txt) after session.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()
    return args


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        LOGGER.error("Interrupted by user.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
