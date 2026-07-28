#!/usr/bin/env bash
set -Eeuo pipefail

dump_file="${1:?Usage: $0 DUMP.sql.gz [STANDBY_ENV]}"
env_file="${2:-/srv/smart-bamboo-dr/config/standby.env}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
role_override="/srv/smart-bamboo-dr/config/role-override.cnf"
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
mysql_exec() {
  local query="$1"
  "${compose[@]}" exec -T db-replica sh -ceu '
    export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
    exec mysql -uroot -e "$1"
  ' sh "${query}"
}
install_role_override() {
  local temporary
  temporary="$(mktemp "${role_override}.tmp.XXXXXX")"
  cat >"${temporary}"
  chmod 644 "${temporary}"
  chown root:root "${temporary}"
  mv -f "${temporary}" "${role_override}"
}
install_bootstrap_override() {
  install_role_override <<'EOF'
[mysqld]
read_only=OFF
super_read_only=OFF
skip_replica_start=ON
EOF
}
install_read_only_override() {
  install_role_override <<'EOF'
[mysqld]
read_only=ON
super_read_only=ON
skip_replica_start=OFF
EOF
}
restore_read_only() {
  local status=$?
  trap - EXIT
  if ! install_read_only_override; then
    status=1
  fi
  if (( status != 0 )); then
    mysql_exec "SET @@GLOBAL.read_only=ON; SET @@GLOBAL.super_read_only=ON;" ||
      true
    "${compose[@]}" stop db-replica || true
  fi
  exit "${status}"
}

install_bootstrap_override
trap restore_read_only EXIT
"${compose[@]}" up -d db-replica
ready=0
for _attempt in $(seq 1 90); do
  if "${compose[@]}" exec -T db-replica sh -ceu '
    export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
    exec mysql -uroot -N -B -e "SELECT 1;"
  '; then
    ready=1
    break
  fi
  sleep 2
done
if (( ready != 1 )); then
  echo "ERROR: replica MySQL did not accept authenticated root queries." >&2
  exit 3
fi
mysql_exec "STOP REPLICA;" || true
mysql_exec "RESET REPLICA ALL;"
mysql_exec "RESET BINARY LOGS AND GTIDS;"
gzip -dc "${dump_file}" | "${compose[@]}" exec -T db-replica sh -ceu '
  export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
  exec mysql -uroot
'
cat <<SQL | "${compose[@]}" exec -T db-replica sh -ceu '
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
exec mysql -uroot
'
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='192.168.0.32',
  SOURCE_PORT=3306,
  SOURCE_USER='${REPLICATION_USER}',
  SOURCE_PASSWORD='${REPLICATION_PASSWORD}',
  SOURCE_AUTO_POSITION=1,
  GET_SOURCE_PUBLIC_KEY=1;
START REPLICA;
SET GLOBAL read_only=ON;
SET GLOBAL super_read_only=ON;
SQL
sleep 5
mysql_exec "SELECT @@GLOBAL.read_only, @@GLOBAL.super_read_only;"
mysql_exec "SHOW REPLICA STATUS\\G"
