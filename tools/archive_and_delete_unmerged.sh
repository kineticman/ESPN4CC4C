#!/usr/bin/env bash
set -euo pipefail

# Branches you want to clean
CANDS=(
  backup/pre-force
  backup/stable-20251028T012005Z
  chore/lan-aware-refresh-and-migrator
  feature/first-run-assist
  fix/fresh-install-guardrails
  fix/lan-origin-xmltv
  fix/rc3-build-args
)

PROTECT_REGEX='^(main|stabilize/.*)$'

git fetch --all --prune

for BR in "${CANDS[@]}"; do
  [[ "$BR" =~ $PROTECT_REGEX ]] && { echo "skip(protected): $BR"; continue; }

  if git rev-parse -q --verify "refs/remotes/origin/$BR" >/dev/null; then
    TIP="origin/$BR"
  elif git rev-parse -q --verify "refs/heads/$BR" >/dev/null; then
    TIP="$BR"
  else
    echo "skip(not found): $BR"
    continue
  fi

  TAG="archive/${BR}-$(date +%Y%m%d)"
  echo "-- archiving $BR @ $TIP -> tag $TAG"
  git tag -f "$TAG" "$TIP"
  git push origin "$TAG"

  echo "   deleting remote branch $BR (if exists)"
  git push origin --delete "$BR" || true

  if git show-ref --verify --quiet "refs/heads/$BR"; then
    echo "   deleting local branch $BR"
    git branch -D "$BR" || true
  fi
done

echo "== remaining remote branches =="
git branch -r | sed 's|origin/||' | sort
echo "== archive tags =="
git tag -l 'archive/*' --sort=-creatordate | head -n 20
