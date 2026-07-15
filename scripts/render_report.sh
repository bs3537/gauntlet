#!/usr/bin/env bash
#
# render_report.sh — render a Gauntlet FINAL_REPORT.md into a styled, self-contained
# HTML report (and optionally a PDF), using the bundled deep-research md_to_html
# renderer with Gauntlet's own template. Prints the output HTML path on stdout
# (renderer chatter goes to stderr, so the last stdout line is the clean path).
#
# Usage:
#   render_report.sh <report.md> [passthrough args for md_to_html.py]
#
# Common passthrough args:
#   --title "Acme Corp (ACME) — Gauntlet Equity Research"
#   --date 2026-07-15
#   --metric "Rating=BUY"            --metric "Weighted Target=\$142"
#   --metric "Expected Return=+23%"  --metric "Reviewer Score=87/100"
#   --pdf-out <path>   # also emit a PDF (needs Chrome/Chromium; optional)
#   --open             # open the HTML in the host browser (explorer.exe on WSL)
#
# The HTML is written next to the .md as <report>.html. Do not pass --out.
set -euo pipefail

MD="${1:?usage: render_report.sh <report.md> [md_to_html.py args...]}"
shift || true
[ -f "$MD" ] || { echo "render_report: markdown not found: $MD" >&2; exit 2; }

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SKILL_DIR/references/gauntlet_report_template.html"

# Locate the deep-research md_to_html renderer across skill trees: installed Claude
# tree first, then the codex parity tree, then the self-contained repo bundle.
RENDERER=""
for base in "$HOME/.claude/skills/deep-research" \
            "$HOME/.codex/skills/deep-research" \
            "$SKILL_DIR/companion-skills/deep-research"; do
  if [ -f "$base/scripts/md_to_html.py" ]; then RENDERER="$base/scripts/md_to_html.py"; break; fi
done
[ -n "$RENDERER" ] || {
  echo "render_report: md_to_html.py not found — install the deep-research companion skill" >&2
  exit 3
}

OUT="${MD%.md}.html"
args=( "$MD" --out "$OUT" )
[ -f "$TEMPLATE" ] && args+=( --template "$TEMPLATE" )

# Renderer status text -> stderr; keep stdout clean for the output path.
python3 "$RENDERER" "${args[@]}" "$@" 1>&2
echo "$OUT"
