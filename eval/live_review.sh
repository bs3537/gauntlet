#!/usr/bin/env bash
# live_review.sh — the LIVE tier of the reviewer regression harness (quota-heavy, opt-in).
#
# Feeds the planted-fraud fixture through the REAL Stage-2 review path (PANEL=0, one judge
# call) and scores the returned review against the answer sheet automatically. This is the
# only test that measures the product's core promise — that a hostile second model actually
# catches planted errors — end to end, so it is worth its quota when the reviewer prompt,
# the fraud screen, or the reviewer model changes.
#
# It replaces a hand-run, eyeball-scored procedure: assembly, launch, QC and scoring are all
# scripted, so the result is a number and an exit code rather than an impression.
#
#   bash eval/live_review.sh [run_dir]
#
# Env:
#   BLIND=1               strip the fixture's leading FICTIONAL banner before feeding it
#                         (stricter: the reviewer is not told the report is a test)
#   MIN_CATCHES=N         override the pass bar (default: detection.json pass_threshold)
#   FAIL_ON_CONTROL_FP=1  also fail if a clean control was flagged as a fraud
#   KEEP=1                keep the run dir even on success
#   (plus everything run_review.sh honors: REVIEWER_MODEL, REVIEWER_EFFORT, PREFLIGHT, …)
#
# Exit: 0 scored at or above the bar · 1 below the bar · 2 setup/assembly failure ·
#       3 the review itself failed QC · 4 codex quota-limited · 124 review timed out.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCEN="$SCRIPT_DIR/scenarios/planted-fraud-money-figures"
FIXTURE="$SCEN/08_preliminary_report.md"
TEMPLATE="$ROOT/references/reviewer_prompt_template.md"

for f in "$FIXTURE" "$TEMPLATE" "$SCEN/detection.json" "$ROOT/scripts/run_review.sh" \
         "$ROOT/scripts/render_prompt.sh" "$SCRIPT_DIR/score_review.py"; do
  [ -f "$f" ] || { echo "[live] missing required file: $f" >&2; exit 2; }
done
command -v codex >/dev/null 2>&1 || { echo "[live] codex CLI not on PATH — this tier needs it" >&2; exit 2; }

RUN_DIR="${1:-$(mktemp -d "${TMPDIR:-/tmp}/gauntlet-live-eval.XXXXXX")}"
mkdir -p "$RUN_DIR"
RUN_DIR="$(realpath "$RUN_DIR")"
echo "[live] run dir: $RUN_DIR"

# 1. The fixture becomes the Stage-2 input, under its real name.
if [ "${BLIND:-0}" = "1" ]; then
  # Drop the leading banner blockquote so the reviewer is not told this is a test.
  awk 'BEGIN{skip=1} skip && (/^>/ || /^[[:space:]]*$/) {next} {skip=0; print}' \
    "$FIXTURE" > "$RUN_DIR/08_preliminary_report.md"
  echo "[live] blind mode: fixture banner stripped"
else
  cp "$FIXTURE" "$RUN_DIR/08_preliminary_report.md"
fi

# 2. Assemble the judge prompt: routing tokens from config/routing.env, then the
#    run-specific placeholders. The answer sheet is NEVER read here — only the assessor
#    (score_review.py, after the fact) may see it.
"$ROOT/scripts/render_prompt.sh" "$TEMPLATE" --body > "$RUN_DIR/09_reviewer_template_rendered.txt" || exit 2
python3 - "$SCEN/detection.json" "$RUN_DIR" <<'PY' || exit 2
import json, pathlib, sys

meta = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
run = pathlib.Path(sys.argv[2])
template = (run / "09_reviewer_template_rendered.txt").read_text(encoding="utf-8")
report = (run / "08_preliminary_report.md").read_text(encoding="utf-8")

values = {
    "{{COMPANY}}": meta["company"],
    "{{TICKER}}": meta["ticker"],
    "{{ASOF_DATETIME}}": f"{meta['asof']} 17:00 America/New_York",
    "{{CURRENT_PRICE}}": f"{meta['price']} (fixture header, as of {meta['asof']}; synthetic)",
    "{{RUN_DIR}}": str(run),
    "{{REVIEW_OUT}}": str(run / "10_adversarial_review_gpt56sol.md"),
    "{{PRIOR_ROUND_LINE}}": "PRIOR ROUND: none (this is round 1).",
    "{{LANE_FINDINGS}}": "none — single-pass review (panel disabled)",
    "{{PRELIMINARY_REPORT_FULL_TEXT}}": report,
}
for token, value in values.items():
    template = template.replace(token, value)

out = run / "09_reviewer_prompt.txt"
out.write_text(template, encoding="utf-8")
left = template.count("{{")
print(f"[live] assembled {out} ({len(template)} chars, {left} unsubstituted placeholders)")
raise SystemExit(1 if left else 0)
PY

# 3. Real Stage-2 launch — single judge, panel disabled. Exit codes pass straight through.
echo "[live] launching the judge (PANEL=0); this is one full-length codex call"
QC_EXPECT_TICKER="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["ticker"])' "$SCEN/detection.json")" \
  bash "$ROOT/scripts/run_review.sh" "$RUN_DIR" 1
launch_rc=$?
if [ "$launch_rc" -ne 0 ]; then
  echo "[live] review did not pass QC (rc=$launch_rc) — nothing to score; artifacts kept in $RUN_DIR" >&2
  exit "$launch_rc"
fi

# 4. Score it against the answer sheet.
score_args=(--review "$RUN_DIR/10_adversarial_review_gpt56sol.md" --scenario "$SCEN"
            --json "$RUN_DIR/eval_score.json")
[ -n "${MIN_CATCHES:-}" ] && score_args+=(--min-catches "$MIN_CATCHES")
[ "${FAIL_ON_CONTROL_FP:-0}" = "1" ] && score_args+=(--fail-on-control-fp)
python3 "$SCRIPT_DIR/score_review.py" "${score_args[@]}"
score_rc=$?

echo "[live] score written to $RUN_DIR/eval_score.json"
if [ "$score_rc" -eq 0 ] && [ "${KEEP:-0}" != "1" ] && [ -z "${1:-}" ]; then
  echo "[live] (set KEEP=1 to retain the scratch run dir)"
fi
exit "$score_rc"
