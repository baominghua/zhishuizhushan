#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate the Smart Bamboo break-glass service token.")
    parser.add_argument("--env-file", default="/srv/smart-bamboo/config/primary.env")
    parser.add_argument("--token-output-file")
    return parser.parse_args()


def env_value(line: str) -> str:
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def replace_env(lines: list[str], key: str, value: str, *, quote: bool = False) -> list[str]:
    rendered = f"{key}={'\'' + value + '\'' if quote else value}\n"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = rendered
            return lines
    lines.append(rendered)
    return lines


def main() -> int:
    args = parse_args()
    path = Path(args.env_file)
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    token_line = next((line for line in lines if line.startswith("REMOTE_SENSING_API_TOKENS=")), None)
    if token_line is None:
        raise SystemExit("REMOTE_SENSING_API_TOKENS is missing from the protected environment file")

    try:
        profiles = json.loads(env_value(token_line))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"REMOTE_SENSING_API_TOKENS is not valid JSON: {exc}") from exc
    if not isinstance(profiles, dict):
        raise SystemExit("REMOTE_SENSING_API_TOKENS must be a JSON object")

    current_line = next((line for line in lines if line.startswith("SMART_BAMBOO_BREAK_GLASS_TOKEN=")), None)
    current_break_glass_token = env_value(current_line) if current_line else ""
    token = secrets.token_hex(32)
    profiles = {
        existing_token: profile
        for existing_token, profile in profiles.items()
        if existing_token != current_break_glass_token
        and (not isinstance(profile, dict) or profile.get("user") != "break_glass")
    }
    profiles[token] = {"user": "break_glass", "roles": ["admin"], "projects": ["*"], "areas": ["*"]}
    encoded_profiles = json.dumps(profiles, separators=(",", ":"), ensure_ascii=True)
    lines = replace_env(lines, "SMART_BAMBOO_BREAK_GLASS_TOKEN", token)
    lines = replace_env(lines, "REMOTE_SENSING_API_TOKENS", encoded_profiles, quote=True)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.writelines(lines)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    if args.token_output_file:
        output_path = Path(args.token_output_file)
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        print(f"Break-glass token written once to {output_path}; transfer it offline and remove the file.")
    else:
        print("Break-glass token (interactive console only; clear the screen after recording it offline): " + token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
