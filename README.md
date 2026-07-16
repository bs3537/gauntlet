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

The bundled **`valuation` skill is grounded in the principles of Aswath Damodaran's *Investment
Valuation*** (its DCF / FCFF / FCFE / DDM, rNPV and real-options, relative-valuation, cost-of-capital,
and per-share / dilution methods) **and, for biotech, in the principles of the *Pharmagellan Guide to
Biotech Forecasting and Valuation*** (the risk-adjusted-NPV framework for pipeline assets). Gauntlet
layers the mandated conventions below on top of that foundation.

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
- **FinTwit / X sentiment — optional.** The default-on Tier-4 social-sentiment step (bundled `fintwit`
  companion) needs an **xAI API key** at `~/.claude/secrets/xai.env` (`XAI_API_KEY=…`, chmod 600, from
  console.x.ai). Without it, gauntlet simply skips FinTwit and notes it in the report — it never blocks
  a run.

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

You get back: the rating + weighted target + expected return in the first sentence; **openable
Windows paths to the three deliverables — `FINAL_REPORT.md`, the styled `FINAL_REPORT.html`, and the
detailed `<TICKER>_Gauntlet_Model.xlsx`** — plus the run directory (the full auditable artifact trail
described under *Outputs* below); the reviewer's score; and the 2–3 highest-impact adjudication
outcomes (what the second model caught, what was rejected and why).

## Outputs — a complete, auditable trail (in the run directory)

**Every step of a Gauntlet run is written to disk in `~/Documents/<TICKER>_Gauntlet_<YYYYMMDD>/`, so
the whole analysis is reproducible and auditable end to end — nothing important lives only in chat.**
You can open any intermediate artifact and trace the reasoning from raw evidence to the final call:
the scope and locked evidence ledger, the source manifest, the **first-pass (preliminary) report**,
the **four adversarial-lane reviews and the scored judge review**, the point-by-point **adjudication**
(every finding accepted / partial / rejected with its verification), the **executable valuation and
catalyst-PoS models** (and the audited engine's Excel/JSON outputs), the **detailed multi-scenario DCF
workbook**, the **final report** in Markdown and styled HTML, the Tier-4 FinTwit sentiment pull, and
the verification log. Keep the folder and you keep the entire paper trail.

| File(s) | What it is |
|---|---|
| `01_scope_and_assumptions.md` · `02_source_manifest.csv` · `03_evidence_ledger.csv` | scope/archetype, every source (tiered), and the locked atomic-claim ledger |
| `04_catalyst_and_pos_model.py` · `05_valuation_model.py` (+ `05_valuation_plan.json`, engine `*_rnpv_results.json` / `.xlsx` / `_validation.json`) · `06_model_outputs.csv` | the **executable** catalyst-PoS and valuation models plus their outputs |
| `07_working_research.md` · `08_preliminary_report.md` | working notes and the **first-pass report** the reviewer audits |
| `09_reviewer_*` · `10_reviewer_lane{1..4}.md` · `10_adversarial_review_gpt56sol.md` | reviewer prompts, the **four adversarial lanes**, and the **scored `/100` judge review** |
| `11_adjudication_and_corrections.md` | the **adjudication** — every reviewer finding ACCEPT / PARTIAL / REJECT with evidence |
| `fintwit_context.md` (+ `.json`) | Tier-4 FinTwit / X sentiment pull |
| **`FINAL_REPORT.md`** + **`FINAL_REPORT.html`** | the **final report** — Markdown plus a styled, self-contained twin (Gauntlet-branded, metric dashboard) |
| **`<TICKER>_Gauntlet_Model.xlsx`** | the **detailed, editable model** — per-scenario income-statement→FCF DCF, equity-value bridges, WACC, assumptions, and sensitivity tabs |
| `VERIFICATION_LOG.md` | commands, recomputations, the external-review round(s), reviewer score, and disposition counts |

On WSL the final `.md` / `.html` / `.xlsx` are also copied to a Windows-accessible Downloads folder and
presented as native `C:\Users\…` paths, so they open with a double-click (raw `file:///home/…` Linux
paths do not open from Windows).

## Modes: full review (default) vs fast (no review)

- **Full (default)** — the complete pipeline including the GPT-5.6 Sol adversarial review,
  adjudication, and gate. The cross-model review adds roughly an hour but is what makes the output
  decision-grade (it catches the blind spots and confident hallucinations a single model cannot see
  in itself). Total wall-clock ~1.5–2.5 hours.
- **Fast** (`/gauntlet fast <TICKER>` or `GAUNTLET_FAST=1`) — first-pass research + final report only,
  **skipping the adversarial review, adjudication, and gate**. Delivers a quick (~1-hour) single-model
  report that carries a prominent "NOT adversarially reviewed" banner and LOW confidence. Use it when
  speed matters more than the extra rigor; the default is always full review.

## Cost & quota (read before running)

A full run is **deliberately heavy** — four Opus 4.8 xhigh deep-research lanes plus a five-call
GPT-5.6 Sol codex panel (4 xhigh lanes + 1 max judge), each 15–60 minutes. One run can consume a
large share of a ChatGPT plan's 5-hour/weekly limits. Use it for **high-stakes names, not routine
screening**. Set `PANEL=0` to fall back to a single GPT-5.6 Sol max judge when quota is tight.

---

## Money-figure fraud screen + planted-fraud eval

Two additive validation layers guard the money figures:

- **Fraud screen (runtime, inside the reviewer).** The adversarial reviewer's D1 dimension
  ends with a six-pattern screen applied to every load-bearing money figure — *stale
  figure · headline-number omission (net debt / dilution / fees dropped, market-cap-vs-EV,
  P/E-vs-EV/EBIT) · guarantee language · base-rate / denominator abuse · cherry-picked
  window · projection as fact*. Strictly additive: dimension weights, score bands, and the
  reviewer's output contract are unchanged — hits surface as ordinary §4 claim-verification
  rows and feed the §7 calibration verdict.
- **Planted-fraud eval (`eval/`, off the runtime path).** A fictional, clearly-bannered
  doctored `08_preliminary_report.md` (Exemplar Grid Industries, "XGRD") carrying exactly
  six planted frauds — one per pattern — plus two clean controls, with a `GROUND-TRUTH.md`
  answer sheet the model under test never sees. `bash eval/check.sh` is the cheap
  deterministic gate (fixture ⇄ answer sheet ⇄ reviewer template kept in sync; no LLM, no
  network); the full test feeds the fixture through a real `PANEL=0` Stage-2 review and
  scores it against the answer sheet (**pass ≥ 5/6**). Smoke-grade by design — it validates
  that the screen exists and its patterns are catchable; it does not benchmark the reviewer.

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
- `eval/` — planted-fraud validation asset: fictional doctored preliminary report + GROUND-TRUTH answer sheet + deterministic `check.sh` (pure validation; the live pipeline never loads it).
- `docs/` — the approved implementation plan.

## Key design invariants (don't break these)

- **`FUSION_FAST` stays 0** — fast mode switches codex to `workspace-write` + `--ignore-user-config`, killing MCP connectors and run-dir writes.
- **Never** swap in the `model-council-fast` runner (its lib hardcodes `FUSION_FAST=1`), and **never** pass `FUSION_RUN_STAGE=review` to the hybrid runner (attaches its peer-review `--output-schema`); gauntlet uses `gauntlet_review`.
- **Absolute paths only** in codex payloads — the reviewer's cwd is a throwaway scratch dir.
- The **judge never spawns subagents**; the gauntlet session orchestrates the lanes.
