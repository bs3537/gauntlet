# Excel model layout (produced by excel_builder.py)

IB conventions: font Calibri; **blue (#0000FF)** = hardcoded inputs, **black** = formulas, **green (#008000)** = cross-sheet links; fills dark-blue #1F4E79 (white bold) = section headers, light-blue #D9E1F2 = subheaders, light-grey #F2F2F2 = input cells, medium-blue #BDD7EE = key outputs / base-case. Formulas are live (recompute on open). Number formats: `#,##0.0` ($M), `0.0%` (rates), `#,##0.00` (per-share).

**Sheets by method:**
- **Summary** (always): company header, method, headline value, Key Outputs table (EV, equity, WACC, terminal g, per-share, scenario target) as static values, methodology/Damodaran pages, warnings.
- **DCF** (fcff/fcfe/ddm/apv): Assumptions (blue inputs: base CF, WACC/rate, stable g, rf, net debt, shares) → horizontal projection (Year/Growth/Cash flow/Period/Discount factor/PV, formula-chained) → Terminal value, PV(TV), Σ explicit PV, Enterprise value, − Net debt, Equity value, Value per share (all formulas) → embedded Sensitivity grid (values, base cell highlighted).
- **WACC** (fcff/apv): rf, beta, ERP, ke=rf+β·ERP, after-tax kd, market-value weights, WACC (formula).
- **rNPV_SOTP** (rnpv): per-asset table with rNPV `=MAX(LoA*PV_commercial−PV_dev,0)`, Σ pipeline, + net cash, − overhead, = equity, ÷ shares, per-share; Scenario table (Prob×Target → Σ weighted, rounded target).
- **Comps** (relative): peer table (outliers in red, "(excl.)"), applied multiple, implied value `=metric×multiple`, − net debt, per share.

Authoritative numbers live in `results.json`; the workbook is the auditable, editable model. With no LibreOffice, formulas compute when opened in Excel/Sheets; the Summary sheet carries static values meanwhile.
