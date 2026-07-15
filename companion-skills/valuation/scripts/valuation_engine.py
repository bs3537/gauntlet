#!/usr/bin/env python3
"""
valuation_engine.py — orchestrator for the `valuation` skill.

Consumes a valuation_plan.json (see schemas/valuation_plan.schema.json), routes to
the right method, computes an authoritative `results` dict (audited Python math from
cost_of_capital.py / dcf.py / rnpv.py / relative_val.py), writes results.json, builds
the Excel model (excel_builder.py), and validates (validate_valuation.py).

The agent/skill gathers data (FMP /stable/, Perplexity, SEC, BioMCP — see
references/data_sourcing_wsl.md) and assembles the plan; this engine is the
deterministic compute+assemble+validate core.

CLI:
  python3 valuation_engine.py run --plan plan.json --out-dir DIR
  python3 valuation_engine.py classify --inputs inputs.json
  python3 valuation_engine.py selftest
"""
import sys, os, json, argparse, math
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import cost_of_capital as coc      # noqa: E402
import dcf as dcf_mod              # noqa: E402
import rnpv as rnpv_mod            # noqa: E402
import relative_val as rel_mod     # noqa: E402
import drivers as drivers_mod      # noqa: E402
import excel_builder               # noqa: E402
import validate_valuation          # noqa: E402

PAGES = {
    'fcff': ['FCFF p.380-399', 'WACC market-value weights p.220', 'terminal g<=rf p.306-307'],
    'fcfe': ['FCFE p.351-379', 'cost of equity (CAPM) p.182-228'],
    'ddm':  ['DDM Gordon/2-stage p.323-350'],
    'apv':  ['APV = unlevered value + PV(tax shield) p.396-422'],
    'rnpv': ['risk-adjusted NPV / SOTP', 'patent-as-option p.781-787', 'dilution already in CFs p.371/443/658'],
    'relative': ['relative-valuation 4-step p.453-467', 'EV/EBITDA determinants p.500-510'],
}


def _round_to(x, step=0.50):
    return round(x / step) * step


# --------------------------------------------------------------------------- WACC
def compute_wacc(w, tax_default=0.24):
    if not w:
        return None
    if w.get('wacc') is not None:
        out = {'wacc': w['wacc']}
        out.update({k: w.get(k) for k in ('rf', 'erp', 'beta', 'tax_rate',
                    'cost_of_equity', 'cost_of_debt_after_tax', 'e_val', 'd_val',
                    'crp', 'tax_band')})
        return out
    rf, erp = w.get('rf'), w.get('erp')
    tax = w.get('tax_rate', tax_default)
    beta = w.get('beta')
    if beta is None and w.get('peer_betas'):
        beta = coc.bottom_up_beta(w['peer_betas'], w['peer_de'], tax, w.get('firm_de', 0.0))
    ke = coc.cost_of_equity(rf, beta, erp)
    kd_at = w.get('cost_of_debt_after_tax')
    if kd_at is None and w.get('interest_coverage') is not None:
        _, spread = coc.synthetic_rating(w['interest_coverage'])
        kd_at = coc.cost_of_debt_after_tax(rf, spread, tax)
    e_val = w.get('equity_value', 1.0)
    d_val = w.get('debt_value', 0.0)
    wv = coc.wacc(ke, kd_at if kd_at is not None else ke, e_val, d_val)
    return {'rf': rf, 'erp': erp, 'beta': beta, 'tax_rate': tax, 'cost_of_equity': ke,
            'cost_of_debt_after_tax': kd_at, 'e_val': e_val, 'd_val': d_val, 'wacc': wv,
            'crp': w.get('crp'), 'tax_band': w.get('tax_band')}


def _projection(flows, growth_rates, rate, mid_year):
    n = len(flows)
    rows = []
    for i in range(n):
        period = (i + 1) - (0.5 if mid_year else 0.0)
        df = 1.0 / (1.0 + rate) ** period
        rows.append({'year': i + 1, 'growth': growth_rates[i], 'cf': flows[i],
                     'period': period, 'disc_factor': df, 'pv': flows[i] * df})
    return rows


def _sensitivity(base_cf, growth_rates, rate, stable_growth, mid_year, rf,
                 net_debt, shares, options):
    rrows = [round(rate + d, 4) for d in (-0.01, 0.0, 0.01)]
    gcols = [round(stable_growth + d, 4) for d in (-0.005, 0.0, 0.005)]
    grid = []
    for rr in rrows:
        line = []
        for gg in gcols:
            try:
                res = dcf_mod.dcf_value(base_cf, growth_rates, rr, gg, mid_year=mid_year, rf=rf)
                eq = dcf_mod.bridge_to_equity(res['total_value'], net_debt=net_debt)
                val = dcf_mod.value_per_share(eq, shares, options) if shares else eq
                line.append(round(val, 2))
            except Exception:
                line.append(None)
        grid.append(line)
    return {'row_var': 'Discount rate', 'col_var': 'Terminal g',
            'row_vals': rrows, 'col_vals': gcols, 'grid': grid}


def _sensitivity_explicit(flows, rate, stable_growth, mid_year, rf, net_debt,
                          shares, options, terminal_cf_fn=None):
    """WACC × terminal-g sensitivity for a driver-built (explicit) FCFF stream.
    terminal_cf_fn(g) recomputes the stable-phase FCFF for each perturbed g."""
    rrows = [round(rate + delta, 4) for delta in (-0.01, 0.0, 0.01)]
    gcols = [round(stable_growth + delta, 4) for delta in (-0.005, 0.0, 0.005)]
    grid = []
    for rr in rrows:
        line = []
        for gg in gcols:
            try:
                tcf = terminal_cf_fn(gg) if terminal_cf_fn else None
                res = dcf_mod.dcf_value_explicit(flows, rr, gg, mid_year=mid_year,
                                                 rf=rf, terminal_cf=tcf)
                eq = dcf_mod.bridge_to_equity(res['total_value'], net_debt=net_debt)
                val = dcf_mod.value_per_share(eq, shares, options) if shares else eq
                line.append(round(val, 2))
            except Exception:
                line.append(None)
        grid.append(line)
    return {'row_var': 'Discount rate', 'col_var': 'Terminal g',
            'row_vals': rrows, 'col_vals': gcols, 'grid': grid}


