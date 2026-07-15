#!/usr/bin/env bash
# render_html.sh — render a fusion RUN_DIR's Markdown reports to styled HTML (in addition to the .md files).
# Converts each panelist report AND the fusion report that exists in RUN_DIR. Missing reports are skipped
# (e.g. a dropped panelist). Self-contained converter (scripts/md_to_html.py, stdlib only).
#
# Usage: render_html.sh RUN_DIR ["<topic>"]
set -uo pipefail
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rd="${1:?usage: render_html.sh RUN_DIR [topic]}"
topic="${2:-Fusion}"

made=0
while IFS=$'\t' read -r base title; do
  [ -n "$base" ] || continue
  [ -s "$rd/$base.md" ] || continue
  if [ "$base" = "report_gpt5.6sol" ] && python3 - "$rd/$base.md.routing.json" <<'PY' 2>/dev/null
import json, sys
route = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if route.get("fallback_used") and route.get("resolved_model") == "gpt-5.5" else 1)
PY
  then
    title="GPT-5.5 safety fallback - $topic"
  fi
  if python3 "$SD/md_to_html.py" "$rd/$base.md" "$rd/$base.html" "$title"; then
    echo "  rendered $base.html"; made=$((made + 1))
  else
    echo "  WARN: failed to render $base.html" >&2
  fi
done < <(python3 "$SD/panel_config.py" render-targets --topic "$topic")
for md in "$rd"/review_*.md "$rd"/contested_claims.md; do
  [ -s "$md" ] || continue
  base="$(basename "$md" .md)"
  if python3 "$SD/md_to_html.py" "$md" "$rd/$base.html" "$base - $topic"; then
    echo "  rendered $base.html"; made=$((made + 1))
  else
    echo "  WARN: failed to render $base.html" >&2
  fi
done
echo "[render_html] wrote $made HTML report(s) to $rd"
