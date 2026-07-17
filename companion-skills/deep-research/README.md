# Deep Research Skill for Claude Code

Enterprise-grade research workflow for Claude Code. Produces citation-backed reports with persisted source-tier tracking, native-web-first discovery, mandatory Search-as-Code integration for Standard/Deep/UltraDeep runs, targeted Perplexity deltas, structured retrieval layers, and automated validation.

**Retrieval order:** Native web search first. Search-as-Code second using the installed Search-as-Code skill. Targeted direct Perplexity follow-ups third. Primary documents before conclusions.

## Installation

```bash
# Clone into Claude Code skills directory
git clone https://github.com/199-biotechnologies/claude-deep-research-skill.git ~/.claude/skills/deep-research
```

No additional dependencies required for basic usage.

### Optional: search-cli (explicitly authorized alternate search)

Install only if you explicitly want an alternate web-search provider available. Do not use search-cli in a run unless the user authorizes alternate web search for that run:

```bash
brew tap 199-biotechnologies/tap && brew install search-cli
search config set keys.perplexity YOUR_KEY  # configure at least one provider
```

## Usage

```
deep research on the current state of quantum computing
```

```
deep research in ultradeep mode: compare PostgreSQL vs Supabase for our stack
```

## Research Modes

| Mode | Phase Profile | Duration | Best For |
|------|--------|----------|----------|
| Quick | 3 core phases + Phase 0.5 | 2-5 min | Initial exploration |
| Standard | 6 core phases + Phases 0.5/4.5 | 5-10 min | Most research questions |
| Deep | 8 core phases + Phases 0.5/4.5/7.5 | 10-20 min | Complex topics, critical decisions |
| UltraDeep | 8 core phases + Phases 0.5/4.5/7.5 and optional 7.6 | 20-45 min | Comprehensive reports, maximum rigor |

## Pipeline

Clarify/Brief &rarr; Scope &rarr; Plan &rarr; **Retrieve** (parallel search + agents) &rarr; Triangulate &rarr; Outline Refinement &rarr; Synthesize &rarr; Critique (with loop-back) &rarr; Refine &rarr; Audit &rarr; Optional Cross-Model Critique &rarr; Package

Key features:
- **Step 0**: Retrieves current date before searches (prevents stale training-data year assumptions)
- **Clarify-or-brief**: One batched clarification round when interactive; otherwise persists `research_brief.md` and `run_manifest.json.assumptions` before retrieval
- **Editable plan checkpoint**: Interactive runs pause on `plan.json`, accept user edits, and require `run_trace.py approve-plan` before retrieval trace records can start
- **Run trace, phase metrics, and coverage map**: Persists `plan.json`, `coverage_map.json`, provider/subagent execution trace, per-phase timing/token/cost metrics, and planned-vs-executed coverage checks
- **Role effort budgets**: `plan.json` pins every Claude worker lane to Sonnet 5 (`claude-sonnet-5`) at `xhigh`; per-role timeout/tool-call hints still tune breadth versus adversarial depth
- **DRY tool routing**: `reference/tool-routing.md` locks Native web search first, Search-as-Code second, Targeted direct Perplexity follow-ups third, and Primary documents before conclusions, then layers BioMCP/PubMed, Semantic Scholar, Scite, FMP, FinTwit, fetch/open, and alternate-provider rules
- **Local artifact ingestion**: `file_ingest.py` registers local PDFs, text files, images, and CSV/TSV tables as sources, preserving `file_manifest.jsonl`, extraction status, hashes, table profiles, and non-fabricated follow-up flags
- **Data-analysis lane**: Quantitative local datasets get `data_profile.jsonl`, optional reproducible artifacts under `analysis/`, and computed claims cited back to source data plus calculation method
- **Optional Deep Crawler**: Browser-automation subagent fallback for hard-target public pages after normal retrieval is exhausted, with no login/paywall/CAPTCHA bypass and evidence persisted back to ledgers
- **Per-section package audit**: Phase 8 rejects draft-while-retrieving streaming and writes per-section CitationAuditor JSON before the final delivery gate
- **Parallel retrieval**: 5-10 concurrent searches + 2-3 focused sub-agents returning structured evidence objects
- **Batch ledger imports**: `register-sources --jsonl` and `evidence_store.py add-batch --jsonl` ingest large retrieval waves idempotently while `ledger_index.json` caches duplicate checks
- **Biotech/pharma investment controls**: Primary-source routing, Perplexity/BioMCP/scite/FMP layering, pipeline-sweep gates, source-lineage preservation, and claim-ledger fields
- **First Finish Search**: Adaptive quality thresholds by mode
- **Critique loop-back**: Phase 6 can return to Phase 3 with delta-queries if critical gaps found
- **Optional cross-model critique**: Phase 7.6 can shell the draft plus claims sample to the opposite model family for a time-boxed advisory rubric review: Claude Code -> Codex GPT/xhigh; Codex or AGY/Gemini -> Claude Opus/max
- **Multi-persona red teaming**: Skeptical Practitioner, Adversarial Reviewer, Implementation Engineer (Deep/UltraDeep)
- **Disk-persisted citations**: `sources.jsonl`, `evidence.jsonl`, and `claims.jsonl` survive context compaction and continuation agents