# --------------------------------------------------------------------------- methods
def run_dcf(plan, method):
    d = plan['dcf']
    mid = d.get('mid_year', True)
    wb = compute_wacc(plan.get('wacc'), d.get('tax_rate', 0.24))
    if method == 'fcfe':
        # FCFE is an equity-level cash flow: discount at cost of EQUITY (ke),
        # never at WACC. Supply dcf.rate (a precomputed ke) or wacc build inputs
        # so the engine computes cost_of_equity. The silent WACC fallback the
        # old code allowed is prohibited [method_selection.md §3]. [report D3]
        rate = d.get('rate') or (wb or {}).get('cost_of_equity')
        if rate is None:
            raise ValueError(
                "FCFE requires a cost of EQUITY (ke), not a firm WACC. Supply "
                "dcf.rate (precomputed ke) or wacc build inputs (rf/erp/beta) so "
                "the engine can compute cost_of_equity. Discounting FCFE at WACC "
                "is prohibited [method_selection.md §3]. [report D3]")
    else:  # fcff
        rate = (wb or {}).get('wacc') or d.get('rate')
    if rate is None:
        raise ValueError("No discount rate / WACC available for DCF.")
    flows = dcf_mod.project_cashflows(d['base_cf'], d['growth_rates'])
    res = dcf_mod.dcf_value(d['base_cf'], d['growth_rates'], rate, d['stable_growth'],
                            mid_year=mid, rf=d.get('rf'))
    ev = res['total_value']
    if method == 'fcfe':
        equity = ev
    else:
        equity = dcf_mod.bridge_to_equity(ev, net_debt=d.get('net_debt', 0.0),
                                          minority_interest=d.get('minority_interest', 0.0),
                                          nonoperating_assets=d.get('nonoperating_assets', 0.0))
    shares = d.get('shares')
    options = d.get('options_value', 0.0)
    vps = dcf_mod.value_per_share(equity, shares, options) if shares else None
    dcf_section = {
        'base_cf': d['base_cf'], 'stable_growth': d['stable_growth'], 'rate': rate,
        'rf': d.get('rf'), 'roc': d.get('roc'), 'mid_year': mid,
        'projection': _projection(flows, d['growth_rates'], rate, mid),
        'terminal_value': res['tv_undiscounted'], 'pv_terminal': res['terminal_pv'],
        'explicit_pv': res['explicit_pv'], 'enterprise_value': ev, 'tv_pct': res['tv_pct'],
        'net_debt': d.get('net_debt', 0.0), 'equity_value': equity,
        'shares': shares, 'value_per_share': vps, 'options_value': options,
    }
    out = {'method': method, 'company': plan.get('company', {}), 'wacc_build': wb,
           'dcf': dcf_section, 'warnings': list(res.get('warnings', [])),
           'methodology_pages': PAGES[method]}
    if shares:
        out['sensitivity'] = _sensitivity(d['base_cf'], d['growth_rates'], rate,
                                           d['stable_growth'], mid, d.get('rf'),
                                           d.get('net_debt', 0.0), shares, options)
    return out


def _rho_u(d, wb):
    """Unlevered cost of equity (ρu) for APV: ρu = rf + β_u × ERP.

    Uses an explicit dcf.rho_u if supplied; otherwise unlevers the levered beta
    from the WACC build (β_u = β_L / [1 + (1−t)·D/E]) and re-runs CAPM. Returns
    None when neither an explicit ρu nor sufficient build inputs are available —
    the caller then hard-errors rather than silently falling back to WACC.
    """
    if d.get('rho_u') is not None:
        return d['rho_u']
    if not wb:
        return None
    rf, erp, beta = wb.get('rf'), wb.get('erp'), wb.get('beta')
    if rf is None or erp is None or beta is None:
        return None
    tax = wb.get('tax_rate') if wb.get('tax_rate') is not None else 0.24
    e_val = wb.get('e_val') or 1.0
    d_val = wb.get('d_val') or 0.0
    de = (d_val / e_val) if e_val else 0.0
    beta_u = coc.unlever_beta(beta, de, tax)
    return coc.cost_of_equity(rf, beta_u, erp)


def run_apv(plan):
    """Adjusted Present Value [dcf_fcff_fcfe_ddm.md §6, printed p.398–401].

    Real APV — NOT WACC-DCF with a tax shield bolted on (the pre-fix double
    count [report D4]):

        V_u  = PV(FCFF) discounted at ρu (unlevered cost of equity)
        APV  = V_u + PV(tax shields) − PV(expected distress cost)
        Equity = APV − net debt (+ non-operating − minority)

    ρu is used precisely because it does NOT embed the interest tax shield; the
    shield is then added once, explicitly. Discounting at WACC would count it
    twice. Reads cash-flow inputs from the `dcf` block; APV-specific inputs are
    dcf.rho_u, dcf.tax_shield_pv, dcf.distress_pv.
    """
    d = plan['dcf']
    mid = d.get('mid_year', True)
    wb = compute_wacc(plan.get('wacc'), d.get('tax_rate', 0.24))
    rho_u = _rho_u(d, wb)
    if rho_u is None:
        raise ValueError(
            "APV requires an unlevered cost of equity ρu. Supply dcf.rho_u "
            "directly, or wacc build inputs (rf, erp, beta or peer_betas, plus "
            "equity_value/debt_value) so the engine can unlever beta. APV must "
            "NOT be discounted at WACC — that embeds the tax shield and then "
            "adding tax_shield_pv double-counts it. [report D4]")
    res = dcf_mod.dcf_value(d['base_cf'], d['growth_rates'], rho_u, d['stable_growth'],
                            mid_year=mid, rf=d.get('rf'))
    v_u = res['total_value']                       # unlevered firm (enterprise) value
    tax_shield_pv = d.get('tax_shield_pv', 0.0) or 0.0
    distress_pv = d.get('distress_pv', 0.0) or 0.0
    apv_firm = v_u + tax_shield_pv - distress_pv    # levered enterprise value
    equity = dcf_mod.bridge_to_equity(apv_firm, net_debt=d.get('net_debt', 0.0),
                                      minority_interest=d.get('minority_interest', 0.0),
                                      nonoperating_assets=d.get('nonoperating_assets', 0.0))
    shares = d.get('shares')
    options = d.get('options_value', 0.0)
    vps = dcf_mod.value_per_share(equity, shares, options) if shares else None
    dcf_section = {
        'base_cf': d['base_cf'], 'stable_growth': d['stable_growth'], 'rate': rho_u,
        'rho_u': rho_u, 'rf': d.get('rf'), 'roc': d.get('roc'), 'mid_year': mid,
        'projection': _projection(res['flows'], d['growth_rates'], rho_u, mid),
        'terminal_value': res['tv_undiscounted'], 'pv_terminal': res['terminal_pv'],
        'explicit_pv': res['explicit_pv'], 'unlevered_value': v_u,
        'tax_shield_pv': tax_shield_pv, 'distress_pv': distress_pv,
        'enterprise_value': apv_firm, 'tv_pct': res['tv_pct'],
        'net_debt': d.get('net_debt', 0.0), 'equity_value': equity,
        'shares': shares, 'value_per_share': vps, 'options_value': options,
    }
    out = {'method': 'apv', 'company': plan.get('company', {}), 'wacc_build': wb,
           'dcf': dcf_section, 'warnings': list(res.get('warnings', [])),
           'methodology_pages': PAGES['apv']}
    if shares:
        out['sensitivity'] = _sensitivity(d['base_cf'], d['growth_rates'], rho_u,
                                           d['stable_growth'], mid, d.get('rf'),
                                           d.get('net_debt', 0.0), shares, options)
    return out


