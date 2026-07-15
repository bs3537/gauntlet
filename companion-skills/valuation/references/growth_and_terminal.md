# Growth Estimation and Terminal Value

**Source:** Damodaran, *Investment Valuation* (3rd ed.)  
**Chapters:** 11 (pp. 271–322), 12 (pp. 304–341)  
**Page-anchor convention:** [printed p.X / PDF p.Y] where PDF = printed + 19

---

## 1. Three Approaches to Estimating Growth [printed p.271 / PDF p.290]

| Method | Reliability | Use case |
|---|---|---|
| Historical (arithmetic or geometric) | Low for high-growth firms; reasonable for stable | Sanity check; stable firms |
| Analyst consensus | Short horizon (1–2 yr) reasonable; long horizon poor | Cross-check only |
| **Fundamental (RR × ROC)** | Internally consistent; links investment to returns | **Preferred for explicit forecast period** |

---

## 2. Historical Growth [printed p.272–273 / PDF p.291–292]

### Arithmetic vs. Geometric Average
```
Arithmetic average = Σ g_t / n          (simple average of year-over-year rates)

Geometric average  = (EPS_n / EPS_0)^(1/n) − 1   (compounded rate)
```
**Use geometric average.** Arithmetic overstates true growth for volatile earnings series.  
For revenue growth the two are closer; for earnings (especially cyclical firms) the gap can be large.

### Limitations of historical growth [printed p.271–272 / PDF p.290–291]
- Negative base-year earnings make historical rates undefined or misleading.
- Past growth driven by acquisitions or one-offs may not persist.
- High historical growth in small firms is not scalable.

---

## 3. Analyst Growth Estimates [printed p.285 / PDF p.304]

Useful inputs: consensus near-term EPS growth, dispersion of estimates (higher dispersion → lower reliability), analyst forecast error track record. Do not extrapolate analyst short-term estimates into the terminal value period.

---

## 4. Fundamental Growth — Operating Income (FCFF path) [printed p.290–295 / PDF p.309–314]

### Stable ROC scenario [printed p.290 / PDF p.309]
```
g_EBIT = Reinvestment Rate × ROC

where:
  Reinvestment Rate = (Net Capex + Δ Noncash WC) / EBIT(1−t)
  ROC = EBIT(1−t) / (BV of Equity + BV of Debt − Cash)
```

**Core principle:** Growth creates value **only if ROC > WACC**. If ROC = WACC, growth is value-neutral. If ROC < WACC, growth destroys value [printed p.308–314 / PDF p.327–333].

### Changing ROC scenario [printed p.294 / PDF p.313]
When the average return on capital shifts from one year to the next:
```
g = ROC_t × RR  +  (ROC_t − ROC_{t−1}) / ROC_{t−1}
```
The second term is "efficiency-generated growth" from improving returns on existing assets. Example:  
ROC improves 10% → 11%, RR = 40%:
```
g = 0.11 × 0.40 + (0.11 − 0.10)/0.10 = 4.4% + 10% = 14.4%
```
This effect is one-time; once ROC stabilizes, growth reverts to RR × ROC.

### Practical steps
1. Normalize RR and ROC over 3–5 years if volatile (Tata Motors example: [printed p.292–293 / PDF p.311–312]).
2. Use marginal/forward ROC for new investments, not legacy average.
3. For negative EBIT: forecast revenue growth, then operating margin path to positive EBIT.

---

## 5. Fundamental Growth — Equity Income (FCFE / DDM path) [printed p.285–289 / PDF p.304–308]

### EPS growth (no new equity issuance)
```
g_EPS = Retention Ratio × ROE
      = b × ROE
```

### Net income growth (including new equity)
```
g_NI = Equity Reinvestment Rate × ROE

Equity Reinvestment Rate = (Net Capex + Δ WC − Net debt issued) / Net Income
```

### ROE decomposition [printed p.288 / PDF p.307]
```
ROE = ROC + (D/E) × [ROC − i(1−t)]
```
where ROC and D/E are on **book value** basis. Higher leverage amplifies ROE if ROC > after-tax cost of debt; this leverage-driven ROE is not sustainable growth — it comes from financial structure, not operating value creation.

---

## 6. Terminal Value [Ch.12, printed p.304–322 / PDF p.323–341]

### Why terminal value dominates
Terminal value (TV) typically comprises **50–70% of total firm value** for most companies, and can reach 80%+ for high-growth firms. This makes the assumptions going into TV the single most consequential judgment in a DCF.

### The stable-growth perpetuity formula [printed p.306 / PDF p.325]
```
TV_n = FCF_{n+1} / (r − g_stable)

For FCFF:   TV_n = FCFF_{n+1} / (WACC − g_stable)
For FCFE:   TV_n = FCFE_{n+1} / (ke − g_stable)
For DDM:    TV_n = DPS_{n+1} / (ke,st − g_stable)
```

### Implied stable-phase reinvestment [printed p.312–313 / PDF p.331–332]
```
RR_stable (FCFF) = g_stable / ROC_stable
EqRR_stable (FCFE) = g_stable / ROE_stable
Payout_stable (DDM) = 1 − g_stable / ROE_stable
```
**A higher terminal growth rate forces a higher reinvestment rate, which lowers terminal FCF.** When ROC_stable = WACC, the choice of g_stable is irrelevant to value [printed p.313–314 / PDF p.332–333].

---

## 7. Constraints on Stable Growth Rate [printed p.306–307 / PDF p.325–326]

### HARD CAPS (non-negotiable guardrails)

