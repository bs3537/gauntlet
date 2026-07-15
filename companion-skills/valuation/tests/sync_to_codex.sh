#!/usr/bin/env bash
# Mirror the Claude valuation skill into Codex (~/.codex/skills/valuation), localized.
# Scripts are __file__-relative (location-independent); only *.md docs are path-localized.
# Shared corpus ~/valuation_reference/ is referenced from both trees (not copied).
set -euo pipefail
SRC=/home/bhavneesh/.claude/skills/valuation
DST=/home/bhavneesh/.codex/skills/valuation
BKROOT=/home/bhavneesh/.codex/skill_restore_backups
TS="${1:-$(date +%Y%m%d_%H%M%S)}"

if [ -d "$DST" ]; then
  mkdir -p "$BKROOT"
  cp -r "$DST" "$BKROOT/valuation-$TS"
  echo "Snapshot of existing Codex skill -> $BKROOT/valuation-$TS"
fi

mkdir -p "$(dirname "$DST")"
rm -rf "$DST"
cp -r "$SRC" "$DST"
rm -rf "$DST/.git" 2>/dev/null || true
find "$DST" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# Localize .claude -> .codex in docs only (scripts unchanged). Shared ~/valuation_reference untouched.
find "$DST" -name "*.md" -print0 | xargs -0 sed -i 's#/\.claude/#/.codex/#g; s#~/\.claude/#~/.codex/#g'

echo "Installed Codex skill at $DST"
echo "Localized .claude -> .codex in *.md docs; scripts are location-independent."
echo "Do NOT add to config.toml (skills are always-on by presence; an entry would DISABLE it)."
echo "Restart Codex to pick up the new skill."
