# Two-Model Adversarial Equity Research Pipeline — Master Prompt v2 (Approved Plan, 2026-07-15)

## Context

Today the workflow is two manual stages: (1) the Universal Master Equity Research Prompt runs in Claude Code (Opus 4.8 max) including a **self-review** Phase 7, then (2) the finished report is manually pasted into Codex CLI where GPT-5.6 Sol max runs the separate ADVERSARIAL RESEARCH REVIEWER prompt. Nothing feeds the review back into the report — the review arrives after the final report is already written.

Target: **one pasteable master prompt** where Claude Code (Opus 4.8) does the research, launches GPT-5.6 Sol via `codex exec` in a shell as the adversarial reviewer of the *preliminary* report, saves the review to disk, **adjudicates** each reviewer finding (accept/reject with independent verification), applies sustained corrections, and only then writes the final report. This reproduces the "reviewer critiques the draft before the final is generated" loop the user read about, with a genuinely different model supplying the second perspective.

## My recommendation on the reviewer-prompt question (asked explicitly)

**Use the separate ADVERSARIAL RESEARCH REVIEWER prompt (the GPT-5.6 Sol one) as the embedded Phase 7 payload, and delete the master prompt's current Phase 7 rubric** — keep old Phase 7 only as a labeled degraded-mode fallback when codex is unreachable. Rationale:

1. The standalone reviewer prompt is purpose-built for **cross-model** review: it explicitly hunts the two failure modes only a second model can catch (unchallenged blind spots, confident-recall hallucination) and mandates verification *outside the report's frame*. The master prompt's Phase 7 rubric was written for self-review; a same-model reviewer shares the generator's priors and its own evidence-ledger frame, so it structurally cannot supply the "missing second perspective."
2. The standalone prompt has stronger reviewer governance: anti-gaming attestation, reviewer anti-hallucination rules, the three-state distinction (VERIFIED WRONG ≠ UNSUPPORTED ≠ UNVERIFIABLE), score bands with anti-clustering — which makes the score a **machine-checkable gate** for the adjudication loop.
3. Keeping both rubrics would produce two competing scores and ~double review runtime for no marginal coverage.
4. Two things from old Phase 7 are worth keeping, relocated: (a) the finance-mechanics checks its D6 has and the reviewer prompt lacks — rerun the Python models, reconcile `06_model_outputs.csv`, audit the per-share bridge / dilution / scenario-probabilities-sum — ported into the embedded reviewer prompt as a short **Model Recomputation addendum** to D1 (codex *can* execute the models: it has shell + full disk access); (b) the mandate "correct working research, ledger, and models for every sustained issue before Phase 8; preserve audit trail; do not mention the review in the polished report" — moved into the new adjudication phase.

## Verified technical foundation (read this session)

- `~/.claude/skills/model-council-fast/scripts/run_codex.sh` (hardened 2026-07-14): `codex exec --skip-git-repo-check --cd <scratch> -m gpt-5.6-sol -s danger-full-access -c tools.web_search=true -c model_reasoning_effort=<effort> --json -o <output_file> - < <prompt_file>`. Prompt via **stdin** (no ARG_MAX risk); `-o` captures only the final message; `FUSION_TIMEOUT` bounds the run (default 1800s, exit 124 on timeout); deadline-bounded transient retry (429/5xx); structured-safety fallback to gpt-5.5 xhigh; writes `<output>.routing.json`.
- `~/.codex/config.toml`: default model gpt-5.6-sol, sandbox `danger-full-access`, `approval_policy=never`, `web_search="live"`, MCP servers **scite, perplexity, biomcp, fmp** — the reviewer has native web search + the same connectors the reviewer prompt's domain routing names. codex-cli 0.144.4 at `~/.local/bin/codex`.
- `run_judge.sh` precedent: gpt-* judge = same runner with `FUSION_TIMEOUT=$FUSION_JUDGE_TIMEOUT` (3000s) and effort `max`.
- Constraints this design must respect: Claude Code Bash foreground cap is 600s → the review **must launch `run_in_background: true`**; `-o` pointer gotcha → reviewer must EMIT the full review as its final message *and* save a copy into the run dir (double capture); `FUSION_FAST` must be pinned to `0` (fast mode flips to workspace-write + `--ignore-user-config`, killing MCPs and run-dir writes); `danger-full-access` means codex can read/write the run dir even though its cwd is a throwaway scratch — so all run-dir paths in the payload must be **absolute**.

## Deliverables (2 files, both in ~/Documents)

1. `~/Documents/Universal_Master_Equity_Research_Prompt_v2_TwoModel_20260715.md` — the combined single master prompt.
2. `~/Documents/TwoModel_Research_Pipeline_Plan_20260715.md` — this plan, saved for the user with a clickable path (explicitly requested).

No skill/scripts/settings changes. The prompt *references* the existing `run_codex.sh` (reuse of hardened infra) and embeds a raw `codex exec` fallback command in case the skill moves.

