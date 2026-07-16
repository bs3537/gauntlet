# rNPV and Real Options Valuation Reference
## Source: Damodaran, *Investment Valuation* (3rd ed.)
## Chapters: 5 (p.87–129), 28 (p.781–823), 29 (p.805–844), 33 (p.894–943)
## Page anchors: [printed p.X / PDF p.Y] where PDF = printed + 19
## Also: Upstream Bio report as canonical worked rNPV example

---

## 1. Risk-Adjusted NPV (rNPV) / Sum-of-the-Parts for Pipeline Assets

### Core Formula
For a single pipeline asset (drug, indication, program):

```
rNPV_asset = LoA × PV(peak commercial cash flows) − PV(remaining development cost)
```

Where:
- **LoA** = Likelihood of Approval = cumulative probability of success through all remaining clinical/regulatory phases (∈ [0, 1])
- **PV(commercial cash flows)** = discounted value of post-approval revenues minus COGS/SGA/royalties, discounted at the biotech WACC or risk-adjusted rate
- **PV(remaining development cost)** = present value of future phase costs (Phase 2, 3, NDA, launch)

**Optional assets floor at zero** (no negative rNPV; if development cost exceeds LoA-adjusted revenues, optionally discard or hold at 0 since management can abandon).

### Sum-of-the-Parts (SOTP) to Equity Value
```
Enterprise rNPV = Σ rNPV_i (across all pipeline assets i)
               + PV(marketed product cash flows)
               + PV(platform/technology option value)

Equity Value = Enterprise rNPV + Net Cash − Debt − PV(G&A overhead)
```

**Dilution treatment (Damodaran, p.371 / p.443 / p.658-659):** value on TODAY's fully diluted share
count. Do NOT subtract a "PV(future R&D dilution)" term or divide by a projected post-raise share
count. Future fundraising is already captured through the negative development/operating cash outflows
(the PV of that spend IS the dilution discount); charging again double-counts, and a fair-value raise
is value-neutral. Model a funding gap as a solvency/liquidity DISCLOSURE and a falsifier, and put a
genuinely below-intrinsic / distress raise in the probability-weighted bear scenario — never as a
structural per-share haircut. Value options as a liability, subtract, and divide by primary shares (p.446).

### LoA Benchmarks (industry rule-of-thumb, not from Damodaran directly)
- Phase 1 → Approval: ~10–15% for oncology; ~20–25% for non-oncology
- Phase 2 → Approval: ~25–35%
- Phase 3 → Approval: ~60–70%
- NDA/BLA → Approval: ~85–90%

LoA must be ∈ [0,1]. Never use LoA > 1.

### Connection to Scenario Weighting
rNPV is equivalent to a scenario-weighted DCF where the scenarios are: (A) drug succeeds with probability LoA and (B) drug fails with probability (1 − LoA). The "bear/base/bull" framework layers probability-weighted scenarios on top of the binary success/failure:

```
Target Price = p_bull × TP_bull + p_base × TP_base + p_bear × TP_bear
```

Where each TP is computed from a full rNPV/SOTP under that macro/market scenario.

### 1a. Partnered / out-licensed asset — value the ROYALTY + MILESTONE interest (not product sales)

When an asset is OUT-LICENSED (the company earns royalties + milestones while the partner funds and
commercializes), value the company's economic INTEREST, not the product P&L:

1. **Royalty FCF stream.** Project the PARTNER's product net sales (launch → ramp → plateau → LoE
   erosion, by geography), multiply by the licensor's royalty rate, risk-adjust by the indication LoA,
   and discount each year at WACC. Royalty income carries ~no COGS/commercial cost to the licensor, so
   it is ~free cash flow (net a modest admin/tax; NOLs may shield early years).
