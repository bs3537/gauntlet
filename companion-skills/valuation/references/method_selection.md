# Valuation Method Selection — Decision Tree & Reference

**Source:** Damodaran, *Investment Valuation* (3rd ed.). Page anchors use `[printed p.X / PDF p.Y]` format.  
**Offset rule:** PDF page = printed page + 19 throughout the body.

---

## 1. Top-Level Branch: Going Concern vs. Distressed

```
Is the firm a going concern?
│
├─ NO (imminent default risk, heavily leveraged, equity < 0)
│   └─ Equity as a Call Option (Ch.30) — see §5
│       Inputs: S = firm asset value, K = face value of debt, t = duration of debt,
│       σ² = variance in firm value, r = risk-free rate
│       [printed p.826-835 / PDF p.845-854]
│
└─ YES → proceed to earnings sign
```

**Distress-adjusted DCF (when going concern + elevated default risk):**

> Adjusted value = DCF value × (1 − P[distress]) + Distress-sale value × P[distress]

*Example: $1B DCF, $500M distress-sale, 20% P[distress] → $900M adjusted value.*  
[printed p.319 / PDF p.338]

Estimate P[distress] via: (a) bond rating lookup (Altman cumulative default rates), or (b) probit on debt ratio + cash burn. Cash-burn proxy: Cash / |EBITDA| in months. [printed p.319-320 / PDF p.338-339]

---

## 2. Earnings Sign Branch

```
Current earnings: positive OR negative/abnormal?
│
├─ NEGATIVE or ABNORMAL
│   │
│   ├─ Temporary / cyclical / commodity price-driven?
│   │   └─ Normalize earnings (Ch.22):
│   │       Option A: Average dollar earnings over 5-10 year cycle
│   │       Option B: Average margin × current revenues  ← preferred for size-changing firms
│   │       Option C: Adjust expected growth rate in near periods to reflect recovery
│   │       [printed p.617-621 / PDF p.636-640]
│   │
│   ├─ Long-term structural problem / debt overhang?
│   │   └─ Do NOT normalize. Either:
│   │       (a) Model path to recovery — adjust margins over time [printed p.931-932 / PDF p.950-951]
│   │       (b) If imminent default → equity-as-option (Ch.30) or liquidation value
│   │       [printed p.826 / PDF p.845]
│   │
│   └─ Young / start-up / infrastructure build-out?
│       └─ Ch.23 approach — see §6
│
└─ POSITIVE → proceed to leverage stability
```

---

## 3. Equity vs. Firm Valuation (Leverage Stability)

```
Is leverage stable (D/E not expected to change materially during the valuation period)?
│
├─ YES (stable leverage)
│   ├─ Either FCFF/WACC or FCFE/ke give same answer [printed p.13-14 / PDF p.32-33]
│   ├─ Choose whichever you are more comfortable with [printed p.929-930 / PDF p.948-949]
│   └─ ERROR GUARD: Never discount FCFE at WACC (+$175 overstatement) or FCFF at ke
│       ($260 understatement in Damodaran's illustration) [printed p.14-15 / PDF p.33-34]
│
└─ NO (changing leverage: LBO, restructuring, deleveraging)
    └─ Use FCFF/WACC or APV [printed p.930 / PDF p.949-950]
        APV: Value = Value(100% equity) + PV(tax shield) − Expected bankruptcy costs
        [printed p.15-16 / PDF p.34-35]
```

**Within equity valuation — dividends vs. FCFE:**

```
Do dividends ≈ FCFE? (check: dividend payout close to free cash flow to equity?)
│
├─ YES → DDM is valid; use when you cannot estimate capex/WC changes
│   (main use case: financial service firms — Ch.21 [printed p.584 / PDF p.603])
│   Use Gordon stable: P = DPS₁ / (ke − g)  [printed p.323 / PDF p.342]
│   Use H-model (declining growth): P = DPS₀[(1+gL) + H(gS−gL)] / (ke − gL)
│   Use 2-stage: PV of dividends + PV of terminal price  [printed p.323-340 / PDF p.342-359]
│
└─ NO (buybacks > dividends, restricted payouts, high reinvestment)
    └─ FCFE model (Ch.14) [printed p.351 / PDF p.370]
        FCFE = Net income − Net capex − ΔNWC − (Debt repaid − New debt)
```

---

## 4. Growth Pattern Branch (Number of Stages)

```
What is the firm's current growth rate relative to the economy?
│
├─ Already at or below nominal GDP growth → Stable (1-stage) Gordon model
│   Terminal g ≤ risk-free rate ≈ nominal GDP; NEVER exceed [printed p.306-307 / PDF p.325-326]
│
├─ Moderate excess growth (within 8-10% above economy) → 2-stage model
│   High-growth period (explicit) + stable-growth terminal value [printed p.931-933 / PDF p.950-952]
│
└─ High growth (much above economy) → 3-stage or n-stage model
    Transition period where growth declines gradually [printed p.932-933 / PDF p.951-952]

Source of growth matters:
  • Legal/patent barriers → abrupt transition (2-stage) when patent expires
  • General brand/scale advantages → gradual erosion (3-stage preferred) [printed p.933 / PDF p.952]
```

**Fundamental growth check:** g = RR × ROC (or ROE for equity). Value-creating only if ROC > WACC. [printed p.271-274 / PDF p.290-293]

