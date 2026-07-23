#!/usr/bin/env bash
set -Eeuo pipefail

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"

role="$(mysql -N -B -h 127.0.0.1 -uroot -e \
  "SELECT CONCAT(@@GLOBAL.read_only, ',', @@GLOBAL.super_read_only);")"
if [[ "${role}" == "0,0" ]]; then
  exit 0
fi
[[ "${role}" == "1,1" ]] || exit 1

status="$(mysql -h 127.0.0.1 -uroot -e "SHOW REPLICA STATUS\\G")"
status_field() {
  local field="$1"
  local matches
  mapfile -t matches < <(
    sed -n "s/^[[:space:]]*${field}:[[:space:]]*//p" <<<"${status}"
  )
  [[ "${#matches[@]}" == "1" ]] || return 1
  printf '%s' "${matches[0]}"
}

Replica_IO_Running="$(status_field Replica_IO_Running)"
Replica_SQL_Running="$(status_field Replica_SQL_Running)"
Last_IO_Error="$(status_field Last_IO_Error)"
Last_SQL_Error="$(status_field Last_SQL_Error)"
Auto_Position="$(status_field Auto_Position)"

[[ "${Replica_IO_Running}" == "Yes" &&
   "${Replica_SQL_Running}" == "Yes" &&
   -z "${Last_IO_Error}" &&
   -z "${Last_SQL_Error}" &&
   "${Auto_Position}" == "1" ]]
