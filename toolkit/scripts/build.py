#!/usr/bin/env python3
"""Build the IPBuilding Gateway Tools downloads.

Used locally and from GitHub Actions. Stages a self-contained bundle, then
runs ``mcpb validate`` and ``mcpb pack``. Also writes the Claude Code zip
for developers. That zip never receives the intake address.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
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

# Shown after install, in the desktop extension list. No install steps:
# the reader already has the tool. Install steps stay on the release page
# and in HANDLEIDING.md.
LONG_DESCRIPTION = (
    "IPBuilding Gateway Tools zijn hulpmiddelen voor AI-assistenten zoals Claude. "
    "Ze helpen je samen met een assistent problemen in je IPBuilding-installatie te vinden. "
    "Wat jullie vinden, kun je als rapport naar Sonic Rocket sturen.\n"
    "\n"
    "Persoonsgegevens, zoals adressen en namen van lampen en ruimtes, "
    "worden standaard weggefilterd uit het rapport.\n"
    "\n"
    'Om mee te kijken zet je in de gateway "Bediening op afstand (voor debuggen)" aan. '
    "Als je klaar bent, zet je het weer uit."
)


def file_version() -> str:
    return (TOOLKIT / "VERSION").read_text(encoding="utf-8").strip()


def resolve_version() -> str:
    """VERSION is the source of truth. A toolkit tag must match it."""
    version = file_version()
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("gateway-tools-v"):
        tagged = tag.removeprefix("gateway-tools-v")
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
    # version.py reads this file from the bundle root. Without it the report
    # falls back to 0.0.0 even though manifest.json has the real version.
    shutil.copy2(TOOLKIT / "VERSION", dest / "VERSION")
    # Same square PNG the Home Assistant add-on uses (512x512).
    shutil.copy2(REPO / "ipbuilding_gateway" / "icon.png", dest / "icon.png")
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


_SEND_OFF = {"0", "false", "no", "off"}


def _report_send_enabled() -> bool:
    """Same default as the toolkit: on unless the build explicitly turns it off."""
    raw = os.environ.get("IPBUILDING_REPORT_SEND")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _SEND_OFF


def _intake_address() -> str:
    """Build-time intake address. Empty means the bundle does not embed one."""
    return os.environ.get("IPBUILDING_REPORT_INTAKE", "").strip()


def _write_manifest(dest: Path, version: str) -> None:
    env = {
        "IPBUILDING_GATEWAY_ADDRESS": "${user_config.gateway_address}",
    }
    intake = _intake_address()
    # Inject only while sending is on, so a build with the flag off does not
    # embed the address. A normal build has no address until CI supplies
    # the Actions secret IPBUILDING_REPORT_INTAKE.
    if _report_send_enabled() and intake:
        env["IPBUILDING_REPORT_INTAKE"] = intake
    tools = [
        {
            "name": "connection_status",
            "description": "Verbinding, adres, gezondheid en ontbrekende mogelijkheden.",
        },
        {
            "name": "gateway_health",
            "description": "Status, subsystemen, meldingen, looptijd en het activiteitenlog.",
        },
        {
            "name": "list_devices",
            "description": (
                "Live inventaris: module, kanaal, knop-id en naam. "
                "Controleer een id altijd opnieuw tegen deze lijst. Kanalen tellen vanaf 0."
            ),
        },
        {
            "name": "recent_events",
            "description": "Statuswijzigingen en knoppen uit het activiteitenlog.",
        },
        {
            "name": "read_logs",
            "description": "Logregels van de gateway, als deze versie dat kan.",
        },
        {
            "name": "discover",
            "description": "Scan starten nadat de tester het bevestigd heeft, daarna het verschil.",
        },
        {
            "name": "device_command",
            "description": "Eén apparaat schakelen of dimmen nadat de tester het bevestigd heeft.",
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
            "description": (
                "Rapport, bugrapport, foutmelding of feedback. Probleem melden, report, bug report. "
                "Namen en adressen gaan er standaard uit."
            ),
        },
    ]
    if _report_send_enabled():
        tools.append(
            {
                "name": "send_report",
                "description": (
                    "Rapport versturen, sturen of doorsturen naar Sonic Rocket, naar Mark, "
                    "naar de ontwikkelaars of de developers. De toolkit verstuurt niets zelf."
                ),
            }
        )
    manifest = {
        "manifest_version": "0.4",
        "name": "ipbuilding-gateway-tools",
        "display_name": "IPBuilding Gateway Tools",
        "version": version,
        # Legacy single-asset field. Clients use this when `icons` is omitted.
        "icon": "icon.png",
        "description": "Hulpmiddelen voor AI-assistenten zoals Claude.",
        "long_description": LONG_DESCRIPTION,
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
                "env": env,
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
                    "homeassistant.local volstaat meestal. "
                    "Lukt dat niet, vul het adres in waarmee je Home Assistant "
                    "in je browser opent, zonder http:// en zonder poort."
                ),
                # required defaults to false in the MCPB spec. A required string
                # shows `default` as a grey placeholder and Claude Desktop will
                # not enable Save until the field is edited.
                "required": False,
                "default": "homeassistant.local",
            }
        },
        "tools": tools,
        "keywords": ["ipbuilding", "home-assistant", "gateway"],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _folded_frontmatter(text: str) -> dict[str, str]:
    """Read the YAML block at the top of SKILL.md. Only name and description."""
    if not text.startswith("---\n"):
        raise SystemExit("SKILL.md must start with frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SystemExit("SKILL.md frontmatter is not closed")
    fields: dict[str, str] = {}
    folding: str | None = None
    folded: list[str] = []
    for line in text[4:end].splitlines():
        if folding is not None and (line.startswith(" ") or line.startswith("\t") or line.strip() == ""):
            folded.append(line.strip())
            continue
        if folding is not None:
            fields[folding] = re.sub(r"\s+", " ", " ".join(folded)).strip()
            folding = None
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        rest = rest.strip().strip('"').strip("'")
        if rest in {">", "|", ">-", "|-"}:
            folding = key
            folded = []
            continue
        fields[key] = rest
    if folding is not None:
        fields[folding] = re.sub(r"\s+", " ", " ".join(folded)).strip()
    return fields


def _validate_skill_frontmatter(skill_dir: Path) -> str:
    """Claude rejects a skill whose name or description breaks the upload rules."""
    skill = skill_dir / "SKILL.md"
    fields = _folded_frontmatter(skill.read_text(encoding="utf-8"))
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise SystemExit(f"skill name {name!r} is not a lowercase slug of at most 64 characters")
    if "claude" in name or "anthropic" in name:
        raise SystemExit(f"skill name {name!r} contains a reserved word")
    if name != skill_dir.name:
        raise SystemExit(f"skill name {name!r} does not match directory {skill_dir.name}")
    if not description or len(description) > 1024:
        raise SystemExit("skill description must be 1 to 1024 characters")
    if "<" in description or ">" in description:
        raise SystemExit("skill description must not contain XML tags")
    return name


def _plugin_files() -> list[Path]:
    skip = {".build", "dist", "__pycache__", ".pytest_cache"}
    return sorted(
        path
        for path in TOOLKIT.rglob("*")
        if path.is_file()
        and not skip.intersection(path.relative_to(TOOLKIT).parts)
        and path.suffix != ".pyc"
    )


def _write_zip(dest: Path, entries: list[tuple[Path, str]]) -> None:
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in entries:
            archive.write(path, arcname=arcname)


def write_download_zips(version: str, dest: Path = DIST) -> Path:
    """Write the Claude Code plugin zip for developers.

    The zip is the toolkit tree under ``ipbuilding-gateway-tools/``. It does
    not get ``IPBUILDING_REPORT_INTAKE``. Only the ``.mcpb`` manifest does, so
    sending a report is not available from this zip.
    """
    versions_agree()
    _validate_skill_frontmatter(TOOLKIT / "skills" / "ipbuilding-gateway-tools")
    dest.mkdir(parents=True, exist_ok=True)
    plugin_zip = dest / f"ipbuilding-gateway-tools-claude-code-{version}.zip"
    _write_zip(
        plugin_zip,
        [
            (path, f"ipbuilding-gateway-tools/{path.relative_to(TOOLKIT).as_posix()}")
            for path in _plugin_files()
        ],
    )
    return plugin_zip


def pack(staging: Path, version: str) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    output = DIST / f"ipbuilding-gateway-tools-{version}.mcpb"
    if output.exists():
        output.unlink()
    subprocess.run(["mcpb", "validate", str(staging / "manifest.json")], check=True)
    subprocess.run(["mcpb", "pack", str(staging), str(output)], check=True)
    if not output.is_file():
        raise SystemExit(f"mcpb pack did not write {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the IPBuilding Gateway Tools .mcpb")
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Write the staging directory and skip mcpb validate/pack",
    )
    args = parser.parse_args(argv)
    version = resolve_version()
    plugin_zip = write_download_zips(version)
    print(f"plugin {plugin_zip}")
    staged = stage(version)
    print(f"staged {staged} ({version})")
    if args.stage_only:
        return 0
    archive = pack(staged, version)
    print(f"packed {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
