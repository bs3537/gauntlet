#!/usr/bin/env bash
# Generic Claude Code runner for Opus panelist and peer-review calls.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

prompt_file="${1:?usage: run_claude.sh <prompt_file> <output_file> [reasoning_effort]}"
output_file="${2:?usage: run_claude.sh <prompt_file> <output_file> [reasoning_effort]}"
effort="${3:-high}"
model="${FUSION_CLAUDE_MODEL:-claude-opus-5}"
permission_mode="${FUSION_CLAUDE_PERMISSION_MODE:-bypassPermissions}"
if [ "${FUSION_RUN_STAGE:-panel}" = "review" ] && [ "${FUSION_REVIEW_LEAST_PRIVILEGE:-0}" = "1" ]; then
  permission_mode="${FUSION_CLAUDE_REVIEW_PERMISSION_MODE:-default}"
fi
setting_sources="${FUSION_CLAUDE_SETTING_SOURCES:-}"
if [ "${FUSION_RUN_STAGE:-panel}" = "panel" ]; then
  setting_sources="${FUSION_CLAUDE_PANEL_SETTING_SOURCES:-project}"
fi

if [ ! -s "$prompt_file" ]; then
  echo "[run_claude.sh] prompt file is missing or empty: $prompt_file" >&2
  exit 2
fi
prompt_file="$(realpath "$prompt_file")"
output_file="$(realpath -m "$output_file")"
mkdir -p "$(dirname "$output_file")"
rm -f "$output_file"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/hybrid-fusion-claude.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
setting_args=()
[ -n "$setting_sources" ] && setting_args=(--setting-sources "$setting_sources")

claude_max_retries="${FUSION_TRANSIENT_RETRIES:-1}"
claude_backoff="${FUSION_TRANSIENT_BACKOFF:-5}"
claude_attempt=0
claude_deadline=$(( $(date +%s) + FUSION_TIMEOUT ))   # all retries SHARE one budget (never exceeds FUSION_TIMEOUT)
while :; do
  claude_rem=$(( claude_deadline - $(date +%s) )); [ "$claude_rem" -lt 1 ] && claude_rem=1
  (
  cd "$scratch" || exit 1
	  _run_with_timeout "$claude_rem" claude -p \
	    --model "$model" \
	    --effort "$effort" \
	    "${setting_args[@]}" \
	    --permission-mode "$permission_mode" \
    --output-format text \
    --no-session-persistence \
    < "$prompt_file" \
    > "$output_file" 2> "$scratch/stream.log"
  )
  status=$?
  if [ "$claude_attempt" -lt "$claude_max_retries" ] && _fusion_should_retry "$status" "$scratch/stream.log" "$output_file"; then
    claude_attempt=$((claude_attempt+1))
    echo "[run_claude.sh] transient failure (status=$status); retry $claude_attempt/$claude_max_retries after ${claude_backoff}s" >&2
    sleep "$claude_backoff"
    continue
  fi
  break
done

if [ $status -eq 124 ]; then
  echo "[run_claude.sh] Claude timed out after ${FUSION_TIMEOUT}s; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 124
fi
if [ $status -ne 0 ] || [ ! -s "$output_file" ]; then
  echo "[run_claude.sh] Claude exited $status or produced no output; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 1
fi
echo "[run_claude.sh] ok (model=$model effort=$effort permission=$permission_mode setting_sources=${setting_sources:-default}) -> $output_file"