2. **Milestones — PoS-weighted, discounted, INCLUDED in the base case.** Value every development,
   regulatory/commercial, and sales milestone tranche as `amount × PoS ÷ (1+WACC)^year`. **Derive each
   PoS** from historical clinical + FDA success rates for the SPECIALTY (e.g. BIO / QLS / Informa
   phase-transition & likelihood-of-approval by disease area — the §36 LoA benchmarks are a floor; use
   the specialty figure where available) through the analysis's ensemble. Gate by trigger: development
   ≈ the phase→filing rate (above the approval LoA, since filing precedes approval); commercial/approval
   ≈ the approval LoA; sales ≈ LoA × P(peak sales ≥ threshold | approved) over the (often confidential)
   threshold ladder. Do NOT bracket confidential milestones to zero — credit them at the derived PoS
   and disclose the ladder assumption + sensitivity; carry the conditional tails into bear/bull.
3. **Per-asset SOTP** = discounted royalty FCFs + PoS-weighted discounted milestones (+ any second
   territory licensee as its own stream). Sum across candidates, add net cash, subtract PV(overhead not
   borne by the partner) and the option liability, and bridge to equity on TODAY's fully diluted shares
   (no future-dilution haircut). Cross-check with a full income-statement → FCF DCF in which the
   licensor's "revenue" is the risk-adjusted royalty + milestone stream (both should bracket the value).

### Upstream Bio Canonical Worked Example (rNPV for one asset)
[Synthetic illustration based on Upstream Bio-style analysis:]

Asset: CRTH2 antagonist (UPB-101), atopic dermatitis Phase 2

Inputs:
- Peak net sales (addressable market × share × pricing, net of gross-to-net): $600M/yr
- Sales ramp: 4 years post-launch, peak held 5 years, then generic erosion
- LoA from Phase 2 start = 35% (Phase 2 → approval conditional × Phase 3 conditional)
- Net margin on peak sales = 70% (royalty-free, small biotech)
- Discount rate = 12% (biotech WACC)
- Time to potential launch = 6 years (3yr Phase 2/3, 1yr NDA, 2yr ramp start)
- Remaining development cost = $200M (Phase 2: $80M, Phase 3: $120M) over 5 years

Step 1: PV(commercial cash flows) — discount the post-launch sales × margin:
```
Annual NCF in peak year ≈ $600M × 70% = $420M
PV of commercial NCF stream (using DCF at 12%) ≈ $850M (illustrative)
```

Step 2: rNPV:
```
rNPV = 0.35 × $850M − $200M (PV of dev costs, partially certain)
     = $297.5M − $200M
     = ~$97.5M
```

Step 3: Sum with other assets and net cash to derive equity value per share.

**Guardrail:** if rNPV_asset < 0 and management has the option to discontinue, floor at 0.

---

## 2. Scenario Analysis, Decision Trees (Roll-Back), and Monte Carlo

**Source:** Ch.33 [printed p.894–935 / PDF p.913–954]

### When Each Is Appropriate

| Method | Best For | Key Limit |
|--------|---------|-----------|
| **Scenario analysis** | 2–5 discrete macro/event outcomes; investor communication; quick triangulation of bear/base/bull | Doesn't cover full probability space; danger of double-counting risk |
| **Decision tree (roll-back)** | Sequential risk with discrete decision nodes (e.g., FDA Phase 1→2→3); ≤10 branches | Complexity explodes with many phases; assumption of constant discount rate across nodes is incorrect |
| **Monte Carlo simulation** | Continuous distributions of inputs; many correlated sources of uncertainty; generates full value distribution | Requires specifying input distributions (garbage-in-garbage-out); variance used as option-pricing input must be variance in value over time, not at a point in time |

### Scenario Analysis — Steps
[printed p.895–896 / PDF p.914–915]

1. Identify 2–3 critical factors that drive the bulk of value uncertainty.
2. Determine number of scenarios (typically 3–5; fewer allows better cash-flow estimation).
3. Estimate cash flows / target price under each scenario.
4. Assign probabilities (must sum to 1 across the full spectrum of scenarios).
5. Compute probability-weighted expected value.

**Double-counting risk:** If the discount rate already reflects the risks in a scenario, do NOT further penalize the scenario-weighted value. Either risk-adjust via probabilities (preferred for discrete/binary risks) OR via discount rate — not both.

### Decision Tree (Roll-Back) — Five Steps
[printed p.900–902 / PDF p.919–921]

