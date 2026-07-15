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

fails=0
fail() { printf 'FAIL: %s\n' "$1"; fails=$((fails+1)); }
need() { [ -f "$1" ] || { fail "missing file: $1"; return 1; }; }
present() { # $1=needle $2=file $3=label — whitespace-normalized fixed-string match,
            # so prose reflows/line wraps cannot silently break the gate
  tr -s '[:space:]' ' ' < "$2" | grep -qF -- "$1" || fail "$3 not found in ${2##*/}: $1"
}

need "$FIXTURE" || { echo "FAILED: fixture missing"; exit 1; }
need "$GT" || { echo "FAILED: answer sheet missing"; exit 1; }
need "$TEMPLATE" || { echo "FAILED: reviewer template missing"; exit 1; }

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

if [ "$fails" -eq 0 ]; then
  echo "PASS: planted-fraud eval is structurally sound (6 frauds + 2 controls documented; screen in sync with the reviewer template)."
  exit 0
else
  echo "FAILED: $fails assertion(s) — see lines above."
  exit 1
fi
