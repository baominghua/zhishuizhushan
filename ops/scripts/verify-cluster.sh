#!/usr/bin/env bash
set -Eeuo pipefail

role="${1:?Usage: $0 primary|standby [ENV_FILE]}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${role}" == "primary" ]]; then
  env_file="${2:-/srv/smart-bamboo/config/primary.env}"
  compose_file="${repo_root}/ops/compose.primary.yml"
  db_service="db-primary"
else
  env_file="${2:-/srv/smart-bamboo-dr/config/standby.env}"
  compose_file="${repo_root}/ops/compose.standby.yml"
  db_service="db-replica"
fi
set -a
source "${env_file}"
set +a
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${compose_file}")
"${compose[@]}" ps

if [[ "${role}" == "primary" ]]; then
  curl -fsS http://127.0.0.1:8010/api/health | grep -q '"status":"ready"'
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
