#!/usr/bin/env bash
set -euo pipefail

# Load env (same one your unit references)
. /home/brad/Projects/ESPN4CC/.env.plan

cd /home/brad/Projects/ESPN4CC

# --- Compute safe resolver base (LAN) ---
H=$(hostname -I | awk '{print $1}')
DEFAULT_BASE="http://$H:8094"
BASE="${VC_RESOLVER_BASE_URL:-${RESOLVER_BASE:-$DEFAULT_BASE}}"

# 1) Build plan
python3 bin/build_plan.py \
  --db "$DB" \
  --tz "$TZ" \
  --valid-hours "$VALID_HOURS" \
  --lanes "$LANES" \
  --align "$ALIGN" \
  --min-gap-mins "$MIN_GAP_MINS"

# 2) XML
python3 bin/xmltv_from_plan.py \
  --db "$DB" \
  --out "$OUT" \
  --resolver-base "$BASE"

# 3) M3U
python3 bin/m3u_from_plan.py \
  --db "$DB" \
  --out "$M3U" \
  --resolver-base "$BASE" \
  ${CC_HOST:+--cc-host "$CC_HOST"} \
  ${CC_PORT:+--cc-port "$CC_PORT"}

# --- Guardrail: fail if any localhost (raw or URL-encoded) remains ---
if grep -qE '127\.0\.0\.1(%3A|:)8094' "$M3U"; then
  echo '{"ts":"'"$(date -u +%FT%TZ)"'","mod":"run_plan_once","event":"guard_fail","reason":"localhost_in_m3u","m3u":"'"$M3U"'"}' >&2
  exit 1
fi

echo '{"ts":"'"$(date -u +%FT%TZ)"'","mod":"run_plan_once","event":"done","out_xml":"'"$OUT"'","out_m3u":"'"$M3U"'","base":"'"$BASE"'"}'
