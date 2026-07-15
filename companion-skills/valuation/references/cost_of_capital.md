# Cost of Capital — Build Guide

**Source:** Aswath Damodaran, *Investment Valuation*, 3rd ed. (Wiley).  
Chapters 4, 7, 8. Page anchors: `[printed p.X / PDF p.Y]` — offset PDF = printed + 19.  
Loaded by: `cost_of_capital.py`, `dcf.py`

---

## 1. CAPM — The Risk/Return Framework

The Capital Asset Pricing Model is the standard workhorse for estimating the cost of equity. It assumes that the marginal investor is well-diversified, so only *market* (non-diversifiable) risk is priced; firm-specific risk is irrelevant [printed p.65-66 / PDF p.84-85].

**CAPM formula:**

```
ke = rf + β · ERP
```

Where:
- `ke` = cost of equity (expected return on equity investment)
- `rf` = risk-free rate
- `β` = beta (firm's sensitivity to market risk)
- `ERP` = equity risk premium (E(Rm) − rf)

This is the special single-factor case of the more general multifactor model:

```
E(R) = rf + β₁[E(R₁) − rf] + β₂[E(R₂) − rf] + ... + βₖ[E(Rₖ) − rf]
```

Table 4.1 [printed p.77 / PDF p.96] summarizes: CAPM is the simplest and still the default model; APT/multifactor models add factors but introduce estimation instability; proxy models (Fama-French) explain past returns well but risk data mining.

---

## 2. Risk-Free Rate

**Definition:** An asset is risk-free if (a) it has no default risk and (b) it has no reinvestment risk — actual return always equals expected return [printed p.154-155 / PDF p.173-174].

### 2.1 Which instrument

- Use a **long-term government bond** for discounted cash flow valuation (where cash flows extend far into the future). Duration of the default-free security should match the duration of the cash flows being analyzed [printed p.155 / PDF p.174].
- Short-term T-bill rates are NOT risk-free for long-horizon valuation because reinvestment risk is unresolved.
- For a firm with a very long life (perpetuity), duration of cash flows exceeds 10 years — use the 10-year+ Treasury bond [printed p.155 / PDF p.174].

### 2.2 Currency consistency rule (critical)

> "The risk-free rate used to come up with expected returns should be measured consistently with how the cash flows are measured." [printed p.156 / PDF p.175]

- **Nominal USD cash flows → USD Treasury bond rate**
- **Nominal EUR cash flows → German/French sovereign bond rate** (or other EUR sovereign)
- **Nominal BRL cash flows → BRL government bond rate minus BRL default spread**

The ﬁrm's country of domicile is irrelevant; the cash-flow currency determines the risk-free rate.

### 2.3 Real vs. nominal

For valuations in real terms (high-inflation environments):
```
Real risk-free rate ≈ Nominal rf − Expected inflation
```
Or use the rate on inflation-indexed Treasuries (TIPS) as a direct real risk-free rate [printed p.156 / PDF p.175].

### 2.4 Emerging-market / no-default-free-entity adjustment

When the local government is not default-free, strip out the sovereign default spread:
```
rf_local = Government bond yield − Sovereign default spread
```
Example (India, 2011): 8.00% government bond − 2.40% default spread = **5.60% risk-free rate in INR** [printed p.157 / PDF p.176].

---

## 3. Equity Risk Premium (ERP)

### 3.1 Historical ERP (geometric, long window, stocks minus T-bonds)

- Use the **geometric mean** (not arithmetic) for long-term forecasting; arithmetic overstates the compounding effect [printed p.161 / PDF p.180].
- Use a **long time window** (50–80+ years) to reduce standard error; US: ~4.31–4.4% geometric mean over 1928–2010 from Dimson-Marsh-Staunton data [printed p.165-166 / PDF p.184-185].
- Compare **stocks minus T-bonds** (not T-bills) if you use a long-term bond as rf, for consistency [printed p.155 / PDF p.174].
- Survivorship bias: US historical premium likely overstates the forward-looking premium because the US is a survivor market [printed p.165 / PDF p.184].

**Damodaran's practice:** geometric average stocks vs. Treasury bonds, 1928–2010 = **4.31%** as the base mature-market ERP [printed p.166 / PDF p.185].

### 3.2 Implied (Forward) ERP — PREFERRED

Back-solve the discount rate `r` from the current index level using projected cash flows, then subtract rf. This is market-driven and current; does not require long historical data [printed p.172-174 / PDF p.191-193].

**Simple Gordon-growth version:**
```
Index = (CF × (1 + g)) / (r − g)
Solve for r:  r = CF(1+g)/Index + g
ERP = r − rf
```

**Two-stage version (Damodaran's preferred, as of Jan 2011 example):**

```
Index = Σ[t=1 to 5] CF_t / (1+r)^t  +  [CF₅(1+g_stable) / (r − g_stable)] / (1+r)^5
```

Where `g_stable ≈ rf` (Treasury bond rate, because stable-growth firms grow at the economy rate).

Solve iteratively for `r`; then:
```
ERP = r − rf
```

Example [printed p.173-174 / PDF p.192-193]: S&P 500 at 1,257.64 on Jan 1, 2011; cash flows (dividends + buybacks) of 53.96 growing at 6.95% for 5 years then 3.29% stable; rf = 3.29%. Solved r = 8.49%, **implied ERP = 5.20%**.

**Key advantages:** forward-looking, currency/market agnostic, can be run on any index.

### 3.3 Country Risk Premium add-on

```
ERP_country = ERP_mature_market + Country_risk_premium
```

**Preferred method — default spread scaled by relative equity volatility** [printed p.170 / PDF p.189]:
```
CRP = Sovereign_default_spread × (σ_equity / σ_sovereign_bond)
```

Example (Brazil, 2011): 2.00% default spread × (17.65% / 7.32%) = **4.82% CRP**; total ERP = 4.31% + 4.82% = **9.13%** [printed p.170 / PDF p.189].

Company-level exposure to country risk can be scaled by λ (revenue mix domestic vs. global) rather than applying CRP uniformly [printed p.171-172 / PDF p.190-191].

---

## 4. Beta

### 4.1 Regression beta and its flaws

Standard method: regress stock returns against market-index returns over 2–5 years (monthly data):
```
Return_stock = α + β · Return_market + ε
```

**Key problems** [printed p.183-184 / PDF p.202-203]:
- High standard error (typical SE ≈ 0.20–0.50); true beta is a wide range around the estimate
- Reflects historical average leverage and business mix over the regression window — not current reality
- Cannot be estimated for private firms, divisions, or recent IPOs
- R² gives proportion of variance explained by market risk; (1 − R²) = firm-specific risk

### 4.2 Bottom-Up Beta — PREFERRED METHOD

Break the beta into its business-risk and financial-leverage components using comparable firms. Does not require a price history on the firm being valued [printed p.197-199 / PDF p.216-218].

**5-Step Process:**

**Step 1.** Identify the business(es) the firm operates in.

**Step 2.** Find publicly traded comparable firms in each business; collect their regression betas.

**Step 3.** Unlever the average (or median) comparable-firm beta to remove financial leverage:

```
β_unlevered = β_comp / [1 + (1 − t) · (D/E)_comp]
```

Where `t` = marginal tax rate; `D/E` = market-value debt-to-equity ratio of the comparable group.

**Step 4.** If the firm operates in multiple businesses, compute a weighted average unlevered beta:

```
β_unlevered_firm = Σ (β_unlevered_j × value_weight_j)
```

**Step 5.** Relever using the firm's own target/current capital structure:

```
β_levered_firm = β_unlevered_firm · [1 + (1 − t_firm) · (D/E)_firm]
```

**Why bottom-up is better:**
- Averaging across many comparable-firm betas reduces standard error by √n
- Can reflect *current* business mix and leverage, not historical average
- Works for private firms, pre-revenue firms, and recent IPOs [printed p.197-198 / PDF p.216-217]

**Worked illustration — Vans Shoes [printed p.201 / PDF p.220]:**
- Average beta of 21 shoe companies: 0.79
- Average D/E: 75.04%; average tax rate: 25.95%
- β_unlevered = 0.79 / [1 + (1 − 0.2595)(0.7504)] = **0.5081**
- Vans D/E = 9.41%; Vans tax rate = 34.06%
- β_levered = 0.5081 × [1 + (1 − 0.3406)(0.0941)] = **0.5397**

**Cash adjustment:** If comparable firms hold significant cash (beta ≈ 0), strip cash from the unlevered beta before weighting:
```
β_operating_business = β_unlevered_sector / (1 − cash_pct_of_value)
```
[printed p.200 / PDF p.219]

**Use bottom-up for:** private firms, pre-revenue biotech/tech, recent IPOs, conglomerates, firms that recently changed capital structure.

---

## 5. Cost of Debt

### 5.1 Pre-tax cost of debt

For **rated firms**: use the bond rating and the current default spread for that rating:
```
kd_pretax = rf + Default_spread(rating)
```

For **unrated firms**: estimate a **synthetic rating** from the interest coverage ratio [printed p.212 / PDF p.231].

**Interest Coverage → Synthetic Rating (small-cap, market cap < $5B):**

| EBIT / Interest Expense | Rating | Default Spread |
|------------------------|--------|---------------|
| > 12.5x               | AAA    | 0.50%         |
| 9.5–12.5x             | AA     | 0.65%         |
| 7.5–9.5x              | A+     | 0.85%         |
| 6.0–7.5x              | A      | 1.00%         |
| 4.5–6.0x              | A−     | 1.10%         |
| 3.5–4.5x              | BBB    | 1.60%         |
| 3.0–3.5x              | BB     | 3.35%         |
| 2.5–3.0x              | B+     | 3.75%         |
| 2.0–2.5x              | B      | 5.00%         |
| 1.5–2.0x              | B−     | 5.25%         |
| 1.25–1.5x             | CCC    | 8.00%         |
| 0.8–1.25x             | CC     | 10.00%        |
| 0.5–0.8x              | C      | 12.00%        |
| < 0.5x                | D      | 15.00%        |

For large-cap firms (market cap > $5B), coverage thresholds shift lower for the same rating [printed p.212-213 / PDF p.231-232].

**Pre-tax kd = rf + spread (from rating)**

### 5.2 After-tax cost of debt

```
kd_aftertax = kd_pretax × (1 − t_marginal)
```

Use the **marginal** tax rate, not the effective rate, because interest saves taxes at the margin [printed p.213 / PDF p.232].

**Note:** If the firm has operating losses, there is no immediate tax benefit; use pre-tax kd for those years [printed p.214 / PDF p.233].

**Boeing illustration [printed p.214 / PDF p.233]:**
- AA-rated; default spread = 1.00%; rf = 5.00%
- Pre-tax kd = 5% + 1% = **6.00%**
- Marginal tax rate = 35%
- After-tax kd = 6.00% × (1 − 0.35) = **3.90%**

### 5.3 Emerging-market firms

Add the country default spread on top:
```
kd = rf + Country_default_spread + Company_synthetic_spread
```
[printed p.214 / PDF p.233]

---

## 6. WACC — Formula and Inputs

### 6.1 Full formula

```
WACC = ke · [E/(D + E + PS)]
     + kd(1−t) · [D/(D + E + PS)]
     + kps · [PS/(D + E + PS)]
```

Where `E`, `D`, `PS` = **market values** of equity, debt, preferred stock [printed p.220 / PDF p.239].

- `ke` = cost of equity (from CAPM)
- `kd(1−t)` = after-tax cost of debt
- `kps` = cost of preferred stock = preferred dividend / preferred stock price

### 6.2 Market-value weights — mandatory

> "The weights on each of these components should reﬂect their market value proportions, since these proportions best measure how the existing ﬁrm is being ﬁnanced." [printed p.220 / PDF p.239]

**Never use book-value weights.** Book values can give wildly different ratios: in Boeing's example, market debt ratio = 12.45% vs. book debt ratio = 36.15% [printed p.219 / PDF p.238]. Using book weights would produce a WACC 2–3 percentage points lower and overvalue the firm.

### 6.3 Market value of debt

Most firms have non-traded bank debt. Treat all debt as a single coupon bond:
- Coupon = total annual interest expense
- Face value = book value of debt
- Maturity = face-value-weighted average maturity
- Discount at the current pre-tax cost of debt to find market value [printed p.219 / PDF p.238]

### 6.4 Iterative WACC

When the firm's leverage changes over the forecast horizon (e.g., during a debt paydown), the WACC weights depend on value, and value depends on WACC. Iterate: run the DCF at an initial WACC estimate, recalculate the market-value weights, update WACC, repeat until convergence.

---

## 7. Worked Example — WACC Computation

**Firm:** Industrial manufacturer, single business.

| Input | Value |
|-------|-------|
| rf (10-year US Treasury) | 4.0% |
| Comparable-firm levered β (average) | 1.20 |
| Comparable-firm D/E (market) | 40% |
| Comparable-firm tax rate | 30% |
| Firm D/E (market) | 25% |
| Firm tax rate | 28% |
| ERP (implied, US) | 5.2% |
| Firm senior bond coverage ratio | 5.8x → A rating |
| Default spread (A) | 1.00% |

**Step 1 — Unlever comparable beta:**
```
β_unlevered = 1.20 / [1 + (1 − 0.30)(0.40)]
            = 1.20 / [1 + 0.28]
            = 1.20 / 1.28
            = 0.9375
```

**Step 2 — Relever at firm's D/E:**
```
β_levered = 0.9375 × [1 + (1 − 0.28)(0.25)]
          = 0.9375 × [1 + 0.18]
          = 0.9375 × 1.18
          = 1.106
```

**Step 3 — Cost of equity (CAPM):**
```
ke = 4.0% + 1.106 × 5.2% = 4.0% + 5.75% = 9.75%
```

**Step 4 — Cost of debt:**
```
kd_pretax = 4.0% + 1.00% = 5.00%
kd_aftertax = 5.00% × (1 − 0.28) = 3.60%
```

**Step 5 — Market-value weights (D/E = 25% → D = 20%, E = 80%):**
```
Weight_E = 1 / (1 + 0.25) = 0.80
Weight_D = 0.25 / 1.25   = 0.20
```

**Step 6 — WACC:**
```
WACC = 9.75% × 0.80 + 3.60% × 0.20
     = 7.80% + 0.72%
     = 8.52%
```

---

## 8. Common Errors Checklist

| Error | Consequence |
|-------|-------------|
| Using T-bill rate as rf | Understates risk-free rate; inflates ERP or distorts ke |
| Using arithmetic mean for historical ERP | Overstates ERP by 1–2%; overvalues firm |
| rf currency mismatch (USD rf on EUR cash flows) | Systematic discounting error |
| Using regression beta for a private/young firm | Meaningless or unavailable |
| Using book-value WACC weights | Overstates debt weight; underestimates WACC |
| Using statutory tax rate when firm has losses | Overestimates tax shield; understates kd_aftertax |
| Applying country risk premium to rf AND also double-counting in β | Double-charges country risk [printed p.169 / PDF p.188] |

---

*Page anchors verified against `damodaran_investment_valuation_fulltext.txt` `===== PAGE N =====` markers. Cross-link: `references/damodaran_dilution_principles.md` for share-count treatment.*