```
┌─────────────────────────────────────────────────────────────────┐
│  GUARDRAILS — THE VALIDATOR WILL ENFORCE THESE                  │
│                                                                 │
│  1. g_stable < r  (discount rate)       — math constraint      │
│     (TV formula goes negative or infinite if violated)          │
│                                                                 │
│  2. g_stable ≤ rf  (risk-free rate)     — economic constraint   │
│     "A simple rule of thumb on the stable growth rate is that  │
│      it generally should not exceed the riskless rate"          │
│     [printed p.307 / PDF p.326]                                 │
│                                                                 │
│  3. g_stable ≤ nominal GDP growth of economy                   │
│     "No firm can grow forever at a rate higher than the growth  │
│      rate of the economy in which it operates"                  │
│     [printed p.306 / PDF p.325]                                 │
│                                                                 │
│  4. g_stable can be negative (firm contracting / liquidating)  │
│                                                                 │
│  5. Terminal value typically 50–70% of total firm value        │
│     FLAG if TV > 80% of total value (assumptions likely too    │
│     aggressive; warrant explicit sensitivity table)             │
└─────────────────────────────────────────────────────────────────┘
```

### Why rf is the practical ceiling [printed p.307 / PDF p.326]
The risk-free rate incorporates expected inflation and long-run real growth expectations. In long-run equilibrium, nominal risk-free rate ≈ nominal GDP growth rate. Hence g_stable ≤ rf is both practically safe and logically grounded.

---

## 8. Characteristics of the Stable-Growth Firm [printed p.310–316 / PDF p.329–335]

| Parameter | High Growth phase | Stable Growth phase |
|---|---|---|
| Beta | Can be 1.5–2.5+ | Must converge to 0.8–1.2 |
| D/E ratio | Often low | Higher; use industry average |
| ROC / ROE | High (excess returns) | Ideally → industry average or WACC |
| Reinvestment Rate | High | = g_stable / ROC_stable |
| Payout Ratio | Low | = 1 − g_stable / ROE_stable |
| Cost of debt | Often higher | Investment-grade (Baa+) |

Make all adjustments **gradual** during a transition / fade period rather than one cliff-edge switch.

---

## 9. Worked Terminal Value Example

**Alloy Mills** — textile firm [printed p.314 / PDF p.333]:

Given:
- EBIT(1−t) current = $100m, g_high = 10%, ROC = 20%, RR_high = 50%
- After year 5: g_stable = 5%, ROC_stable = 20% (same; retains competitive advantage)
- WACC = 10%

```
Step 1 — Stable reinvestment rate:
  RR_stable = 5% / 20% = 25%

Step 2 — Operating income in year 6:
  EBIT₆(1−t) = $100m × 1.10⁵ × 1.05 = $169.1m

Step 3 — Terminal Value at end of year 5:
  TV₅ = $169.1m × (1 − 0.25) / (0.10 − 0.05)
      = $169.1m × 0.75 / 0.05
      = $2,537m

Step 4 — PV of explicit cash flows (Years 1–5):
  FCF_t = EBIT_t(1−t) × (1 − 0.50)   [RR_high = 50%]
  PV of CFs ≈ $55/1.10 + $60.5/1.10² + ... + $80.5/1.10⁵ ≈ $237m

Step 5 — Firm Value:
  V = PV(explicit) + PV(TV₅)
    = $237m + $2,537m/1.10⁵
    = $237m + $1,575m = ~$2,075m

  TV as % of total value ≈ 76%  [flag, but not atypical for 10-yr high-growth firm]
```

**Sensitivity check:** if ROC_stable drops from 20% to 10% (WACC parity):
```
  RR_stable = 5%/10% = 50%
  TV₅ = $169.1m × (1−0.50)/(0.10−0.05) = $1,691m
  Firm Value ≈ $1,300m   (−37% vs. high-ROC case)
```
This demonstrates that **growth with ROC > WACC creates enormous value**; growth with ROC = WACC adds nothing. The choice of stable ROC often matters more than the choice of g_stable.

---

## 10. Exit Multiple as Terminal Value [printed p.305–306 / PDF p.324–325]

**Permissible** in a relative valuation context but creates a hybrid that is inconsistent with an intrinsic DCF. The multiple implicitly embeds the market's pricing of growth and risk at that future date, which may itself be mispriced.

**Rule:** If using exit multiple for TV in a DCF, back-solve to check the implied g and ROC. If implied g > rf or implied ROC is unreasonably high/low, the multiple is not defensible on a fundamental basis.

---

## 11. Survival / Going-Concern Note

The perpetuity formula assumes the firm is a going concern. For distressed firms or those with concentrated business risk:
- Apply a **survival probability** to each year's cash flows.
- Or discount using a higher rate that incorporates default risk (equity as a call option — see Ch.30).
- Terminal value should be set to liquidation value (not perpetuity) if going-concern assumption is questionable [printed p.304–306 / PDF p.323–325].

---

## 12. Multi-Stage Structure Summary

```
High Growth  ────────►  Transition / Fade  ────────►  Stable Growth
(Explicit CFs;          (Linear decline in g;          (Perpetuity;
 ROC > WACC;            ROC fading toward               ROC ≈ industry
 RR_high)               industry avg;                   avg or WACC;
                        beta → 1.0;                     RR = g/ROC_st)
                        D/E → target)
```

The transition period is **not optional** for firms growing at 20–40%+. Jumping directly from 30% growth to 3% growth in a two-stage model is mechanically valid but economically implausible for large markets.

---

*Page-anchor format: [printed p.X / PDF p.Y]. PDF page = printed page + 19 throughout Damodaran (3rd ed.).*
