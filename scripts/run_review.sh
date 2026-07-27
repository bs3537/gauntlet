#!/usr/bin/env bash
# run_review.sh — launch the Gauntlet external adversarial reviewer (GPT-5.6 Sol via codex)
# on an assembled reviewer prompt, then QC-gate the returned review.
#
# Usage:
#   run_review.sh <run_dir> [round]              # round: 1 (default) or 2
#   run_review.sh --qc-only <run_dir> [round]    # gate an existing review without launching codex
#   run_review.sh --preflight-only <run_dir>     # Stage-0 fail-fast probe (reachability + quota)
#   run_review.sh --contract-check               # verify the codex launcher contract, then exit
#   run_review.sh --show-routing                 # print the resolved model/effort route, then exit
#
# Round 1 expects <run_dir>/09_reviewer_prompt.txt      -> 10_adversarial_review_gpt56sol.md
# Round 2 expects <run_dir>/09b_reviewer_prompt_r2.txt  -> 10b_adversarial_review_gpt56sol_r2.md
#
# Env:
#   REVIEWER_MODEL      default from config/routing.env (GAUNTLET_REVIEWER_MODEL_ID)
#   REVIEWER_EFFORT     explicit override; default is the config's judge effort for
#                       QC_MODE=judge and lane effort for QC_MODE=lane
#   REVIEWER_WORKER_EFFORT  lane default (config GAUNTLET_REVIEWER_LANE_EFFORT)
#   REVIEWER_TIMEOUT_S  (default 3600)
#   QC_MIN_BYTES        (default 3000)
#   PREFLIGHT           1 = codex reachability + quota probe before the review.
#                       DEFAULT: on for QC_MODE=judge (fail fast on the single judge call),
#                       off for QC_MODE=lane (4 parallel lanes would ping codex 4x redundantly).
#                       PREFLIGHT=0 force-skips; PREFLIGHT=1 force-runs.
#   QC_EXPECT_TICKER    optional; if set, the review must name this ticker/company
#                       >= QC_MIN_TICKER_HITS times (default 2). Catches empty stubs and
#                       wrong-company responses the size+token gate alone would pass.
#   QC_MIN_TICKER_HITS  (default 2) minimum QC_EXPECT_TICKER occurrences
#   QC_MIN_TABLE_ROWS   (default 3) minimum non-separator markdown table rows the judge's
#                       claim-verification table must carry (judge mode only)
#   QC_MODE             judge (default; full scored-review token gate) | lane (size-only, for research lanes)
#   PROMPT_FILE / REVIEW_FILE / CAPTURE_FILE   override the round-derived paths so this
#                       hardened launcher can run each panel research lane and the judge
#                       (panel mode). Unset = the single-reviewer round-1/round-2 defaults.
#   GAUNTLET_CODEX_RUNNER    path to the hardened codex launcher (default: the
#                       hybrid-model-fusion one). Set to a nonexistent path to force the
#                       Gauntlet-owned raw-codex launcher.
#   GAUNTLET_STRICT_CONTRACT 1 = abort instead of falling back when the external launcher
#                       fails its contract check (CI / release gating).
#   GAUNTLET_ROUTING_CONF    path to the routing SSOT (default ../config/routing.env)
#
# Exit codes: 0 review completed AND passed QC · 1 launch/preflight failure (unreachable or
#             unauthenticated) · 2 usage/missing input · 3 QC fail · 4 codex reachable but
#             QUOTA/RATE LIMITED (downgrade to PANEL=0 or the labeled self-review) · 124 timeout
#
# Load-bearing notes:
# - The reviewer is launched through an EXTERNAL hardened launcher owned by another skill
#   (hybrid-model-fusion/scripts/run_codex.sh: danger-full-access sandbox, MCP connectors live,
#   stdin prompt, -o final-message capture, deadline-bounded transient retry, routing json).
#   That coupling is a private env contract, so it is VERIFIED at startup
#   (runner_contract_check) instead of assumed: if the launcher is missing, or no longer
#   honors the flags Gauntlet passes, the run says so loudly and uses the Gauntlet-owned raw
#   codex launcher below — which is artifact-equivalent (same capture file, same
#   <capture>.routing.json, same stream log), so downstream QC and the SKILL's routing-json
#   sanity check work identically on either path.
#   Gauntlet disables the launcher's cross-model safety fallback to preserve the requested
#   reviewer route. Do NOT point GAUNTLET_CODEX_RUNNER at the model-council-fast runner:
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Routing SSOT (config/routing.env) ─────────────────────────────────────────────
# One file owns model IDs and effort tiers; explicit env still wins over it, and the
# literal defaults below only apply if the config is missing (e.g. a stale install).
ROUTING_CONF="${GAUNTLET_ROUTING_CONF:-$SCRIPT_DIR/../config/routing.env}"
if [ -f "$ROUTING_CONF" ]; then
  # shellcheck disable=SC1090
  . "$ROUTING_CONF"
