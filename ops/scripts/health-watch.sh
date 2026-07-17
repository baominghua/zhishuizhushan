#!/usr/bin/env bash
set -Eeuo pipefail

url="${SMART_BAMBOO_PRIMARY_HEALTH_URL:-http://192.168.0.32/api/health}"
log_dir="${SMART_BAMBOO_MONITOR_DIR:-/srv/smart-bamboo-dr/monitoring}"
mkdir -p "${log_dir}"
stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if payload="$(curl -fsS --connect-timeout 3 --max-time 10 "${url}")"; then
  printf '%s status=ok payload=%s\n' "${stamp}" "${payload}" >> "${log_dir}/primary-health.log"
else
  printf '%s status=failed url=%s\n' "${stamp}" "${url}" | tee -a "${log_dir}/primary-health.log" >&2
  exit 1
fi
