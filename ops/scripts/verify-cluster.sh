#!/usr/bin/env bash
set -Eeuo pipefail

role="${1:?Usage: $0 primary|standby [ENV_FILE] [--allow-human-auth-pending]}"
shift
if [[ "${role}" != "primary" && "${role}" != "standby" ]]; then
  echo "ERROR: role must be primary or standby." >&2
  exit 64
fi
env_override=""
allow_human_auth_pending=0
for argument in "$@"; do
  case "${argument}" in
    --allow-human-auth-pending) allow_human_auth_pending=1 ;;
    *)
      if [[ -z "${env_override}" ]]; then
        env_override="${argument}"
      else
        echo "ERROR: unknown argument: ${argument}" >&2
        exit 64
      fi
      ;;
  esac
done
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${role}" == "primary" ]]; then
  env_file="${env_override:-/srv/smart-bamboo/config/primary.env}"
  compose_file="${repo_root}/ops/compose.primary.yml"
  db_service="db-primary"
else
  env_file="${env_override:-/srv/smart-bamboo-dr/config/standby.env}"
  compose_file="${repo_root}/ops/compose.standby.yml"
  db_service="db-replica"
fi
set -a
source "${env_file}"
set +a
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${compose_file}")
"${compose[@]}" ps

if [[ "${role}" == "primary" ]]; then
  health_payload="$(curl -fsS http://127.0.0.1:8010/api/health)"
  if [[ "${allow_human_auth_pending}" == "1" ]]; then
    printf '%s' "${health_payload}" | "${compose[@]}" exec -T app python -c '
import json
import sys
readiness = json.load(sys.stdin)["deployment"]["readiness"]
warning_keys = {item["key"] for item in readiness["warnings"]}
if readiness["status"] != "warning" or readiness["blockingIssues"] or warning_keys != {"human_auth_pending_https"}:
    raise SystemExit("expected only the human_auth_pending_https rollout warning")
'
  elif [[ "${allow_human_auth_pending}" == "0" ]]; then
    printf '%s' "${health_payload}" | "${compose[@]}" exec -T app python -c '
import json
import sys
readiness = json.load(sys.stdin)["deployment"]["readiness"]
if readiness["status"] != "ready" or readiness["blockingIssues"] or readiness["warnings"]:
    raise SystemExit("expected ready deployment with no warnings")
'
  fi
  "${compose[@]}" exec -T "${db_service}" mysql -Nse "SELECT @@server_id, @@gtid_mode, @@binlog_format;" -uroot -p"${MYSQL_ROOT_PASSWORD}"
  exit 0
fi

status="$("${compose[@]}" exec -T "${db_service}" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "SHOW REPLICA STATUS\G")"
grep -q "Replica_IO_Running: Yes" <<<"${status}"
grep -q "Replica_SQL_Running: Yes" <<<"${status}"
read_only="$("${compose[@]}" exec -T "${db_service}" mysql -Nse "SELECT @@read_only, @@super_read_only;" -uroot -p"${MYSQL_ROOT_PASSWORD}")"
[[ "${read_only}" == $'1\t1' ]]
echo "${status}" | grep -E "Replica_(IO|SQL)_Running|Seconds_Behind_Source|Last_(IO|SQL)_Error"
echo "super_read_only=${read_only}"
