#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a provider-backed fencing proof for standby promotion."
    )
    parser.add_argument("--expected-instance", required=True)
    parser.add_argument("--expected-nonce", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        proof = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit(f"invalid fencing proof JSON: {exc}") from exc
    if not isinstance(proof, dict):
        raise SystemExit("fencing proof must be a JSON object")
    if proof.get("fenced") is not True:
        raise SystemExit("provider did not attest that the primary is fenced")
    if str(proof.get("instanceId") or "") != args.expected_instance:
        raise SystemExit("fencing proof targets a different primary instance")
    if str(proof.get("nonce") or "") != args.expected_nonce:
        raise SystemExit("fencing proof nonce does not match this promotion")
    if str(proof.get("state") or "").lower() not in {"stopped", "isolated", "fenced"}:
        raise SystemExit("fencing proof has no accepted provider state")
    if not str(proof.get("provider") or "").strip():
        raise SystemExit("fencing proof has no provider identity")
    if not str(proof.get("proofId") or "").strip():
        raise SystemExit("fencing proof has no provider proof identifier")
    print("FENCE_PROOF_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
