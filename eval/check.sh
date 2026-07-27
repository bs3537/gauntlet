#!/usr/bin/env bash
# Gauntlet eval — deterministic gate. No LLM, no network, no codex, no quota.
# Two things live here:
#   STRUCTURAL — the fixture, the answer sheet, the machine-readable detection rules and
#   the reviewer template's MONEY-FIGURE FRAUD SCREEN stay in sync; model routing matches
#   config/routing.env (the single source of truth) everywhere it is written down.
#   BEHAVIORAL — the four self-tests that actually exercise code: the QC gate, the codex
#   preflight, the launcher contract/artifact equivalence, and the review scorer.
# PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCEN="$SCRIPT_DIR/scenarios/planted-fraud-money-figures"
FIXTURE="$SCEN/08_preliminary_report.md"
GT="$SCEN/GROUND-TRUTH.md"
DETECT="$SCEN/detection.json"
TEMPLATE="$ROOT/references/reviewer_prompt_template.md"
MASTER="$ROOT/references/master_research_prompt.md"
SKILL="$ROOT/SKILL.md"
RUNNER="$ROOT/scripts/run_review.sh"
RENDER="$ROOT/scripts/render_prompt.sh"
ROUTING_CONF="$ROOT/config/routing.env"

# Every routing assertion below is DERIVED from the config, never re-typed — otherwise this
# gate would just be another copy to keep in sync (which is the drift it exists to catch).
# shellcheck disable=SC1090
[ -f "$ROUTING_CONF" ] && . "$ROUTING_CONF"

fails=0
fail() { printf 'FAIL: %s\n' "$1"; fails=$((fails+1)); }
need() { [ -f "$1" ] || { fail "missing file: $1"; return 1; }; }
present() { # $1=needle $2=file $3=label — whitespace-normalized fixed-string match,
            # so prose reflows/line wraps cannot silently break the gate
  tr -s '[:space:]' ' ' < "$2" | grep -qF -- "$1" || fail "$3 not found in ${2##*/}: $1"
}
absent() { # $1=needle $2=file $3=label
  if tr -s '[:space:]' ' ' < "$2" | grep -qF -- "$1"; then
    fail "$3 unexpectedly found in ${2##*/}: $1"
  fi
}

need "$FIXTURE" || { echo "FAILED: fixture missing"; exit 1; }
need "$GT" || { echo "FAILED: answer sheet missing"; exit 1; }
need "$DETECT" || { echo "FAILED: detection rules missing"; exit 1; }
need "$TEMPLATE" || { echo "FAILED: reviewer template missing"; exit 1; }
need "$MASTER" || { echo "FAILED: master prompt missing"; exit 1; }
need "$SKILL" || { echo "FAILED: skill instructions missing"; exit 1; }
need "$RUNNER" || { echo "FAILED: reviewer runner missing"; exit 1; }
need "$RENDER" || { echo "FAILED: prompt renderer missing"; exit 1; }
need "$ROUTING_CONF" || { echo "FAILED: routing config missing"; exit 1; }

# 1. Banners: the fixture declares itself fictional; the answer sheet declares secrecy.
present "GAUNTLET EVAL FIXTURE — FICTIONAL COMPANY, PLANTED ERRORS" "$FIXTURE" "fixture banner"
present "Do not show this file to the model under test" "$GT" "answer-sheet banner"

# 2. The six planted frauds: verbatim snippet present in the fixture AND documented
#    in the answer sheet (one per screen pattern, in pattern order).
snippets=(
  '$31.20, the March 2025 52-week high'
  '$2,480M market capitalization ÷ $465M'
  'guaranteed to clear at a sub-7% coupon'
  'net income of $216M against gross profit of $790M'
  'revenue CAGR of 30.0% (FY2023–FY2025)'
  'will reach $980M by FY2030'
)
i=0
for s in "${snippets[@]}"; do
  i=$((i+1))
  present "$s" "$FIXTURE" "planted fraud #$i"
  present "$s" "$GT" "answer-sheet entry for fraud #$i"
done

# 3. The two clean controls, present in both files.
controls=(
  'a 5.0% yield on the current $24.80 price'
  '[FORECAST] FY2027 revenue of $1,953M'
)
i=0
for s in "${controls[@]}"; do
  i=$((i+1))
  present "$s" "$FIXTURE" "clean control #$i"
  present "$s" "$GT" "answer-sheet entry for control #$i"
