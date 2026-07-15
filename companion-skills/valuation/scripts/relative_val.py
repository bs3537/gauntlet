"""
relative_val.py — Relative Valuation Toolkit
=============================================
Implements determinant-formula multiples derived from Damodaran,
*Investment Valuation* (3rd ed.), Chapters 17–20.

All functions use stable-growth closed-form expressions unless
otherwise noted.  No network access required.

Usage
-----
    python3 relative_val.py pe --g 0.04 --roe 0.15 --ke 0.09
    python3 relative_val.py peers --target-ebitda 500 --peer-multiples "8,9,11,40"
    python3 relative_val.py selftest
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

import numpy as np


# ---------------------------------------------------------------------------
# 1. P/E  [Ch.18, printed p.468–486 / PDF p.487–505]
# ---------------------------------------------------------------------------

def forward_pe_from_fundamentals(g: float, roe: float, ke: float) -> float:
    """
    Stable-growth forward P/E from DDM fundamentals.

    Derivation [Ch.18, printed p.472 / PDF p.491]:
        P/EPS1 = Payout / (ke − g),  Payout = 1 − g/ROE
        → Forward PE = (1 − g/ROE) / (ke − g)

    Parameters
    ----------
    g   : expected stable growth rate (decimal, e.g. 0.08)
    roe : return on equity in stable growth (decimal, e.g. 0.16)
    ke  : cost of equity (decimal, e.g. 0.115)

    Returns
    -------
    float — forward P/E multiple (×)

    Raises
    ------
    ValueError  if ke <= g (Gordon model collapses)
    ZeroDivisionError if roe == 0
    """
    if ke <= g:
        raise ValueError(f"ke ({ke}) must exceed g ({g}) for stable-growth model.")
    payout = 1.0 - g / roe
    return payout / (ke - g)


def trailing_pe_from_fundamentals(g: float, roe: float, ke: float) -> float:
    """
    Stable-growth trailing P/E from DDM fundamentals.

    Derivation [Ch.18, printed p.472 / PDF p.491]:
        Trailing PE = P/EPS0 = P/EPS1 × (1+g)
                    = (1+g)(1 − g/ROE) / (ke − g)

    Parameters
    ----------
    g   : expected stable growth rate (decimal)
    roe : return on equity in stable growth (decimal)
    ke  : cost of equity (decimal)

    Returns
    -------
    float — trailing P/E multiple (×)
    """
    return (1.0 + g) * forward_pe_from_fundamentals(g, roe, ke)


# ---------------------------------------------------------------------------
# 2. PEG  [Ch.18, printed p.487–491 / PDF p.506–510]
# ---------------------------------------------------------------------------

def fair_peg(g: float, roe: float, ke: float) -> float:
    """
    Fair PEG ratio implied by fundamentals.

    Definition [Ch.18, printed p.491 / PDF p.510]:
        PEG = Forward PE / g_pct,  where g_pct = g × 100

    This is equivalent to:
        PEG = Forward PE / (100 × g)

    A PEG of 1 is the conventional "fair value" baseline.
    PEG is NOT growth-neutral; it decreases with risk and is
    non-monotone in g.

    Parameters
    ----------
    g   : expected growth rate (decimal, e.g. 0.25)
    roe : return on equity (decimal)
    ke  : cost of equity (decimal)

    Returns
    -------
    float — PEG ratio
    """
    fpe = forward_pe_from_fundamentals(g, roe, ke)
    g_pct = 100.0 * g          # convert to percentage form per PEG convention
    return fpe / g_pct


# ---------------------------------------------------------------------------
# 3. P/B  [Ch.19, printed p.515 / PDF p.534]
# ---------------------------------------------------------------------------

def pb_from_roe(roe: float, ke: float, g: float) -> float:
    """
    Stable-growth Price-to-Book ratio from ROE and cost of equity.

    Derivation [Ch.19, printed p.515 / PDF p.534]:
        P/BV = ROE × Payout / (ke − g),  Payout = 1 − g/ROE
             = (ROE − g) / (ke − g)

    Key insight: P/B > 1 iff ROE > ke (value-creation test).

    Parameters
    ----------
    roe : return on equity (decimal)
    ke  : cost of equity (decimal)
    g   : stable growth rate (decimal)

    Returns
    -------
    float — P/B multiple (×)
    """
    if ke <= g:
        raise ValueError(f"ke ({ke}) must exceed g ({g}) for stable-growth model.")
    return (roe - g) / (ke - g)


# ---------------------------------------------------------------------------
# 4. P/S  [Ch.20, printed p.544–545 / PDF p.563–564]
# ---------------------------------------------------------------------------

def ps_from_margin(
    net_margin: float,
    payout: float,
    ke: float,
    g: float,
) -> float:
    """
    Stable-growth Price-to-Sales ratio from net margin.

    Derivation [Ch.20, printed p.544 / PDF p.563]:
        P/S = net_margin × payout × (1+g) / (ke − g)

    Net margin is the dominant driver; a firm with structurally
    negative margin cannot sustain a positive P/S multiple.

    Parameters
    ----------
    net_margin : net profit margin (decimal, e.g. 0.10)
    payout     : dividend payout ratio (decimal, e.g. 0.50)
    ke         : cost of equity (decimal)
    g          : stable growth rate (decimal)

    Returns
    -------
    float — P/S multiple (×)
    """
    if ke <= g:
        raise ValueError(f"ke ({ke}) must exceed g ({g}) for stable-growth model.")
    return net_margin * payout * (1.0 + g) / (ke - g)


# ---------------------------------------------------------------------------
# 5. EV/EBITDA  [Ch.18, printed p.503–504 / PDF p.522–523]
# ---------------------------------------------------------------------------

def ev_ebitda_implied(
    tax: float,
    da_pct: float,
    reinvest_pct: float,
    wacc: float,
    g: float,
) -> float:
    """
    Stable-growth EV/EBITDA multiple from FCFF-derived determinants.

    Derivation [Ch.18, printed p.503–504 / PDF p.522–523]:
        EV  = FCFF1 / (WACC − g)
        FCFF = EBITDA(1−t) − DA(1−t) − Reinvestment
        → EV/EBITDA = [(1−t) − da_pct(1−t) − reinvest_pct] / (WACC − g)

    Note: DA/EBITDA carries the (1−t) tax shield because depreciation
    reduces taxable income; net reinvestment (net capex / EBITDA) does
    not carry an additional tax factor as it is already an after-FCFF
    deduction.

    Micro-example (Castillo Cable) [printed p.504–506 / PDF p.523–525]:
        WACC=10%, t=36%, DA/EBITDA=20%, Capex/EBITDA=45%, g=5%
        reinvest_pct = 0.45 − 0.20 = 0.25
        EV/EBITDA = [0.64 − 0.128 − 0.25] / 0.05 = 0.262/0.05 = 5.24×

    Parameters
    ----------
    tax          : effective tax rate (decimal, e.g. 0.36)
    da_pct       : depreciation & amortisation / EBITDA (decimal, e.g. 0.20)
    reinvest_pct : net reinvestment (net capex) / EBITDA (decimal, e.g. 0.25)
    wacc         : weighted average cost of capital (decimal)
    g            : stable growth rate (decimal)

    Returns
    -------
    float — EV/EBITDA multiple (×)
    """
    if wacc <= g:
        raise ValueError(f"wacc ({wacc}) must exceed g ({g}) for stable-growth model.")
    numerator = (1.0 - tax) - da_pct * (1.0 - tax) - reinvest_pct
    return numerator / (wacc - g)


# ---------------------------------------------------------------------------
# 6. Peer-implied value  [Ch.17, printed p.456–467 / PDF p.475–486]
# ---------------------------------------------------------------------------

def peer_implied_value(
    target_metric_value: float,
    peer_multiples: list[float],
    stat: str = "median",
    exclude_outliers: bool = False,
) -> dict:
    """
    Derive implied value for a target firm from a peer multiple distribution.

    Follows Damodaran's Step 2 (describe cross-sectional distribution)
    and Step 4 (control for outliers) [Ch.17, printed p.456–467 / PDF p.475–486].

    Outlier detection uses Tukey's 1.5×IQR fence on the peer multiples.
    The central estimate uses the requested `stat` (default: median,
    which is preferred over mean for positively-skewed multiples per p.456).

    Parameters
    ----------
    target_metric_value : the target's metric (e.g. EBITDA = 500)
    peer_multiples      : list of multiples from comparable firms
    stat                : "median" (default) or "mean"
    exclude_outliers    : if True, DROP Tukey-fence outliers from the central
                          multiple and the 25/75 range before computing implied
                          values (result then reports outliers_excluded=True).
                          If False (default) every peer is used and outliers are
                          returned for flagging only — nothing is silently
                          excluded, so callers must not claim otherwise. [D8]

    Returns
    -------
    dict with keys:
        multiple_used     : float — central multiple (median or mean)
        implied_value     : float — target_metric_value × multiple_used
        low               : float — implied value at 25th-percentile multiple
        high              : float — implied value at 75th-percentile multiple
        outliers          : list[int] — indices outside the Tukey fence
        outliers_excluded : bool — whether outliers were dropped from the stats
    """
    arr = np.array(peer_multiples, dtype=float)
    n = len(arr)

    # Tukey IQR fence for outlier detection
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outlier_indices = [
        i for i, v in enumerate(arr) if v < lower_fence or v > upper_fence
    ]

    # Statistics are computed on stat_arr. Exclusion only takes effect when it
    # is requested AND leaves at least one peer; otherwise all peers are used and
    # the outlier list is purely informational (no silent exclusion). [report D8]
    did_exclude = bool(exclude_outliers and outlier_indices and len(outlier_indices) < n)
    if did_exclude:
        stat_arr = np.array([v for i, v in enumerate(arr) if i not in outlier_indices])
    else:
        stat_arr = arr

    if stat == "median":
        central = float(np.median(stat_arr))
    elif stat == "mean":
        central = float(np.mean(stat_arr))
    else:
        raise ValueError(f"stat must be 'median' or 'mean', got '{stat}'")

    # 25th / 75th percentile range for implied value
    low_mult  = float(np.percentile(stat_arr, 25))
    high_mult = float(np.percentile(stat_arr, 75))

    return {
        "multiple_used": central,
        "implied_value": target_metric_value * central,
        "low":           target_metric_value * low_mult,
        "high":          target_metric_value * high_mult,
        "outliers":      outlier_indices,
        "outliers_excluded": did_exclude,
    }


# ---------------------------------------------------------------------------
# 7. Regression multiple  [Ch.17–18, printed p.481–486 / PDF p.500–505]
# ---------------------------------------------------------------------------

def regression_multiple(
    fundamentals_matrix: list[list[float]],
    multiples_vector: list[float],
) -> dict:
    """
    Fit a least-squares regression of a multiple on fundamental drivers.

    Method [Ch.17, printed p.484–486 / PDF p.503–505]:
        multiple = a + b1*x1 + b2*x2 + ... + error

    Uses numpy.polyfit for simple (1-predictor) cases and
    numpy.linalg.lstsq for the multivariate case.

    Parameters
    ----------
    fundamentals_matrix : shape (N, K) — N observations, K predictors
                          (e.g. [[growth, beta, payout], ...])
    multiples_vector    : shape (N,) — observed multiples (e.g. PE values)

    Returns
    -------
    dict with keys:
        coef      : list[float] — regression coefficients [b1, ..., bK]
        intercept : float — regression intercept (a)
        predict   : Callable[[list[float]], float]
                    — predict(x) returns fitted multiple for a new
                      observation x (length K list)
        r_squared : float — coefficient of determination on training data
    """
    X = np.array(fundamentals_matrix, dtype=float)
    y = np.array(multiples_vector, dtype=float)
    N, K = X.shape

    # Augment X with a column of ones for the intercept
    X_aug = np.hstack([np.ones((N, 1)), X])   # shape (N, K+1)

    # Least-squares solution via numpy (no scipy dependency)
    result, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    intercept = float(result[0])
    coef      = [float(c) for c in result[1:]]

    # R-squared on training data
    y_hat   = X_aug @ result
    ss_res  = float(np.sum((y - y_hat) ** 2))
    ss_tot  = float(np.sum((y - np.mean(y)) ** 2))
    r_sq    = 1.0 - ss_res / ss_tot if ss_tot != 0.0 else 0.0

    # Closure over fitted coefficients
    _intercept = intercept
    _coef      = coef

    def predict(x: list[float]) -> float:
        """Return fitted multiple for predictor vector x (length K)."""
        xv = np.array(x, dtype=float)
        return float(_intercept + np.dot(_coef, xv))

    return {
        "coef":      coef,
        "intercept": intercept,
        "predict":   predict,
        "r_squared": r_sq,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relative_val",
        description="Relative valuation toolkit (Damodaran Ch.17–20).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- pe subcommand ---
    pe_p = sub.add_parser("pe", help="Forward & trailing PE from fundamentals.")
    pe_p.add_argument("--g",   type=float, required=True, help="Growth rate (decimal)")
    pe_p.add_argument("--roe", type=float, required=True, help="ROE (decimal)")
    pe_p.add_argument("--ke",  type=float, required=True, help="Cost of equity (decimal)")

    # --- peers subcommand ---
    peers_p = sub.add_parser("peers", help="Peer-implied EV with outlier detection.")
    peers_p.add_argument(
        "--target-ebitda", type=float, required=True,
        dest="target_ebitda", help="Target firm EBITDA (e.g. 500)"
    )
    peers_p.add_argument(
        "--peer-multiples", type=str, required=True,
        dest="peer_multiples", help="Comma-separated EV/EBITDA multiples (e.g. '8,9,11,40')"
    )

    # --- selftest subcommand ---
    sub.add_parser("selftest", help="Run built-in correctness checks.")

    return parser


def _cmd_pe(args: argparse.Namespace) -> None:
    fpe = forward_pe_from_fundamentals(args.g, args.roe, args.ke)
    tpe = trailing_pe_from_fundamentals(args.g, args.roe, args.ke)
    peg = fair_peg(args.g, args.roe, args.ke)
    print(f"Forward  PE : {fpe:.4f}×")
    print(f"Trailing PE : {tpe:.4f}×")
    print(f"Fair PEG    : {peg:.4f}")


def _cmd_peers(args: argparse.Namespace) -> None:
    raw = [float(x.strip()) for x in args.peer_multiples.split(",")]
    result = peer_implied_value(args.target_ebitda, raw)
    print(f"Peer multiples   : {raw}")
    print(f"Median multiple  : {result['multiple_used']:.2f}×")
    print(f"Implied EV       : {result['implied_value']:,.0f}")
    print(f"Range (25–75th%) : {result['low']:,.0f} – {result['high']:,.0f}")
    if result["outliers"]:
        flagged = [(i, raw[i]) for i in result["outliers"]]
        print(f"Outliers (1.5×IQR fence): {flagged}  ← flagged")
    else:
        print("Outliers: none")


def _cmd_selftest() -> None:
    """
    Selftest suite — prints PASS/FAIL per check, exits 0 only if all pass.

    Checks
    ------
    (a) forward_pe_from_fundamentals with stable-growth inputs from
        the reference PE micro-example [Ch.18, printed p.472 / PDF p.491]:
        stable phase: g=0.08, payout_stable=0.50 → ROE_stable=0.08/0.50=0.16,
        ke=0.115.
        Expected: (1 − 0.08/0.16) / (0.115 − 0.08) = 0.5 / 0.035 = 14.2857×

    (b) pb_from_roe(roe=0.20, ke=0.10, g=0.04)
        [Ch.19, printed p.515 / PDF p.534]
        Expected: (0.20 − 0.04) / (0.10 − 0.04) = 0.16 / 0.06 = 2.6667×

    (c) peer_implied_value(500, [8, 9, 11, 40])
        [Ch.17, printed p.456 / PDF p.475]
        Median of [8,9,11,40] = (9+11)/2 = 10 → implied EV = 5000
        Tukey fence: Q1=8.5, Q3=14.0, IQR=5.5,
                     upper fence=14+8.25=22.25 → index 3 (40×) is outlier.

    (d) fair_peg(g=0.25, roe=0.3125, ke=0.115) > 0
        [Ch.18, printed p.491 / PDF p.510]
        ROE_hg = g/(1−payout_hg) = 0.25/0.80 = 0.3125
        Forward PE = (1−0.25/0.3125)/(0.115−0.25) → negative ke-g:
        ke=0.115 < g=0.25 in high-growth phase, so high-growth stable-form
        is ill-defined.  Use reference's stable-phase numbers instead:
        g=0.08, roe=0.16, ke=0.115 → PEG = 14.2857 / (100×0.08) = 1.7857 > 0.

    (e) ev_ebitda_implied with Castillo Cable numbers
        [Ch.18, printed p.504–506 / PDF p.523–525]
        tax=0.36, da_pct=0.20, reinvest_pct=0.25, wacc=0.10, g=0.05
        Expected: [(1−0.36)−0.20(1−0.36)−0.25]/(0.10−0.05)
                = [0.64−0.128−0.25]/0.05 = 0.262/0.05 = 5.24×
    """
    TOL = 1e-3
    failures: list[str] = []

    # (a) Forward PE — stable-growth phase from reference micro-example
    g_a, roe_a, ke_a = 0.08, 0.16, 0.115
    expected_a = 0.5 / 0.035   # = 14.285714...
    got_a = forward_pe_from_fundamentals(g_a, roe_a, ke_a)
    ok_a  = abs(got_a - expected_a) <= TOL
    tag_a = "PASS" if ok_a else "FAIL"
    print(
        f"[{tag_a}] (a) forward_pe_from_fundamentals"
        f"(g={g_a}, roe={roe_a}, ke={ke_a})"
        f" = {got_a:.6f}, expected {expected_a:.6f}"
    )
    if not ok_a:
        failures.append("(a) forward_pe_from_fundamentals")

    # (b) P/B from ROE
    roe_b, ke_b, g_b = 0.20, 0.10, 0.04
    expected_b = 0.16 / 0.06   # = 2.666...
    got_b = pb_from_roe(roe_b, ke_b, g_b)
    ok_b  = abs(got_b - expected_b) <= TOL
    tag_b = "PASS" if ok_b else "FAIL"
    print(
        f"[{tag_b}] (b) pb_from_roe"
        f"(roe={roe_b}, ke={ke_b}, g={g_b})"
        f" = {got_b:.6f}, expected {expected_b:.6f}"
    )
    if not ok_b:
        failures.append("(b) pb_from_roe")

    # (c) peer_implied_value — median, outlier at index 3
    got_c = peer_implied_value(500.0, [8.0, 9.0, 11.0, 40.0])
    median_c    = got_c["multiple_used"]
    implied_c   = got_c["implied_value"]
    outliers_c  = got_c["outliers"]

    ok_c_med = abs(median_c - 10.0) <= TOL
    ok_c_ev  = abs(implied_c - 5000.0) <= 1.0
    ok_c_out = 3 in outliers_c

    ok_c = ok_c_med and ok_c_ev and ok_c_out
    tag_c = "PASS" if ok_c else "FAIL"
    print(
        f"[{tag_c}] (c) peer_implied_value"
        f" → median={median_c:.2f}× (want 10.00), "
        f"implied_EV={implied_c:,.0f} (want 5,000), "
        f"outliers={outliers_c} (want [3])"
    )
    if not ok_c:
        failures.append("(c) peer_implied_value")

    # (d) fair_peg > 0  (using stable-phase numbers: g=0.08, roe=0.16, ke=0.115)
    g_d, roe_d, ke_d = 0.08, 0.16, 0.115
    got_d = fair_peg(g_d, roe_d, ke_d)
    ok_d  = got_d > 0.0
    tag_d = "PASS" if ok_d else "FAIL"
    print(
        f"[{tag_d}] (d) fair_peg"
        f"(g={g_d}, roe={roe_d}, ke={ke_d})"
        f" = {got_d:.6f} (want > 0)"
    )
    if not ok_d:
        failures.append("(d) fair_peg")

    # (e) EV/EBITDA — Castillo Cable
    expected_e = 5.24
    got_e = ev_ebitda_implied(
        tax=0.36, da_pct=0.20, reinvest_pct=0.25, wacc=0.10, g=0.05
    )
    ok_e  = abs(got_e - expected_e) <= TOL
    tag_e = "PASS" if ok_e else "FAIL"
    print(
        f"[{tag_e}] (e) ev_ebitda_implied (Castillo Cable)"
        f" = {got_e:.6f}, expected {expected_e:.6f}"
    )
    if not ok_e:
        failures.append("(e) ev_ebitda_implied")

    # Summary
    print()
    if failures:
        print(f"SELFTEST FAILED — {len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    else:
        print("SELFTEST PASSED — all 5 checks OK")
        sys.exit(0)


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.command == "pe":
        _cmd_pe(args)
    elif args.command == "peers":
        _cmd_peers(args)
    elif args.command == "selftest":
        _cmd_selftest()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
