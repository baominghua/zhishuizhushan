#!/usr/bin/env python3
import argparse
import json
import sys


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-human-auth-pending", action="store_true")
    arguments = parser.parse_args()

    payload = json.load(sys.stdin)
    readiness = payload.get("deployment", {}).get("readiness", {})
    blocking_issues = readiness.get("blockingIssues") or []
    warning_keys = {
        str(item.get("key") or "")
        for item in readiness.get("warnings") or []
    }

    if payload.get("ok") is not True:
        fail("health payload is not ready")
    if blocking_issues:
        fail("deployment readiness contains blocking issues")

    if arguments.allow_human_auth_pending:
        if (
            readiness.get("status") != "warning"
            or warning_keys != {"human_auth_pending_https"}
        ):
            fail("expected only the human_auth_pending_https rollout warning")
        return

    if readiness.get("status") != "ready" or warning_keys:
        fail("expected ready deployment with no warnings")


if __name__ == "__main__":
    main()
