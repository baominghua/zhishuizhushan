#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enable the secure V2 password-login environment.")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--cert-path", type=Path, required=True)
    parser.add_argument("--key-path", type=Path, required=True)
    return parser.parse_args()


def render_env(source: str, updates: dict[str, str]) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for raw in source.splitlines():
        key = raw.split("=", 1)[0] if "=" in raw else ""
        if key in updates:
            if key in seen:
                raise ValueError(f"duplicate protected dotenv key: {key}")
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    return "\n".join(output) + "\n"


def atomic_write(path: Path, content: str) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    if not args.env_file.is_file():
        raise SystemExit(f"protected environment does not exist: {args.env_file}")
    for path in (args.cert_path, args.key_path):
        if not path.is_absolute() or "\n" in str(path) or "\r" in str(path):
            raise SystemExit("TLS paths must be absolute single-line paths")
    updates = {
        "SMART_BAMBOO_TLS_ENABLED": "1",
        "SMART_BAMBOO_TLS_CERT_PATH": str(args.cert_path),
        "SMART_BAMBOO_TLS_KEY_PATH": str(args.key_path),
    }
    rendered = render_env(args.env_file.read_text(encoding="utf-8-sig"), updates)
    atomic_write(args.env_file, rendered)
    print("V2 TLS paths configured; no credential values were logged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