1. **Divide into risk phases** (FDA stages, clinical milestones, regulatory decisions).
2. **Estimate probabilities** at each event node (must sum to 1 per node; test for conditional vs unconditional probabilities).
3. **Define decision nodes** (points where management can abandon, expand, or continue).
4. **Compute cash flows / value at end nodes** — including NPV of downstream commercial program.
5. **Fold back (roll-back):** at event nodes, compute probability-weighted expected value; at decision nodes, take the highest-value branch.

**Example: Pharma drug three-stage FDA process**
[printed p.902–904 / PDF p.921–923]

```
Phase 1 (p_success=70%, cost=$50M, 1yr)
  → Phase 2: 50% chance → Type 1+2 diabetes ($400M/yr revenue, 15yr)
           : 30% chance → Type 1 only ($300M/yr, 15yr)
           : 10% chance → Type 2 only ($125M/yr, 15yr)
           : 10% fail
  → Phase 3: p_success=80% (single indication) or 75% (both)
```

Roll-back with 10% discount rate → expected value of drug today = **$50.36M**

### Monte Carlo — Key Note for Real Option Inputs
[printed p.808–809 / PDF p.827–828]

The variance input for real option pricing (σ²) must be the variance in the **present value of the project** over time — not variance in annual revenue or current-period income. Estimating this:
- Use historical variance of comparable public biotech firms
- Or run a simulation over key inputs (market size, price, uptake) and compute the standard deviation of the resulting distribution of present values

---

## 3. Patent / R&D as a Real Option (Biotech rNPV Foundation)

**Source:** Ch.28 [printed p.781–806 / PDF p.800–825]

### Core Framework: Patent as a Call Option
[printed p.789–791 / PDF p.808–810]

A patent (or exclusive R&D program) gives the firm the **right but not the obligation** to commercialize. It is a **call option** on the underlying project:

| Option Input | Patent / R&D Analog |
|---|---|
| S (underlying asset value) | PV of cash flows if the product were commercialized today |
| K (strike price) | Development/commercialization cost (CapEx, launch costs) |
| t (time to expiration) | Remaining patent life (or exclusive license period) |
| σ² (variance) | Variance in the present value of the underlying project |
| r (risk-free rate) | Rate matching expiration horizon (e.g., 17-yr Treasury) |
| y (dividend yield analog) | **Cost of delay ≈ 1 / patent life** (each year of waiting loses one year of protected cash flows) |

[printed p.784 / PDF p.803]:
```
Annual cost of delay = 1 / n   (where n = years remaining on patent)
```
This rises over time: 1/17 in year 1, 1/16 in year 2, … making early exercise more attractive as the patent ages.

### Black-Scholes (Dividend-Adjusted) Formula
```
C = S × exp(−y×t) × N(d1) − K × exp(−r×t) × N(d2)

d1 = [ln(S/K) + (r − y + σ²/2) × t] / (σ × √t)
d2 = d1 − σ × √t
```

Where `y = cost of delay = 1/patent life`.

### Worked Example: Avonex Patent (Biogen, 1997)
[printed p.791–792 / PDF p.810–811]

**Inputs:**
- S = PV of commercial cash flows = $3,422M
- K = Development cost = $2,875M
- t = 17 years (patent life)
- σ² = 0.224 (average variance of publicly traded biotech firms)
- r = 6.7% (17-year T-bond rate)
- y = 1/17 = 5.89% (cost of delay)

**Outputs:**
- d1 = 1.1362, N(d1) = 0.8720
- d2 = −0.8512, N(d2) = 0.2076

**Option value:**
```
C = 3,422 × exp(−0.0589×17) × 0.8720 − 2,875 × exp(−0.067×17) × 0.2076
  = $907M
```

**vs. naive NPV:**
```
NPV = S − K = 3,422 − 2,875 = $547M
```

The **time premium = $907M − $547M = $360M** — value of waiting to let uncertainty resolve. The firm is better off not commercializing immediately. N(d2) = 0.2076 implies only ~21% probability the option ends in-the-money by expiration.

