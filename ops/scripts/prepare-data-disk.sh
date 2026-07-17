#!/usr/bin/env bash
set -Eeuo pipefail

ROLE="${1:-}"
DEVICE="${DEVICE:-/dev/sdb}"
# Required destructive-operation gate: CONFIRM_FORMAT_EMPTY_DISK="YES"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root." >&2
  exit 1
fi
if [[ "${ROLE}" != "primary" && "${ROLE}" != "standby" ]]; then
  echo "Usage: CONFIRM_FORMAT_EMPTY_DISK=YES $0 primary|standby" >&2
  exit 2
fi
if [[ "${CONFIRM_FORMAT_EMPTY_DISK:-}" != "YES" ]]; then
  echo "ERROR: formatting is locked. Set CONFIRM_FORMAT_EMPTY_DISK=YES only after checking lsblk." >&2
  exit 3
fi
if [[ ! -b "${DEVICE}" ]]; then
  echo "ERROR: ${DEVICE} is not a block device." >&2
  exit 4
fi
if [[ "$(lsblk -dnro TYPE "${DEVICE}")" != "disk" ]]; then
  echo "ERROR: ${DEVICE} is not a whole disk." >&2
  exit 5
fi

size_bytes="$(lsblk -bdnro SIZE "${DEVICE}")"
minimum_bytes=$((900 * 1024 * 1024 * 1024))
if [[ "${ROLE}" == "primary" ]]; then
  minimum_bytes=$((3500 * 1024 * 1024 * 1024))
fi
if (( size_bytes < minimum_bytes )); then
  echo "ERROR: ${DEVICE} is smaller than expected for ${ROLE}." >&2
  exit 6
fi

if lsblk -nrpo TYPE "${DEVICE}" | tail -n +2 | grep -q .; then
  echo "ERROR: ${DEVICE} already has child partitions; refusing to format." >&2
  exit 7
fi
if findmnt -rn -S "${DEVICE}" | grep -q .; then
  echo "ERROR: ${DEVICE} is mounted; refusing to format." >&2
  exit 8
fi
if wipefs -n "${DEVICE}" | grep -q .; then
  echo "ERROR: ${DEVICE} contains a filesystem or partition signature; refusing to format." >&2
  exit 9
fi

mount_point="/srv/smart-bamboo"
label="smart-bamboo-primary"
if [[ "${ROLE}" == "standby" ]]; then
  mount_point="/srv/smart-bamboo-dr"
  label="smart-bamboo-standby"
fi

echo "Creating GPT/XFS on confirmed empty disk ${DEVICE} for ${ROLE}."
parted -s "${DEVICE}" mklabel gpt
parted -s "${DEVICE}" mkpart primary xfs 1MiB 100%
udevadm settle
partition="${DEVICE}1"
if [[ "${DEVICE}" =~ [0-9]$ ]]; then
  partition="${DEVICE}p1"
fi
mkfs.xfs -L "${label}" "${partition}"

uuid="$(blkid -s UUID -o value "${partition}")"
if [[ -z "${uuid}" ]]; then
  echo "ERROR: failed to read XFS UUID." >&2
  exit 10
fi
mkdir -p "${mount_point}"
if ! grep -q "^UUID=${uuid}[[:space:]]" /etc/fstab; then
  printf 'UUID=%s %s xfs defaults,nofail,noatime 0 2\n' "${uuid}" "${mount_point}" >> /etc/fstab
fi
mount "${mount_point}"

if [[ "${ROLE}" == "primary" ]]; then
  mkdir -p "${mount_point}"/{mysql,data/remote-sensing/inbox,geoserver,backups,config,incoming}
  chown -R 999:999 "${mount_point}/mysql"
else
  mkdir -p "${mount_point}"/{mysql-replica,data/remote-sensing/inbox,geoserver,backups,monitoring,config,incoming,app}
  chown -R 999:999 "${mount_point}/mysql-replica"
  cat > "${mount_point}/config/role-override.cnf" <<'EOF'
[mysqld]
read_only=ON
super_read_only=ON
skip_replica_start=ON
EOF
fi
chown -R 1000:1000 "${mount_point}/geoserver"
chmod 0750 "${mount_point}" "${mount_point}/config" "${mount_point}/backups"

echo "UUID=${uuid}"
lsblk -f "${DEVICE}"
df -hT "${mount_point}"
