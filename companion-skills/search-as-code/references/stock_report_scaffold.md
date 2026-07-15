# Standard Stock Deep-Dive — Report Scaffold

Generate the discovery pack with:

```bash
python /home/bhavneesh/.claude/skills/search-as-code/scripts/sac_search.py template \
  --ticker MSFT --company "Microsoft Corporation" --exchange NASDAQ \
  --sector "Information Technology" --fy FY2025 --peers "Salesforce CRM,Oracle ORCL" \
  --mode ultradeep --out msft_plan.json
python .../sac_search.py run --plan msft_plan.json --out-dir runs/msft --extract
python .../sac_search.py import --run-dir runs/msft --into ~/Documents/MSFT_Research_20260602
```

The 24-query template (feature #7) maps to the eight sections below. Each query is
tagged with a `query_type` so the run-time domain filter routes filings/governance/
financials to SEC EDGAR + SEDAR+, earnings/M&A to issuer wires, and leaves
valuation/peers/bear-case broad. `entity`/`ticker` are set so ticker-collision
results are dropped to the exclusion log.

## Report sections → primary sources

| # | Section | query_type(s) | Primary sources to anchor on |
|---|---|---|---|
| 1 | Filings & disclosures | `filings` | 10-K, 10-Q, 8-K (SEC EDGAR), company IR |
| 2 | Latest results | `results_earnings` | Earnings release (8-K Ex-99.1), call transcript, guidance |
| 3 | Governance | `governance` | DEF 14A proxy, Form 4, 13F/13D/G |
| 4 | M&A history | `ma` | Deal 8-Ks, PR wires, 10-K segment notes |
| 5 | Financial quality | `financials` | 10-K/10-Q statements, debt notes, critical accounting policies |
| 6 | Valuation | `valuation` | Multiples & price targets (corroborate; Tier 4 = hypothesis-only) |
| 7 | Peers & landscape | `peers` | Peer 10-Ks, 10-K competition section, industry reports |
| 8 | Bear case | `bear_case` | Short reports, SEC enforcement (Wells/8-K), risk factors, customer-concentration |

## Markdown scaffold for the downstream deep-research draft

```markdown
# {company} ({ticker}) — Institutional Equity Deep-Dive
**Exchange:** {exchange} | **Sector:** {sector} | **As of:** {date}

## Executive Summary

## 1. Filings & Disclosures
### 1.1 Most recent 10-K   ### 1.2 Recent 10-Q   ### 1.3 Material 8-Ks   ### 1.4 IR disclosures
## 2. Latest Results
### 2.1 Most recent quarter   ### 2.2 Full-year guidance   ### 2.3 Management commentary
## 3. Governance
### 3.1 Board & independence   ### 3.2 Executive comp   ### 3.3 Insider ownership (Form 4)   ### 3.4 Institutional ownership (13F)
## 4. M&A History
### 4.1 Acquisition chronology   ### 4.2 Integration track record   ### 4.3 Divestitures
## 5. Financial Quality
### 5.1 Revenue (organic vs acquired)   ### 5.2 Margins   ### 5.3 FCF generation   ### 5.4 Balance sheet   ### 5.5 Accounting flags
## 6. Valuation
### 6.1 Current multiples   ### 6.2 Consensus & targets   ### 6.3 Historical range vs sector
## 7. Peers & Competitive Landscape
### 7.1 Peer set   ### 7.2 Relative benchmarking   ### 7.3 Industry structure & TAM
## 8. Bear Case
### 8.1 Published short/bear arguments   ### 8.2 Regulatory & legal risk   ### 8.3 Customer concentration   ### 8.4 Management stability

## Evidence Ledger   <!-- from evidence.jsonl (extracted_quote preferred over search_snippet) -->
## Sources           <!-- from sources.jsonl, ranked; Tier 4 flagged hypothesis-only -->
```
