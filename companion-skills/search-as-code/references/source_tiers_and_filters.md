# Source Tiers, Domain Filters & Exclusions

This is the trust model that `sac_search.py` applies to every run. Definitions live in
code (`SOURCE_TIERS`, `QUERY_TYPE_FILTERS`, `NOISE_DOMAINS`); this doc explains intent.

## Source tiers (feature #3)

Each result's host is suffix-matched to a tier (subdomains resolve to the registrable
parent, e.g. `efts.sec.gov` → `sec.gov`). Tier drives both ranking weight and the
`source_tier` / `hypothesis_only` labels on every source and evidence row.

| Tier | Label | May anchor a material claim? | Examples |
|---|---|---|---|
| 1 | `primary` | Yes | SEC EDGAR (`sec.gov`), SEDAR+ (`sedarplus.ca`), exchanges (NASDAQ/NYSE/LSE/TSX/Euronext/ASX/JPX/HKEX), company IR (`ir.*`, `investors.*`), regulators (`.gov`, FDA, EMA, FCA), ClinicalTrials.gov |
| 2 | `high_quality_secondary` | With one corroborating source | Reuters, Bloomberg, WSJ, FT, AP, CNBC, Morningstar, S&P, Moody's, FMP, official PR wires (GlobeNewswire/BusinessWire/PRNewswire) |
| 3 | `secondary` | Discovery / corroborate first (default for unknown domains) | MarketWatch, Forbes, Business Insider, Statista, Macrotrends, Investopedia |
| 4 | `low_confidence` | **Never** — kept but `hypothesis_only: true` | Seeking Alpha, Motley Fool, Benzinga, InvestorPlace, Zacks, Yahoo, TipRanks, Reddit, Stocktwits, Medium, YouTube, X |

Ranking bonus: Tier 1 `+45`, Tier 2 `+22`, Tier 3 `+5`, Tier 4 `-30`, plus recency,
snippet length, and query-overlap/priority terms. `.gov`/`.mil` resolve to Tier 1 and
`.edu`/`.ac.uk` to Tier 2 even when not in the explicit lists. Pass `issuer_domains`
in the plan to force a company's own domains to Tier 1.

## Domain filters by query type (feature #4)

A query may declare a `query_type`. At run time, if that query has **no explicit
`search_domain_filter`**, the harness injects one so authoritative questions don't get
answered by generic finance blogs. Perplexity domain filters are single-mode: injected
filters use either allowlist mode or denylist mode, never both, and are capped at 20.
Issuer domains from the plan are prepended to issuer/filing/results allowlists.

| query_type | allow (Perplexity `search_domain_filter`) | denies |
|---|---|---|
| `filings`, `financials`, `governance` | issuer domains + `sec.gov`, `sedarplus.ca` | none |
| `issuer_ir` | issuer domains only | none |
| `results_earnings` | issuer domains + `sec.gov` + PR wires | none |
| `ma` | `sec.gov`, PR wires, reuters, bloomberg | none |
| `news_catalyst` | reuters, bloomberg, wsj, ft, ap, cnbc | none |
| `valuation` | (none — broad) | fool, benzinga, investorplace |
| `peers` | (none — broad) | fool, benzinga |
| `bear_case` | (none — broadest) | (none; tier labels handle trust) |

An explicit `search_domain_filter` on a query always wins over the query_type default.

## Exclusion log (feature #6)

Results are partitioned before they reach `sources.jsonl`; dropped rows go to
`exclusion_log.jsonl` with an `exclude_reason`:

- `noise_domain` — host is in `NOISE_DOMAINS` (junk aggregators / spam).
- `ticker_collision:entity_and_ticker_absent` — when the plan sets `entity` and `ticker`,
  neither entity tokens nor ticker appear in the title/snippet/url, and the source is not
  Tier 1 or Tier 2. `entity_name_absent` alone is a non-fatal flag; a ticker match rescues
  the result, and Tier 1 sources are never excluded solely for collision flags.
- `extract_failed:<reason>` — `--extract` could not fetch/parse the document (paywall,
  JS-only page, 403/429, encrypted PDF). The source still keeps its search-snippet
  evidence; only the extraction attempt is logged.

Tier 4 sources are **not** excluded — they remain available, labeled `hypothesis_only`.
