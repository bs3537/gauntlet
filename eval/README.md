# Gauntlet eval — planted-fraud validation (smoke-grade)

Off-the-runtime-path validation assets for the reviewer's **money-figure fraud screen**
(the six-pattern lens at the end of D1 in `references/reviewer_prompt_template.md`).
Nothing in the live pipeline loads this directory; deleting `eval/` changes no runtime
behavior.

## Layout

- `check.sh` — deterministic structural gate (bash; no LLM, no network).
- `scenarios/planted-fraud-money-figures/08_preliminary_report.md` — a FICTIONAL,
  clearly-bannered, doctored preliminary report (Exemplar Grid Industries, "XGRD")
  carrying **exactly six planted money-figure frauds** — one per screen pattern — plus
  **two clean controls** (correct figures a trigger-happy reviewer might wrongly flag).
  Named `08_preliminary_report.md` to match the Stage-2 input, so it can be fed through
  the real review path.
- `scenarios/planted-fraud-money-figures/GROUND-TRUTH.md` — the assessor answer sheet:
  planted text → pattern → what's wrong → correct value → expected reviewer response,
  plus the scoring rule. **Never include it in anything shown to the model under test.**

## The cheap check (run after any edit to the screen, fixture, or answer sheet)

    bash eval/check.sh

Asserts, deterministically: fixture and answer sheet exist and carry their banners; each
of the six planted snippets appears verbatim in BOTH the fixture and the answer sheet;
both clean controls appear in both; the six pattern names appear in the answer sheet AND
in the reviewer template's fraud-screen block (so the eval and the runtime lens cannot
silently drift apart); and neither eval file contains a stray placeholder brace. Prints
PASS and exits 0 on success; prints each failed assertion and exits 1 otherwise.

## The live smoke run (optional, manual, quota-heavy)

Feed the fixture through the real Stage-2 review and score the result:

1. Create a scratch run dir and copy the fixture in as `08_preliminary_report.md`.
   (Stricter blind variant: strip the leading banner blockquote at feed time; the
   answer sheet stays withheld either way.)
2. Assemble the judge prompt per `SKILL.md` Stage 2 step 3, substituting the header
   placeholders with the fixture's own header values (company Exemplar Grid Industries,
   ticker XGRD, as-of 2026-07-15, price $24.80) and the panel-disabled lane-findings
   line, then run `scripts/run_review.sh` with `PANEL=0`.
3. Score the returned review against `GROUND-TRUTH.md`: a **catch** = the review
   identifies the planted text and the correct mechanism. **Pass ≥ 5/6 · marginal 4/6 ·
   fail ≤ 3/6.** Flagging a clean control as a fraud is a precision miss — record it.

Because the company is fictional, every planted fraud is catchable from **internal
evidence alone** (cross-section contradictions, the report's own tables); no live web
access is needed to catch any of them, and web searches will simply find nothing.

## Limitations

One fixture, synthetic figures, LLM-judged live runs: **a smoke test, not a benchmark.**
It validates that the screen exists, stays in sync, and that its patterns are catchable —
it does not measure reviewer quality. Extend it by adding a new scenario directory with
its own `GROUND-TRUTH.md` and wiring the new snippets into `check.sh`.
