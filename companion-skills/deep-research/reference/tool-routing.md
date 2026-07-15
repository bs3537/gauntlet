# Tool Routing

Load this reference before Phase 3 retrieval. It is the single source of truth for general retrieval, structured-provider, citation-intelligence, market-data, social-sentiment, fetch/open, and alternate-provider routing.

For biotech/pharma equities, drug pipelines, clinical catalysts, FDA/regulatory events, commercial treatment landscapes, or life-sciences investment recommendations, also load [biotech-pharma-investment-research.md](./biotech-pharma-investment-research.md). Do not load that biotech/pharma pack for unrelated research.

---

## Surface Adapter: Claude Code WSL

- Search-as-Code path: `~/.claude/skills/search-as-code`.
- Perplexity Search MCP: use as the targeted complementary follow-up layer after native search and Search-as-Code.
- FinTwit command: `python3 ~/.claude/skills/fintwit/scripts/fintwit_engine.py --ticker <TICKER> --out <run_dir>`.
- Scite access: Claude Code reaches Scite through the hosted `claude.ai Scite` connector (`mcp__claude_ai_Scite__*` tools, for example `mcp__claude_ai_Scite__search_literature`). It is authenticated through claude.ai; do not run the Codex local OAuth token-refresh helper in Claude Code. If Scite returns an auth error, reconnect via `/mcp` or claude.ai. If it remains unavailable, disclose the gap and continue with BioMCP + PubMed/PMC + Semantic Scholar fallbacks where defensible.
- Subagents: use the Agent tool when available, leave workers on latest Sonnet by default, pass `model: "sonnet"` when model overrides are supported, and embed or paraphrase `templates/subagent_brief_template.md` in every research-worker prompt.
- Optional auxiliary search: do not use search-cli in a run unless the user authorizes alternate web search. If `search-cli` is installed and configured, it is an explicit-override auxiliary path only, never the default or primary path for this skill.

---

## Shared Routing Contract

SHARED ROUTING CONTRACT BEGIN

### Web Discovery

Native web search is the default WSL broad-discovery and current-verification provider. Use it first for regulatory developments, SEC filings, trial records, competitive landscapes, current news, and discovery of primary documents.

For external, current, or source-backed work, use this order:

1. **Native web search first** — map the landscape, verify recency, and surface primary-source targets.
2. **Search-as-Code second** — execute the active surface's installed Search-as-Code skill for coordinated Perplexity Search API fanout, dedupe, coverage diagnostics, and persisted source/evidence ledgers.
3. **Targeted direct Perplexity follow-ups third** — query unresolved gaps, alternative formulations, and source-specific targets that remain after native search and Search-as-Code.
4. **Primary documents before conclusions** — open and verify every load-bearing FDA, SEC, registry, journal, issuer, exchange, or other authoritative document.

- Use `perplexity_search` as the complementary fast layer for alternate query formulations, source-targeted follow-ups, and finding material native search or Search-as-Code may have missed.
- Use `search_recency_filter` for recent news, catalysts, and time-sensitive queries.
- Use `search_domain_filter` to restrict high-value domains such as `sec.gov`, `fda.gov`, `clinicaltrials.gov`, `pubmed.ncbi.nlm.nih.gov`, `pmc.ncbi.nlm.nih.gov`, company IR domains, and major journal or conference domains.
- Use `perplexity_ask` only when a synthesized orientation with citations is more useful than a raw result list.
- Treat native-search snippets, Perplexity snippets, and synthesized answers as discovery only. Verify material claims against the underlying source documents.
- For every material investment, regulatory, clinical, financial, or market claim, open and verify the underlying authoritative document before relying on it.

If either native search or Perplexity is unavailable, rate-limited, stale, promotional, or too thin, use the other provider plus already identified primary-source URLs and structured providers, and disclose the coverage gap. Do not use search-cli or another non-native alternate provider unless the user explicitly authorizes another web-search provider for that run. If providers conflict on a market-moving or otherwise material claim, stop and write a discrepancy note rather than merging the claims.

Use fetch/open tools for known URLs surfaced by native search, Perplexity, structured providers, local files, or primary-source discovery. Opening the primary document is mandatory for load-bearing claims.

Browser automation, when exposed through Playwright, computer-use, or a browser MCP, is an optional renderer for known public URLs only. It is not a search provider, not a default dependency, and not a way to bypass logins, paywalls, CAPTCHAs, robots/access controls, rate limits, or terms-of-use restrictions. Use it only after hard-target retrieval escalation fails for a material public-web claim, then persist rendered text back to the normal source/evidence ledgers.

### Search-as-Code

