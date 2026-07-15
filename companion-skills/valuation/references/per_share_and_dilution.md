# Per-Share Value & Dilution — Build Guide

**Source:** Aswath Damodaran, *Investment Valuation*, 3rd ed. (Wiley).  
Chapter 16: Estimating Equity Value per Share [printed p.423–451 / PDF p.442–470].  
Page anchors: `[printed p.X / PDF p.Y]` — offset PDF = printed + 19.  
Cross-link: `references/damodaran_dilution_principles.md` (verbatim quotes).  
Loaded by: `dcf.py`, `per_share_bridge.py`

---

## 1. Firm Value → Equity Value → Per Share: The Bridge

**General structure [printed p.440-441 / PDF p.459-460]:**

```
Firm Value (operating assets)
+ Cash & near-cash investments (at fair value, see §2)
+ Non-operating assets (cross-holdings, real assets; see §3)
─────────────────────────────────────────
= Total Firm Value

− Debt (at market value)
− Preferred stock (at market value = pref. dividend / kps)
− Other nonequity claims (unfunded pensions, expected lawsuit liabilities discounted)
─────────────────────────────────────────
= Equity Value

− Value of outstanding options/warrants (option-pricing model; see §4)
─────────────────────────────────────────
= Equity value attributable to common shareholders

÷ Primary (basic) shares outstanding
─────────────────────────────────────────
= Intrinsic Value per Share
```

Do **not** subtract future debt issues or future equity raises — those do not exist today [printed p.441 / PDF p.460].

---

## 2. Cash and Non-Operating Assets

### 2.1 Cash and near-cash investments

- Cash and marketable securities should be **valued separately** from operating assets and **added at face value** (or at market value for risky securities) [printed p.424-426 / PDF p.443-445].
- If cash earns a fair risk-adjusted return, it is worth its face value. Only discount cash when: (1) it earns a below-market return, or (2) management has a demonstrated history of destroying value with excess cash through poor acquisitions [printed p.426-427 / PDF p.445-446].
- Trapped foreign cash (parked abroad to defer repatriation tax): value it net of the estimated differential tax cost on repatriation [printed p.427 / PDF p.446].
- **Illustration:** A firm with $1B in operating assets (β=1) and $200M in cash earns $129M total net income. If you mistakenly discount all $129M at the risky cost of equity (11%), you value cash at ~$90M instead of $200M — a $110M error [printed p.425 / PDF p.444]. Separate treatment prevents this.

### 2.2 Investments in risky securities

Three valuation approaches for marketable securities held in other firms [printed p.430-431 / PDF p.449-450]:
1. **Current market value** — simplest; use when holdings are numerous and liquid
2. **Market value net of capital gains taxes** — use when planning to sell, or on liquidation basis
3. **DCF of the subsidiary** — best for large, concentrated, identifiable holdings

### 2.3 Cross-holdings in subsidiaries

Accounting rules create two regimes based on ownership stake [printed p.432-438 / PDF p.451-457]:

**Majority stake (> 50%, consolidated):**
- Parent consolidates subsidiary's revenues and operating income in its financials
- Minority interest (the share you do NOT own) appears as a liability
- In DCF: value the consolidated operating assets → subtract **minority interest at market value** (not book), not at the accounting book-value line
- Correct minority interest = (1 − ownership%) × estimated equity value of subsidiary

**Minority stake (< 50%, equity method or cost basis):**
- Only a proportional share of earnings (or dividends) flows through to the parent
- In DCF: do NOT include subsidiary cash flows in your FCFF/FCFE model; instead ADD the equity value of the stake as a separate non-operating asset
- Value = ownership% × equity value of subsidiary (estimated independently)

**Practical formula for equity value:**
```
Equity value = Value of parent's own operating assets
             + Σ (ownership_i% × equity_value_i)     [minority stakes]
             − Minority interest in consolidated subs  [at market value]
```

[printed p.436-437 / PDF p.455-456]

---

## 3. Subtraction of Nonequity Claims

When subtracting debt, use the **same definition of debt** you used in the WACC calculation [printed p.440 / PDF p.459]. If you capitalized operating leases as debt for the cost-of-capital computation, subtract the operating lease debt from firm value here. Consistency is mandatory.

Other claims to net [printed p.441 / PDF p.460]:
- **Expected litigation liabilities:** probability × expected damages, present-valued
- **Unfunded pension/healthcare:** present value of expected future cash funding requirements
- **Deferred tax liability:** discount it to present based on when it comes due (typically when growth normalizes)

---

## 4. Employee Stock Options (ESOs) — Three Approaches

When options/warrants exist, the equity must be allocated between common shareholders and option holders. There are four approaches; only one is correct [printed p.443-447 / PDF p.462-466].

