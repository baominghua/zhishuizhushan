#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bind standby RPO acceptance to the durable final fence proof."
    )
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--fence-proof", required=True, type=Path)
    parser.add_argument("--release-commit", required=True)
    parser.add_argument("--primary-instance-id", required=True)
    parser.add_argument("--expected-evidence-sha256", required=True)
    parser.add_argument("--current-retrieved-gtid-set", required=True)
    parser.add_argument("--current-executed-gtid-set", required=True)
    return parser.parse_args()


def require_safe_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"{label} is missing or is not a safe regular file")


def read_fields(path: Path, label: str) -> dict[str, str]:
    require_safe_file(path, label)
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        if "=" not in line:
            raise SystemExit(f"{label} contains an invalid field")
        key, value = line.split("=", 1)
        if not key or key in fields:
            raise SystemExit(f"{label} field is missing or duplicated: {key}")
        fields[key] = value
    return fields


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_field(fields: dict[str, str], key: str, label: str) -> str:
    if key not in fields:
        raise SystemExit(f"{label} field is missing or duplicated: {key}")
    return fields[key]


def main() -> int:
    args = parse_args()
    state = read_fields(args.state, "promotion state")
    evidence = read_fields(args.evidence, "RPO evidence")
    require_safe_file(args.fence_proof, "final fence proof")

    if require_field(state, "phase", "promotion state") != "rpo-review":
        raise SystemExit("promotion state is not awaiting RPO review")
    if require_field(state, "release_commit", "promotion state") != args.release_commit:
        raise SystemExit("promotion state belongs to another release")
    if (
        require_field(state, "primary_instance_id", "promotion state")
        != args.primary_instance_id
    ):
        raise SystemExit("promotion state belongs to another primary instance")
    if require_field(state, "accepted_rpo_evidence_sha256", "promotion state"):
        raise SystemExit("promotion state already contains an RPO acceptance")

    expected_evidence = args.expected_evidence_sha256
    actual_evidence = sha256_file(args.evidence)
    state_evidence = require_field(state, "rpo_evidence_sha256", "promotion state")
    if (
        not SHA256_RE.fullmatch(expected_evidence)
        or expected_evidence != actual_evidence
        or expected_evidence != state_evidence
    ):
        raise SystemExit("expected digest does not match the final RPO evidence")

    actual_proof = sha256_file(args.fence_proof)
    state_proof = require_field(state, "fence_proof_sha256", "promotion state")
    evidence_proof = require_field(evidence, "fence_proof_sha256", "RPO evidence")
    if (
        not SHA256_RE.fullmatch(actual_proof)
        or actual_proof != state_proof
        or actual_proof != evidence_proof
    ):
        raise SystemExit("final fence proof digest does not match accepted RPO evidence")

    if require_field(evidence, "release_commit", "RPO evidence") != args.release_commit:
        raise SystemExit("RPO evidence belongs to another release")
    if (
        require_field(evidence, "primary_instance_id", "RPO evidence")
        != args.primary_instance_id
    ):
        raise SystemExit("RPO evidence belongs to another primary instance")
    if (
        require_field(evidence, "retrieved_gtid_set", "RPO evidence")
        != args.current_retrieved_gtid_set
        or require_field(evidence, "executed_gtid_set", "RPO evidence")
        != args.current_executed_gtid_set
    ):
        raise SystemExit("replica GTID state changed after RPO evidence capture")

    print("RPO_EVIDENCE_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
