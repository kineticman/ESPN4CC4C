#!/usr/bin/env bash
set -euo pipefail
bad=$(git diff --cached --name-only --diff-filter=ACM | xargs -r grep -nE '(^|[^0-9])((10\.[0-9]{1,3}\.)|(192\.168\.)|(172\.(1[6-9]|2[0-9]|3[0-1])\.))' || true)
if [ -n "$bad" ]; then
  echo "❌ Private LAN IPs detected in staged files:"
  echo "$bad"
  echo "Tip: use HOST_IP / CC_HOST / VC_RESOLVER_BASE_URL variables instead."
  exit 1
fi
