"""
dcf.py — Intrinsic DCF / DDM valuation toolkit
================================================
Formulas sourced from Damodaran, *Investment Valuation* (3rd ed.).
Page-anchor format: [printed p.X / PDF p.Y]  (PDF = printed + 19)

Requires: Python 3.8+, numpy (for tolerance comparisons only; pure-math
          functions do not use numpy arrays so the module stays portable).
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Cash-flow projection
# ---------------------------------------------------------------------------

def project_cashflows(base_cf: float, growth_rates) -> list:
    """Return a list of cash flows, each compounded by the next growth rate.

    [printed p.383 / PDF p.402] — multi-stage FCFF model: compound the
    base cash flow successively through each explicit high-growth rate.

    Parameters
    ----------
    base_cf : float
        The starting (current-period) free cash flow.
    growth_rates : sequence of float
        Growth rates for each successive period (e.g. [0.12, 0.10, 0.08]).

    Returns
    -------
    list of float
        len(growth_rates) projected cash flows; flow[i] is the cash flow
        for period i+1 after compounding through growth_rates[0..i].

    Examples
    --------
    >>> project_cashflows(100, [0.10, 0.08])
    [110.0, 118.80000000000001]
    """
    flows: list[float] = []
    cf = base_cf
    for g in growth_rates:
        cf = cf * (1.0 + g)
        flows.append(cf)
    return flows


# ---------------------------------------------------------------------------
# 2. Present value of a sequence of flows
# ---------------------------------------------------------------------------

def pv_of_flows(flows, rate: float, mid_year: bool = False) -> float:
    """Discount a sequence of cash flows to present value.

    [printed p.383–385 / PDF p.402–404]

    End-year convention (mid_year=False):
        PV = Σ  flow_t / (1+rate)^t        t = 1, 2, …, n

    Mid-year convention (mid_year=True):
        PV = Σ  flow_t / (1+rate)^(t-0.5)  t = 1, 2, …, n

    Parameters
    ----------
    flows : sequence of float
        Cash flows in order (flows[0] = period-1 cash flow, etc.).
    rate : float
        Periodic discount rate (e.g. 0.09 for 9 %).
    mid_year : bool
        If True use mid-year (t-0.5) convention; else end-of-year.

    Returns
    -------
    float
        Sum of discounted cash flows.
    """
    total = 0.0
    for i, cf in enumerate(flows):
        t = i + 1  # periods start at 1
        exponent = t - 0.5 if mid_year else float(t)
        total += cf / (1.0 + rate) ** exponent
    return total


# ---------------------------------------------------------------------------
# 3. Terminal value
# ---------------------------------------------------------------------------

def terminal_value(
    last_cf: float,
    rate: float,
    stable_growth: float,
    rf: Optional[float] = None,
) -> float:
    """Gordon-growth terminal value (perpetuity).

    [printed p.306 / PDF p.325]
    TV_n = last_cf × (1 + stable_growth) / (rate − stable_growth)

    Hard guardrails enforced:
    1. stable_growth < rate        (math constraint — denominator must be > 0)
       [printed p.306 / PDF p.325]
    2. stable_growth ≤ rf          (economic constraint — no firm grows forever
       faster than the risk-free rate, which proxies nominal GDP growth)
       [printed p.307 / PDF p.326]

    Parameters
    ----------
    last_cf : float
        Cash flow at end of explicit forecast period (FCF_n or DPS_n).
    rate : float
        Discount rate for the stable-growth phase (WACC, ke, etc.).
    stable_growth : float
        Perpetuity growth rate.
    rf : float or None
        Risk-free rate; if supplied, stable_growth > rf raises ValueError.

    Returns
    -------
    float
        Terminal value as of the end of the explicit forecast period.

    Raises
    ------
    ValueError
        If stable_growth >= rate (math collapses).
        If rf is provided and stable_growth > rf (economic guardrail).
    """
    # Guardrail 1 — math constraint [printed p.306 / PDF p.325]
    if stable_growth >= rate:
        raise ValueError(
            f"stable_growth ({stable_growth:.6f}) must be strictly less than "
            f"rate ({rate:.6f}). The terminal-value denominator would be "
            f"zero or negative. [Damodaran printed p.306 / PDF p.325]"
        )
    # Guardrail 2 — economic constraint [printed p.307 / PDF p.326]
    if rf is not None and stable_growth > rf + 1e-9:
        raise ValueError(
            f"stable_growth ({stable_growth:.6f}) exceeds rf ({rf:.6f}). "
            f"'No firm can grow forever at a rate higher than the risk-free "
            f"rate.' [Damodaran printed p.307 / PDF p.326]"
        )
    return last_cf * (1.0 + stable_growth) / (rate - stable_growth)


# ---------------------------------------------------------------------------
# 4. Full DCF value
# ---------------------------------------------------------------------------

def dcf_value(
    base_cf: float,
    growth_rates,
    rate: float,
    stable_growth: float,
    mid_year: bool = False,
    rf: Optional[float] = None,
) -> dict:
    """Multi-stage DCF: explicit PV + terminal value PV.

    [printed p.383–385 / PDF p.402–404]

    Returns a dict with:
        explicit_pv  — PV of the explicit-forecast-period cash flows
        terminal_pv  — PV of the terminal (perpetuity) value
        total_value  — explicit_pv + terminal_pv
        tv_pct       — terminal_pv / total_value
        flows        — list of projected cash flows (for inspection)
        tv_undiscounted — terminal value before discounting
        warnings     — list of advisory strings (empty if none)

    tv_pct advisory flags [printed p.306–307 / PDF p.325–326]:
        > 0.80  → "TV exceeds 80% of total value: assumptions likely
                   aggressive; run sensitivity table."
        < 0.40  → "TV below 40% of total value: unusually low for a
                   going-concern; verify growth assumptions."

    Parameters
    ----------
    base_cf : float
        Current-period cash flow (starting point for projection).
    growth_rates : sequence of float
        Explicit-period growth rates.
    rate : float
        Discount rate.
    stable_growth : float
        Perpetual stable growth rate for terminal value.
    mid_year : bool
        Mid-year discounting convention.
    rf : float or None
        Risk-free rate; forwarded to terminal_value() for economic guardrail.

    Returns
    -------
    dict
    """
    flows = project_cashflows(base_cf, growth_rates)

    # Terminal value is based on the last projected cash flow
    tv = terminal_value(flows[-1], rate, stable_growth, rf=rf)

    explicit_pv = pv_of_flows(flows, rate, mid_year=mid_year)

    # Discount TV back n periods from end of explicit period
    n = len(flows)
    tv_discount_exponent = n - 0.5 if mid_year else float(n)
    terminal_pv = tv / (1.0 + rate) ** tv_discount_exponent

    total_value = explicit_pv + terminal_pv

    # tv_pct guard (avoid division by zero for degenerate inputs)
    tv_pct = terminal_pv / total_value if total_value != 0.0 else float("nan")

    warnings: list[str] = []
    if not math.isnan(tv_pct):
        if tv_pct > 0.80:
            warnings.append(
                f"tv_pct = {tv_pct:.1%} > 80% — assumptions likely aggressive; "
                f"run a sensitivity table on stable_growth and rate. "
                f"[Damodaran printed p.306–307 / PDF p.325–326]"
            )
        if tv_pct < 0.40:
            warnings.append(
                f"tv_pct = {tv_pct:.1%} < 40% — unusually low for a going-concern; "
                f"verify growth and rate assumptions. "
                f"[Damodaran printed p.306–307 / PDF p.325–326]"
            )

    return {
        "explicit_pv": explicit_pv,
        "terminal_pv": terminal_pv,
        "tv_undiscounted": tv,
        "total_value": total_value,
        "tv_pct": tv_pct,
        "flows": flows,
        "warnings": warnings,
    }


def dcf_value_explicit(
    flows,
    rate: float,
    stable_growth: float,
    mid_year: bool = False,
    rf: Optional[float] = None,
    terminal_cf: Optional[float] = None,
) -> dict:
    """DCF of an EXPLICIT cash-flow list + terminal value.

    Same return shape as dcf_value(), but the flows are supplied directly rather
    than projected from base_cf + growth_rates. Use for driver-built FCFF streams
    (Damodaran Ch.22–23 young/cyclical firms) where each year's cash flow is
    constructed from revenue × margin − reinvestment.

    The terminal value uses the SAME n−0.5 (mid-year) / n (end-year) discount
    exponent as dcf_value() so results.json and the Excel workbook stay in parity
    [report D12]. `terminal_cf`, if given, is the first stable-phase cash flow
    used for the Gordon perpetuity (e.g. EBIT_term·(1−t)·(1 − g/ROC_stable));
    otherwise the last explicit flow grown by (1+stable_growth) is used.
    """
    if not flows:
        raise ValueError("flows must be a non-empty sequence for dcf_value_explicit.")
    if stable_growth >= rate:
        raise ValueError(
            f"stable_growth ({stable_growth:.6f}) must be < rate ({rate:.6f}) "
            f"[Damodaran printed p.306 / PDF p.325]."
        )
    if rf is not None and stable_growth > rf + 1e-9:
        raise ValueError(
            f"stable_growth ({stable_growth:.6f}) exceeds rf ({rf:.6f}) "
            f"[Damodaran printed p.307 / PDF p.326]."
        )
    flows = list(flows)
    n = len(flows)
    explicit_pv = pv_of_flows(flows, rate, mid_year=mid_year)
    first_stable = terminal_cf if terminal_cf is not None else flows[-1] * (1.0 + stable_growth)
    tv = first_stable / (rate - stable_growth)
    tv_period = (n - 0.5) if mid_year else float(n)
    terminal_pv = tv / (1.0 + rate) ** tv_period
    total_value = explicit_pv + terminal_pv
    tv_pct = terminal_pv / total_value if total_value != 0.0 else float("nan")
    warnings: list[str] = []
    if not math.isnan(tv_pct):
        if tv_pct > 0.80:
            warnings.append(f"tv_pct = {tv_pct:.1%} > 80% — terminal-heavy; verify drivers.")
        if tv_pct < 0.40:
            warnings.append(f"tv_pct = {tv_pct:.1%} < 40% — unusually low; verify drivers.")
    return {
        "explicit_pv": explicit_pv,
        "terminal_pv": terminal_pv,
        "tv_undiscounted": tv,
        "total_value": total_value,
        "tv_pct": tv_pct,
        "flows": flows,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. Enterprise Value → Equity bridge
# ---------------------------------------------------------------------------

def bridge_to_equity(
    enterprise_value: float,
    net_debt: float = 0.0,
    minority_interest: float = 0.0,
    nonoperating_assets: float = 0.0,
) -> float:
    """Convert enterprise value to equity value.

    [printed p.385, 423–428 / PDF p.404, 442–447]

    Equity Value = EV
                 + Non-operating assets  (cash, cross-holdings, etc.)
                 − Net Debt              (Total Debt − Cash; market value)
                 − Minority Interest

    Note: net_debt = Total Debt − Cash. Supplying a positive net_debt
    reduces equity value; supplying a negative net_debt (net-cash firm)
    increases equity value.

    Parameters
    ----------
    enterprise_value : float
        PV of operating assets (from dcf_value or fcff_valuation).
    net_debt : float
        Market value of debt minus cash (positive = levered firm).
    minority_interest : float
        Book/market value of minority interest claims.
    nonoperating_assets : float
        Cash and near-cash, cross-holdings, undeveloped land, etc.
        Added at face value unless specifically haircutted.

    Returns
    -------
    float
        Equity value.
    """
    return enterprise_value + nonoperating_assets - net_debt - minority_interest


# ---------------------------------------------------------------------------
# 6. Equity value per share
# ---------------------------------------------------------------------------

def value_per_share(
    equity_value: float,
    basic_shares: float,
    options_value: float = 0.0,
) -> float:
    """Compute intrinsic per-share value, adjusting for options dilution.

    [printed p.423–428 / PDF p.442–447]

    Do NOT use fully-diluted share count (that overstates dilution and
    drops the time premium). Instead: value options via Black-Scholes →
    subtract from equity value → divide by basic shares.

    Value/share = (Equity Value − Options Value) / Basic Shares

    Parameters
    ----------
    equity_value : float
        Total equity value (from bridge_to_equity).
    basic_shares : float
        Basic shares outstanding (not diluted).
    options_value : float
        Black-Scholes value of outstanding employee options.

    Returns
    -------
    float
        Intrinsic value per share.
    """
    if basic_shares <= 0:
        raise ValueError(f"basic_shares must be positive, got {basic_shares}.")
    return (equity_value - options_value) / basic_shares


# ---------------------------------------------------------------------------
# 7. FCFF two-stage valuation
# ---------------------------------------------------------------------------

def fcff_valuation(
    base_fcff: float,
    growth_rates,
    wacc: float,
    stable_growth: float,
    net_debt: float = 0.0,
    shares: Optional[float] = None,
    mid_year: bool = True,
    rf: Optional[float] = None,
) -> dict:
    """Full FCFF two-stage DCF: EV → equity bridge → (optional) per share.

    [printed p.383–385 / PDF p.402–404] — FCFF valuation
    [printed p.385, 423–428 / PDF p.404, 442–447] — EV→equity bridge

    Discounts FCFF at WACC → enterprise value.
    Then applies bridge_to_equity (net_debt, no minority_interest here;
    pass via pre-adjusted EV if needed).
    If shares is provided, also returns value_per_share.

    Parameters
    ----------
    base_fcff : float
        Current-year FCFF (Year-0 base for projection).
    growth_rates : sequence of float
        Explicit-period growth rates.
    wacc : float
        Weighted average cost of capital.
    stable_growth : float
        Terminal perpetuity growth rate.
    net_debt : float
        Net debt for equity bridge (debt − cash).
    shares : float or None
        Basic shares outstanding; if None, per-share value is omitted.
    mid_year : bool
        Mid-year discounting (default True per standard DCF practice).
    rf : float or None
        Risk-free rate forwarded to terminal_value() guardrail.

    Returns
    -------
    dict
        Keys: all keys from dcf_value(), plus
        'enterprise_value', 'equity_value', and optionally 'value_per_share'.
    """
    result = dcf_value(
        base_cf=base_fcff,
        growth_rates=growth_rates,
        rate=wacc,
        stable_growth=stable_growth,
        mid_year=mid_year,
        rf=rf,
    )
    ev = result["total_value"]
    result["enterprise_value"] = ev
    equity = bridge_to_equity(ev, net_debt=net_debt)
    result["equity_value"] = equity
    if shares is not None and shares > 0:
        result["value_per_share"] = value_per_share(equity, shares)
    return result


# ---------------------------------------------------------------------------
# 8. FCFE two-stage valuation
# ---------------------------------------------------------------------------

def fcfe_valuation(
    base_fcfe: float,
    growth_rates,
    cost_of_equity: float,
    stable_growth: float,
    shares: Optional[float] = None,
    mid_year: bool = True,
    rf: Optional[float] = None,
) -> dict:
    """Full FCFE two-stage DCF: directly produces equity value (no bridge).

    [printed p.355–370 / PDF p.374–389]

    FCFE is already an equity-level cash flow; discounting at cost_of_equity
    produces equity value directly — no EV-to-equity bridge is required.

    Parameters
    ----------
    base_fcfe : float
        Current-year FCFE (Year-0 base for projection).
    growth_rates : sequence of float
        Explicit-period growth rates.
    cost_of_equity : float
        Levered cost of equity (ke).
    stable_growth : float
        Terminal perpetuity growth rate.
    shares : float or None
        Basic shares outstanding for per-share output.
    mid_year : bool
        Mid-year discounting (default True).
    rf : float or None
        Risk-free rate forwarded to terminal_value() guardrail.

    Returns
    -------
    dict
        Keys: all keys from dcf_value(), plus 'equity_value' and
        optionally 'value_per_share'.
    """
    result = dcf_value(
        base_cf=base_fcfe,
        growth_rates=growth_rates,
        rate=cost_of_equity,
        stable_growth=stable_growth,
        mid_year=mid_year,
        rf=rf,
    )
    # For FCFE the total_value IS equity value — label it explicitly
    result["equity_value"] = result["total_value"]
    if shares is not None and shares > 0:
        result["value_per_share"] = value_per_share(result["equity_value"], shares)
    return result


# ---------------------------------------------------------------------------
# 9. Gordon Growth Model (single-stage DDM)
# ---------------------------------------------------------------------------

def ddm_value(dps1: float, cost_of_equity: float, stable_growth: float) -> float:
    """Gordon Growth Model — stable DDM.

    [printed p.323–327 / PDF p.342–346]

    P₀ = DPS₁ / (ke − g)

    Parameters
    ----------
    dps1 : float
        Next-period (Year 1) dividend per share.
    cost_of_equity : float
        Required return on equity (ke).
    stable_growth : float
        Perpetual dividend growth rate (must be < ke).

    Returns
    -------
    float
        Intrinsic stock price.

    Raises
    ------
    ValueError
        If stable_growth >= cost_of_equity (same math constraint).
    """
    if stable_growth >= cost_of_equity:
        raise ValueError(
            f"stable_growth ({stable_growth}) must be < cost_of_equity "
            f"({cost_of_equity}) for the Gordon model. "
            f"[Damodaran printed p.323 / PDF p.342]"
        )
    return dps1 / (cost_of_equity - stable_growth)


# ---------------------------------------------------------------------------
# 10. Two-stage DDM
# ---------------------------------------------------------------------------

def ddm_two_stage(
    dps0: float,
    high_growth: float,
    high_years: int,
    stable_growth: float,
    ke_high: float,
    ke_stable: float,
    payout_stable: Optional[float] = None,
    payout_high: Optional[float] = None,
) -> float:
    """Two-stage Dividend Discount Model.

    [printed p.329–331 / PDF p.348–350]

    Stage 1 (t=1..high_years):
        DPS_t = DPS_{t-1} × (1 + high_growth)
        Discounted at ke_high.

    Stage 2 (perpetuity from t=high_years+1):
        DPS_{n+1} = DPS_n × (1 + stable_growth)                        [payout_stable is None]
        OR (payout-ratio step-up, anchored to EARNINGS per p.331):
        DPS_{n+1} = EPS_n × (1 + stable_growth) × payout_stable        [payout_stable given]
                  = (DPS_n / payout_high) × (1 + stable_growth) × payout_stable
        P_n       = DPS_{n+1} / (ke_stable − stable_growth)
        PV(P_n)   = P_n / (1 + ke_high)^n

    When payout_stable is None the function assumes the DPS series already
    reflects the correct payout trajectory (i.e., DPS grows at stable_growth
    from the last high-growth DPS). To model a payout-ratio step-change at the
    stable transition (e.g., the Damodaran P&G example: payout rises to 75%),
    pass BOTH payout_stable and payout_high. The stable dividend is anchored to
    EPS_n (recovered as DPS_n / payout_high), because a stable firm reinvests
    less and pays out a HIGHER fraction of the same earnings. Multiplying the
    last-high DPS directly by payout_stable (the pre-fix behaviour) double-counts
    the payout ratio and materially understates value. [report D5, p.331]

    Parameters
    ----------
    dps0 : float
        Current (Year-0) dividend per share.
    high_growth : float
        Dividend growth rate during the high-growth phase.
    high_years : int
        Number of explicit high-growth years.
    stable_growth : float
        Perpetual growth rate in stable phase.
    ke_high : float
        Cost of equity during high-growth phase (used for discounting stage 1
        and the terminal price).
    ke_stable : float
        Cost of equity in stable phase (used in Gordon model for terminal P).
    payout_stable : float or None
        Stable-phase dividend payout ratio (= 1 − g_stable/ROE_stable). If
        provided, the terminal dividend is earnings-anchored:
            DPS_{n+1} = (DPS_n / payout_high) × (1 + stable_growth) × payout_stable
        Pass None to simply grow the last high-growth DPS by (1+stable_growth).
    payout_high : float or None
        High-phase dividend payout ratio, required whenever payout_stable is
        supplied (used to recover EPS_n = DPS_n / payout_high). Must be > 0.

    Returns
    -------
    float
        Intrinsic stock price (P₀).

    Raises
    ------
    ValueError
        If stable_growth >= ke_stable.
    """
    if stable_growth >= ke_stable:
        raise ValueError(
            f"stable_growth ({stable_growth}) must be < ke_stable ({ke_stable}). "
            f"[Damodaran printed p.329 / PDF p.348]"
        )

    # Stage 1: PV of explicit dividends
    pv_dividends = 0.0
    dps = dps0
    for t in range(1, high_years + 1):
        dps = dps * (1.0 + high_growth)
        pv_dividends += dps / (1.0 + ke_high) ** t

    # dps is now DPS_{high_years} (last high-growth dividend)
    dps_last_high = dps

    # Stage 2: terminal dividend and price
    if payout_stable is None:
        dps_next = dps_last_high * (1.0 + stable_growth)
    else:
        # Payout-ratio step-up at the stable transition. The stable dividend is
        # anchored to EARNINGS, not to the last high-growth dividend:
        #   DPS_{n+1} = EPS_n × (1 + g_stable) × payout_stable   [p.331 / PDF p.350]
        # Recover EPS_n from DPS_n via the high-phase payout ratio. Scaling the
        # last-high DPS directly by payout_stable (the pre-fix path) is
        # dimensionally wrong — it re-applies a payout ratio to a number that
        # already embeds one — and understates value. [report D5]
        if payout_high is None or payout_high <= 0.0:
            raise ValueError(
                "payout_high (high-phase payout ratio, > 0) is required when "
                "payout_stable is supplied, to convert DPS_n back to EPS_n. "
                "[Damodaran printed p.331 / PDF p.350]"
            )
        eps_last_high = dps_last_high / payout_high
        dps_next = eps_last_high * (1.0 + stable_growth) * payout_stable

    p_n = ddm_value(dps_next, ke_stable, stable_growth)
    pv_terminal = p_n / (1.0 + ke_high) ** high_years

    return pv_dividends + pv_terminal


# ---------------------------------------------------------------------------
# 11. CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcf.py",
        description="Intrinsic valuation: FCFF / FCFE / DDM — Damodaran (3rd ed.)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- fcff subcommand ---
    p_fcff = sub.add_parser("fcff", help="2-stage FCFF DCF valuation")
    p_fcff.add_argument("--base", type=float, required=True,
                        help="Base FCFF (year-0, $m or per share)")
    p_fcff.add_argument("--growth", type=str, required=True,
                        help='Comma-separated explicit growth rates e.g. "0.10,0.08,0.06"')
    p_fcff.add_argument("--wacc", type=float, required=True,
                        help="WACC (e.g. 0.09)")
    p_fcff.add_argument("--tg", type=float, required=True,
                        help="Terminal/stable growth rate (e.g. 0.025)")
    p_fcff.add_argument("--net-debt", type=float, default=0.0,
                        help="Net debt = total debt − cash ($m); default 0")
    p_fcff.add_argument("--shares", type=float, default=None,
                        help="Basic shares outstanding (for per-share output)")
    p_fcff.add_argument("--rf", type=float, default=None,
                        help="Risk-free rate (activates economic guardrail)")
    p_fcff.add_argument("--mid-year", action="store_true", default=True,
                        help="Use mid-year discounting (default: on)")

    # --- ddm subcommand ---
    p_ddm = sub.add_parser("ddm", help="Gordon Growth Model (single-stage DDM)")
    p_ddm.add_argument("--dps1", type=float, required=True,
                       help="Next-period dividend per share (DPS₁)")
    p_ddm.add_argument("--ke", type=float, required=True,
                       help="Cost of equity (e.g. 0.085)")
    p_ddm.add_argument("--g", type=float, required=True,
                       help="Perpetual dividend growth rate (e.g. 0.03)")

    # --- selftest subcommand ---
    sub.add_parser("selftest", help="Run built-in self-tests")

    return parser


def _run_fcff(args: argparse.Namespace) -> None:
    growth_rates = [float(x) for x in args.growth.split(",")]
    result = fcff_valuation(
        base_fcff=args.base,
        growth_rates=growth_rates,
        wacc=args.wacc,
        stable_growth=args.tg,
        net_debt=args.net_debt,
        shares=args.shares,
        mid_year=args.mid_year,
        rf=args.rf,
    )
    print("\n=== FCFF Valuation ===")
    print(f"  Explicit-period flows : {[f'{v:.2f}' for v in result['flows']]}")
    print(f"  PV of explicit flows  : {result['explicit_pv']:,.2f}")
    print(f"  Terminal value (TV)   : {result['tv_undiscounted']:,.2f}")
    print(f"  PV of TV              : {result['terminal_pv']:,.2f}")
    print(f"  Enterprise Value      : {result['enterprise_value']:,.2f}")
    print(f"  Equity Value          : {result['equity_value']:,.2f}")
    print(f"  TV as % of total      : {result['tv_pct']:.1%}")
    if "value_per_share" in result:
        print(f"  Value per share       : {result['value_per_share']:,.2f}")
    for w in result["warnings"]:
        print(f"  [WARNING] {w}")
    print()


def _run_ddm(args: argparse.Namespace) -> None:
    price = ddm_value(args.dps1, args.ke, args.g)
    print(f"\n=== Gordon DDM ===")
    print(f"  DPS₁ = {args.dps1:.4f},  ke = {args.ke:.4f},  g = {args.g:.4f}")
    print(f"  Intrinsic Price = {price:,.4f}")
    print()


# ---------------------------------------------------------------------------
# 12. Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Run deterministic self-tests against hand-computed reference values."""
    import numpy as np  # only used for isclose tolerance in selftest

    TOL = 1e-4  # relative tolerance ~0.01%
    results: list[tuple[str, bool, str]] = []

    def check(name: str, computed: float, expected: float, tol: float = TOL) -> None:
        ok = bool(np.isclose(computed, expected, rtol=tol))
        results.append((name, ok, f"computed={computed:.6f}  expected={expected:.6f}"))

    # -----------------------------------------------------------------------
    # Check A — Hand-checkable 2-stage FCFF (end-year convention)
    #
    # Inputs:  base_fcff=80, growth=[0.12, 0.12, 0.12], wacc=0.09,
    #          stable_growth=0.03, net_debt=0, mid_year=False
    #
    # Hand computation:
    #   Projected flows:
    #     Y1 = 80 × 1.12        = 89.6000
    #     Y2 = 89.6 × 1.12      = 100.3520
    #     Y3 = 100.352 × 1.12   = 112.3942
    #
    #   Terminal value (at end of Y3):
    #     TV3 = 112.3942 × 1.03 / (0.09 − 0.03)
    #         = 115.7661 / 0.06
    #         = 1,929.4340
    #
    #   PV of explicit CFs (end-year):
    #     PV(Y1) = 89.6000 / 1.09^1  =  89.6000 / 1.09000  =  82.2018
    #     PV(Y2) = 100.3520/ 1.09^2  = 100.3520 / 1.18810  =  84.4698
    #     PV(Y3) = 112.3942/ 1.09^3  = 112.3942 / 1.29503  =  86.7758
    #     PV_explicit = 82.2018 + 84.4698 + 86.7758 = 253.4474
    #
    #   PV of TV:
    #     PV(TV) = 1929.4340 / 1.09^3 = 1929.4340 / 1.29503 = 1489.8816
    #
    #   Total firm value = 253.4474 + 1489.8816 = 1743.3290
    # -----------------------------------------------------------------------
    EXPECTED_FCFF_TOTAL = (
        89.6 / 1.09
        + 100.352 / 1.09 ** 2
        + 112.3942 / 1.09 ** 3
        + (112.3942 * 1.03 / 0.06) / 1.09 ** 3
    )
    # More precise hand value using exact floats:
    y1 = 80 * 1.12
    y2 = y1 * 1.12
    y3 = y2 * 1.12
    tv3 = y3 * 1.03 / (0.09 - 0.03)
    expected_total = (
        y1 / 1.09 ** 1
        + y2 / 1.09 ** 2
        + y3 / 1.09 ** 3
        + tv3 / 1.09 ** 3
    )

    res_a = fcff_valuation(
        base_fcff=80.0,
        growth_rates=[0.12, 0.12, 0.12],
        wacc=0.09,
        stable_growth=0.03,
        net_debt=0.0,
        shares=None,
        mid_year=False,
        rf=None,
    )
    check("A: 2-stage FCFF total value", res_a["total_value"], expected_total)
    check("A: 2-stage FCFF enterprise_value == total_value",
          res_a["enterprise_value"], res_a["total_value"])

    # -----------------------------------------------------------------------
    # Check B — Gordon DDM:  ddm_value(2.0, 0.10, 0.04) = 2.0/0.06 ≈ 33.3333
    # -----------------------------------------------------------------------
    expected_gordon = 2.0 / 0.06
    computed_gordon = ddm_value(2.0, 0.10, 0.04)
    check("B: Gordon DDM ddm_value(2.0, 0.10, 0.04)", computed_gordon, expected_gordon)

    # -----------------------------------------------------------------------
    # Check C1 — terminal_value RAISES when stable_growth >= rate
    # -----------------------------------------------------------------------
    raised_c1 = False
    try:
        terminal_value(100.0, rate=0.09, stable_growth=0.09)
    except ValueError:
        raised_c1 = True
    results.append(("C1: terminal_value raises when stable_growth == rate",
                    raised_c1,
                    f"ValueError raised: {raised_c1}"))

    raised_c1b = False
    try:
        terminal_value(100.0, rate=0.09, stable_growth=0.10)
    except ValueError:
        raised_c1b = True
    results.append(("C1b: terminal_value raises when stable_growth > rate",
                    raised_c1b,
                    f"ValueError raised: {raised_c1b}"))

    # -----------------------------------------------------------------------
    # Check C2 — terminal_value RAISES when stable_growth > rf (economic guard)
    # -----------------------------------------------------------------------
    raised_c2 = False
    try:
        # stable_growth=0.04, rf=0.035 → 0.04 > 0.035 + 1e-9 → should raise
        terminal_value(100.0, rate=0.09, stable_growth=0.04, rf=0.035)
    except ValueError:
        raised_c2 = True
    results.append(("C2: terminal_value raises when stable_growth > rf",
                    raised_c2,
                    f"ValueError raised: {raised_c2}"))

    # Verify it does NOT raise when stable_growth == rf (boundary is ≤ rf)
    no_raise_c2 = True
    try:
        terminal_value(100.0, rate=0.09, stable_growth=0.035, rf=0.035)
    except ValueError:
        no_raise_c2 = False
    results.append(("C2b: terminal_value does NOT raise when stable_growth == rf",
                    no_raise_c2,
                    f"No raise: {no_raise_c2}"))

    # -----------------------------------------------------------------------
    # Check D — tv_pct is between 0 and 1 (exclusive) for normal inputs
    # -----------------------------------------------------------------------
    res_d = dcf_value(
        base_cf=50.0,
        growth_rates=[0.08, 0.06, 0.05],
        rate=0.10,
        stable_growth=0.025,
    )
    tv_pct_ok = 0.0 < res_d["tv_pct"] < 1.0
    results.append(("D: tv_pct between 0 and 1",
                    tv_pct_ok,
                    f"tv_pct={res_d['tv_pct']:.4f}"))

    # -----------------------------------------------------------------------
    # Extra — Damodaran Con Ed worked DDM example [printed p.326–327 / PDF p.345–346]
    # DPS0=2.22, ke=7.5%, g=3.5%  → P0 = 2.22*1.035/(0.075-0.035) = 2.2977/0.04 = 57.4425
    # -----------------------------------------------------------------------
    expected_coned = 2.22 * 1.035 / (0.075 - 0.035)
    computed_coned = ddm_value(2.22 * 1.035, 0.075, 0.035)
    check("E: Con Ed DDM example [p.326-327]", computed_coned, expected_coned)

    # -----------------------------------------------------------------------
    # Check F — Two-stage DDM with payout step-up: Damodaran P&G example
    # [printed p.331–332 / PDF p.350–351], book P0 = $68.90.
    # EPS0=3.82, payout_high=0.50 → DPS0=1.91; g_hi=10% for 5y; g_n=3%;
    # ke_hi=8.0%, ke_st=8.5%, payout_stable = 1 − 3%/12% = 0.75.
    # Regression guard: the pre-fix payout branch returned $39.50 (dimensional
    # error); the earnings-anchored fix reproduces the book's ~$68.90. [D5]
    # -----------------------------------------------------------------------
    pg_dps0 = 3.82 * 0.50
    pg_p0 = ddm_two_stage(pg_dps0, high_growth=0.10, high_years=5,
                          stable_growth=0.03, ke_high=0.08, ke_stable=0.085,
                          payout_stable=0.75, payout_high=0.50)
    results.append(("F: Two-stage DDM P&G payout step-up ≈ $68.90 [p.331]",
                    abs(pg_p0 - 68.90) < 0.15,
                    f"computed={pg_p0:.4f}  expected≈68.90 (pre-fix bug gave 39.50)"))

    # Check F2 — payout_stable without payout_high must raise (no silent
    # dimensional error). [D5]
    raised_f2 = False
    try:
        ddm_two_stage(pg_dps0, 0.10, 5, 0.03, 0.08, 0.085, payout_stable=0.75)
    except ValueError:
        raised_f2 = True
    results.append(("F2: payout_stable without payout_high raises",
                    raised_f2, f"ValueError raised: {raised_f2}"))

    # -----------------------------------------------------------------------
    # Check G — dcf_value_explicit reproduces dcf_value on the same (geometric)
    # flows, and discounts the terminal value at n−0.5 under mid-year — the
    # parity guarantee the driver models rely on. [report D12]
    # -----------------------------------------------------------------------
    gflows = project_cashflows(100.0, [0.10, 0.08, 0.06, 0.05])
    v_proj = dcf_value(100.0, [0.10, 0.08, 0.06, 0.05], 0.09, 0.025, mid_year=True)
    v_expl = dcf_value_explicit(gflows, 0.09, 0.025, mid_year=True)
    check("G: dcf_value_explicit total == dcf_value total (mid-year)",
          v_expl["total_value"], v_proj["total_value"])
    n_g = len(gflows)
    v_tcf = dcf_value_explicit(gflows, 0.09, 0.025, mid_year=True, terminal_cf=50.0)
    exp_tv_pv = (50.0 / (0.09 - 0.025)) / (1.09) ** (n_g - 0.5)
    check("G2: explicit terminal_cf discounted at n−0.5", v_tcf["terminal_pv"], exp_tv_pv)

    # -----------------------------------------------------------------------
    # Print results
    # -----------------------------------------------------------------------
    print("\n=== DCF Self-Test ===")
    all_pass = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        print(f"         {detail}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("ONE OR MORE CHECKS FAILED — see above")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "fcff":
        _run_fcff(args)
    elif args.command == "ddm":
        _run_ddm(args)
    elif args.command == "selftest":
        _selftest()


if __name__ == "__main__":
    main()