### When Option Value > Naive NPV
The gap (time premium) is largest when:
- The project is **out-of-the-money** (S < K) but volatile
- Patent life is long (low cost-of-delay)
- σ² is high (highly uncertain underlying value)

This is exactly the biotech Phase 1/2 case: S < K is common, σ² is 0.2–0.6, patent life is 10–17 years.

### Valuing a Firm with Multiple Patents (Biogen illustration)
[printed p.793–795 / PDF p.812–814]

```
Firm Value = PV(licensed/marketed products)
           + Value(undeveloped patents via option model per patent)
           + NPV(future R&D pipeline, if research generates value > cost)
```

For Biogen 1997:
- PV(license fees, 12yr, 7% discount) = $397M
- Value(Avonex patent) = $907M (option model)
- PV(future R&D surplus) = $318M
- **Total = $1,622M → $45.70/share**

### Guardrail: When Not to Use the Patent-Option Framework
[printed p.793 / PDF p.812]: Use the real option model for small firms with 1–2 patents and limited assets. For large established pharma with many patents and significant marketed revenue, use DCF (growth rate implicitly captures option value).

**Double-counting caution:** If the DCF model already uses a high growth rate that reflects the value of the R&D pipeline and patent portfolio, do NOT additionally add an explicit real option value for those same patents. [Ch.28, printed p.793 / PDF p.812; Ch.29, printed p.815 / PDF p.834]

---

## 4. Option to Expand

**Source:** Ch.29 [printed p.805–815 / PDF p.824–834]

### Framework
The option to expand is a call option on future investment:

| Option Input | Expand Analog |
|---|---|
| S | PV of expected cash flows from the expansion project today |
| K | Cost of expansion (exercise price) |
| t | Time horizon for decision (internally imposed; no legal expiry) |
| σ² | Variance in the PV of the expansion opportunity |

The initial project (even if NPV < 0) may be worth taking if it grants the right to expand:

```
NPV_adjusted = NPV_initial + C(S, K, t, σ², r)
```

[printed p.808 / PDF p.827] Ambev example: initial NPV = −$100M, expansion option C = $203M → adjusted NPV = +$103M; proceed.

### When Expansion Options Are Most Valuable
1. Initial investment is a **prerequisite** (legal or practical) for the subsequent expansion.
2. Firm has **exclusive rights** to the expansion opportunity (patent, license, first-mover advantage).
3. Competitive advantages are **sustainable** — otherwise NPV of expansion converges to zero as competition enters.

**Guardrail:** Do not use expansion option value to justify investments that are merely "strategic" without quantifying the option. The option value must exceed the NPV deficit. [printed p.812–813 / PDF p.831–832]

**Double-counting rule:** If the DCF model already reflects an above-WACC return or high growth from the expansion pathway, adding an explicit option value is double-counting. [printed p.815 / PDF p.834]

### Multistage Projects as Sequential Options
Each stage = a call option on the right to proceed to the next stage. This is equivalent to compound options. Gains are highest when:
- Barriers to entry exist (competitors cannot copy immediately)
- Uncertainty is high (high σ²)
- Investments are lumpy with high fixed costs

---

## 5. Option to Abandon

**Source:** Ch.29 [printed p.816–822 / PDF p.835–841]

The option to abandon (sell/scrap a project) is a **put option** on the underlying project:

| Option Input | Abandon Analog |
|---|---|
| S | PV of expected cash flows continuing the project |
| K | Salvage value / liquidation proceeds |
| t | Life of the project or time to decision |
| σ² | Variance in project value |

```
Put value = K × exp(−r×t) × N(−d2) − S × exp(−y×t) × N(−d1)
```

The option to abandon is most valuable when:
- Salvage value K is high (large liquidation proceeds)
- Project value S is volatile (high σ²)
- The firm has flexibility (not locked into long-term contracts)

Adding the abandonment put to a project makes it more valuable than the naive DCF:
```
Project value (with abandonment) = DCF value + Put value
```

---

## 6. Equity as a Call Option in Distressed Firms

**Source:** Ch.30 [printed p.826–829 / PDF p.845–848]

For firms with substantial debt, equity is equivalent to a call option on firm assets:

