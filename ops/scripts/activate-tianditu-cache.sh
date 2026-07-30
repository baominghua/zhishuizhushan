#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo/config/primary.env}"
if [[ "$#" -gt 1 ]]; then
  echo "Usage: $0 [ENV_FILE]" >&2
  exit 64
fi

if [[ -t 0 ]]; then
  IFS= read -r -s -p "Tianditu server key: " tianditu_key
  printf '\n'
else
  IFS= read -r tianditu_key || {
    echo "ERROR: provide one Tianditu key line on stdin." >&2
    exit 64
  }
fi

printf '%s\n' "${tianditu_key}" |
  python3 "${repo_root}/ops/scripts/configure-tianditu-key.py" \
    --env-file "${env_file}" \
    --key-stdin
unset tianditu_key

compose=(
  docker compose
  --project-directory "${repo_root}"
  --env-file "${env_file}"
  -f "${repo_root}/ops/compose.primary.yml"
)

echo "=== VALIDATE COMPOSE ==="
"${compose[@]}" config --quiet

echo "=== RECREATE APPLICATION ONLY ==="
"${compose[@]}" up -d --no-deps --no-build --force-recreate app

base_url="http://127.0.0.1:8010"
health_file="$(mktemp)"
first_headers="$(mktemp)"
second_headers="$(mktemp)"
trap 'rm -f "${health_file}" "${first_headers}" "${second_headers}"' EXIT

echo "=== WAIT FOR APPLICATION ==="
ready=0
for attempt in $(seq 1 60); do
  if curl -fsS --max-time 5 "${base_url}/api/health" >"${health_file}"; then
    if python3 - "${health_file}" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
proxy = payload.get("deployment", {}).get("tiandituProxy") or payload.get("tiandituProxy") or {}
raise SystemExit(0 if proxy.get("hasServerTk") is True else 1)
PY
    then
      echo "application_ready_attempt=${attempt}"
      ready=1
      break
    fi
  fi
  sleep 2
done
if [[ "${ready}" != "1" ]]; then
  echo "ERROR: application did not expose an enabled Tianditu server key." >&2
  exit 1
fi

tile_url="${base_url}/api/basemaps/tianditu/img_w/12/3392/1733.png"
echo "=== VERIFY PERSISTENT TILE CACHE ==="
curl -fsS --max-time 30 -D "${first_headers}" -o /dev/null "${tile_url}"
grep -Eqi '^x-tianditu-cache: (miss|hit)' "${first_headers}" || {
  echo "ERROR: first tile response did not include a cache result." >&2
  exit 1
}
curl -fsS --max-time 30 -D "${second_headers}" -o /dev/null "${tile_url}"
grep -Eqi '^x-tianditu-cache: hit' "${second_headers}" || {
  echo "ERROR: second tile response was not served from cache." >&2
  exit 1
}
grep -Eqi '^cache-control: .*max-age=2592000' "${second_headers}" || {
  echo "ERROR: browser cache policy is missing." >&2
  exit 1
}

echo "TIANDITU_KEY_AND_PERSISTENT_CACHE_READY"
