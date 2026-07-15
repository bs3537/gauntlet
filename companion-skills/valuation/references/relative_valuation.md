# Relative Valuation Reference
## Source: Damodaran, *Investment Valuation* (3rd ed.)
## Chapters: 17 (p.453–467), 18 (p.468–510), 19 (p.511–530), 20 (p.542–561)
## Page anchors: [printed p.X / PDF p.Y] where PDF = printed + 19

---

## 1. Four-Step Framework for Any Multiple

**Source:** Ch.17 [printed p.456 / PDF p.475]

Every multiple must pass four tests before being applied:

### Step 1: Define Consistently
The multiple must be internally consistent — numerator and denominator must refer to the same claimants. Examples of consistency failures:
- Price-to-EBITDA is **inconsistent**: price = equity value; EBITDA accrues to firm (debt + equity). Use EV/EBITDA instead.
- PE ratio: numerator is equity price, denominator must be equity earnings (EPS), not operating income.
- Use trailing, current, or forward EPS uniformly across all comparables; mixing them invalidates comparisons.

### Step 2: Describe the Cross-Sectional Distribution
Multiples are **positively skewed** — unconstrained above zero, floored at zero. Therefore:
- Mean >> Median; median is the better measure of the typical firm.
- Know the 25th, 50th, 75th percentile values in the sector and the market.
- Outliers (PE = 5,000 when EPS is near zero) must be capped or removed before averaging.

### Step 3: Analyze Fundamental Determinants
Every multiple maps directly to DCF drivers. Extract the determinant formula by linking the multiple to the appropriate equity or firm valuation model. The three universal drivers are **growth (g)**, **risk (ke or WACC)**, and **cash-return potential (payout / RR / net margin)**. Changes in fundamentals always have sign-consistent effects on the multiple.

### Step 4: Apply to Comparable Firms — Control for Differences
Defining "comparable" subjectively (same industry) is insufficient. Two methods:
- **Narrow comparables + subjective adjustment:** pick similar firms, adjust for growth/risk differences by judgment. Error-prone.
- **Regression on fundamentals (preferred):** regress the multiple against the key determinants across the sector or the full market, then use fitted values to identify under/overvaluation. Controls for all observable drivers simultaneously.

[printed p.467 / PDF p.486]: "There are four steps in using multiples wisely. First, you have to define the multiple consistently and measure it uniformly across the firms being compared. Second, you need to have a sense of how the multiple varies across firms in the market. Third, you need to identify the fundamental variables that determine each multiple. Finally, you need to find truly comparable firms and adjust for differences."

---

## 2. Price/Earnings (P/E) Ratio

**Source:** Ch.18 [printed p.468–486 / PDF p.487–505]

### Definition
`PE = Market price per share / EPS`
Variants: current PE (latest reported EPS), trailing PE (last 4 quarters), forward PE (next-12-month consensus EPS). Forward PE is generally lowest because earnings are expected to grow.

### Determinants — DDM Derivation
Starting from the stable-growth dividend discount model:

```
P0 = DPS1 / (ke − gn)
   = EPS1 × Payout ratio / (ke − gn)
```

Forward PE (P/EPS1):
```
P/EPS1 = Payout ratio / (ke − gn)
```

Substituting `Payout = 1 − g/ROE`:
```
Forward PE = (1 − gn/ROEn) / (ke − gn)
```

For the **two-stage model** (high-growth period n years, then stable growth):
```
PE = [Σ Payout_hg × (1+g)^t / (1+ke,hg)^t for t=1..n]
   + [Payout_n × (1+g)^n × (1+gn) / ((ke,st − gn)(1+ke,hg)^n)]
   (divided by EPS0)
```

PE is therefore:
- **Increasing** in payout ratio (for given g; equivalently, increasing in ROE for given g)
- **Increasing** in expected growth rate g (as long as ROE > ke)
- **Decreasing** in risk (higher ke → lower PE)

### Micro-Example: Implied P/E from Fundamentals
[printed p.472–473 / PDF p.491–492]

Firm: g_hg = 25%, payout_hg = 20%, g_stable = 8%, payout_stable = 50%, beta = 1.0, rf = 6%, ERP = 5.5% → ke = 11.5%

