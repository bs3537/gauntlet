---
name: hybrid-model-fusion
description: >-
  Explicit-invocation-only hybrid Model Fusion workflow: independent Opus 4.8, Grok 4.5, Gemini 3.5 Flash, and GPT-5.6 Sol reports, blind peer ranking, deterministic aggregate scorecard, and an Opus 4.8 max final report. Use only when the user affirmatively asks to use or run hybrid-model-fusion. Never auto-trigger from research, analysis, investment work, technical decisions, consensus, blind-spot checks, complexity, or inferred usefulness.
---

# Hybrid Model Fusion

## Invocation Gate

This skill is opt-in only. Run it only when the active user request affirmatively names `hybrid-model-fusion` or explicitly asks to use/run the Hybrid Model Fusion workflow. A request for multiple viewpoints, consensus, peer ranking, a hard decision, or a blind-spot check is not authorization by itself. Negated, quoted, historical, and comparative references do not count. No separate hybrid-fusion-fast workflow exists here; do not infer one from the word "fast."

Hybrid Model Fusion is a separate skill from `model-fusion`. Use it when the user wants the hybrid workflow:

```text
independent model reports -> blind cross-rank/scoring -> aggregate scorecard -> Opus 4.8 final judge
```

The required output is file-based: individual model reports, each model's blind ranking/critique of the other outputs, an aggregate scorecard, and the final judge report — each report saved as Markdown **and** a styled HTML copy (see Step 6). Do not create any other UI or dashboard unless the user explicitly asks.

## Core Rule

Keep Stage 1 independent. Panelists must not see each other's reports until all primary reports are saved. Blind peer review happens only after Stage 1 is complete.

## Model Roles

- `Opus 4.8`: panelist and peer reviewer through Claude Code CLI, and the **default final judge** (see below).
- `Grok 4.5`: panelist and peer reviewer through Grok Build CLI (`grok`) at `high` effort. Its full tool suite (Perplexity/FMP/Scite/BioMCP MCP + web) comes from `~/.grok/config.toml` and `~/.claude.json`; `~/.grok/AGENTS.md` supplies the single-pass panelist doctrine. `FUSION_GROK_MODEL` overrides the model id.
- `Gemini 3.5 Flash`: panelist and peer reviewer through Antigravity `agy` at High.
- `GPT-5.6 Sol`: panelist and peer reviewer through Codex CLI at `max` effort. An allowlisted structured Codex safety error triggers one `gpt-5.5`/`xhigh` retry (`FUSION_CODEX_SAFETY_FALLBACK=0` disables it).

Artifact stems match their models: `report_opus4.8.md`, `report_grok4.5.md`, `report_gemini3.5flash.md`, `report_gpt5.6sol.md` — used across run folders, review manifests, and eval fixtures. The `grok4.5` stem runs the Grok Build CLI panelist (`grok-4.5`); the `gpt5.6sol` stem runs the Codex panelist (`gpt-5.6-sol`, safety fallback `gpt-5.5`).

The Grok panelist has no safety-fallback path; the Codex (GPT-5.6 Sol) panelist does — one allowlisted structured-safety retry with `gpt-5.5`/`xhigh`, recorded in `report_gpt5.6sol.md.routing.json` and propagated into the blind response mapping.

The final judge defaults to Opus 4.8 with max effort (run via Claude Code); `run_judge.sh` dispatches on the judge model family, so a `gpt-*`/`codex` `FUSION_JUDGE_MODEL` override runs the judge through Codex instead. Judge blinding is on by default: the judge sees anonymous, run-randomized `Response A/B/C/D` labels and no response mapping, so it cannot favor its own manufacturer's report (the self-preference / same-vendor bias). `run_judge.sh` then **de-anonymizes the finished report** back to real model names (via `response_mapping.json`) so the agree / disagree / unique-insight tables show which model said what. Set `FUSION_JUDGE_BLIND=0` only when model identities must be disclosed during adjudication (this also skips de-anon, since the report is already named). Residual caveat: blinding removes the *labeled* bias, not any style-fingerprint the judge might infer. If the final judge cannot be run through `scripts/run_judge.sh`, disclose the fallback.

## Standard Run Folder

Create one folder per run:

```bash
slug=$(printf '%s' "<short-topic>" | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9_-' | cut -c1-50)
RUN_DIR="$HOME/hybrid_fusion/${slug}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"
```

Save the user's prompt verbatim:

```bash
$EDITOR "$RUN_DIR/original_prompt.md"
```

## Step 0: Preflight

```bash
bash <skill_dir>/scripts/detect_panel.sh "$RUN_DIR"
```

The full hybrid workflow expects `claude`, `grok`, `codex`, and `agy`. If one model is missing, either stop and report the missing dependency or run a downgraded best-effort panel only if the user accepts the limitation.

