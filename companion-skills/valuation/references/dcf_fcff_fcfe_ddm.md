# Intrinsic Valuation Models: FCFF, FCFE, DDM, and APV

**Source:** Damodaran, *Investment Valuation* (3rd ed.)  
**Chapters:** 10, 13, 14, 15, 16  
**Page-anchor convention:** [printed p.X / PDF p.Y] where PDF = printed + 19

---

## 1. Building Block: From Earnings to Free Cash Flow

### Taxes [printed p.250–252 / PDF p.269–271]
- Use **marginal tax rate** for terminal value computation; effective tax rate is acceptable in early explicit-forecast years if it is expected to converge.
- For NOL-carrying firms, shield future income explicitly — do not apply the full marginal rate until NOLs are exhausted.

### Reinvestment components [printed p.260–269 / PDF p.279–288]
```
Net Capital Expenditures = Capex − Depreciation
   (include capitalized R&D and acquisitions, normalize volatile years)

Δ Noncash Working Capital = Δ(Non-cash current assets − Non-debt current liabilities)
   (exclude cash/T-bills from current assets; exclude short-term debt from current liabilities)
```

---

## 2. FCFF — Free Cash Flow to the Firm

### Formula [printed p.380–381 / PDF p.399–400]
```
FCFF = EBIT(1 − t)  −  Net Capex  −  Δ Noncash WC
     = EBIT(1 − t)  −  (Capex − Dep)  −  Δ Noncash WC
```

Equivalent reconstruction from equity cash flows:
```
FCFF = FCFE  +  Interest(1 − t)  +  Principal repaid  −  New debt issued
                +  Preferred dividends
```

This cash flow is **pre-debt** (unlevered). Tax benefit of interest is captured in WACC's after-tax cost of debt — do not build it into FCFF (would double-count).

### Discount rate: WACC [printed p.239 / PDF p.258, from Ch.8]
```
WACC = ke × [E/(D+E+PS)]  +  kd(1−t) × [D/(D+E+PS)]  +  kps × [PS/(D+E+PS)]
```
Always use **market-value weights**, never book weights.

### Valuation [printed p.383–385 / PDF p.402–404]

**Stable-growth FCFF model:**
```
Value of operating assets = FCFF₁ / (WACC − g_stable)
```

**Multi-stage general model:**
```
Firm Value = Σ [FCFF_t / (1+WACC)^t]  +  [TV_n / (1+WACC)^n]

TV_n = FCFF_{n+1} / (WACC − g_stable)
     = EBIT_{n+1}(1−t) × (1 − RR_stable) / (WACC − g_stable)

where RR_stable = g_stable / ROC_stable   [printed p.313 / PDF p.332]
```

### EV → Equity bridge [printed p.385, 423–428 / PDF p.404, 442–447]
```
Enterprise Value (EV)   = PV of FCFF + Terminal Value
+ Cash and near-cash    (add at face unless trapped/misallocated)
+ Other non-operating assets (minority stakes at market; undeveloped land)
− Total Debt (market value, or book if close)
− Minority Interest
− Preferred Stock
= Equity Value
÷ Diluted Shares Outstanding  (see Ch.16 on options below)
= Intrinsic Value per Share
```

### Worked micro-example — FCFF
| | Year 1 |
|---|---|
| EBIT | $200m |
| Tax rate | 30% |
| EBIT(1−t) | $140m |
| Net Capex | ($45m) |
| Δ Noncash WC | ($15m) |
| **FCFF** | **$80m** |

Assumptions: WACC = 9%, 3-year high growth at 12% then g_stable = 3%, ROC_stable = 12%.
```
RR_stable = 3%/12% = 25%
FCFF_4   = FCFF_1 × 1.12³ × 1.03 = $80m × 1.405 × 1.03 = $115.8m
FCFF_4 net of reinvestment = $115.8m × (1 − 0.25) = $86.9m
TV_3     = $86.9m / (0.09 − 0.03) = $1,448m
PV(TV)   = $1,448m / 1.09³ = $1,118m
PV of explicit FCFFs ≈ $215m   [illustrative sum]
Firm Value ≈ $1,333m
```

---

## 3. FCFE — Free Cash Flow to Equity

### Formula [printed p.351–352 / PDF p.370–371]

**Full version:**
```
FCFE = Net Income
       − Net Capex                         (= Capex − Depreciation)
       − Δ Noncash WC
       + (New debt issued − Debt repaid)
```

