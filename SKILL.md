---
name: gauntlet
description: >-
  Explicit-invocation-only two-model adversarial equity research pipeline (Gauntlet): Opus 4.8 max
  runs the universal institutional master research prompt (Phases 0-6: evidence ledger, competitive
  moat, catalyst PoS ensembles, Python valuation, convexity) and drafts a preliminary report; GPT-5.6
  Sol max then attacks that draft as an external adversarial reviewer via the codex CLI (blind-spot
  protocol, independent verification, model recomputation, scored /100); the first-pass model
  adjudicates every finding with evidence (accept/partial/reject), applies sustained corrections, and
  only then writes the final Wall-Street-style report. Use only when the user affirmatively asks to
  run gauntlet (e.g. "/gauntlet TICKER", "run the gauntlet on X"). Never auto-trigger from a ticker,
  "deep dive", "analyze", research breadth, adversarial framing, or inferred usefulness.
---

# Gauntlet — two-model adversarial equity research

## Invocation Gate

Opt-in only. Run this skill only when the active user request affirmatively invokes **gauntlet**
("/gauntlet", "run gauntlet on <ticker>", "use the gauntlet skill"). A ticker, "deep dive",
"comprehensive research", or "adversarial review" language is not authorization by itself. Negated,
quoted, historical, and comparative references do not count.

## What it is

One invocation produces institutional equity research that must **survive a hostile second model
before it ships**. The generator and the reviewer are different frontier models from different
vendors, so the review supplies the missing second perspective a single-model pass cannot: the
generator's unchallenged blind spots and confident-recall hallucinations.

```text
Stage 0  Intake + codex preflight (fail fast)
Stage 1  FIRST PASS — Opus 4.8 max ORCHESTRATOR over a research panel: deep-research
         ultradeep = 4 Opus 4.8 xhigh lanes (+ Opus xhigh subagents); it QCs/verifies/
         synthesizes -> 01..07 artifacts + 08_preliminary_report.md (full draft)
Stage 2  EXTERNAL ADVERSARIAL REVIEW — GPT-5.6 Sol PANEL: 4 GPT-5.6 Sol xhigh research
         lanes attack the draft, then a GPT-5.6 Sol max JUDGE synthesizes them (codex,
         scripts/run_review.sh, background) -> 10_adversarial_review_gpt56sol.md (/100, QC-gated)
Stage 3  ADJUDICATION — first-pass model dispositions EVERY finding with independent
         verification -> corrections + 11_adjudication_and_corrections.md
Stage 4  GATE — proceed, or ONE bounded round-2 review of the corrected draft
Stage 5  FINAL REPORT — master prompt Phase 8 from corrected artifacts -> FINAL_REPORT.md
```

| Role | Model | Where | Effort |
|---|---|---|---|
| First-pass orchestrator + adjudicator | Opus 4.8 (intended) | this Claude Code session | max |
| First-pass research lanes / subagents (×4+) | Opus 4.8 | deep-research ultradeep + Agent subagents | xhigh |
| Reviewer research lanes (×4) | GPT-5.6 Sol | `codex exec` (launched by Stage 2) | xhigh |
| Reviewer orchestrator / judge | GPT-5.6 Sol | `codex exec` (launched by Stage 2) | max (gpt-5.5/xhigh structured-safety fallback) |

Both sides fan out, then judge: the Opus 4.8 max orchestrator drives four Opus 4.8 xhigh
deep-research lanes (plus targeted subagents) and admits only verified evidence; the GPT-5.6 Sol
max judge synthesizes four GPT-5.6 Sol xhigh adversarial lanes into one scored review. The reviewer
side gets native live web search, shell, and the scite/fmp/biomcp/perplexity MCPs from
`~/.codex/config.toml`; it can open the run directory's artifacts and **execute the Python models**.

**Session-model check (Stage 0):** this skill is designed for session model **Opus 4.8 at `/effort
max`**. If the live session model differs (e.g. Fable 5), tell the user in one line and proceed with
the session model, recording the deviation in `VERIFICATION_LOG.md`. Do not silently substitute.

## Files

- `references/master_research_prompt.md` — the full universal master research prompt (Phases 0–6 and 8, v2 file set, degraded-mode self-review appendix). Stage 1 and Stage 5 execute it.
- `references/reviewer_prompt_template.md` — the adversarial reviewer prompt with `{{PLACEHOLDERS}}`. Stage 2 assembles it.
- `scripts/run_review.sh` — preflight + codex launch (hardened runner with raw fallback) + QC gate.

## Stage 0 — Intake and preflight

1. Fill the master prompt's INPUT BLOCK from the user's request (company, ticker, as-of date, price
   to be verified, horizons, constraints). Default run directory:
   `~/Documents/<TICKER>_Gauntlet_<YYYYMMDD>/` — create it; everything lives there. `RUN_DIR` must
   always be used as an **absolute path**.
