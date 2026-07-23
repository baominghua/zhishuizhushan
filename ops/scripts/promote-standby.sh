#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${CONFIRM_PRIMARY_UNAVAILABLE:-}" != "YES" ]]; then
  echo "ERROR: set CONFIRM_PRIMARY_UNAVAILABLE=YES only after confirming the primary cannot write." >&2
  exit 1
fi
if curl -fsS --connect-timeout 2 --max-time 5 http://192.168.0.32/api/health >/dev/null 2>&1; then
  [[ "${CONFIRM_FORCE_SPLIT_BRAIN_RISK:-}" == "YES" ]] || { echo "ERROR: primary still responds. Promotion blocked to prevent split brain." >&2; exit 2; }
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo-dr/config/standby.env}"
env_reader="${repo_root}/ops/scripts/read-protected-env.py"
durable_writer="${repo_root}/ops/scripts/durable-atomic-write.py"
state_file="/srv/smart-bamboo-dr/config/promotion-state"
role_override="/srv/smart-bamboo-dr/config/role-override.cnf"
io_stopped=0

read_env_value() { python3 "${env_reader}" "${env_file}" "$1"; }
durable_write() { python3 "${durable_writer}" "$1" "$2"; }
write_state() {
  local phase="$1"
  case "${phase}" in preflight|draining|commit-intent|database-promoted|services-started|recovery-failed) ;; *)
    echo "ERROR: invalid promotion state: ${phase}" >&2; return 1 ;; esac
  printf 'phase=%s\nrelease_commit=%s\n' "${phase}" "${release_commit}" | durable_write "${state_file}" 0600
}
read_state() {
  local phases commits
  [[ -e "${state_file}" ]] || { printf 'preflight'; return 0; }
  mapfile -t phases < <(sed -n 's/^phase=//p' "${state_file}")
  mapfile -t commits < <(sed -n 's/^release_commit=//p' "${state_file}")
  [[ "${#phases[@]}" == "1" && "${#commits[@]}" == "1" && "${commits[0]}" == "${release_commit}" ]] || {
    echo "ERROR: promotion state is missing, duplicated, or belongs to another release." >&2; return 1; }
  case "${phases[0]}" in preflight|draining|commit-intent|database-promoted|services-started|recovery-failed) printf '%s' "${phases[0]}" ;; *)
    echo "ERROR: unsupported promotion state: ${phases[0]}" >&2; return 1 ;; esac
}

human_auth_enabled="$(read_env_value SMART_BAMBOO_HUMAN_AUTH_ENABLED)"
tls_enabled="$(read_env_value SMART_BAMBOO_TLS_ENABLED)"
release_commit="$(read_env_value SMART_BAMBOO_RELEASE_COMMIT)"
release_tag="$(read_env_value SMART_BAMBOO_RELEASE_TAG)"
remote_tokens="$(read_env_value REMOTE_SENSING_API_TOKENS)"
break_glass_token="$(read_env_value SMART_BAMBOO_BREAK_GLASS_TOKEN)"
mysql_root_password="$(read_env_value MYSQL_ROOT_PASSWORD)"
tls_cert_path="$(read_env_value SMART_BAMBOO_TLS_CERT_PATH)"
tls_key_path="$(read_env_value SMART_BAMBOO_TLS_KEY_PATH)"

compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.standby.yml")
for required_dir in /srv/smart-bamboo-dr/config /srv/smart-bamboo-dr/data /srv/smart-bamboo-dr/mysql-replica /srv/smart-bamboo-dr/geoserver; do
  [[ -d "${required_dir}" ]] || { echo "ERROR: required standby directory is missing: ${required_dir}" >&2; exit 3; }
done
[[ "${release_commit}" =~ ^[0-9a-fA-F]{40}$ && "${release_tag}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "ERROR: standby release commit/tag is invalid." >&2; exit 3; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${release_commit}" ]] || { echo "ERROR: checked-out commit does not match SMART_BAMBOO_RELEASE_COMMIT." >&2; exit 3; }
[[ -n "${remote_tokens}" && -n "${break_glass_token}" && -n "${mysql_root_password}" ]] || { echo "ERROR: standby token or MySQL root-password configuration is incomplete." >&2; exit 3; }
case "${human_auth_enabled}" in
  1) [[ "${tls_enabled}" == "1" ]] || { echo "ERROR: standby human authentication requires SMART_BAMBOO_TLS_ENABLED=1." >&2; exit 4; }
     [[ "${CONFIRM_HUMAN_AUTH_ENABLED:-}" == "1" ]] || { echo "ERROR: set CONFIRM_HUMAN_AUTH_ENABLED=1 to promote the synchronized password-authentication state." >&2; exit 5; } ;;
  0) ;;
  *) echo "ERROR: SMART_BAMBOO_HUMAN_AUTH_ENABLED must be 0 or 1." >&2; exit 6 ;;
