#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root." >&2
  exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != "bclinux" ]] || [[ "${PRETTY_NAME:-}" != *"BigCloud Enterprise Linux"* ]]; then
  echo "ERROR: this installer is only for BigCloud Enterprise Linux." >&2
  exit 2
fi

dnf install -y dnf-plugins-core git curl ca-certificates openssl xfsprogs parted gzip tar
curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo \
  -o /etc/yum.repos.d/docker-ce.repo
# BC-Linux 21.10U4 is EL8-compatible; Docker's repository does not publish a BC-Linux release path.
sed -i 's/\$releasever/8/g' /etc/yum.repos.d/docker-ce.repo
dnf install -y \
  docker-ce-29.6.2-1.el8 \
  docker-ce-cli-29.6.2-1.el8 \
  containerd.io-2.2.6-1.el8 \
  docker-buildx-plugin-0.35.0-1.el8 \
  docker-compose-plugin-5.3.1-1.el8
systemctl enable --now docker

docker version
docker compose version