def run_fcff_drivers(plan):
    """Driver-based FCFF [Damodaran Ch.22–23]: build the FCFF stream from
    revenue growth → operating-margin convergence → sales-to-capital reinvestment
    (with NOL tracking), then discount at WACC. Used for young/high-growth/
    cyclical firms whose FCFF cannot be a naked base_cf + growth list.
    """
    d = plan['dcf']
    drv = d['drivers']
    mid = d.get('mid_year', True)
    g = d['stable_growth']
    wb = compute_wacc(plan.get('wacc'), d.get('tax_rate', 0.24))
    rate = (wb or {}).get('wacc') or d.get('rate')
    if rate is None:
        raise ValueError("Driver-based FCFF needs a WACC — supply the wacc block or dcf.rate.")
    tax = drv.get('tax_rate', d.get('tax_rate', 0.24))
    dd = drivers_mod.fcff_from_drivers(
        drv['base_revenue'], drv['revenue_growth'], drv['current_margin'],
        drv['target_margin'], drv['sales_to_capital'], tax,
        drv.get('margin_converge', 0.5), drv.get('margin_mode', 'fraction'),
        drv.get('nol', 0.0))
    if not dd['fcff']:
        # Guard BEFORE terminal_cf_fn's def-time default arg reads revenues[-1]. [verifier]
        raise ValueError("Driver-based FCFF needs a non-empty revenue_growth path.")
    troc = drv.get('terminal_roc')
    terminal_cf_fn = None
    if troc:
        def terminal_cf_fn(gg, _rev=dd['revenues'][-1], _m=drv['target_margin'], _t=tax, _roc=troc):
            return _rev * (1.0 + gg) * _m * (1.0 - _t) * (1.0 - gg / _roc)
    terminal_cf = terminal_cf_fn(g) if terminal_cf_fn else None
    res = dcf_mod.dcf_value_explicit(dd['fcff'], rate, g, mid_year=mid,
                                     rf=d.get('rf'), terminal_cf=terminal_cf)
    ev = res['total_value']
    equity = dcf_mod.bridge_to_equity(ev, net_debt=d.get('net_debt', 0.0),
                                      minority_interest=d.get('minority_interest', 0.0),
                                      nonoperating_assets=d.get('nonoperating_assets', 0.0))
    shares = d.get('shares')
    options = d.get('options_value', 0.0)
    vps = dcf_mod.value_per_share(equity, shares, options) if shares else None
    proj = []
    prev_rev = drv['base_revenue']
    for i in range(len(dd['fcff'])):
        period = (i + 1) - (0.5 if mid else 0.0)
        df = 1.0 / (1.0 + rate) ** period
        rev_growth = (dd['revenues'][i] / prev_rev - 1.0) if prev_rev else None
        prev_rev = dd['revenues'][i]
        proj.append({'year': i + 1, 'revenue': dd['revenues'][i], 'margin': dd['margins'][i],
                     'ebit': dd['ebit'][i], 'tax': dd['tax'][i],
                     'ebit_after_tax': dd['ebit_after_tax'][i],
                     'reinvestment': dd['reinvestment'][i], 'growth': rev_growth,
                     'cf': dd['fcff'][i], 'period': period, 'disc_factor': df,
                     'pv': dd['fcff'][i] * df})
    dcf_section = {
        'base_cf': dd['fcff'][0] if dd['fcff'] else None, 'stable_growth': g, 'rate': rate,
        'rf': d.get('rf'), 'roc': troc, 'mid_year': mid, 'driver_based': True,
        'drivers': {'base_revenue': drv['base_revenue'], 'current_margin': drv['current_margin'],
                    'target_margin': drv['target_margin'], 'sales_to_capital': drv['sales_to_capital'],
                    'margin_converge': drv.get('margin_converge', 0.5),
                    'margin_mode': drv.get('margin_mode', 'fraction'),
                    'nol': drv.get('nol', 0.0), 'terminal_roc': troc,
                    'nol_balance_end': dd['nol_balance_end']},
        'projection': proj, 'terminal_value': res['tv_undiscounted'],
        'pv_terminal': res['terminal_pv'], 'explicit_pv': res['explicit_pv'],
        'enterprise_value': ev, 'tv_pct': res['tv_pct'], 'net_debt': d.get('net_debt', 0.0),
        'equity_value': equity, 'shares': shares, 'value_per_share': vps,
        'options_value': options,
    }
    out = {'method': 'fcff', 'company': plan.get('company', {}), 'wacc_build': wb,
           'dcf': dcf_section, 'warnings': list(res.get('warnings', [])),
           'methodology_pages': PAGES['fcff'] + ['driver-based FCFF: revenue→margin→reinvestment Ch.22-23 p.643-685']}
    if shares:
        out['sensitivity'] = _sensitivity_explicit(dd['fcff'], rate, g, mid, d.get('rf'),
                                                    d.get('net_debt', 0.0), shares, options,
                                                    terminal_cf_fn)
    return out


