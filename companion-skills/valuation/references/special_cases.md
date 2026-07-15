# Special Case Valuation — Sector Playbooks

**Source:** Damodaran, *Investment Valuation* (3rd ed.). Page anchors: `[printed p.X / PDF p.Y]`.  
**Offset:** PDF = printed + 19.

---

## 1. Financial Service Firms (Banks, Insurance, Investment Banks)

**Chapter 21 [printed p.581-629 / PDF p.600-648]**

### Core problem

Debt is raw material, not capital. You cannot define FCFF or WACC meaningfully because:
- Deposits and other borrowings are the inputs that banks transform into loans — they are not "financial leverage" in the usual sense.
- Capital at a financial service firm = **equity capital only** (reinforced by regulatory capital ratios).
- Net capex and working capital changes are undefined or meaninglessly large.
- Regulatory constraints directly cap reinvestment and growth.

**Consequence: FCFF/WACC does NOT apply to financial service firms.** EV/EBITDA multiples also fail. You must value equity directly. [printed p.583-584 / PDF p.602-603]

### Adjusted methods

**Option A — Dividend Discount Model (preferred when dividends ≈ sustainable FCFE)**

```
Value of equity = Σ DPSt / (1+ke)^t

Stable: P = DPS₁ / (ke − g)

Payout in stable growth:
  Payout ratio = 1 − g / ROE_stable

  (If ROE < ke in stable growth → firm destroys value; payout must still be set to
   achieve target g, but value will be below book equity)
```

Key inputs:
- ke from CAPM: use average **levered** beta of comparable financial firms (do NOT unlever/relever — leverage is structural and homogeneous across sector peers). [printed p.585-586 / PDF p.604-605]
- Expected growth = Retention ratio × ROE [printed p.587 / PDF p.606]
  `g = (1 − payout) × ROE`  or if ROE changing: `g = (1−payout) × ROE_{t+1} + (ROE_{t+1} − ROE_t)/ROE_t`
- Stable growth ≤ nominal GDP / risk-free rate. [printed p.587-588 / PDF p.606-607]

**Option B — FCFE model (when dividends diverge from FCFE)**

Redefine reinvestment as investment in **regulatory capital**:
```
FCFE = Net income − Increase in equity regulatory capital required to support growth
```
If bank targets a capital ratio of c and wants to grow assets by ΔA:
`Required equity reinvestment = c × ΔA`
`FCFE = Net income − Required equity reinvestment`

[printed p.592-595 / PDF p.611-614]

**Option C — Excess Return Model**

```
Value of equity = Equity capital invested currently
                + PV(Excess equity returns)

Excess equity return = (ROE − ke) × Equity capital invested
```

A bank earning ROE = ke has market value = book value (P/B = 1).  
ROE > ke → P/B > 1; ROE < ke → P/B < 1. [printed p.596-597 / PDF p.615-616]

This is the theoretically cleanest model because it directly links value to the bank's ability to earn above its cost of equity.

### Relative valuation

- **P/B is the primary multiple** for financial service firms — assets are often marked to market, so book value is meaningful. [printed p.600 / PDF p.619]
- P/E is secondary; use when comparing firms with similar ROE and payout.
- EV/Sales and EV/EBITDA: NOT applicable.

### Guardrails

- Regulate-adjusted beta: if regulatory environment has been stable, regression beta can be used; if rules are changing (e.g., post-crisis), use sector average levered beta instead. [printed p.585 / PDF p.604]
- Provisions for bad loans affect reported earnings and P/E — banks with more conservative provisioning show lower earnings and higher P/E. Normalize for this when comparing. [printed p.600 / PDF p.619]
- Never assume retained earnings alone fund growth unless capital ratio is below target; otherwise, excess capital just accumulates and does not earn a return. [printed p.594 / PDF p.613]

---

## 2. Cyclical Firms / Commodity Producers

**Chapter 22 [printed p.611-661 / PDF p.630-680]**

### Core problem

Earnings and cash flows track the economic cycle or commodity price cycle. Using current (trough or peak) earnings as the base creates systematically wrong valuations. [printed p.611-612 / PDF p.630-631]

Signs you have a cyclical/commodity problem:
- Historical growth rate is negative even though firm is profitable on average
- Current operating margin far above or below 5-10 year average
- Earnings highly correlated with GDP or a commodity price index

### Adjusted methods

**Normalize earnings (primary approach):**

