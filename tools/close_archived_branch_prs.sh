#!/usr/bin/env bash
set -euo pipefail

# Toggle a dry run by setting DRY_RUN=1
DRY_RUN="${DRY_RUN:-0}"

# Branches we archived and want to sweep PRs for (edit if needed)
CANDS=(
  backup/pre-force
  backup/stable-20251028T012005Z
  chore/lan-aware-refresh-and-migrator
  feature/first-run-assist
  fix/fresh-install-guardrails
  fix/lan-origin-xmltv
  fix/rc3-build-args
)

# Resolve "owner/repo" from origin
REPO_URL="$(git remote get-url origin)"
if [[ "$REPO_URL" =~ github.com[:/](.+)/(.+)(\.git)?$ ]]; then
  OWNER="${BASH_REMATCH[1]}"; NAME="${BASH_REMATCH[2]%.git}"
  REPO="${OWNER}/${NAME}"
else
  echo "Could not parse origin remote into owner/repo" >&2
  exit 1
fi

NOTE_PREFIX="This pull request targets a branch we archived."
NOTE_BODY=$'We consolidated changes into the v3.x line.\n\n'\
$'• The old branch was archived (tagged) for posterity.\n'\
$'• If you still want this change, please re-open against **main**\n'\
$'  or a fresh branch.\n\n'\
$'Closing for repo hygiene. Thanks! 🙏'

LABEL="archived-branch"

echo "Repo: $REPO"
echo "Branches to sweep: ${#CANDS[@]}"
echo "DRY_RUN=$DRY_RUN"
echo

for BR in "${CANDS[@]}"; do
  echo "-- scanning PRs with head=$BR"
  mapfile -t PRS < <(gh pr list \
    --repo "$REPO" \
    --state open \
    --head "$BR" \
    --json number,url \
    --jq '.[] | "\(.number) \(.url)"') || PRS=()

  if [[ ${#PRS[@]} -eq 0 ]]; then
    echo "   none open."
    continue
  fi

  for row in "${PRS[@]}"; do
    NUM="${row%% *}"
    URL="${row#* }"
    echo "   PR #$NUM  $URL"

    if [[ "$DRY_RUN" = "1" ]]; then
      echo "     [dry-run] would add label '$LABEL', comment, and close."
      continue
    fi

    gh pr edit "$NUM" --repo "$REPO" --add-label "$LABEL" || true
    gh pr comment "$NUM" --repo "$REPO" --body \
"${NOTE_PREFIX} **Branch:** \`$BR\`

${NOTE_BODY}" || true
    gh pr close "$NUM" --repo "$REPO" --delete-branch=false || true
    echo "     closed."
  done
done

echo
echo "== Remaining open PRs =="
gh pr list --repo "$REPO" --state open --limit 200 \
  --json number,title,headRefName,url \
  --jq '.[] | "\(.number)\t\(.headRefName)\t\(.title)\t\(.url)"'
