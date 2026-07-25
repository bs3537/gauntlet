#!/usr/bin/env bash
# Run Gemini 3.6 Flash (High) through Antigravity CLI for panelist or peer-review calls.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

prompt_file="${1:?usage: run_gemini.sh <prompt_file> <output_file>}"
output_file="${2:?usage: run_gemini.sh <prompt_file> <output_file>}"

if ! have agy; then
  echo "[run_gemini.sh] Antigravity CLI 'agy' not installed; skip this model." >&2
  exit 127
fi

if [ ! -s "$prompt_file" ]; then
  echo "[run_gemini.sh] prompt file is missing or empty: $prompt_file" >&2
  exit 2
fi
mkdir -p "$(dirname "$output_file")"
rm -f "$output_file"

AGY_PRINT_TIMEOUT="${AGY_PRINT_TIMEOUT:-${FUSION_TIMEOUT}s}"
FUSION_AGY_ARG_MAX_BYTES="${FUSION_AGY_ARG_MAX_BYTES:-120000}"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/hybrid-fusion-gemini.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
agy_args=(--model "gemini-3.6-flash-high" --dangerously-skip-permissions --print-timeout "$AGY_PRINT_TIMEOUT")
if [ "${FUSION_RUN_STAGE:-panel}" = "review" ] && [ "${FUSION_REVIEW_LEAST_PRIVILEGE:-0}" = "1" ]; then
  if agy --help 2>/dev/null | grep -q -- '--sandbox'; then
    agy_args=(--model "gemini-3.6-flash-high" --sandbox --print-timeout "$AGY_PRINT_TIMEOUT")
  fi
fi

prompt_bytes=$(wc -c < "$prompt_file")
run_dir="$(dirname "$(realpath "$prompt_file")")"
agy_prompt_arg="$(cat "$prompt_file")"
agy_extra=()
if [ "$prompt_bytes" -gt "$FUSION_AGY_ARG_MAX_BYTES" ]; then
  pointer="$scratch/agy_prompt_pointer.txt"
  {
    printf 'Read the full prompt from this run directory file and answer it completely inline:\n\n'
    printf '%s\n\n' "$(realpath "$prompt_file")"
    printf 'The run directory has been added with --add-dir. Do not summarize the prompt path; execute the requested task and emit the complete final output.\n'
  } > "$pointer"
  agy_prompt_arg="$(cat "$pointer")"
  agy_extra=(--add-dir "$run_dir")
fi

# Bounded retry: agy's transient signature is often exit 0 + EMPTY stdout (provider overload), not a
# nonzero/timeout code; also retry the narrow 429/5xx set. Bounded so it can't eat the timeout budget.
agy_max_retries="${FUSION_AGY_TRANSIENT_RETRIES:-1}"
agy_backoff="${FUSION_AGY_TRANSIENT_BACKOFF:-8}"
agy_attempt=0
agy_deadline=$(( $(date +%s) + FUSION_TIMEOUT ))   # all retries SHARE one budget (never exceeds FUSION_TIMEOUT)
while :; do
  agy_rem=$(( agy_deadline - $(date +%s) )); [ "$agy_rem" -lt 1 ] && agy_rem=1
  _run_with_timeout "$agy_rem" agy "${agy_args[@]}" ${agy_extra[@]+"${agy_extra[@]}"} --print "$agy_prompt_arg" \
    > "$output_file" 2> "$scratch/stderr.log"
  status=$?
  if [ "$agy_attempt" -lt "$agy_max_retries" ] \
     && { { [ "$status" -eq 0 ] && [ ! -s "$output_file" ]; } || _fusion_should_retry "$status" "$scratch/stderr.log" "$output_file"; }; then
    agy_attempt=$((agy_attempt+1))
    echo "[run_gemini.sh] transient agy failure (status=$status, empty-output); retry $agy_attempt/$agy_max_retries after ${agy_backoff}s" >&2
    sleep "$agy_backoff"
    continue
  fi
  break
done
if [ $status -eq 124 ]; then
  echo "[run_gemini.sh] agy timed out after ${FUSION_TIMEOUT}s; tail of stderr:" >&2
  tail -20 "$scratch/stderr.log" >&2
  exit 124
fi
if [ $status -ne 0 ] || [ ! -s "$output_file" ]; then
  echo "[run_gemini.sh] agy exited $status or produced no output." >&2
  tail -20 "$scratch/stderr.log" >&2
  exit 1
fi
echo "[run_gemini.sh] ok -> $output_file"