```
Method A — Average dollar earnings over a full cycle (5-10 years):
  Normalized earnings = Average(EBIT or Net Income, t-5 to t)
  ⚠ Only valid if firm size has not changed materially.

Method B — Average margin × current revenues (preferred for size-changing firms):
  Average operating margin = Mean(EBIT/Revenue, t-5 to t)
  Normalized EBIT = Average margin × Current revenues
  → Captures both scale change and cyclicality [printed p.619-620 / PDF p.638-639]

Method C — Industry average margin (use when firm-specific margin data is scarce):
  Normalized EBIT = Industry average margin × Current revenues
  ⚠ Understates if firm is above-average within sector.
```

**Normalized reinvestment rate:**
```
  Stable reinvestment rate = g / ROC
```
Build DCF from normalized EBIT × (1 − tax) × (1 − reinvestment rate), discounted at normalized WACC (use sector average beta, not regression beta from trough period).

**Timing discount:** If normalization is expected to take several periods, discount the normalized value back:
`Value = Normalized value / (1 + cost of capital)^n_periods_to_recovery` [printed p.619 / PDF p.638]

**For commodity firms specifically:**
Three choices [printed p.621 / PDF p.640]:
1. Forecast commodity prices from futures market curve → build explicit revenue path
2. Use normalized commodity price (long-run average over a cycle)
3. Value current production at current price + value undeveloped reserves as real options (Ch.28)

### Relative valuation

- **Normalized P/E**: use earnings-per-share averaged over the cycle, not trailing.
- **EV/EBITDA**: useful but also needs cycle-average EBITDA.
- Rule: never use a trough multiple on trough earnings or a peak multiple on peak earnings — this double-counts the cyclical effect.

### Guardrails

- Use **higher betas and/or higher cost of debt** to capture cyclical earnings variability through the discount rate, not just the cash flows. [printed p.622 / PDF p.641]
- Do not embed specific macroeconomic recession/recovery timing predictions — this makes your valuation hostage to macro forecasts that are usually wrong. [printed p.617 / PDF p.636]
- For cyclical ﬁrms using higher near-term growth to capture recovery: `This ties accuracy to precision of macroeconomic predictions.` Prefer normalized earnings unless near-term recovery timing is extremely well-evidenced. [printed p.617-618 / PDF p.636-637]

---

## 3. Young / Start-Up Firms

**Chapter 23 [printed p.643-685 / PDF p.662-704]**

### Core problem

- Revenues low or zero; earnings negative; no history; few comparables.
- Most of value comes from future growth potential, not current assets.
- Standard growth formulas (g = RR × ROC) break down with negative earnings.
- Risk is extreme and undiversified capital providers (VCs) use target-rate shortcuts that embed both risk AND negotiating power — not a reliable discount rate. [printed p.646-648 / PDF p.665-667]

### Adjusted method — Revenue-forward DCF

**Step 1: Revenue anchor**
Pick a reasonable end-state revenue (Year 10-15) from addressable market analysis.  
Work backwards to set annual growth rates; ensure they decelerate over time.  
`Key: the starting and ending revenues matter most; year-by-year rates are secondary.` [printed p.649 / PDF p.668]

**Step 2: Operating margin path**
Current margin is negative. Estimate sustainable stable-state margin from mature comparable firms in the same underlying business (not just the subsector label).  
Interpolate margin linearly from current to stable over the projection period. [printed p.650 / PDF p.669]

**Step 3: Reinvestment — Sales/Capital ratio**
When earnings are negative, ROC is undefined. Use:
```
Expected reinvestment = ΔRevenue / (Sales/Capital ratio)
```
Obtain Sales/Capital from industry averages. For stable state:
```
Reinvestment rate = g / ROC_stable
```
[printed p.651 / PDF p.670]

**Step 4: NOL carry-forward tracking**
Accumulate losses as NOLs. Zero effective tax rate until NOLs are exhausted.  
Full marginal tax rate applies only after NOLs clear. [printed p.652-653 / PDF p.671-672]

**Step 5: Beta — bottom-up from public comps**
No regression beta possible. Use average unlevered beta from comparable public firms; relever to firm's target D/E. [printed p.662-668 / PDF p.681-687]

**Step 6: Survival discount**
If near-term cash burn threatens solvency:
```
Adjusted value = DCF value × (1 − P[distress]) + Distress-sale value × P[distress]
```
[printed p.319 / PDF p.338]

### Dilution from future equity raises — critical rule

Future equity raises are financing decisions, not operating costs. The negative near-term FCFs already price in the cash the firm will need. **Do NOT additionally charge dilution on top of negative FCFs — this is double-counting.**

