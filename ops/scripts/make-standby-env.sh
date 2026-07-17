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
sed \
  -e 's/@db-primary:3306/@db-replica:3306/g' \
  -e 's#http://36\.140\.138\.117#http://36.137.23.53#g' \
  "${source_env}" > "${target}"
chmod 0600 "${target}"
dashboard_token="$(sed -n 's/^SMART_BAMBOO_DASHBOARD_TOKEN=//p' "${source_env}" | tail -n 1)"
if [[ ! "${dashboard_token}" =~ ^[A-Fa-f0-9]{64}$ ]]; then
  echo "ERROR: source environment has no valid dashboard token." >&2
  exit 2
fi
cat > "$(dirname "${target}")/satellite-config.local.js" <<EOF
window.SATELLITE_CONFIG = {
  remoteApiBase: "",
  apiToken: "${dashboard_token}",
  tiandituProxy: true,
  tiandituProxyBaseUrl: "",
};
EOF
chmod 0640 "$(dirname "${target}")/satellite-config.local.js"
echo "Created ${target}."
