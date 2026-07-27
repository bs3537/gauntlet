# Report Assembly: Progressive File Generation

## Length Requirements by Mode

| Mode | Target Words | Description |
|------|--------------|-------------|
| Quick | 2,000-4,000 | Baseline quality threshold |
| Standard | 4,000-8,000 | Comprehensive analysis |
| Deep | 8,000-15,000 | Thorough investigation |
| UltraDeep | 15,000-20,000+ | Maximum rigor (at output limit) |

---

## Output Token Safeguard

**Claude Code default limit:** 32,000 output tokens (~24,000 words total per execution)

**Practical limits:**
- Target <=20,000 words total output
- Leave safety margin for tool call overhead
- Reports >20,000 words require auto-continuation (see continuation.md)

---

## Progressive Section Generation

**Core Strategy:** Generate and write each section individually using Write/Edit tools. This allows unlimited report length while keeping each generation manageable.

### Phase 8.1: Setup

```bash
# Create folder: ~/Documents/[TopicName]_Research_[YYYYMMDD]/
mkdir -p ~/Documents/[folder_name]

# Initialize markdown file with frontmatter
# Path: [folder]/research_report_[YYYYMMDD]_[slug].md
```

### Mandatory run-status line

Directly under the report title, before the executive summary, emit exactly one status line taken from `audit_manifest.json.run_status` -- never hand-authored:

- `**Status: Verified**` when `run_status == "verified"`
- `**Status: Partial - see Limitations**` when `run_status == "partial"`

`run_status` is computed by `scripts/audit_manifest.py` and flips to `partial` on any lane that was bounded, below target, or shipped with a disclosed gap; any support waiver; any surviving semantic-gate warning; any failed research subagent lane; any CitationAuditor issue resolved by hedging rather than a fix; and any trigger declared through `--partial-reason` (for example a Quick-mode Search-as-Code skip, or a `verify_citations` warning-pass).

A `partial` run is not a failed run: the strict delivery gate governs whether the report may ship at all, and `run_status` governs what the reader is told about it. Never write `**Status: Verified**` over a run whose manifest says `partial`, and when the status is `partial`, every reason in `run_status_reasons` must have a corresponding entry in Limitations.

### Phase 8.2: Section Generation Loop

**Pattern:** Generate section -> Write/Edit to file -> Move to next section
Each Write/Edit call contains ONE section (<=2,000 words per call)

**P2-12 package boundary:** Do not generate final narrative sections while retrieval, subagent evidence merge, plan coverage closure, or Phase 4.5 outline refinement is still active. Draft-while-retrieving streaming is rejected because it anchors the report to incomplete evidence. During retrieval, maintain notes, evidence tables, and outline stubs only; final section prose starts after the evidence-driven outline is stable.

**Initialize research run (persist to disk):**
```bash
# Create run manifest and artifact files using citation_manager CLI
python scripts/citation_manager.py init-run --out-dir [folder] --query "[question]" --mode [mode]
# Creates: run_manifest.json, sources.jsonl, display_map.json, evidence.jsonl, claims.jsonl
```

**Register each source as you encounter it:**
```bash
python scripts/citation_manager.py register-source \
  --json '{"raw_url": "...", "title": "...", "source_type": "academic", "year": "2024"}' \
  --dir [folder]
# Returns stable source_id (sha256-based, survives renumbering and continuation)
```

**Assign display numbers after all sources registered:**
```bash
python scripts/citation_manager.py assign-display-numbers --dir [folder] --write --order-from-report [report.md]
# Writes display_map.json and maps stable source_ids to [1], [2], [3]... for rendering
```

Source identity is stable across edits and continuation. Display numbers are persisted in `display_map.json` so claim extraction and audit gates resolve `[N]` labels to the same source IDs the report used instead of falling back to registration order.

**Section sequence:**

1. **Executive Summary** (200-400 words)
   - Tool: Write(file, frontmatter + Executive Summary)
   - Track citations
   - Run section CitationAuditor and save `audit/section_citation_issues/executive_summary.json`
   - Progress: "Executive Summary complete"