When shares outstanding increase via a future round at fair value, value per existing share does not change (value transferred equals shares issued times price per share). For warrants/options already outstanding, use dilution-adjusted value per share per Ch.16 [printed p.423-443 / PDF p.442-462].

Cross-link: `references/damodaran_dilution_principles.md` for the full treatment. [printed p.371 / PDF p.390; printed p.443 / PDF p.462; printed p.658 / PDF p.677]

### Relative valuation

- **P/S or EV/Sales**: when earnings are negative, price-to-sales is the only widely-applicable multiple.
- EV/Revenue is preferred when leverage differs across peers.
- Validate implied forward margins: `does the P/S multiple imply a reasonable eventual margin?`

### Guardrails

- Use trailing 12-month revenues, not annual report — high-growth firm numbers shift dramatically. [printed p.648 / PDF p.667]
- Venture capital "target return" approach (30-70% discount rates) is not a risk model — it conflates risk, illiquidity, and negotiating power. Do not use for intrinsic value. [printed p.646-647 / PDF p.665-666]
- Sector metrics like "value per site visitor" or "value per user" are comparables shortcuts, not valuations. They can be used as relative checks only if the implicit margin and growth assumptions are made explicit and tested. [printed p.643-644 / PDF p.662-663]

---

## 4. Private Firms

**Chapter 24 [printed p.667-720 / PDF p.686-739]**

### Core problem

- No market price for equity → no regression beta.
- Owner is often undiversified (all wealth in the firm) → exposed to total risk, not just market risk.
- Personal expenses intermixed; owner salary may not reflect market rate.
- Value depends on who is buying (IPO buyers vs. private individual vs. strategic acquirer).

### Adjusted methods

**Beta estimation — three options:**

```
Option A: Accounting beta
  Regress annual ΔEarnings_firm vs. ΔEarnings_S&P500
  (limited observations; smoothed earnings reduce reliability)
  [printed p.668-669 / PDF p.687-688]

Option B: Fundamental beta
  Beta = f(ROE, FA/TA, D/C, growth, tax rate) from cross-sectional regression
  R² = ~9% — high prediction error; use as sanity check only
  [printed p.670 / PDF p.689]

Option C: Bottom-up beta (preferred)
  β_private = β_unlevered_sector × [1 + (1−t) × (D/E)_target]
  Use industry-average or target D/E if market D/E not available
  [printed p.671-673 / PDF p.690-692]
```

**Total beta (for undiversified owner selling to another individual):**
```
Total beta = Market beta / ρ_jm

where ρ_jm = correlation between firm's returns and market index
           (use correlation of comparable public firms)

Cost of equity_total = rf + Total beta × ERP
```
Total beta > market beta; use it only when buyer is undiversified.  
For IPO (buyer = diversified stock market investor): use market beta. [printed p.672-673 / PDF p.691-692]

**Synthetic credit rating for cost of debt:**
```
Interest coverage ratio = EBIT / Interest expense
→ Lookup Table 24.1 → Rating → Default spread → kd = rf + spread
After-tax cost of debt = kd × (1 − tax rate)
```
Use small-company rating table (private firms are smaller and riskier than average public firms). [printed p.675-676 / PDF p.694-695]

### Illiquidity discount

Private equity is illiquid — no ready market to exit. Adjust value downward:

```
Illiquidity discount ≈ estimated from:
  (a) Restricted stock studies: average discount 20-30% vs. freely traded shares
  (b) IPO-to-private transactions: implied discount to public market value
  (c) Option-based approach: cost of inability to sell = value of a put at market price
```

Discount is larger for:
- Firms where most of value is in growth assets (harder to liquidate)
- Firms with concentrated customer/supplier relationships
- Higher revenue concentration (key person / single client risk)

[printed p.686-720 / PDF p.705-739 — see Chapter 24 sections on Illiquidity Discount]

### Control premium

When valuing for acquisition or to an owner who can change management:

```
Value with control = Value with optimal management
Premium = Value_optimal − Value_status_quo

Warranted only if:
  (a) Buyer can and will actually change management
  (b) Corporate governance mechanisms are weak (incumbent hard to remove)
```

For minority stake purchase in a well-run firm: no control premium. [printed p.926-928 / PDF p.945-947]

### Cash flow adjustments specific to private firms

1. **Owner salary:** If owner is not paying themselves market rate, add imputed market-rate salary as an expense before computing operating income. Otherwise income is overstated. [printed p.678 / PDF p.697]
2. **Personal expenses:** Strip out personal expenses intermixed with business expenses. [printed p.678-679 / PDF p.697-698]
3. **Tax rate:** Use buyer's marginal tax rate, not a single corporate rate — this can vary from corporate rate to highest individual rate. Value differs by buyer. [printed p.678 / PDF p.697]