def run_ddm(plan):
    d = plan['ddm']
    ke = d.get('ke_stable') or d.get('ke_high')
    g = d['stable_growth']
    rf = d.get('rf')
    # Enforce the economic terminal-growth cap g <= rf on the DDM path too. The
    # old run_ddm never populated rf, so the validator's cap silently never
    # fired for dividend models. [report D6]
    if rf is not None and g > rf + 1e-9:
        raise ValueError(
            f"DDM stable growth ({g:.4%}) exceeds risk-free rate ({rf:.4%}); no "
            f"firm grows forever faster than the economy [p.307]. [report D6]")
    if d.get('high_years'):
        p0 = dcf_mod.ddm_two_stage(d['dps0'], d['high_growth'], d['high_years'],
                                   g, d['ke_high'], d['ke_stable'],
                                   payout_stable=d.get('payout_stable'),
                                   payout_high=d.get('payout_high'))
    else:
        p0 = dcf_mod.ddm_value(d['dps1'], ke, g)
    shares = plan.get('dcf', {}).get('shares') or d.get('shares')
    equity = p0 * shares if shares else None
    # ROE implied by the stable payout (payout = 1 − g/ROE ⇒ ROE = g/(1−payout)),
    # so the validator can test value-creating growth (ROE vs ke). [report D13]
    roc = d.get('roc')
    ps = d.get('payout_stable')
    if roc is None and ps is not None and ps < 1.0 and g:
        roc = g / (1.0 - ps)
    dcf_section = {'rate': ke, 'stable_growth': g, 'rf': rf, 'roc': roc,
                   'value_per_share': p0, 'equity_value': equity, 'shares': shares,
                   'enterprise_value': None, 'projection': [], 'tv_pct': None}
    return {'method': 'ddm', 'company': plan.get('company', {}), 'wacc_build': None,
            'dcf': dcf_section, 'warnings': [], 'methodology_pages': PAGES['ddm']}


def run_rnpv(plan):
    r = plan['rnpv']
    assets_out, rnpvs = [], []
    shares = r.get('shares')
    for a in r['assets']:
        pv_c = a.get('pv_commercial')
        comm = a.get('commercial')
        commercial_curve = None
        if pv_c is None and comm:
            # Build pv_commercial from a drug commercial curve (launch → ramp →
            # plateau → LoE erosion → margin → discount) so the biggest input to
            # rNPV is auditable instead of a hand-supplied black box. Risk stays
            # in LoA below — the curve is risk-UNADJUSTED. [Ch.28 / drivers.py]
            cres = drivers_mod.drug_commercial_pv(
                comm['peak_sales'], comm['launch_year'], comm['ramp_years'],
                comm['plateau_years'], comm['erosion_years'], comm['erosion_rate'],
                comm['margin'], comm['discount_rate'], comm.get('tax_rate'))
            pv_c = cres['pv_commercial']
            commercial_curve = cres['revenues']
        if pv_c is None:
            # peak_sales is a headline revenue figure, NOT a present value; the
            # old silent fallback treated undiscounted revenue as a PV. [report D9]
            raise ValueError(
                f"rNPV asset '{a.get('name','?')}': supply pv_commercial (PV of "
                f"risk-unadjusted commercial cash flows, $M) or a `commercial` "
                f"driver block. peak_sales is a headline figure, not a present "
                f"value, and is not a substitute. [report D9]")
        # A contractually committed program cannot be abandoned, so it must be
        # allowed to carry a negative rNPV — do not floor it. [report D15]
        committed = a.get('committed', False)
        floor = a.get('floor_zero', True) and not committed
        val = rnpv_mod.asset_rnpv(pv_c, a['loa'], a.get('pv_dev_cost', 0.0),
                                  floor_zero=floor)
        rnpvs.append(val)
        assets_out.append({'name': a.get('name', '?'),
                           'peak_sales': a.get('peak_sales') or (comm.get('peak_sales') if comm else None),
                           'loa': a['loa'], 'pv_commercial': pv_c,
                           'pv_commercial_built': commercial_curve is not None,
                           'commercial_curve': commercial_curve,
                           'pv_dev_cost': a.get('pv_dev_cost', 0.0),
                           'committed': committed, 'rnpv': val,
                           'per_share': (val / shares) if shares else None})
    pipeline = float(sum(rnpvs))
    net_cash = r.get('net_cash', 0.0)
    overhead = r.get('overhead_pv', 0.0)
    options_value = r.get('options_value', 0.0)
    # Options subtracted as a liability; per-share divides by BASIC shares. [D10]
    equity = rnpv_mod.sotp_equity(rnpvs, net_cash, overhead, options_value=options_value)
    vps = rnpv_mod.per_share(equity, shares) if shares else None
    scen_section, sw, rounded = [], None, None
    if r.get('scenarios'):
        pairs = [(s['prob'], s['target']) for s in r['scenarios']]
        sw = rnpv_mod.scenario_weighted(pairs)
        rounded = _round_to(sw, 0.50)
        scen_section = [{'name': s.get('name'), 'prob': s['prob'], 'target': s['target']}
                        for s in r['scenarios']]
    rnpv_section = {'assets': assets_out, 'pipeline_subtotal': pipeline,
                    'net_cash': net_cash, 'overhead_pv': overhead,
                    'options_value': options_value, 'equity_value': equity,
                    'shares': shares, 'value_per_share': vps, 'scenarios': scen_section,
                    'scenario_weighted': sw, 'rounded_target': rounded}
    return {'method': 'rnpv', 'company': plan.get('company', {}), 'rnpv': rnpv_section,
            'warnings': [], 'methodology_pages': PAGES['rnpv']}


def run_relative(plan):
    r = plan['relative']
    pm = [p['multiple'] for p in r['peers']]
    out = rel_mod.peer_implied_value(r['target_metric'], pm, stat=r.get('stat', 'median'),
                                     exclude_outliers=r.get('exclude_outliers', False))
    import numpy as np
    q1 = float(np.percentile(pm, 25)); q3 = float(np.percentile(pm, 75))
    metric = r.get('metric_name', 'EV/EBITDA')
    implied_value = out['implied_value']
    net_debt = r.get('net_debt', 0.0)
    shares = r.get('shares')
    mu = metric.upper().replace(' ', '')
    is_ev = mu.startswith('EV/') or 'ENTERPRISE' in mu
    # Resolve the target_metric basis. EV/* multiples ALWAYS apply to an aggregate
    # metric (EBITDA, sales). Equity (P/*) multiples are ambiguous: target_metric
    # may be per-share (EPS/BVPS/SPS) OR an aggregate ($M net income / book equity /
    # sales), so `basis` MUST be supplied — inferring it silently is exactly the
    # dual-unit footgun that turned $5bn equity into $250bn. [report D7]
    basis = r.get('basis')
    if basis is None:
        if is_ev:
            basis = 'aggregate'
        else:
            raise ValueError(
                "relative.basis is required for equity (P/*) multiples: set "
                "'per_share' (target_metric = EPS/BVPS/SPS, per share) or "
                "'aggregate' (target_metric = total net income / book equity / "
                "sales, $M). Passing an aggregate metric as if per-share yields an "
                "order-of-magnitude error. [report D7]")
    if basis not in ('per_share', 'aggregate'):
        raise ValueError(f"relative.basis must be 'per_share' or 'aggregate', got {basis!r}.")
    if is_ev and basis == 'per_share':
        raise ValueError("EV/* multiples operate on aggregate metrics (EBITDA, sales); "
                         "basis must be 'aggregate'. [report D7]")

    if is_ev:
        # implied_value is an aggregate enterprise value → bridge to equity
        equity = implied_value - net_debt
        per_share = (equity / shares) if shares else None
    elif basis == 'per_share':
        per_share = implied_value            # price per share directly
        equity = per_share * shares if shares else None
    else:  # equity multiple, aggregate basis
        equity = implied_value               # aggregate equity value
        per_share = (equity / shares) if shares else None

    rel_section = {'metric_name': metric, 'basis': basis, 'target_metric': r['target_metric'],
                   'peers': r['peers'], 'median_multiple': out['multiple_used'],
                   'implied_value': implied_value, 'low': out['low'], 'high': out['high'],
                   'low_multiple': q1, 'high_multiple': q3, 'outliers': out['outliers'],
                   'outliers_excluded': out['outliers_excluded'],
                   'net_debt': net_debt, 'shares': shares, 'equity_value': equity,
                   'implied_per_share': per_share}
    return {'method': 'relative', 'company': plan.get('company', {}), 'relative': rel_section,
            'warnings': [], 'methodology_pages': PAGES['relative']}


