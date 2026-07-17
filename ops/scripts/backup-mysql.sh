#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-/srv/smart-bamboo/config/primary.env}"
backup_dir="${2:-/srv/smart-bamboo/backups}"
set -a
source "${env_file}"
set +a
mkdir -p "${backup_dir}"
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="smart-bamboo-${stamp}.sql.gz"
compose=(docker compose --project-directory "${repo_root}" --env-file "${env_file}" -f "${repo_root}/ops/compose.primary.yml")

"${compose[@]}" exec -T db-primary mysqldump \
  -uroot -p"${MYSQL_ROOT_PASSWORD}" \
  --databases "${MYSQL_DATABASE}" \
  --single-transaction --routines --events --triggers \
  --set-gtid-purged=ON --source-data=2 | gzip -9 > "${backup_dir}/${name}"
(cd "${backup_dir}" && sha256sum "${name}" > "${name}.sha256")
find "${backup_dir}" -type f -name 'smart-bamboo-*.sql.gz*' -mtime +14 -delete
echo "${backup_dir}/${name}"
