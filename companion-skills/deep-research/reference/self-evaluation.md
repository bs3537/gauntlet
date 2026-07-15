# Internal Self-Evaluation

Use `scripts/run_eval.py` to measure completed deep-research runs over time. This harness is internal: do not describe its scores as DeepResearch Bench, DeepConsult, BrowseComp, RACE, DRACO, or any other public benchmark result unless the exact public task set, judge, scoring protocol, and sampling method were used.

## When To Run

- Run after P0/P1 skill changes to compare before/after behavior.
- Run quarterly on a stable task mix to detect quality drift.
- Run on representative user workload tasks before changing retrieval, citation, or delivery-gate logic.
- Do not make ordinary user delivery wait for this harness unless the user explicitly asks for a scored eval.

## Required Metadata

Every scored run must pin:

- `judge_provider`
- `judge_model`
- `judge_version`
- `rubric_version`
- `judge_prompt_hash`
- `temperature`
- `seed`
- `network_mode`
- artifact hashes for report, source, evidence, claim, and audit files

This prevents false precision when judge models or rubrics change.

## Offline Fixture Mode

Tests and reproducible local checks should pass `--judge-output [json]` and leave network mode disabled:

```bash
python scripts/run_eval.py score-run \
  --task evals/tasks/gold_tasks.json \
  --task-id adversarial-negation-001 \
  --run-dir [completed_run_folder] \
  --judge-output [judge_output.json] \
  --judge-provider fixture \
  --judge-model fixture-race-mini \
  --judge-version 2026-07-05 \
  --strict
```

Live judge mode can pass `--judge-command`, but the result must record `llm_used: true`.

Golden adversarial gate tests are separate fixture-only delivery-gate checks. They do not use live judges or network access, and they should run before modifying citation display maps, claim-support scoring, DOI verification, or subagent evidence merge behavior.

## Outputs

- Updates `[run_folder]/run_manifest.json` with `self_eval`.
- Writes a full result JSON under `evals/results/` by default.
- Appends a summary row to `evals/runs.csv`.

`runs.csv` is only an index. The result JSON is the source of truth.
