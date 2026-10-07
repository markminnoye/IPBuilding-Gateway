#!/usr/bin/env python3
"""Build the IPBuilding debug toolkit .mcpb.

Used locally and from GitHub Actions. Stages a self-contained bundle, then
runs ``mcpb validate`` and ``mcpb pack``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
REPO = TOOLKIT.parent
STAGING = TOOLKIT / ".build" / "mcpb"
DIST = TOOLKIT / "dist"

PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
)

GATEWAY_FILES = (
    "gateway/__init__.py",
    "gateway/version.py",
    "gateway/models.py",
    "gateway/button_id.py",
)
GATEWAY_DIRS = ("gateway/payloads",)

COPY_NAMES = (
    "ipbuilding_debug",
    "skills",
    "HANDLEIDING.md",
    "README.md",
    ".mcpbignore",
)


def file_version() -> str:
    return (TOOLKIT / "VERSION").read_text(encoding="utf-8").strip()


def resolve_version() -> str:
    """VERSION is the source of truth. A toolkit tag must match it."""
    version = file_version()
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("toolkit-v"):
        tagged = tag.removeprefix("toolkit-v")
        if tagged != version:
            raise SystemExit(
                f"tag {tag} does not match toolkit/VERSION ({version}). "
                "Bump VERSION in the same commit as the tag."
            )
    return version


def versions_agree() -> None:
    version = file_version()
    plugin = json.loads((TOOLKIT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    pyproject = (TOOLKIT / "pyproject.toml").read_text(encoding="utf-8")
    if plugin.get("version") != version:
        raise SystemExit(f"plugin.json version {plugin.get('version')} != VERSION {version}")
    if f'version = "{version}"' not in pyproject:
        raise SystemExit(f"pyproject.toml version does not match VERSION {version}")


def _copy_tree(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    else:
        shutil.copy2(src, dest)


def scan_private_ips(path: Path) -> None:
    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    for file in files:
        if file.suffix in {".pyc"}:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        match = PRIVATE_IP.search(text)
        if match:
            raise SystemExit(f"private address {match.group(0)} in {file}")


def stage(version: str, dest: Path = STAGING) -> Path:
    versions_agree()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in COPY_NAMES:
        _copy_tree(TOOLKIT / name, dest / name)
    for rel in GATEWAY_FILES:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, target)
    for rel in GATEWAY_DIRS:
        _copy_tree(REPO / rel, dest / rel)
    _write_pyproject(dest, version)
    _write_manifest(dest, version)
    for relative in ("ipbuilding_debug", "skills", "README.md", "HANDLEIDING.md", "manifest.json"):
        scan_private_ips(dest / relative)
    return dest


def _write_pyproject(dest: Path, version: str) -> None:
    text = (TOOLKIT / "pyproject.toml").read_text(encoding="utf-8")
    lines = []
    replaced = False
    for line in text.splitlines(True):
        if not replaced and line.startswith("version = "):
            lines.append(f'version = "{version}"\n')
            replaced = True
        else:
            lines.append(line)
    (dest / "pyproject.toml").write_text("".join(lines), encoding="utf-8")


def _write_manifest(dest: Path, version: str) -> None:
    manifest = {
        "manifest_version": "0.4",
        "name": "ipbuilding-debug-toolkit",
        "display_name": "IPBuilding debug",
        "version": version,
        "description": "Meekijken en testen via de IPBuilding Gateway in je thuisnetwerk.",
        "long_description": (TOOLKIT / "HANDLEIDING.md").read_text(encoding="utf-8"),
        "author": {"name": "Sonic Rocket"},
        "license": "MIT",
        "repository": {
            "type": "git",
            "url": "https://github.com/markminnoye/IPBuilding-Gateway",
        },
        "server": {
            "type": "uv",
            "entry_point": "ipbuilding_debug/__main__.py",
            "mcp_config": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    "${__dirname}",
                    "python",
                    "-m",
                    "ipbuilding_debug",
                ],
                "env": {
                    "IPBUILDING_GATEWAY_ADDRESS": "${user_config.gateway_address}",
                },
            },
        },
        "compatibility": {
            "claude_desktop": ">=1.0.0",
            "platforms": ["darwin", "win32", "linux"],
            "runtimes": {"python": ">=3.11"},
        },
        "user_config": {
            "gateway_address": {
                "type": "string",
                "title": "Gateway-adres",
                "description": (
                    "Adres van de IPBuilding Gateway, zonder http:// en zonder poort. "
                    "Meestal homeassistant.local."
                ),
                "required": True,
                "default": "homeassistant.local",
            }
        },
        "tools": [
            {
                "name": "connection_status",
                "description": "Verbinding, schakelaar en mogelijkheden van deze gateway-versie.",
            },
            {
                "name": "probe_generation",
                "description": "Modules en versie van deze installatie.",
            },
            {
                "name": "capture_frames",
                "description": "Veldbusframes meelezen, als deze versie dat kan.",
            },
            {
                "name": "send_raw",
                "description": "Een testpakket sturen nadat de tester het bevestigd heeft.",
            },
            {
                "name": "decode_test",
                "description": "Een frame lokaal door de decoders halen.",
            },
            {
                "name": "export_session",
                "description": "Notities en de sessie bundelen.",
            },
        ],
        "keywords": ["ipbuilding", "home-assistant", "debug"],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def pack(staging: Path, version: str) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    output = DIST / f"ipbuilding-debug-toolkit-{version}.mcpb"
    if output.exists():
        output.unlink()
    subprocess.run(["mcpb", "validate", str(staging / "manifest.json")], check=True)
    subprocess.run(["mcpb", "pack", str(staging), str(output)], check=True)
    if not output.is_file():
        raise SystemExit(f"mcpb pack did not write {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the debug toolkit .mcpb")
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Write the staging directory and skip mcpb validate/pack",
    )
    args = parser.parse_args(argv)
    version = resolve_version()
    staged = stage(version)
    print(f"staged {staged} ({version})")
    if args.stage_only:
        return 0
    archive = pack(staged, version)
    print(f"packed {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
