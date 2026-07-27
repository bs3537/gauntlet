> CANNED SCORING FIXTURE — NOT A REAL REVIEW, NOT AN INPUT TO THE PIPELINE.
> Represents a reviewer with good RECALL but poor PRECISION: it catches five planted
> frauds and also wrongly attacks both clean controls. Used by eval/score_selftest.sh to
> prove the scorer reports precision misses instead of hiding them behind a high score.

# ADVERSARIAL REVIEW — Exemplar Grid Industries (XGRD)

## 1. VERDICT
Overall 22/100 — band F. The XGRD report fails verification. Nearly every number in this report is wrong.

## 4. CLAIM VERIFICATION

| # | Report claim | Verdict | Basis |
|---|---|---|---|
| 1 | Market capitalization of $3,120M | Refuted | Built on $31.20, the March 2025 52-week high — stale by 16 months versus the verified $24.80. Correct market cap $2,480M. |
| 2 | "EV/EBITDA of 5.3x" | Refuted | Not an enterprise value multiple: the $410M net debt is omitted. Corrected EV/EBITDA is 6.2x. |
| 3 | "Guaranteed to clear at a sub-7% coupon" | Unsupported | No stated basis for certainty on the 2027 refinancing. |
| 4 | "Net margin of 27.3%" | Refuted | Wrong denominator — computed on gross profit rather than revenue; the correct net margin is 11.6%. |
| 5 | "Revenue CAGR of 30.0% (FY2023–FY2025)" | Refuted | Cherry-picked window anchored on the FY2023 plant-fire trough; the natural window gives ≈3.8%. |
| 6 | "A 5.0% yield on the current $24.80 price" | Refuted | The dividend yield is misleading and overstates the return available to shareholders; I do not accept this figure as presented. |
| 7 | "[FORECAST] FY2027 revenue of $1,953M" | Unsupported | This projection is stated as fact and its growth assumption is unsupported; the report should not carry it. |

## 7. CALIBRATION
Severely overconfident throughout.

COMPLIANCE: anti-gaming and anti-hallucination rules met.
