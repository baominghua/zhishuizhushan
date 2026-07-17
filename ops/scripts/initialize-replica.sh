#!/usr/bin/env bash
set -Eeuo pipefail

dump_file="${1:?Usage: $0 DUMP.sql.gz [STANDBY_ENV]}"
env_file="${2:-/srv/smart-bamboo-dr/config/standby.env}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ ! -f "${dump_file}" || ! -f "${dump_file}.sha256" ]]; then
  echo "ERROR: dump or checksum file missing." >&2
  exit 1
fi
(cd "$(dirname "${dump_file}")" && sha256sum -c "$(basename "${dump_file}").sha256")
set -a
source "${env_file}"
set +a
if [[ ! "${REPLICATION_USER}" =~ ^[A-Za-z0-9_]+$ ]] || [[ ! "${REPLICATION_PASSWORD}" =~ ^[A-Fa-f0-9]+$ ]]; then
  echo "ERROR: invalid replication credentials format." >&2
  exit 2
fi
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.standby.yml")
"${compose[@]}" up -d db-replica
until "${compose[@]}" exec -T db-replica mysqladmin ping -uroot -p"${MYSQL_ROOT_PASSWORD}" --silent; do sleep 2; done
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "STOP REPLICA;" || true
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "RESET REPLICA ALL;"
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "RESET BINARY LOGS AND GTIDS;"
gzip -dc "${dump_file}" | "${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}"
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='192.168.0.32',
  SOURCE_PORT=3306,
  SOURCE_USER='${REPLICATION_USER}',
  SOURCE_PASSWORD='${REPLICATION_PASSWORD}',
  SOURCE_AUTO_POSITION=1,
  GET_SOURCE_PUBLIC_KEY=1;
START REPLICA;
SQL
sleep 5
"${compose[@]}" exec -T db-replica mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "SHOW REPLICA STATUS\G"