## Output

Reports saved to `~/Documents/[Topic]_Research_[Date]/`:
- Markdown (primary source of truth)
- `research_brief.md` (scope, open questions, assumptions, retrieval implications)
- `plan.json` (planned lanes, query families, expected roles, stop conditions, editable checkpoint)
- `coverage_map.json` (planned-vs-executed lane and query-family coverage)
- `ledger_index.json` (rebuildable source/evidence index cache; ledgers remain source of truth)
- `file_manifest.jsonl` (local file inventory, hashes, extraction status, follow-up actions)
- `data_profile.jsonl` (deterministic profiles for ingested CSV/TSV tables)
- `run_manifest.json` (mode, assumptions, artifacts, execution trace, phase metrics, eval metadata)
- HTML (McKinsey-style, host-opened via `xdg-open` or `explorer.exe`)
- PDF (professional print via Windows Chrome headless on WSL; WeasyPrint optional when installed)

Reports >18K words auto-continue via recursive agent spawning with context preservation.

## Quality Standards

- 10+ sources, 3+ per major claim
- Executive summary 200-400 words
- Findings 600-2,000 words each, prose-first (>=80%)
- Do not append a full bibliography, full source list, or long "Sources Used" section to the main report unless the user explicitly requests it. Store full metadata in external ledgers; if useful, add only a 1-3 line "Evidence Artifacts" note pointing to `sources.jsonl`, `evidence.jsonl`, and `claims.jsonl`.
- Run trace and coverage accounting checked by `audit_manifest.py`; UltraDeep strict blocks missing planned coverage
- Phase metrics in `run_manifest.json.execution_trace.phase_metrics` record measured searches, sources, tokens, cost, and wall-clock duration where available
- Automated semantic delivery gate: `delivery_gate.py --strict --semantic --require-section-citation-audits` runs structure validation, citation checks, current-report claim extraction, strict deterministic + semantic claim-support verification, final and per-section CitationAuditor issue blocking, and `audit_manifest.py --strict`
- Internal self-evaluation: `run_eval.py` scores completed runs with pinned judge metadata and writes `self_eval` plus `evals/runs.csv`; scores are internal, not public benchmark claims
- Golden adversarial gate tests: offline fixture-only regression checks for negation, paraphrase, 0.60-floor, YEAR_RE, shuffled display-map, DOI-locator, and subagent merge round-trip cases
- Deep Crawler gate: browser-automation fallback is optional, bounded to hard-target public pages, and must persist rendered evidence and lane coverage before delivery
- Per-section CitationAuditor gate: package-stage section audits are saved under `audit/section_citation_issues/`, and strict delivery blocks on critical section-level citation issues
- Validation loop: delivery gate &rarr; fix &rarr; retry (max 3 cycles)

## Search Tools

