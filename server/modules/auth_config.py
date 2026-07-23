from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Mapping


AUTH_CONFIG_KEYS = (
    "REMOTE_SENSING_API_TOKENS",
    "SMART_BAMBOO_BREAK_GLASS_TOKEN",
    "SMART_BAMBOO_HUMAN_AUTH_ENABLED",
    "SMART_BAMBOO_AUTH_REQUIRE_HTTPS",
    "SMART_BAMBOO_TRUST_PROXY_HEADERS",
    "SMART_BAMBOO_SESSION_COOKIE_SECURE",
    "SMART_BAMBOO_TLS_ENABLED",
)
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def auth_config_digest(values: Mapping[str, str] | None = None) -> str:
    source = os.environ if values is None else values
    canonical = [[key, str(source.get(key, ""))] for key in AUTH_CONFIG_KEYS]
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
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
        if key in values:
            raise ValueError(f"duplicate protected dotenv key: {key}")
        values[key] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calculate the standby-safe authentication configuration digest."
    )
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    values = dotenv_values(args.env_file)
    missing = [key for key in AUTH_CONFIG_KEYS if key not in values]
    if missing:
        raise SystemExit("missing authentication dotenv key(s): " + ", ".join(missing))
    print(auth_config_digest(values))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
