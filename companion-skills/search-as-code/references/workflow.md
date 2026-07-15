# Search-as-Code Workflow

## MVP Pattern

Use Search API for retrieval, local code for orchestration, and downstream research skills for final claim verification.

1. Decompose the topic into 5-30 logical queries.
2. Assign every query a `purpose`, such as `official-source`, `recent-news`, `technical-docs`, `counterevidence`, `competitor-map`, or `benchmark`.
3. Use domain filters only when the source class matters. Explicit filters must be either allowlist or denylist mode, not both.
4. Run the plan with `sac_search.py run`. The default is one query per request; use `--batch` only when the attribution and metering assumptions are acceptable.
5. Inspect `coverage_summary.md`, `coverage_diagnostics.json`, `errors.jsonl`, and cost fields for source concentration, weak result groups, failed requests, duplicate-heavy queries, and cost.
6. If gaps remain, create a second delta plan with narrower queries.

## Example Plan

```json
{
  "topic": "Perplexity Search as Code architecture",
  "mode": "standard",
  "queries": [
    {
      "query": "site:research.perplexity.ai \"Search as Code\" Perplexity",
      "purpose": "official-source",
      "search_domain_filter": ["research.perplexity.ai"],
      "max_results": 10,
      "snippet_mode": "high",
      "priority": 1
    },
    {
      "query": "site:docs.perplexity.ai \"Search API\" \"Pricing\"",
      "purpose": "api-docs",
      "search_domain_filter": ["docs.perplexity.ai"],
      "max_results": 10,
      "snippet_mode": "high",
      "priority": 2
    }
  ]
}
```

## Downstream Use

For deep research, treat the output as the discovery pack:
- Register high-value URLs as sources.
- Use `evidence.jsonl` snippets to decide which primary sources to fetch.
- Prefer `extracted_evidence.jsonl` rows when `--extract` succeeded, but preserve their `source_tier` and `hypothesis_only` trust fields.
- Do not cite a snippet as final proof when a primary document is available.
