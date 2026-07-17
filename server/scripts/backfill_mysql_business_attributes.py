from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.modules.business import backfill_business_attribute_rows
from server.modules.database import init_platform_schema, mysql_connect
from server.modules.settings import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill indexed core attributes for existing MySQL business records."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("SMART_BAMBOO_DATABASE_URL", ""),
    )
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("SMART_BAMBOO_DATABASE_URL or --database-url is required")
    if args.batch_size < 1 or args.batch_size > 10_000:
        raise SystemExit("--batch-size must be between 1 and 10000")

    os.environ["SMART_BAMBOO_STORAGE_BACKEND"] = "mysql"
    os.environ["SMART_BAMBOO_DATABASE_URL"] = args.database_url
    get_settings.cache_clear()
    init_platform_schema()

    report = {"recordsProcessed": 0, "attributesWritten": 0, "unknownModules": []}
    unknown_modules: set[str] = set()
    with mysql_connect(args.database_url) as conn:
        with conn.cursor() as read_cur, conn.cursor() as write_cur:
            read_cur.execute(
                "SELECT id, module_key, properties, updated_at "
                "FROM business_records ORDER BY id"
            )
            while True:
                rows = list(read_cur.fetchmany(args.batch_size))
                if not rows:
                    break
                batch = backfill_business_attribute_rows(write_cur, rows)
                report["recordsProcessed"] += int(batch["recordsProcessed"])
                report["attributesWritten"] += int(batch["attributesWritten"])
                unknown_modules.update(batch["unknownModules"])
                conn.commit()
    report["unknownModules"] = sorted(unknown_modules)
    report["status"] = "passed" if not unknown_modules else "warning"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
