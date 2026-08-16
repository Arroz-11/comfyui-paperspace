#!/bin/bash
# update.sh — bring /notebooks up to date with the repo, discarding local edits
# to REPO files only.
#
# Your stuff is safe by design: everything personal (config/keys.json, ComfyUI/,
# logs/, models, outputs) is git-ignored, and `git reset --hard` can only touch
# TRACKED files. No protected-list needed — protection is structural.

set -e
cd /notebooks

echo "checking for updates..."
git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✓ already up to date ($(git log -1 --format='%h %s'))"
    exit 0
fi

echo "updating $(git log -1 --format=%h) -> $(git log -1 --format=%h origin/main):"
git log --oneline HEAD..origin/main | sed 's/^/   /'
CHANGED=$(git diff --name-only HEAD origin/main)
git reset --hard origin/main -q

echo
echo "✓ updated"
if echo "$CHANGED" | grep -q '\.ipynb$'; then
    echo "⚠ a notebook changed — reload its tab: File → Reload Notebook from Disk"
    echo "  (don't save the old tab over it)"
fi
echo "to apply everything (new nodes, settings): bash /notebooks/scripts/start.sh"
