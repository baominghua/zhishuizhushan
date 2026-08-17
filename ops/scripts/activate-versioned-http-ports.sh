#!/usr/bin/env bash
set -Eeuo pipefail

repo="${SMART_BAMBOO_REPO:-/opt/smart-bamboo}"
env_file="${SMART_BAMBOO_ENV_FILE:-/srv/smart-bamboo/config/primary.env}"
compose_file="${SMART_BAMBOO_COMPOSE_FILE:-ops/compose.primary.yml}"

cd "${repo}"
test -f "${env_file}"
test -f "${compose_file}"
test -f ops/nginx/smart-bamboo.conf

compose=(
    docker compose
    --project-directory "${repo}"
    --env-file "${env_file}"
    -f "${compose_file}"
)

echo "=== VERSIONED PORT GATE ==="
app_id="$("${compose[@]}" ps -q app)"
test -n "${app_id}"
test "$(docker inspect --format '{{.State.Health.Status}}' "${app_id}")" = "healthy"

"${compose[@]}" config --quiet
grep -q 'listen 81;' ops/nginx/smart-bamboo.conf

echo "=== RECREATE NGINX ONLY ==="
"${compose[@]}" up -d --no-deps --force-recreate nginx

echo "=== WAIT FOR VERSIONED PORTS ==="
for attempt in $(seq 1 30); do
    v1_status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18080/zhushan-bigdata.html || true)"
    v2_status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18081/v2/workspace || true)"
    if [[ "${v1_status}" = "200" && "${v2_status}" = "200" ]]; then
        echo "ports_ready_attempt=${attempt}"
        break
    fi
    if [[ "${attempt}" = "30" ]]; then
        echo "ERROR: versioned HTTP ports did not become ready (v1=${v1_status}, v2=${v2_status})." >&2
        exit 1
    fi
    sleep 2
done

echo "=== LOGIN RETURN CONTRACT ==="
login_location="$(curl -sS -o /dev/null -w '%{redirect_url}' --max-time 5 http://127.0.0.1:18081/admin-login.html)"
login_path="$(printf '%s\n' "${login_location}" | sed -E 's#^https?://[^/]+##')"
test "${login_path}" = "/admin-login.html?returnTo=/v2/workspace"

echo "=== PORT BINDINGS ==="
docker port "$("${compose[@]}" ps -q nginx)"
echo "v1_url=http://36.140.138.117:18080/zhushan-bigdata.html"
echo "v2_url=http://36.140.138.117:18081/v2/workspace"
echo "SMART_BAMBOO_VERSIONED_HTTP_PORTS_READY"
