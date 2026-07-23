#!/usr/bin/env bash
set -Eeuo pipefail

source_env="${1:?Usage: $0 PRIMARY_ENV [OUTPUT_ENV]}"
target="${2:-/srv/smart-bamboo-dr/config/standby.env}"
if [[ ! -f "${source_env}" ]]; then
  echo "ERROR: primary environment file not found." >&2
  exit 1
fi
mkdir -p "$(dirname "${target}")"
umask 077
target_dir="$(dirname "${target}")"
target_satellite="${target_dir}/satellite-config.local.js"
tmp_env="$(mktemp "${target_dir}/.standby.env.XXXXXX")"
tmp_satellite="$(mktemp "${target_dir}/.satellite-config.local.js.XXXXXX")"
backup_env=""
backup_satellite=""
env_existed=0
satellite_existed=0
env_installed=0
satellite_installed=0
cleanup() { rm -f "${tmp_env}" "${tmp_satellite}" "${backup_env:-}" "${backup_satellite:-}"; }
trap cleanup EXIT
if [[ -e "${target}" ]]; then
  backup_env="$(mktemp "${target_dir}/.standby.env.backup.XXXXXX")"
  cp -p "${target}" "${backup_env}"
  env_existed=1
fi
if [[ -e "${target_satellite}" ]]; then
  backup_satellite="$(mktemp "${target_dir}/.satellite-config.local.js.backup.XXXXXX")"
  cp -p "${target_satellite}" "${backup_satellite}"
  satellite_existed=1
fi
rollback_pair() {
  local status=$?
  set +e
  if [[ "${satellite_installed}" == "1" ]]; then
    if [[ "${satellite_existed}" == "1" ]]; then mv -f "${backup_satellite}" "${target_satellite}"; else rm -f "${target_satellite}"; fi
  fi
  if [[ "${env_installed}" == "1" ]]; then
    if [[ "${env_existed}" == "1" ]]; then mv -f "${backup_env}" "${target}"; else rm -f "${target}"; fi
  fi
  exit "${status:-1}"
}
sed \
  -e 's/@db-primary:3306/@db-replica:3306/g' \
  -e 's#http://36\.140\.138\.117#http://36.137.23.53#g' \
  -e 's#/srv/smart-bamboo/tls#/srv/smart-bamboo-dr/tls#g' \
  "${source_env}" > "${tmp_env}"
for key in SMART_BAMBOO_RELEASE_COMMIT SMART_BAMBOO_RELEASE_TAG SMART_BAMBOO_HUMAN_AUTH_ENABLED SMART_BAMBOO_TLS_ENABLED SMART_BAMBOO_TLS_CERT_PATH SMART_BAMBOO_TLS_KEY_PATH REMOTE_SENSING_API_TOKENS SMART_BAMBOO_BREAK_GLASS_TOKEN; do
  grep -q "^${key}=" "${source_env}"
  grep -q "^${key}=" "${tmp_env}"
done
dashboard_token="$(sed -n 's/^SMART_BAMBOO_DASHBOARD_TOKEN=//p' "${source_env}" | tail -n 1)"
if [[ ! "${dashboard_token}" =~ ^[A-Fa-f0-9]{64}$ ]]; then
  echo "ERROR: source environment has no valid dashboard token." >&2
  exit 2
fi
cat > "${tmp_satellite}" <<EOF
window.SATELLITE_CONFIG = {
  remoteApiBase: "",
  apiToken: "${dashboard_token}",
  tiandituProxy: true,
  tiandituProxyBaseUrl: "",
};
EOF
chmod 0600 "${tmp_env}"
chmod 0640 "${tmp_satellite}"
mv -f "${tmp_env}" "${target}" || rollback_pair
env_installed=1
mv -f "${tmp_satellite}" "${target_satellite}" || rollback_pair
satellite_installed=1
grep -q '^window.SATELLITE_CONFIG' "${target_satellite}" || rollback_pair
grep -q '^SMART_BAMBOO_RELEASE_COMMIT=' "${target}" || rollback_pair
trap - EXIT
cleanup
echo "Created ${target}."
