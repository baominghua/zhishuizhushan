from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.modules.mysql_migration import collect_json_migration_inventory, migrate_json_to_mysql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate Smart Bamboo JSON data into MySQL 8.")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("REMOTE_SENSING_DATA_DIR", str(ROOT / "data" / "remote-sensing")),
        help="Existing JSON data directory.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("SMART_BAMBOO_DATABASE_URL", ""),
        help="Target mysql:// connection URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only inventory source records; do not write MySQL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    inventory = collect_json_migration_inventory(data_dir)
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "dataDir": str(data_dir), "inventory": inventory}, ensure_ascii=False, indent=2))
        return 0
    if int(inventory.get("totalRecords") or 0) <= 0:
        print(
            json.dumps(
                {
                    "mode": "migrate",
                    "status": "refused",
                    "dataDir": str(data_dir),
                    "reason": "Migration source inventory is empty; check --data-dir before writing MySQL.",
                    "inventory": inventory,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    if not args.database_url:
        raise SystemExit("SMART_BAMBOO_DATABASE_URL or --database-url is required")
    os.environ["SMART_BAMBOO_STORAGE_BACKEND"] = "mysql"
    os.environ["SMART_BAMBOO_DATABASE_URL"] = args.database_url
    os.environ["REMOTE_SENSING_CATALOG_BACKEND"] = "mysql"
    os.environ["REMOTE_SENSING_DATABASE_URL"] = args.database_url

    from server.modules.settings import get_settings

    get_settings.cache_clear()
    migrated = migrate_json_to_mysql(data_dir)
    print(json.dumps({"mode": "migrate", "dataDir": str(data_dir), "migrated": migrated}, ensure_ascii=False, indent=2))
    return 0 if migrated.get("verification", {}).get("verified") else 2


if __name__ == "__main__":
    raise SystemExit(main())
