#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root." >&2
  exit 1
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
target="${1:-/srv/smart-bamboo/config/primary.env}"
mkdir -p "$(dirname "${target}")"
umask 077

mysql_password="$(openssl rand -hex 24)"
mysql_root_password="$(openssl rand -hex 24)"
replication_password="$(openssl rand -hex 24)"
geoserver_password="$(openssl rand -hex 24)"
admin_token="$(openssl rand -hex 32)"
dashboard_token="$(openssl rand -hex 32)"
release_tag="20260717-$(git -C "${repo_root}" rev-parse --short=12 HEAD)"

cat > "${target}" <<EOF
MYSQL_DATABASE=smart_bamboo
MYSQL_USER=smart_bamboo
MYSQL_PASSWORD=${mysql_password}
MYSQL_ROOT_PASSWORD=${mysql_root_password}
REPLICATION_USER=smart_bamboo_repl
REPLICATION_PASSWORD=${replication_password}
SMART_BAMBOO_RELEASE_TAG=${release_tag}
SMART_BAMBOO_DASHBOARD_TOKEN=${dashboard_token}
SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:${mysql_password}@db-primary:3306/smart_bamboo?charset=utf8mb4
REMOTE_SENSING_DATABASE_URL=mysql://smart_bamboo:${mysql_password}@db-primary:3306/smart_bamboo?charset=utf8mb4
REMOTE_SENSING_API_TOKENS='{"${admin_token}":{"user":"admin","roles":["admin"],"projects":["*"],"areas":["*"]},"${dashboard_token}":{"user":"dashboard","roles":["viewer"],"projects":["*"],"areas":["*"]}}'
REMOTE_SENSING_CORS_ORIGINS=http://36.140.138.117
REMOTE_SENSING_TASK_WORKERS=4
REMOTE_SENSING_TIANDITU_TK=
REMOTE_SENSING_TIANDITU_REFERER=http://36.140.138.117
REMOTE_SENSING_BASEMAP_CACHE_MAX_BYTES=53687091200
REMOTE_SENSING_BASEMAP_CACHE_MAX_AGE_DAYS=30
SMART_BAMBOO_MYSQL_WRITE_BATCH_SIZE=1000
SMART_BAMBOO_IDENTITY_LOOKUP_BATCH_SIZE=1000
SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_BYTES=21474836480
GEOSERVER_ADMIN_USER=admin
GEOSERVER_ADMIN_PASSWORD=${geoserver_password}
EOF
chmod 0600 "${target}"
printf '%s\n' "${admin_token}" > "$(dirname "${target}")/admin-token.txt"
chmod 0600 "$(dirname "${target}")/admin-token.txt"
cat > "$(dirname "${target}")/satellite-config.local.js" <<EOF
window.SATELLITE_CONFIG = {
  remoteApiBase: "",
  apiToken: "${dashboard_token}",
  tiandituProxy: true,
  tiandituProxyBaseUrl: "",
};
EOF
chmod 0640 "$(dirname "${target}")/satellite-config.local.js"
echo "Created ${target}; admin token is private and the browser received a separate read-only token."