fi

REVIEWER_MODEL="${REVIEWER_MODEL:-${GAUNTLET_REVIEWER_MODEL_ID:-gpt-5.6-sol}}"
QC_MODE="${QC_MODE:-judge}"   # judge = full scored-review gate; lane = size-only
case "$QC_MODE" in
  lane)  REVIEWER_EFFORT="${REVIEWER_EFFORT:-${REVIEWER_WORKER_EFFORT:-${GAUNTLET_REVIEWER_LANE_EFFORT:-high}}}" ;;
  judge) REVIEWER_EFFORT="${REVIEWER_EFFORT:-${GAUNTLET_REVIEWER_JUDGE_EFFORT:-xhigh}}" ;;
  *) echo "[run_review] invalid QC_MODE: $QC_MODE (expected judge or lane)" >&2; exit 2 ;;
esac
# Fail-fast preflight defaults on for the judge (one call, cheap insurance against
# spending the 20-60 min judge wall on a dead/unauthenticated/quota-exhausted codex);
# off for lanes so the four parallel lane launches do not ping codex four redundant times.
case "$QC_MODE" in
  judge) PREFLIGHT="${PREFLIGHT:-1}" ;;
  lane)  PREFLIGHT="${PREFLIGHT:-0}" ;;
esac
REVIEWER_TIMEOUT_S="${REVIEWER_TIMEOUT_S:-3600}"
QC_MIN_BYTES="${QC_MIN_BYTES:-3000}"
QC_MIN_TABLE_ROWS="${QC_MIN_TABLE_ROWS:-3}"
GAUNTLET_CODEX_SAFETY_FALLBACK=0
CODEX_RUNNER="${GAUNTLET_CODEX_RUNNER:-$HOME/.claude/skills/hybrid-model-fusion/scripts/run_codex.sh}"

# ── Launcher contract (item: no silent coupling to another skill's internals) ──────
# Every env flag Gauntlet passes to the external launcher, asserted to still be honored.
RUNNER_CONTRACT_VARS=(FUSION_FAST FUSION_CODEX_SAFETY_FALLBACK FUSION_TIMEOUT FUSION_CODEX_MODEL FUSION_RUN_STAGE)

# The contract surface is the launcher PLUS the sibling libraries it sources (the fusion
# launcher keeps part of the env contract in _fusion_lib.sh), so scan all of them.
runner_contract_files() {  # runner_contract_files <path>
  local r="$1" d f
  d="$(dirname "$r")"
  printf '%s\n' "$r"
  grep -oE '^[[:space:]]*(\.|source)[[:space:]]+"?\$\{?SCRIPT_DIR\}?/[A-Za-z0-9._-]+"?' "$r" 2>/dev/null |
    sed -E 's@.*/@@; s@"$@@' |
    while read -r f; do [ -f "$d/$f" ] && printf '%s\n' "$d/$f"; done
}

