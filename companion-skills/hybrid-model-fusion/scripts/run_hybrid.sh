#!/usr/bin/env bash
# End-to-end Hybrid Model Fusion driver with checkpoints.

set -uo pipefail

SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SD/.." && pwd)"

prompt_file=""
topic="hybrid_fusion"
run_dir=""
mode="normal"
effort="max"
skip_fintwit=0

usage() {
  cat >&2 <<'EOF'
usage: run_hybrid.sh --prompt PROMPT_FILE [--topic TOPIC] [--run-dir RUN_DIR] [--mode normal|deep] [--effort max] [--skip-fintwit]
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prompt) prompt_file="${2:?missing --prompt value}"; shift 2 ;;
    --topic) topic="${2:?missing --topic value}"; shift 2 ;;
    --run-dir) run_dir="${2:?missing --run-dir value}"; shift 2 ;;
    --mode) mode="${2:?missing --mode value}"; shift 2 ;;
    --effort) effort="${2:?missing --effort value}"; shift 2 ;;
    --skip-fintwit) skip_fintwit=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[ -s "$prompt_file" ] || { echo "missing prompt file: $prompt_file" >&2; exit 2; }
if [ -z "$run_dir" ]; then
  slug=$(printf '%s' "$topic" | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9_-' | cut -c1-50)
  run_dir="$HOME/hybrid_fusion/${slug}_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$run_dir/logs"
cp "$prompt_file" "$run_dir/original_prompt.md"

write_state() {
  python3 - "$run_dir/run_state.json" "$run_dir/run_metrics.json" "$1" <<'PY'
import json, pathlib, sys, time
path = pathlib.Path(sys.argv[1])
metrics_path = pathlib.Path(sys.argv[2])
step = sys.argv[3]
now = int(time.time())
state = json.loads(path.read_text()) if path.exists() else {"steps": []}
state["steps"].append({"step": step, "time": now})
path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {"stage_events": []}
metrics["stage_events"].append({"stage": step, "time": now})
events = metrics["stage_events"]
if len(events) >= 2:
    metrics["elapsed_seconds"] = events[-1]["time"] - events[0]["time"]
metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
PY
}

write_state "start"
bash "$SD/detect_panel.sh" "$run_dir" || exit $?

# Hybrid runs with MCP connectors ON — warm them up so the FIRST real tool call inside the panel
# isn't the first contact with a stale server / expired OAuth. All WARN-only (native web search
# remains a fallback); opt out with FUSION_MCP_WARMUP=0.
if [ "${FUSION_MCP_WARMUP:-1}" = "1" ]; then
  . "$SD/_fusion_lib.sh"
  _wt="${FUSION_MCP_WARMUP_TIMEOUT:-60}"
  scite_refresh="$HOME/.codex/scripts/refresh-scite-token.py"
  if [ -x "$scite_refresh" ]; then
    if _run_with_timeout "$_wt" python3 "$scite_refresh" --force >"$run_dir/logs/scite_refresh.log" 2>&1; then
      echo "[preflight] Scite OAuth token refreshed/valid" >&2
    else
      echo "[preflight] WARN: Scite token refresh failed (see logs/scite_refresh.log); panelists fall back to other sources" >&2
    fi
  fi
  _grok_bin="${FUSION_GROK_BIN:-$HOME/.grok/bin/grok}"
  [ -x "$_grok_bin" ] || _grok_bin="grok"
  if have "$_grok_bin" || [ -x "$_grok_bin" ]; then
    if _run_with_timeout "$_wt" "$_grok_bin" mcp doctor >"$run_dir/logs/grok_mcp_doctor.log" 2>&1; then
      echo "[preflight] grok mcp doctor ok (see logs/grok_mcp_doctor.log)" >&2
    else
      echo "[preflight] WARN: grok mcp doctor reported issues (see logs/grok_mcp_doctor.log)" >&2
    fi
  fi
  if have claude; then
    if _run_with_timeout "$_wt" claude mcp list >"$run_dir/logs/claude_mcp_list.log" 2>&1; then
      echo "[preflight] claude mcp list ok (see logs/claude_mcp_list.log)" >&2
    else
      echo "[preflight] WARN: claude mcp list reported issues (see logs/claude_mcp_list.log)" >&2
    fi
  fi
fi

python3 - "$SKILL_DIR" "$run_dir" "$prompt_file" <<'PY'
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "scripts"))
from panel_config import load_panelists
skill_dir = pathlib.Path(sys.argv[1])
run_dir = pathlib.Path(sys.argv[2])
prompt_text = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8").strip()
panel_ref = (skill_dir / "references" / "panel.md").read_text(encoding="utf-8").strip()
research_routing = (skill_dir / "references" / "research_routing.md").read_text(encoding="utf-8").strip()
fintwit = run_dir / "fintwit_context.md"
fintwit_block = ""
if fintwit.exists() and fintwit.stat().st_size:
    fintwit_block = "\n\n## FinTwit / X Sentiment Context [Tier 4 - social sentiment only; do NOT anchor material claims]\n" + fintwit.read_text(encoding="utf-8").strip()
for panelist in load_panelists(skill_dir):
    body = "\n\n".join([
        "You are an independent panelist in a Hybrid Model Fusion run.",
        panel_ref,
        research_routing,
        "Use available web or structured tools when needed; cite primary sources for material claims; keep the report complete but avoid unnecessary verbosity. Treat FinTwit/social context, when provided, as Tier 4 only.",
        "## User Task",
        prompt_text + fintwit_block,
        "Produce a complete Markdown research/analysis report. Do not mention other panelists.",
    ])
    (run_dir / panelist["prompt_file"]).write_text(body + "\n", encoding="utf-8")
PY
write_state "panel_prompts"

bash "$SD/run_panel.sh" "$run_dir" "$mode" "$effort" || exit $?
write_state "panel_complete"
python3 "$SD/build_review_packets.py" "$run_dir" || exit $?
write_state "review_packets"
bash "$SD/run_reviews.sh" "$run_dir" "$effort" || exit $?
write_state "reviews_complete"
python3 "$SD/aggregate_reviews.py" "$run_dir" || exit $?
write_state "aggregate_complete"
python3 "$SD/build_judge_prompt.py" "$run_dir" || exit $?
write_state "judge_prompt"
bash "$SD/run_judge.sh" "$run_dir/judge_prompt.txt" "$run_dir/report_fusion.md" "$effort" || exit $?
write_state "judge_complete"
bash "$SD/render_html.sh" "$run_dir" "$topic" || exit $?
write_state "html_complete"

echo "[run_hybrid] complete: $run_dir"
