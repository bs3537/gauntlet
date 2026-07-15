# WSL Valuation Data Stack — Sourcing Rules & Input Mapping

*This file is NOT from Damodaran — it documents the live WSL toolchain used by the valuation skill.*  
*Last verified: 2026-06-24. See memory files for additional context on each provider.*

---

## 1. FMP (Financial Modeling Prep) — Hard Rules

### Endpoint version
**Use `/stable/` endpoints ONLY.**  
v3 (`/api/v3/`) and v4 (`/api/v4/`) were retired 2025-08-31 and return `401`/`403` even with valid keys.  
All calls must be to `https://financialmodelingprep.com/stable/...`

### MCP vs. direct REST

| Condition | Method |
|---|---|
| Normal operation | `mcp__claude_ai_FMP__*` tools (claude.ai OAuth, Premium plan) |
| MCP returns "Server not found" or auth error | Direct REST fallback: read `~/.fmp_api_key` (chmod 0600), curl to `https://financialmodelingprep.com/stable/...?apikey=<key>` |

### What works on Premium plan

| FMP Tool / Endpoint | Works? | Notes |
|---|---|---|
| `quote` | YES | Live price, shares outstanding, market cap |
| `chart` | YES | OHLCV history |
| `statements` / `financials` | YES | Income stmt, balance sheet, cash flow |
| `ratios` | YES | P/E, P/B, EV/EBITDA, ROE, etc. |
| `key-metrics` | YES | ROIC, FCF, capex, D/E |
| `profile` | YES | Sector, industry, description, employees |
| `analyst` | YES | Consensus estimates, price targets |
| `peers` | YES | Peer set for comps |
| `news` | YES | Recent news headlines |
| `search` | YES | Ticker lookup |
| `secFilings` | YES | Links to EDGAR filings |
| `earningsTranscript` | NO — ACCESS DENIED | Requires Ultimate/Enterprise plan. Get transcripts via Perplexity + 8-K SEC filing instead. |

---

## 2. Web Search — Perplexity MCP

**Default WSL web provider: Perplexity MCP** (`mcp__perplexity__perplexity_search` and `mcp__perplexity__perplexity_ask`)

Do NOT use built-in `WebSearch` or Brave or Exa by default (removed/not default in WSL Claude Code as of 2026-05-31).

### When to use which Perplexity tool

| Tool | Use case |
|---|---|
| `perplexity_search` | Ranked web results: qualitative inputs, catalysts, peer-set discovery, news, company background, industry analysis |
| `perplexity_ask` | Live-web orientation with citations; open-ended questions about current state of a market or firm |

**IMPORTANT:** Perplexity snippets and synthesized answers are NOT final authority. Always verify material numbers (revenues, margins, capex, guidance) against primary filings before using them in a model. Use Perplexity to find candidate sources, then pull from EDGAR/company IR/FMP.

### Primary use cases for Perplexity in valuation

- ERP / country risk premium updates (Damodaran posts annual datasets; Perplexity can find latest URL)
- Earnings transcript summaries (when `earningsTranscript` is blocked)
- Industry reports and market size estimates for TAM inputs
- Qualitative moat / competitive analysis
- Catalyst calendar and upcoming events
- Peer set discovery and confirmation
- Macro inputs (GDP growth, interest rate expectations)

---

## 3. SEC Filings (EDGAR)

Use FMP `secFilings` (links to EDGAR) or direct EDGAR (`https://www.sec.gov/cgi-bin/browse-edgar`) for:
- 10-K / 10-Q: authoritative income statement, balance sheet, cash flow, footnotes
- 8-K: earnings releases, material events, full earnings transcripts (when MCP earningsTranscript is blocked)
- Proxy (DEF 14A): executive compensation, share count verification, dilution schedule
- S-1: IPO / pre-revenue firms — use for TAM assumptions and risk factor analysis

**Primary source authority:** SEC filings trump FMP ratios whenever there is a discrepancy. FMP may lag on restatements.

---

## 4. BioMCP + ClinicalTrials / PubMed (Biotech)

For biotech / biopharma pipeline inputs to rNPV / real option models:

- **BioMCP local CLI** is the primary biomedical backbone (installed locally; remote MCP removed 2026-05-29)
- **ClinicalTrials.gov** for trial design, phase, endpoints, enrollment, expected completion
- **PubMed / PMC** for peer-reviewed data on LoA (likelihood of approval) rates by indication and phase
- **Scite** (claude.ai connector `mcp__claude_ai_Scite__*`) for citation-quality evidence, full-text excerpts, retraction checks on key clinical papers — use selectively, not as first search