### Guardrails

- Never use book D/E ratio for levering betas if you can avoid it — use industry-average market D/E or iterate. [printed p.671 / PDF p.690]
- If valuing for IPO: NO total beta adjustment; NO illiquidity discount. Buyers are diversified public investors. [printed p.672-673 / PDF p.691-692]
- If valuing for private sale to strategic buyer (publicly traded acquirer): use market beta; control premium may apply; no illiquidity discount (buyer is liquid).

---

## 5. Distressed Firms — Equity as a Call Option

**Chapter 30 [printed p.826-840 / PDF p.845-859]**

### Core problem

For highly leveraged firms with negative earnings:
- DCF values equity as a going concern → may yield negative equity or near-zero value.
- But equity investors have **limited liability** — they cannot lose more than invested.
- Equity therefore has option value even when firm value < debt face value, because of time premium and volatility.

**Trigger:** Use equity-as-option when: (a) firm has substantial debt, (b) earnings are negative, (c) going-concern DCF yields zero or negative equity value, and (d) firm is publicly traded (limited liability confirmed). [printed p.826-827 / PDF p.845-846]

### Equity as a European call option on firm assets

```
Equity value = C = S × N(d1) − K × e^(−rt) × N(d2)

where:
  S = Current value of firm assets (estimate via DCF of operating assets
      or market value of debt + equity)
  K = Face value of total debt outstanding (use duration-weighted sum of
      all debt + cumulated interest if appropriate) [printed p.833-834 / PDF p.852-853]
  t = Duration of debt (value-weighted average duration of all issues)
      [printed p.832-833 / PDF p.851-852]
  σ² = Variance in firm value (estimate from equity + debt volatilities
       and their weights and correlation) [printed p.832 / PDF p.851]
  r  = Risk-free rate matched to option life

  d1 = [ln(S/K) + (r + σ²/2)t] / (σ√t)
  d2 = d1 − σ√t

Risk-neutral probability of default = 1 − N(d2)  [printed p.830 / PDF p.849]
```

[Full illustration: Eurotunnel 1997 — printed p.834-835 / PDF p.853-854]

### Distress-adjusted value (when going concern + default risk)

When DCF is valid but default risk is non-trivial, use the distress-adjusted formula from Ch.12:

```
Adjusted value = DCF value × (1 − P[distress]) + Distress-sale value × P[distress]
```

[printed p.319 / PDF p.338]

- Distress-sale value is typically 30-70% of going-concern DCF value (depends on asset tangibility and liquidity)
- P[distress] from bond rating (Altman tables) or probit on financial ratios

### Key implications of the option framework

| Effect | Interpretation |
|---|---|
| Firm value below debt face value | Equity ≠ zero (time premium keeps it positive) [printed p.828 / PDF p.847] |
| Higher asset volatility | Increases equity value (risk is the equity holder's ally in distress) [printed p.828-829 / PDF p.847-848] |
| Longer debt duration | Increases equity value (option has more time to expire in-the-money) [printed p.832 / PDF p.851] |
| Risky project with negative NPV but higher variance | Can increase equity value at expense of bondholders [printed p.836-837 / PDF p.855-856] |
| Conglomerate merger (diversification) | Reduces variance → transfers wealth from equity to debt [printed p.837-839 / PDF p.856-858] |

### Practical inputs — handling complex debt structures

```
Multiple debt issues:
  K = Sum of face value of all debt + cumulated interest payments
  t = Face-value-weighted average duration of all issues
  [printed p.833-834 / PDF p.852-853]

σ²_firm = w_e² × σ²_e + w_d² × σ²_d + 2 w_e w_d ρ_ed σ_e σ_d
  (use sector-average firm variance if firm is in severe distress and own
   stock/bond volatilities are distorted) [printed p.832 / PDF p.851]
```

### Guardrails

- Equity-as-option applies ONLY with limited liability (publicly traded, or incorporated private firm with no personal guarantees). [printed p.827 / PDF p.846]
- For well-funded going-concern firms with moderate debt: DCF going-concern value > equity-as-option value → use DCF. Option value is the relevant ceiling only when DCF yields near-zero or negative equity. [printed p.838 / PDF p.857]
- Do NOT double count: if option-to-expand is already in DCF growth rate, do not add it again as a real option premium. [printed p.937 / PDF p.956 — Ch.34 caution]
- Use sector-average variance for σ²_firm when the distressed firm's own volatilities are unreliable. [printed p.832 / PDF p.851]