2. Session-model check (above).
3. Codex preflight (fail fast before hours of research):
   `timeout 150 codex exec --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort=low -o "$RUN_DIR/preflight_codex.txt" - <<<'Reply with exactly: OK'` then check the file contains `OK`.
   (Equivalently, Stage 2 can be launched with `PREFLIGHT=1`, which runs the same ping first.)
   On failure: warn the user that Stage 2 will fall back to the labeled degraded-mode self-review
   unless codex recovers, and continue.

## Stage 1 — First-pass research (in-session, orchestrated fan-out)

Read `references/master_research_prompt.md` and execute **Phases 0 through 6 exactly** (evidence
rules, 300+/50+ source breadth, ledger lock, Python models, bounds, convexity). Deliverables
`01_…` through `07_…` plus `08_preliminary_report.md` — the complete Phase-8-format draft (all 15
sections). Do not write `FINAL_REPORT.md` yet.

You are the **orchestrator/reviewer/judge of a research panel**, not a solo researcher (see the
master prompt's "Research execution model — Gauntlet fan-out"):
1. Invoke the **deep-research skill at `ultradeep`** — its four concurrent lanes are your four
   **Opus 4.8 xhigh** research subagents, one per non-overlapping evidence stream (demand/TAM/epi;
   competition/moat/pipeline; filings/financials/valuation inputs; catalysts/regulatory/legal/mgmt).
   It chains Search-as-Code as its second pass.
2. Spawn extra **Opus 4.8 xhigh** Agent subagents for residual gaps; each gets a complete brief and
   never spawns its own subagents.
3. QC every lane/subagent artifact, independently verify load-bearing claims, and admit ONLY
   verified evidence into `03_evidence_ledger.csv` (lock rule) and the draft; lane disagreements
   become `[SOURCE CONFLICT]` items. The `deep-research` and `valuation` skills must be installed
   (see Dependencies); the biotech valuation delegates to the `valuation` engine per master prompt 4B.

## Stage 2 — External adversarial review (GPT-5.6 Sol panel via codex)

The review is a **four-lane panel judged by GPT-5.6 Sol max**. Four GPT-5.6 Sol xhigh research
lanes attack the draft on different rubric slices, then one GPT-5.6 Sol max judge verifies,
reconciles, and synthesizes them into the single scored `/100` review. **All five codex calls are
orchestrated HERE, by this session** — a `codex exec` leaf never spawns its own subagents. Set
`PANEL=0` to skip the lanes and run the single-judge review only (quota-constrained runs); Stage 4
round 2 is always judge-only.

1. **Assemble the four lane prompts** `09_reviewer_lane{1..4}.txt`: each is a dimension-scoped
   adversarial brief over `08_preliminary_report.md`, using ABSOLUTE `RUN_DIR` paths, told to
   cite-or-abstain and write labeled findings — lane 1 = D1 factual grounding + independently rerun
   and verify the `04`/`05` models; lane 2 = D2 blind spots + missed signal (independent searches);
   lane 3 = D3–D4 counter-thesis + logical chain; lane 4 = D5–D6 source reliability + calibration.
2. **Launch the four lanes in parallel** (Bash `run_in_background: true`), reusing the hardened
   launcher in lane/QC mode:
   ```bash
   for i in 1 2 3 4; do
     QC_MODE=lane REVIEWER_EFFORT=xhigh \
     PROMPT_FILE="$RUN_DIR/09_reviewer_lane$i.txt" \
     REVIEW_FILE="$RUN_DIR/10_reviewer_lane$i.md" \
     CAPTURE_FILE="$RUN_DIR/10_reviewer_lane$i.capture.md" \
       bash <skill_dir>/scripts/run_review.sh "$RUN_DIR" 1 &
   done; wait
   ```
   QC each `10_reviewer_lane$i.md` (size gate). A dropped lane is logged in `VERIFICATION_LOG.md`
   and the judge proceeds with the survivors; do not block the pipeline on one failed lane.
3. **Assemble the judge prompt** `09_reviewer_prompt.txt`: copy everything below the
   `<!-- TEMPLATE BEGINS -->` marker in `references/reviewer_prompt_template.md`, substitute every
   `{{PLACEHOLDER}}` (company, ticker, as-of, verified price, absolute `RUN_DIR`, `REVIEW_OUT`,
   prior-round line), inline the four `10_reviewer_lane*.md` at `{{LANE_FINDINGS}}` (or the literal
   `none — single-pass review (panel disabled)` when `PANEL=0`), and inline the FULL text of
   `08_preliminary_report.md` at `{{PRELIMINARY_REPORT_FULL_TEXT}}`. Verify no `{{` remains:
   `grep -c '{{' 09_reviewer_prompt.txt` must print 0.
4. **Launch the judge in background** (GPT-5.6 Sol max; foreground Bash caps at 600 s and the judge
   runs 20–60 min; you are re-invoked when it exits; never sleep-poll):
   ```bash
   bash <skill_dir>/scripts/run_review.sh "$RUN_DIR" 1
   ```
   Defaults: `REVIEWER_MODEL=gpt-5.6-sol`, `REVIEWER_EFFORT=max`, `QC_MODE=judge`,
   `REVIEWER_TIMEOUT_S=3600`. The script pins `FUSION_FAST=0`, snapshots `01–08` into
   `review_backup_r1/`, delegates to the hardened `hybrid-model-fusion/scripts/run_codex.sh` in
   standard mode (raw `codex exec` fallback built in), and double-captures the review. After exit,
   sanity-check `10_review_capture_r1.md.routing.json`: expect `"fast": false` and
   `"resolved_effort"` = the effort you passed.
5. **QC the judge on exit** — exit code 0 means the review exists AND passed the gate (>3 KB;
   VERDICT, /100 score, claim-verification table, compliance line all present). Exit 3 = QC fail,
   124 = timeout, 1 = launch/auth failure. Script exit 0 is necessary but not sufficient: open
   `10_adversarial_review_gpt56sol.md` and confirm it is a real review of THIS company that
   reflects the lane findings.
6. **One relaunch** on any judge failure. If the relaunch also fails: execute the degraded-mode
   self-review appendix in `references/master_research_prompt.md`, save it as
   `10_selfreview_fallback.md`, and carry the label "external cross-model review unavailable —
   same-model self-review used" into `VERIFICATION_LOG.md` and the confidence classification.
7. Log to `VERIFICATION_LOG.md` ("External review round(s)"): lanes launched/QC'd, exact judge
   command, model, effort, duration, exit status, routing-json contents, reviewer score.

## Stage 3 — Adjudication (first-pass model; the core loop)

The reviewer's output is **claims, not truth** — reviewers hallucinate too. But it exists because
your own pass has blind spots — so deference and defensiveness are both failure modes.

0. **Pre-analysis first**: BEFORE opening the review, write 5–10 lines at the top of
   `11_adjudication_and_corrections.md` naming which of your own claims you consider most
   vulnerable and why (guards against anchoring on the reviewer's frame).
1. **Enumerate** every finding: Top-3 issues, every claim-verification row with verdict
   Refuted/Unsupported/Unverifiable, every confirmed blind spot, model-recomputation mismatches,
   the calibration verdict.
2. **Disposition each CRITICAL and MODERATE finding only after independent verification**: open the
   reviewer's cited source yourself; reopen your own ledger locator; rerun the disputed
   computation. Then ACCEPT / PARTIAL / REJECT.
   - ACCEPT requires your own confirmation of the reviewer's evidence — "the reviewer said so" is
     not evidence.
   - REJECT requires citing the specific source/locator the reviewer missed or misread — "I
     already verified this" is not a rebuttal.
   - Two materially different failed verification attempts → disposition UNRESOLVED, label
     `[UNKNOWN - NOT VERIFIED]`, and treat the affected claim conservatively in the final report.
3. MINOR/presentation findings: batch-apply without per-item verification.
4. **Apply sustained corrections**: update `03_evidence_ledger.csv` (new rows verified before
   entry, per the lock rule), fix `04_/05_` models, rerun them, regenerate `06_model_outputs.csv`,
   update `07_working_research.md`. Record rating and target before → after.
5. Complete `11_adjudication_and_corrections.md`: the pre-analysis, then one row per finding —
   `# | reviewer severity | finding | disposition | verification evidence (source + locator) |
   change made | value impact` — then a closing summary (reviewer score, accepted/rejected/
   unresolved counts, rating/target delta).

## Stage 4 — Gate and bounded round 2

- **Proceed to Stage 5** when sustained corrections are applied AND the reviewer score is ≥ 60 AND
  no sustained CRITICAL finding flips the rating.
- **Round 2 (maximum one)** when score < 60 OR a sustained CRITICAL flips the rating: rebuild the
  affected phases, write `08b_preliminary_report_r2.md`, assemble `09b_reviewer_prompt_r2.txt`
  (prior-round line carries the round-1 score; `{{LANE_FINDINGS}}` = `none — round 2 is judge-only`),
  run `run_review.sh "$RUN_DIR" 2` (judge-only — round 2 skips the research lanes to stay bounded),
  adjudicate into `11b_adjudication_r2.md`.
- **Hard stop**: if round 2 still scores < 60, still deliver — but with an explicit LOW-CONFIDENCE
  banner at the top of `FINAL_REPORT.md` and the unresolved findings listed in the verification
  log. Never silently ship an unreviewed or failed-review report.

## Stage 5 — Final report

Execute master prompt **Phase 8** from the CORRECTED artifacts (reopen every run-dir file first,
including the review and adjudication files). The final quality gate includes v2 item 11: every
sustained finding reflected; every rejected finding has a documented, evidence-backed rejection.
Do not mention the adversarial-review process in the polished report body; it lives in
`VERIFICATION_LOG.md` and the appendix.

## Presenting

Give the user: rating + weighted target + expected return in the first sentence; the path to
`FINAL_REPORT.md` and the run directory; the reviewer's score and 2–3 highest-impact adjudication
outcomes (what the second model caught, what was rejected and why). Do not paste the whole report
into chat.

## Failure modes and gotchas (load-bearing)

- **`FUSION_FAST` must stay 0** (the script pins it): fast mode switches codex to
  `workspace-write` + `--ignore-user-config`, killing MCP connectors and run-dir writes.
- **Absolute paths only** in the reviewer payload — the reviewer's cwd is a throwaway scratch dir;
  it reaches `RUN_DIR` only via `danger-full-access` + absolute paths.
- **`-o` pointer gotcha**: `-o` captures only the final message; if the model ends with "review
  saved to X", the capture is a stub. The DELIVERY CONTRACT (emit full review + write canonical
  file) plus the script's promote-on-QC logic is the mitigation — keep both.
- **Reviewer file clobber**: reviewer is instructed read-only outside its output file, and the
  script snapshots `01–08` to `review_backup_r<round>/` before launch. Restore from there if needed.
- **codex quota (the panel multiplies it)**: the reviewer panel is FIVE codex calls — 4 GPT-5.6 Sol
  xhigh lanes + 1 GPT-5.6 Sol max judge — each 15–60 min, so one Gauntlet run can consume a large
  share of the ChatGPT-plan 5-hour/weekly limits. Set `PANEL=0` for a single-judge review when quota
  is tight. Exit 1 with auth/limit errors in the stream log → wait or fall back; the runner's
  structured-safety fallback (gpt-5.5 xhigh) only covers safety blocks, not quota.
- **first-pass fan-out cost**: deep-research `ultradeep` runs four Opus 4.8 xhigh lanes plus their
  Search-as-Code second pass; combined with the codex panel, a full Gauntlet run is deliberately
  heavy. This is intended for high-stakes names, not routine screening.
- **Never sleep-poll** the background review; the harness re-invokes you when it exits.

## Tuning (env, all optional)

| Var | Default | Meaning |
|---|---|---|
| `REVIEWER_MODEL` | `gpt-5.6-sol` | codex model for the review |
| `REVIEWER_EFFORT` | `max` | `model_reasoning_effort` for the review |
| `REVIEWER_TIMEOUT_S` | `3600` | hard wall for one review attempt |
| `QC_MIN_BYTES` | `3000` | minimum review size to pass QC |
| `PREFLIGHT` | `0` | `1` = script pings codex before launching the review |
| `PANEL` | `1` (intended) | orchestration flag: `0` = skip the 4 research lanes, run the single GPT-5.6 Sol max judge only |
| `QC_MODE` | `judge` | `judge` = full scored-review gate; `lane` = size-only gate for a research lane |
| `PROMPT_FILE` / `REVIEW_FILE` / `CAPTURE_FILE` | round-derived | per-lane path overrides so `run_review.sh` runs each lane and the judge |

## Dependencies

**Required companion skills (install alongside gauntlet):**
- **`deep-research`** — Stage 1 first-pass fan-out runs it at `ultradeep` (four Opus 4.8 xhigh lanes).
- **`search-as-code`** — deep-research chains it as its second pass.
- **`valuation`** — Stage 1 valuation delegates dev-stage biotech rNPV to `valuation/scripts/valuation_engine.py` (master prompt 4B); mirrored in `~/.codex/skills/valuation/` so the reviewer can rerun it.
- **`hybrid-model-fusion`** — its `scripts/run_codex.sh` is the hardened codex launcher `run_review.sh` prefers.

`codex` on PATH and authenticated (preflight checks this). Prefers the hardened
`~/.claude/skills/hybrid-model-fusion/scripts/run_codex.sh` (transient retry, safety fallback,
routing json); `run_review.sh` falls back to raw `codex exec` with identical flags if it is gone.
Never swap in the `model-council-fast` runner: its `_fusion_lib.sh` hardcodes `FUSION_FAST=1`
(fast-only skill), which silently degrades the review (workspace-write sandbox, no MCPs, word-capped
fast preamble, effort forced to high). Also never pass `FUSION_RUN_STAGE=review` to the hybrid
runner — that literal stage attaches hybrid's peer-review `--output-schema` JSON contract; the
script uses `gauntlet_review`.
Claude-tree-only skill: no codex/gemini/grok tree copy is needed — codex is the *target* here, not
a host.
