# Deep Research Internal Self-Evaluation

This folder contains an internal harness for measuring deep-research runs over time. It is not an implementation of DeepResearch Bench, DeepConsult, BrowseComp, RACE, DRACO, or any other public benchmark.

Use `scripts/run_eval.py` on completed run directories after the delivery gate has passed. Always pin the judge provider, model, version/date, rubric version, prompt hash, network mode, and eval task version in the saved result.

Task files intentionally contain prompts and success criteria only. Do not place answer keys in the prompt file that the research runner can read.

Typical offline scoring:

```bash
python scripts/run_eval.py score-run \
  --task evals/tasks/gold_tasks.json \
  --task-id adversarial-negation-001 \
  --run-dir /path/to/completed/run \
  --judge-output /path/to/judge_output.json \
  --judge-provider fixture \
  --judge-model fixture-race-mini \
  --judge-version 2026-07-05 \
  --strict
```

Live judge scoring can pass `--judge-command`, but tests should use fixture JSON and leave network mode disabled.

Golden adversarial gate tests live in `tests/test_golden_adversarial_gate.py`. They are offline fixture checks for delivery-gate regressions and are not public benchmark claims. Keep answer keys and fixture judgments outside prompt task files; task files should contain prompts and success criteria only.
