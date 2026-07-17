#!/usr/bin/env bash
set -Eeuo pipefail

role="${1:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ "${EUID}" -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

case "${role}" in
  primary)
    install -m 0644 "${repo_root}/ops/systemd/smart-bamboo-backup.service" /etc/systemd/system/
    install -m 0644 "${repo_root}/ops/systemd/smart-bamboo-backup.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now smart-bamboo-backup.timer
    ;;
  standby)
    install -m 0644 "${repo_root}/ops/systemd/smart-bamboo-health.service" /etc/systemd/system/
    install -m 0644 "${repo_root}/ops/systemd/smart-bamboo-health.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now smart-bamboo-health.timer
    ;;
  *)
    echo "Usage: $0 primary|standby" >&2
    exit 2
    ;;
esac

systemctl list-timers --all 'smart-bamboo-*'
