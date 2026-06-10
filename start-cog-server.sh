#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install -r server/requirements.txt
./.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8010