## Step 0.5: FinTwit / X Sentiment (stock topics only)

If the task concerns a specific stock/ticker, pull live X/FinTwit sentiment as shared panel context.
Identify the ticker; if none is identifiable, skip this step. (Hybrid has no fast mode, so this runs
whenever there is a ticker; set `SKIP_FINTWIT=1` to bypass.)

```bash
FINTWIT_SCRIPT="${CODEX_HOME:-$HOME/.codex}/skills/fintwit/scripts/fintwit.sh"
[ -x "$FINTWIT_SCRIPT" ] || FINTWIT_SCRIPT="$HOME/.claude/skills/fintwit/scripts/fintwit.sh"
bash "$FINTWIT_SCRIPT" "$RUN_DIR" "<TICKER>"   # writes $RUN_DIR/fintwit_context.md
```

When you build each panel prompt in Step 1, prepend the contents of `$RUN_DIR/fintwit_context.md` (if it
exists) under a `## FinTwit / X Sentiment Context [Tier 4 — social sentiment only; do NOT anchor material
claims]` header, so every panelist sees the same context. It is **Tier-4 social signal** — never a basis
for a material claim and never overrides structured data or primary sources; the judge also auto-ingests
it. Cost ~$0.05–0.15/ticker.

## Evaluation Harness

For skill changes or model-roster changes, run the DRACO-style evaluation harness before trusting the change:

```bash
bash <skill_dir>/eval/run_eval.sh --dry-run --out "$HOME/hybrid_fusion/eval_$(date +%Y%m%d_%H%M%S)"
```

The harness compares arms under the same grading rubric: `best-solo`, `model-fusion`, `hybrid`, `fable-panelist`, and `self-fusion`. Dry-run mode validates task/rubric plumbing without calling live CLIs. Real evaluation runs should use fresh tasks, at least three independent grading passes, and a held-out non-panelist judge where available.

Harness-gated experiments are listed in `config/experimental_variants.json`: shared evidence pack, bounded single-round critique, and PoLL-style three-judge adjudication. Do not enable them by default; compare them in the harness first.

For a checkpointed end-to-end run from a saved prompt:

```bash
bash <skill_dir>/scripts/run_hybrid.sh --prompt "$RUN_DIR/original_prompt.md" --topic "<short-topic>"
```

## Step 1: Independent Panel Reports

Read `references/panel.md` and `references/research_routing.md`.

Build one panel prompt per model. Each prompt should contain the user task verbatim and a short instruction to produce a complete Markdown research/analysis report. Do not assign personas or lenses. Add the same tool-guidance paragraph to each panelist: use available web or structured tools when needed, cite primary sources for material claims, keep the report complete but avoid unnecessary verbosity, and treat FinTwit/social context as Tier 4 only.

Apply the same research routing to every panelist: native search/fetch first as the wide Search-as-Code-style
discovery and current-verification pass; Perplexity Search MCP second for alternate queries, competing
narratives, and gaps; then open the underlying primary documents for load-bearing claims. If Perplexity is
unavailable in one runtime, that lane continues native-only and discloses the limitation. Preserve material
provider discrepancies rather than silently merging them.

Run the panel via the reliability launcher (DEFAULT). Panel inputs are MANDATORY — it guarantees
all panelist reports: ALWAYS PARALLEL (all panelists concurrent in both modes, regardless of RAM/deep-research), per-panelist validate → single-pass retry → escalate;
it also sanitizes agy output and prevents orphaned processes.

```bash
# mode "normal"|"deep": BOTH run ALL panelists in PARALLEL, always (RAM-based sequential downgrade removed 2026-06-25). "deep" only tunes agy/retry timeouts for heavier deep-research panels.
bash <skill_dir>/scripts/run_panel.sh "$RUN_DIR" normal max
```

If `run_panel.sh` returns non-zero, a panelist could not produce a valid report after retries —
surface that and do NOT proceed with fewer than 3 panel reports. (Low-level fallback to drive one
panelist manually: `bash <skill_dir>/scripts/run_{claude,grok,codex,gemini}.sh PROMPT OUT EFFORT`.)
Tunables via env: `FUSION_PANEL_RETRIES`, `FUSION_PANEL_TIMEOUT`, `FUSION_DEEP_PARALLEL_RAM_GB`,
`FUSION_AGY_PRINT_TIMEOUT` (see `scripts/fusion_reliability.sh`).

Expected primary reports:

```text
report_opus4.8.md
report_grok4.5.md
report_gemini3.5flash.md
report_gpt5.6sol.md
```

## Step 2: Build Blind Review Packets

After all primary reports are saved:

```bash
python3 <skill_dir>/scripts/build_review_packets.py "$RUN_DIR"
```

