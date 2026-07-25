#!/usr/bin/env bash
# Final Hybrid Model Fusion judge runner. Defaults to Opus 5 at max effort (run via `claude`).
# A gpt-*/codex FUSION_JUDGE_MODEL override runs via run_codex.sh; a claude-* value runs via `claude`.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

prompt_file="${1:?usage: run_judge.sh <judge_prompt_file> <output_file> [reasoning_effort]}"
output_file="${2:?usage: run_judge.sh <judge_prompt_file> <output_file> [reasoning_effort]}"
effort="${3:-max}"
judge_model="${FUSION_JUDGE_MODEL:-claude-opus-5}"
# The judge now does tool-based ultradeep verification (native WebSearch/WebFetch first, Perplexity
# second, plus FMP/Scite/BioMCP as relevant and up to 4 subagents) BEFORE adjudicating.
# Tools are available via the inherited claude.ai/local MCP config + bypassPermissions (no extra flag).
FUSION_JUDGE_TIMEOUT="${FUSION_JUDGE_TIMEOUT:-3000}"

if [ ! -s "$prompt_file" ]; then
  echo "[run_judge.sh] judge prompt file is missing or empty: $prompt_file" >&2
  exit 2
fi
prompt_file="$(realpath "$prompt_file")"
output_file="$(realpath -m "$output_file")"
mkdir -p "$(dirname "$output_file")"
rm -f "$output_file"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/hybrid-fusion-judge.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

case "$judge_model" in
  gpt-*|codex*|o[0-9]*-*)
    # GPT / Codex judge (optional FUSION_JUDGE_MODEL override). Delegate to the codex runner so the judge reuses
    # codex web search + MCP connectors, the structured-safety fallback, and routing json.
    # The judge-scoped timeout replaces the panel's FUSION_TIMEOUT; the stage is tagged "judge".
    FUSION_TIMEOUT="$FUSION_JUDGE_TIMEOUT" \
    FUSION_CODEX_MODEL="$judge_model" \
    FUSION_RUN_STAGE="judge" \
      bash "$SCRIPT_DIR/run_codex.sh" "$prompt_file" "$output_file" "$effort" 2> "$scratch/stream.log"
    status=$?
    ;;
  claude-*|claude)
    # Bounded transient retry (429/5xx/reset with empty output) — the judge is the last stage after
    # ~1h of panel+review spend, so a single transient API error must not discard the whole run.
    # All retries SHARE the judge budget (never exceeds FUSION_JUDGE_TIMEOUT).
    judge_max_retries="${FUSION_TRANSIENT_RETRIES:-1}"
    judge_backoff="${FUSION_TRANSIENT_BACKOFF:-5}"
    judge_attempt=0
    judge_deadline=$(( $(date +%s) + FUSION_JUDGE_TIMEOUT ))
    while :; do
      judge_rem=$(( judge_deadline - $(date +%s) )); [ "$judge_rem" -lt 1 ] && judge_rem=1
      (
        cd "$scratch" || exit 1
        _run_with_timeout "$judge_rem" claude -p \
          --model "$judge_model" \
          --effort "$effort" \
          --permission-mode bypassPermissions \
          --output-format text \
          --no-session-persistence \
          < "$prompt_file" \
          > "$output_file" 2> "$scratch/stream.log"
      )
      status=$?
      if [ "$judge_attempt" -lt "$judge_max_retries" ] && _fusion_should_retry "$status" "$scratch/stream.log" "$output_file"; then
        judge_attempt=$((judge_attempt+1))
        echo "[run_judge.sh] transient judge failure (status=$status); retry $judge_attempt/$judge_max_retries after ${judge_backoff}s" >&2
        sleep "$judge_backoff"
        continue
      fi
      break
    done
    ;;
  *)
    echo "[run_judge.sh] unsupported judge model: '$judge_model' (expected claude-* or gpt-*)" >&2
    exit 2
    ;;
esac

if [ $status -eq 124 ]; then
  echo "[run_judge.sh] judge ($judge_model) timed out after ${FUSION_JUDGE_TIMEOUT}s; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 124
fi
if [ $status -ne 0 ] || [ ! -s "$output_file" ]; then
  echo "[run_judge.sh] judge ($judge_model) exited $status or produced no output; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 1
fi

# De-anonymize: the judge adjudicated BLIND (Response A/B/C/D under response_mapping.json); restore real
# model names in the final report so the reader sees which model proposed what. Skipped when unblinded
# (FUSION_JUDGE_BLIND=0) or when no mapping exists.
rd="$(dirname "$output_file")"
if [ "${FUSION_JUDGE_BLIND:-1}" != "0" ] && [ -f "$rd/response_mapping.json" ] && [ -f "$SCRIPT_DIR/deanonymize_report.py" ]; then
  python3 "$SCRIPT_DIR/deanonymize_report.py" "$output_file" "$rd/response_mapping.json" \
    && echo "[run_judge.sh] de-anonymized final report (blind judge -> named report)" >&2 \
    || echo "[run_judge.sh] WARN: de-anon failed; report keeps Response labels" >&2
fi
echo "[run_judge.sh] ok (judge=$judge_model effort=$effort) -> $output_file"
