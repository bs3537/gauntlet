#!/usr/bin/env bash
# Run GPT-5.6 Sol through Codex CLI for panelist or peer-review calls.
# A structured safety failure can trigger one GPT-5.5/xhigh retry within the same timeout budget.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

prompt_file="${1:?usage: run_codex.sh <prompt_file> <output_file> [reasoning_effort]}"
output_file="${2:?usage: run_codex.sh <prompt_file> <output_file> [reasoning_effort]}"
primary_effort="${3:-xhigh}"
primary_model="${FUSION_CODEX_MODEL:-gpt-5.6-sol}"

if [ ! -s "$prompt_file" ]; then
  echo "[run_codex.sh] prompt file is missing or empty: $prompt_file" >&2
  exit 2
fi
mkdir -p "$(dirname "$output_file")"
rm -f "$output_file"
routing_file="${output_file}.routing.json"
prompt_sha256="${FUSION_CODEX_PROMPT_SHA256:-}"
if ! [[ "$prompt_sha256" =~ ^[0-9a-fA-F]{64}$ ]]; then
  prompt_sha256="$(sha256sum "$prompt_file" | awk '{print $1}')"
fi

scratch="$(mktemp -d "${TMPDIR:-/tmp}/hybrid-fusion-codex.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

# NOTE: -s danger-full-access (not workspace-write). codex's workspace-write sandbox blocks
# LOCAL stdio MCP servers' network (perplexity/scite/biomcp/fmp -> "user cancelled MCP tool call");
# danger-full-access lets them work and matches the user's codex config default. Panelist runs are
# isolated to the scratch cwd. Verified 2026-06-23 (perplexity_search returns results).
sandbox="danger-full-access"
schema_args=()
if [ "${FUSION_RUN_STAGE:-panel}" = "review" ] && [ "${FUSION_REVIEW_LEAST_PRIVILEGE:-0}" = "1" ]; then
  sandbox="${FUSION_CODEX_REVIEW_SANDBOX:-read-only}"
fi
schema_file="$SCRIPT_DIR/../config/review_output_schema.json"
if [ "${FUSION_RUN_STAGE:-panel}" = "review" ] && [ -s "$schema_file" ]; then
  schema_args=(--output-schema "$schema_file")
fi
fallback_model="${FUSION_CODEX_FALLBACK_MODEL:-gpt-5.5}"
fallback_effort="${FUSION_CODEX_FALLBACK_EFFORT:-xhigh}"

run_attempt() {
  local timeout="$1" attempt_model="$2" attempt_effort="$3" event_log="$4"
  local _tr=0 _trmax="${FUSION_TRANSIENT_RETRIES:-1}" _trbackoff="${FUSION_TRANSIENT_BACKOFF:-5}" _rc _rem
  local _deadline=$(( $(date +%s) + timeout ))   # transient retries SHARE this call's budget, so the
  while :; do                                    # outer safety-fallback's remaining-time math stays correct
    _rem=$(( _deadline - $(date +%s) )); [ "$_rem" -lt 1 ] && _rem=1
    _run_with_timeout "$_rem" codex exec \
      --skip-git-repo-check \
      --cd "$scratch" \
      -m "$attempt_model" \
      -s "$sandbox" \
      -c tools.web_search=true \
      -c "model_reasoning_effort=$attempt_effort" \
      --json \
      "${schema_args[@]}" \
      -o "$output_file" \
      - < "$prompt_file" \
      > "$event_log" 2>&1
    _rc=$?
    # Retry only NARROW transient infra errors (429/5xx/reset) with empty output; a content-policy
    # safety block is NOT transient (won't match) and is left to the safety-fallback path below.
    if [ "$_tr" -lt "$_trmax" ] && _fusion_should_retry "$_rc" "$event_log" "$output_file"; then
      _tr=$((_tr+1))
      echo "[run_codex.sh] transient failure (status=$_rc); retry $_tr/$_trmax after ${_trbackoff}s" >&2
      sleep "$_trbackoff"
      continue
    fi
    return "$_rc"
  done
}

