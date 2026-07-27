#!/usr/bin/env bash
# score_selftest.sh — the OFFLINE tier of the reviewer regression harness.
#
# The live scored run (eval/live_review.sh) needs a real codex call and real quota. This
# tier needs neither: it runs the same scorer against canned review artifacts whose grade is
# known in advance, so CI can prove — deterministically, on every commit — that the scoring
# harness still discriminates a good review from a regressed one. If this breaks, the live
# score means nothing either.
#
# Asserts: full-catch review scores 6/6 PASS with no precision miss · a regressed review
# scores below the bar and FAILS · a trigger-happy review is reported as a precision miss
# (and fails under --fail-on-control-fp) · an empty review scores 0 · matches must be LOCAL
# (a mechanism word far from the figure is not a catch). PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCEN="$SCRIPT_DIR/scenarios/planted-fraud-money-figures"
SCORER="$SCRIPT_DIR/score_review.py"
CANNED="$SCEN/canned"
[ -f "$SCORER" ] || { echo "FAILED: scorer missing: $SCORER"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/gauntlet-score.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

fails=0
run_score() {  # run_score <review> [extra args...] -> writes $TMP/out.json, echoes rc
  local review="$1"; shift
  python3 "$SCORER" --review "$review" --scenario "$SCEN" --json "$TMP/out.json" --quiet "$@" >/dev/null 2>&1
  echo $?
}
field() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$TMP/out.json" "$1"; }

assert() {  # assert <label> <actual> <expected>
  if [ "$2" = "$3" ]; then printf 'PASS  %-56s (%s)\n' "$1" "$2"
  else printf 'FAIL  %-56s (%s, wanted %s)\n' "$1" "$2" "$3"; fails=$((fails+1)); fi
}

# 1. A reviewer that catches everything.
rc="$(run_score "$CANNED/review_full_catch.md")"
assert "full-catch review: exit code"            "$rc"                      "0"
assert "full-catch review: catches"              "$(field catches)"         "6"
assert "full-catch review: verdict"              "$(field verdict)"         "PASS"
assert "full-catch review: precision misses"     "$(field control_false_positives)" "0"

# 2. A regressed reviewer — the regression this whole tier exists to catch.
rc="$(run_score "$CANNED/review_partial.md")"
assert "regressed review: exit code (nonzero)"   "$rc"                      "1"
assert "regressed review: catches"               "$(field catches)"         "3"
assert "regressed review: verdict"               "$(field verdict)"         "FAIL"

# 3. Good recall, bad precision: both clean controls wrongly attacked.
rc="$(run_score "$CANNED/review_trigger_happy.md")"
assert "trigger-happy review: catches"           "$(field catches)"         "5"
assert "trigger-happy review: precision misses"  "$(field control_false_positives)" "2"
assert "trigger-happy review: passes on recall alone" "$rc"                 "0"
rc="$(run_score "$CANNED/review_trigger_happy.md" --fail-on-control-fp)"
assert "trigger-happy review: fails with --fail-on-control-fp" "$rc"        "1"

# 4. Degenerate input scores zero rather than erroring.
printf 'No comment.\n' > "$TMP/empty_review.md"
rc="$(run_score "$TMP/empty_review.md")"
assert "empty review: exit code (nonzero)"       "$rc"                      "1"
assert "empty review: catches"                   "$(field catches)"         "0"

# 5. Locality: the figure and a mechanism word must appear NEAR each other. A review that
#    mentions $31.20 in one place and the word "stale" pages away has not caught F1 — this
#    is what stops keyword soup from scoring as adversarial work.
{
  echo 'The report states a market capitalization derived from $31.20 per share.'
  yes 'Filler sentence about segment mix that says nothing about pricing vintage at all.' | head -n 40
  echo 'Separately, the peer-set commentary reads as stale relative to the 2026 landscape.'
} > "$TMP/far_apart.md"
run_score "$TMP/far_apart.md" >/dev/null
assert "distant figure/mechanism is NOT scored as a catch" "$(field catches)" "0"

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: offline reviewer-scoring regression harness."; exit 0
else
  echo "FAILED: $fails assertion(s)."; exit 1
fi
