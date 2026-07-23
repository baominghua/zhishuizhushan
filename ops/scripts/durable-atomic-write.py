#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Durably atomically replace a protected file from stdin.")
    parser.add_argument("target", type=Path)
    parser.add_argument("mode", type=lambda value: int(value, 8))
    return parser.parse_args()


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


def main() -> int:
    args = parse_args()
    payload = os.read(0, 64 * 1024 * 1024)
    if not payload:
        raise SystemExit("refusing to atomically write an empty protected file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{args.target.name}.", dir=args.target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, args.mode)
        os.replace(temporary, args.target)
        fsync_directory(args.target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