ROE_hg = 25% / (1 − 20%) = 31.25%; ROE_stable = 8% / (1 − 50%) = 16%

Plugging into two-stage PE formula → **PE = 28.75×**

If beta rises to 1.5, ke = 14.25% → **PE drops to 14.87×**

### Trailing vs Forward PE
- Trailing PE uses last 4 quarters of reported EPS — vulnerable to cyclical distortions.
- Forward PE uses consensus forward EPS — preferred for valuation but subject to analyst forecast errors.
- Normalize EPS over a cycle for cyclical firms before computing PE for comparables.

### Relative and Sector PE
Market PE is driven by macro: as T-bond rates rise, PE falls; as ERP rises, PE falls. Regression of S&P 500 EP ratio on T-bond rate: EP = 0.026 + 0.69 × T-bond rate (R² = 48%). [printed p.478 / PDF p.497]

Cross-country PE comparisons must control for interest rate differentials, real growth, and risk premium before inferring under/overvaluation.

---

## 3. PEG Ratio

**Source:** Ch.18 [printed p.487–491 / PDF p.506–510]

### Definition
```
PEG = PE ratio / Expected EPS growth rate (in %)
```
A PEG of 1 is conventionally considered "fair value." PEG < 1 → potentially undervalued; PEG > 1 → potentially overvalued. **Consistency rule:** use current PE with current-base growth rate, or forward PE with years-2-through-5 growth — never forward PE with full-period growth (double-counts year 1 growth).

### "Fair PEG" from Fundamentals
Dividing the two-stage PE formula by the high-growth rate g:

```
PEG = PE / g  (g expressed as a decimal × 100 when PE uses that convention)
```

The PEG is NOT growth-neutral. It is:
- **Decreasing** in risk (higher beta → lower PEG)
- **Non-monotone** in growth rate — at very high growth, PEG rises (U-shaped)
- Sensitive to payout ratio and ROE structure

[printed p.491 / PDF p.510]: Firm with g=25%, payout=20%, g_stable=8%, payout_stable=50%, beta=1, ke=11.5% → **PEG = 1.15**

### Regression PEG
Rather than using a fixed-PEG threshold of 1, regress PE on g, risk, and payout across comparables to derive a sector-specific PEG slope coefficient. Firms with PE below the regression-fitted value for their growth rate are undervalued.

**Caution:** PEG comparisons are valid only if growth rates are estimated on the same basis (same horizon, same EPS definition) for all firms.

---

## 4. EV/EBITDA Multiple

**Source:** Ch.18 [printed p.500–508 / PDF p.519–527]

### Why EV/EBITDA is Preferred for Capital-Intensive / Levered Firms
- EBITDA is pre-depreciation and pre-interest — unaffected by differences in debt levels or depreciation policies across firms.
- EV (enterprise value = equity market cap + net debt − cash) matches the claim structure: EBITDA accrues to all capital providers.
- Useful for comparing firms across different leverage ratios, depreciation conventions, or tax jurisdictions.
- Widely used in telecom, cable, infrastructure, mining, and any capital-intensive sector.

### Determinants — Five Drivers
Starting from the stable-growth FCFF model:

```
EV = FCFF1 / (WACC − g)
FCFF = EBITDA(1−t) − DA(1−t) − Reinvestment
```

Dividing by EBITDA:

```
EV/EBITDA = [(1−t) − (DA/EBITDA)(1−t) − Reinvestment/EBITDA] / (WACC − g)
```

[printed p.503–504 / PDF p.522–523]

The **five determinants** are:
1. **Tax rate (t):** Higher t → lower EV/EBITDA (taxes reduce after-tax cash flows)
2. **Depreciation/EBITDA ratio:** Higher DA% → lower EV/EBITDA (more of EBITDA is non-cash)
3. **Reinvestment/EBITDA (Net Capex / EBITDA):** Higher reinvestment → lower EV/EBITDA
4. **WACC:** Higher WACC → lower EV/EBITDA (higher discount rate)
5. **Expected growth g:** Higher g → higher EV/EBITDA