This creates:

```text
response_mapping.json
review_prompt_opus4.8.txt
review_prompt_grok4.5.txt
review_prompt_gemini3.5flash.txt
review_manifest.json
```

The review prompts use anonymous `Response A/B/C` labels and exclude counted self-review.

## Step 3: Blind Peer Reviews

Run the blind reviews via the reliability launcher (DEFAULT). Reviewer inputs are OPTIONAL — it
proceeds on QUORUM (default 2 valid reviews) plus a short grace, so a slow/flaky panelist can never stall the run:

```bash
bash <skill_dir>/scripts/run_reviews.sh "$RUN_DIR" max
```

2 of 3 reviews is fine — `aggregate_reviews.py` handles a missing review, and empty outputs are set
aside as `review_<model>.md.empty`. Tunables: `FUSION_REVIEW_TIMEOUT`, `FUSION_REVIEW_QUORUM`,
`FUSION_REVIEW_GRACE`.

Each review must include strict JSON with ranked order, dimension scores, confidence, and notes for the judge. See `references/peer_review_rubric.md`.

## Step 4: Aggregate Rankings

```bash
python3 <skill_dir>/scripts/aggregate_reviews.py "$RUN_DIR"
```

This parses the review outputs and writes:

```text
review_opus4.8.json
review_grok4.5.json
review_gemini3.5flash.json
review_gpt5.6sol.json
aggregate_scorecard.json
aggregate_scorecard.md
contested_claims.json
contested_claims.md
```

Use the scorecard as an audit surface, not as an automatic winner.

## Step 5: Final Judge (Opus 4.8, max)

Read `references/judge_rubric.md`, then assemble the final judge prompt:

```bash
python3 <skill_dir>/scripts/build_judge_prompt.py "$RUN_DIR"
```

Run the final judge:

```bash
bash <skill_dir>/scripts/run_judge.sh "$RUN_DIR/judge_prompt.txt" "$RUN_DIR/report_fusion.md" max
```

**Before adjudicating, the judge independently verifies the panel's load-bearing, contested, and time-sensitive claims with its runtime's live tools (the default Opus 4.8 judge uses native WebSearch/WebFetch, Perplexity, FMP / Scite / BioMCP, and up to 4 verification subagents; a `gpt-*`/`codex` override judge instead uses Codex `web_search` + its FMP / Scite / Perplexity connectors) and records them in a `§2 Independent Verification Log`** — it must not disclaim a training cutoff when a tool can resolve a figure. The prompt uses untrusted-content delimiters around panel/review text, withholds `response_mapping.json` by default, and requires a two-pass adjudication: structured consensus/contradiction/unique-insight/blind-spot table first, synthesis second. Because of this the judge stage runs longer than a pure-synthesis pass; tune with `FUSION_JUDGE_TIMEOUT` (default 3000s).

The final report must keep the Model Fusion style: where models agree, where they disagree, unique insights, comprehensive analysis, final recommendations, and follow-up questions. Hybrid mode adds a dedicated section: `How the Models Ranked Each Other`.

If the judge rejects the peer consensus, it must explain why with evidence, source quality, task fit, or logic.

## Step 6: Render HTML Reports

Render styled HTML copies of every report (panelists + fusion), **in addition to** the Markdown:

```bash
bash <skill_dir>/scripts/render_html.sh "$RUN_DIR" "<short-topic>"
```

This writes `report_opus4.8.html`, `report_grok4.5.html`, `report_gemini3.5flash.html`, `report_gpt5.6sol.html`, and `report_fusion.html`
next to the `.md` files, plus HTML copies for the aggregate scorecard, peer reviews, and contested claims when present (a dropped panelist's report is simply skipped).

## Required Output Contract

A complete run folder should contain:

```text
original_prompt.md
report_opus4.8.md
report_opus4.8.html
report_grok4.5.md
report_grok4.5.html
report_gemini3.5flash.md
report_gemini3.5flash.html
report_gpt5.6sol.md
report_gpt5.6sol.html
response_mapping.json
review_opus4.8.md
review_opus4.8.json
review_grok4.5.md
review_grok4.5.json
review_gemini3.5flash.md
review_gemini3.5flash.json
review_gpt5.6sol.md
review_gpt5.6sol.json
aggregate_scorecard.json
aggregate_scorecard.md
judge_prompt.txt
report_fusion.md
report_fusion.html
review_manifest.json
```

## Presenting Results

Report the run folder path and list the key files (each report is saved as both `.md` and a styled `.html`). Then summarize the final judge's bottom line and point the user to:

- individual model reports,
- peer-ranking reviews,
- aggregate scorecard,
- final fusion report.

Do not silently rewrite the judge's synthesis. You may fix obvious formatting only.
