#!/usr/bin/env bash
# Gauntlet eval — deterministic structural gate for the planted-fraud fixture.
# No LLM, no network: asserts the fixture, the answer sheet, and the reviewer
# template's MONEY-FIGURE FRAUD SCREEN stay in sync. PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCEN="$SCRIPT_DIR/scenarios/planted-fraud-money-figures"
FIXTURE="$SCEN/08_preliminary_report.md"
GT="$SCEN/GROUND-TRUTH.md"
TEMPLATE="$ROOT/references/reviewer_prompt_template.md"
MASTER="$ROOT/references/master_research_prompt.md"
SKILL="$ROOT/SKILL.md"
RUNNER="$ROOT/scripts/run_review.sh"

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
need "$TEMPLATE" || { echo "FAILED: reviewer template missing"; exit 1; }
need "$MASTER" || { echo "FAILED: master prompt missing"; exit 1; }
need "$SKILL" || { echo "FAILED: skill instructions missing"; exit 1; }
need "$RUNNER" || { echo "FAILED: reviewer runner missing"; exit 1; }

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

# 6. Model/effort routing contract. This catches silent quota and quality regressions:
#    Opus 5/high lead -> Sonnet 5/xhigh workers; GPT-5.6 Sol/xhigh judge ->
#    GPT-5.6 Sol/high workers.
present "Opus 5 high ORCHESTRATOR" "$SKILL" "first-pass lead route"
present 'Sonnet 5 (`claude-sonnet-5`) xhigh' "$SKILL" "Claude worker route"
present "GPT-5.6 Sol xhigh judge" "$SKILL" "reviewer judge route"
present "GPT-5.6 Sol high research" "$SKILL" "reviewer worker route"
present 'REVIEWER_EFFORT="${REVIEWER_EFFORT:-xhigh}"' "$RUNNER" "reviewer default effort"
present 'Sonnet 5 (`claude-sonnet-5`), xhigh-effort' "$MASTER" "master-prompt Claude worker route"
present "GPT-5.6 Sol xhigh JUDGE" "$TEMPLATE" "review-template judge route"
present "GPT-5.6 Sol, high-effort research lanes/subagents" "$TEMPLATE" "review-template worker route"
present "GAUNTLET_CODEX_SAFETY_FALLBACK=0" "$RUNNER" "reviewer cross-model fallback disable"
present "Skip deep-research Phase 7.6 optional cross-model critique inside Gauntlet" "$SKILL" "bounded external-review topology"
absent "Opus 5 max" "$SKILL" "stale first-pass lead route"
absent "Opus 5 xhigh" "$SKILL" "stale first-pass lead effort"
absent "GPT-5.6 Sol max" "$SKILL" "stale reviewer judge route"

lane_route="$(env -u REVIEWER_EFFORT -u REVIEWER_WORKER_EFFORT QC_MODE=lane \
  "$RUNNER" --show-routing)" || fail "lane routing probe failed"
judge_route="$(env -u REVIEWER_EFFORT -u REVIEWER_WORKER_EFFORT QC_MODE=judge \
  "$RUNNER" --show-routing)" || fail "judge routing probe failed"
[ "$lane_route" = "model=gpt-5.6-sol effort=high qc_mode=lane safety_fallback=disabled" ] ||
  fail "lane executable route mismatch: $lane_route"
[ "$judge_route" = "model=gpt-5.6-sol effort=xhigh qc_mode=judge safety_fallback=disabled" ] ||
  fail "judge executable route mismatch: $judge_route"

if [ "$fails" -eq 0 ]; then
  echo "PASS: planted-fraud eval and Gauntlet model/effort routing contract are structurally sound."
  exit 0
else
  echo "FAILED: $fails assertion(s) — see lines above."
  exit 1
fi
