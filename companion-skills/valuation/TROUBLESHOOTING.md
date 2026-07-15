# Troubleshooting — valuation skill

**Validation status = FAIL.** Read `<...>_validation.json`. Common causes:
- *Terminal growth ≥ discount rate* or *> risk-free rate* → lower `stable_growth` (cap at the risk-free rate / nominal GDP) [growth_and_terminal.md p.306–307].
- *rNPV LoA not in [0,1]* → a probability was entered as a percent (e.g. 58 instead of 0.58).
- *No headline value* → for DCF/rNPV you must supply `shares` to get a per-share figure.

**Engine raises `ValueError` before finishing (method-input guardrails, added 2026-07-11).** These are deliberate hard-stops that used to be silent wrong numbers — fix the plan, don't work around them:
- *"FCFE requires a cost of EQUITY (ke), not a firm WACC"* → set `dcf.rate` to the cost of equity, or give WACC build inputs (`rf`/`erp`/`beta`) so the engine computes `cost_of_equity`. FCFE is never discounted at WACC.
- *"APV requires an unlevered cost of equity ρu"* → set `dcf.rho_u`, or supply `wacc` build inputs (`rf`, `erp`, `beta`/`peer_betas`, `equity_value`/`debt_value`) so β can be unlevered. APV must not use WACC.
- *"relative.basis is required for equity (P/*) multiples"* → set `relative.basis` to `per_share` (target_metric = EPS/BVPS/SPS) or `aggregate` (target_metric = total NI/book equity/sales, $M). EV/* multiples default to `aggregate`.
- *"rNPV asset '…': pv_commercial is required"* → give the PV of risk-unadjusted commercial cash flows; `peak_sales` is a headline figure, not a present value.
- *"DDM stable growth … exceeds risk-free rate"* → lower `ddm.stable_growth` to ≤ `ddm.rf`.
- *"payout_high … is required when payout_stable is supplied"* → for a two-stage DDM payout step-up, pass both `ddm.payout_high` and `ddm.payout_stable`.

**Excel opens but cells show 0 / blank, or validator says "recalc unavailable."** No LibreOffice (`soffice`) is installed, so openpyxl can't pre-compute formula values. The formulas are correct and compute the moment the file is opened in Excel/Sheets. The `Summary` sheet always carries the static computed values, and the authoritative numbers are in `results.json`. To enable a cached-value scan, install LibreOffice and re-open/save, or trust `results.json` (the math source of truth).

**FMP returns 401/403.** You used a retired `/api/v3/` or `/api/v4/` endpoint — use `/stable/` only. If the claude.ai FMP MCP says "Server not found," fall back to `~/.fmp_api_key` + curl `https://financialmodelingprep.com/stable/...`. `earningsTranscript` is plan-gated (ACCESS DENIED) — get transcripts via Perplexity + the 8-K.

**WACC looks wrong / outside 5–20%.** Check market-value (not book) weights, and that beta is bottom-up (unlever peers → relever to firm D/E) for private/pre-revenue/recent-IPO names [cost_of_capital.md]. For a legitimately high emerging-market discount rate, set `wacc.crp` (country-risk premium) so the band widens to 5%–(20%+crp) instead of warning; override the tax band with `wacc.tax_band` for non-US jurisdictions.

**Terminal value is >80% of EV.** Either the explicit horizon is too short (extend the high-growth/fade stages) or growth/margins are too high. This is a warning, not an error — but disclose it.

**`ModuleNotFoundError` when running a script directly.** Run from the skill `scripts/` dir, or rely on `valuation_engine.py`, which inserts its own dir on `sys.path`. Install deps: `pip install -r ../requirements.txt`.

**memo_builder produced an empty/odd section.** It only renders sections present in `results.json` (e.g., no `scenarios` → no scenario table). Re-run the engine with the missing inputs in `plan.json`.

**Method choice feels wrong.** Re-run STEP 0: read `references/method_selection.md` and re-classify (distressed? negative earnings? financial-service firm? biotech pipeline?). The wrong method is the most expensive error — fix it before modelling.
