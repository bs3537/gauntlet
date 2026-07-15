# Changelog

## 3.0.0 - 2026-07-05

- P0-1A: Persisted `display_map.json` so report citation labels resolve to stable source IDs.
- P0-1B: Hardened lexical claim-support checks for years, negation, vacuous overlap, and self-support.
- P0-1C: Added table claim extraction for markdown tables.
- P0-1D: Added subagent evidence merge into canonical source/evidence ledgers.
- P0-2: Wired `CitationAuditor` issues into the delivery gate.
- P0-3: Added the internal eval harness and strict eval metadata checks.
- P1-1: Added clarify-or-brief assumptions and editable `plan.json` checkpointing.
- P1-2: Added run trace and coverage-map accounting.
- P1-3: Added Search-as-Code and source-routing documentation gates.
- P1-4: Added semantic claim-support verification.
- P1-5: Replaced hidden numeric credibility gates with source-tier audit warnings.
- P1-6: Reworked HTML/PDF packaging for WSL host-safe output.
- P2-1: Added editable plan approval before retrieval trace records.
- P2-2: Added optional cross-model critique artifacts.
- P2-2A: Routed optional cross-model critique to an opposite-model reviewer by WSL surface: Claude Code -> Codex GPT/xhigh; Codex or AGY/Gemini -> Claude Opus/max.
- P2-3: Added phase metrics for searches, sources, tokens, cost, and duration.
- P2-4: Added role-based effort, timeout, and tool-call budgets.
- P2-5: Added batch ledger JSONL imports and rebuildable `ledger_index.json`.
- P2-6: Replaced the legacy runtime-style `research_engine.py` with a phase-instruction provider and deprecated `Source`/`ResearchState` shims.
- P2-7: Added `finish-run`, aligned phase/version/search-cli/template wording, and locked consistency checks in tests.
- P2-8: Added `reference/tool-routing.md`, trimmed always-loaded routing instructions, and lazy-loaded biotech/pharma details.
- P2-9: Added local file ingestion for PDFs, text, CSV/TSV tables, and images, with `file_manifest.jsonl`, `data_profile.jsonl`, and data-analysis guidance.
- P2-10: Added golden adversarial gate tests for negation, paraphrase, 0.60 floor, display-map ordering, subagent merge round-trip, DOI locators, and YEAR_RE regressions.
- P2-11: Added optional browser-automation Deep Crawler escalation after hard-target retrieval exhaustion, with no-bypass rules and evidence persistence gates.
- P2-12: Added per-section CitationAuditor package checkpoints and strict delivery-gate blocking for critical section citation issues while rejecting draft-while-retrieving streaming.
