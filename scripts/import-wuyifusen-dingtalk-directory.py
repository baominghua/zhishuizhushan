from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.modules.wuyifusen_dingtalk_directory import import_wuyifusen_directory


if __name__ == "__main__":
    print(json.dumps(import_wuyifusen_directory(), ensure_ascii=False, indent=2))