def build_results(plan):
    m = plan['method']
    if m == 'fcff':
        if (plan.get('dcf') or {}).get('drivers'):
            return run_fcff_drivers(plan)
        return run_dcf(plan, 'fcff')
    if m == 'apv':
        return run_apv(plan)
    if m == 'fcfe':
        return run_dcf(plan, 'fcfe')
    if m == 'ddm':
        return run_ddm(plan)
    if m == 'rnpv':
        return run_rnpv(plan)
    if m == 'relative':
        return run_relative(plan)
    raise ValueError(f"Unknown method: {m}")


def classify(inputs):
    """Lightweight Damodaran method suggestion (references/method_selection.md)."""
    s = []
    if inputs.get('pipeline') or inputs.get('clinical_assets') or inputs.get('sector', '').lower() in ('biotech', 'pharma'):
        s.append('rnpv')
    if inputs.get('distress_probability', 0) and inputs['distress_probability'] > 0.25:
        s.append('apv/equity-as-option (distressed)')
    if inputs.get('negative_earnings'):
        s.append('fcfe/fcff with normalized earnings (Ch.22-23)')
    if inputs.get('sector', '').lower() in ('bank', 'insurance', 'financial'):
        s.append('ddm/excess-return + P/B (financials, Ch.21)')
    if inputs.get('stable_leverage', True):
        s.append('fcfe or ddm')
    else:
        s.append('fcff/apv (changing leverage)')
    s.append('relative (always, as cross-check)')
    return s


def run(plan_path, out_dir):
    plan = json.loads(Path(plan_path).read_text())
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    results = build_results(plan)
    name = (results.get('company', {}).get('ticker')
            or results.get('company', {}).get('name', 'company')).replace(' ', '_')
    rp = out / f"{name}_{results['method']}_results.json"
    rp.write_text(json.dumps(results, indent=2, default=str))
    excel_path = out / f"{name}_{results['method']}_model.xlsx"
    if plan.get('output', {}).get('excel', True):
        excel_builder.build_workbook(results, str(excel_path))
    v = validate_valuation.ValuationValidator()
    # Delivery gate must ALWAYS produce validation.json — even if the validator
    # raises — so an "audited" run never ships results.json + model.xlsx with no
    # verdict. A validator exception is itself a hard FAIL. [report D2]
    try:
        v.validate_results(results)
        if excel_path.exists():
            v.validate_excel(str(excel_path), results['method'])
    except Exception as e:
        v.errors.append(f"Validation raised {type(e).__name__}: {e} — "
                        f"results may be incomplete; treated as FAIL.")
    vres = v.result({'results': str(rp), 'excel': str(excel_path)})
    (out / f"{name}_{results['method']}_validation.json").write_text(json.dumps(vres, indent=2))
    print(json.dumps({'results': str(rp), 'excel': str(excel_path),
                      'validation_status': vres['status'],
                      'errors': vres['errors'], 'warnings': vres['warnings']}, indent=2, default=str))
    return results, vres