### 4.1 Fully-diluted share count (WRONG — understates per-share value)

```
Value per share = Equity Value / (Basic shares + All options outstanding)
```

**Why it fails:**
1. Ignores the exercise proceeds the firm receives when options are exercised (a cash inflow)
2. Includes out-of-the-money, unvested options that may never be exercised
3. Treats out-of-the-money options as having full dilutive weight — wrong
4. **Most importantly: drops the time premium.** An option worth $5 today is counted as one share worth zero exercise proceeds. This systematically understates value per share [printed p.443 / PDF p.462].

### 4.2 Treasury stock approach (CLOSER — but still wrong direction)

```
Value per share = (Equity Value + Exercise proceeds from in-the-money options)
                 / (Basic shares + In-the-money options)
```

Where exercise proceeds = number of in-the-money options × weighted average exercise price.

Better than fully-diluted (it incorporates cash inflows), but still ignores the time premium on the options. Generally *overestimates* per-share value because options are undervalued [printed p.444-445 / PDF p.463-464].

Cisco example [printed p.444-445 / PDF p.463-464]:
- Equity value = $113,331M; 5,528M basic shares; 732M total options (208M in-the-money)
- Exercise proceeds on 208M in-the-money options: $3,135M (avg. exercise price $15.07)
- Treasury stock value = ($113,331 + $3,135) / (5,528 + 208) = **$20.30/share**

### 4.3 Option-value method — CORRECT APPROACH

```
Value of equity per share = (Equity Value − Value of options outstanding)
                            / Primary (basic) shares outstanding
```

**Procedure** [printed p.445-447 / PDF p.464-466]:
1. Estimate aggregate equity value from DCF (before any option deduction)
2. Value each tranche of options using a **dilution-adjusted Black-Scholes model** (or binomial); inputs: current stock price or estimated intrinsic value per share, exercise price, time to expiry, stock volatility, rf, dividend yield
3. Sum the option values across all tranches → total option liability
4. Subtract option liability from equity value
5. Divide by **basic (primary) shares outstanding** — NOT the diluted count

**Why this is correct:** Options are a contingent claim on equity. Their value captures the time premium, the exercise-price discount, and the probability of exercise. Subtracting the present value of that claim and dividing by basic shares gives the true per-share value of the common stock [printed p.445 / PDF p.464].

**Tax adjustment** (optional refinement):
```
After-tax option value = Option value × (1 − marginal tax rate)
```
Because when options are exercised, the firm deducts the spread as a compensation expense [printed p.446 / PDF p.465].

**Iterative circularity:** The stock price is an input to Black-Scholes AND an output. Resolve: (a) use the treasury-stock-approach value per share as the starting stock price, (b) compute option values, (c) compute new per-share value, (d) iterate until convergence [printed p.446 / PDF p.465].

**Cisco verification [printed p.447 / PDF p.466]:**
- 732M options valued at $2.96/option (B-S, σ=40%, maturity=3.94 yrs, K=$21.39)
- Total option value = $2,165M
- Equity to common = $113,331 − $2,165 = $111,166M
- Per share = $111,166 / 5,528M = **$20.10/share**
- Compare: fully-diluted = $18.10, treasury-stock = $20.30, correct = **$20.10**

**Rule of thumb:** When option overhang is small (<5% of equity value), the three methods converge. When it is large (tech firms, biotech), the option-value method can differ materially.

### 4.4 Future option grants

Options granted in future periods reduce the free cash flows to existing equity holders (either through cash buybacks or dilution). If current operating expenses already include the option grant expense (post-2007 accounting), and you carry forward current margins, future dilution from normal grant levels is already embedded in your cash flows [printed p.448 / PDF p.467]. No separate adjustment needed unless grant rates are expected to change materially.

---

## 5. Dilution from Future Financing — Core Rule and Exception

> **See `references/damodaran_dilution_principles.md` for verbatim source quotes and extended discussion.**

### 5.1 The core rule: fair-value raises are already in the DCF

For money-losing or capital-consuming firms (clinical-stage biotech, pre-revenue growth companies):

> "In the FCFE model, the negative free cash ﬂows to equity in the earlier years will reduce the estimated value of equity today. Thus the dilution effect is captured in the present value, and no additional consideration is needed of new stock issues in future years and the effect on value per share today." [printed p.371 / PDF p.390]

**Mechanism:** negative early FCFEs represent cash the firm must raise externally. Discounting those negative cash flows already imposes the economic cost of future dilution on the current valuation. Re-charging via a larger denominator (projected post-raise share count) is **double counting** [printed p.658-659 / PDF p.677-678].

