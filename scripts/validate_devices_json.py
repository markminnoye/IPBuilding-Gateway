#!/usr/bin/env python3
"""Validate devices.json against discovery scratch-test criteria.

Exits 0 if validation passes; exits 1 with per-error lines on stderr on failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gateway.installation import InstallationConfig, InstallationError


def validate_devices_file(
    path: Path,
    *,
    expected_active_channels: int | None = None,
) -> list[str]:
    """Return a list of error strings; empty list means validation passed."""
    errors: list[str] = []
    try:
        cfg = InstallationConfig.load(path)
    except InstallationError as exc:
        return [str(exc)]

    seen_macs: list[str] = []
    for mod in cfg.modules:
        if mod.mac:
            seen_macs.append(mod.mac)
        else:
            errors.append(f"Module at {mod.ip} missing 'mac' field")

    if len(seen_macs) != len(set(seen_macs)):
        errors.append("Duplicate MAC addresses found across modules")

    active = sum(1 for mod in cfg.modules for ch in mod.channels if ch.active)

    if expected_active_channels is not None and active != expected_active_channels:
        errors.append(
            f"Expected {expected_active_channels} active channels, found {active}"
        )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate devices.json against discovery scratch-test criteria."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="devices.json",
        help="Path to devices.json (default: devices.json)",
    )
    parser.add_argument(
        "--expect-channels",
        type=int,
        default=None,
        help="Expected total count of active channels (e.g. 28 for the full install)",
    )
    args = parser.parse_args()

    errors = validate_devices_file(
        Path(args.path),
        expected_active_channels=args.expect_channels,
    )
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {args.path}")


if __name__ == "__main__":
    main()