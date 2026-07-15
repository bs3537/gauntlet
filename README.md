# gauntlet

Two-model adversarial equity research skill for Claude Code (WSL). Opus 4.8 max runs the
universal institutional master research prompt (Phases 0-6) and drafts a preliminary report;
GPT-5.6 Sol max attacks the draft as an external adversarial reviewer via the codex CLI
(blind-spot protocol, independent verification, model recomputation, scored /100); the
first-pass model adjudicates every finding with evidence, applies sustained corrections,
and only then writes the final Wall-Street-style report. Explicit invocation only: `/gauntlet <TICKER>`.

## Layout

- `SKILL.md` — orchestrator (Stages 0-5, gates, gotchas, env tuning)
- `references/master_research_prompt.md` — universal master equity research prompt (Phases 0-6 + 8, v2 file set, degraded-mode self-review appendix)
- `references/reviewer_prompt_template.md` — GPT-5.6 Sol adversarial reviewer prompt with placeholders and delivery contract
- `scripts/run_review.sh` — preflight + hardened codex launch (hybrid-model-fusion runner, raw fallback) + QC gate (`--qc-only` mode)
- `docs/` — approved implementation plan (2026-07-15)

## Deploy (staging -> copies model)

```bash
cp -r SKILL.md scripts references ~/.claude/skills/gauntlet/   # canonical host tree
cp -r SKILL.md scripts references ~/.codex/skills/gauntlet/    # parity copy (add codex-tree note)
```

Requires: `codex` CLI authenticated (gpt-5.6-sol), `~/.claude/skills/hybrid-model-fusion/scripts/run_codex.sh`
(standard mode; run_review.sh falls back to raw `codex exec` if absent). Never swap in the
model-council-fast runner (its lib hardcodes FUSION_FAST=1) and never pass FUSION_RUN_STAGE=review
to the hybrid runner (attaches its peer-review --output-schema).
