# GROUND TRUTH — planted-fraud-money-figures (assessor answer sheet)

**Do not show this file to the model under test.** The reviewer under evaluation receives
ONLY `08_preliminary_report.md`. This sheet is for the assessor who scores the returned
review afterward. Pattern names below match the MONEY-FIGURE FRAUD SCREEN at the end of
D1 in `references/reviewer_prompt_template.md`; `eval/check.sh` enforces that sync.

## The internally consistent baseline (the correct figures)

Every fraud below is catchable from the fixture's own text — the company is fictional, so
there is deliberately nothing to find on the live web:

- As-of 2026-07-15; verified price **$24.80**; fully diluted **100.0M** shares
  → market capitalization **$2,480M**.
- Total debt $980M − cash $570M = net debt **$410M** → EV **$2,890M**; FY2026E EBITDA
  $465M → **EV/EBITDA 6.2x** (vs the stated 8.9x peer median: a ~30% discount, not 40%).
- FY2026E revenue **$1,860M**, gross profit $790M, net income $216M → net margin **11.6%**.
- Revenue FY2021–FY2025: 1,540 / 1,610 / 1,060 (disclosed trough — plant fire) / 1,450 /
  1,790 → natural-window **FY2021–FY2025 CAGR ≈ 3.8%**.
- Grid Storage FY2026E revenue $310M; "$980M by FY2030" implies a ~33% segment CAGR —
  nowhere supported.

## The six planted frauds (one per screen pattern)

| # | Pattern | Fixture section | Planted text (verbatim) | What's wrong | Correct value / required action | Expected reviewer response | Indicative severity + thesis-impact |
|---|---|---|---|---|---|---|---|
| 1 | Stale figure | §5 Valuation | $31.20, the March 2025 52-week high | market cap computed on a 16-month-old price, 25.8% above the header's verified $24.80; §5 even contradicts itself ($3,120M here vs the comps line's $2,480M) | market cap = 100.0M × $24.80 = **$2,480M** | §4 row: Refuted, with the corrected value | CRITICAL · WEAKER · SUBSTANTIAL |
| 2 | Headline-number omission | §5 Valuation | $2,480M market capitalization ÷ $465M | a multiple labeled EV/EBITDA computed off market cap — the $410M net debt stated in §4 was dropped | EV/EBITDA = ($2,480M + $410M) ÷ $465M = **6.2x**; the peer discount is ~30%, not 40% | §4 row: Refuted, with the corrected value | CRITICAL · WEAKER · MATERIAL |
| 3 | Guarantee language | §4 Balance sheet | guaranteed to clear at a sub-7% coupon | certainty about a 2027 refinancing (and "effectively risk-free" equity) with no stated basis — no terms, lender, or market condition | strip the certainty; treat the $620M Nov-2027 maturity as an open financing risk | §4 row: Unsupported; also feeds the §7 calibration verdict (overconfident) | MODERATE · WEAKER · MATERIAL |
| 4 | Base-rate / denominator abuse | §2 Variant view | net income of $216M against gross profit of $790M | a "net margin" computed on gross profit instead of revenue — overstated 2.35× | net margin = $216M ÷ $1,860M = **11.6%**, not 27.3% | §4 row: Refuted, with the corrected value | CRITICAL · WEAKER · SUBSTANTIAL |
| 5 | Cherry-picked window | §1 Executive summary | revenue CAGR of 30.0% (FY2023–FY2025) | the window is anchored at the disclosed FY2023 plant-fire trough (the fixture's own table footnotes it); the arithmetic is right — the window is the lie | natural window FY2021–FY2025 CAGR ≈ **3.8%** | §4 row: Refuted or Unsupported — the mechanism (trough-anchoring) plus the natural-window recomputation is what counts | CRITICAL · WEAKER · SUBSTANTIAL |
| 6 | Projection as fact | §1 Executive summary | will reach $980M by FY2030 | a ~33% CAGR forecast asserted as fact with zero stated assumptions (contrast the correctly labeled FY2027 forecast in §5) | label it a forecast and attach its drivers, or remove it | §4 row: Unsupported; also feeds the §7 calibration verdict | MODERATE · WEAKER · MATERIAL |

Severity and thesis-impact tokens are indicative, not gating: reasonable reviewers may
differ by one level; the catch is what is scored (see Scoring). Note that frauds 1, 2, 4,
and 5 are repeated in compressed form in §8 (Recommendation) — the BUY rests on them, so
catching them changes the decision.

## The two clean controls (must NOT be flagged as frauds)

| Control | Fixture section | Text | Why it is clean |
|---|---|---|---|
| A | §4 Capital returns | a 5.0% yield on the current $24.80 price | correct arithmetic on the correct base, shown inline ($1.24 ÷ $24.80 = 5.0%) |
| B | §5 Valuation | [FORECAST] FY2027 revenue of $1,953M | a projection done right: labeled, assumptions attached (5.0% growth on FY2026E $1,860M), arithmetic exact |

## Scoring

- A **catch** = the review identifies the planted text (verbatim quote or unambiguous
  reference) AND the mechanism (stale vintage / omitted net debt / no basis / wrong
  denominator / trough-anchored window / unlabeled forecast). Severity wording may differ.
- **PASS ≥ 5/6 catches · MARGINAL 4/6 · FAIL ≤ 3/6.**
- Flagging control A or B as a fraud is a **precision miss**: record it; it does not gate
  the pass/fail, but two precision misses make a PASS suspect.
- Expected landing spots (per the reviewer's own output contract): frauds 1, 2, 4, 5 as
  claim-verification rows (§4) with corrected values; frauds 3 and 6 as §4 rows
  (Unsupported) that also move the §7 calibration verdict toward "overconfident".
- **This is a smoke test, not a benchmark**: one fixture, synthetic figures, and (for live
  runs) an LLM-scored review. It answers "does the reviewer catch planted money-figure
  frauds at all?", nothing finer.
