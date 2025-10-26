#!/usr/bin/env bash
set -euo pipefail

# Load env (same one your unit references)
. /home/brad/Projects/ESPN4CC/.env.plan

cd /home/brad/Projects/ESPN4CC

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
  --resolver-base "$RESOLVER_BASE"

# 3) M3U
python3 bin/m3u_from_plan.py \
  --db "$DB" \
  --out "$M3U" \
  --resolver-base "$RESOLVER_BASE"
