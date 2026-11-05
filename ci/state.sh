#!/bin/bash
# Usage: ci/state.sh restore|save NAME DIR
# Each job keeps its data on an orphan branch state-NAME. Restore copies it into DIR; save force-pushes DIR as one
# new commit (git only uploads files that changed, so pushes stay small).
set -e
ACT=$1; NAME=$2; mkdir -p "$3"; DIR=$(cd "$3" && pwd)
URL="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"; S="$RUNNER_TEMP/state-$NAME.git"
g() { git --git-dir="$S" --work-tree="$DIR" -C "$DIR" "$@"; }
if [ ! -d "$S" ]; then git init -q --bare "$S"; git --git-dir="$S" remote add origin "$URL"; fi
if [ "$ACT" = restore ]; then
  if git --git-dir="$S" fetch -q --depth 1 origin "state-$NAME" 2>/dev/null; then g checkout -q FETCH_HEAD -- . ; echo "restored state-$NAME"; else echo "no state-$NAME yet"; fi
else
  g add -A .
  g -c user.name="paper-bot" -c user.email="paper-bot@users.noreply.github.com" commit -q -m "state $(date -u +%FT%TZ)" || true
  for i in 1 2 3; do git --git-dir="$S" push -q -f origin "HEAD:refs/heads/state-$NAME" && break; sleep 5; done
  echo "saved state-$NAME"
fi
