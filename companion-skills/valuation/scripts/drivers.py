#!/usr/bin/env python3
"""
drivers.py — driver-based cash-flow construction for the `valuation` skill.

Two builders, one shared idea: don't hand the engine a black-box cash flow —
build it from operating drivers so every number is auditable.

A. Young / high-growth / cyclical FCFF (Damodaran Ch.22-23; special_cases.md §3)
   FCFF_t = Revenue_t × margin_t × (1 − tax_eff_t) − ΔRevenue_t / (Sales/Capital)
   - revenue grows off an explicit (decelerating) growth path
   - operating margin converges from its current level to a mature target
   - reinvestment is ΔRevenue / Sales-to-Capital (ROC is undefined while EBIT<0)
   - taxes respect an NOL carry-forward (0% until losses are used up)

B. Development-stage biotech/pharma drug commercial curve (Ch.28 rNPV foundation;
   rnpv_and_real_options.md §1). Produces pv_commercial (the risk-UNADJUSTED PV of
   a drug's post-launch cash flows) from clinical/commercial drivers — the biggest
   black-box input to rNPV. Feed it to rnpv.asset_rnpv(pv_commercial, loa, dev_cost).
     revenue curve: pre-launch 0 → linear ramp to peak → plateau → geometric LoE erosion
     NCF_t = revenue_t × margin (× (1−tax) if a tax rate is given)
     pv_commercial = Σ NCF_t / (1+r)^t

CLI:
  python3 drivers.py fcff --base 100 --growth 0.5,0.4,0.3 --cur-margin 0 \
      --tgt-margin 0.15 --s2c 2.0 --tax 0.25
  python3 drivers.py drug --peak 600 --launch 6 --ramp 4 --plateau 5 \
      --erosion-years 5 --erosion 0.4 --margin 0.70 --rate 0.12
  python3 drivers.py selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import dcf as dcf_mod  # noqa: E402  (pv_of_flows / dcf_value_explicit)


# --------------------------------------------------------------------------- A
def margin_path(current: float, target: float, years: int,
                converge: float = 0.5, mode: str = "fraction") -> List[float]:
    """Operating-margin path from `current` toward `target` over `years` years.

    mode="fraction" (default): each year closes fraction `converge` of the
        remaining gap — m_{t} = m_{t-1} + (target − m_{t-1}) × converge.
        converge=0.5 reproduces Damodaran's LinkedIn path ((m+target)/2);
        converge=1/3 reproduces his Tesla path. [Ch.23, printed p.297]
    mode="linear": straight-line interpolation, m_t = current + (target−current)·t/years.

    Returns the projected margins for years 1..years (the current level is NOT
    included in the list).
    """
    if years <= 0:
        return []
    out: List[float] = []
    if mode == "linear":
        for t in range(1, years + 1):
            out.append(current + (target - current) * (t / years))
    elif mode == "fraction":
        if not (0.0 < converge <= 1.0):
            raise ValueError(f"converge must be in (0,1]; got {converge}.")
        m = current
        for _ in range(years):
            m = m + (target - m) * converge
            out.append(m)
    else:
        raise ValueError(f"mode must be 'fraction' or 'linear'; got {mode!r}.")
    return out


def revenue_path(base_revenue: float, growth_rates) -> List[float]:
    """Revenues for years 1..N by compounding base_revenue through growth_rates."""
    revs: List[float] = []
    r = base_revenue
    for g in growth_rates:
        r = r * (1.0 + g)
        revs.append(r)
    return revs


def fcff_from_drivers(
    base_revenue: float,
    revenue_growth,
    current_margin: float,
    target_margin: float,
    sales_to_capital: float,
    tax_rate: float,
    margin_converge: float = 0.5,
    margin_mode: str = "fraction",
    nol: float = 0.0,
) -> dict:
    """Build an explicit FCFF stream from operating drivers [Ch.23 Steps 1-4].

    Returns a dict of parallel per-year lists (revenues, margins, ebit, tax,
    ebit_after_tax, reinvestment, fcff) plus the ending NOL balance. Reinvestment
    in year 1 is measured against `base_revenue`.
    """
    if sales_to_capital <= 0:
        raise ValueError(f"sales_to_capital must be > 0; got {sales_to_capital}.")
    revenues = revenue_path(base_revenue, revenue_growth)
    n = len(revenues)
    margins = margin_path(current_margin, target_margin, n, margin_converge, margin_mode)
    ebit, tax, eat, reinvest, fcff = [], [], [], [], []
    nol_balance = float(nol)
    prev_rev = base_revenue
    for i in range(n):
        e = revenues[i] * margins[i]
        ebit.append(e)
        if e <= 0.0:
            # loss: accumulate NOL, no tax
            nol_balance += -e
            t = 0.0
        else:
            shielded = min(e, nol_balance)
            nol_balance -= shielded
            taxable = e - shielded
            t = taxable * tax_rate
        tax.append(t)
        eat.append(e - t)
        rein = (revenues[i] - prev_rev) / sales_to_capital
        reinvest.append(rein)
        fcff.append((e - t) - rein)
        prev_rev = revenues[i]
    return {
        "revenues": revenues, "margins": margins, "ebit": ebit, "tax": tax,
        "ebit_after_tax": eat, "reinvestment": reinvest, "fcff": fcff,
        "nol_balance_end": nol_balance,
    }


def driver_dcf(
    base_revenue: float,
    revenue_growth,
    current_margin: float,
    target_margin: float,
    sales_to_capital: float,
    tax_rate: float,
    stable_growth: float,
    wacc: float,
    margin_converge: float = 0.5,
    margin_mode: str = "fraction",
    nol: float = 0.0,
    terminal_roc: Optional[float] = None,
    mid_year: bool = True,
    rf: Optional[float] = None,
) -> dict:
    """Full driver FCFF → enterprise value. Terminal FCFF uses a stable
    reinvestment rate g/terminal_roc when terminal_roc is given (Ch.23 Step 3);
    otherwise the last explicit FCFF is grown by (1+g).
    """
    d = fcff_from_drivers(base_revenue, revenue_growth, current_margin, target_margin,
                          sales_to_capital, tax_rate, margin_converge, margin_mode, nol)
    terminal_cf = None
    if terminal_roc:  # falsy (None or 0) → Gordon on the last flow; 0 would divide-by-zero
        # stable-phase FCFF = EBIT_term·(1−t)·(1 − g/ROC); EBIT_term from the last
        # explicit revenue grown by g at the target margin.
        rev_term = d["revenues"][-1] * (1.0 + stable_growth)
        ebit_term = rev_term * target_margin
        reinvest_rate = stable_growth / terminal_roc
        terminal_cf = ebit_term * (1.0 - tax_rate) * (1.0 - reinvest_rate)
    val = dcf_mod.dcf_value_explicit(d["fcff"], wacc, stable_growth,
                                     mid_year=mid_year, rf=rf, terminal_cf=terminal_cf)
    val["drivers"] = d
    return val


# --------------------------------------------------------------------------- B
def drug_revenue_curve(
    peak_sales: float,
    launch_year: int,
    ramp_years: int,
    plateau_years: int,
    erosion_years: int,
    erosion_rate: float,
) -> List[float]:
    """Per-year drug revenue: pre-launch 0 → linear ramp to peak → plateau →
    geometric loss-of-exclusivity erosion. Year 1 is the first calendar year;
    the drug's first sales fall in `launch_year`.
    """
    if launch_year < 1:
        raise ValueError(f"launch_year must be >= 1; got {launch_year}.")
    if ramp_years < 1:
        raise ValueError(f"ramp_years must be >= 1; got {ramp_years}.")
    if not (0.0 <= erosion_rate < 1.0):
        raise ValueError(f"erosion_rate must be in [0,1); got {erosion_rate}.")
    curve = [0.0] * (launch_year - 1)
    for i in range(1, ramp_years + 1):
        curve.append(peak_sales * i / ramp_years)     # linear ramp to peak
    for _ in range(plateau_years):
        curve.append(peak_sales)                       # plateau at peak
    rev = peak_sales
    for _ in range(erosion_years):
        rev = rev * (1.0 - erosion_rate)               # geometric LoE erosion
        curve.append(rev)
    return curve


def drug_commercial_pv(
    peak_sales: float,
    launch_year: int,
    ramp_years: int,
    plateau_years: int,
    erosion_years: int,
    erosion_rate: float,
    margin: float,
    discount_rate: float,
    tax_rate: Optional[float] = None,
) -> dict:
    """PV of a drug's (risk-UNADJUSTED) commercial cash flows → pv_commercial.

    NCF_t = revenue_t × margin, optionally × (1 − tax_rate). Discounted at
    year-end (drug cash flows are conventionally taken at period end). Feed the
    returned pv_commercial into rnpv.asset_rnpv(pv_commercial, loa, dev_cost);
    risk stays in LoA, NOT in an inflated discount rate. [rnpv §1, §8]
    """
    revenues = drug_revenue_curve(peak_sales, launch_year, ramp_years,
                                  plateau_years, erosion_years, erosion_rate)
    after_tax = margin * (1.0 - (tax_rate or 0.0))
    ncf = [r * after_tax for r in revenues]
    pv = 0.0
    for t, cf in enumerate(ncf, start=1):
        pv += cf / (1.0 + discount_rate) ** t
    return {"revenues": revenues, "ncf": ncf, "pv_commercial": pv,
            "peak_ncf": peak_sales * after_tax}


# --------------------------------------------------------------------------- selftest
def _selftest() -> bool:
    checks = []

    def approx(name, got, exp, tol=5e-4):
        checks.append((name, abs(got - exp) <= tol, f"got {got:.6f} exp {exp:.6f}"))

    # G1a — Damodaran LinkedIn margin path (current 8.23%, target 15%, half gap) [p.297]
    li = margin_path(0.0823, 0.15, 10, converge=0.5)
    li_book = [0.1162, 0.1331, 0.1415, 0.1458, 0.1479, 0.1489, 0.1495, 0.1497, 0.1499, 0.1499]
    checks.append(("G1a LinkedIn margin path reproduces book [p.297]",
                   all(abs(a - b) < 6e-4 for a, b in zip(li, li_book)),
                   f"{[round(x,4) for x in li]}"))
    # G1b — Damodaran Tesla margin path (current -69.87%, target 10%, 1/3 gap) [p.297]
    te = margin_path(-0.6987, 0.10, 10, converge=1.0 / 3.0)
    te_book = [-0.4325, -0.2550, -0.1367, -0.0578, -0.0052, 0.0299, 0.0533, 0.0688, 0.0792, 0.0861]
    checks.append(("G1b Tesla margin path reproduces book [p.297]",
                   all(abs(a - b) < 6e-4 for a, b in zip(te, te_book)),
                   f"{[round(x,4) for x in te]}"))

    # G2 — full FCFF-from-drivers, hand-verified arithmetic
    d = fcff_from_drivers(base_revenue=100.0, revenue_growth=[0.5, 0.4, 0.3],
                          current_margin=0.0, target_margin=0.15, sales_to_capital=2.0,
                          tax_rate=0.25, margin_converge=0.5, margin_mode="linear")
    # revenues 150,210,273; margins .05,.10,.15; ebit 7.5,21,40.95;
    # tax .25 → eat 5.625,15.75,30.7125; reinvest (50,60,63)/2 = 25,30,31.5
    exp_fcff = [5.625 - 25.0, 15.75 - 30.0, 30.7125 - 31.5]
    checks.append(("G2 driver revenues 150/210/273",
                   d["revenues"] == [150.0, 210.0, 273.0], f"{d['revenues']}"))
    checks.append(("G2 driver FCFF hand-check [-19.375,-14.25,-0.7875]",
                   all(abs(a - b) < 1e-6 for a, b in zip(d["fcff"], exp_fcff)),
                   f"{[round(x,4) for x in d['fcff']]}"))

    # G3 — NOL zeroes tax until exhausted, then marginal tax applies
    n1 = fcff_from_drivers(100.0, [0.5], 0.20, 0.20, 1e9, 0.30, nol=50.0)
    checks.append(("G3 NOL: EBIT 30 vs NOL 50 → tax 0, NOL end 20",
                   abs(n1["tax"][0]) < 1e-9 and abs(n1["nol_balance_end"] - 20.0) < 1e-9,
                   f"tax={n1['tax'][0]} nol_end={n1['nol_balance_end']}"))
    n2 = fcff_from_drivers(100.0, [0.5, 0.5], 0.20, 0.20, 1e9, 0.30, nol=50.0)
    # Y1 ebit 30 (NOL 50→20); Y2 rev 225, ebit 45, taxable 45-20=25, tax 7.5
    checks.append(("G3 NOL exhaustion: Y2 tax 7.5, NOL end 0",
                   abs(n2["tax"][1] - 7.5) < 1e-9 and abs(n2["nol_balance_end"]) < 1e-9,
                   f"Y2 tax={n2['tax'][1]} nol_end={n2['nol_balance_end']}"))

    # G4 — drug commercial curve + PV, hand-verified
    curve = drug_revenue_curve(1000.0, launch_year=1, ramp_years=2, plateau_years=2,
                               erosion_years=2, erosion_rate=0.5)
    checks.append(("G4 drug curve [500,1000,1000,1000,500,250]",
                   curve == [500.0, 1000.0, 1000.0, 1000.0, 500.0, 250.0], f"{curve}"))
    r = 0.10
    ncf = [c * 0.5 for c in curve]
    exp_pv = sum(cf / (1.0 + r) ** t for t, cf in enumerate(ncf, start=1))
    dc = drug_commercial_pv(1000.0, 1, 2, 2, 2, 0.5, margin=0.5, discount_rate=r)
    approx("G4 drug pv_commercial matches independent sum", dc["pv_commercial"], exp_pv, 1e-6)

    # G5 — UPB-style order-of-magnitude sanity check. The reference PV (~$850M,
    # rnpv_and_real_options.md §1) is explicitly "illustrative" and leaves the
    # erosion depth unspecified; a full 5-year peak plateau lands a bit higher,
    # which is correct — this only guards against an order-of-magnitude error.
    upb = drug_commercial_pv(600.0, launch_year=6, ramp_years=4, plateau_years=5,
                             erosion_years=5, erosion_rate=0.4, margin=0.70, discount_rate=0.12)
    checks.append(("G5 UPB-style PV order-of-magnitude ($700M-$1.3B for $600M peak)",
                   700.0 <= upb["pv_commercial"] <= 1300.0,
                   f"pv_commercial={upb['pv_commercial']:.1f}"))

    # G6 — driver_dcf end-to-end sane (positive EV, terminal-ROC path runs)
    dd = driver_dcf(base_revenue=200.0, revenue_growth=[0.25, 0.20, 0.15, 0.10],
                    current_margin=0.05, target_margin=0.15, sales_to_capital=2.5,
                    tax_rate=0.25, stable_growth=0.03, wacc=0.09, terminal_roc=0.12,
                    mid_year=True, rf=0.04)
    checks.append(("G6 driver_dcf produces finite EV > 0 with terminal-ROC",
                   isinstance(dd["total_value"], float) and dd["total_value"] > 0,
                   f"EV={dd['total_value']:.2f} tv_pct={dd['tv_pct']:.2%}"))

    print("=" * 64); print("drivers.py selftest")
    ok = True
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if not passed:
            print(f"         {detail}")
        ok = ok and passed
    print("=" * 64); print("ALL PASS" if ok else "SOME FAILED")
    return ok


# --------------------------------------------------------------------------- CLI
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="drivers.py", description="Driver-based cash-flow builders")
    sub = p.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fcff", help="Young-firm FCFF from revenue/margin/reinvestment drivers")
    pf.add_argument("--base", type=float, required=True)
    pf.add_argument("--growth", type=str, required=True, help='e.g. "0.5,0.4,0.3"')
    pf.add_argument("--cur-margin", type=float, required=True)
    pf.add_argument("--tgt-margin", type=float, required=True)
    pf.add_argument("--s2c", type=float, required=True, help="sales-to-capital ratio")
    pf.add_argument("--tax", type=float, required=True)
    pf.add_argument("--converge", type=float, default=0.5)
    pf.add_argument("--margin-mode", choices=["fraction", "linear"], default="fraction")
    pf.add_argument("--nol", type=float, default=0.0)

    pd = sub.add_parser("drug", help="Biotech drug commercial curve → pv_commercial")
    pd.add_argument("--peak", type=float, required=True)
    pd.add_argument("--launch", type=int, required=True)
    pd.add_argument("--ramp", type=int, required=True)
    pd.add_argument("--plateau", type=int, required=True)
    pd.add_argument("--erosion-years", type=int, required=True)
    pd.add_argument("--erosion", type=float, required=True)
    pd.add_argument("--margin", type=float, required=True)
    pd.add_argument("--rate", type=float, required=True)
    pd.add_argument("--tax", type=float, default=None)

    sub.add_parser("selftest")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.cmd == "selftest":
        sys.exit(0 if _selftest() else 1)
    elif args.cmd == "fcff":
        g = [float(x) for x in args.growth.split(",")]
        d = fcff_from_drivers(args.base, g, args.cur_margin, args.tgt_margin,
                              args.s2c, args.tax, args.converge, args.margin_mode, args.nol)
        print("Year   Revenue   Margin      EBIT   Reinvest      FCFF")
        for i in range(len(d["fcff"])):
            print(f"{i+1:>4}  {d['revenues'][i]:>8.1f}  {d['margins'][i]:>6.2%}  "
                  f"{d['ebit'][i]:>8.1f}  {d['reinvestment'][i]:>8.1f}  {d['fcff'][i]:>8.1f}")
    elif args.cmd == "drug":
        r = drug_commercial_pv(args.peak, args.launch, args.ramp, args.plateau,
                               args.erosion_years, args.erosion, args.margin, args.rate, args.tax)
        print(f"pv_commercial = ${r['pv_commercial']:,.1f}M   peak_ncf = ${r['peak_ncf']:,.1f}M")
        print("revenue curve:", [round(x, 1) for x in r["revenues"]])


if __name__ == "__main__":
    main()