| Tool | Priority | Setup |
|------|----------|-------|
| Native web search | **First** — broad discovery, recency verification, and primary-document targeting | Claude Code native web search |
| Search-as-Code | **Second and mandatory for Standard, Deep, and UltraDeep external/current research** — coordinated Perplexity fanout, dedupe, diagnostics, and ledger import | `~/.claude/skills/search-as-code` + `PERPLEXITY_API_KEY` |
| Perplexity Search MCP | **Third** — targeted gap filling, alternate formulations, and source-specific deltas | `~/.claude/scripts/perplexity-mcp.sh` + `PERPLEXITY_API_KEY` |
| Primary documents | **Required before conclusions** — verify load-bearing claims against authoritative sources | FDA, SEC, registries, journals, issuer materials, exchanges, and other claim-appropriate authorities |
| BioMCP | Required for biotech/pharma structured biomedical retrieval when available | Local BioMCP server or CLI |
| Semantic Scholar | Citation graph expansion, references, cited-by, related papers, recommendations, OA PDF metadata, and author/venue metadata after PubMed/PMC | `S2_API_KEY` |
| scite | Required for peer-reviewed biomedical claim support/dispute and editorial notices when available | scite MCP auth |
| FMP | Preferred structured financial and market data layer for public-company research | FMP MCP/API key |
| search-cli | Optional — alternate provider aggregation only with explicit user authorization | `brew install search-cli` + API keys |
| Built-in web search | Default first-pass discovery and current-verification provider | None (built-in) |

## Architecture

```
deep-research/
├── SKILL.md                          # Skill entry point (lean, ~100 lines)
├── reference/
│   ├── tool-routing.md               # General retrieval and provider routing
│   ├── methodology.md                # 8-phase pipeline details
│   ├── biotech-pharma-investment-research.md # Biotech/pharma investment source-routing gates
│   ├── report-assembly.md            # Progressive generation strategy
│   ├── quality-gates.md              # Validation standards
│   ├── html-generation.md            # McKinsey HTML conversion
│   ├── self-evaluation.md            # Internal eval harness protocol
│   ├── continuation.md               # Auto-continuation protocol
│   └── weasyprint_guidelines.md      # PDF generation
├── templates/
│   ├── report_template.md            # Report structure template
│   └── mckinsey_report_template.html # HTML report template
├── scripts/
│   ├── validate_report.py            # 9-check structure validator
│   ├── verify_citations.py           # DOI/URL/hallucination checker
│   ├── delivery_gate.py              # Strict final report package gate
│   ├── cross_model_critique.py       # Optional opposite-model draft critique hook
│   ├── verify_claim_support_llm.py   # Semantic claim-support verifier
│   ├── run_trace.py                  # Run trace and coverage map accounting
│   ├── source_evaluator.py           # Optional source-tier heuristic, not a delivery gate
│   ├── citation_manager.py           # Citation tracking, assumptions, briefs, batch source imports, ledger index rebuild
│   ├── evidence_store.py             # Single-row and batch evidence persistence
│   ├── file_ingest.py                # Local file ingestion, table profiling, PDF/image follow-up flags
│   ├── ledger_index.py               # Rebuildable source/evidence index cache
│   ├── md_to_html.py                 # Markdown to HTML converter
│   ├── verify_html.py                # HTML verification
│   ├── run_eval.py                   # Internal self-evaluation harness
│   └── research_engine.py            # Phase instruction provider; not a runtime orchestrator
├── evals/
│   ├── judge_rubric.json             # Internal RACE-mini rubric
│   └── tasks/gold_tasks.json         # 20 internal gold-task prompts
└── tests/
    └── fixtures/                     # Test report fixtures
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0.0 | 2026-07-05 | Fusion-report hardening: citation display maps, lexical/table/subagent support, delivery gate wiring, eval harness, plan checkpoint, phase metrics, role budgets, batch ledger index, phase-provider cleanup, adversarial gate tests, and consistency sweep |
| 2.3.1 | 2026-03-19 | Template/validator harmonization, structured evidence, critique loop-back, multi-persona red teaming |
| 2.3 | 2026-03-19 | Contract harmonization, search-cli integration, dynamic year detection, disk-persisted citations, validation loops |
| 2.2 | 2025-11-05 | Auto-continuation system for unlimited length |
| 2.1 | 2025-11-05 | Progressive file assembly |
| 1.0 | 2025-11-04 | Initial release |

## License

MIT - modify as needed for your workflow.