runner_contract_check() {  # runner_contract_check <path> -> 0 usable / 1 unusable
  local r="$1" rc=0 v
  if [ ! -f "$r" ]; then
    echo "[contract] launcher absent: $r"
    return 1
  fi
  local files=(); mapfile -t files < <(runner_contract_files "$r")
  for v in "${RUNNER_CONTRACT_VARS[@]}"; do
    grep -q -- "$v" "${files[@]}" || { echo "[contract] launcher no longer reads $v: $r"; rc=1; }
  done
  # The --output-schema JSON contract must still be gated on the literal stage "review"
  # (Gauntlet passes "gauntlet_review" precisely to avoid it). If that condition is gone,
  # our stage tag no longer protects the markdown format.
  grep -qE 'FUSION_RUN_STAGE.*"review"' "${files[@]}" ||
    { echo "[contract] cannot confirm --output-schema stays gated on stage \"review\": $r"; rc=1; }
  # Artifact contract: the launcher must still emit the routing json the SKILL sanity-checks.
  grep -q 'routing.json' "${files[@]}" || { echo "[contract] launcher no longer emits <output>.routing.json: $r"; rc=1; }
  # Sandbox contract: workspace-write kills the MCP connectors and run-dir writes.
  grep -q 'danger-full-access' "${files[@]}" || { echo "[contract] launcher no longer uses danger-full-access: $r"; rc=1; }
  return "$rc"
}

if [ "${1:-}" = "--show-routing" ]; then
  printf 'model=%s effort=%s qc_mode=%s preflight=%s safety_fallback=%s\n' \
    "$REVIEWER_MODEL" "$REVIEWER_EFFORT" "$QC_MODE" "$PREFLIGHT" \
    "$([ "$GAUNTLET_CODEX_SAFETY_FALLBACK" = "0" ] && printf disabled || printf enabled)"
  exit 0
fi

if [ "${1:-}" = "--contract-check" ]; then
  if runner_contract_check "$CODEX_RUNNER"; then
    echo "[contract] OK: $CODEX_RUNNER honors ${RUNNER_CONTRACT_VARS[*]} + routing json + danger-full-access"
    exit 0
  fi
  echo "[contract] FAILED for $CODEX_RUNNER — Gauntlet would use its own raw-codex launcher" >&2
  exit 1
fi

# ── Preflight: reachability AND a cheap quota/limit probe ─────────────────────────
# Returns 0 reachable · 1 unreachable/unauthenticated · 4 reachable but quota/rate limited.
# Quota is probed BEFORE reachability so a limit message is never read as a dead endpoint:
# the two need different responses (wait / downgrade to PANEL=0 vs. fix auth).
preflight_probe() {  # preflight_probe <out_file> <log_file> -> 0|1|4
  local pf="$1" log="$2"
  rm -f "$pf" "$log"
  timeout "${PREFLIGHT_TIMEOUT_S:-150}" codex exec --skip-git-repo-check -m "$REVIEWER_MODEL" \
    -c model_reasoning_effort=low -o "$pf" - <<<'Reply with exactly: OK' >"$log" 2>&1
  if grep -qiE 'usage limit|rate.?limit|quota|too many requests|\b429\b|weekly limit|limit reached|limit exceeded|resets (at|in)' \
      "$log" "$pf" 2>/dev/null; then
    return 4
  fi
  grep -qi 'OK' "$pf" 2>/dev/null && return 0
  return 1
}

report_preflight() {  # report_preflight <rc>
  case "$1" in
    0) echo "[run_review] preflight ok (codex/$REVIEWER_MODEL reachable, no limit signal)" ;;
    4) echo "[run_review] preflight QUOTA/RATE LIMITED: codex/$REVIEWER_MODEL is reachable but" \
            "limited — downgrade to PANEL=0 or the labeled degraded-mode self-review instead of" \
            "spending the review wall" >&2 ;;
    *) echo "[run_review] preflight FAILED: codex/$REVIEWER_MODEL unreachable or unauthenticated" >&2 ;;
  esac
}

if [ "${1:-}" = "--preflight-only" ]; then
  shift
  pf_dir="${1:?usage: run_review.sh --preflight-only <run_dir>}"
  pf_dir="$(realpath "$pf_dir" 2>/dev/null)" || { echo "[run_review] bad run_dir" >&2; exit 2; }
  preflight_probe "$pf_dir/preflight_codex.txt" "$pf_dir/preflight_codex.log"
  pf_rc=$?
  report_preflight "$pf_rc"
  exit "$pf_rc"
fi

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

# Panel mode: override the round-derived paths so this hardened launcher+QC can run
# each research lane and the judge. Unset = the single-reviewer defaults above.
prompt_file="${PROMPT_FILE:-$prompt_file}"
review_file="${REVIEW_FILE:-$review_file}"
capture_file="${CAPTURE_FILE:-$capture_file}"
# Per-call artifact names derived from the capture file so four parallel lanes and the
# judge never clobber each other's stream log or routing json.
routing_file="${capture_file}.routing.json"
stream_log="${capture_file%.md}.stream.log"

