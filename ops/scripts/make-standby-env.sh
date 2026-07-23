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
tmp_env="$(mktemp "${target_dir}/.standby.env.XXXXXX")"
tmp_satellite="$(mktemp "${target_dir}/.satellite-config.local.js.XXXXXX")"
cleanup() { rm -f "${tmp_env}" "${tmp_satellite}"; }
trap cleanup EXIT
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
mv -f "${tmp_env}" "${target}"
mv -f "${tmp_satellite}" "${target_dir}/satellite-config.local.js"
trap - EXIT
echo "Created ${target}."
