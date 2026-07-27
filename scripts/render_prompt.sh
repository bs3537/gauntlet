#!/usr/bin/env bash
# render_prompt.sh — resolve the ROUTING tokens in a Gauntlet prompt template from the
# single source of truth (config/routing.env) and print the result on stdout.
#
# Why this exists: model IDs and display names used to be hand-copied into every prompt
# template, so a model bump meant editing the same name in N places and hoping none were
# missed. The template now carries tokens; this script fills them at assembly time, and a
# bump is a one-line edit in config/routing.env.
#
# Usage:
#   render_prompt.sh <template.md> [--body]   # --body = only the text BELOW the
#                                             #          <!-- TEMPLATE BEGINS --> marker,
#                                             #          which is what Stage 2 assembles
#   render_prompt.sh --list                   # print the token -> value mapping
#
# Run-specific placeholders ({{COMPANY}}, {{TICKER}}, {{RUN_DIR}}, {{LANE_FINDINGS}},
# {{PRELIMINARY_REPORT_FULL_TEXT}}, …) are deliberately LEFT ALONE — Stage 2 substitutes
# those per run. Only routing tokens are resolved here.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTING_CONF="${GAUNTLET_ROUTING_CONF:-$SCRIPT_DIR/../config/routing.env}"
[ -f "$ROUTING_CONF" ] || { echo "render_prompt: missing routing config: $ROUTING_CONF" >&2; exit 2; }
# shellcheck disable=SC1090
. "$ROUTING_CONF"

# token -> value. Keep in sync with the tokens used in references/*.md; eval/check.sh
# asserts the rendered output carries the config's values and no leftover routing token.
routing_pairs() {
  cat <<EOF
{{LEAD_MODEL}}	$GAUNTLET_LEAD_MODEL_DISPLAY
{{LEAD_EFFORT}}	$GAUNTLET_LEAD_EFFORT
{{WORKER_MODEL}}	$GAUNTLET_WORKER_MODEL_DISPLAY
{{WORKER_MODEL_ID}}	$GAUNTLET_WORKER_MODEL_ID
{{WORKER_EFFORT}}	$GAUNTLET_WORKER_EFFORT
{{REVIEWER_MODEL}}	$GAUNTLET_REVIEWER_MODEL_DISPLAY
{{REVIEWER_MODEL_ID}}	$GAUNTLET_REVIEWER_MODEL_ID
{{REVIEWER_JUDGE_EFFORT}}	$GAUNTLET_REVIEWER_JUDGE_EFFORT
{{REVIEWER_LANE_EFFORT}}	$GAUNTLET_REVIEWER_LANE_EFFORT
EOF
}

if [ "${1:-}" = "--list" ]; then
  routing_pairs | while IFS=$'\t' read -r token value; do printf '%-26s %s\n' "$token" "$value"; done
  exit 0
fi

template="${1:?usage: render_prompt.sh <template.md> [--body]}"
[ -s "$template" ] || { echo "render_prompt: missing/empty template: $template" >&2; exit 2; }
body_only=0
[ "${2:-}" = "--body" ] && body_only=1

routing_pairs | python3 -c '
import sys

pairs = [line.rstrip("\n").split("\t", 1) for line in sys.stdin if "\t" in line]
template, body_only = sys.argv[1], sys.argv[2] == "1"
text = open(template, encoding="utf-8").read()
if body_only:
    # Split on the marker LINE, not on the prose that mentions the marker by name.
    marker = "<!-- TEMPLATE BEGINS -->"
    lines = text.splitlines(keepends=True)
    idx = next((i for i, line in enumerate(lines) if line.strip() == marker), None)
    if idx is None:
        sys.exit(f"render_prompt: no {marker} marker line in {template}")
    text = "".join(lines[idx + 1 :]).lstrip("\n")
for token, value in pairs:
    text = text.replace(token, value)
sys.stdout.write(text)
' "$template" "$body_only"