| Option Input | Distressed Equity Analog |
|---|---|
| S | Current market value of firm assets |
| K | Face value of outstanding debt |
| t | Maturity of debt (approximated by weighted average) |
| σ² | Variance in firm asset value |

```
Equity value = C = S × N(d1) − K × exp(−r×t) × N(d2)
Debt value = Firm value − Equity value
```

[printed p.828 / PDF p.847] Example: S=$100M, K=$80M, t=10yr, σ=40%, r=10% → Equity value = $75.94M (Black-Scholes call). Even if S drops to $50M < K=$80M, equity retains $30.44M of option time value.

**Key insight:** For distressed biotech with negative DCF equity value but high asset variance, the option framework may show positive equity value. This motivates the rNPV + real option hybrid approach.

**Pointer:** See `special_cases.md` for detailed distressed/negative-equity treatment.

---

## 7. Reconciling Real Option Value vs. DCF

**Source:** Ch.29 [printed p.823 / PDF p.842]; Ch.28 [printed p.793 / PDF p.812]

Real option models yield higher values than DCF when:
1. The DCF model assumes fixed expected cash flows and ignores management's ability to wait, expand, or abandon in response to information.
2. The underlying project is **out-of-the-money** (S < K) but variance is high.

Why the two approaches can diverge:
- DCF uses a single risk-adjusted discount rate for all future periods.
- Real options / decision trees can adjust the discount rate at each node (as risk exposure to market risk changes); if you do this consistently, both approaches converge.
- Real options pricing uses the **risk-free rate** in the replication/arbitrage argument; this is appropriate when you can form replicating portfolios. For non-traded projects, the arbitrage is imperfect — a conservatism adjustment (higher S-discount rate or illiquidity haircut) is appropriate.

[printed p.786 / PDF p.805]: "If you want to be more conservative in your estimate of value for real options to reflect the difficulty of arbitrage, you have two choices: use a higher discount rate in computing PV of cash flows (lowering S), or apply an illiquidity discount to the option value."

---

## 8. Master Guardrails

1. **LoA ∈ [0, 1] always.** Never apply probabilities that exceed 100% or sum to more than 1 across mutually exclusive outcomes.

2. **No double-counting growth-option value:** If a DCF model already uses a high growth rate that implicitly captures the value of the option to expand or the pipeline, do NOT add an explicit real option premium on top. The two are mutually exclusive.
   - DCF with high growth → drop the explicit option model
   - Option model for specific patent/phase → use a conservative (near-zero or breakeven) DCF growth rate

3. **Floor optional/early-stage assets at rNPV ≥ 0** when management retains the right to abandon.

4. **Cost of delay is dynamic:** 1/n rises each year as patent life shortens. Re-compute annually.

5. **Variance input for options is variance in project value over time** — not variance in quarterly revenue or EBITDA. Use public comparable biotech equity/firm value volatility (σ² ≈ 0.15–0.30 for established biotech; 0.30–0.60 for early-stage) or derive from Monte Carlo on DCF inputs.

6. **Risk-adjusting in rNPV:** Risk is captured through LoA (probability of failure), NOT through an elevated discount rate that also penalizes for failure risk. Using both LoA and a very high discount rate double-penalizes the downside.

---

## Summary: Option Pricing Inputs by Real Option Type

| Real Option Type | S | K | t | σ² | Yield analog (y) |
|---|---|---|---|---|---|
| Patent / R&D (Ch.28) | PV(commercial CF if launched now) | Development cost | Patent life remaining | Biotech firm value variance | 1/patent life |
| Option to delay project (Ch.28) | PV(project CF if started now) | Up-front investment | Exclusive rights period | Project value variance | 1/project life or CF/PV |
| Option to expand (Ch.29) | PV(expansion CF today) | Expansion cost | Decision horizon | Expansion market variance | Cost of deferring first expansion CF |
| Option to abandon (Ch.29) | PV(continuation CF) | Salvage value | Project life | Project value variance | n/a (put option) |
| Equity as call option (Ch.30) | Firm asset value | Face value of debt | Debt maturity | Firm asset value variance | Dividend yield |
