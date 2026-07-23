#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys


FIELD_PATTERN = re.compile(r"^\s*([A-Za-z0-9_]+):\s?(.*)$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read one unambiguous field from SHOW REPLICA STATUS\\G output.")
    parser.add_argument("field")
    args = parser.parse_args()
    values: list[str] = []
    for line in sys.stdin.read().splitlines():
        match = FIELD_PATTERN.fullmatch(line)
        if match and match.group(1) == args.field:
            values.append(match.group(2))
    if len(values) != 1:
        raise SystemExit(f"expected exactly one {args.field} field; found {len(values)} (multiple channels are unsupported)")
    print(values[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
