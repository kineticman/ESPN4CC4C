wait_http() { # wait_http <url> [tries=40] [sleep=0.25]
  local url="$1" tries="${2:-40}" nap="${3:-0.25}"
  for _ in $(seq 1 "$tries"); do
    curl -fsS "$url" >/dev/null && return 0
    sleep "$nap"
  done
  echo "Timeout waiting for $url" >&2
  return 1
}
wait_resolver() {
  local H BASE
  H=$(hostname -I | awk '{print $1}')
  BASE="http://$H:8094"
  wait_http "$BASE/health" "${1:-40}" "${2:-0.25}"
}
