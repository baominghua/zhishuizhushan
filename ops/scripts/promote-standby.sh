#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${CONFIRM_PRIMARY_UNAVAILABLE:-}" != "YES" ]]; then
  echo "ERROR: set CONFIRM_PRIMARY_UNAVAILABLE=YES only after confirming the primary cannot write." >&2
  exit 1
fi
if curl -fsS --connect-timeout 2 --max-time 5 http://192.168.0.32/api/health >/dev/null 2>&1; then
  if [[ "${CONFIRM_FORCE_SPLIT_BRAIN_RISK:-}" != "YES" ]]; then
    echo "ERROR: primary still responds. Promotion blocked to prevent split brain." >&2
    exit 2
  fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo-dr/config/standby.env}"
set -a
source "${env_file}"
set +a
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.standby.yml")
human_auth_enabled="${SMART_BAMBOO_HUMAN_AUTH_ENABLED:-0}"
tls_enabled="${SMART_BAMBOO_TLS_ENABLED:-0}"
for required_dir in /srv/smart-bamboo-dr/config /srv/smart-bamboo-dr/data /srv/smart-bamboo-dr/mysql-replica; do
  [[ -d "${required_dir}" ]] || { echo "ERROR: required standby directory is missing: ${required_dir}" >&2; exit 3; }
done
[[ -n "${SMART_BAMBOO_RELEASE_COMMIT:-}" && -n "${SMART_BAMBOO_RELEASE_TAG:-}" ]] || { echo "ERROR: standby release commit/tag is missing; run upgrade-primary-env.py and make-standby-env.sh first." >&2; exit 3; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${SMART_BAMBOO_RELEASE_COMMIT}" ]] || { echo "ERROR: checked-out commit does not match SMART_BAMBOO_RELEASE_COMMIT." >&2; exit 3; }
[[ -n "${REMOTE_SENSING_API_TOKENS:-}" && -n "${SMART_BAMBOO_BREAK_GLASS_TOKEN:-}" ]] || { echo "ERROR: standby token configuration is incomplete." >&2; exit 3; }
case "${human_auth_enabled}" in
  1)
    if [[ "${tls_enabled}" != "1" ]]; then
      echo "ERROR: standby human authentication requires SMART_BAMBOO_TLS_ENABLED=1." >&2
      exit 4
    fi
    if [[ "${CONFIRM_HUMAN_AUTH_ENABLED:-}" != "1" ]]; then
      echo "ERROR: set CONFIRM_HUMAN_AUTH_ENABLED=1 to promote the synchronized password-authentication state." >&2
      exit 5
    fi
    ;;
  0) ;;
  *)
    echo "ERROR: SMART_BAMBOO_HUMAN_AUTH_ENABLED must be 0 or 1." >&2
    exit 6
    ;;
esac
case "${tls_enabled}" in
  1)
    for required_dir in /srv/smart-bamboo-dr/tls; do
      [[ -d "${required_dir}" ]] || { echo "ERROR: required standby TLS directory is missing: ${required_dir}" >&2; exit 7; }
    done
    [[ "${SMART_BAMBOO_TLS_CERT_PATH:-}" == /srv/smart-bamboo-dr/tls/* && -f "${SMART_BAMBOO_TLS_CERT_PATH}" ]] || { echo "ERROR: standby TLS certificate is missing or outside /srv/smart-bamboo-dr/tls." >&2; exit 7; }
    [[ "${SMART_BAMBOO_TLS_KEY_PATH:-}" == /srv/smart-bamboo-dr/tls/* && -f "${SMART_BAMBOO_TLS_KEY_PATH}" ]] || { echo "ERROR: standby TLS private key is missing or outside /srv/smart-bamboo-dr/tls." >&2; exit 7; }
    openssl x509 -in "${SMART_BAMBOO_TLS_CERT_PATH}" -noout -checkend 2592000
    openssl pkey -in "${SMART_BAMBOO_TLS_KEY_PATH}" -noout
    compose+=( -f "${repo_root}/ops/compose.tls.yml" )
    ;;
  0) ;;
  *)
    echo "ERROR: SMART_BAMBOO_TLS_ENABLED must be 0 or 1." >&2
    exit 8
    ;;
esac
"${compose[@]}" config --quiet
docker image inspect "smart-bamboo-app:${SMART_BAMBOO_RELEASE_TAG}" >/dev/null
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<'SQL'
STOP REPLICA;
RESET REPLICA ALL;
SET GLOBAL super_read_only=OFF;
SET GLOBAL read_only=OFF;
SQL
cat > /srv/smart-bamboo-dr/config/role-override.cnf <<'EOF'
[mysqld]
read_only=OFF
super_read_only=OFF
skip_replica_start=ON
EOF
chmod 0640 /srv/smart-bamboo-dr/config/role-override.cnf
"${compose[@]}" --profile failover up -d app geoserver nginx
echo "Standby promoted with SMART_BAMBOO_HUMAN_AUTH_ENABLED=${human_auth_enabled}. Open public port 80/443 only after application health passes."
