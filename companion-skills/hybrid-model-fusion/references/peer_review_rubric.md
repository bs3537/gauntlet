# Blind Peer Review Rubric

You are reviewing anonymized outputs from other models. Do not infer author identity. Evaluate only the content.

## Required JSON

Return a fenced JSON block using this schema, followed by a short Markdown explanation:

```json
{
  "reviewer": "<reviewer-id>",
  "reviewed_responses": ["<LABEL_1>", "<LABEL_2>"],
  "ranked_order": ["<LABEL_2>", "<LABEL_1>"],
  "forced_choice_winner": "<LABEL_2>",
  "scores": {
    "<LABEL_1>": {
      "correctness": 7,
      "evidence_quality": 7,
      "completeness": 7,
      "reasoning_quality": 7,
      "calibration": 7,
      "actionability": 7,
      "total": 42
    },
    "<LABEL_2>": {
      "correctness": 8,
      "evidence_quality": 8,
      "completeness": 8,
      "reasoning_quality": 8,
      "calibration": 8,
      "actionability": 8,
      "total": 48
    }
  },
  "best_supported_claims": {
    "<LABEL_1>": [],
    "<LABEL_2>": []
  },
  "weak_or_unsupported_claims": {
    "<LABEL_1>": [],
    "<LABEL_2>": []
  },
  "missed_by_response": {
    "<LABEL_1>": [],
    "<LABEL_2>": []
  },
  "claim_verdicts": [
    {
      "claim": "<falsifiable claim or figure>",
      "response": "<LABEL_1>",
      "verdict": "strong|weak|flawed|unverified",
      "reason": "<short reason>"
    }
  ],
  "decisive_differences": [],
  "confidence": 0.8,
  "notes_for_judge": []
}
```

## Scoring

Use 0-10 integer scores for each dimension.

- `correctness`: factual and technical accuracy.
- `evidence_quality`: primary-source use, citations, verification, and grounding.
- `completeness`: coverage of the user's actual task.
- `reasoning_quality`: logical structure, causal reasoning, and handling of alternatives.
- `calibration`: uncertainty, confidence, caveats, and avoidance of overclaiming.
- `actionability`: usefulness of recommendations, next steps, or decision support.

`total` is the sum of the six dimensions, maximum 60.

`confidence` is 0.0-1.0 and means confidence in your own review, not confidence in the winning answer.

## Ranking Rules

- Rank only the anonymized responses you were given.
- Do not rank your own primary response.
- Do not tie responses.
- Prefer the better-evidenced answer over the more polished answer.
- Preserve minority insights: a lower-ranked response may still contain one useful point.
- If the responses are close, explain the decisive difference.
- Use `claim_verdicts` for specific falsifiable claims or figures the judge should verify first.