**Short-form (stable target debt ratio δ):**
```
FCFE = Net Income  −  (Net Capex)(1 − δ)  −  (Δ Noncash WC)(1 − δ)
```
where δ = proportion of reinvestment funded by debt (book-value basis).

If preferred stock exists, subtract preferred dividends and adjust δ.

### Discount rate: Cost of equity (k_e)
Discount FCFE at the levered cost of equity → produces **equity value directly** (no EV bridge needed).

### Multi-stage model [printed p.355–370 / PDF p.374–389]
```
Equity Value = Σ [FCFE_t / (1+ke)^t]  +  [TVe_n / (1+ke)^n]

TVe_n = FCFE_{n+1} / (ke − g_stable)
      = NI_{n+1} × (1 − EqRR_stable) / (ke − g_stable)

where EqRR_stable = g_stable / ROE_stable
```

### Negative FCFE and dilution [printed p.370–371 / PDF p.389–390]
When FCFE < 0 the firm implicitly issues new equity; the negative present value of those future equity issuances is already captured in the DCF. **Do not charge dilution again** — that is double-counting [see damodaran_index.md, principle 6].

---

## 4. DDM — Dividend Discount Models

### General model [printed p.323 / PDF p.342]
```
P₀ = Σ [DPS_t / (1+ke)^t]   (t = 1 to ∞)
```

### 4a. Gordon Growth Model (stable DDM) [printed p.323–327 / PDF p.342–346]
```
P₀ = DPS₁ / (ke − g)
   = DPS₀ × (1+g) / (ke − g)
```
Caveats:
- g **must be ≤ risk-free rate** (else firm outlives the economy).
- Stable payout ratio = `1 − g/ROE`; stable beta ∈ [0.8, 1.2].
- Sensitive to small g changes; use only for utilities, REITs, mature firms paying full residual cash.

**Worked example** (Con Ed, May 2011) [printed p.326–327 / PDF p.345–346]:
```
DPS₀ = $2.22, ke = 7.5% (β=0.80, rf=3.5%, ERP=5%), g = 3.5%
P₀ = $2.22 × 1.035 / (0.075 − 0.035) = $2.298 / 0.04 = $57.46
```

### 4b. Two-Stage DDM [printed p.329–331 / PDF p.348–350]
```
P₀ = Σ [DPS_t / (1+ke,hg)^t]  (t=1 to n)
   + [P_n / (1+ke,hg)^n]

where P_n = DPS_{n+1} / (ke,st − g_n)
      DPS_{n+1} = EPS_n × (1+g_n) × Stable payout ratio
```
Best for: firms with patent/barrier-driven supernormal growth that ends abruptly, modest initial growth rate (≤ ~7–8%), regular dividend payers.

**Worked example** (P&G, May 2011) [printed p.331–332 / PDF p.350–351]:
```
ke = 8.0%, g = 10% for 5 yrs (ROE=20%, b=50%), then g_n=3%, ROE=12%, ke,st=8.5%
Stable payout = 1 − 3%/12% = 75%
EPS₅ = $3.82 × 1.10⁵ = $6.15; DPS₆ = $6.15 × 1.03 × 0.75 = $4.75
P₅   = $4.75 / (0.085 − 0.03) = $86.41
PV(P₅) = $86.41 / 1.08⁵ = $58.81; PV(DPS₁..₅) = $10.09
P₀ = $68.90
```

### 4c. H-Model [printed p.338–339 / PDF p.357–358]
Growth declines **linearly** from g_a to g_n over 2H years:
```
P₀ = [DPS₀ × (1 + g_n)] / (ke − g_n)
   + [DPS₀ × H × (g_a − g_n)] / (ke − g_n)
   = [DPS₀ / (ke − g_n)] × [(1 + g_n) + H(g_a − g_n)]
```
Constant payout throughout; use for firms whose growth is already decelerating gradually.

### 4d. Three-Stage DDM
Explicit high-growth phase → linear fade (H-model style) → stable growth. Most flexible form; appropriate for high-growth firms where growth cannot realistically drop overnight.
```
P₀ = Σ [DPS_t/(1+ke,hg)^t]        (t=1..n₁)
   + Σ [DPS_t/(1+ke,tr)^t]        (t=n₁+1..n₂)  [declining g, payout rising]
   + [P_n₂ / (1+ke,tr)^n₂]
```