esac
case "${tls_enabled}" in
  1)
    [[ -d /srv/smart-bamboo-dr/tls ]] || { echo "ERROR: required standby TLS directory is missing." >&2; exit 7; }
    [[ "${tls_cert_path}" == /srv/smart-bamboo-dr/tls/* && -f "${tls_cert_path}" ]] || { echo "ERROR: standby TLS certificate is missing or outside /srv/smart-bamboo-dr/tls." >&2; exit 7; }
    [[ "${tls_key_path}" == /srv/smart-bamboo-dr/tls/* && -f "${tls_key_path}" ]] || { echo "ERROR: standby TLS private key is missing or outside /srv/smart-bamboo-dr/tls." >&2; exit 7; }
    openssl x509 -in "${tls_cert_path}" -noout -checkend 2592000
    openssl pkey -in "${tls_key_path}" -noout
    cert_public_key="$(openssl x509 -in "${tls_cert_path}" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')"
    key_public_key="$(openssl pkey -in "${tls_key_path}" -pubout -outform DER | sha256sum | awk '{print $1}')"
    [[ -n "${cert_public_key}" && "${cert_public_key}" == "${key_public_key}" ]] || { echo "ERROR: standby TLS certificate and private key do not match." >&2; exit 7; }
    compose+=( -f "${repo_root}/ops/compose.tls.yml" ) ;;
  0) ;;
  *) echo "ERROR: SMART_BAMBOO_TLS_ENABLED must be 0 or 1." >&2; exit 8 ;;
esac
"${compose[@]}" config --quiet
for image in "smart-bamboo-app:${release_tag}" "docker.osgeo.org/geoserver:2.25.7" "nginx:1.30.4-alpine"; do docker image inspect "${image}" >/dev/null; done

mysql_exec() { "${compose[@]}" exec -T db-replica mysql -N -B -uroot -p"${mysql_root_password}" -e "$1"; }
replica_status() { "${compose[@]}" exec -T db-replica mysql -uroot -p"${mysql_root_password}" -e "SHOW REPLICA STATUS\\G"; }
status_field() { python3 "${repo_root}/ops/scripts/read-replica-status.py" "$1" <<<"$2"; }
database_role() { mysql_exec "SELECT CONCAT(@@GLOBAL.read_only, ',', @@GLOBAL.super_read_only);"; }
install_role_override() {
  printf '[mysqld]\nread_only=OFF\nsuper_read_only=OFF\nskip_replica_start=ON\n' | durable_write "${role_override}" 0640
}
io_restart_is_healthy() {
  local status io sql sql_error
  status="$(replica_status)" || return 1
  io="$(status_field Replica_IO_Running "${status}")" || return 1
  sql="$(status_field Replica_SQL_Running "${status}")" || return 1
  sql_error="$(status_field Last_SQL_Error "${status}")" || return 1
  [[ ( "${io}" == "Yes" || "${io}" == "Connecting" ) && "${sql}" == "Yes" && -z "${sql_error}" ]]
}
resume_io_or_fail() {
  if mysql_exec "START REPLICA IO_THREAD;" >/dev/null && io_restart_is_healthy; then
    write_state preflight
    echo "RECOVERY: REPLICA IO_THREAD is ${io:-healthy}; status verification passed and preflight may restart." >&2
    return 0
  fi
  write_state recovery-failed || true
  echo "ERROR: REPLICA IO_THREAD did not recover to Yes/Connecting with a healthy SQL thread; state is recovery-failed." >&2
  return 1
}
restore_io_on_failure() {
  local status=$?
  trap - EXIT
  if [[ "${io_stopped}" == "1" ]]; then
    resume_io_or_fail || true
  fi
  exit "${status}"
}
ensure_database_promoted() {
  case "$(database_role)" in
    0,0) ;;
    1,1) mysql_exec "STOP REPLICA; SET GLOBAL super_read_only=OFF; SET GLOBAL read_only=OFF;" ;;
    *) echo "ERROR: promotion marker has an unsafe, indeterminate database read-only state." >&2; return 1 ;;
  esac
  install_role_override
  write_state database-promoted
}
finish_services() {
  "${compose[@]}" --profile failover up -d app geoserver nginx
  write_state services-started
  echo "Standby promoted with SMART_BAMBOO_HUMAN_AUTH_ENABLED=${human_auth_enabled}. Retrieved GTIDs were fully applied; confirm source-side RPO for transactions never received before opening public port 80/443."
}

phase="$(read_state)"
case "${phase}" in
  services-started)
    [[ "$(database_role)" == "0,0" ]] || { echo "ERROR: services-started marker conflicts with database read-only state." >&2; exit 11; }
    install_role_override
    finish_services
    ;;
  database-promoted)
    ensure_database_promoted
    finish_services
    ;;
  commit-intent)
    ensure_database_promoted
    finish_services
    ;;
  draining|recovery-failed)
    case "$(database_role)" in
      1,1) resume_io_or_fail || exit 11 ;;
      0,0) install_role_override; write_state database-promoted; finish_services; exit 0 ;;
      *) echo "ERROR: ${phase} marker has an unsafe, indeterminate database read-only state." >&2; exit 11 ;;
    esac
    ;&
  preflight)
    write_state preflight
    initial_status="$(replica_status)" || { echo "ERROR: SHOW REPLICA STATUS failed before promotion." >&2; exit 9; }
    initial_sql_running="$(status_field Replica_SQL_Running "${initial_status}")" || { echo "ERROR: replication SQL-thread status is missing or ambiguous." >&2; exit 9; }
    initial_sql_error="$(status_field Last_SQL_Error "${initial_status}")" || { echo "ERROR: replication Last_SQL_Error status is missing or ambiguous." >&2; exit 9; }
    [[ "${initial_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread is not running." >&2; exit 9; }
    [[ -z "${initial_sql_error}" ]] || { echo "ERROR: replication has Last_SQL_Error: ${initial_sql_error}" >&2; exit 9; }
    mysql_exec "STOP REPLICA IO_THREAD;"
    io_stopped=1
    trap restore_io_on_failure EXIT
    write_state draining
    drain_status="$(replica_status)" || { echo "ERROR: SHOW REPLICA STATUS failed while draining GTIDs." >&2; exit 10; }
    drain_sql_running="$(status_field Replica_SQL_Running "${drain_status}")" || { echo "ERROR: replication SQL-thread status is missing or ambiguous while draining." >&2; exit 10; }
    drain_sql_error="$(status_field Last_SQL_Error "${drain_status}")" || { echo "ERROR: replication Last_SQL_Error status is missing or ambiguous while draining." >&2; exit 10; }
    retrieved_gtid_set="$(status_field Retrieved_Gtid_Set "${drain_status}")" || { echo "ERROR: replication Retrieved_Gtid_Set status is missing or ambiguous." >&2; exit 10; }
    [[ "${drain_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread stopped before GTID convergence." >&2; exit 10; }
    [[ -z "${drain_sql_error}" ]] || { echo "ERROR: replication has Last_SQL_Error while draining: ${drain_sql_error}" >&2; exit 10; }
    gtid_wait_seconds="${GTID_WAIT_TIMEOUT_SECONDS:-60}"
    [[ "${gtid_wait_seconds}" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: GTID_WAIT_TIMEOUT_SECONDS must be a positive integer." >&2; exit 10; }
    wait_result="$(mysql_exec "SELECT WAIT_FOR_EXECUTED_GTID_SET('${retrieved_gtid_set}', ${gtid_wait_seconds});")" || { echo "ERROR: GTID convergence wait failed." >&2; exit 10; }
    [[ "${wait_result}" == "0" ]] || { echo "ERROR: GTID convergence timed out before promotion." >&2; exit 10; }
    subset_result="$(mysql_exec "SELECT GTID_SUBSET('${retrieved_gtid_set}', @@GLOBAL.gtid_executed);")" || { echo "ERROR: GTID convergence verification failed." >&2; exit 10; }
    [[ "${subset_result}" == "1" ]] || { echo "ERROR: Retrieved_Gtid_Set is not fully applied to @@GLOBAL.gtid_executed." >&2; exit 10; }
    write_state commit-intent
    trap - EXIT
    ensure_database_promoted
    finish_services
    ;;
esac