### Micro-Example: Castillo Cable
[printed p.504–506 / PDF p.523–525]

Inputs: WACC=10%, t=36%, capex=45%×EBITDA, DA=20%×EBITDA, g=5%

Reinvestment/EBITDA = 0.45 − 0.20 = 0.25

```
EV/EBITDA = [(1−0.36) − (0.20)(1−0.36) − 0.25] / (0.10 − 0.05)
           = [0.64 − 0.128 − 0.25] / 0.05
           = 0.262 / 0.05
           = 5.24×
```

Implied ROC at that reinvestment rate = 10.24% (just above WACC).

### Application Rule
Firms with low ROC and high reinvestment should trade at **low** EV/EBITDA multiples. In sector regressions, control for tax rate and DA/EBITDA when growth and WACC are similar across firms. [printed p.507–508 / PDF p.526–527]

---

## 5. Price-to-Book (P/B) Ratio

**Source:** Ch.19 [printed p.511–530 / PDF p.530–549]

### Definition
```
P/B = Market value of equity / Book value of equity
```

### ROE-Growth Derivation — Stable Growth
From the DDM:
```
P = DPS1 / (ke − gn) = EPS1 × Payout / (ke − gn)
```

Substituting EPS1 = BV0 × ROE and Payout = 1 − g/ROE:

```
P/BV = ROE × Payout / (ke − gn)
```

Simplifying with `Payout = (1 − g/ROE)`:

```
P/BV = (ROE − g) / (ke − g)
```

[printed p.515 / PDF p.534]

**Key insight:** P/B > 1 if and only if ROE > ke. A firm earning below its cost of equity should trade **below book value**. This is the value-creation test.

### For High-Growth Firms (Two-Stage)
```
P/BV = ROE_hg × Payout_hg × [(1+g)^n summed / (ke,hg)] 
     + ROE_st × Payout_st × (1+g)^n × (1+gn) / ((ke,st − gn)(1+ke,hg)^n)
```

Determinants: ROE, payout, ke, g — same drivers as PE, but ROE has direct first-order impact.

### Micro-Example: Jenapharm (Germany, 1991)
[printed p.516 / PDF p.535]

ROE = 9/58 = 15.52%, ke = 7% + 1.25(3.5%) = 11.375%, g = 5%

```
P/BV = (ROE − g) / (ke − g) = (0.1552 − 0.05) / (0.11375 − 0.05) = 1.65×
Equity value = 58 × 1.65 = 95.7M DM
```

### Tobin's Q
Q = Market value of assets / Replacement cost of assets (rather than book value). Q > 1 implies the market values assets above replacement cost — signals excess returns / competitive advantage.

### Application: P/B vs ROE Matrix
[printed p.523–524 / PDF p.542–543]

Plot firms on a P/B × ROE scatter:
- Low P/B + High ROE = potentially undervalued
- High P/B + Low ROE = potentially overvalued

Regression: `P/BV = a + b × ROE` (+ beta + growth as additional controls) gives predicted P/B for each firm; mismatch signals valuation anomaly.

---

## 6. EV/Sales and P/S Ratios

**Source:** Ch.20 [printed p.542–561 / PDF p.561–580]

### Definition
```
P/S (Price-to-Sales) = Market value of equity / Revenue
EV/Sales = (Equity MV + Debt MV − Cash) / Revenue
```

EV/Sales is more robust: it matches the claim structure (EV includes debt) to the revenue base (which services all capital providers). P/S understates value for levered firms.

### Net-Margin as the Primary Determinant
From the stable-growth DDM:
```
P/S = Net margin × Payout × (1+gn) / (ke − gn)
```

For two-stage model:
```
P/S = Net margin × [Payout_hg × Σ(1+g)^t/(1+ke,hg)^t 
    + Payout_n × (1+g)^n(1+gn) / ((ke,st−gn)(1+ke,hg)^n)]
```

[printed p.544–545 / PDF p.563–564]

P/S is therefore:
- **Increasing** in net profit margin (the dominant driver)
- Increasing in payout ratio and growth
- Decreasing in risk (ke)

