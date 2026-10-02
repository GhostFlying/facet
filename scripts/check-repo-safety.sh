#!/usr/bin/env bash
# Check the Git index, not ignored runtime files. Never print matched values.
set -euo pipefail

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "Repository safety check requires a Git worktree." >&2
  exit 2
fi

blocked_paths=0
while IFS= read -r -d '' tracked_path; do
  case "$tracked_path" in
    .facet-spike/*|*/.facet-spike/*|.facet/*|*/.facet/*|data/*|credentials/*|*/credentials/*|backups/*|.venv/*)
      printf 'Blocked private/runtime path: %s\n' "$tracked_path" >&2
      blocked_paths=1
      ;;
    .env.example|*/.env.example)
      ;;
    .env|.env.*|*/.env|*/.env.*|*client_secret*.json|*token*.json|*.eml|*.mbox|*.db|*.db-wal|*.db-shm|*.db-journal|*.sqlite|*.sqlite-wal|*.sqlite-shm|*.sqlite-journal|*.sqlite3|*.sqlite3-wal|*.sqlite3-shm|*.sqlite3-journal)
      printf 'Blocked private/content file: %s\n' "$tracked_path" >&2
      blocked_paths=1
      ;;
  esac
done < <(git ls-files -z)

# This baseline recognizes common credential formats, not all sensitive data.
# Patterns are deliberately not themselves complete credential-shaped strings.
credential_patterns=(
  '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----'
  'ya29\.[A-Za-z0-9_-]{20,}'
  'gh[pousr]_[A-Za-z0-9]{30,}'
  'github_pat_[A-Za-z0-9_]{30,}'
  'GOCSPX-[A-Za-z0-9_-]{20,}'
  '1//[A-Za-z0-9_-]{30,}'
  '"(refresh_token|access_token|client_secret)"[[:space:]]*:[[:space:]]*"[^"[:space:]]+"'
)
grep_args=()
for credential_pattern in "${credential_patterns[@]}"; do
  grep_args+=(-e "$credential_pattern")
done

scan_status=0
git grep --cached -I -l -E "${grep_args[@]}" -- . || scan_status=$?
if (( scan_status == 0 )); then
  echo "Credential-shaped content found in the files above; do not publish." >&2
  exit 1
elif (( scan_status != 1 )); then
  echo "Credential scan failed; publication is blocked." >&2
  exit 2
fi

if (( blocked_paths != 0 )); then
  exit 1
fi

echo "Repository safety baseline passed (tracked/staged content only)."
