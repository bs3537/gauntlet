# Hybrid Fusion Evaluation Rubric

Grade each arm on 0-10 for each category. Use the same judge and rubric for every arm in a task.

## Categories

- `accuracy`: factual correctness, absence of hallucinated numbers, and correct use of primary evidence.
- `evidence`: quality, recency, and traceability of sources or local code/file anchors.
- `reasoning`: causal logic, handling of alternatives, and explicit treatment of uncertainty.
- `decision_usefulness`: whether the output gives a clear answer, recommendation, or implementation path.

## Penalties

- Subtract up to 4 points for confident-wrong claims.
- Subtract up to 3 points for verbosity that obscures the answer.
- Subtract up to 3 points for missing the user's actual task.
- Subtract up to 2 points for unsupported social, market, or literature claims.

## Required JSON

Return a fenced JSON object:

```json
{
  "task_id": "<task-id>",
  "arm": "<arm-name>",
  "pass_id": "<pass-id>",
  "scores": {
    "accuracy": 0,
    "evidence": 0,
    "reasoning": 0,
    "decision_usefulness": 0
  },
  "penalties": {
    "confident_wrong": 0,
    "verbosity": 0,
    "missed_task": 0,
    "unsupported_claims": 0
  },
  "total": 0,
  "rationale": "<short rationale>",
  "fatal_flaws": []
}
```