previous_fallback=""
if [ "${FUSION_CODEX_OUTER_RETRY:-0}" = "1" ]; then
  previous_fallback=$(python3 - "$routing_file" "$prompt_sha256" "$fallback_model" \
    "${FUSION_RUN_STAGE:-panel}" "${FUSION_CODEX_SAFETY_CODES:-content_policy_violation,safety_check_failed,safety_identifier_blocked,safety_rejected,safety_violation}" <<'PY' 2>/dev/null || true
import json, sys
try:
    route = json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
allowed = {item.strip() for item in sys.argv[5].split(",") if item.strip()}
if (
    route.get("prompt_sha256") == sys.argv[2]
    and route.get("fallback_used")
    and route.get("primary_model") == "gpt-5.6-sol"
    and route.get("resolved_model") == sys.argv[3]
    and route.get("stage") == sys.argv[4]
    and route.get("fallback_reason") in allowed
):
    print(f"{route.get('fallback_reason', '')}|{route.get('primary_returncode', 1)}")
PY
  )
fi

started=$(date +%s)
if [ -n "$previous_fallback" ]; then
  IFS='|' read -r fallback_reason primary_status <<< "$previous_fallback"
  resolved_model="$fallback_model"
  resolved_effort="$fallback_effort"
  fallback_used=1
  echo "[run_codex.sh] retrying previously selected safety fallback model=$fallback_model effort=$fallback_effort" >&2
  run_attempt "$FUSION_TIMEOUT" "$fallback_model" "$fallback_effort" "$scratch/stream.log"
  status=$?
else
  run_attempt "$FUSION_TIMEOUT" "$primary_model" "$primary_effort" "$scratch/stream.log"
  status=$?
  primary_status=$status
  resolved_model="$primary_model"
  resolved_effort="$primary_effort"
  fallback_used=0
  fallback_reason=""

  if [ "$status" -ne 0 ] && [ "$status" -ne 124 ] && [ "$status" -ne 127 ] \
    && [ ! -s "$output_file" ] && [ "$primary_model" = "gpt-5.6-sol" ] \
    && [ "${FUSION_CODEX_SAFETY_FALLBACK:-1}" = "1" ]; then
    fallback_reason="$(_fusion_codex_safety_code "$scratch/stream.log" 2>/dev/null || true)"
    if [ -n "$fallback_reason" ]; then
      elapsed=$(( $(date +%s) - started ))
      remaining=$(( FUSION_TIMEOUT - elapsed ))
      if [ "$remaining" -gt 0 ]; then
        fallback_used=1
        resolved_model="$fallback_model"
        resolved_effort="$fallback_effort"
        cp "$scratch/stream.log" "$scratch/primary_stream.log"
        rm -f "$output_file"
        echo "[run_codex.sh] structured safety block ($fallback_reason); retrying with model=$fallback_model effort=$fallback_effort" >&2
        run_attempt "$remaining" "$fallback_model" "$fallback_effort" "$scratch/stream.log"
        status=$?
      fi
    fi
  fi
fi

_fusion_write_codex_routing "$routing_file" "$primary_model" "$primary_effort" \
  "$resolved_model" "$resolved_effort" "$fallback_used" "$fallback_reason" \
  "$primary_status" "$status" "${FUSION_RUN_STAGE:-panel}" "$prompt_sha256"

if [ $status -eq 124 ]; then
  echo "[run_codex.sh] codex timed out after ${FUSION_TIMEOUT}s; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 124
fi
if [ $status -ne 0 ] || [ ! -s "$output_file" ]; then
  echo "[run_codex.sh] codex exited $status; tail of log:" >&2
  tail -20 "$scratch/stream.log" >&2
  exit 1
fi
echo "[run_codex.sh] ok (model=$resolved_model effort=$resolved_effort sandbox=$sandbox fallback=$fallback_used) -> $output_file"
