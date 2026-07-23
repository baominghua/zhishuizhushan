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
for required_dir in /srv/smart-bamboo-dr/config /srv/smart-bamboo-dr/data /srv/smart-bamboo-dr/mysql-replica /srv/smart-bamboo-dr/geoserver; do
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
    cert_public_key="$(openssl x509 -in "${SMART_BAMBOO_TLS_CERT_PATH}" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')"
    key_public_key="$(openssl pkey -in "${SMART_BAMBOO_TLS_KEY_PATH}" -pubout -outform DER | sha256sum | awk '{print $1}')"
    [[ -n "${cert_public_key}" && "${cert_public_key}" == "${key_public_key}" ]] || { echo "ERROR: standby TLS certificate and private key do not match." >&2; exit 7; }
    compose+=( -f "${repo_root}/ops/compose.tls.yml" )
    ;;
  0) ;;
  *)
    echo "ERROR: SMART_BAMBOO_TLS_ENABLED must be 0 or 1." >&2
    exit 8
    ;;
esac
"${compose[@]}" config --quiet
for image in "smart-bamboo-app:${SMART_BAMBOO_RELEASE_TAG}" "docker.osgeo.org/geoserver:2.25.7" "nginx:1.30.4-alpine"; do
  docker image inspect "${image}" >/dev/null
done
mysql_exec() {
  "${compose[@]}" exec -T db-replica mysql -N -B -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "$1"
}
replica_status() {
  "${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "SHOW REPLICA STATUS\\G"
}
status_field() {
  local field="$1" status="$2"
  grep -Eq "^[[:space:]]*${field}:" <<<"${status}" || return 1
  sed -n "s/^[[:space:]]*${field}:[[:space:]]*//p" <<<"${status}" | tail -n 1
}
initial_status="$(replica_status)" || { echo "ERROR: SHOW REPLICA STATUS failed before promotion." >&2; exit 9; }
initial_sql_running="$(status_field Replica_SQL_Running "${initial_status}")" || { echo "ERROR: replication SQL-thread status is missing." >&2; exit 9; }
initial_sql_error="$(status_field Last_SQL_Error "${initial_status}")" || { echo "ERROR: replication Last_SQL_Error status is missing." >&2; exit 9; }
[[ "${initial_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread is not running." >&2; exit 9; }
[[ -z "${initial_sql_error}" ]] || { echo "ERROR: replication has Last_SQL_Error: ${initial_sql_error}" >&2; exit 9; }

# Freeze the received GTID set while leaving the SQL thread running to drain it.
mysql_exec "STOP REPLICA IO_THREAD;"
drain_status="$(replica_status)" || { echo "ERROR: SHOW REPLICA STATUS failed while draining GTIDs." >&2; exit 10; }
drain_sql_running="$(status_field Replica_SQL_Running "${drain_status}")" || { echo "ERROR: replication SQL-thread status is missing while draining." >&2; exit 10; }
drain_sql_error="$(status_field Last_SQL_Error "${drain_status}")" || { echo "ERROR: replication Last_SQL_Error status is missing while draining." >&2; exit 10; }
retrieved_gtid_set="$(status_field Retrieved_Gtid_Set "${drain_status}")" || { echo "ERROR: replication Retrieved_Gtid_Set status is missing." >&2; exit 10; }
[[ "${drain_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread stopped before GTID convergence." >&2; exit 10; }
[[ -z "${drain_sql_error}" ]] || { echo "ERROR: replication has Last_SQL_Error while draining: ${drain_sql_error}" >&2; exit 10; }
gtid_wait_seconds="${GTID_WAIT_TIMEOUT_SECONDS:-60}"
[[ "${gtid_wait_seconds}" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: GTID_WAIT_TIMEOUT_SECONDS must be a positive integer." >&2; exit 10; }
wait_result="$(mysql_exec "SELECT WAIT_FOR_EXECUTED_GTID_SET('${retrieved_gtid_set}', ${gtid_wait_seconds});")" || { echo "ERROR: GTID convergence wait failed." >&2; exit 10; }
[[ "${wait_result}" == "0" ]] || { echo "ERROR: GTID convergence timed out before promotion." >&2; exit 10; }
subset_result="$(mysql_exec "SELECT GTID_SUBSET('${retrieved_gtid_set}', @@GLOBAL.gtid_executed);")" || { echo "ERROR: GTID convergence verification failed." >&2; exit 10; }
[[ "${subset_result}" == "1" ]] || { echo "ERROR: Retrieved_Gtid_Set is not fully applied to @@GLOBAL.gtid_executed." >&2; exit 10; }

# Preserve replication metadata for incident evidence and later replica rebuilding.
mysql_exec "STOP REPLICA; SET GLOBAL super_read_only=OFF; SET GLOBAL read_only=OFF;"
cat > /srv/smart-bamboo-dr/config/role-override.cnf <<'EOF'
[mysqld]
read_only=OFF
super_read_only=OFF
skip_replica_start=ON
EOF
chmod 0640 /srv/smart-bamboo-dr/config/role-override.cnf
"${compose[@]}" --profile failover up -d app geoserver nginx
echo "Standby promoted with SMART_BAMBOO_HUMAN_AUTH_ENABLED=${human_auth_enabled}. Retrieved GTIDs were fully applied; confirm source-side RPO for transactions never received before opening public port 80/443."