# --------------------------------------------------------------------------- selftest
def selftest():
    import tempfile
    td = tempfile.mkdtemp(prefix='valeng_')
    checks = []

    # 1) FCFF end-to-end
    fcff_plan = {'method': 'fcff', 'company': {'name': 'Acme Inc', 'ticker': 'ACME'},
                 'wacc': {'rf': 0.04, 'erp': 0.05, 'beta': 1.1, 'tax_rate': 0.24,
                          'interest_coverage': 6.0, 'equity_value': 1000.0, 'debt_value': 200.0},
                 'dcf': {'base_cf': 100.0, 'growth_rates': [0.08, 0.07, 0.06, 0.05, 0.04],
                         'stable_growth': 0.025, 'rf': 0.04, 'mid_year': True,
                         'net_debt': 200.0, 'shares': 100.0},
                 'output': {'out_dir': td}}
    r1 = build_results(fcff_plan)
    vps = r1['dcf']['value_per_share']
    checks.append(("FCFF per-share finite & >0", isinstance(vps, float) and vps > 0))
    checks.append(("FCFF tv_pct in (0,1)", 0 < r1['dcf']['tv_pct'] < 1))
    checks.append(("FCFF WACC built in 5-20%", 0.05 < r1['wacc_build']['wacc'] < 0.20))
    checks.append(("FCFF sensitivity grid present", bool(r1.get('sensitivity'))))

    # 2) rNPV — Upstream Bio golden lock
    upb = {'method': 'rnpv', 'company': {'name': 'Upstream Bio', 'ticker': 'UPB'},
           'rnpv': {'assets': [
               {'name': 'asthma', 'peak_sales': 900, 'pv_commercial': 430.0, 'loa': 0.50},
               {'name': 'crswnp', 'peak_sales': 500, 'pv_commercial': 258.62069, 'loa': 0.58},
               {'name': 'copd', 'peak_sales': 700, 'pv_commercial': 68.1818, 'loa': 0.22}],
               'net_cash': 255.0, 'overhead_pv': 110.0, 'shares': 54.45,
               'scenarios': [{'name': 'bull', 'prob': 0.25, 'target': 18.0},
                             {'name': 'base', 'prob': 0.45, 'target': 9.65},
                             {'name': 'bear', 'prob': 0.30, 'target': 4.25}]}}
    r2 = build_results(upb)
    checks.append(("UPB equity ≈ 525", abs(r2['rnpv']['equity_value'] - 525.0) < 1.0))
    checks.append(("UPB per-share ≈ 9.65", abs(r2['rnpv']['value_per_share'] - 9.65) < 0.05))
    checks.append(("UPB scenario-weighted ≈ 10.1175", abs(r2['rnpv']['scenario_weighted'] - 10.1175) < 0.01))
    checks.append(("UPB rounded target == 10.00", abs(r2['rnpv']['rounded_target'] - 10.0) < 1e-9))

    # 2b) UPB dilution-stress golden [report D11] — the base $9.65 lock is pure
    #     Σassets+cash−overhead arithmetic and would not catch a regression in the
    #     dilution machinery. This golden exercises dev-cost subtraction, a
    #     committed (unfloored) NEGATIVE asset, options-as-liability, and the
    #     BASIC-share denominator, all at once, with a hand-computed answer.
    upb2 = {'method': 'rnpv', 'company': {'name': 'Upstream Bio DX', 'ticker': 'UPBX'},
            'rnpv': {'assets': [
                {'name': 'lead', 'pv_commercial': 1000.0, 'loa': 0.60, 'pv_dev_cost': 100.0},
                {'name': 'follow', 'pv_commercial': 400.0, 'loa': 0.50, 'pv_dev_cost': 50.0},
                {'name': 'committed_ph3', 'pv_commercial': 100.0, 'loa': 0.20,
                 'pv_dev_cost': 80.0, 'committed': True}],
                'net_cash': 100.0, 'overhead_pv': 40.0, 'options_value': 90.0, 'shares': 56.0}}
    r2b = build_results(upb2)
    a = r2b['rnpv']['assets']
    checks.append(("UPBX dev-cost subtracted: 0.6*1000−100 = 500", abs(a[0]['rnpv'] - 500.0) < 1e-9))
    checks.append(("UPBX committed asset unfloored: 0.2*100−80 = −60", abs(a[2]['rnpv'] - (-60.0)) < 1e-9))
    checks.append(("UPBX options-as-liability: equity 560 (not 740 if added)",
                   abs(r2b['rnpv']['equity_value'] - 560.0) < 1e-9))
    checks.append(("UPBX per-share on BASIC shares: 560/56 = 10.00",
                   abs(r2b['rnpv']['value_per_share'] - 10.0) < 1e-9))

    # 3) Relative — EV/EBITDA with outlier
    rel = {'method': 'relative', 'company': {'name': 'Beta Co', 'ticker': 'BETA'},
           'relative': {'metric_name': 'EV/EBITDA', 'target_metric': 500.0,
                        'peers': [{'name': 'a', 'multiple': 8}, {'name': 'b', 'multiple': 9},
                                  {'name': 'c', 'multiple': 11}, {'name': 'd', 'multiple': 40}],
                        'net_debt': 200.0, 'shares': 50.0}}
    r3 = build_results(rel)
    checks.append(("Relative median multiple == 10", abs(r3['relative']['median_multiple'] - 10.0) < 1e-9))
    checks.append(("Relative implied EV == 5000", abs(r3['relative']['implied_value'] - 5000.0) < 1e-6))
    checks.append(("Relative outlier flagged [3]", r3['relative']['outliers'] == [3]))
    checks.append(("Relative per-share == (5000-200)/50 = 96", abs(r3['relative']['implied_per_share'] - 96.0) < 1e-6))

    # 4) Excel build + validate for all three
    for res, tag in ((r1, 'fcff'), (r2, 'rnpv'), (r3, 'relative')):
        xp = os.path.join(td, f"{tag}.xlsx")
        try:
            excel_builder.build_workbook(res, xp)
            built = os.path.exists(xp)
        except Exception as e:
            built = False
            print("  excel build error:", e)
        v = validate_valuation.ValuationValidator()
        v.validate_results(res)
        if built:
            v.validate_excel(xp, res['method'])
        vr = v.result({})
        checks.append((f"{tag}: excel built", built))
        checks.append((f"{tag}: validation PASS", vr['status'] == 'PASS'))

    # 5) Delivery-gate regression [report D1/D2]: run() end-to-end must never
    #    crash and must ALWAYS write validation.json on the paths that carry
    #    wacc_build == None (DDM) or a caller-supplied direct rate (no WACC).
    import glob
    ddm_plan = {'method': 'ddm', 'company': {'name': 'DivCo', 'ticker': 'DIV'},
                'ddm': {'dps1': 2.0, 'ke_stable': 0.09, 'stable_growth': 0.03,
                        'rf': 0.04, 'shares': 100.0}}
    dpath = os.path.join(td, 'ddm_plan.json'); Path(dpath).write_text(json.dumps(ddm_plan))
    try:
        _, dv = run(dpath, td); ddm_ok = True
    except Exception as e:
        ddm_ok, dv = False, {'status': 'CRASH'}; print("  DDM run error:", e)
    checks.append(("DDM run() does not crash", ddm_ok))
    checks.append(("DDM validation.json written (delivery gate)",
                   bool(glob.glob(os.path.join(td, 'DIV_ddm_validation.json')))))
    checks.append(("DDM validation PASS", dv.get('status') == 'PASS'))
    # Two-stage DDM payout step-up through the engine [D5]: reproduces the P&G
    # book P0 $68.90 AND derives the implied stable ROE (0.03/(1−0.75)=12%, the
    # value Damodaran states for P&G) — locks the run_ddm payout wiring + roc. [D13]
    pg = build_results({'method': 'ddm', 'company': {'name': 'PG'},
                        'ddm': {'dps0': 1.91, 'high_growth': 0.10, 'high_years': 5,
                                'stable_growth': 0.03, 'ke_high': 0.08, 'ke_stable': 0.085,
                                'payout_high': 0.50, 'payout_stable': 0.75}})
    checks.append(("DDM two-stage P&G via engine == $68.90 & implied ROE 12% [D5/D13]",
                   abs(pg['dcf']['value_per_share'] - 68.90) < 0.15 and
                   abs(pg['dcf']['roc'] - 0.12) < 1e-9))

    dr_plan = {'method': 'fcfe', 'company': {'name': 'RateCo', 'ticker': 'RATE'},
               'dcf': {'base_cf': 100.0, 'growth_rates': [0.05, 0.04, 0.03],
                       'stable_growth': 0.02, 'rate': 0.10, 'rf': 0.04, 'shares': 50.0}}
    rpath = os.path.join(td, 'rate_plan.json'); Path(rpath).write_text(json.dumps(dr_plan))
    try:
        _, rv = run(rpath, td); dr_ok = True
    except Exception as e:
        dr_ok, rv = False, {'status': 'CRASH'}; print("  direct-rate run error:", e)
    checks.append(("direct-rate FCFE run() does not crash", dr_ok))
    checks.append(("direct-rate validation.json written",
                   bool(glob.glob(os.path.join(td, 'RATE_fcfe_validation.json')))))

    # 6) APV regression [report D4]: real APV = V_u(@ρu) + shield − distress,
    #    NOT WACC-DCF + shield. Reproduce the Damodaran J.Crew LBO (~$2,469m)
    #    and lock the no-double-count invariant.
    jc_fcff0 = 230 * 0.65 * 0.75  # 112.125
    jcrew = {'method': 'apv', 'company': {'name': 'J Crew', 'ticker': 'JCG'},
             'dcf': {'base_cf': jc_fcff0, 'growth_rates': [0.035], 'stable_growth': 0.035,
                     'rho_u': 0.085, 'mid_year': False, 'tax_shield_pv': 305.0,
                     'distress_pv': 158.0, 'net_debt': 500.0, 'shares': 100.0}}
    ra = build_results(jcrew)
    apv_firm = ra['dcf']['enterprise_value']
    v_u_indep = dcf_mod.dcf_value(jc_fcff0, [0.035], 0.085, 0.035, mid_year=False)['total_value']
    checks.append(("APV J.Crew enterprise value ≈ $2,469m [p.401]", abs(apv_firm - 2469.0) < 4.0))
    checks.append(("APV rate == ρu (0.085), not WACC", abs(ra['dcf']['rate'] - 0.085) < 1e-9))
    checks.append(("APV no double-count: EV == V_u + shield − distress",
                   abs(apv_firm - (v_u_indep + 305.0 - 158.0)) < 1e-6))

    # Hard-error regressions: silent wrong-rate paths must now raise.
    def _raises(plan):
        try:
            build_results(plan); return False
        except ValueError:
            return True
    checks.append(("APV without ρu/build-inputs raises (no silent WACC)",
                   _raises({'method': 'apv', 'company': {'name': 'NoRhoU'},
                            'dcf': {'base_cf': 100.0, 'growth_rates': [0.03],
                                    'stable_growth': 0.02, 'tax_shield_pv': 40.0}})))
    checks.append(("FCFE with only firm WACC raises (no silent FCFE@WACC)",
                   _raises({'method': 'fcfe', 'company': {'name': 'WaccOnly'},
                            'wacc': {'wacc': 0.09},
                            'dcf': {'base_cf': 100.0, 'growth_rates': [0.04, 0.03],
                                    'stable_growth': 0.02, 'shares': 50.0}})))
    checks.append(("DDM g>rf raises (economic cap now fires) [D6]",
                   _raises({'method': 'ddm', 'company': {'name': 'FastGrower'},
                            'ddm': {'dps1': 2.0, 'ke_stable': 0.09,
                                    'stable_growth': 0.05, 'rf': 0.04}})))

    # 7) Comps + rNPV interface hardening [report D7/D8/D9/D10/D15]
    checks.append(("P/E without basis raises (dual-unit footgun) [D7]",
                   _raises({'method': 'relative', 'company': {'name': 'PECo'},
                            'relative': {'metric_name': 'P/E', 'target_metric': 500.0,
                                         'peers': [{'name': 'a', 'multiple': 10},
                                                   {'name': 'b', 'multiple': 10}],
                                         'shares': 100.0}})))
    rpe = build_results({'method': 'relative', 'company': {'name': 'PECo'},
                         'relative': {'metric_name': 'P/E', 'basis': 'per_share',
                                      'target_metric': 5.0,
                                      'peers': [{'name': 'a', 'multiple': 10},
                                                {'name': 'b', 'multiple': 10}], 'shares': 100.0}})
    checks.append(("P/E per_share basis: 5.0 EPS × 10 = $50/sh [D7]",
                   abs(rpe['relative']['implied_per_share'] - 50.0) < 1e-9))
    rpa = build_results({'method': 'relative', 'company': {'name': 'PECo'},
                         'relative': {'metric_name': 'P/E', 'basis': 'aggregate',
                                      'target_metric': 500.0,
                                      'peers': [{'name': 'a', 'multiple': 10},
                                                {'name': 'b', 'multiple': 10}], 'shares': 100.0}})
    checks.append(("P/E aggregate basis: equity 5000 & $50/sh (was 250k footgun) [D7]",
                   abs(rpa['relative']['equity_value'] - 5000.0) < 1e-9 and
                   abs(rpa['relative']['implied_per_share'] - 50.0) < 1e-9))
    rex = build_results({'method': 'relative', 'company': {'name': 'ExCo'},
                         'relative': {'metric_name': 'EV/EBITDA', 'target_metric': 100.0,
                                      'exclude_outliers': True,
                                      'peers': [{'name': 'a', 'multiple': 8}, {'name': 'b', 'multiple': 9},
                                                {'name': 'c', 'multiple': 11}, {'name': 'd', 'multiple': 40}]}})
    checks.append(("exclude_outliers drops 40×: median 9.0, flagged true [D8]",
                   abs(rex['relative']['median_multiple'] - 9.0) < 1e-9 and
                   rex['relative']['outliers_excluded'] is True))
    checks.append(("rNPV peak_sales without pv_commercial raises [D9]",
                   _raises({'method': 'rnpv', 'company': {'name': 'BioCo'},
                            'rnpv': {'assets': [{'name': 'x', 'peak_sales': 900, 'loa': 0.5}],
                                     'shares': 10.0}})))
    rop = build_results({'method': 'rnpv', 'company': {'name': 'OptCo'},
                         'rnpv': {'assets': [{'name': 'x', 'pv_commercial': 1000.0, 'loa': 1.0}],
                                  'net_cash': 0.0, 'options_value': 200.0, 'shares': 100.0}})
    checks.append(("rNPV options subtracted: (1000−200)/100 = $8.00/sh [D10]",
                   abs(rop['rnpv']['equity_value'] - 800.0) < 1e-9 and
                   abs(rop['rnpv']['value_per_share'] - 8.0) < 1e-9))
    rcm = build_results({'method': 'rnpv', 'company': {'name': 'CommitCo'},
                         'rnpv': {'assets': [{'name': 'ph3', 'pv_commercial': 100.0, 'loa': 0.3,
                                              'pv_dev_cost': 80.0, 'committed': True}],
                                  'net_cash': 0.0, 'shares': 10.0}})
    checks.append(("committed asset carries negative rNPV (−50, unfloored) [D15]",
                   abs(rcm['rnpv']['assets'][0]['rnpv'] - (-50.0)) < 1e-9))

    # 8) Growth-must-pay-for-itself + country-risk bands [report D13/D14]
    def _warns(res, needle):
        vv = validate_valuation.ValuationValidator(); vv.validate_results(res)
        return any(needle in m for m in vv.warnings)
    def _infos(res, needle):
        vv = validate_valuation.ValuationValidator(); vv.validate_results(res)
        return any(needle in m for m in vv.info)
    base_dcf = lambda **kw: dict({'base_cf': 100.0, 'growth_rates': [0.05, 0.04],
                                  'stable_growth': 0.025, 'net_debt': 0.0, 'shares': 50.0}, **kw)
    checks.append(("D13 g/ROC>100% warns (infeasible reinvestment)",
                   _warns(build_results({'method': 'fcff', 'company': {'name': 'RRCo'},
                                         'wacc': {'wacc': 0.09},
                                         'dcf': base_dcf(stable_growth=0.04, roc=0.03)}),
                          "exceeds 100%")))
    checks.append(("D13 ROC<=discount rate warns (value-destroying)",
                   _warns(build_results({'method': 'fcff', 'company': {'name': 'VDCo'},
                                         'wacc': {'wacc': 0.09}, 'dcf': base_dcf(roc=0.08)}),
                          "value-neutral-to-destructive")))
    checks.append(("D13 ROC>rate → 'growth creates value' info",
                   _infos(build_results({'method': 'fcff', 'company': {'name': 'VCCo'},
                                         'wacc': {'wacc': 0.09}, 'dcf': base_dcf(roc=0.15)}),
                          "growth creates value")))
    checks.append(("D14 24% WACC warns without CRP",
                   _warns(build_results({'method': 'fcff', 'company': {'name': 'EMNoCRP'},
                                         'wacc': {'wacc': 0.24},
                                         'dcf': base_dcf(growth_rates=[0.05], stable_growth=0.03)}),
                          "WACC/discount rate")))
    checks.append(("D14 24% WACC does NOT warn with 7% CRP",
                   not _warns(build_results({'method': 'fcff', 'company': {'name': 'EMwithCRP'},
                                             'wacc': {'wacc': 0.24, 'crp': 0.07},
                                             'dcf': base_dcf(growth_rates=[0.05], stable_growth=0.03)}),
                              "WACC/discount rate")))

    # 9) Driver-based builders — young-firm FCFF + development-stage biotech curve
    # 9a: rNPV asset builds pv_commercial from a drug commercial curve; the
    #     black-box input becomes auditable and risk stays in LoA.
    bio = build_results({'method': 'rnpv', 'company': {'name': 'DevBio'},
                         'rnpv': {'assets': [
                             {'name': 'lead', 'loa': 0.35, 'pv_dev_cost': 200.0,
                              'commercial': {'peak_sales': 600, 'launch_year': 6, 'ramp_years': 4,
                                             'plateau_years': 5, 'erosion_years': 5, 'erosion_rate': 0.4,
                                             'margin': 0.70, 'discount_rate': 0.12}}],
                             'net_cash': 0.0, 'shares': 50.0}})
    a0 = bio['rnpv']['assets'][0]
    pvc_ind = drivers_mod.drug_commercial_pv(600, 6, 4, 5, 5, 0.4, 0.70, 0.12)['pv_commercial']
    checks.append(("driver: rNPV builds pv_commercial from drug curve (auditable)",
                   a0['pv_commercial_built'] and abs(a0['pv_commercial'] - pvc_ind) < 1e-6))
    checks.append(("driver: rNPV = LoA*pvc − dev, risk via LoA",
                   abs(a0['rnpv'] - (0.35 * pvc_ind - 200.0)) < 1e-6))
    # 9b: young-firm FCFF from drivers reproduces Damodaran's LinkedIn margin path
    grw = build_results({'method': 'fcff', 'company': {'name': 'GrowthCo'}, 'wacc': {'wacc': 0.10},
                         'dcf': {'stable_growth': 0.03, 'shares': 100.0,
                                 'drivers': {'base_revenue': 243.0,
                                             'revenue_growth': [0.6, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1, 0.08, 0.05],
                                             'current_margin': 0.0823, 'target_margin': 0.15,
                                             'margin_converge': 0.5, 'sales_to_capital': 2.20,
                                             'tax_rate': 0.25, 'terminal_roc': 0.12}}})
    gd = grw['dcf']
    checks.append(("driver: FCFF driver_based, y1 margin 11.62% (LinkedIn), EV>0",
                   gd['driver_based'] and abs(gd['projection'][0]['margin'] - 0.1162) < 6e-4
                   and gd['enterprise_value'] > 0))
    checks.append(("driver: FCFF y1 FCFF<0 (young reinvesting firm), y10 margin→15%",
                   gd['projection'][0]['cf'] < 0 and abs(gd['projection'][-1]['margin'] - 0.15) < 1e-3))
    # empty revenue_growth WITH terminal_roc must raise a clean ValueError, not an
    # IndexError from the terminal_cf_fn default-arg. [verifier]
    try:
        build_results({'method': 'fcff', 'company': {'name': 'Empty'}, 'wacc': {'wacc': 0.10},
                       'dcf': {'stable_growth': 0.03, 'shares': 100.0,
                               'drivers': {'base_revenue': 100.0, 'revenue_growth': [],
                                           'current_margin': 0.05, 'target_margin': 0.15,
                                           'sales_to_capital': 2.0, 'tax_rate': 0.25,
                                           'terminal_roc': 0.12}}})
        empty_ok = False
    except ValueError:
        empty_ok = True
    except Exception:
        empty_ok = False
    checks.append(("driver: empty revenue_growth raises clean ValueError (not IndexError)", empty_ok))

    print("=" * 64); print("valuation_engine.py selftest  (tmp:", td, ")")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("=" * 64); print("ALL PASS" if ok else "SOME FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser(description="Valuation orchestrator")
    sub = ap.add_subparsers(dest='cmd')
    pr = sub.add_parser('run'); pr.add_argument('--plan', required=True); pr.add_argument('--out-dir', required=True)
    pc = sub.add_parser('classify'); pc.add_argument('--inputs', required=True)
    sub.add_parser('selftest')
    args = ap.parse_args()
    if args.cmd == 'run':
        _, vres = run(args.plan, args.out_dir)
        sys.exit(0 if vres['status'] == 'PASS' else 2)
    elif args.cmd == 'classify':
        print(json.dumps(classify(json.loads(Path(args.inputs).read_text())), indent=2))
    elif args.cmd == 'selftest':
        sys.exit(0 if selftest() else 1)
    else:
        ap.print_help(); sys.exit(1)


if __name__ == '__main__':
    main()
