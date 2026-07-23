#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add password-authentication rollout keys to an existing primary environment without rotating database secrets.")
    parser.add_argument("--env-file", default="/srv/smart-bamboo/config/primary.env")
    parser.add_argument("--release-commit")
    parser.add_argument("--token-output-file")
    return parser.parse_args()


def value(line: str) -> str:
    raw = line.split("=", 1)[1].strip()
    return raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'} else raw


def set_value(lines: list[str], key: str, raw: str, *, quote: bool = False) -> None:
    rendered = f"{key}={'\'' + raw + '\'' if quote else raw}\n"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = rendered
            return
    lines.append(rendered)


def valid_break_glass_profile(profile: object) -> bool:
    if not isinstance(profile, dict):
        return False
    roles = profile.get("roles")
    return (
        profile.get("user") == "break_glass"
        and isinstance(roles, list)
        and "admin" in roles
        and profile.get("projects") == ["*"]
        and profile.get("areas") == ["*"]
    )


def write_handoff(token: str, output_file: str | None) -> Path:
    if output_file is None:
        raise SystemExit("a missing or invalid break-glass token requires --token-output-file so it is not sent to service logs")
    handoff = Path(output_file)
    descriptor = os.open(handoff, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        handoff.unlink(missing_ok=True)
        raise
    return handoff


def atomic_replace_env(path: Path, lines: list[str]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    path = Path(args.env_file)
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    existing = {line.split("=", 1)[0]: value(line) for line in lines if "=" in line and not line.lstrip().startswith("#")}
    commit = args.release_commit or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if len(commit) != 40:
        raise SystemExit("release commit must be a full 40-character SHA")
    set_value(lines, "SMART_BAMBOO_RELEASE_COMMIT", existing.get("SMART_BAMBOO_RELEASE_COMMIT") or commit)
    set_value(lines, "SMART_BAMBOO_RELEASE_TAG", existing.get("SMART_BAMBOO_RELEASE_TAG") or f"release-{commit[:12]}")
    set_value(lines, "SMART_BAMBOO_HUMAN_AUTH_ENABLED", existing.get("SMART_BAMBOO_HUMAN_AUTH_ENABLED") or "0")
    set_value(lines, "SMART_BAMBOO_AUTH_REQUIRE_HTTPS", existing.get("SMART_BAMBOO_AUTH_REQUIRE_HTTPS") or "1")
    set_value(lines, "SMART_BAMBOO_TRUST_PROXY_HEADERS", existing.get("SMART_BAMBOO_TRUST_PROXY_HEADERS") or "1")
    set_value(lines, "SMART_BAMBOO_SESSION_COOKIE_SECURE", existing.get("SMART_BAMBOO_SESSION_COOKIE_SECURE") or "1")
    set_value(lines, "SMART_BAMBOO_TLS_ENABLED", existing.get("SMART_BAMBOO_TLS_ENABLED") or "0")
    set_value(lines, "SMART_BAMBOO_TLS_CERT_PATH", existing.get("SMART_BAMBOO_TLS_CERT_PATH", ""))
    set_value(lines, "SMART_BAMBOO_TLS_KEY_PATH", existing.get("SMART_BAMBOO_TLS_KEY_PATH", ""))
    encoded = existing.get("REMOTE_SENSING_API_TOKENS")
    if not encoded:
        raise SystemExit("REMOTE_SENSING_API_TOKENS is required; refusing to create a replacement token set")
    profiles = json.loads(encoded)
    if not isinstance(profiles, dict):
        raise SystemExit("REMOTE_SENSING_API_TOKENS must be a JSON object")
    break_glass = existing.get("SMART_BAMBOO_BREAK_GLASS_TOKEN")
    handoff: Path | None = None
    if not break_glass or not valid_break_glass_profile(profiles.get(break_glass)):
        if break_glass:
            profiles.pop(break_glass, None)
        break_glass = secrets.token_hex(32)
        handoff = write_handoff(break_glass, args.token_output_file)
        profiles[break_glass] = {"user": "break_glass", "roles": ["admin"], "projects": ["*"], "areas": ["*"]}
        set_value(lines, "SMART_BAMBOO_BREAK_GLASS_TOKEN", break_glass)
        set_value(lines, "REMOTE_SENSING_API_TOKENS", json.dumps(profiles, separators=(",", ":")), quote=True)
    try:
        atomic_replace_env(path, lines)
    except BaseException:
        if handoff is not None:
            handoff.unlink(missing_ok=True)
        raise
    print("Primary environment upgrade completed without rotating existing database or service credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
