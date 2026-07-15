"""
cost_of_capital.py
==================
Damodaran-aligned cost-of-capital toolkit (numpy only, no network).

Source: Aswath Damodaran, *Investment Valuation*, 3rd ed. (Wiley).
        Chapters 4, 7, 8.  Page anchors follow printed-page / PDF-page convention
        where PDF offset = printed + 19.

Orchestrator import pattern:
    from cost_of_capital import (
        unlever_beta, relever_beta, bottom_up_beta,
        cost_of_equity, synthetic_rating,
        cost_of_debt_after_tax, wacc, implied_erp,
    )
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 1.  Beta functions
# ---------------------------------------------------------------------------

def unlever_beta(levered_beta: float, de_ratio: float, tax_rate: float) -> float:
    """
    Remove financial leverage from an observed (levered) beta.

    Formula [printed p.197 / PDF p.216]:
        β_unlevered = β_levered / [1 + (1 − t) · (D/E)]

    Parameters
    ----------
    levered_beta : float
        Observed regression or market beta (includes leverage).
    de_ratio : float
        Market-value debt-to-equity ratio (e.g. 0.40 for 40 %).
    tax_rate : float
        Marginal corporate tax rate (e.g. 0.30 for 30 %).

    Returns
    -------
    float
        Unlevered (asset) beta.

    Raises
    ------
    ValueError
        If any input is negative.
    """
    if levered_beta < 0 or de_ratio < 0 or tax_rate < 0:
        raise ValueError(
            f"unlever_beta: all inputs must be non-negative; got "
            f"levered_beta={levered_beta}, de_ratio={de_ratio}, tax_rate={tax_rate}"
        )
    return levered_beta / (1.0 + (1.0 - tax_rate) * de_ratio)


def relever_beta(unlevered_beta: float, de_ratio: float, tax_rate: float) -> float:
    """
    Re-introduce financial leverage into an unlevered (asset) beta.

    Formula [printed p.197 / PDF p.216]:
        β_levered = β_unlevered · [1 + (1 − t) · (D/E)]

    Parameters
    ----------
    unlevered_beta : float
        Asset (unlevered) beta.
    de_ratio : float
        Target market-value debt-to-equity ratio.
    tax_rate : float
        Marginal corporate tax rate.

    Returns
    -------
    float
        Levered beta at the specified capital structure.

    Raises
    ------
    ValueError
        If any input is negative.
    """
    if unlevered_beta < 0 or de_ratio < 0 or tax_rate < 0:
        raise ValueError(
            f"relever_beta: all inputs must be non-negative; got "
            f"unlevered_beta={unlevered_beta}, de_ratio={de_ratio}, tax_rate={tax_rate}"
        )
    return unlevered_beta * (1.0 + (1.0 - tax_rate) * de_ratio)


def bottom_up_beta(
    peer_betas: List[float],
    peer_de: List[float],
    tax_rate: float,
    firm_de: float,
) -> float:
    """
    Compute a bottom-up (fundamental) beta for a firm by:
      1. Unlevering each peer's beta (simple average).
      2. Averaging the unlevered betas across peers (reduces standard error by √n).
      3. Re-levering to the firm's own D/E ratio.

    Reference [printed p.197-199 / PDF p.216-218]:
        β_u_avg = mean(β_i / [1 + (1−t)(D/E)_i])
        β_firm  = β_u_avg · [1 + (1−t) · (D/E)_firm]

    Note: All peers use the *same* tax_rate supplied here.  If peer-specific
    tax rates are needed, call unlever_beta() per peer and pass the average to
    relever_beta() manually.

    Parameters
    ----------
    peer_betas : list of float
        Levered (regression) betas for comparable firms.
    peer_de : list of float
        Market-value D/E ratios for those same comparable firms.
    tax_rate : float
        Common marginal tax rate applied to unlever/relever.
    firm_de : float
        Target D/E ratio for the firm being valued.

    Returns
    -------
    float
        Firm levered beta re-levered to firm_de.

    Raises
    ------
    ValueError
        If lists have different lengths, are empty, or any value is negative.
    """
    if len(peer_betas) != len(peer_de):
        raise ValueError(
            f"bottom_up_beta: peer_betas (len={len(peer_betas)}) and "
            f"peer_de (len={len(peer_de)}) must have the same length."
        )
    if len(peer_betas) == 0:
        raise ValueError("bottom_up_beta: peer_betas is empty.")
    if tax_rate < 0 or firm_de < 0:
        raise ValueError(
            f"bottom_up_beta: tax_rate and firm_de must be non-negative; "
            f"got tax_rate={tax_rate}, firm_de={firm_de}"
        )
    unlevered = [unlever_beta(b, d, tax_rate) for b, d in zip(peer_betas, peer_de)]
    avg_unlevered = float(np.mean(unlevered))
    return relever_beta(avg_unlevered, firm_de, tax_rate)


# ---------------------------------------------------------------------------
# 2.  Cost of equity (CAPM)
# ---------------------------------------------------------------------------

def cost_of_equity(rf: float, beta: float, erp: float) -> float:
    """
    Capital Asset Pricing Model (CAPM) cost of equity.

    Formula [printed p.65-66 / PDF p.84-85]:
        ke = rf + β · ERP

    Parameters
    ----------
    rf : float
        Risk-free rate (decimal, e.g. 0.04 for 4 %).
    beta : float
        Levered equity beta for the firm.
    erp : float
        Equity risk premium — E(Rm) − rf (decimal).

    Returns
    -------
    float
        Cost of equity (decimal).

    Raises
    ------
    ValueError
        If rf or erp is negative.  (Beta may be negative for short/hedge assets.)
    """
    if rf < 0:
        raise ValueError(f"cost_of_equity: rf must be non-negative; got {rf}")
    if erp < 0:
        raise ValueError(f"cost_of_equity: erp must be non-negative; got {erp}")
    return rf + beta * erp


# ---------------------------------------------------------------------------
# 3.  Synthetic rating (interest-coverage → rating + default spread)
# ---------------------------------------------------------------------------

# Table from [printed p.212 / PDF p.231] — small-cap (market cap < $5 B) version.
# Note: The reference states that large-cap thresholds "shift lower for the same
# rating" but does not supply the large-cap table numerically.  The table below
# is the one explicitly given in the reference text and is the basis for the
# worked WACC example in Section 7.
#
# Each entry: (lower_bound_exclusive, upper_bound_inclusive, rating, spread)
# Coverage > 12.5 → AAA, so upper bound for AAA is +∞.
_SYNTHETIC_RATING_TABLE: List[Tuple[float, float, str, float]] = [
    (12.50,  float("inf"), "AAA",  0.0050),
    ( 9.50,        12.50,  "AA",  0.0065),
    ( 7.50,         9.50,  "A+",  0.0085),
    ( 6.00,         7.50,   "A",  0.0100),
    ( 4.50,         6.00,  "A-",  0.0110),
    ( 3.50,         4.50, "BBB",  0.0160),
    ( 3.00,         3.50,  "BB",  0.0335),
    ( 2.50,         3.00,  "B+",  0.0375),
    ( 2.00,         2.50,   "B",  0.0500),
    ( 1.50,         2.00,  "B-",  0.0525),
    ( 1.25,         1.50, "CCC",  0.0800),
    ( 0.80,         1.25,  "CC",  0.1000),
    ( 0.50,         0.80,   "C",  0.1200),
    (float("-inf"), 0.50,   "D",  0.1500),
]


def synthetic_rating(interest_coverage: float) -> Tuple[str, float]:
    """
    Estimate a synthetic bond rating and default spread from the
    interest-coverage ratio (EBIT / Interest Expense).

    Lookup table [printed p.212 / PDF p.231] — small-cap (market cap < $5 B):

        Coverage > 12.5x  →  AAA, spread 0.50 %
        9.5–12.5x         →  AA,  spread 0.65 %
        7.5–9.5x          →  A+,  spread 0.85 %
        6.0–7.5x          →  A,   spread 1.00 %
        4.5–6.0x          →  A−,  spread 1.10 %
        3.5–4.5x          →  BBB, spread 1.60 %
        3.0–3.5x          →  BB,  spread 3.35 %
        2.5–3.0x          →  B+,  spread 3.75 %
        2.0–2.5x          →  B,   spread 5.00 %
        1.5–2.0x          →  B−,  spread 5.25 %
        1.25–1.5x         →  CCC, spread 8.00 %
        0.8–1.25x         →  CC,  spread 10.00 %
        0.5–0.8x          →  C,   spread 12.00 %
        < 0.5x            →  D,   spread 15.00 %

    Parameters
    ----------
    interest_coverage : float
        EBIT divided by interest expense.

    Returns
    -------
    tuple (rating: str, default_spread: float)
        rating : Moody's/S&P-style letter grade (e.g. "A", "BBB").
        default_spread : Annual default spread in decimal (e.g. 0.0100 for 1.00 %).

    Raises
    ------
    ValueError
        If interest_coverage is NaN.
    """
    if np.isnan(interest_coverage):
        raise ValueError("synthetic_rating: interest_coverage is NaN.")
    for lower, upper, rating, spread in _SYNTHETIC_RATING_TABLE:
        if lower < interest_coverage <= upper:
            return (rating, spread)
    # Fallback for exactly 0.5 edge — covered by D bucket (< 0.5 handled first,
    # but float("-inf") < 0.5 covers ≤ 0.5 after iteration order): unreachable
    # if table is complete, but guard defensively.
    return ("D", 0.1500)


# ---------------------------------------------------------------------------
# 4.  Cost of debt (after-tax)
# ---------------------------------------------------------------------------

def cost_of_debt_after_tax(rf: float, default_spread: float, tax_rate: float) -> float:
    """
    After-tax cost of debt.

    Formula [printed p.213 / PDF p.232]:
        kd_aftertax = (rf + default_spread) · (1 − t_marginal)

    Use the *marginal* tax rate because interest shields taxes at the margin.
    If the firm has net operating losses (no current tax benefit), pass tax_rate=0.

    Parameters
    ----------
    rf : float
        Risk-free rate (decimal).
    default_spread : float
        Default/credit spread for the firm's rating (decimal).
    tax_rate : float
        Marginal corporate tax rate (decimal).

    Returns
    -------
    float
        After-tax cost of debt (decimal).

    Raises
    ------
    ValueError
        If any input is negative.
    """
    if rf < 0 or default_spread < 0 or tax_rate < 0:
        raise ValueError(
            f"cost_of_debt_after_tax: all inputs must be non-negative; got "
            f"rf={rf}, default_spread={default_spread}, tax_rate={tax_rate}"
        )
    return (rf + default_spread) * (1.0 - tax_rate)


# ---------------------------------------------------------------------------
# 5.  WACC
# ---------------------------------------------------------------------------

def wacc(
    ke: float,
    kd_after_tax: float,
    e_val: float,
    d_val: float,
    ps_val: float = 0.0,
    kps: float = 0.0,
) -> float:
    """
    Weighted Average Cost of Capital using market-value weights.

    Formula [printed p.220 / PDF p.239]:
        WACC = ke · [E / V] + kd(1−t) · [D / V] + kps · [PS / V]
        where V = E + D + PS  (all market values)

    Market-value weights are mandatory — never use book values [printed p.220 /
    PDF p.239]:  "The weights on each of these components should reflect their
    market value proportions."

    Parameters
    ----------
    ke : float
        Cost of equity (decimal, already includes beta and ERP).
    kd_after_tax : float
        After-tax cost of debt (decimal).
    e_val : float
        Market value of equity (e.g. market capitalisation).
    d_val : float
        Market value of debt (interest-bearing, including capitalized leases).
        Pass 0.0 for a net-cash / debt-free firm.
    ps_val : float, optional
        Market value of preferred stock. Default 0.0.
    kps : float, optional
        Cost of preferred stock = preferred dividend / preferred price. Default 0.0.

    Returns
    -------
    float
        WACC (decimal).

    Raises
    ------
    ValueError
        If ke, kd_after_tax, e_val, d_val, ps_val, or kps is negative.
        (A net-cash firm may have d_val = 0; that is allowed.)
    """
    for name, val in [
        ("ke", ke), ("kd_after_tax", kd_after_tax),
        ("e_val", e_val), ("d_val", d_val),
        ("ps_val", ps_val), ("kps", kps),
    ]:
        if val < 0:
            raise ValueError(
                f"wacc: '{name}' must be non-negative (net-cash firms use d_val=0); "
                f"got {name}={val}"
            )
    total = e_val + d_val + ps_val
    if total <= 0:
        raise ValueError(
            f"wacc: total market value (E+D+PS) must be > 0; got {total}"
        )
    w_e  = e_val  / total
    w_d  = d_val  / total
    w_ps = ps_val / total
    return ke * w_e + kd_after_tax * w_d + kps * w_ps


# ---------------------------------------------------------------------------
# 6.  Implied ERP (iterative / numerical)
# ---------------------------------------------------------------------------

def implied_erp(
    index_level: float,
    base_cashflow: float,
    growth_rates: List[float],
    terminal_growth: float,
    rf: float,
) -> float:
    """
    Back-solve the implied equity risk premium (ERP) from current index level
    and projected cash flows using a two-stage dividend discount model.

    Model [printed p.172-174 / PDF p.191-193]:
        index_level = Σ[t=1..N] CF_t / (1+r)^t  +  TV / (1+r)^N

    where:
        CF_t = base_cashflow · Π[i=1..t] (1 + growth_rates[i-1])
        TV   = CF_N · (1 + terminal_growth) / (r − terminal_growth)
        N    = len(growth_rates)

    Solve for r using bisection on the interval (terminal_growth, 0.50).
    Then:
        ERP = r − rf

    Parameters
    ----------
    index_level : float
        Current index or stock price (e.g. S&P 500 level).
    base_cashflow : float
        Cash flow at t=0 (dividends + buybacks per index unit) before any growth.
    growth_rates : list of float
        Per-year growth rates for the explicit forecast period.
        e.g. [0.0695, 0.0695, 0.0695, 0.0695, 0.0695] for 5 years at 6.95 %.
        Must be a non-empty list.
    terminal_growth : float
        Stable / perpetuity growth rate after the explicit period (≈ rf per
        Damodaran's convention).
    rf : float
        Risk-free rate (decimal).

    Returns
    -------
    float
        Implied ERP = r − rf (decimal).

    Raises
    ------
    ValueError
        If any input is negative (except growth_rates which may be any real),
        if terminal_growth >= upper bisection bound, or if the solver fails
        to bracket or converge.
    """
    if index_level <= 0:
        raise ValueError(f"implied_erp: index_level must be > 0; got {index_level}")
    if base_cashflow < 0:
        raise ValueError(f"implied_erp: base_cashflow must be non-negative; got {base_cashflow}")
    if rf < 0:
        raise ValueError(f"implied_erp: rf must be non-negative; got {rf}")
    if len(growth_rates) == 0:
        raise ValueError("implied_erp: growth_rates must be a non-empty list.")
    if terminal_growth >= 0.50:
        raise ValueError(
            f"implied_erp: terminal_growth must be < 0.50; got {terminal_growth}"
        )

    n = len(growth_rates)

    # Build cash flow array CF[1..N]
    cfs = np.empty(n)
    cf = float(base_cashflow)
    for i, g in enumerate(growth_rates):
        cf *= (1.0 + g)
        cfs[i] = cf

    cf_n = cfs[-1]  # CF at end of explicit period

    def pv_minus_index(r: float) -> float:
        """PV of all cash flows at discount rate r, minus the index level."""
        if r <= terminal_growth:
            return float("inf")
        t_exponents = np.arange(1, n + 1, dtype=float)
        pv_explicit = float(np.sum(cfs / (1.0 + r) ** t_exponents))
        tv = cf_n * (1.0 + terminal_growth) / (r - terminal_growth)
        pv_tv = tv / (1.0 + r) ** n
        return pv_explicit + pv_tv - index_level

    # Bisection bounds: r ∈ (terminal_growth + ε, 0.50)
    lo = terminal_growth + 1e-6
    hi = 0.50

    f_lo = pv_minus_index(lo)
    f_hi = pv_minus_index(hi)

    if f_lo * f_hi > 0:
        raise ValueError(
            f"implied_erp: could not bracket root. f(lo={lo:.6f})={f_lo:.4f}, "
            f"f(hi={hi:.6f})={f_hi:.4f}. Check inputs."
        )

    # Bisection — 60 iterations gives precision < 2^-60 ≈ 8.7e-19
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = pv_minus_index(mid)
        if abs(f_mid) < 1e-10 or (hi - lo) < 1e-12:
            lo = mid
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo = mid
            f_lo = f_mid

    r_implied = 0.5 * (lo + hi)
    return r_implied - rf


# ---------------------------------------------------------------------------
# 7.  CLI
# ---------------------------------------------------------------------------

def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost_of_capital",
        description="Damodaran cost-of-capital toolkit (Wiley Investment Valuation, 3rd ed.)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- wacc ---------------------------------------------------------------
    p_wacc = sub.add_parser(
        "wacc",
        help="Compute WACC given cost of equity, after-tax cost of debt, and market values.",
    )
    p_wacc.add_argument("--ke",  type=float, required=True,
                         help="Cost of equity as decimal (e.g. 0.0975 for 9.75 %%)")
    p_wacc.add_argument("--kd",  type=float, required=True,
                         help="After-tax cost of debt as decimal")
    p_wacc.add_argument("--tax", type=float, required=False, default=0.0,
                         help="Tax rate (ignored if --kd is already after-tax; default 0)")
    p_wacc.add_argument("--e",   type=float, required=True,
                         help="Market value of equity")
    p_wacc.add_argument("--d",   type=float, required=True,
                         help="Market value of debt (0 for net-cash firms)")
    p_wacc.add_argument("--ps",  type=float, default=0.0,
                         help="Market value of preferred stock (default 0)")
    p_wacc.add_argument("--kps", type=float, default=0.0,
                         help="Cost of preferred stock (default 0)")

    # ---- beta ---------------------------------------------------------------
    p_beta = sub.add_parser(
        "beta",
        help="Bottom-up beta: unlever peers, average, relever to firm D/E.",
    )
    p_beta.add_argument("--peer-betas", required=True,
                         help='Comma-separated levered betas for peers, e.g. "1.1,0.9"')
    p_beta.add_argument("--peer-de", required=True,
                         help='Comma-separated D/E ratios for peers, e.g. "0.3,0.5"')
    p_beta.add_argument("--tax",     type=float, required=True,
                         help="Common marginal tax rate (decimal)")
    p_beta.add_argument("--firm-de", type=float, required=True,
                         help="Firm's target D/E ratio (decimal)")

    # ---- selftest -----------------------------------------------------------
    sub.add_parser("selftest", help="Run built-in assertion suite; exits 0 if all pass.")

    return parser


def _run_selftest() -> int:
    """
    Reproduce the worked examples from the reference document
    (cost_of_capital.md, Sections 4, 7, 3.2) and a round-trip beta check.

    Returns 0 if all checks pass, 1 otherwise.
    """
    results: List[Tuple[str, bool, str]] = []  # (label, passed, detail)

    def check(label: str, got: float, expected: float, tol: float) -> None:
        pct_err = abs(got - expected) / abs(expected) if expected != 0 else abs(got)
        passed = pct_err <= tol
        results.append((
            label,
            passed,
            f"got={got:.6f}  expected≈{expected:.6f}  "
            f"err={pct_err*100:.4f}%  tol={tol*100:.2f}%",
        ))

    # ------------------------------------------------------------------
    # Check 1 — Unlever beta (Section 4, worked example)
    # Vans: β_levered=0.79, D/E=0.7504, t=0.2595 → β_u≈0.5081
    # ------------------------------------------------------------------
    bu_vans = unlever_beta(0.79, 0.7504, 0.2595)
    check("Unlever beta (Vans example)", bu_vans, 0.5081, 0.002)

    # ------------------------------------------------------------------
    # Check 2 — Relever beta (Vans): β_u=0.5081, D/E=0.0941, t=0.3406 → 0.5397
    # ------------------------------------------------------------------
    bl_vans = relever_beta(0.5081, 0.0941, 0.3406)
    check("Relever beta (Vans example)", bl_vans, 0.5397, 0.002)

    # ------------------------------------------------------------------
    # Check 3 — Round-trip: unlever then relever at same D/E and t must
    # recover the original levered beta.
    # ------------------------------------------------------------------
    orig_beta = 1.20
    bu_rt = unlever_beta(orig_beta, 0.40, 0.30)
    bl_rt = relever_beta(bu_rt, 0.40, 0.30)
    rt_err = abs(bl_rt - orig_beta)
    rt_ok = rt_err < 1e-10
    results.append((
        "Unlever→relever round-trip",
        rt_ok,
        f"got={bl_rt:.10f}  expected={orig_beta:.10f}  abs_err={rt_err:.2e}",
    ))

    # ------------------------------------------------------------------
    # Check 4–7 — WACC worked example (Section 7, target ≈ 8.52%)
    # rf=4%, comp_beta=1.20, comp_D/E=40%, comp_t=30%,
    # firm_D/E=25%, firm_t=28%, ERP=5.2%,
    # spread(A, 5.8x)=1.00%  → WACC ≈ 8.52%
    # ------------------------------------------------------------------
    # Step 1: unlever
    bu_wacc = unlever_beta(1.20, 0.40, 0.30)
    check("WACC: β_unlevered (step 1)", bu_wacc, 0.9375, 0.001)

    # Step 2: relever
    bl_wacc = relever_beta(bu_wacc, 0.25, 0.28)
    check("WACC: β_levered (step 2)", bl_wacc, 1.1063, 0.002)

    # Step 3: ke
    ke_val = cost_of_equity(0.04, bl_wacc, 0.052)
    check("WACC: ke (step 3)", ke_val, 0.09753, 0.002)

    # Step 4: synthetic rating at 5.8x → A (spread=1.00%)
    rating, spread = synthetic_rating(5.8)
    rating_ok = (rating == "A-")
    results.append((
        "Synthetic rating at 5.8x coverage",
        rating_ok,
        f"got=({rating!r}, {spread:.4f})  expected=('A-', 0.0110)  "
        f"[note: 5.8x falls in 4.5–6.0x bucket = A−]",
    ))

    # Step 4b: after-tax kd
    kd_val = cost_of_debt_after_tax(0.04, spread, 0.28)

    # NOTE: The worked example in the reference document uses spread=1.00%
    # (A rating, 6.0-7.5x bucket) because the document states "5.8x → A rating"
    # in the table header.  However, per the actual table, 5.8x (4.5–6.0x) maps
    # to A− with spread=1.10%.  We reproduce the reference's *stated* WACC of
    # 8.52% by using the spread the reference explicitly specifies (1.00%=A).
    # The discrepancy is a known inconsistency in the reference document between
    # the worked-example narrative and the lookup table.
    kd_ref = cost_of_debt_after_tax(0.04, 0.0100, 0.28)  # reference uses A spread
    check("WACC: kd_aftertax (step 4, ref spread=1.00%)", kd_ref, 0.0360, 0.001)

    # Step 5: weights (D/E=25% → E=80%, D=20%)
    # Use e_val=80, d_val=20 (unit-agnostic market values)
    wacc_val = wacc(ke_val, kd_ref, 80.0, 20.0)
    check("WACC: final WACC (target ≈ 8.52%)", wacc_val, 0.0852, 0.002)

    # ------------------------------------------------------------------
    # Check: Implied ERP (Section 3.2, target ≈ 5.20%)
    # S&P 500 = 1,257.64, CF0 = 53.96, g = 6.95% for 5 years,
    # terminal_growth = 3.29%, rf = 3.29%
    # ------------------------------------------------------------------
    erp_val = implied_erp(
        index_level=1257.64,
        base_cashflow=53.96,
        growth_rates=[0.0695] * 5,
        terminal_growth=0.0329,
        rf=0.0329,
    )
    check("Implied ERP (Section 3.2, target ≈ 5.20%)", erp_val, 0.0520, 0.003)

    # ------------------------------------------------------------------
    # Print results
    # ------------------------------------------------------------------
    all_pass = True
    print("=" * 68)
    print("cost_of_capital.py — SELFTEST")
    print("=" * 68)
    for label, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"[{status}] {label}")
        print(f"       {detail}")
    print("=" * 68)
    if all_pass:
        print("ALL CHECKS PASSED")
    else:
        n_fail = sum(1 for _, p, _ in results if not p)
        print(f"{n_fail} CHECK(S) FAILED")
    print("=" * 68)
    return 0 if all_pass else 1


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    if args.command == "selftest":
        sys.exit(_run_selftest())

    elif args.command == "wacc":
        result = wacc(
            ke=args.ke,
            kd_after_tax=args.kd,
            e_val=args.e,
            d_val=args.d,
            ps_val=args.ps,
            kps=args.kps,
        )
        print(f"WACC = {result*100:.4f}%")

    elif args.command == "beta":
        peer_betas = [float(x) for x in args.peer_betas.split(",")]
        peer_de    = [float(x) for x in args.peer_de.split(",")]
        result = bottom_up_beta(peer_betas, peer_de, args.tax, args.firm_de)
        print(f"Bottom-up beta (relevered) = {result:.4f}")


if __name__ == "__main__":
    main()
