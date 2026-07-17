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

docker_repo_args=()
if [[ -f /etc/yum.repos.d/docker-ce.repo ]]; then
  sed -i 's/^enabled=1$/enabled=0/' /etc/yum.repos.d/docker-ce.repo
  docker_repo_args+=("--disablerepo=docker-ce-stable")
fi

dnf install -y "${docker_repo_args[@]}" \
  dnf-plugins-core git curl ca-certificates openssl xfsprogs parted gzip tar gnupg2

readonly DOCKER_RPM_BASE="https://download.docker.com/linux/rhel/8/x86_64/stable/Packages"
readonly DOCKER_GPG_URL="https://download.docker.com/linux/rhel/gpg"
readonly DOCKER_GPG_FINGERPRINT="060A61C51B558A7F742B77AAC52FEB6B621E9F35"
readonly CACHE_DIR="/var/cache/smart-bamboo/docker-rpms"
readonly PACKAGES=(
  "docker-ce-29.6.2-1.el8.x86_64.rpm"
  "docker-ce-cli-29.6.2-1.el8.x86_64.rpm"
  "containerd.io-2.2.6-1.el8.x86_64.rpm"
  "docker-buildx-plugin-0.35.0-1.el8.x86_64.rpm"
  "docker-compose-plugin-5.3.1-1.el8.x86_64.rpm"
)

install -d -m 0755 "${CACHE_DIR}"

download_file() {
  local url="$1"
  local target="$2"
  local partial="${target}.part"

  if [[ -s "${target}" ]]; then
    echo "Using cached file: ${target}"
    return
  fi

  curl -4 --http1.1 --tlsv1.2 -fL \
    --retry 10 \
    --retry-all-errors \
    --retry-delay 3 \
    --connect-timeout 15 \
    --max-time 1800 \
    --continue-at - \
    --output "${partial}" \
    "${url}"
  mv -f "${partial}" "${target}"
}

download_file "${DOCKER_GPG_URL}" "${CACHE_DIR}/docker.gpg"
actual_fingerprint="$(
  gpg --batch --show-keys --with-colons "${CACHE_DIR}/docker.gpg" \
    | awk -F: '$1 == "fpr" { print $10; exit }'
)"
if [[ "${actual_fingerprint}" != "${DOCKER_GPG_FINGERPRINT}" ]]; then
  echo "ERROR: Docker GPG fingerprint mismatch: ${actual_fingerprint}" >&2
  exit 3
fi
rpm --import "${CACHE_DIR}/docker.gpg"

rpm_paths=()
for package in "${PACKAGES[@]}"; do
  rpm_path="${CACHE_DIR}/${package}"
  download_file "${DOCKER_RPM_BASE}/${package}" "${rpm_path}"
  signature_output="$(rpm -Kv "${rpm_path}")"
  echo "${signature_output}"
  if ! grep -Eqi 'Signature.*key ID 621e9f35: OK' <<<"${signature_output}"; then
    echo "ERROR: Docker RPM signature verification failed: ${package}" >&2
    exit 4
  fi
  rpm_paths+=("${rpm_path}")
done

dnf install -y "${docker_repo_args[@]}" "${rpm_paths[@]}"
systemctl enable --now docker

docker version
docker compose version
