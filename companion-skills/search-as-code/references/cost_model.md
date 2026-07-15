# Search-as-Code Cost Model

## Default MVP Pricing

Search API request estimate:

```text
estimated_cost_usd = http_request_count * 0.005
```

Track both:
- `logical_query_count`: number of planned searches.
- `http_request_count`: number of Search API calls attempted after batching choice.
- `successful_http_request_count`: Search API calls that returned usable payloads.
- `failed_http_request_count`: Search API calls written to `errors.jsonl`.
- `http_attempt_count`: initial requests plus retry attempts.
- `worst_case_logical_query_cost_usd`: `logical_query_count * 0.005`.

## Batching

Default runs send one logical query per HTTP request. Batch up to five logical queries into
one HTTP request only with `--batch` and only when all request parameters except `query`
are identical. Queries with different filters or result budgets must be separate requests.

Cost ledgers use the documented per-request price for successful Search API responses.
Because multi-query billing and response grouping can vary by API behavior, compare against
`worst_case_logical_query_cost_usd` when batching is enabled. Retries are counted in
`http_attempt_count`; failed requests are logged in `errors.jsonl`.

## Agent API Boundary

Agent API adds model-token charges and tool charges. Use it only when it is expected to reduce total model-visible intermediate state or produce materially better autonomous tool use.

MVP defaults:
- Search API: yes.
- Local deterministic orchestration: yes.
- Agent API `web_search`: no.
- Agent API `fetch_url`: no.
- Agent API `sandbox`: no.
