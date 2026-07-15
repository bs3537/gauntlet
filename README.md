# Gauntlet — two-model adversarial equity research

Gauntlet produces institutional-grade equity research that **must survive a hostile second
model from a different vendor before it ships**. One frontier model researches and drafts;
a different-vendor frontier model attacks the draft; the first model then adjudicates every
finding with evidence and only then writes the final report. It exists to kill the two things
a single model cannot catch in itself: **unchallenged blind spots** and **confident-recall
hallucinations**.

**Explicit invocation only** — run it with `/gauntlet <TICKER>` (or "run the gauntlet on X").
A bare ticker, "deep dive", or "analyze" does **not** trigger it.

---

## Architecture at a glance

```text
                    ┌──────────────────────── STAGE 1: FIRST PASS ────────────────────────┐
                    │  Opus 4.8 max  =  ORCHESTRATOR / REVIEWER / JUDGE                    │
                    │      │                                                               │
   /gauntlet TICKER │      ├── deep-research (ultradeep) → 4 concurrent lanes             │
        │           │      │        Opus 4.8 · xhigh   (+ Search-as-Code 2nd pass)        │
        ▼           │      ├── extra Opus 4.8 xhigh Agent subagents (gap-fill)            │
   Stage 0 intake   │      └── QC + independent verify + synthesize → 08_preliminary_report│
   + codex preflight└──────────────────────────────────┬──────────────────────────────────┘
                                                        │  (draft + artifacts on disk)
                    ┌───────────────────────── STAGE 2: ADVERSARIAL REVIEW ───────────────┐
                    │  GPT-5.6 Sol max  =  ORCHESTRATOR / JUDGE   (via codex CLI)          │
                    │      ├── lane 1  D1 factual + rerun 04/05 models   ┐                 │
                    │      ├── lane 2  D2 blind spots + missed signal    │ GPT-5.6 Sol     │
                    │      ├── lane 3  D3–D4 counter-thesis + logic      │ xhigh ×4        │
                    │      ├── lane 4  D5–D6 sources + calibration       ┘                 │
                    │      └── JUDGE verifies + reconciles → 10_adversarial_review (/100)   │
                    └──────────────────────────────────┬──────────────────────────────────┘
                                                        ▼
        Stage 3 ADJUDICATION → Stage 4 GATE (±1 bounded round 2) → Stage 5 FINAL_REPORT.md
```

Both sides **fan out, then judge**. The generator side supplies breadth and internal
cross-checking; the reviewer side — a *different vendor* — supplies the missing cross-vendor
perspective. Neither replaces the other.

| Role | Model | Effort | Where |
|---|---|---|---|
| First-pass orchestrator + adjudicator | Opus 4.8 | max | this Claude Code session |
| First-pass research lanes / subagents (×4+) | Opus 4.8 | xhigh | deep-research ultradeep + Agent subagents |
| Reviewer research lanes (×4) | GPT-5.6 Sol | xhigh | `codex exec` (launched by Stage 2) |
| Reviewer orchestrator / judge | GPT-5.6 Sol | max | `codex exec` (launched by Stage 2) |

---

## How it works, stage by stage

- **Stage 0 — Intake + preflight.** Fill the master prompt's INPUT BLOCK (company, ticker,
  as-of date, price to verify, horizons, constraints), create the run directory
  `~/Documents/<TICKER>_Gauntlet_<YYYYMMDD>/`, and ping codex to fail fast if it is
  unauthenticated.
- **Stage 1 — First-pass research (fan-out).** Opus 4.8 max executes the universal master
  research prompt (Phases 0–6: scope/archetype, proof-based foundation, competitive moat,
  catalyst probability-of-success ensembles, financials + valuation, synthesis/convexity). It
  does **not** research alone: it drives **deep-research at `ultradeep`** (four Opus 4.8 xhigh
  lanes on non-overlapping evidence streams) plus targeted subagents, QCs every lane, verifies
  load-bearing claims itself, locks an evidence ledger, and writes `08_preliminary_report.md`.
- **Stage 2 — Adversarial review (panel).** The gauntlet session launches **four GPT-5.6 Sol
  xhigh codex lanes** — each attacking a different rubric slice — then a **GPT-5.6 Sol max
  judge** that treats the lane findings as claims to verify, reruns the Python models, does its
  own independent searches, reconciles disagreements, and emits one review scored `/100`. (A
  `codex exec` process never spawns its own subagents; the session orchestrates all five calls.)
