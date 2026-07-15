#!/usr/bin/env bash
# run_review.sh — launch the Gauntlet external adversarial reviewer (GPT-5.6 Sol via codex)
# on an assembled reviewer prompt, then QC-gate the returned review.
#
# Usage:
#   run_review.sh <run_dir> [round]            # round: 1 (default) or 2
#   run_review.sh --qc-only <run_dir> [round]  # gate an existing review without launching codex
#
# Round 1 expects <run_dir>/09_reviewer_prompt.txt      -> 10_adversarial_review_gpt56sol.md
# Round 2 expects <run_dir>/09b_reviewer_prompt_r2.txt  -> 10b_adversarial_review_gpt56sol_r2.md
#
# Env:
#   REVIEWER_MODEL      (default gpt-5.6-sol)
#   REVIEWER_EFFORT     (default max)
#   REVIEWER_TIMEOUT_S  (default 3600)
#   QC_MIN_BYTES        (default 3000)
#   PREFLIGHT=1         run a cheap codex auth/availability ping before the review
#
# Exit codes: 0 review completed AND passed QC · 3 QC fail · 124 timeout · 2 usage/missing input · 1 launch/preflight failure
#
# Load-bearing notes:
# - Delegates to the HYBRID-model-fusion run_codex.sh (standard mode: danger-full-access sandbox,
#   MCP connectors live, stdin prompt, -o final-message capture, deadline-bounded transient retry,
#   gpt-5.5 structured-safety fallback, routing json). Do NOT use the model-council-fast runner:
#   its _fusion_lib.sh hardcodes FUSION_FAST=1 (council is fast-only), which silently forces
#   workspace-write + --ignore-user-config (no MCPs, no run-dir writes outside /tmp), a word-capped
#   fast preamble, and effort=high. FUSION_FAST=0 is still pinned here defensively.
# - FUSION_RUN_STAGE is a custom tag ("gauntlet_review"), NOT "review": the literal stage "review"
#   makes the hybrid runner attach its peer-review --output-schema JSON contract, which would
#   force the review out of the required markdown format.
# - DOUBLE CAPTURE, two distinct paths so neither can clobber the other:
#     canonical = the file the reviewer itself writes into <run_dir> via shell (absolute path in its prompt)
#     capture   = the -o/--output-last-message file (reviewer's final message)
#   QC prefers canonical; if only the capture is complete, it is promoted to canonical.

set -uo pipefail

qc_only=0
if [ "${1:-}" = "--qc-only" ]; then qc_only=1; shift; fi
run_dir="${1:?usage: run_review.sh [--qc-only] <run_dir> [round]}"
round="${2:-1}"

run_dir="$(realpath "$run_dir" 2>/dev/null)" || { echo "[run_review] bad run_dir" >&2; exit 2; }
if [ "$round" = "2" ]; then
  prompt_file="$run_dir/09b_reviewer_prompt_r2.txt"
  review_file="$run_dir/10b_adversarial_review_gpt56sol_r2.md"
  capture_file="$run_dir/10b_review_capture_r2.md"
else
  prompt_file="$run_dir/09_reviewer_prompt.txt"
  review_file="$run_dir/10_adversarial_review_gpt56sol.md"
  capture_file="$run_dir/10_review_capture_r1.md"
fi

REVIEWER_MODEL="${REVIEWER_MODEL:-gpt-5.6-sol}"
REVIEWER_EFFORT="${REVIEWER_EFFORT:-max}"
REVIEWER_TIMEOUT_S="${REVIEWER_TIMEOUT_S:-3600}"
QC_MIN_BYTES="${QC_MIN_BYTES:-3000}"

qc_gate() {  # qc_gate <file>  -> 0 pass / 1 fail (prints reason)
  local f="$1"
  [ -s "$f" ] || { echo "[qc] FAIL: missing/empty $f"; return 1; }
  local bytes; bytes="$(wc -c < "$f")"
  if [ "$bytes" -lt "$QC_MIN_BYTES" ]; then echo "[qc] FAIL: $f is $bytes bytes < $QC_MIN_BYTES"; return 1; fi
  local ok=0 tok
  for tok in 'VERDICT' '/100' 'CLAIM VERIFICATION' 'COMPLIANCE'; do
    grep -qi -- "$tok" "$f" || { echo "[qc] FAIL: token not found in $f: $tok"; ok=1; }
  done
  [ "$ok" -eq 0 ] && echo "[qc] PASS: $f ($bytes bytes)"
  return "$ok"
}

finish_qc() {  # prefer canonical; promote capture if needed
  if qc_gate "$review_file"; then return 0; fi
  if [ -s "$capture_file" ] && qc_gate "$capture_file"; then
    cp -f "$capture_file" "$review_file"
    echo "[run_review] canonical file failed QC; promoted -o capture -> $review_file"
    return 0
  fi
  return 1
}

if [ "$qc_only" = "1" ]; then
  finish_qc && exit 0 || exit 3
fi

[ -s "$prompt_file" ] || { echo "[run_review] missing reviewer prompt: $prompt_file" >&2; exit 2; }

if [ "${PREFLIGHT:-0}" = "1" ]; then
  pf="$run_dir/preflight_codex.txt"; rm -f "$pf"
  timeout 150 codex exec --skip-git-repo-check -m "$REVIEWER_MODEL" \
    -c model_reasoning_effort=low -o "$pf" - <<<'Reply with exactly: OK' >/dev/null 2>&1
  if ! grep -qi 'OK' "$pf" 2>/dev/null; then
    echo "[run_review] preflight FAILED: codex/$REVIEWER_MODEL unreachable or unauthenticated" >&2
    exit 1
  fi
  echo "[run_review] preflight ok"
fi

# Snapshot core artifacts once per round — insurance against reviewer file clobber.
backup="$run_dir/review_backup_r$round"
mkdir -p "$backup"
for p in "$run_dir"/0[1-8]*; do
  [ -f "$p" ] && cp -n "$p" "$backup/" 2>/dev/null
done

rm -f "$capture_file"
runner="$HOME/.claude/skills/hybrid-model-fusion/scripts/run_codex.sh"
started=$(date +%s)
if [ -f "$runner" ]; then
  FUSION_FAST=0 FUSION_TIMEOUT="$REVIEWER_TIMEOUT_S" FUSION_CODEX_MODEL="$REVIEWER_MODEL" \
  FUSION_RUN_STAGE=gauntlet_review \
    bash "$runner" "$prompt_file" "$capture_file" "$REVIEWER_EFFORT"
  status=$?
else
  echo "[run_review] hardened runner missing at $runner; using raw codex exec" >&2
  timeout "$REVIEWER_TIMEOUT_S" codex exec --skip-git-repo-check --cd "$run_dir" \
    -m "$REVIEWER_MODEL" -s danger-full-access \
    -c tools.web_search=true -c "model_reasoning_effort=$REVIEWER_EFFORT" \
    --json -o "$capture_file" - < "$prompt_file" > "$run_dir/review_stream_r$round.log" 2>&1
  status=$?
fi
elapsed=$(( $(date +%s) - started ))
echo "[run_review] codex exited status=$status after ${elapsed}s (model=$REVIEWER_MODEL effort=$REVIEWER_EFFORT round=$round)"

[ "$status" -eq 124 ] && exit 124
finish_qc && exit 0
echo "[run_review] review failed QC on both canonical and capture paths" >&2
exit 3