done

# 4. The six screen-pattern names, present in the answer sheet AND in the reviewer
#    template's MONEY-FIGURE FRAUD SCREEN (keeps eval and runtime lens in sync).
patterns=(
  'Stale figure'
  'Headline-number omission'
  'Guarantee language'
  'Base-rate / denominator abuse'
  'Cherry-picked window'
  'Projection as fact'
)
present "MONEY-FIGURE FRAUD SCREEN" "$TEMPLATE" "fraud-screen block"
for p in "${patterns[@]}"; do
  present "$p" "$GT" "pattern name"
  present "$p" "$TEMPLATE" "pattern name"
done

# 5. No stray template placeholders in eval assets (fixture must be feedable as-is).
for f in "$FIXTURE" "$GT"; do
  if grep -qF -- '{{' "$f"; then fail "'{{' placeholder found in ${f##*/}"; fi
done

# 6. Detection rules ⇄ fixture ⇄ answer sheet. The scorer reads detection.json; if its
#    planted/control text ever drifts from the fixture, the harness would be scoring a
#    review against something the reviewer was never shown.
mapfile -t detect_texts < <(python3 -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
for f in d["frauds"]:
    print(f["planted_text"])
for c in d["controls"]:
    print(c["control_text"])
' "$DETECT") || fail "detection.json is not readable JSON"
[ "${#detect_texts[@]}" -eq 8 ] || fail "detection.json should carry 6 frauds + 2 controls, got ${#detect_texts[@]}"
for s in "${detect_texts[@]}"; do
  present "$s" "$FIXTURE" "detection.json entry"
  present "$s" "$GT" "detection.json entry vs answer sheet"
done
python3 -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["pass_threshold"] == 5 and d["marginal_threshold"] == 4, "thresholds must match GROUND-TRUTH scoring"
for f in d["frauds"]:
    assert f["anchor_any"] and f["mechanism_any"], f["id"]
' "$DETECT" || fail "detection.json thresholds/rules malformed (pass>=5, marginal 4, rules non-empty)"
present "PASS ≥ 5/6 catches · MARGINAL 4/6 · FAIL ≤ 3/6." "$GT" "answer-sheet scoring rule"

# 7. Model/effort routing contract, DERIVED from config/routing.env. This catches silent
#    quota and quality regressions (a downgraded lead, a capped effort tier) and any copy
#    of a model name that a bump left behind.
present "$GAUNTLET_LEAD_MODEL_DISPLAY $GAUNTLET_LEAD_EFFORT ORCHESTRATOR" "$SKILL" "first-pass lead route"
present "$GAUNTLET_WORKER_MODEL_DISPLAY (\`$GAUNTLET_WORKER_MODEL_ID\`) $GAUNTLET_WORKER_EFFORT" "$SKILL" "Claude worker route"
present "$GAUNTLET_REVIEWER_MODEL_DISPLAY $GAUNTLET_REVIEWER_JUDGE_EFFORT judge" "$SKILL" "reviewer judge route"
present "$GAUNTLET_REVIEWER_MODEL_DISPLAY $GAUNTLET_REVIEWER_LANE_EFFORT research" "$SKILL" "reviewer worker route"
present "$GAUNTLET_WORKER_MODEL_DISPLAY (\`$GAUNTLET_WORKER_MODEL_ID\`), ${GAUNTLET_WORKER_EFFORT}-effort" "$MASTER" "master-prompt Claude worker route"
present "GAUNTLET_CODEX_SAFETY_FALLBACK=0" "$RUNNER" "reviewer cross-model fallback disable"
present "Skip deep-research Phase 7.6 optional cross-model critique inside Gauntlet" "$SKILL" "bounded external-review topology"
absent "$GAUNTLET_LEAD_MODEL_DISPLAY max" "$SKILL" "stale first-pass lead route"
absent "$GAUNTLET_REVIEWER_MODEL_DISPLAY max" "$SKILL" "stale reviewer judge route"

# The reviewer template must carry routing TOKENS, not hardcoded names — and must render
# to exactly the configured route. That is what makes a model bump a one-line edit.
present "{{REVIEWER_MODEL}} {{REVIEWER_JUDGE_EFFORT}} JUDGE" "$TEMPLATE" "review-template judge token"
absent "$GAUNTLET_REVIEWER_MODEL_DISPLAY" "$TEMPLATE" "hardcoded reviewer name in a tokenized template"
absent "$GAUNTLET_LEAD_MODEL_DISPLAY" "$TEMPLATE" "hardcoded lead name in a tokenized template"
rendered="$(mktemp)"; trap 'rm -f "$rendered"' EXIT
if bash "$RENDER" "$TEMPLATE" > "$rendered" 2>/dev/null; then
  present "$GAUNTLET_REVIEWER_MODEL_DISPLAY $GAUNTLET_REVIEWER_JUDGE_EFFORT JUDGE" "$rendered" "rendered judge route"
  present "$GAUNTLET_REVIEWER_MODEL_DISPLAY, ${GAUNTLET_REVIEWER_LANE_EFFORT}-effort research lanes/subagents" "$rendered" "rendered lane route"
  present "$GAUNTLET_LEAD_MODEL_DISPLAY orchestrator with $GAUNTLET_WORKER_MODEL_DISPLAY" "$rendered" "rendered first-pass provenance"
  grep -qE '\{\{(LEAD|WORKER|REVIEWER)_[A-Z_]*\}\}' "$rendered" &&
    fail "routing token left unresolved after rendering the reviewer template"
else
  fail "render_prompt.sh could not render the reviewer template"
fi

# Executable route (what the launcher would actually pass to codex), also derived.
lane_route="$(env -u REVIEWER_EFFORT -u REVIEWER_WORKER_EFFORT -u PREFLIGHT QC_MODE=lane \
  "$RUNNER" --show-routing)" || fail "lane routing probe failed"
judge_route="$(env -u REVIEWER_EFFORT -u REVIEWER_WORKER_EFFORT -u PREFLIGHT QC_MODE=judge \
  "$RUNNER" --show-routing)" || fail "judge routing probe failed"
# Lane route: lane effort, preflight OFF (4 parallel lanes must not ping codex 4x).
# Judge route: judge effort, preflight ON (fail fast before the long judge wall).
[ "$lane_route" = "model=$GAUNTLET_REVIEWER_MODEL_ID effort=$GAUNTLET_REVIEWER_LANE_EFFORT qc_mode=lane preflight=0 safety_fallback=disabled" ] ||
  fail "lane executable route mismatch: $lane_route"
[ "$judge_route" = "model=$GAUNTLET_REVIEWER_MODEL_ID effort=$GAUNTLET_REVIEWER_JUDGE_EFFORT qc_mode=judge preflight=1 safety_fallback=disabled" ] ||
  fail "judge executable route mismatch: $judge_route"

# 8. Stale model names anywhere else in the core tree (prose cannot be tokenized).
if ! bash "$ROOT/scripts/routing_lint.sh" >/dev/null 2>&1; then
  fail "routing_lint.sh found stale model names (run it directly for the file:line list)"
fi

# 9. Behavioral self-tests — the tiers that exercise code rather than strings.
#    Each is runnable standalone for detail; here they are pass/fail gates.
run_tier() {  # run_tier <script> <label>
  if [ ! -f "$1" ]; then fail "missing $2: ${1##*/}"; return; fi
  if ! bash "$1" >/dev/null 2>&1; then
    fail "$2 failed (run it directly for detail: bash eval/${1##*/})"
  fi
}
run_tier "$SCRIPT_DIR/qc_selftest.sh"        "QC-gate behavioral self-test"
run_tier "$SCRIPT_DIR/preflight_selftest.sh" "preflight reachability/quota self-test"
run_tier "$SCRIPT_DIR/launcher_smoke.sh"     "launcher contract + artifact-equivalence smoke test"
run_tier "$SCRIPT_DIR/score_selftest.sh"     "offline reviewer-scoring regression harness"

if [ "$fails" -eq 0 ]; then
  echo "PASS: fixture/answer-sheet/detection sync, routing contract vs config/routing.env, and all"
  echo "      four behavioral tiers (QC gate · preflight · launcher contract · review scorer)."
  exit 0
else
  echo "FAILED: $fails assertion(s) — see lines above."
  exit 1
fi
