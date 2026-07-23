#!/usr/bin/env bash
set -Eeuo pipefail

role="${1:?Usage: $0 primary|standby [ENV_FILE]}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${role}" == "primary" ]]; then
  env_file="${2:-/srv/smart-bamboo/config/primary.env}"
  compose_file="${repo_root}/ops/compose.primary.yml"
else
  env_file="${2:-/srv/smart-bamboo-dr/config/standby.env}"
  compose_file="${repo_root}/ops/compose.standby.yml"
fi
set -a
source "${env_file}"
set +a

[[ "${SMART_BAMBOO_TLS_ENABLED:-0}" == "1" ]] || { echo "ERROR: set SMART_BAMBOO_TLS_ENABLED=1 first." >&2; exit 2; }
[[ -n "${SMART_BAMBOO_TLS_CERT_PATH:-}" && -f "${SMART_BAMBOO_TLS_CERT_PATH}" ]] || { echo "ERROR: certificate path is missing or unreadable." >&2; exit 3; }
[[ -n "${SMART_BAMBOO_TLS_KEY_PATH:-}" && -f "${SMART_BAMBOO_TLS_KEY_PATH}" ]] || { echo "ERROR: private-key path is missing or unreadable." >&2; exit 4; }
openssl x509 -in "${SMART_BAMBOO_TLS_CERT_PATH}" -noout -checkend 2592000

compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${compose_file}" -f "${repo_root}/ops/compose.tls.yml")
"${compose[@]}" config >/tmp/smart-bamboo-${role}-tls-compose.txt
"${compose[@]}" up -d --no-deps nginx
echo "TLS Nginx configured. Verify the public DNS name and certificate chain from an external client before enabling human authentication."