2. **Introduction** (400-800 words)
   - Tool: Edit(file, append Introduction)
   - Track citations
   - Run section CitationAuditor and save `audit/section_citation_issues/introduction.json`
   - Progress: "Introduction complete"

3. **Finding 1-N** (600-2,000 words each)
   - Tool: Edit(file, append Finding N)
   - Track citations
   - Run section CitationAuditor and save `audit/section_citation_issues/finding_[n].json`
   - Progress: "Finding N complete"

4. **Synthesis & Insights**
   - Novel insights beyond source statements
   - Tool: Edit(append)

5. **Limitations & Caveats**
   - Counterevidence, gaps, uncertainties
   - Tool: Edit(append)

6. **Recommendations**
   - Immediate actions, next steps, research needs
   - Tool: Edit(append)

7. **Methodology Appendix**
   - Research process, verification approach
   - Tool: Edit(append)

8. **Evidence artifacts**
   - Save full source metadata in `sources.jsonl`
   - Save claim evidence in `evidence.jsonl` and `claims.jsonl`
   - Save per-section CitationAuditor outputs in `audit/section_citation_issues/`; use `[]` for sections with no issues
   - Do not append a full bibliography, full source list, or long "Sources Used" section to the main report unless the user explicitly requests it. Store full metadata in external ledgers; if useful, add only a 1-3 line "Evidence Artifacts" note pointing to `sources.jsonl`, `evidence.jsonl`, and `claims.jsonl`.

### Dual-locator provenance (material claims)

When a material claim carries independent verification (`verifier_quote` + `verifier_locator`, written by CitationAuditor per Phase 7.5) **and** the auditor's `verifier_source_url` or `verifier_locator` differs from the source that was originally cited, show that the check was independent rather than a re-read of the same page. In the Claims-Evidence table or the claim's supporting line, append:

```
(independently checked against "<verifier source title>" - <verifier_locator>)
```

Render this only on the difference. When the auditor re-opened the same URL at the same locator, the annotation adds noise and must be omitted -- the `verified_independently_at` timestamp in `claims.jsonl` already records that the check happened. This is display-only: it changes no gate, and `audit_manifest.py` decides materiality and sufficiency independently of whether the annotation was rendered.

---

## File Organization

**1. Create dedicated folder:**
- Location: `~/Documents/[TopicName]_Research_[YYYYMMDD]/`
- Clean topic name (remove special chars, use underscores)

**2. File naming convention:**
All files use same base name:
- `research_report_20251104_topic_slug.md`
- `research_report_20251104_topic_slug.html`
- `research_report_20251104_topic_slug.pdf`
- `sources.jsonl`
- `display_map.json`
- `evidence.jsonl`
- `claims.jsonl`
- `file_manifest.jsonl` when local files are used
- `data_profile.jsonl` when local CSV/TSV tables are profiled
- `ingested_files/` for extracted text produced by `file_ingest.py`; do not mutate original files
- `analysis/` for reproducible scripts/notebooks/formulas/calculation logs and derived tables
- `browser_crawl/` for optional Deep Crawler screenshots, rendered-page notes, or browser traces used as provenance/locator artifacts
- `audit/section_citation_issues/` for per-section CitationAuditor JSON produced during Phase 8 packaging

**3. Also save copy to:** `~/.claude/research_output/` (internal tracking)

**4. Before HTML/PDF/user delivery, run the strict package gate:**

```bash
python scripts/citation_manager.py assign-display-numbers --dir [folder] --write --order-from-report [report.md]
python scripts/delivery_gate.py --dir [folder] --report [report.md] --strict --semantic --require-section-citation-audits
```

The delivery gate checks both `[folder]/audit/citation_issues.json` and `[folder]/audit/section_citation_issues/*.json`; strict delivery blocks on any critical final or per-section CitationAuditor issue. Do not convert to HTML/PDF, open the report, or mark the run delivered unless the gate passes and `[folder]/audit_manifest.json` has `status: pass`.

---

## Word Count Per Section

**CRITICAL:** No single Edit call should exceed 2,000 words.

Example: 10 findings x 1,500 words = 15,000 words total
- Each Edit call: 1,500 words (under limit)
- File grows to 15,000 words
- No single tool call exceeds limits
