#!/usr/bin/env bash
# Grok 4.5 runner (Grok Build CLI, `grok`) for panelist or peer-review calls.
# Modeled on run_claude.sh: plain stdout is the report; no GPT-style safety fallback
# (Grok has no structured content-policy retry path). Grok's own MCP stack
# (perplexity/fmp/scite/biomcp, from ~/.grok/config.toml + ~/.claude.json) gives the
# panelist a full tool suite; ~/.grok/AGENTS.md supplies the single-pass panelist doctrine.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

prompt_file="${1:?usage: run_grok.sh <prompt_file> <output_file> [reasoning_effort]}"
output_file="${2:?usage: run_grok.sh <prompt_file> <output_file> [reasoning_effort]}"
# Grok panelist effort is pinned to `high` per policy (FUSION_GROK_EFFORT overrides). The positional
# effort arg (arg 3, tuned for the max/xhigh Anthropic/Codex seats) is accepted for interface parity but ignored.
effort="${FUSION_GROK_EFFORT:-high}"
model="${FUSION_GROK_MODEL:-grok-4.5}"
grok_bin="${FUSION_GROK_BIN:-$HOME/.grok/bin/grok}"

if [ ! -s "$prompt_file" ]; then
  echo "[run_grok.sh] prompt file is missing or empty: $prompt_file" >&2
  exit 2
fi
prompt_file="$(realpath "$prompt_file")"
output_file="$(realpath -m "$output_file")"
mkdir -p "$(dirname "$output_file")"
rm -f "$output_file"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/hybrid-fusion-grok.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

# --prompt-file reads the prompt from a file (avoids ARG_MAX on large prompts, unlike argv).
# --always-approve auto-approves tool calls; --no-subagents keeps the panelist single-pass;
# --cwd isolates the run to the scratch dir; plain stdout is captured as the report.
grok_max_retries="${FUSION_TRANSIENT_RETRIES:-1}"
grok_backoff="${FUSION_TRANSIENT_BACKOFF:-5}"
grok_attempt=0
grok_deadline=$(( $(date +%s) + FUSION_TIMEOUT ))   # all retries SHARE one budget (never exceeds FUSION_TIMEOUT)
while :; do
  grok_rem=$(( grok_deadline - $(date +%s) )); [ "$grok_rem" -lt 1 ] && grok_rem=1
  (
    cd "$scratch" || exit 1
    # GROK_CLAUDE_MCPS_ENABLED=false: skip grok's Claude-compat MCP ingestion (11 finance-plugin
    # remote servers that fail OAuth at boot). Grok's own config.toml servers (perplexity/fmp/
    # scite/biomcp) are unaffected — the panelist's full MCP suite stays available.
    _run_with_timeout "$grok_rem" env GROK_CLAUDE_MCPS_ENABLED=false "$grok_bin" \
      --prompt-file "$prompt_file" \
      -m "$model" \
      --effort "$effort" \
      --cwd "$scratch" \
      --output-format plain \
      --always-approve \
      --no-subagents \
      > "$output_file" 2> "$scratch/stream.log"
  )
  status=$?
  if [ "$grok_attempt" -lt "$grok_max_retries" ] && _fusion_should_retry "$status" "$scratch/stream.log" "$output_file"; then
    grok_attempt=$((grok_attempt+1))
    echo "[run_grok.sh] transient failure (status=$status); retry $grok_attempt/$grok_max_retries after ${grok_backoff}s" >&2
    sleep "$grok_backoff"
    continue
  fi
  break
done
if [ $status -eq 124 ]; then
  echo "[run_grok.sh] grok timed out after ${FUSION_TIMEOUT}s; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 124
fi
if [ $status -ne 0 ] || [ ! -s "$output_file" ]; then
  echo "[run_grok.sh] grok exited $status or produced no output; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 1
fi
echo "[run_grok.sh] ok (model=$model effort=$effort) -> $output_file"
