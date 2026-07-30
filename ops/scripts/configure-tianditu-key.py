#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import tempfile
from pathlib import Path


TIANDITU_KEY = re.compile(r"^[A-Za-z0-9]{32}$")
ENV_KEY = "REMOTE_SENSING_TIANDITU_TK"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Store a Tianditu server key in the protected primary environment."
    )
    parser.add_argument("--env-file", default="/srv/smart-bamboo/config/primary.env")
    parser.add_argument(
        "--key-stdin",
        action="store_true",
        help="Read one key line from stdin instead of prompting.",
    )
    return parser.parse_args()


def read_key(*, from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().strip()
    return getpass.getpass("Tianditu server key: ").strip()


def fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        if os.name == "posix":
            raise
        return
    try:
        os.fsync(descriptor)
    except OSError:
        if os.name == "posix":
            raise
    finally:
        os.close(descriptor)


def atomic_replace(path: Path, lines: list[str]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    path = Path(args.env_file)
    if not path.is_file():
        raise SystemExit(f"environment file does not exist: {path}")

    key = read_key(from_stdin=args.key_stdin)
    if TIANDITU_KEY.fullmatch(key) is None:
        raise SystemExit("Tianditu key must contain exactly 32 letters or digits")

    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(f"{ENV_KEY}=")]
    if len(matches) > 1:
        raise SystemExit(f"refusing to update duplicate {ENV_KEY} entries")
    rendered = f"{ENV_KEY}={key}\n"
    if matches:
        lines[matches[0]] = rendered
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(rendered)

    atomic_replace(path, lines)
    print(f"Tianditu server key stored in {path}; key value was not logged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
