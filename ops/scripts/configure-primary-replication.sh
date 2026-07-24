#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo/config/primary.env}"
set -a
source "${env_file}"
set +a

if [[ ! "${REPLICATION_USER}" =~ ^[A-Za-z0-9_]+$ ]] || [[ ! "${REPLICATION_PASSWORD}" =~ ^[A-Fa-f0-9]+$ ]]; then
  echo "ERROR: invalid replication credentials format." >&2
  exit 1
fi
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.primary.yml")
MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${compose[@]}" exec -T -e MYSQL_PWD db-primary mysql -uroot <<SQL
CREATE USER IF NOT EXISTS '${REPLICATION_USER}'@'192.168.0.104' IDENTIFIED WITH caching_sha2_password BY '${REPLICATION_PASSWORD}';
ALTER USER '${REPLICATION_USER}'@'192.168.0.104' IDENTIFIED WITH caching_sha2_password BY '${REPLICATION_PASSWORD}';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO '${REPLICATION_USER}'@'192.168.0.104';
FLUSH PRIVILEGES;
SHOW MASTER STATUS;
SQL