## Master Prompt v2 — section-by-section spec

Phases 0–6 and all evidence rules stay **verbatim** except the deltas below.

### 1. INPUT BLOCK — add reviewer fields
`REVIEWER_MODEL` (default `gpt-5.6-sol`), `REVIEWER_EFFORT` (default `max`), `REVIEWER_TIMEOUT_S` (default `3600`), `REVIEW_ROUNDS` (default 1, auto-escalates to 2 — see gate), plus the rule that all review artifacts live in the run's output directory.

### 2. Required-files list — v2 numbering
01–07 unchanged; then:
- `08_preliminary_report.md` (NEW — full Phase-8-format draft, the review target)
- `09_reviewer_prompt.txt` (assembled payload)
- `10_adversarial_review_gpt56sol.md` (+ `.routing.json` sidecar) — replaces old `08_adversarial_review.md`
- `11_adjudication_and_corrections.md` (NEW)
- round 2 if triggered: `08b_…`, `10b_…`, `11b_…`
- `FINAL_REPORT.md`, `VERIFICATION_LOG.md` (gains a required "External review round(s)" section: exact command, model/effort, duration, exit status, score, disposition counts)

### 3. Phase 0 addition — codex preflight (fail fast)
Before research starts: `codex exec --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort=low - <<<'Reply OK'` bounded to ~120s. On failure: warn the user, plan for the degraded-mode self-review fallback, continue research.

### 4. Phase 6 addition — assemble the review target
New step 6C: write `08_preliminary_report.md` in the full Phase-8 report format (so the reviewer can audit presentation/D7 on the real artifact). Snapshot core artifacts to `review_backup/` before launching the reviewer (insurance against the known codex file-clobber failure mode).

### 5. Phase 7A — external adversarial review (replaces old Phase 7)
Orchestration steps the prompt spells out:
1. Assemble `09_reviewer_prompt.txt` = adapted reviewer prompt (below) + payload header (ticker, as-of date/time, verified current price, absolute run-dir path, artifact table) + **full inline text** of `08_preliminary_report.md` + output contract restated at the end.
2. Launch via the hardened runner, in background (Bash `run_in_background: true`):
   `FUSION_FAST=0 FUSION_TIMEOUT=$REVIEWER_TIMEOUT_S FUSION_CODEX_MODEL=$REVIEWER_MODEL FUSION_RUN_STAGE=review bash ~/.claude/skills/model-council-fast/scripts/run_codex.sh "$RUN_DIR/09_reviewer_prompt.txt" "$RUN_DIR/10_adversarial_review_gpt56sol.md" $REVIEWER_EFFORT`
   Fallback raw command (if runner missing): `codex exec --skip-git-repo-check --cd "$RUN_DIR" -m gpt-5.6-sol -s danger-full-access -c tools.web_search=true -c model_reasoning_effort=max --json -o "$RUN_DIR/10_adversarial_review_gpt56sol.md" - < "$RUN_DIR/09_reviewer_prompt.txt"`
3. QC gate on completion (exit 0 or file present is NOT success): non-empty, > 3 KB, contains VERDICT + /100 score + dimension table + ≥3 issues + claim-verification table + compliance line. One relaunch on failure/timeout.
4. Degraded mode (both attempts fail): run old Phase 7 self-review in-session, save as `10_selfreview_fallback.md`, and **label** the final report's verification log "external cross-model review unavailable — same-model self-review used."

### 6. Embedded reviewer prompt — user's text verbatim plus exactly 5 adaptations
1. Header: "the research report above" → "the PRELIMINARY report included below; supporting artifacts at the absolute paths listed" (paths table: 01–08 files).
2. D1 **Model Recomputation addendum**: rerun `04_…py` and `05_…py`, reconcile outputs to `06_model_outputs.csv`, audit per-share bridge, dilution treatment, scenario probabilities sum to 100% (ports old-Phase-7 D6).
3. Tooling note: native web search + scite/fmp/biomcp/perplexity MCPs + shell; "independent verification" = sources NOT in `02_source_manifest.csv`.
4. Output contract: write the full review to `$RUN_DIR/10_adversarial_review_gpt56sol.md` AND emit the complete review (not a pointer) as the final message; read-only on all other run-dir files.
5. Payload header supplies as-of date, ticker, price so the reviewer doesn't trust its training cutoff.

### 7. Phase 7B — adjudication by the first-pass model (NEW, the core loop)
- Enumerate every reviewer finding (Top-3 issues, claim-verification rows, blind spots, calibration verdict).
- For each CRITICAL/MODERATE finding: **independently verify before disposition** — open the reviewer's cited source; reopen own ledger locator. Disposition ACCEPT / PARTIAL / REJECT. Anti-sycophancy + anti-defensiveness rules: ACCEPT requires independent confirmation (reviewer assertions are claims, not truth — reviewers hallucinate too); REJECT requires citing the specific evidence/locator the reviewer missed. MINOR/presentation items: batch-apply, no verification burden.
- Sustained findings: update ledger (new rows verified first, per lock rule), fix models, rerun Python, regenerate outputs; record rating/target before → after.
- Write `11_adjudication_and_corrections.md`: one row per finding — severity | disposition | verification evidence | change made | value impact.
- Old Phase 7 mandates preserved here: correct all working files before Phase 8; keep the audit trail; never mention the review process in the polished final report.

