#!/usr/bin/env bash
set -Eeuo pipefail

role="${1:?Usage: $0 primary|standby [ENV_FILE]}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${role}" != "primary" ]]; then
  echo "ERROR: TLS activation is primary only; standby TLS starts through promote-standby.sh after failover." >&2
  exit 64
fi
env_file="${2:-/srv/smart-bamboo/config/primary.env}"
compose_file="${repo_root}/ops/compose.primary.yml"
env_reader="${repo_root}/ops/scripts/read-protected-env.py"
read_env_value() {
  python3 "${env_reader}" "${env_file}" "$1"
}
tls_enabled="$(read_env_value SMART_BAMBOO_TLS_ENABLED)"
tls_cert_path="$(read_env_value SMART_BAMBOO_TLS_CERT_PATH)"
tls_key_path="$(read_env_value SMART_BAMBOO_TLS_KEY_PATH)"

[[ "${tls_enabled}" == "1" ]] || { echo "ERROR: set SMART_BAMBOO_TLS_ENABLED=1 first." >&2; exit 2; }
[[ -n "${tls_cert_path}" && -f "${tls_cert_path}" ]] || { echo "ERROR: certificate path is missing or unreadable." >&2; exit 3; }
[[ -n "${tls_key_path}" && -f "${tls_key_path}" ]] || { echo "ERROR: private-key path is missing or unreadable." >&2; exit 4; }
openssl x509 -in "${tls_cert_path}" -noout -checkend 2592000
cert_public_key="$(openssl x509 -in "${tls_cert_path}" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')"
key_public_key="$(openssl pkey -in "${tls_key_path}" -pubout -outform DER | sha256sum | awk '{print $1}')"
[[ -n "${cert_public_key}" && "${cert_public_key}" == "${key_public_key}" ]] || { echo "ERROR: TLS certificate and private key do not match." >&2; exit 2; }

compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${compose_file}" -f "${repo_root}/ops/compose.tls.yml")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-deps nginx
echo "TLS Nginx configured. Verify the public DNS name and certificate chain from an external client before enabling human authentication."
