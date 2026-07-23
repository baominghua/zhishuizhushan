#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read selected protected dotenv values without executing them.")
    parser.add_argument("env_file", type=Path)
    parser.add_argument("keys", nargs="+")
    return parser.parse_args()


def parse_value(raw: str, line_number: int) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"line {line_number} is not a KEY=VALUE assignment")
    key, value = raw.split("=", 1)
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(f"line {line_number} has an invalid key")
    value = value.strip()
    if value[:1] in {"'", '"'}:
        if len(value) < 2 or value[-1] != value[0]:
            raise ValueError(f"line {line_number} has an unterminated quoted value")
        value = value[1:-1]
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"line {line_number} contains an unsafe multiline value")
    return key, value


def main() -> int:
    args = parse_args()
    requested = set(args.keys)
    if any(not KEY_PATTERN.fullmatch(key) for key in requested):
        raise SystemExit("requested keys must be uppercase dotenv keys")

    values: dict[str, str] = {}
    for line_number, raw in enumerate(args.env_file.read_text(encoding="utf-8-sig").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = parse_value(raw, line_number)
        if key in requested:
            if key in values:
                raise SystemExit(f"duplicate protected dotenv key: {key}")
            values[key] = value

    missing = [key for key in args.keys if key not in values]
    if missing:
        raise SystemExit("missing protected dotenv key(s): " + ", ".join(missing))
    sys.stdout.write("\n".join(values[key] for key in args.keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
