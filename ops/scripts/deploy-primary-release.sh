#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_HOST="${EXPECTED_HOST:-ecs-98299861}"
EXPECTED_IP="${EXPECTED_IP:-192.168.0.32}"
TARGET_COMMIT="${TARGET_COMMIT:-}"
RELEASE_TAG="${RELEASE_TAG:-}"
REPOSITORY="${REPOSITORY:-/opt/smart-bamboo}"
ENV_FILE="${ENV_FILE:-/srv/smart-bamboo/config/primary.env}"
PUBLIC_BRANCH="${PUBLIC_BRANCH:-production-deploy}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-40}"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-5}"
BASE_IMAGE_PULL_ATTEMPTS="${BASE_IMAGE_PULL_ATTEMPTS:-3}"
BASE_IMAGE_PULL_TIMEOUT_SECONDS="${BASE_IMAGE_PULL_TIMEOUT_SECONDS:-1200}"
LOCK_FILE="${LOCK_FILE:-/run/lock/smart-bamboo-primary-release.lock}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "deploy-primary-release.sh must run as root."
exec 9>"${LOCK_FILE}"
flock -n 9 || fail "another primary release is already running."
[[ "${TARGET_COMMIT}" =~ ^[0-9a-f]{40}$ ]] ||
  fail "TARGET_COMMIT must be a full 40-character Git commit."
[[ "${RELEASE_TAG}" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$ ]] ||
  fail "RELEASE_TAG contains unsupported characters."
[[ "${RELEASE_TAG}" == *"${TARGET_COMMIT:0:12}"* ]] ||
  fail "RELEASE_TAG must contain the first 12 characters of TARGET_COMMIT."
