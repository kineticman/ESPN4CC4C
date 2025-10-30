#!/usr/bin/env bash
set -euo pipefail

PROTECT_REGEX='^(main|stabilize/.*)$'

# Candidate branches seen in your repo snapshot:
CANDS=(
  backup/pre-force
  backup/stable-20251028T012005Z
  chore/lan-aware-refresh-and-migrator
  feature/first-run-assist
  fix/fresh-install-guardrails
  fix/lan-origin-xmltv
  fix/rc3-build-args
)

git fetch --all --prune

echo "== Checking merge status vs origin/main =="
for BR in "${CANDS[@]}"; do
  [[ "$BR" =~ $PROTECT_REGEX ]] && { echo "skip(protected): $BR"; continue; }

  if git branch -r --merged origin/main | sed 's|origin/||' | grep -qx "$BR"; then
    TAG="archive/${BR}-$(date +%Y%m%d)"
    echo "-- MERGED: $BR → tag & delete"
    # tag remote tip (belt & suspenders)
    git fetch origin "$BR" || true
    # create/force tag at the remote branch tip (ok if it no longer exists)
    if git rev-parse -q --verify "origin/$BR" >/dev/null; then
      git tag -f "$TAG" "origin/$BR" || true
      git push origin "$TAG" || true
    else
      echo "   (note) origin/$BR no longer exists; skipping tag push"
    fi
    # delete remote branch
    git push origin --delete "$BR" || true
    # delete local branch if present
    if git show-ref --verify --quiet "refs/heads/$BR"; then
      git branch -d "$BR" || git branch -D "$BR"
    fi
  else
    echo "-- NOT MERGED: $BR (left intact)"
  fi
done
echo "Done."
