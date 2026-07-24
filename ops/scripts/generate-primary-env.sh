#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root." >&2
  exit 1
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
replace=0
if [[ "${1:-}" == "--replace" ]]; then
  replace=1
  shift
fi
target="${1:-/srv/smart-bamboo/config/primary.env}"
if [[ "$#" -gt 1 ]]; then
  echo "Usage: $0 [--replace] [TARGET]" >&2
  exit 64
fi
if [[ -e "${target}" ]]; then
  if [[ "${replace}" != "1" || "${CONFIRM_REPLACE_PRIMARY_ENV:-}" != "YES" ]]; then
    echo "ERROR: refusing to overwrite ${target}; use --replace with CONFIRM_REPLACE_PRIMARY_ENV=YES only during a reviewed secret rotation." >&2
    exit 2
  fi
fi
mkdir -p "$(dirname "${target}")"
umask 077

mysql_password="$(openssl rand -hex 24)"
mysql_root_password="$(openssl rand -hex 24)"
replication_password="$(openssl rand -hex 24)"
geoserver_password="$(openssl rand -hex 24)"
dashboard_token="$(openssl rand -hex 32)"
break_glass_token="$(openssl rand -hex 32)"
release_commit="$(git -C "${repo_root}" rev-parse HEAD)"
release_tag="20260717-${release_commit:0:12}"

cat > "${target}" <<EOF
MYSQL_DATABASE=smart_bamboo
MYSQL_USER=smart_bamboo
MYSQL_PASSWORD=${mysql_password}
MYSQL_ROOT_PASSWORD=${mysql_root_password}
REPLICATION_USER=smart_bamboo_repl
REPLICATION_PASSWORD=${replication_password}
SMART_BAMBOO_RELEASE_TAG=${release_tag}
SMART_BAMBOO_RELEASE_COMMIT=${release_commit}
SMART_BAMBOO_DASHBOARD_TOKEN=${dashboard_token}
SMART_BAMBOO_BREAK_GLASS_TOKEN=${break_glass_token}
SMART_BAMBOO_HUMAN_AUTH_ENABLED=0
SMART_BAMBOO_AUTH_REQUIRE_HTTPS=1
SMART_BAMBOO_TRUST_PROXY_HEADERS=1
SMART_BAMBOO_SESSION_COOKIE_SECURE=1
SMART_BAMBOO_TLS_ENABLED=0
SMART_BAMBOO_TLS_CERT_PATH=
SMART_BAMBOO_TLS_KEY_PATH=
SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:${mysql_password}@db-primary:3306/smart_bamboo?charset=utf8mb4
REMOTE_SENSING_DATABASE_URL=mysql://smart_bamboo:${mysql_password}@db-primary:3306/smart_bamboo?charset=utf8mb4
REMOTE_SENSING_API_TOKENS='{"${dashboard_token}":{"user":"dashboard","roles":["viewer"],"projects":["*"],"areas":["*"]},"${break_glass_token}":{"user":"break_glass","roles":["admin"],"projects":["*"],"areas":["*"]}}'
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
cat > "$(dirname "${target}")/satellite-config.local.js" <<EOF
window.SATELLITE_CONFIG = {
  humanLoginEnabled: null,
  remoteApiBase: "",
  tiandituProxy: true,
  tiandituProxyBaseUrl: "",
};
EOF
chmod 0640 "$(dirname "${target}")/satellite-config.local.js"
echo "Created ${target}; record the immutable release commit and store the break-glass token offline."
