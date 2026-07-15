"""
rnpv.py — Risk-adjusted NPV (rNPV), Sum-of-the-Parts (SOTP), and Real Options
for biotech / life-sciences valuation.

Formulae sourced from:
  Damodaran, Investment Valuation, 3rd ed.
  Ch.5  [p.87-129]  — DCF foundations
  Ch.28 [p.781-823] — Patent/R&D as real option
  Ch.29 [p.805-844] — Options to expand / abandon
  Ch.30 [p.826-829] — Equity as call option on firm assets
  Ch.33 [p.894-943] — Scenario analysis, decision trees, Monte Carlo
  Upstream Bio (UPB) canonical worked rNPV/SOTP example (synthetic illustration)
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import List, Tuple

import numpy as np
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Core rNPV / SOTP functions
# ---------------------------------------------------------------------------

def asset_rnpv(
    pv_commercial: float,
    loa: float,
    pv_dev_cost: float = 0.0,
    floor_zero: bool = True,
) -> float:
    """
    Compute risk-adjusted NPV for a single pipeline asset.

    Formula [Ch.28, p.781-823; UPB canonical example]:
        rNPV = LoA × PV(commercial cash flows) − PV(remaining development cost)

    Optional assets may be floored at zero because management retains the right
    to abandon when rNPV < 0 [Master Guardrail #3, p.344]:
        if floor_zero: rNPV = max(rNPV, 0)

    Parameters
    ----------
    pv_commercial : float
        Present value of post-approval commercial cash flows ($M).
    loa : float
        Likelihood of Approval — cumulative probability of success through all
        remaining clinical/regulatory phases.  Must be in [0, 1].
    pv_dev_cost : float, optional
        Present value of remaining development costs ($M).  Default 0.
    floor_zero : bool, optional
        If True (default), floor the result at 0 (management can abandon).

    Returns
    -------
    float
        rNPV of the asset ($M).

    Raises
    ------
    ValueError
        If loa is not in the closed interval [0, 1].
    """
    if not (0.0 <= loa <= 1.0):
        raise ValueError(
            f"LoA must be in [0, 1]; received {loa!r}. "
            "Probabilities cannot exceed 100 % or be negative "
            "[Master Guardrail #1, p.344]."
        )
    value = loa * pv_commercial - pv_dev_cost
    if floor_zero:
        value = max(value, 0.0)
    return value


def sotp_equity(
    asset_rnpvs: List[float],
    net_cash: float,
    overhead_pv: float = 0.0,
    options_value: float = 0.0,
) -> float:
    """
    Aggregate pipeline asset rNPVs into a Sum-of-the-Parts equity value.

    Formula [Ch.28, p.781-823; UPB SOTP bridge; per_share_and_dilution.md §4.3]:
        Enterprise rNPV = Σ rNPV_i
        Equity Value    = Enterprise rNPV + Net Cash − PV(G&A overhead)
                          − Options Value

    Options are treated as a LIABILITY subtracted from equity value (then the
    remainder is divided by BASIC shares) — never by padding the share count to
    "fully diluted", which drops the option time premium. [report D10]

    Parameters
    ----------
    asset_rnpvs : list of float
        Individual asset rNPV values ($M), as returned by asset_rnpv().
    net_cash : float
        Cash and equivalents minus financial debt ($M).  Can be negative.
    overhead_pv : float, optional
        Present value of ongoing G&A / corporate overhead not already captured
        in individual asset cost lines ($M).  Default 0.
    options_value : float, optional
        Black-Scholes value of outstanding employee options / warrants ($M),
        subtracted as a liability.  Default 0.

    Returns
    -------
    float
        Total equity value ($M).
    """
    return float(np.sum(asset_rnpvs)) + net_cash - overhead_pv - options_value


def per_share(equity_value: float, shares: float) -> float:
    """
    Convert aggregate equity value to a per-share price.

    Parameters
    ----------
    equity_value : float
        Total equity value ($M), already net of options value (options are
        subtracted from equity in sotp_equity, not added to this denominator).
    shares : float
        BASIC shares outstanding (millions). Do NOT pass a fully-diluted count —
        that double-counts dilution and drops the option time premium. [D10]

    Returns
    -------
    float
        Equity value per share ($).

    Raises
    ------
    ValueError
        If shares is zero or negative.
    """
    if shares <= 0.0:
        raise ValueError(f"shares must be positive; received {shares!r}.")
    # equity_value is in $M and shares is in millions → ratio is pure $/share
    return equity_value / shares


def scenario_weighted(scenarios: List[Tuple[float, float]]) -> float:
    """
    Compute a probability-weighted expected target price from discrete scenarios.

    Formula [Ch.33, p.895-896]:
        E[TP] = Σ p_i × TP_i

    Probabilities must sum to 1 (checked within tolerance 1e-9).

    Parameters
    ----------
    scenarios : list of (probability, target_price) tuples
        Each tuple is (p_i, TP_i) where p_i ∈ (0, 1] and TP_i is the
        per-share target price under that scenario.

    Returns
    -------
    float
        Probability-weighted expected target price.

    Raises
    ------
    ValueError
        If probabilities do not sum to approximately 1.
    """
    probs = [p for p, _ in scenarios]
    total = sum(probs)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"Scenario probabilities must sum to 1; received sum={total!r}. "
            "[Ch.33, p.895-896: probabilities must cover the full probability space]."
        )
    return sum(p * tp for p, tp in scenarios)


# ---------------------------------------------------------------------------
# Real Option functions
# ---------------------------------------------------------------------------

def patent_option(
    S: float,
    K: float,
    t: float,
    sigma: float,
    rf: float,
    cost_of_delay: float,
) -> float:
    """
    Value a patent or R&D program as a dividend-adjusted Black-Scholes call.

    Formula [Ch.28, p.789-791; Avonex worked example p.791-792]:

        y  = cost_of_delay  (annual dividend yield analog; = 1/patent_life)
        d1 = [ln(S/K) + (rf − y + σ²/2) × t] / (σ × √t)
        d2 = d1 − σ × √t
        C  = S × exp(−y×t) × N(d1) − K × exp(−rf×t) × N(d2)

    The cost-of-delay rises each year as patent life shortens
    [Master Guardrail #4, p.354]:
        cost_of_delay = 1 / n   (n = years of patent life remaining)
    This makes early exercise increasingly attractive as the patent ages.

    Parameters
    ----------
    S : float
        PV of cash flows if the product were commercialized today ($M).
    K : float
        Development / commercialisation cost; the option strike price ($M).
    t : float
        Remaining patent (or exclusive license) life in years.
    sigma : float
        Volatility of the underlying project value (annualised).
        [Guardrail #5, p.354]: use variance in project *value over time*,
        not variance in quarterly revenue. σ² ≈ 0.15-0.30 for established
        biotech; 0.30-0.60 for early-stage.
    rf : float
        Continuously compounded risk-free rate matching the expiry horizon.
    cost_of_delay : float
        Annual dividend yield analog = 1 / patent_life (see above).

    Returns
    -------
    float
        Option value of the patent / R&D program ($M).
    """
    q = cost_of_delay
    sigma_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(S / K) + (rf - q + sigma ** 2 / 2) * t) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    call = S * math.exp(-q * t) * norm.cdf(d1) - K * math.exp(-rf * t) * norm.cdf(d2)
    return call


def equity_as_call(
    firm_value: float,
    face_debt: float,
    t: float,
    sigma: float,
    rf: float,
) -> float:
    """
    Value distressed-firm equity as a call option on firm assets.

    Formula [Ch.30, p.826-829]:

        d1 = [ln(S/K) + (rf + σ²/2) × t] / (σ × √t)
        d2 = d1 − σ × √t
        E  = S × N(d1) − K × exp(−rf×t) × N(d2)

    No dividend-yield adjustment on the asset term: the reference formula
    [p.828] uses S·N(d1) directly (equity holders receive no interim payout
    from the firm's assets when modelling through-to-debt-maturity).

    Key insight [p.828]: Even when firm_value < face_debt, equity retains
    positive option time value driven by asset variance and time remaining.

    Parameters
    ----------
    firm_value : float
        Current market value of firm assets ($M).
    face_debt : float
        Face value of outstanding debt; the option strike price ($M).
    t : float
        Weighted-average debt maturity in years.
    sigma : float
        Volatility of firm asset value (annualised).
    rf : float
        Continuously compounded risk-free rate.

    Returns
    -------
    float
        Equity value of the distressed firm ($M).
    """
    sigma_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(firm_value / face_debt) + (rf + sigma ** 2 / 2) * t) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    equity = firm_value * norm.cdf(d1) - face_debt * math.exp(-rf * t) * norm.cdf(d2)
    return equity


# ---------------------------------------------------------------------------
# Self-test suite
# ---------------------------------------------------------------------------

def _run_selftest() -> int:
    """
    Execute all golden-test assertions.  Returns 0 if all pass, 1 otherwise.

    Golden tests lock the Upstream Bio (UPB) illustrative SOTP result and the
    Avonex patent-option example from Damodaran Ch.28 [p.791-792].
    """
    failures: List[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        tag = "PASS" if condition else "FAIL"
        msg = f"  [{tag}] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        if not condition:
            failures.append(name)

    print("=" * 60)
    print("rnpv.py selftest")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Test 1: SOTP golden — Upstream Bio base case
    # assets=[215,150,15], net_cash=255, overhead_pv=110 → equity=525
    # ------------------------------------------------------------------
    assets = [215.0, 150.0, 15.0]
    sotp_val = sotp_equity(assets, net_cash=255.0, overhead_pv=110.0)
    expected_sotp = 525.0
    check(
        "UPB SOTP equity == $525.0M",
        abs(sotp_val - expected_sotp) < 1e-6,
        f"got {sotp_val:.6f}",
    )

    # Options-as-liability: subtracted from equity, never added / never padded
    # into the share denominator. [report D10/D11]
    sotp_opt = sotp_equity(assets, net_cash=255.0, overhead_pv=110.0, options_value=50.0)
    check(
        "SOTP options subtracted: 525 − 50 == $475.0M",
        abs(sotp_opt - 475.0) < 1e-6,
        f"got {sotp_opt:.6f}",
    )

    # ------------------------------------------------------------------
    # Test 2: per-share — base case $9.65
    # per_share(525.0, 54.45) ≈ 9.642  (tol 0.02)
    # ------------------------------------------------------------------
    ps = per_share(525.0, 54.45)
    check(
        "UPB per_share(525, 54.45) ≈ $9.642 (base case $9.65)",
        abs(ps - 9.642) < 0.02,
        f"got {ps:.4f}",
    )

    # ------------------------------------------------------------------
    # Test 3: scenario-weighted — $10.00 rounded
    # 0.25×18 + 0.45×9.65 + 0.30×4.25 ≈ 10.1175  (tol 1e-3)
    # ------------------------------------------------------------------
    sw = scenario_weighted([(0.25, 18.0), (0.45, 9.65), (0.30, 4.25)])
    check(
        "UPB scenario_weighted ≈ $10.1175 ($10.00 rounded)",
        abs(sw - 10.1175) < 1e-3,
        f"got {sw:.6f}",
    )

    # ------------------------------------------------------------------
    # Test 4: asset_rnpv — asthma asset (Phase 2 CRTH2 50% LoA)
    # asset_rnpv(430, 0.50, 0) == 215.0
    # ------------------------------------------------------------------
    rv = asset_rnpv(pv_commercial=430.0, loa=0.50, pv_dev_cost=0.0)
    check(
        "asset_rnpv(430, 0.50, 0) == 215.0",
        rv == 215.0,
        f"got {rv!r}",
    )

    # ------------------------------------------------------------------
    # Test 5: asset_rnpv — LoA > 1 must raise ValueError
    # ------------------------------------------------------------------
    raised = False
    try:
        asset_rnpv(pv_commercial=100.0, loa=1.3)
    except ValueError:
        raised = True
    check("asset_rnpv(loa=1.3) raises ValueError", raised)

    # ------------------------------------------------------------------
    # Test 6: patent_option — Avonex example (Damodaran Ch.28, p.791-792)
    # Inputs:  S=3422, K=2875, t=17, sigma=sqrt(0.224), rf=0.067, y=1/17
    # Expected option value ≈ $907M  (tolerance ±5%)
    # Also assert option_value > naive NPV = S − K = 547 (time premium > 0)
    # ------------------------------------------------------------------
    S_av, K_av, t_av = 3422.0, 2875.0, 17.0
    sigma_av = math.sqrt(0.224)           # σ² = 0.224 → σ ≈ 0.4733
    rf_av = 0.067
    y_av = 1.0 / 17.0                     # cost of delay
    ref_option = 907.0
    option_val = patent_option(S_av, K_av, t_av, sigma_av, rf_av, y_av)
    tol_5pct = ref_option * 0.05          # ±5% = ±45.35
    naive_npv = S_av - K_av              # 547
    check(
        f"Avonex patent_option ≈ ${ref_option:.0f}M (±5%)",
        abs(option_val - ref_option) <= tol_5pct,
        f"got {option_val:.2f}, tol ±{tol_5pct:.2f}",
    )
    check(
        "Avonex option_value > naive NPV (time premium > 0)",
        option_val > naive_npv,
        f"option={option_val:.2f} > naive={naive_npv:.2f}",
    )

    # ------------------------------------------------------------------
    # Bonus sanity: deep in-the-money call ≈ S·exp(−q·t) − K·exp(−rf·t)
    # For a very deep ITM call (S=1000, K=1, t=1, sigma=0.01) the time
    # value is negligible and option_value ≈ intrinsic (discounted).
    # ------------------------------------------------------------------
    deep_itm = patent_option(S=1000.0, K=1.0, t=1.0, sigma=0.01, rf=0.05, cost_of_delay=0.02)
    intrinsic = 1000.0 * math.exp(-0.02 * 1.0) - 1.0 * math.exp(-0.05 * 1.0)
    check(
        "Deep ITM call ≈ discounted intrinsic (sanity)",
        deep_itm > intrinsic * 0.99,
        f"option={deep_itm:.4f}, intrinsic≈{intrinsic:.4f}",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("-" * 60)
    total = 8   # 6 named + options-as-liability + 1 bonus = 8 check() calls
    n_fail = len(failures)
    n_pass = total - n_fail
    print(f"Result: {n_pass}/{total} PASS, {n_fail}/{total} FAIL")
    if failures:
        print("Failed checks:")
        for f in failures:
            print(f"  • {f}")
        return 1
    else:
        print("ALL PASS")
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rnpv",
        description="rNPV / SOTP / Real Options valuation utilities (Damodaran Ch.28-30,33).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- rnpv subcommand ------------------------------------------------
    p_rnpv = sub.add_parser("rnpv", help="Compute single-asset risk-adjusted NPV.")
    p_rnpv.add_argument("--pv-commercial", type=float, required=True,
                        help="PV of post-approval commercial cash flows ($M).")
    p_rnpv.add_argument("--loa", type=float, required=True,
                        help="Likelihood of Approval [0, 1].")
    p_rnpv.add_argument("--dev-cost", type=float, default=0.0,
                        help="PV of remaining development costs ($M). Default 0.")
    p_rnpv.add_argument("--no-floor", action="store_true",
                        help="Disable the zero floor (allow negative rNPV).")

    # ---- sotp subcommand ------------------------------------------------
    p_sotp = sub.add_parser("sotp", help="Compute SOTP equity value and per-share price.")
    p_sotp.add_argument("--assets", required=True,
                        help='Comma-separated asset rNPV values ($M). E.g. "215,150,15".')
    p_sotp.add_argument("--net-cash", type=float, required=True,
                        help="Net cash (cash minus debt) ($M).")
    p_sotp.add_argument("--overhead", type=float, default=0.0,
                        help="PV of G&A overhead ($M). Default 0.")
    p_sotp.add_argument("--options", type=float, default=0.0,
                        help="Options value ($M), subtracted as a liability. Default 0.")
    p_sotp.add_argument("--shares", type=float, default=None,
                        help="BASIC shares outstanding (millions). If given, compute per-share price.")

    # ---- selftest subcommand --------------------------------------------
    sub.add_parser("selftest", help="Run built-in golden tests and exit 0 if all pass.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "selftest":
        return _run_selftest()

    elif args.cmd == "rnpv":
        result = asset_rnpv(
            pv_commercial=args.pv_commercial,
            loa=args.loa,
            pv_dev_cost=args.dev_cost,
            floor_zero=not args.no_floor,
        )
        print(f"rNPV = ${result:,.2f}M")
        return 0

    elif args.cmd == "sotp":
        asset_list = [float(x.strip()) for x in args.assets.split(",")]
        equity = sotp_equity(asset_list, net_cash=args.net_cash,
                             overhead_pv=args.overhead, options_value=args.options)
        print(f"SOTP Equity Value = ${equity:,.2f}M")
        if args.shares is not None:
            ps = per_share(equity, args.shares)
            print(f"Per Share = ${ps:,.2f}")
        return 0

    return 1  # unreachable


if __name__ == "__main__":
    sys.exit(main())
