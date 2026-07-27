#!/usr/bin/env bash
# qc_selftest.sh — deterministic behavioral test of run_review.sh's QC gate.
# No LLM, no network, no codex: drives `run_review.sh --qc-only` (which never launches
# the reviewer) against crafted review fixtures and asserts the pass/fail decision.
# Locks in the hardened gate: numeric NN/100 score + range, optional ticker echo,
# claim-verification table rows, pointer-stub screen, size floor. PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../scripts/run_review.sh"
[ -f "$RUNNER" ] || { echo "FAILED: runner missing: $RUNNER"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/gauntlet-qc.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# ~79 bytes per line, so line count is a direct size lever for the size-floor and
# pointer-stub thresholds (floor 3000, pointer screen fires below 2x floor = 6000).
pad() { yes 'padding: independent verification of the claim against its primary-source locator.' | head -n "${1:-600}"; }

tbl() {  # tbl [n_data_rows] — a claim-verification table with a header + separator
  local n="${1:-3}" i
  echo '| # | Claim | Verdict | Evidence |'
  echo '|---|-------|---------|----------|'
  for i in $(seq 1 "$n"); do
    echo "| $i | XGRD claim $i | Confirmed | FY25 10-K p.$((60 + i)) |"
  done
}

fails=0
check() { # check <label> <expected_rc> <QC_MODE> <QC_EXPECT_TICKER|-> <review_file>
  local label="$1" want="$2" mode="$3" tick="$4" rf="$5" got env_tick=()
  [ "$tick" != "-" ] && env_tick=(QC_EXPECT_TICKER="$tick")
  env QC_MODE="$mode" "${env_tick[@]}" REVIEW_FILE="$rf" \
    bash "$RUNNER" --qc-only "$TMP" 1 >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then
    printf 'PASS  %-52s (rc=%s)\n' "$label" "$got"
  else
    printf 'FAIL  %-52s (rc=%s, wanted %s)\n' "$label" "$got" "$want"; fails=$((fails+1))
  fi
}

# --- fixtures -----------------------------------------------------------------
# 1. A complete, well-formed judge review of ticker XGRD.
good="$TMP/good.md"; {
  echo '# ADVERSARIAL REVIEW — Exemplar Grid Industries (XGRD)'
  echo 'VERDICT: the thesis survives with material caveats; decision-ready in band B.'
  echo 'Overall 87/100 + band B. XGRD prior round: none.'
  echo '## CLAIM VERIFICATION TABLE'
  tbl 4
  echo 'COMPLIANCE: anti-gaming and anti-hallucination rules met.'
  pad
} > "$good"

# 2. Same, but the score is a bare '/100' with no number (old gate would pass this).
noscore="$TMP/noscore.md"; {
  echo 'VERDICT: survives. Overall score: /100 (band withheld). XGRD XGRD.'
  echo 'CLAIM VERIFICATION TABLE:'; tbl 4; echo 'COMPLIANCE: rules met.'; pad
} > "$noscore"

# 3. Numeric score out of range.
overrange="$TMP/overrange.md"; {
  echo 'VERDICT: survives. Overall 150/100 band A. XGRD XGRD.'
  echo 'CLAIM VERIFICATION TABLE:'; tbl 4; echo 'COMPLIANCE: rules met.'; pad
} > "$overrange"

# 4. A well-formed review, but of the WRONG company (never names XGRD).
wrongco="$TMP/wrongco.md"; {
  echo 'VERDICT: survives. Overall 82/100 band B. Acme Beta Corp (ABCD) ABCD.'
  echo '## CLAIM VERIFICATION TABLE'
  echo '| # | Claim | Verdict | Evidence |'
  echo '|---|-------|---------|----------|'
  echo '| 1 | ABCD FY25 revenue | Confirmed | FY25 10-K p.61 |'
  echo '| 2 | ABCD net debt | Refuted | FY25 10-K p.88 |'
  echo 'COMPLIANCE: rules met.'; pad
} > "$wrongco"

# 5. A too-small file (below the size floor).
tiny="$TMP/tiny.md"; printf 'VERDICT 87/100 CLAIM VERIFICATION COMPLIANCE XGRD XGRD\n' > "$tiny"

# 6. Every token and a real score, but the claim-verification table is an EMPTY heading —
#    the review announced the section and did none of the verification work.
notable="$TMP/notable.md"; {
  echo 'VERDICT: survives. Overall 74/100 band B. XGRD XGRD.'
  echo '## CLAIM VERIFICATION TABLE'
  echo '(to be completed in a follow-up pass)'
  echo 'COMPLIANCE: rules met.'; pad
} > "$notable"

# 7. The `-o` pointer gotcha: a padded-but-small signpost message, not a review.
#    ~3.7 KB — clears the 3000-byte floor, so ONLY the pointer screen can catch it.
pointer="$TMP/pointer.md"; {
  echo 'VERDICT: complete. Overall 88/100 band A. XGRD XGRD.'
  echo 'CLAIM VERIFICATION TABLE:'; tbl 3
  echo 'COMPLIANCE: rules met.'
  echo 'The full adversarial review has been written to /home/u/Documents/XGRD/10_review.md'
  pad 40
} > "$pointer"

# 8. A genuine full-length review that ALSO mentions writing the canonical file — the
#    pointer screen must NOT reject this (that would be the expensive false positive).
longptr="$TMP/longptr.md"; {
  echo 'VERDICT: survives. Overall 79/100 band B. XGRD XGRD.'
  echo '## CLAIM VERIFICATION TABLE'; tbl 6
  echo 'COMPLIANCE: rules met.'
  echo 'This review was also saved to /home/u/Documents/XGRD/10_review.md as required.'
  pad 600
} > "$longptr"

# --- assertions ---------------------------------------------------------------
check "judge: complete review, ticker enforced"          0 judge XGRD "$good"
check "judge: complete review, no ticker check"          0 judge -    "$good"
check "judge: '/100' present but NO number -> reject"    3 judge XGRD "$noscore"
check "judge: score 150/100 out of range -> reject"      3 judge XGRD "$overrange"
check "judge: wrong company (no XGRD) -> reject"         3 judge XGRD "$wrongco"
check "judge: wrong company but ticker check OFF"        0 judge -    "$wrongco"
check "judge: empty claim-verification table -> reject"  3 judge XGRD "$notable"
check "judge: pointer stub above size floor -> reject"   3 judge XGRD "$pointer"
check "lane: pointer stub caught by size-only gate too"  3 lane  -    "$pointer"
check "judge: long review naming its own file -> pass"   0 judge XGRD "$longptr"
check "lane: size-only gate passes"                      0 lane  -    "$good"
check "any: below size floor -> reject"                  3 judge XGRD "$tiny"

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: QC gate behavioral self-test (12/12)."; exit 0
else
  echo "FAILED: $fails assertion(s)."; exit 1
fi