- **Stage 3 — Adjudication.** The first-pass model writes a pre-analysis, then dispositions
  **every** finding — ACCEPT / PARTIAL / REJECT — only after *independent* verification (open
  the reviewer's source, reopen its own ledger locator, rerun the disputed computation), and
  applies sustained corrections to the models, ledger, and draft.
- **Stage 4 — Gate.** Proceed when corrections are applied, the score is ≥ 60, and no sustained
  CRITICAL flips the rating; otherwise run **one** bounded round-2 review of the corrected draft
  (judge-only). A persistent failure still ships — with a LOW-CONFIDENCE banner.
- **Stage 5 — Final report.** Regenerate the Wall-Street-format report (master prompt Phase 8)
  from the corrected artifacts. The adversarial process itself lives in `VERIFICATION_LOG.md`,
  not the report body.

---

## Valuation (built in)

For **developmental-stage biotech/pharma with no marketed product**, the master prompt (§4B)
uses mandated base-case conventions — regional epidemiology (US / EU5 / ROW-incl-Japan), US net
ASP = 0.74 × comparator WAC, ex-US ASP = 0.50 × US, US-first launch with EU/ROW +1yr, peak sales
six years after launch, 15% WACC, risk carried singularly in PoS, full pre/post-launch opex, and
a fully-diluted-**today** per-share bridge with no hypothetical future dilution — and **delegates
the rNPV mechanics to the audited `valuation` skill engine** rather than hand-rolling them.
`05_valuation_model.py` becomes a thin wrapper that emits a declarative `05_valuation_plan.json`
and calls `valuation/scripts/valuation_engine.py`; the reviewer reruns the same engine (mirrored
in the codex tree) and cross-checks the rNPV independently.

---

## Bundled companion skills (no separate install)

Gauntlet orchestrates four other skills. **They ship inside this repo under
[`companion-skills/`](companion-skills/)** — cloning gauntlet gets you every dependency in one
go; there is nothing else to download or install separately.

| Skill | Role in Gauntlet | Needed by |
|---|---|---|
| **`deep-research`** | Stage-1 breadth engine, run at `ultradeep` (4 Opus 4.8 xhigh lanes) | first pass |
| **`search-as-code`** | deep-research's second-pass source-discovery harness | first pass |
| **`valuation`** | Damodaran-grounded rNPV/DCF/SOTP engine (dev-stage biotech §4B) | first pass + reviewer |
| **`hybrid-model-fusion`** | provides `scripts/run_codex.sh`, the hardened codex launcher | reviewer |

> **Damodaran text (optional — standalone `valuation` deep-lookups only).** The bundled `valuation`
> skill ships original *method → chapter/page* reference **notes** and its engine hard-codes the
> formulas, so **Gauntlet and the rNPV/DCF engine need nothing more**. The skill's *standalone*
> STEP 0 deep page-lookups additionally `grep` the full text of Damodaran's *Investment Valuation*
> (3rd ed.) at `~/valuation_reference/damodaran_investment_valuation_fulltext.txt` (page-delimited
> `===== PAGE N =====`). That book is **© John Wiley & Sons — not redistributed here**; to enable
> those lookups, obtain your own copy and place it there. Damodaran also publishes extensive **free**
> valuation material — lecture notes, chapter front matter, spreadsheets — on his official NYU site
> (<https://pages.stern.nyu.edu/~adamodar/>). ("Available as a PDF somewhere on the web" does **not**
> make the book public-domain — it stays Wiley-copyrighted, so it is not bundled or linked here.)

---

## External data sources & tools you must provide

The bundled skills are the *orchestration* — they are not useful until you connect them to live
data and search. **None of the following are bundled**; supply whichever your target names
require:

- **Financial data — required.** An **FMP (Financial Modeling Prep)** API key
  (`~/.fmp_api_key`, and/or the FMP MCP) for quotes, financials, filings, estimates, and
  ownership — use FMP `/stable/` endpoints. **Or substitute an equivalent financial-data
  provider** your MCPs/models can reach; Gauntlet just needs *some* authoritative fundamentals +
  market-data source.
- **Literature search — required for source-backed research; pick per domain.**
  - **Biomedical / biotech names** → **BioMCP** (PubMed / PMC) as the backbone, plus
    **Semantic Scholar** (`S2_API_KEY`) for citation graphs and **Scite** for citation context,
    retraction / editorial-notice checks, and full text.
  - **Tech / general / non-bio names** → **Scite** and/or **Semantic Scholar** for technical
    literature.
- **Web search for `search-as-code` — required, but zero-config by default.** search-as-code runs
  on the **LLM's native web search** out of the box (no key needed). For programmable,
  cost-tracked query fanout you can instead wire an external web-search API — **Perplexity, Brave,
  or Exa** — via that provider's API key.
- **Reviewer side (Stage 2) — required for the cross-model review.** The **`codex` CLI** on PATH
  and authenticated for **`gpt-5.6-sol`** (a ChatGPT plan with sufficient quota), with the
  scite / fmp / biomcp / perplexity MCPs configured in `~/.codex/config.toml`. Without codex,
  Stage 2 falls back to a labeled same-model self-review.

See each bundled skill's own `SKILL.md` / `README.md` for its exact key names and MCP setup.

---

## Install / deploy

Clone the repo and run the installer — it copies gauntlet **and** all four companion skills into
your Claude Code skills tree (and mirrors the reviewer-side `valuation` engine into the codex
tree) in one step:

```bash
git clone https://github.com/bs3537/gauntlet.git
cd gauntlet
./install.sh
```

Gauntlet is a **Claude-tree-orchestrated** skill: its canonical copy lives at
`~/.claude/skills/gauntlet/`, and the `~/.codex/skills/gauntlet/` copy is parity/reference only
(do not invoke it from codex — codex is the reviewer *target*, and running it there would make the
reviewer self-review). The installer sets up both trees.

Prefer to do it by hand? Copy the trees yourself:

```bash
# Claude tree — gauntlet + every companion skill
cp -r SKILL.md scripts references README.md ~/.claude/skills/gauntlet/
cp -r companion-skills/* ~/.claude/skills/

# Codex tree — the reviewer needs valuation to rerun the engine (+ gauntlet parity copy)
cp -r companion-skills/valuation ~/.codex/skills/
cp -r SKILL.md scripts references README.md ~/.codex/skills/gauntlet/
```

Then configure the external data sources above, and you are ready to invoke.

## Invoke

```
/gauntlet TSLA
run the gauntlet on <TICKER>
```

You get back: the rating + weighted target + expected return in the first sentence; **direct
clickable links to both deliverables — `FINAL_REPORT.md` and the styled `FINAL_REPORT.html`** — plus
the run directory; the reviewer's score; and the 2–3 highest-impact adjudication outcomes (what the
second model caught, what was rejected and why).

