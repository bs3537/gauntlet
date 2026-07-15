# valuation — Damodaran-grounded multi-method valuation skill

A Claude Code / Codex / agy **skill** that values a company, security, or asset by the method that fits it — grounded in Aswath Damodaran's *Investment Valuation* (3rd ed.). It **reads the relevant Damodaran guidance first**, selects the method for the firm type, runs audited Python math (never model weights), and emits an **Excel model + a narrative memo**. Also serves as the valuation stage (Section 09) of the Investment Research AI Agent.

## Methods
- **Intrinsic DCF**: FCFF, FCFE, DDM, APV — multi-stage, guardrailed terminal value, EV→equity→per-share
- **Cost of capital**: bottom-up beta, implied ERP, synthetic-rating cost of debt, market-value WACC
- **rNPV / SOTP + real options**: patent-as-call, equity-as-call; scenario weighting
- **Relative / comps**: P/E, PEG, EV/EBITDA, P/B, EV/Sales; peer IQR outliers; regression
- **Special cases** (reference-guided): financials, cyclical/commodity, young, private, distressed

## Layout
- `SKILL.md` — dispatcher; **STEP 0 = "read Damodaran first, then value"**
- `references/` — 11 page-anchored Damodaran distillations (`damodaran_index.md` read first)
- `scripts/` — calculators + orchestrator + Excel builder + validator + memo builder (each has a `selftest`)
- `schemas/` · `templates/` · `tests/`

## Use
1. Assemble a `plan.json` (`schemas/valuation_plan.schema.json`; units = $M, rates = decimals).
2. `python3 scripts/valuation_engine.py run --plan plan.json --out-dir DIR` → `results.json` + `model.xlsx` + `validation.json`
3. `python3 scripts/memo_builder.py --results <...>_results.json --out DIR` → memo `.md`/`.docx`

Run every self-test: `bash tests/run_all.sh`. Guardrails (auto-enforced by `validate_valuation.py`): terminal g ≤ risk-free < WACC, terminal value 40–80% of EV, market-value WACC, rNPV LoA ∈ [0,1], and Damodaran-correct dilution (a fair-value future raise is already in the cash flows — not double-counted; only a below-intrinsic raise transfers value).

## Damodaran corpus (NOT in this repo)
The skill greps the full book text on demand from `~/valuation_reference/damodaran_investment_valuation_fulltext.txt` (993 pages, page-delimited) — intentionally **not** committed. The `references/` here are short, page-anchored distillations + a method→page index. Put the fulltext at `~/valuation_reference/` for deep lookups (see `references/data_sourcing_wsl.md`).

## Cross-ecosystem
Scripts are location-independent (`__file__`-relative). Mirror to Codex / agy with `tests/sync_to_codex.sh` / `tests/sync_to_gemini.sh` (localizes `.claude`→`.codex`/`.gemini` in `*.md`; scripts unchanged).

## Requirements
`pip install --user --break-system-packages -r requirements.txt` — numpy, scipy, openpyxl, python-docx. LibreOffice optional (formulas compute on open without it).

---
*Private. Damodaran excerpts in `references/` are short, page-anchored quotations for personal study use; the full copyrighted text is not included.*
