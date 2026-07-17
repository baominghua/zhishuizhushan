#!/usr/bin/env bash
set -Eeuo pipefail

env_file="${1:-/srv/smart-bamboo/config/backup-upload.env}"
backup_dir="${2:-/srv/smart-bamboo/backups}"
if [[ -f "${env_file}" ]]; then
  set -a
  source "${env_file}"
  set +a
fi

: "${RCLONE_BACKUP_REMOTE:?Set RCLONE_BACKUP_REMOTE in ${env_file}}"
rclone_config="${RCLONE_CONFIG_FILE:-/srv/smart-bamboo/config/rclone.conf}"
[[ -r "${rclone_config}" ]] || { echo "Missing rclone config: ${rclone_config}" >&2; exit 1; }
[[ -d "${backup_dir}" ]] || { echo "Missing backup directory: ${backup_dir}" >&2; exit 1; }

docker run --rm --read-only \
  --mount "type=bind,src=${backup_dir},dst=/data,readonly" \
  --mount "type=bind,src=${rclone_config},dst=/config/rclone/rclone.conf,readonly" \
  rclone/rclone:1.74.3 \
  copy /data "${RCLONE_BACKUP_REMOTE}" \
  --config /config/rclone/rclone.conf \
  --include 'smart-bamboo-*.sql.gz' \
  --include 'smart-bamboo-*.sql.gz.sha256' \
  --checksum --immutable --log-level INFO
