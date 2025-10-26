#!/usr/bin/env bash
set -euo pipefail

H=${1:-$(hostname -I | awk '{print $1}')}
BASE="http://$H:8094"

# Best-effort readiness
for _ in {1..40}; do curl -fsS "$BASE/health" >/dev/null && break || sleep 0.25; done

live=0; slate=0; other=0
declare -a live_list=() slate_list=()

for l in eplus{1..40}; do
  out="$(curl -sS --max-time 3 -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE/vc/$l" || echo '000 ')"
  code="${out%% *}"; loc="${out#* }"

  if [[ "$code" == "302" && "$loc" == *"/static/slate.html"* ]]; then
    ((slate+=1)); slate_list+=("$l")
  elif [[ "$code" == "302" && -n "$loc" ]]; then
    ((live+=1)); live_list+=("$l")
  else
    ((other+=1))
  fi
done

printf "Total: 40  Live: %d  Placeholders: %d  Other: %d\n" "$live" "$slate" "$other"
printf "Live lanes: %s\n" "${live_list[*]}"
printf "Placeholder lanes: %s\n" "${slate_list[*]}"