[[ "${HEALTH_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "HEALTH_ATTEMPTS must be a positive integer."
[[ "${HEALTH_INTERVAL_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "HEALTH_INTERVAL_SECONDS must be a positive integer."
[[ "${BASE_IMAGE_PULL_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "BASE_IMAGE_PULL_ATTEMPTS must be a positive integer."
[[ "${BASE_IMAGE_PULL_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "BASE_IMAGE_PULL_TIMEOUT_SECONDS must be a positive integer."

[[ "$(hostname)" == "${EXPECTED_HOST}" ]] ||
  fail "This is not the expected primary host ${EXPECTED_HOST}."
ip -4 addr show eth0 | grep -Fq "${EXPECTED_IP}/" ||
  fail "Primary address ${EXPECTED_IP} is not assigned to eth0."
[[ -d "${REPOSITORY}/.git" ]] || fail "Git repository is missing: ${REPOSITORY}"
[[ -f "${ENV_FILE}" ]] || fail "Protected environment is missing: ${ENV_FILE}"
command -v timeout >/dev/null || fail "The coreutils timeout command is required."
[[ "$(stat -c '%a' "${ENV_FILE}")" == "600" ]] ||
  fail "Protected environment must have mode 600."

cd "${REPOSITORY}"
[[ -z "$(git status --porcelain)" ]] ||
  fail "Repository has uncommitted changes."

compose=(
  docker compose
  --project-directory "${REPOSITORY}"
  --env-file "${ENV_FILE}"
  -f "${REPOSITORY}/ops/compose.primary.yml"
)
"${compose[@]}" config --quiet

current_commit="$(git rev-parse HEAD)"
current_app_container="$("${compose[@]}" ps -q app)"
[[ -n "${current_app_container}" ]] ||
  fail "The primary application container is not running."
current_app_health="$(
  docker inspect \
    --format='{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "${current_app_container}"
)"
[[ "${current_app_health}" == "running healthy" ]] ||
  fail "The running application is not healthy: ${current_app_health}."
old_app_image="$(
  docker inspect --format='{{.Config.Image}}' "${current_app_container}"
)"
[[ "${old_app_image}" == smart-bamboo-app:* ]] ||
  fail "The running application does not use a versioned smart-bamboo-app image."
old_release_tag="${old_app_image#smart-bamboo-app:}"
[[ "${old_release_tag}" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$ ]] ||
  fail "The running application image tag is invalid."
docker image inspect "${old_app_image}" >/dev/null ||
  fail "The current application image is unavailable for rollback."

env_backup="$(mktemp "${ENV_FILE}.rollback.XXXXXX")"
awk \
  -v rollback_tag="${old_release_tag}" '
  BEGIN { tag_seen=0 }
  /^SMART_BAMBOO_RELEASE_TAG=/ {
    print "SMART_BAMBOO_RELEASE_TAG=" rollback_tag
    tag_seen=1
    next
  }
  { print }
  END {
    if (!tag_seen) print "SMART_BAMBOO_RELEASE_TAG=" rollback_tag
  }
' "${ENV_FILE}" >"${env_backup}"
chown root:root "${env_backup}"
chmod 600 "${env_backup}"
env_tmp=""
env_updated=0
app_recreated=0
rollback_succeeded=0

wait_for_app_health() {
  local container_id=""
  local attempt=0
  local health=""
  for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
    container_id="$("${compose[@]}" ps -q app 2>/dev/null || true)"
    if [[ -n "${container_id}" ]]; then
      health="$(
        docker inspect \
          --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
          "${container_id}" 2>/dev/null || true
      )"
      echo "app_health_attempt=${attempt} status=${health:-missing}"
      [[ "${health}" == "healthy" ]] && return 0
      [[ "${health}" == "unhealthy" || "${health}" == "exited" || "${health}" == "dead" ]] &&
        return 1
    fi
    sleep "${HEALTH_INTERVAL_SECONDS}"
  done
  return 1
}

restore_environment() {
  local restore_tmp=""
  restore_tmp="$(mktemp "${ENV_FILE}.restore.XXXXXX")"
  cp -p "${env_backup}" "${restore_tmp}"
  chown root:root "${restore_tmp}"
  chmod 600 "${restore_tmp}"
  mv -f "${restore_tmp}" "${ENV_FILE}"
  env_updated=0
}

rollback_application() {
  echo "=== ROLLBACK APPLICATION ===" >&2
  restore_environment
  if [[ "${app_recreated}" == "1" ]]; then
    "${compose[@]}" config --quiet
    "${compose[@]}" up -d --no-deps --no-build app
    if wait_for_app_health; then
      rollback_succeeded=1
      echo "APPLICATION_ROLLBACK_OK" >&2
    else
      echo "APPLICATION_ROLLBACK_FAILED" >&2
    fi
  else
    rollback_succeeded=1
    echo "ENVIRONMENT_ROLLBACK_OK" >&2
  fi
}

finish() {
  local status=$?
  trap - EXIT
  if [[ "${status}" -ne 0 && "${env_updated}" == "1" ]]; then
    set +e
    rollback_application
    if [[ "${rollback_succeeded}" != "1" ]]; then
      echo "ERROR: automatic rollback did not recover the previous application." >&2
    fi
    set -e
  fi
  rm -f "${env_backup}" "${env_tmp:-}"
  exit "${status}"
}
trap finish EXIT

echo "=== FETCH EXACT RELEASE ==="
fetch_succeeded=0
for attempt in 1 2 3 4 5; do
  echo "fetch_attempt=${attempt}"
  if git -c http.version=HTTP/1.1 fetch --no-tags --force origin \
    "+refs/heads/${PUBLIC_BRANCH}:refs/remotes/origin/${PUBLIC_BRANCH}"; then
    fetch_succeeded=1
    break
  fi
  sleep $((attempt * 5))
done
[[ "${fetch_succeeded}" == "1" ]] || fail "Unable to fetch ${PUBLIC_BRANCH}."
fetched_commit="$(git rev-parse "refs/remotes/origin/${PUBLIC_BRANCH}")"
[[ "${fetched_commit}" == "${TARGET_COMMIT}" ]] ||
  fail "Fetched ${PUBLIC_BRANCH} at ${fetched_commit}; expected TARGET_COMMIT ${TARGET_COMMIT}."
git merge-base --is-ancestor "${current_commit}" "${TARGET_COMMIT}" ||
  fail "TARGET_COMMIT is not a fast-forward from the current checkout."
git merge --ff-only "${TARGET_COMMIT}"
[[ "$(git rev-parse HEAD)" == "${TARGET_COMMIT}" ]] ||
  fail "Checkout did not reach TARGET_COMMIT."

echo "=== UPDATE RELEASE POINTERS ==="
env_tmp="$(mktemp "${ENV_FILE}.update.XXXXXX")"
awk \
  -v commit="${TARGET_COMMIT}" \
  -v tag="${RELEASE_TAG}" '
  BEGIN { commit_seen=0; tag_seen=0 }
  /^SMART_BAMBOO_RELEASE_COMMIT=/ {
    print "SMART_BAMBOO_RELEASE_COMMIT=" commit
    commit_seen=1
    next
  }
  /^SMART_BAMBOO_RELEASE_TAG=/ {
    print "SMART_BAMBOO_RELEASE_TAG=" tag
    tag_seen=1
    next
  }
  { print }
  END {
    if (!commit_seen) print "SMART_BAMBOO_RELEASE_COMMIT=" commit
    if (!tag_seen) print "SMART_BAMBOO_RELEASE_TAG=" tag
  }
' "${ENV_FILE}" >"${env_tmp}"
chown root:root "${env_tmp}"
chmod 600 "${env_tmp}"
mv -f "${env_tmp}" "${ENV_FILE}"
env_updated=1

grep -Fxq "SMART_BAMBOO_RELEASE_COMMIT=${TARGET_COMMIT}" "${ENV_FILE}" ||
  fail "Release commit was not persisted."
grep -Fxq "SMART_BAMBOO_RELEASE_TAG=${RELEASE_TAG}" "${ENV_FILE}" ||
  fail "Release tag was not persisted."
grep -Fxq "SMART_BAMBOO_HUMAN_AUTH_ENABLED=0" "${ENV_FILE}" ||
  fail "HTTP acceptance requires SMART_BAMBOO_HUMAN_AUTH_ENABLED=0."
grep -Eq '^REMOTE_SENSING_API_TOKENS=.+' "${ENV_FILE}" ||
  fail "REMOTE_SENSING_API_TOKENS is missing."
grep -Eq '^SMART_BAMBOO_DASHBOARD_TOKEN=.+' "${ENV_FILE}" ||
  fail "SMART_BAMBOO_DASHBOARD_TOKEN is missing."

"${compose[@]}" config --quiet

echo "=== CACHE BASE IMAGES ==="
mapfile -t base_images < <(
  awk 'toupper($1) == "FROM" { print $2 }' "${REPOSITORY}/Dockerfile" |
    awk '!seen[$0]++'
)
[[ "${#base_images[@]}" -gt 0 ]] || fail "Dockerfile does not declare a base image."
for base_image in "${base_images[@]}"; do
  [[ "${base_image}" != *'$'* ]] ||
    fail "Dockerfile base image variables are not supported by this release script: ${base_image}"
  if docker image inspect "${base_image}" >/dev/null 2>&1; then
    echo "base_image_cached=${base_image}"
    continue
  fi

  echo "base_image_missing=${base_image}"
  echo "The running application remains online while this one-time image download runs."
  image_pull_succeeded=0
  for ((attempt = 1; attempt <= BASE_IMAGE_PULL_ATTEMPTS; attempt++)); do
    echo "base_image_pull_attempt=${attempt}/${BASE_IMAGE_PULL_ATTEMPTS} image=${base_image}"
    if timeout --foreground "${BASE_IMAGE_PULL_TIMEOUT_SECONDS}" \
      docker pull "${base_image}"; then
      image_pull_succeeded=1
      break
    fi
    echo "base_image_pull_retry=${base_image}" >&2
    sleep $((attempt * 5))
  done
  [[ "${image_pull_succeeded}" == "1" ]] ||
    fail "Unable to cache base image ${base_image}; check Docker Hub connectivity."
done

echo "=== BUILD APPLICATION IMAGE ==="
DOCKER_BUILDKIT=1 BUILDKIT_PROGRESS=plain "${compose[@]}" build app
new_image="smart-bamboo-app:${RELEASE_TAG}"
docker image inspect "${new_image}" >/dev/null

echo "=== RECREATE APPLICATION ONLY ==="
app_recreated=1
"${compose[@]}" up -d --no-deps --no-build app
wait_for_app_health || fail "New application did not become healthy."

echo "=== VERIFY APPLICATION READINESS ==="
health_payload="$(curl -fsS http://127.0.0.1:8010/api/health)"
printf '%s' "${health_payload}" |
  "${compose[@]}" exec -T app \
    python /app/ops/scripts/verify-deployment-readiness.py \
      --allow-human-auth-pending

runtime_config="$(curl -fsS http://127.0.0.1:8010/satellite-config.local.js)"
grep -Fq "humanLoginEnabled: false" <<<"${runtime_config}" ||
  fail "Runtime config did not keep human login disabled."
grep -Fq "apiToken:" <<<"${runtime_config}" ||
  fail "Runtime config did not publish the read-only dashboard token."

env_updated=0
rm -f "${env_backup}" "${env_tmp:-}"
trap - EXIT

echo "release_commit=${TARGET_COMMIT}"
echo "release_tag=${RELEASE_TAG}"
echo "PRIMARY_APPLICATION_RELEASE_READY"