---

## 5. Sector Special Cases — Quick Reference

| Sector | Core Problem | Primary Method | Relative Multiple | Chapter |
|---|---|---|---|---|
| Financial services (banks, insurance, investment banks) | Debt = raw material; capex undefined; regulatory capital | DDM or FCFE or Excess-Return model; equity only | P/B (marked-to-market assets), P/E | 21 |
| Cyclical / commodity | Earnings track cycle/commodity price; current may be trough or peak | Normalize earnings over full cycle (5-10 yr average margin × current revenues) | Normalized P/E; EV/EBITDA on normalized EBITDA | 22 |
| Young / start-up | Negative FCF; no history; no comparables | DCF with forward revenue model → margin path to stable; survival discount | P/S; EV/Sales | 23 |
| Private firms | No market price for risk; undiversified owner | Bottom-up beta; total beta (β/ρ); illiquidity discount; control premium | Transaction multiples | 24 |
| Biotech / patents / undeveloped reserves | Value contingent on event (FDA approval, price threshold) | Real option / rNPV (Ch.28): S = PV(commercialize), K = development cost, cost of delay ≈ 1/patent life | EV/pipeline + probability-weighted NPV | 28 |
| Real estate | Separate assets; income-generating | Cap-rate / NAV: Value = NOI / Cap rate [Ch.26] | P/CF; Price/sq ft | 26 |
| Distressed (high leverage) | DCF overstates; equity has option value | Equity as call option on firm (Ch.30) + distress-adjusted DCF [printed p.319 / PDF p.338] | EV/Assets; recovery rate | 30 |

---

## 6. Young / Start-Up Method (Ch.23)

**Six-step framework** [printed p.648-662 / PDF p.667-681]:

1. Use trailing 12-month revenues (not annual report) — numbers change too fast.
2. Estimate revenue growth path: anchor to market size + competition barriers.
   Reinvestment when FCF negative: use Sales/Capital ratio → Reinvestment = ΔRevenue / (Sales/Capital).
3. Estimate sustainable operating margin in stable state → use mature-industry comparables.
4. Track NOL carry-forward — zero tax until NOLs exhausted.
5. Estimate β from comparable public firms (bottom-up); no regression beta available.
6. Survival discount if cash burn threatens near-term survival:
   Adjusted value = DCF × (1 − P[distress]) + Distress-sale × P[distress] [printed p.319 / PDF p.338]

**Dilution from future equity raises:** dilution is ALREADY embedded in the negative near-term FCFs (future equity raises are financing, not an additional drag on value). Do NOT re-charge dilution on top of negative cash flows — that is double-counting. See `references/damodaran_dilution_principles.md` for full treatment. [printed p.371 / PDF p.390; printed p.443 / PDF p.462; printed p.658 / PDF p.677]

---

## 7. Firm-Type → Method → Chapter Table

| Firm Type | Recommended DCF Method | Relative Method | Chapter(s) |
|---|---|---|---|
| Stable mature, positive FCF, stable leverage | FCFF/WACC stable-growth or FCFE Gordon | EV/EBITDA, P/E, P/B | 13-15 |
| Stable mature, dividends ≈ FCFE | DDM (Gordon) | P/E, P/B | 13 |
| High-growth, changing leverage | FCFF/WACC 2-3 stage; APV if dollar debt | PEG, P/S | 14-15 |
| Financial services | DDM or FCFE or Excess-Return | P/B, P/E | 21 |
| Cyclical / commodity | Normalized FCFF or FCFE | Normalized P/E, EV/EBITDA | 22 |
| Young / start-up | Revenue-forward DCF + survival discount | P/S, EV/Sales | 23 |
| Private firm | DCF with total beta; or bottom-up beta | Private transaction multiples | 24 |
| Distressed (high leverage) | Equity-as-option + distress-adjusted DCF | EV/liquidation assets | 30 |
| Biotech / patent assets | Real option (Ch.28) + rNPV | Pipeline probability-weighted NPV | 28 |
| Real estate / REIT | Cap-rate NAV; P/CF | Cap rate vs. sector | 26 |

---

## 8. Mandatory Cross-Check Rule

**ALWAYS run relative valuation (Ch.17-20) alongside intrinsic DCF.**

From Damodaran [printed p.465-466 / PDF p.484-485]:
> If a firm is overvalued on DCF but undervalued on relative valuation (or vice versa), the divergence is usually a signal that the **entire sector** is mispriced relative to fundamentals — not that your DCF is wrong.

Reconciliation workflow [printed p.466 / PDF p.485]:
1. Identify the multiple most correlated with value for the sector (see Ch.34 Table 34.1 [printed p.935-936 / PDF p.954-955]).
2. Run sector regression of multiple on fundamentals (growth, payout, risk) to get a predicted multiple.
3. Compare actual multiple to predicted: if actual < predicted → relatively cheap; if actual > predicted → relatively expensive.
4. Compare DCF intrinsic value to market price and to peer-derived value. Document the reconciliation and state which view has stronger evidential support.

**Prefer the multiple with the highest R² vs. fundamentals in the sector.** Cyclical manufacturing → P/E (normalized); high-growth/negative earnings → P/S or EV/Sales; infrastructure → EV/EBITDA; financial services → P/B; REIT → P/CF; retailing → P/S or EV/Sales. [printed p.935 / PDF p.954]