---

## 5. DDM vs. FCFE: When They Agree and When They Diverge [printed p.371–374 / PDF p.390–393]

| Condition | Effect |
|---|---|
| Dividends = FCFE | DDM = FCFE value |
| FCFE > Dividends, excess invested at zero NPV | DDM = FCFE value |
| FCFE > Dividends, excess wasted/invested poorly | FCFE value > DDM value |
| Dividends > FCFE (unsustainable) | FCFE value < DDM value; prefer FCFE |

**Key rule:** When dividends systematically differ from FCFE, the FCFE model captures true value of the operating business; the gap between FCFE value and DDM value represents the value of controlling dividend policy. Use FCFE when: (a) firm has history of retaining excess cash, or (b) control change is likely. Use DDM when: (a) firm pays out ≈ FCFE as dividends, (b) takeover is remote.

---

## 6. APV — Adjusted Present Value [printed p.398–401 / PDF p.417–420]

### Three-step mechanics
```
Step 1: Unlevered firm value
   V_u = FCFF₁ / (ρ_u − g)
   where ρ_u = unlevered cost of equity
             = rf + β_u × ERP
             and β_u = β_levered / [1 + (1−t)(D/E)]

Step 2: PV of tax shields
   PV(tax shields) = t_c × D    [if debt is permanent perpetuity]
   Otherwise: discount each year's interest tax saving at pretax cost of debt.

Step 3: Expected bankruptcy cost
   PV(bankruptcy cost) = π_default × BC_fraction × Firm Value

APV = V_u + PV(tax shields) − PV(bankruptcy cost)
```

**Full APV formula** [printed p.401 / PDF p.420]:
```
V_levered = FCFF₀(1+g)/(ρ_u − g)  +  t_c × D  −  π_a × BC
```

### APV vs. WACC choice [printed p.401 / PDF p.420]
- **WACC approach:** simpler; assumes stable debt ratio; embeds tax shield in discount rate. Use for stable-leverage ongoing firms.
- **APV approach:** more flexible on debt schedules; explicitly models bankruptcy cost. Preferred for LBOs, leveraged recaps, firms with rapidly changing leverage.

### Worked APV example (J. Crew LBO, 2010) [printed p.400–401 / PDF p.419–420]
```
ρ_u = 8.5% (β_u = 1.00, rf = 3.5%, ERP = 5%)
FCFF_stable = $230m × 0.65 × 0.75 = $112m
V_u = $112m × 1.035 / (0.085 − 0.035) = $2,321m

PV(tax shields) = $305m  [scheduled debt paydown to $500m perpetuity]

π_default = 20% (BB rating), BC = 30% of firm value
PV(bankruptcy cost) = (2,321 + 305) × 0.30 × 0.20 = $158m

APV = $2,321 + $305 − $158 = $2,469m
```

---

## 7. Model Selection: Equity vs. Firm Approach

| Condition | Preferred model |
|---|---|
| Stable leverage, dividend-paying firm | DDM or FCFE |
| Leveraged firm, changing D/E | FCFF or APV |
| LBO / known debt schedule | APV |
| Firm with minority interest / complex capital | FCFF |
| Firm pays dividends ≈ FCFE | DDM |
| Firm retains significant cash vs. payout | FCFE |

**Both approaches yield the same equity value** if leverage assumptions are fully consistent. In practice, use FCFF and bridge to equity; separately value cash and non-operating assets [printed p.396–397 / PDF p.415–416].

---

## 8. Handling Non-Operating Assets in the EV→Equity Bridge [Ch.16, printed p.423–428 / PDF p.442–447]

- **Cash/near-cash:** add at face (no discount rate mismatch). Exception: foreign trapped cash — haircut for repatriation tax. Exception: excess cash at management-mistrusted firms — apply probability-weighted agency discount.
- **Cross-holdings (minority stakes):** add at market value if publicly traded; use book value or revenue multiple otherwise.
- **Employee stock options:** do NOT use fully-diluted share count (overstates dilution, drops time premium). Value options via Black-Scholes at grant terms → subtract from equity value → divide by **basic** shares outstanding. For high-growth/negative-FCFE firms the dilution is already embedded in negative cash flows — do not double-charge.

---

*Page-anchor format: [printed p.X / PDF p.Y]. PDF page = printed page + 19 throughout Damodaran (3rd ed.).*