**A firm with low margin cannot sustain a high P/S multiple.** High-revenue-growth firms that lose money may appear attractively priced on P/S but are value-destroyers if margin is structurally negative.

### Micro-Example: P/S for High-Growth Firm
[printed p.546 / PDF p.565]

Net margin=10%, g_hg=20%, payout_hg=20%, g_stable=8%, payout_stable=50%, ke=11.5%:

```
P/S = 0.10 × {0.20×[(1.20)^5−1]/[(1.115)^5×(0.115−0.20)] 
             + 0.50×(1.20)^5×(1.08)/[(0.115−0.08)×(1.115)^5]}
    = 2.35×
```

### Sector-Specific Multiples
Used when EBITDA or earnings are unavailable or meaningless:
- **Subscribers / users:** telecom (EV per subscriber), streaming (EV per paid sub)
- **Customers:** retail banking (P/deposits)
- **Throughput:** pipelines (EV per barrel)

Danger: sector multiples cannot be cross-compared to market; easy to misuse to justify overpriced sectors. Must anchor to an economic conversion (e.g., what LTV per subscriber justifies $X EV per sub).

---

## 7. Comparables Selection and Regression-on-Fundamentals

**Source:** Ch.17–18 [printed p.456–467, 481–486 / PDF p.475–486, 500–505]

### Comparables Selection — What Makes a True Comparable
"Comparable" is often defined as "same industry," but this fails when firms within an industry differ significantly in:
- Expected growth rate
- Risk (beta, leverage)
- Return on invested capital
- Capital intensity

The correct standard: a comparable firm is one with **similar fundamentals** — same growth, risk, and cash-return profile — not merely the same SIC code.

### Regression-on-Fundamentals (Preferred Method)
Rather than using simple industry averages (which ignore fundamental differences), regress the multiple across a broad sample:

```
PE = a + b1 × Expected_growth + b2 × Payout + b3 × Beta + error
PBV = a + b1 × ROE + b2 × Beta + b3 × Expected_growth + error
```

[printed p.484–486 / PDF p.503–505]

Example regression for telecom PE (Sept 2000):
```
PE = 13.12 + 121.22 × Expected_growth − 13.85 × Emerging_market_dummy
R² = 66%
```

Use predicted PE from regression as the benchmark; actual PE vs. predicted PE flags over/undervaluation.

**Limitations of regression approach:**
- Multicollinearity among growth, risk, and payout
- Relationships shift over time (R² ranged 0.32–0.93 over 1987–1991)
- Linear form may misspecify the true functional relationship

### Reconciling Relative vs. DCF Valuation
[printed p.453, 466–467 / PDF p.472, 485–486]

Relative valuation reflects the mood of the market, measuring value relative to how comparable firms are priced — not intrinsic value. The two will diverge when:
- The entire sector is over- or undervalued relative to DCF fundamentals
- Comparable firms are themselves mispriced by the market

When DCF value > relative value: the firm is undervalued relative to intrinsic value but fairly priced vs. peers (wait for sector re-rating).
When relative value > DCF value: peers are overpriced; sell the firm if fundamentals don't support the price.

**Best practice:** triangulate — run both methods and explain discrepancies in terms of growth, risk, or payout differences. The regression-on-fundamentals approach bridges the two by anchoring relative valuation to DCF drivers.

---

## Summary: Determinant Formula for Each Multiple

| Multiple | Primary Formula | Key Drivers |
|----------|----------------|-------------|
| Forward PE | `(1 − g/ROE) / (ke − g)` | Growth, ROE, ke |
| Trailing PE | Two-stage DDM / EPS0 | Payout, g, ke |
| PEG | PE / g | Risk (↑ risk → ↓ PEG); non-monotone in g |
| EV/EBITDA | `[(1−t) − DA(1−t)/EBITDA − Reinvest/EBITDA] / (WACC−g)` | Tax, DA%, Reinvest%, WACC, g |
| P/B | `(ROE − g) / (ke − g)` | ROE, ke, g |
| P/S | `Net margin × Payout × (1+gn) / (ke − gn)` | Net margin, ke, g |
| EV/Sales | Similar to P/S, firm-level analog | EBIT margin, WACC, reinvestment, g |
