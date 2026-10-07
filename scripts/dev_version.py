#!/usr/bin/env python3
"""Dev-channel add-on version for the develop branch.

Home Assistant pulls ``image:<version>`` using the ``version`` field in
``ipbuilding_gateway/config.yaml``. Each push to develop needs a new,
strictly newer version so Supervisor offers an update, and that tag must
never be a plain release or ``latest``.

A release version such as ``1.7.0`` becomes ``1.8.0-dev.<run>``.
An existing ``X.Y.Z-dev.N`` keeps ``X.Y.Z`` and adopts the workflow run
number when that number is higher.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_RELEASE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_DEV_RE = re.compile(r"^(\d+\.\d+\.\d+)-dev\.(\d+)$")

DEFAULT_CONFIG = Path("ipbuilding_gateway/config.yaml")


def read_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError(f"no version field in {path}")
    return match.group(1).strip()


def next_dev_version(current: str, run_number: int) -> str:
    """Return the dev tag to publish for this workflow run."""
    if run_number < 1:
        raise ValueError("run_number must be >= 1")
    release = _RELEASE_RE.fullmatch(current)
    if release:
        major, minor, _patch = release.groups()
        return f"{major}.{int(minor) + 1}.0-dev.{run_number}"
    dev = _DEV_RE.fullmatch(current)
    if dev:
        base, _number = dev.groups()
        return f"{base}-dev.{run_number}"
    raise ValueError(f"unsupported version {current!r}")


def _base_tuple(base: str) -> tuple[int, int, int]:
    major, minor, patch = base.split(".")
    return int(major), int(minor), int(patch)


def is_dev_version(version: str) -> bool:
    return _DEV_RE.fullmatch(version) is not None


def is_older_dev(current: str, proposed: str) -> bool:
    """True when writing ``proposed`` would move the dev channel backwards."""
    current_dev = _DEV_RE.fullmatch(current)
    proposed_dev = _DEV_RE.fullmatch(proposed)
    if not current_dev or not proposed_dev:
        return False
    current_base = _base_tuple(current_dev.group(1))
    proposed_base = _base_tuple(proposed_dev.group(1))
    if current_base != proposed_base:
        return current_base > proposed_base
    return int(current_dev.group(2)) >= int(proposed_dev.group(2))


def write_version(path: Path, version: str, *, no_downgrade: bool = False) -> bool:
    """Set ``version`` in config.yaml. Only ``X.Y.Z-dev.N`` is allowed.

    Returns True when the file changed.
    """
    if not is_dev_version(version):
        raise ValueError(
            f"refusing to write {version!r}; only X.Y.Z-dev.N is allowed"
        )
    current = read_version(path)
    if no_downgrade and is_older_dev(current, version):
        return False
    text = path.read_text(encoding="utf-8")
    new_text, count = _VERSION_RE.subn(f'version: "{version}"', text, count=1)
    if count != 1:
        raise ValueError(f"version field not replaced in {path}")
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _cmd_next(args: argparse.Namespace) -> int:
    current = read_version(args.config)
    print(next_dev_version(current, args.run_number))
    return 0


def _cmd_write(args: argparse.Namespace) -> int:
    changed = write_version(
        args.config, args.version, no_downgrade=args.no_downgrade
    )
    print("updated" if changed else "unchanged")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    if not is_dev_version(args.version):
        print(
            f"refusing to publish {args.version!r} from develop; "
            "only X.Y.Z-dev.N tags are allowed",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    next_parser = sub.add_parser("next", help="print the next dev version")
    next_parser.add_argument("--run-number", type=int, required=True)
    next_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    next_parser.set_defaults(func=_cmd_next)

    write_parser = sub.add_parser("write", help="write a dev version into config")
    write_parser.add_argument("--version", required=True)
    write_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    write_parser.add_argument("--no-downgrade", action="store_true")
    write_parser.set_defaults(func=_cmd_write)

    check_parser = sub.add_parser(
        "check", help="exit 1 unless the version is X.Y.Z-dev.N"
    )
    check_parser.add_argument("--version", required=True)
    check_parser.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