### 5.2 Divide by current (primary/basic) share count

> "This value should then be divided by the actual number of shares outstanding to arrive at the equity value per share." [printed p.658 / PDF p.677]

> "Value of equity per share = (Value of equity − Value of options outstanding) / Primary number of shares outstanding" [printed p.447 / PDF p.466]

Do not enlarge the denominator to include projected future shares from anticipated raises. The PV of negative cash flows is the dilution discount; using an inflated denominator double-counts it.

### 5.3 The only legitimate per-share hit: below-value issuance

> "The reason there is dilution is because the additional shares are issued only to the option holders at a price below the current price. In contrast, the dilution that occurs in a rights issue where every stockholder gets the right to buy additional shares at a lower price is value neutral." [printed p.443 (footnote 9) / PDF p.462]

A fair-value equity raise (shares issued at intrinsic value) is **value neutral** — cash in equals value of shares out. Per-share value is unaffected.

Value transfers occur **only** when shares are issued below intrinsic value (forced raises at distress discounts, or issuance to a subset of holders at below-market prices).

### 5.4 Bear case / distress exception

If there is a material probability the firm is forced to raise equity below intrinsic value (distressed scenario):

```
Intrinsic value = DCF_value × (1 − P_distress) + Distress_sale_value × P_distress
```

[See `damodaran_dilution_principles.md` §Caveats, citing printed p.319 / PDF p.338]

Model the forced discount as reduced cash proceeds in the bear-case cash flows, not as a structural haircut to the base-case share count. Weight by probability and put in the **bear scenario**, not the base case.

### 5.5 Application to clinical-stage / rNPV models

1. rNPV already subtracts PV(remaining development costs). That is the cash the firm must raise.
2. A future raise at fair value is per-share neutral. Do **not** deduct a separate "dilution leak" and do **not** inflate the share count.
3. Keep real cash costs that are outside the per-asset rNPV (corporate G&A, pre-launch overhead) — those are genuine outflows, not financing artifacts.
4. Divide intrinsic equity value by the **current** share count. Treat options as a valued liability using Black-Scholes if the option overhang is material.

---

## 6. Worked Per-Share Bridge (4-Line Example)

**Firm:** Mid-stage biotech; one asset in Phase 3.

| Line | Value ($M) |
|------|-----------|
| rNPV of lead asset (prob-adjusted, net of R&D) | 850 |
| + Cash on balance sheet (at face value) | 120 |
| − Debt (at market value) | 80 |
| − ESO value (30M options, B-S $1.50/option) | 45 |
| **= Equity value to common shareholders** | **845** |
| ÷ Basic shares outstanding | 200M |
| **= Intrinsic value per share** | **$4.23** |

**What NOT to do:**
- Do not use 230M diluted shares as denominator (double-counts dilution already in negative rNPV cash flows)
- Do not subtract a separate "future raise haircut" for the upcoming Series B (value-neutral at fair value)
- Do not add the cash the company will need to raise as an additional negative (it is already netted inside the rNPV)

---

## 7. Voting Rights Adjustment (if share classes differ)

When a firm has voting and non-voting shares [printed p.449-450 / PDF p.468-469]:

```
Value per non-voting share = Status quo equity value / (voting + non-voting shares)

Value per voting share = Value per non-voting share
                       + [P(mgmt change) × (Optimal value − Status quo value)] / # voting shares
```

The voting premium is larger when: (a) the firm is badly managed (large Optimal − Status quo spread), and (b) management change is probable (high π).

---

## 8. Quick-Reference Formulas

```python
# Per-share bridge
equity_to_common = firm_value + cash + cross_holdings - debt - preferred - option_value
value_per_share  = equity_to_common / basic_shares_outstanding

# Option value (Black-Scholes, dilution-adjusted)
# Use: S=intrinsic_value_per_share, K=exercise_price, T=maturity, σ=stock_vol, rf=risk_free
option_value_per_option = black_scholes_dilution_adjusted(S, K, T, sigma, rf, dividend_yield)
total_option_value = option_value_per_option * options_outstanding

# Bottom-up beta for cost of equity used in rNPV discount rate
beta_unlevered = beta_comp / (1 + (1 - tax) * de_comp)
beta_levered   = beta_unlevered * (1 + (1 - tax_firm) * de_firm)
ke             = rf + beta_levered * ERP
```

---

*Page anchors verified against `damodaran_investment_valuation_fulltext.txt` `===== PAGE N =====` markers.*  
*Cross-link: `references/cost_of_capital.md` for ke, WACC construction.*  
*Cross-link: `references/damodaran_dilution_principles.md` for verbatim quotes on fair-value raise / double-counting.*