**Standard industry LoA benchmarks (use as priors, verify against primary):**
- Phase 1 → approval: ~10-15% (oncology lower; rare disease can be higher)
- Phase 2 → approval: ~15-25%
- Phase 3 → approval: ~50-65%
- NDA/BLA → approval: ~85-90%

---

## 5. Damodaran Annual Datasets (ERP / Beta / Industry)

Damodaran publishes free annual datasets at `https://pages.stern.nyu.edu/~adamodar/`.  
Cache downloaded files to `~/valuation_reference/datasets/` to avoid repeat fetches.

Key files:
- `histretSP.xls` — historical ERP, implied ERP
- `betas.xls` — industry average unlevered betas by sector
- `countryriskpremiums.xls` — country risk premiums, CDS spreads
- `impliedERP.xls` — forward-implied ERP (preferred over historical)
- `wacc.xls` — industry average WACC

If Damodaran site is unreachable, use Perplexity to find the latest published version or a mirror.

---

## 6. Valuation Input → Source Mapping Table

| Valuation Input | Preferred Source | Fallback |
|---|---|---|
| Income statement (revenue, EBIT, net income) | FMP `statements` (financials) → verify vs. 10-K | EDGAR 10-K directly |
| Balance sheet (assets, debt, equity, book value) | FMP `statements` | EDGAR 10-K |
| Cash flow statement (capex, D&A, FCF) | FMP `statements` or `key-metrics` | EDGAR 10-K cash flow statement |
| Shares outstanding (basic and diluted) | FMP `quote` or `profile` → cross-check vs. 10-K cover page | EDGAR 10-K or proxy DEF 14A |
| Current stock price | FMP `quote` | Yahoo Finance via Perplexity snippet (verify) |
| Market cap | FMP `quote` (price × shares) | FMP `profile` |
| Beta (regression) | FMP `key-metrics` or `ratios` | Bloomberg/FactSet via Perplexity |
| Beta (bottom-up, preferred) | FMP `peers` → gather sector betas → unlever/relever per Ch.8 [printed p.216-218 / PDF p.235-237] | Damodaran `betas.xls` by industry |
| Peer set | FMP `peers` + Perplexity for qualitative confirmation | Manual SIC-code lookup on EDGAR |
| ERP (equity risk premium) | Damodaran `impliedERP.xls` (forward/implied preferred over historical) [printed p.173 / PDF p.192] | Perplexity to find latest Damodaran update |
| Risk-free rate | 10-yr Treasury yield (duration-match to valuation horizon); for EM: local government bond in local currency | Fed H.15 release via Perplexity |
| Country risk premium | Damodaran `countryriskpremiums.xls` | Perplexity for CDS-spread based estimate |
| Industry beta (unlevered) | Damodaran `betas.xls` | FMP `peers` → compute average |
| Synthetic credit rating / cost of debt | Coverage ratio → rating table (Ch.8 [printed p.230-238 / PDF p.249-257]); or FMP bond rating if available | Perplexity for latest credit rating |
| Consensus EPS / revenue estimates | FMP `analyst` | Perplexity (cite source) |
| Earnings transcript (qualitative guidance) | FMP `secFilings` → 8-K text; Perplexity for summary | Manual EDGAR 8-K search |
| Pipeline LoA / clinical data (biotech) | BioMCP + ClinicalTrials.gov + PubMed | Scite for citation-quality clinical paper data |
| Industry margins / multiples for comparables | FMP `ratios` for peer set + Damodaran industry datasets | Perplexity (must verify vs. primary) |
| NOL carry-forward | EDGAR 10-K footnotes (income taxes section) | FMP statements → deferred tax assets |
| Options / warrants outstanding (dilution) | EDGAR 10-K or proxy DEF 14A (equity compensation table) | FMP `profile` (may be incomplete) |

---

## 7. Workflow Notes

1. **Always start with FMP MCP** for financials and price data. It is faster and structured.
2. **If FMP MCP fails** (server not found, timeout), switch immediately to direct REST curl with `~/.fmp_api_key`.
3. **For earnings transcripts**: FMP MCP will return ACCESS DENIED. Use `mcp__perplexity__perplexity_search` to find the transcript or key highlights, then cross-reference with the 8-K on EDGAR.
4. **For bottom-up beta**: pull FMP `peers`, get beta for each peer, unlever using each peer's D/E and tax rate, average the unlevered betas, then relever at target D/E. This is the method Damodaran recommends as more reliable than regression beta for any non-stable firm.
5. **Never use book-value WACC weights.** Always use market-value weights: ke × E/(D+E) + kd(1−t) × D/(D+E). [printed p.239 / PDF p.258]
6. **Verify primary-source numbers before entering into models.** FMP ratios can include stale or pre-restatement figures. When in doubt, pull the 10-K directly.
