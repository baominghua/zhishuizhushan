#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_KEYS = {
    "REMOTE_SENSING_API_TOKENS",
    "SMART_BAMBOO_BREAK_GLASS_TOKEN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the synchronized break-glass service-token profile."
    )
    parser.add_argument("env_file", type=Path)
    return parser.parse_args()


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw:
            raise SystemExit(f"invalid environment assignment on line {line_number}")
        key, encoded = raw.split("=", 1)
        if key in values:
            raise SystemExit(f"duplicate environment key: {key}")
        value = encoded.strip()
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise SystemExit(f"unterminated environment value on line {line_number}")
            value = value[1:-1]
        values[key] = value
    missing = sorted(REQUIRED_KEYS - values.keys())
    if missing:
        raise SystemExit("missing break-glass environment key(s): " + ", ".join(missing))
    return values


def contains(value: object, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    return isinstance(value, list) and expected in value


def main() -> int:
    values = parse_env(parse_args().env_file)
    pointer = values["SMART_BAMBOO_BREAK_GLASS_TOKEN"]
    if not pointer:
        raise SystemExit("SMART_BAMBOO_BREAK_GLASS_TOKEN is empty")
    try:
        profiles = json.loads(values["REMOTE_SENSING_API_TOKENS"])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"REMOTE_SENSING_API_TOKENS is invalid JSON: {exc}") from exc
    if not isinstance(profiles, dict) or pointer not in profiles:
        raise SystemExit("break-glass token pointer is absent from REMOTE_SENSING_API_TOKENS")
    profile = profiles[pointer]
    if not isinstance(profile, dict) or profile.get("user") != "break_glass":
        raise SystemExit('break-glass profile user must be "break_glass"')
    if not contains(profile.get("roles"), "admin"):
        raise SystemExit('break-glass profile roles must contain "admin"')
    if not contains(profile.get("projects"), "*"):
        raise SystemExit('break-glass profile projects must contain "*"')
    if not contains(profile.get("areas"), "*"):
        raise SystemExit('break-glass profile areas must contain "*"')
    print("BREAK_GLASS_PROFILE_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
