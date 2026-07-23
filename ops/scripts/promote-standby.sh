#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run standby promotion as root." >&2
  exit 1
fi
if [[ "${CONFIRM_PRIMARY_UNAVAILABLE:-}" != "YES" ]]; then
  echo "ERROR: set CONFIRM_PRIMARY_UNAVAILABLE=YES only after the provider has stopped or isolated the primary." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo-dr/config/standby.env}"
env_reader="${repo_root}/ops/scripts/read-protected-env.py"
durable_writer="${repo_root}/ops/scripts/durable-atomic-write.py"
fence_proof_verifier="${repo_root}/ops/scripts/verify-fence-proof.py"
break_glass_verifier="${repo_root}/ops/scripts/verify-break-glass-env.py"
state_file="/srv/smart-bamboo-dr/config/promotion-state"
role_override="/srv/smart-bamboo-dr/config/role-override.cnf"
fence_proof_file="/srv/smart-bamboo-dr/config/fence-proof.json"
rpo_evidence_file="/srv/smart-bamboo-dr/config/rpo-evidence"
fence_adapter="${SMART_BAMBOO_FENCE_ADAPTER:-}"
primary_instance_id="${SMART_BAMBOO_PRIMARY_INSTANCE_ID:-}"
fence_adapter_snapshot=""
io_stopped=0

read_env_value() { python3 "${env_reader}" "${env_file}" "$1"; }
durable_write() { python3 "${durable_writer}" "$1" "$2"; }
write_state() {
  local phase="$1"
  case "${phase}" in preflight|draining|rpo-review|commit-intent|database-promoted|services-started|recovery-failed) ;; *)
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
  case "${phases[0]}" in preflight|draining|rpo-review|commit-intent|database-promoted|services-started|recovery-failed) printf '%s' "${phases[0]}" ;; *)
    echo "ERROR: unsupported promotion state: ${phases[0]}" >&2; return 1 ;; esac
}

human_auth_enabled="$(read_env_value SMART_BAMBOO_HUMAN_AUTH_ENABLED)"
tls_enabled="$(read_env_value SMART_BAMBOO_TLS_ENABLED)"
release_commit="$(read_env_value SMART_BAMBOO_RELEASE_COMMIT)"
release_tag="$(read_env_value SMART_BAMBOO_RELEASE_TAG)"
mysql_root_password="$(read_env_value MYSQL_ROOT_PASSWORD)"
tls_cert_path="$(read_env_value SMART_BAMBOO_TLS_CERT_PATH)"
tls_key_path="$(read_env_value SMART_BAMBOO_TLS_KEY_PATH)"

compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.standby.yml")
for required_dir in /srv/smart-bamboo-dr/config /srv/smart-bamboo-dr/data /srv/smart-bamboo-dr/mysql-replica /srv/smart-bamboo-dr/geoserver; do
  [[ -d "${required_dir}" ]] || { echo "ERROR: required standby directory is missing: ${required_dir}" >&2; exit 3; }
done
[[ "${release_commit}" =~ ^[0-9a-fA-F]{40}$ && "${release_tag}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "ERROR: standby release commit/tag is invalid." >&2; exit 3; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${release_commit}" ]] || { echo "ERROR: checked-out commit does not match SMART_BAMBOO_RELEASE_COMMIT." >&2; exit 3; }
[[ -n "${mysql_root_password}" ]] || { echo "ERROR: standby MySQL root-password configuration is incomplete." >&2; exit 3; }
python3 "${break_glass_verifier}" "${env_file}"
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