### 8. Phase 7C — gate and bounded round 2
- Proceed to Phase 8 when: reviewer score ≥ 60 AND no sustained thesis-breaking CRITICAL, after corrections.
- Auto round 2 (max one): if score < 60 OR a sustained CRITICAL flips the rating → rebuild affected phases, write `08b_preliminary_report_r2.md`, re-run Phase 7A/7B once (reviewer prompt notes prior score for the multi-round rule).
- Hard stop: if round 2 still < 60, deliver with an explicit LOW-confidence banner and the unresolved findings listed — never silently ship.

### 9. Phase 8 — unchanged content rules; source updates
Builds FINAL_REPORT.md from *corrected* artifacts; "reopen every file" list updated to v2 numbering; quality gate gains one item: "every sustained review finding is reflected; every rejected finding has a documented, evidence-backed rejection."

## Implementation steps (after approval)

1. Save this plan to `~/Documents/TwoModel_Research_Pipeline_Plan_20260715.md`; give the user the clickable path.
2. Author `Universal_Master_Equity_Research_Prompt_v2_TwoModel_20260715.md`: original text preserved verbatim where unchanged; splice in the deltas above; embed the adapted reviewer prompt in full.
3. **Plumbing smoke test** (cheap, no full research run): stub run dir with a 5-line fake `08_preliminary_report.md` + minimal reviewer prompt; launch the exact Phase 7A runner command at `low` effort, `FUSION_TIMEOUT=600`, in background; verify stdin delivery, `-o` capture, run-dir write-back, routing json, exit code, and the QC gate logic. Also run the Phase 0 preflight ping once.
4. Consistency audit of the v2 prompt: no orphan refs to old `08_adversarial_review.md` / old Phase 7; file numbering coherent end-to-end; reviewer-prompt block intact (diff against user's original text); phase cross-references correct.
5. Write a memory file recording the v2 prompt path, the runner invocation, and the FUSION_FAST=0 / absolute-path / double-capture gotchas; add MEMORY.md pointer.

## Verification

- Smoke test above is the executable acceptance test for orchestration (observed exit code, both capture paths non-empty, QC gate passes/fails correctly on a deliberately truncated file).
- Prompt-level check: grep the v2 file for `08_adversarial_review.md` (must be absent), `10_adversarial_review` (present), `run_in_background` guidance (present), `FUSION_FAST=0` (present).
- Full-pipeline validation is a real research run (hours, user-triggered) — out of scope here; recommend first live use on a small-cap name the user already has ground truth for (e.g., DERM or CAMP, where known traps exist to see if the reviewer catches them).

## Risks and mitigations

- **codex weekly/5-hour limit exhaustion mid-review** → runner exits nonzero; one relaunch, then labeled self-review fallback (pipeline never ships unreviewed silently).
- **Reviewer hallucination** → adjudication verifies reviewer sources before accepting; disposition table records evidence.
- **`-o` pointer gotcha / codex file clobber** → double capture + `review_backup/` snapshot + read-only instruction.
- **Runtime** → adds roughly 30–60 min review (3600s cap) + 15–45 min adjudication to a research run; costs land on the existing ChatGPT plan quota, not per-token API.
- **Stale runner path** → raw `codex exec` fallback embedded in the prompt.

---

## Addendum (2026-07-15, same session)

User redirected packaging mid-implementation: deliver as a **Claude Code skill named `gauntlet`** (`~/.claude/skills/gauntlet/`) instead of a standalone pasteable prompt. Single source of truth lives in the skill (`references/master_research_prompt.md`, `references/reviewer_prompt_template.md`, `scripts/run_review.sh`, `SKILL.md`); no duplicate prompt copy in ~/Documents, to avoid deploy drift. First pass: Opus 4.8 max in-session. Reviewer: GPT-5.6 Sol max via codex. All other plan content unchanged.

**Smoke-test finding (same session):** the plan's choice of the model-council-fast `run_codex.sh` was wrong — that tree's `_fusion_lib.sh` hardcodes `FUSION_FAST=1` (council is fast-only), which silently forced fast mode (routing json `"fast": true`, effort high, workspace-write). Fixed: `run_review.sh` now delegates to the hybrid-model-fusion runner in standard mode with `FUSION_RUN_STAGE=gauntlet_review` (the literal stage `review` would attach hybrid's peer-review `--output-schema` JSON contract). Re-smoked after the fix.
