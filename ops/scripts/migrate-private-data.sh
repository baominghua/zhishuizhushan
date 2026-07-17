#!/usr/bin/env bash
set -Eeuo pipefail

archive="${1:?Usage: $0 PRIVATE_DATA.sbbundle [PRIMARY_ENV]}"
env_file="${2:-/srv/smart-bamboo/config/primary.env}"
if [[ ! -f "${archive}" || ! -f "${archive}.sha256" ]]; then
  echo "ERROR: encrypted bundle or checksum file missing." >&2
  exit 1
fi
(cd "$(dirname "${archive}")" && sha256sum -c "$(basename "${archive}").sha256")
if [[ "${CONFIRM_MIGRATE_PRIVATE_DATA:-}" != "YES" ]]; then
  echo "Checksum passed. Set CONFIRM_MIGRATE_PRIVATE_DATA=YES to decrypt and migrate." >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bundle_dir="$(cd "$(dirname "${archive}")" && pwd)"
bundle_name="$(basename "${archive}")"
staging="$(mktemp -d /srv/smart-bamboo/incoming/restore.XXXXXX)"
cleanup() {
  local resolved
  resolved="$(realpath "${staging}" 2>/dev/null || true)"
  case "${resolved}" in
    /srv/smart-bamboo/incoming/restore.*) rm -rf -- "${resolved}" ;;
    *) echo "Refusing unsafe staging cleanup: ${resolved}" >&2 ;;
  esac
}
trap cleanup EXIT

if [[ -z "${SMART_BAMBOO_BUNDLE_PASSPHRASE:-}" ]]; then
  read -r -s -p "Private bundle passphrase: " SMART_BAMBOO_BUNDLE_PASSPHRASE
  printf '\n'
  export SMART_BAMBOO_BUNDLE_PASSPHRASE
fi
docker build -t smart-bamboo-private-tool:20260717 "${repo_root}/ops/tools"
docker run --rm \
  -e SMART_BAMBOO_BUNDLE_PASSPHRASE \
  --mount "type=bind,src=${bundle_dir},dst=/input,readonly" \
  --mount "type=bind,src=${staging},dst=/restore" \
  smart-bamboo-private-tool:20260717 \
  extract "/input/${bundle_name}" /restore
unset SMART_BAMBOO_BUNDLE_PASSPHRASE

[[ -d "${staging}/data" ]] || { echo "ERROR: decrypted bundle has no data directory." >&2; exit 3; }
mkdir -p /srv/smart-bamboo/data
cp -a "${staging}/data/." /srv/smart-bamboo/data/
set -a
source "${env_file}"
set +a
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.primary.yml")
"${compose[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py --dry-run
"${compose[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py
"${compose[@]}" exec -T app python server/scripts/verify_mysql_production.py --initialize