## Outputs (in the run directory)

`01_scope…` · `02_source_manifest.csv` · `03_evidence_ledger.csv` · `04_catalyst_and_pos_model.py`
· `05_valuation_model.py` (+ `05_valuation_plan.json` + engine `*_rnpv_results.json/.xlsx`) ·
`06_model_outputs.csv` · `07_working_research.md` · `08_preliminary_report.md` ·
`09_reviewer_*` prompts · `10_reviewer_lane{1..4}.md` + `10_adversarial_review_gpt56sol.md` ·
`11_adjudication_and_corrections.md` · **`FINAL_REPORT.md`** + **`FINAL_REPORT.html`** (styled,
self-contained twin — same content in a Gauntlet-branded template with a rating / target / return /
reviewer-score metric dashboard) · `VERIFICATION_LOG.md`.

## Cost & quota (read before running)

A full run is **deliberately heavy** — four Opus 4.8 xhigh deep-research lanes plus a five-call
GPT-5.6 Sol codex panel (4 xhigh lanes + 1 max judge), each 15–60 minutes. One run can consume a
large share of a ChatGPT plan's 5-hour/weekly limits. Use it for **high-stakes names, not routine
screening**. Set `PANEL=0` to fall back to a single GPT-5.6 Sol max judge when quota is tight.

---

## File layout

- `SKILL.md` — the orchestrator: Stages 0–5, gates, gotchas, env tuning (the operational contract).
- `references/master_research_prompt.md` — the universal institutional research prompt (Phases 0–6 + 8, the Stage-1 fan-out model, §4B valuation-engine delegation, degraded-mode self-review appendix).
- `references/reviewer_prompt_template.md` — the GPT-5.6 Sol adversarial **judge** prompt (panel mode, rubric D1–D7, delivery contract, placeholders incl. `{{LANE_FINDINGS}}`).
- `scripts/run_review.sh` — hardened codex launcher + QC gate; reused per research lane (`QC_MODE=lane`, path overrides) and for the judge (`QC_MODE=judge`).
- `scripts/render_report.sh` — renders `FINAL_REPORT.md` → styled `FINAL_REPORT.html` (+ optional PDF) via the bundled deep-research `md_to_html.py`; prints the HTML path.
- `references/gauntlet_report_template.html` — the Gauntlet-branded HTML template (McKinsey-style, metric dashboard) `render_report.sh` fills.
- `install.sh` — one-shot installer: copies gauntlet + all companion skills into the Claude tree and mirrors the reviewer-side `valuation` into the codex tree.
- `companion-skills/` — the four bundled dependencies (`deep-research`, `search-as-code`, `valuation`, `hybrid-model-fusion`), so a clone is self-contained.
- `docs/` — the approved implementation plan.

## Key design invariants (don't break these)

- **`FUSION_FAST` stays 0** — fast mode switches codex to `workspace-write` + `--ignore-user-config`, killing MCP connectors and run-dir writes.
- **Never** swap in the `model-council-fast` runner (its lib hardcodes `FUSION_FAST=1`), and **never** pass `FUSION_RUN_STAGE=review` to the hybrid runner (attaches its peer-review `--output-schema`); gauntlet uses `gauntlet_review`.
- **Absolute paths only** in codex payloads — the reviewer's cwd is a throwaway scratch dir.
- The **judge never spawns subagents**; the gauntlet session orchestrates the lanes.
