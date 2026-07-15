# Valuation memo template (scaffold)

`memo_builder.py` fills this from `results.json`. Sections render only when the data exists. Style mirrors an equity-research initiation (clinical, sectioned, page-anchored). Keep it honest: disclose warnings and the method rationale.

```
# {COMPANY} ({TICKER}) — Valuation

**Method: {METHOD}  |  Value: {HEADLINE}  |  As of {DATE}**

## 1. Summary
One paragraph: what it's worth, by what method, and the single biggest swing factor.
{For rnpv: scenario-weighted target, rounded target, upside vs current price.}

## 2. Why this method (Damodaran)
1–3 sentences tying the firm type to the method, citing method_selection.md / the index.
Pages consulted: {METHODOLOGY_PAGES}.

## 3. Valuation
{DCF methods}  rNPV/DCF bridge table: drivers → EV → (− net debt) → equity → per share;
              WACC build (rf, beta, ERP, ke, kd, weights); terminal value & TV% of EV.
{rnpv}        Per-asset SOTP table (peak, LoA, rNPV, per-share) → pipeline + net cash − overhead
              → equity → per share; scenario table → scenario-weighted → rounded target.
{relative}    Peer multiple table (with outliers flagged) → applied multiple → implied value
              → equity → per share; reconciliation vs intrinsic if both run.

## 4. Scenarios & convexity   {if scenarios}
Bull / Base / Bear targets, probabilities, drivers; scenario-weighted value; upside/downside vs price.

## 5. Sensitivity   {if grid}
Per-share across discount rate × terminal growth (or method-specific axes).

## 6. Risks & guardrails
Key risks; any validation warnings (e.g. TV% high); the dilution treatment note.

## 7. Methodology note (Damodaran-anchored)
Bullet the principles applied with page anchors:
- discount rate / WACC (market-value weights) — p.220
- terminal growth ≤ risk-free rate — p.306–307
- {dilution} fair-value future raise already in cash flows; no double-count — p.371/443/658
- {rnpv} patent/asset as risk-adjusted option — p.781–787
Divide intrinsic equity value by current/primary shares; options valued as a liability — p.446–447.

*For research only; not investment advice.*
```
