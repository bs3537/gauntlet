# Gauntlet eval — validation tiers

Off-the-runtime-path validation for the Stage-2 adversarial reviewer. Nothing in the live
pipeline loads this directory; deleting `eval/` changes no runtime behavior.

Four of the five tiers are **deterministic** (no LLM, no network, no codex, no quota) and run
on every commit and every push. The fifth spends one real review call and is opt-in.

## Layout

- `check.sh` — the gate: structural sync + routing contract + it runs every self-test below.
- `qc_selftest.sh` — behavior of the Stage-2 QC gate.
- `preflight_selftest.sh` — behavior of the codex preflight (reachability vs quota vs dead).
- `launcher_smoke.sh` — launcher contract + artifact equivalence between launcher paths.
- `score_selftest.sh` — behavior of the review scorer, against canned reviews.
- `score_review.py` — scores a returned review against a scenario's answer sheet.
- `live_review.sh` — the real, scored, end-to-end review run (quota-heavy).
- `scenarios/planted-fraud-money-figures/`
  - `08_preliminary_report.md` — a FICTIONAL, clearly-bannered, doctored preliminary report
    (Exemplar Grid Industries, "XGRD") carrying **exactly six planted money-figure frauds** —
    one per screen pattern — plus **two clean controls** (correct figures a trigger-happy
    reviewer might wrongly flag). Named to match the Stage-2 input so it can be fed through
    the real review path.
  - `GROUND-TRUTH.md` — the human-readable answer sheet: planted text → pattern → what's
    wrong → correct value → expected reviewer response, plus the scoring rule.
    **Never include it in anything shown to the model under test.**
  - `detection.json` — the same answer sheet in machine-readable form (anchor + mechanism
    rules per fraud, accusation rules per control) so scoring is a script, not an eyeball.
  - `canned/` — three fixed review artifacts of known grade (full-catch, regressed,
    trigger-happy). They are what let CI test the scorer with no model in the loop.

## The deterministic gate

    make check          # or: bash eval/check.sh

Enable it locally on every commit with `make hooks`; CI runs it via
`.github/workflows/ci.yml`. It asserts:

- **Sync** — each of the six planted snippets and both controls appear verbatim in the
  fixture, the answer sheet AND `detection.json`; the six pattern names appear in the answer
  sheet and in the reviewer template's fraud-screen block; banners present; no stray `{{`.
- **Routing** — every model/effort claim in `SKILL.md`, the master prompt and the reviewer
  template matches `config/routing.env`; the reviewer template carries routing **tokens**
  rather than hardcoded names and renders to the configured route; the executable route
  (`run_review.sh --show-routing`) matches; `scripts/routing_lint.sh` finds no stale model
  name anywhere else in the tree.
- **Behavior** — all four self-tests pass. Run any of them directly for detail.

## The live scored run (quota-heavy, opt-in)

    make eval-live                      # or: bash eval/live_review.sh [run_dir]
    BLIND=1 FAIL_ON_CONTROL_FP=1 bash eval/live_review.sh

It copies the fixture in as `08_preliminary_report.md`, assembles the judge prompt (routing
tokens resolved from the config, run-specific placeholders filled, `PANEL=0` lane line),
launches the real Stage-2 review, QC-gates it, then scores the result against
`detection.json`: **PASS ≥ 5/6 · MARGINAL 4/6 · FAIL ≤ 3/6**, with clean-control false
positives reported as precision misses. `BLIND=1` strips the fixture's leading banner so the
reviewer is not told it is a test. The answer sheet is never part of the prompt.

Exit codes: 0 at/above the bar · 1 below it · 2 setup failure · 3 the review failed QC ·
4 codex quota-limited · 124 timeout.

Because the company is fictional, every planted fraud is catchable from **internal evidence
alone** (cross-section contradictions, the report's own tables); no live web access is needed.

## Limitations

One fixture, synthetic figures: **a smoke test, not a benchmark.** It answers "does the
reviewer catch planted money-figure frauds at all?", nothing finer. Extend it by adding a
scenario directory with its own `GROUND-TRUTH.md` and `detection.json`, and wiring its
snippets into `check.sh`.