qc_gate() {  # qc_gate <file>  -> 0 pass / 1 fail (prints reason)
  local f="$1"
  [ -s "$f" ] || { echo "[qc] FAIL: missing/empty $f"; return 1; }
  local bytes; bytes="$(wc -c < "$f")"
  if [ "$bytes" -lt "$QC_MIN_BYTES" ]; then echo "[qc] FAIL: $f is $bytes bytes < $QC_MIN_BYTES"; return 1; fi
  local ok=0 tok score="" rows=""
  # Optional company/ticker echo: a real review of THIS company names it repeatedly; an
  # empty stub or a wrong-company answer does not. Opt-in (unset QC_EXPECT_TICKER = skipped),
  # so callers that do not pass a ticker keep the previous behavior.
  if [ -n "${QC_EXPECT_TICKER:-}" ]; then
    local hits; hits="$(grep -oiF -- "$QC_EXPECT_TICKER" "$f" | wc -l)"
    if [ "$hits" -lt "${QC_MIN_TICKER_HITS:-2}" ]; then
      echo "[qc] FAIL: ticker '$QC_EXPECT_TICKER' appears ${hits}x (< ${QC_MIN_TICKER_HITS:-2}) in $f — wrong-company/stub?"; ok=1
    fi
  fi
  # Pointer-stub screen (the known `-o` gotcha: the model ends with "full review saved to
  # /path/x.md" and the capture is a signpost, not a review). Rejected only when the file is
  # ALSO small (< 2x the floor) — a genuine full review may legitimately mention that it also
  # wrote the canonical file, and that one must not be rejected.
  if grep -qiE '(saved|written|wrote|stored|available)[^.]{0,60}(to|at|in)[[:space:]]+[`"'"'"']?(/|~/|\$)' "$f" &&
     [ "$bytes" -lt $(( QC_MIN_BYTES * 2 )) ]; then
    echo "[qc] FAIL: $f looks like a pointer stub — it points at a file path and is only $bytes bytes"; ok=1
  fi
  if [ "$QC_MODE" = "judge" ]; then
    for tok in 'VERDICT' 'CLAIM VERIFICATION' 'COMPLIANCE'; do
      grep -qi -- "$tok" "$f" || { echo "[qc] FAIL: token not found in $f: $tok"; ok=1; }
    done
    # Parse an ACTUAL numeric score (reviewer output §1 = "Overall NN/100 + band"), not just
    # the '/100' substring, and range-check it — so a stub that merely contains '/100' fails.
    score="$(grep -oiE '[0-9]{1,3} *[/] *100' "$f" | grep -oE '^[0-9]{1,3}' | head -1)"
    if [ -z "$score" ]; then
      echo "[qc] FAIL: no parseable NN/100 score in $f (has '/100' as a bare substring only?)"; ok=1
    elif [ "$score" -gt 100 ]; then
      echo "[qc] FAIL: score $score/100 out of range in $f"; ok=1
    fi
    # The claim-verification table must have actual rows. A review whose §4 is an empty
    # heading (or a promise to verify later) contains the token but did no verification —
    # which is precisely the work Stage 3 adjudication consumes.
    rows="$(grep -E '^[[:space:]]*\|' "$f" | grep -cvE '^[[:space:]]*\|[[:space:]:|-]*$')"
    if [ "$rows" -lt "$QC_MIN_TABLE_ROWS" ]; then
      echo "[qc] FAIL: only $rows table row(s) in $f (< $QC_MIN_TABLE_ROWS) — claim-verification table is empty/stubbed"; ok=1
    fi
  fi
  [ "$ok" -eq 0 ] && echo "[qc] PASS ($QC_MODE): $f ($bytes bytes${QC_EXPECT_TICKER:+, ticker ok}${score:+, score $score/100}${rows:+, $rows table rows})"
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

# Gauntlet-owned raw codex launcher. Used when the external hardened launcher is missing or
# fails its contract check. Deliberately artifact-EQUIVALENT to the external path: same
# capture file, same <capture>.routing.json (same keys the SKILL sanity-checks), same stream
# log — so a launcher swap cannot silently change what downstream stages find on disk.
write_routing_json() {  # write_routing_json <primary_rc> <resolved_rc>
  python3 - "$routing_file" "$REVIEWER_MODEL" "$REVIEWER_EFFORT" "$1" "$2" \
      "$(sha256sum "$prompt_file" | awk '{print $1}')" <<'PY'
import json, pathlib, sys

path, model, effort, primary_rc, resolved_rc, sha = sys.argv[1:7]

def rc(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

payload = {
    "stage": "gauntlet_review",
    "fast": False,
    "primary_model": model,
    "primary_effort": effort,
    "primary_returncode": rc(primary_rc),
    "fallback_used": False,
    "fallback_reason": "",
    "resolved_model": model,
    "resolved_effort": effort,
    "resolved_returncode": rc(resolved_rc),
    "prompt_sha256": sha,
    "launcher": "gauntlet-raw-codex",
}
pathlib.Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

launch_raw_codex() {
  timeout "$REVIEWER_TIMEOUT_S" codex exec --skip-git-repo-check --cd "$run_dir" \
    -m "$REVIEWER_MODEL" -s danger-full-access \
    -c tools.web_search=true -c "model_reasoning_effort=$REVIEWER_EFFORT" \
    --json -o "$capture_file" - < "$prompt_file" > "$stream_log" 2>&1
  local rc=$?
  write_routing_json "$rc" "$rc"
  return "$rc"
}

if [ "$qc_only" = "1" ]; then
  finish_qc && exit 0 || exit 3
fi

[ -s "$prompt_file" ] || { echo "[run_review] missing reviewer prompt: $prompt_file" >&2; exit 2; }

if [ "${PREFLIGHT:-0}" != "0" ]; then
  preflight_probe "$run_dir/preflight_codex.txt" "$run_dir/preflight_codex.log"
  pf_rc=$?
  report_preflight "$pf_rc"
  [ "$pf_rc" -ne 0 ] && exit "$pf_rc"
fi

# Snapshot core artifacts once per round — insurance against reviewer file clobber.
backup="$run_dir/review_backup_r$round"
mkdir -p "$backup"
for p in "$run_dir"/0[1-8]*; do
  [ -f "$p" ] && cp -n "$p" "$backup/" 2>/dev/null
done

rm -f "$capture_file" "$routing_file" "$stream_log"

# Verify the external launcher's contract BEFORE spending the review wall on it. A launcher
# that drifted is louder than a launcher that silently degraded: we say what broke and run
# the Gauntlet-owned equivalent instead (or abort under GAUNTLET_STRICT_CONTRACT=1).
use_external=1
if ! runner_contract_check "$CODEX_RUNNER"; then
  use_external=0
  if [ "${GAUNTLET_STRICT_CONTRACT:-0}" = "1" ]; then
    echo "[run_review] launcher contract failed and GAUNTLET_STRICT_CONTRACT=1 — aborting" >&2
    exit 1
  fi
  echo "[run_review] launcher contract not satisfied -> using the Gauntlet-owned raw codex launcher" >&2
fi

started=$(date +%s)
if [ "$use_external" = "1" ]; then
  FUSION_FAST=0 FUSION_CODEX_SAFETY_FALLBACK="$GAUNTLET_CODEX_SAFETY_FALLBACK" \
  FUSION_TIMEOUT="$REVIEWER_TIMEOUT_S" \
  FUSION_CODEX_MODEL="$REVIEWER_MODEL" \
  FUSION_RUN_STAGE=gauntlet_review \
    bash "$CODEX_RUNNER" "$prompt_file" "$capture_file" "$REVIEWER_EFFORT" > "$stream_log" 2>&1
  status=$?
  tail -5 "$stream_log"
else
  launch_raw_codex
  status=$?
fi
elapsed=$(( $(date +%s) - started ))
echo "[run_review] codex exited status=$status after ${elapsed}s (model=$REVIEWER_MODEL effort=$REVIEWER_EFFORT round=$round launcher=$([ "$use_external" = 1 ] && printf external || printf gauntlet-raw))"

[ "$status" -eq 124 ] && exit 124
finish_qc && exit 0
echo "[run_review] review failed QC on both canonical and capture paths" >&2
exit 3
