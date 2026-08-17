#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${SMART_BAMBOO_ENV_FILE:-/srv/smart-bamboo/config/primary.env}"
public_ip="${SMART_BAMBOO_PUBLIC_IP:-36.140.138.117}"
tls_dir="/srv/smart-bamboo/tls"
cert_path="${tls_dir}/v2-test-fullchain.pem"
key_path="${tls_dir}/v2-test-privkey.pem"

[[ "$(id -u)" == "0" ]] || { echo "ERROR: run as root." >&2; exit 2; }
[[ -f "${env_file}" ]] || { echo "ERROR: protected environment not found." >&2; exit 2; }
cd "${repo_root}"

read -r -p "Administrator username [admin]: " username
username="${username:-admin}"
read -r -p "Display name [System Administrator]: " display_name
display_name="${display_name:-System Administrator}"
read -r -s -p "Custom password: " password
echo
read -r -s -p "Repeat password: " password_repeat
echo
[[ -n "${password}" && "${password}" == "${password_repeat}" ]] || {
  unset password password_repeat
  echo "ERROR: passwords are empty or do not match." >&2
  exit 2
}

compose=(
  docker compose
  --project-directory "${repo_root}"
  --env-file "${env_file}"
  -f ops/compose.primary.yml
)

app_id="$("${compose[@]}" ps -q app)"
[[ -n "${app_id}" ]] || { echo "ERROR: primary application is not running." >&2; exit 2; }
[[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${app_id}")" == "healthy" ]] || {
  echo "ERROR: primary application is not healthy." >&2
  exit 2
}

echo "=== CREATE ADMINISTRATOR CREDENTIAL ==="
printf '%s\n' "${password}" | "${compose[@]}" exec -T app \
  python /app/ops/scripts/bootstrap-admin-password.py \
  --username "${username}" \
  --display-name "${display_name}" \
  --password-stdin
unset password password_repeat

"${compose[@]}" exec -T app python -c \
  'import sys; from server.modules import admin_users; from server.modules.auth_store import credential_for_user, save_credential; u=admin_users.user_by_username(sys.argv[1]); assert u; c=credential_for_user(u["id"]); assert c; c["mustChangePassword"]=False; save_credential(c)' \
  "${username}"

echo "=== CREATE TEST TLS CERTIFICATE ==="
install -d -m 700 -o root -g root "${tls_dir}"
if [[ ! -s "${cert_path}" || ! -s "${key_path}" ]]; then
  openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
    -subj "/CN=${public_ip}" \
    -addext "subjectAltName=IP:${public_ip}" \
    -keyout "${key_path}" \
    -out "${cert_path}" >/dev/null 2>&1
fi
chown root:root "${cert_path}" "${key_path}"
chmod 644 "${cert_path}"
chmod 600 "${key_path}"
openssl x509 -in "${cert_path}" -noout -checkend 86400

echo "=== CONFIGURE V2 TLS PATHS ==="
python3 ops/scripts/configure-v2-password-env.py \
  --env-file "${env_file}" \
  --cert-path "${cert_path}" \
  --key-path "${key_path}"
chown root:root "${env_file}"
chmod 600 "${env_file}"

compose_secure=(
  docker compose
  --project-directory "${repo_root}"
  --env-file "${env_file}"
  -f ops/compose.primary.yml
  -f ops/compose.v2-secure.yml
)
"${compose_secure[@]}" config --quiet

echo "=== START ISOLATED V2 APPLICATION ==="
"${compose_secure[@]}" up -d --no-deps app-v2-secure
for attempt in $(seq 1 30); do
  app_id="$("${compose_secure[@]}" ps -q app-v2-secure)"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${app_id}")"
  [[ "${health}" == "healthy" ]] && break
  echo "app_health_attempt=${attempt} status=${health}"
  sleep 5
done
[[ "${health}" == "healthy" ]] || { echo "ERROR: application did not become healthy." >&2; exit 1; }

echo "=== START SECURE V2 ENTRY ==="
"${compose_secure[@]}" up -d --no-deps nginx-v2-secure
for attempt in $(seq 1 20); do
  if curl -kfsS "https://127.0.0.1:18443/api/auth/config" | grep -q '"humanLoginEnabled":true'; then
    echo "secure_login_ready_attempt=${attempt}"
    break
  fi
  sleep 2
done
curl -kfsS "https://127.0.0.1:18443/api/auth/config" | grep -q '"humanLoginEnabled":true'

echo "username=${username}"
echo "v2_secure_url=https://${public_ip}:18443/v2/workspace"
echo "SMART_BAMBOO_V2_PASSWORD_LOGIN_READY"