mysql_exec() {
  local query="$1"
  printf '%s\n' "${mysql_root_password}" |
    "${compose[@]}" exec -T db-replica sh -ceu '
      IFS= read -r MYSQL_PWD
      export MYSQL_PWD
      exec mysql -N -B -uroot -e "$1"
    ' sh "${query}"
}
replica_status() {
  printf '%s\n' "${mysql_root_password}" |
    "${compose[@]}" exec -T db-replica sh -ceu '
      IFS= read -r MYSQL_PWD
      export MYSQL_PWD
      exec mysql -uroot -e "SHOW REPLICA STATUS\\G"
    '
}
status_field() { python3 "${repo_root}/ops/scripts/read-replica-status.py" "$1" <<<"$2"; }
database_role() { mysql_exec "SELECT CONCAT(@@GLOBAL.read_only, ',', @@GLOBAL.super_read_only);"; }
validate_fence_adapter() {
  [[ -n "${fence_adapter}" ]] || { echo "ERROR: SMART_BAMBOO_FENCE_ADAPTER is required; promotion has no safe default." >&2; return 1; }
  [[ "${fence_adapter}" == /* && -f "${fence_adapter}" && ! -L "${fence_adapter}" && -x "${fence_adapter}" ]] || {
    echo "ERROR: fence adapter must be an absolute executable regular file, not a symlink." >&2
    return 1
  }
  command -v getfacl >/dev/null || {
    echo "ERROR: getfacl is required to validate fence adapter ACLs." >&2
    return 1
  }
  local resolved current owner mode
  resolved="$(realpath -e -- "${fence_adapter}")"
  [[ "${resolved}" == "${fence_adapter}" ]] || {
    echo "ERROR: fence adapter path must be canonical and contain no symlink component." >&2
    return 1
  }
  current="${fence_adapter}"
  while :; do
    read -r owner mode < <(stat -c '%u %a' -- "${current}")
    [[ "${owner}" == "0" ]] || {
      echo "ERROR: fence adapter must be owned by root, including every parent path: ${current}" >&2
      return 1
    }
    (( (8#${mode: -3} & 8#022) == 0 )) || {
      echo "ERROR: fence adapter parent path and file must not be group/world writable: ${current}" >&2
      return 1
    }
    if getfacl -cp -- "${current}" | grep -Eq '^(default:|user:[^:]+:|group:[^:]+:)'; then
      echo "ERROR: fence adapter parent path and file must not grant named/default ACL access: ${current}" >&2
      return 1
    fi
    [[ "${current}" == "/" ]] && break
    current="$(dirname -- "${current}")"
  done
}
run_fence_adapter() {
  validate_fence_adapter
  [[ -n "${primary_instance_id}" ]] || {
    echo "ERROR: SMART_BAMBOO_PRIMARY_INSTANCE_ID is required for provider fencing." >&2
    return 1
  }
  local nonce proof verification
  fence_adapter_snapshot="$(mktemp /root/.smart-bamboo-fence-adapter.XXXXXX)"
  install -o root -g root -m 0700 -- "${fence_adapter}" "${fence_adapter_snapshot}"
  sync -f "${fence_adapter_snapshot}"
  nonce="$(openssl rand -hex 32)"
  proof="$("${fence_adapter_snapshot}" --instance-id "${primary_instance_id}" --nonce "${nonce}")" || {
    rm -f -- "${fence_adapter_snapshot}"
    fence_adapter_snapshot=""
    echo "ERROR: provider-backed fence adapter failed." >&2
    return 1
  }
  rm -f -- "${fence_adapter_snapshot}"
  fence_adapter_snapshot=""
  verification="$(
    printf '%s' "${proof}" |
      python3 "${fence_proof_verifier}" \
        --expected-instance "${primary_instance_id}" \
        --expected-nonce "${nonce}"
  )"
  [[ "${verification}" == "FENCE_PROOF_VERIFIED" ]] || {
    echo "ERROR: provider fencing did not return an explicit verified proof." >&2
    return 1
  }
  printf '%s\n' "${proof}" | durable_write "${fence_proof_file}" 0600
  echo "FENCE_PROOF_VERIFIED"
}
verify_runtime_auth_config() {
  local local_digest replicated runtime_digest runtime_commit
  local_digest="$(
    cd "${repo_root}"
    python3 -m server.modules.auth_config --env-file "${env_file}"
  )"
  replicated="$(
    mysql_exec \
      "SELECT CONCAT(config_digest, '|', COALESCE(release_commit, '')) FROM platform_runtime_config WHERE config_key = 'authentication';"
  )"
  IFS='|' read -r runtime_digest runtime_commit <<<"${replicated}"
  [[ "${local_digest}" =~ ^[a-f0-9]{64}$ &&
     "${runtime_digest}" == "${local_digest}" &&
     "${runtime_commit}" == "${release_commit}" ]] || {
    echo "ERROR: standby authentication environment does not match the replicated primary runtime digest/commit." >&2
    return 1
  }
  echo "AUTH_CONFIG_DIGEST_VERIFIED"
}
write_rpo_evidence() {
  local retrieved_gtid_set="$1"
  local executed_gtid_set="$2"
  local io_state="$3"
  local io_error="$4"
  local sql_state="$5"
  local fence_hash io_error_hash
  fence_hash="$(sha256sum "${fence_proof_file}" | awk '{print $1}')"
  io_error_hash="$(printf '%s' "${io_error}" | sha256sum | awk '{print $1}')"
  printf \
    'release_commit=%s\nprimary_instance_id=%s\nretrieved_gtid_set=%s\nexecuted_gtid_set=%s\nio_state=%s\nio_error_sha256=%s\nsql_state=%s\nfence_proof_sha256=%s\ncaptured_at=%s\n' \
    "${release_commit}" \
    "${primary_instance_id}" \
    "${retrieved_gtid_set}" \
    "${executed_gtid_set}" \
    "${io_state}" \
    "${io_error_hash}" \
    "${sql_state}" \
    "${fence_hash}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" |
    durable_write "${rpo_evidence_file}" 0600
  sha256sum "${rpo_evidence_file}" | awk '{print $1}'
}
evidence_value() {
  local key="$1"
  local values
  mapfile -t values < <(sed -n "s/^${key}=//p" "${rpo_evidence_file}")
  [[ "${#values[@]}" == "1" ]] || {
    echo "ERROR: RPO evidence field is missing or duplicated: ${key}" >&2
    return 1
  }
  printf '%s' "${values[0]}"
}
require_source_rpo_acceptance() {
  [[ "${CONFIRM_SOURCE_RPO_ACCEPTED:-}" == "YES" ]] || {
    echo "ERROR: set CONFIRM_SOURCE_RPO_ACCEPTED=YES only after reviewing the final RPO evidence." >&2
    return 1
  }
  local expected_digest actual_digest status current_retrieved current_executed
  local evidence_retrieved evidence_executed evidence_commit evidence_instance
  [[ -f "${rpo_evidence_file}" && ! -L "${rpo_evidence_file}" ]] || {
    echo "ERROR: final RPO evidence is missing or unsafe." >&2
    return 1
  }
  expected_digest="${CONFIRM_SOURCE_RPO_EVIDENCE_SHA256:-}"
  actual_digest="$(sha256sum "${rpo_evidence_file}" | awk '{print $1}')"
  [[ "${expected_digest}" =~ ^[a-f0-9]{64}$ && "${expected_digest}" == "${actual_digest}" ]] || {
    echo "ERROR: CONFIRM_SOURCE_RPO_EVIDENCE_SHA256 does not match the final RPO evidence." >&2
    return 1
  }
  evidence_commit="$(evidence_value release_commit)"
  evidence_instance="$(evidence_value primary_instance_id)"
  evidence_retrieved="$(evidence_value retrieved_gtid_set)"
  evidence_executed="$(evidence_value executed_gtid_set)"
  [[ "${evidence_commit}" == "${release_commit}" &&
     "${evidence_instance}" == "${primary_instance_id}" ]] || {
    echo "ERROR: RPO evidence belongs to a different release or primary instance." >&2
    return 1
  }
  status="$(replica_status)"
  current_retrieved="$(status_field Retrieved_Gtid_Set "${status}")"
  current_executed="$(mysql_exec "SELECT @@GLOBAL.gtid_executed;")"
  [[ "${current_retrieved}" == "${evidence_retrieved}" &&
     "${current_executed}" == "${evidence_executed}" ]] || {
    echo "ERROR: replica GTID state changed after RPO evidence capture." >&2
    return 1
  }
  echo "RPO_EVIDENCE_VERIFIED"
}
install_role_override() {
  printf '[mysqld]\nread_only=OFF\nsuper_read_only=OFF\nskip_replica_start=ON\n' | durable_write "${role_override}" 0644
}
io_restart_is_healthy() {
  local status io sql io_error sql_error auto_position
  status="$(replica_status)" || return 1
  io="$(status_field Replica_IO_Running "${status}")" || return 1
  sql="$(status_field Replica_SQL_Running "${status}")" || return 1
  io_error="$(status_field Last_IO_Error "${status}")" || return 1
  sql_error="$(status_field Last_SQL_Error "${status}")" || return 1
  auto_position="$(status_field Auto_Position "${status}")" || return 1
  [[ ( "${io}" == "Yes" || "${io}" == "Connecting" ) &&
     "${sql}" == "Yes" && -z "${io_error}" && -z "${sql_error}" &&
     "${auto_position}" == "1" ]]
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
  echo "Standby promoted with SMART_BAMBOO_HUMAN_AUTH_ENABLED=${human_auth_enabled}. Provider fencing was verified and source-side RPO was explicitly accepted before opening public port 80/443."
}

run_fence_adapter
verify_runtime_auth_config

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
  rpo-review)
    require_source_rpo_acceptance
    write_state commit-intent
    trap - EXIT
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
    initial_io_running="$(status_field Replica_IO_Running "${initial_status}")" || { echo "ERROR: replication IO-thread status is missing or ambiguous." >&2; exit 9; }
    initial_sql_running="$(status_field Replica_SQL_Running "${initial_status}")" || { echo "ERROR: replication SQL-thread status is missing or ambiguous." >&2; exit 9; }
    initial_io_error="$(status_field Last_IO_Error "${initial_status}")" || { echo "ERROR: replication Last_IO_Error status is missing or ambiguous." >&2; exit 9; }
    initial_sql_error="$(status_field Last_SQL_Error "${initial_status}")" || { echo "ERROR: replication Last_SQL_Error status is missing or ambiguous." >&2; exit 9; }
    initial_auto_position="$(status_field Auto_Position "${initial_status}")" || { echo "ERROR: replication Auto_Position status is missing or ambiguous." >&2; exit 9; }
    [[ "${initial_io_running}" == "Yes" ||
       "${initial_io_running}" == "Connecting" ||
       "${initial_io_running}" == "No" ]] || {
      echo "ERROR: replication IO thread has an unsupported state: ${initial_io_running}" >&2
      exit 9
    }
    [[ "${initial_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread is not running." >&2; exit 9; }
    [[ -z "${initial_sql_error}" ]] || { echo "ERROR: replication has Last_SQL_Error: ${initial_sql_error}" >&2; exit 9; }
    [[ "$initial_auto_position" == "1" ]] || { echo "ERROR: replication must use GTID Auto_Position=1 before promotion." >&2; exit 9; }
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

    final_status="$(replica_status)" || { echo "ERROR: SHOW REPLICA STATUS failed after GTID convergence." >&2; exit 10; }
    final_io_running="$(status_field Replica_IO_Running "${final_status}")" || { echo "ERROR: final replication IO-thread status is missing or ambiguous." >&2; exit 10; }
    final_io_error="$(status_field Last_IO_Error "${final_status}")" || { echo "ERROR: final replication Last_IO_Error status is missing or ambiguous." >&2; exit 10; }
    final_sql_running="$(status_field Replica_SQL_Running "${final_status}")" || { echo "ERROR: final replication SQL-thread status is missing or ambiguous." >&2; exit 10; }
    final_sql_error="$(status_field Last_SQL_Error "${final_status}")" || { echo "ERROR: final replication Last_SQL_Error status is missing or ambiguous." >&2; exit 10; }
    final_auto_position="$(status_field Auto_Position "${final_status}")" || { echo "ERROR: final replication Auto_Position status is missing or ambiguous." >&2; exit 10; }
    final_retrieved_gtid_set="$(status_field Retrieved_Gtid_Set "${final_status}")" || { echo "ERROR: final replication Retrieved_Gtid_Set status is missing or ambiguous." >&2; exit 10; }
    final_executed_gtid_set="$(mysql_exec "SELECT @@GLOBAL.gtid_executed;")" || { echo "ERROR: final executed GTID query failed." >&2; exit 10; }

    [[ "${final_sql_running}" == "Yes" ]] || { echo "ERROR: replication SQL thread stopped after GTID convergence." >&2; exit 10; }
    [[ -z "${final_sql_error}" ]] || { echo "ERROR: replication has a final Last_SQL_Error: ${final_sql_error}" >&2; exit 10; }
    [[ "${final_auto_position}" == "1" ]] || { echo "ERROR: final replica status no longer uses GTID Auto_Position=1." >&2; exit 10; }
    [[ "${final_retrieved_gtid_set}" == "${retrieved_gtid_set}" ]] || { echo "ERROR: Retrieved_Gtid_Set changed after the IO thread was stopped." >&2; exit 10; }

    rpo_evidence_digest="$(
      write_rpo_evidence \
        "${final_retrieved_gtid_set}" \
        "${final_executed_gtid_set}" \
        "${final_io_running}" \
        "${final_io_error:-${initial_io_error}}" \
        "${final_sql_running}"
    )"
    [[ "${rpo_evidence_digest}" =~ ^[a-f0-9]{64}$ ]] || { echo "ERROR: final RPO evidence digest is invalid." >&2; exit 10; }
    write_state rpo-review
    trap - EXIT
    io_stopped=0
    printf 'RPO_EVIDENCE_READY_SHA256=%s\n' "${rpo_evidence_digest}"
    printf '%s\n' \
      "Review ${rpo_evidence_file}, then rerun with CONFIRM_SOURCE_RPO_ACCEPTED=YES and CONFIRM_SOURCE_RPO_EVIDENCE_SHA256=${rpo_evidence_digest}."
    exit 12
    ;;
esac