Use the active surface's installed Search-as-Code skill as a front-loaded wide-discovery pack:

- Always for Standard, Deep, and UltraDeep deep-research modes when external, current, or source-backed discovery is material.
- Always for prompts that say "deep dive" when external/current/source-backed discovery is relevant.
- For Quick mode only when 10+ coordinated searches, dedupe, persisted source/evidence ledgers, coverage summaries, or cost tracking materially improve quality. If Quick mode omits Search-as-Code, disclose the skip and reason in the methodology.

This means invoking the installed Search-as-Code skill and its `sac_search.py` workflow, not assigning a vaguely named "Search-as-Code" research lane or imitating its output manually. Import its `sources.jsonl` and `evidence.jsonl` into the Deep Research run before triangulation. If the installed skill or Perplexity transport is unavailable after a bounded retry, use targeted direct Perplexity when available, record the failure, and disclose the coverage gap; never silently skip the mandatory Standard/Deep/UltraDeep step. Search-as-Code is not final evidence authority and must not bypass native current verification, BioMCP/PubMed, Semantic Scholar, Scite, FMP, or primary-source verification.

### Biomedical And Scientific Literature

Use this order for biomedical, clinical, translational, trial-heavy, or peer-reviewed scientific literature work:

1. **BioMCP + direct PubMed/PMC** - primary biomedical literature backbone for PubMed discovery, PMID/PMCID retrieval, PubMed/PMC metadata, ClinicalTrials.gov, FDA/openFDA data, genes, variants, drugs, diseases, pathways, study analytics, and entity resolution. Use `NCBI_API_KEY` when available.
2. **Semantic Scholar** - citation graph expansion when `S2_API_KEY` is present: references, cited-by papers, related papers, recommendations, open-access PDF metadata, author metadata, and venue metadata. Use it after PubMed/PMC, not as the primary biomedical search source.
3. **Scite** - selective citation-intelligence after BioMCP + PubMed/PMC for central papers and contested claims: Smart Citations, support/contrast/mention context, full-text excerpts when available, and editorial-notice/retraction checks.

Before citing a peer-reviewed paper, check Scite `editorialNotices` when Scite is available. Preserve DOI/title, metadata, Smart Citation context, full-text excerpts when available, and editorial-notice/retraction status. Do not stall biomedical literature search on Scite transport failure, but label any missing editorial-notice check in the source registry and audit output.

Primary sources win conflicts: FDA materials, ClinicalTrials.gov records, PubMed/PMC papers, conference abstracts/posters, company IR, official study materials, labels, and regulator documents outrank retrieval summaries and metadata providers.

### Markets, Companies, And Biotech Catalysts

For stocks, public companies, approvals, clinical catalysts, earnings, financing, M&A, or other market-sensitive claims:

- Start with native web search for broad discovery, current verification, and primary-document retrieval; then use Search-as-Code and targeted direct Perplexity in the shared order above.
- Use FMP as the preferred structured-data layer when available for quotes, price history, news aggregation, filings metadata, calendars, transcript discovery, financials, ownership, comparable-company screens, and valuation inputs.
- Treat FMP as structured context, not a primary source. Verify material claims against company IR, SEC filings, FDA materials, ClinicalTrials.gov, conference materials, official transcripts, or regulator sources.
- Never rely on article discovery alone for approval status, filing status, market reaction, valuation-relevant events, guidance, offering terms, M&A terms, or share-count-sensitive conclusions.
- For any identifiable stock ticker, run the surface-specific FinTwit / X-sentiment step during retrieval. Register `fintwit_context.md` as Tier-4 social sentiment only. Use it for narrative, positioning, and crowd-watched catalysts; never use it to anchor a material claim or override structured data or primary sources.

For biotech/pharma investment work, load the biotech/pharma reference after this file. It controls pipeline-sweep gates, primary-source priorities, query construction, line-of-therapy adjacency, named-threat carry-forward, and claim-ledger fields.

### Source Hierarchy

Use Perplexity, Search-as-Code, BioMCP, Semantic Scholar, Scite, FMP, and FinTwit as discovery, graph-expansion, citation-intelligence, structured-data, or social-sentiment layers. They surface candidate documents and claims; they do not replace primary-source verification.

When sources conflict, prefer the highest-authority source for the claim type:

- Regulators, trial registries, labels, SEC filings, issuer materials, official transcripts, and primary papers for factual status claims.
- Peer-reviewed papers and Scite context for scientific reception, support/contrast, and editorial-notice checks.
- Structured market-data providers for standardized market data, with issuer/regulator checks for material status claims.
- Social/forum data only for sentiment and positioning context.

SHARED ROUTING CONTRACT END
