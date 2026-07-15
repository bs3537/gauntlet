#!/usr/bin/env python3
"""
memo_builder.py — Narrative-memo generator for the `valuation` skill.

Renders a polished equity-research-style memo (.md + .docx) from a `results` dict
produced by valuation_engine.py.

Public API:
    build_memo(results: dict, out_dir: str) -> {"md": path, "docx": path}

CLI:
    python3 memo_builder.py --results results.json --out DIR
    python3 memo_builder.py selftest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent


# ──────────────────────────────────────────────────────────────────────────────
# Number formatting helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_m(v: Any) -> str:
    """Format a numeric value as $1,234.5M."""
    try:
        return f"${float(v):,.1f}M"
    except (TypeError, ValueError):
        return str(v)


def _fmt_sh(v: Any) -> str:
    """Format a per-share value as $12.34."""
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v: Any) -> str:
    """Format a rate (0.09 → '9.0%')."""
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _fmt_rate(v: Any) -> str:
    """Same as _fmt_pct but accepts already-percentage values > 1 too."""
    try:
        f = float(v)
        # treat values already expressed as percent (e.g. 9.0 rather than 0.09)
        if abs(f) > 1:
            return f"{f:.1f}%"
        return f"{f * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _safe(d: dict, *keys, default="—"):
    """Drill into nested dict safely."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, None)
        if cur is None:
            return default
    return cur


# ──────────────────────────────────────────────────────────────────────────────
# Headline helper
# ──────────────────────────────────────────────────────────────────────────────

def _headline(results: dict) -> str:
    method = results.get("method", "")
    if method in ("fcff", "fcfe", "ddm"):
        dcf = results.get("dcf", {})
        v = dcf.get("value_per_share")
        return _fmt_sh(v) if v is not None else "—"
    if method == "rnpv":
        rnpv = results.get("rnpv", {})
        v = rnpv.get("rounded_target") or rnpv.get("scenario_weighted") or rnpv.get("value_per_share")
        return _fmt_sh(v) if v is not None else "—"
    if method == "relative":
        rel = results.get("relative", {})
        v = rel.get("implied_per_share")
        return _fmt_sh(v) if v is not None else "—"
    # fallback: any value_per_share in top level
    v = results.get("value_per_share")
    return _fmt_sh(v) if v is not None else "—"


# ──────────────────────────────────────────────────────────────────────────────
# Section renderers — each returns a list of markdown lines
# ──────────────────────────────────────────────────────────────────────────────

def _section_summary(results: dict) -> list[str]:
    company = results.get("company", {})
    name = company.get("name", "The company")
    ticker = company.get("ticker", "")
    method = results.get("method", "")
    currency = company.get("currency", "$")
    headline = _headline(results)

    lines = ["## 1. Summary", ""]

    if method in ("fcff", "fcfe", "ddm"):
        dcf = results.get("dcf", {})
        wacc_b = results.get("wacc_build", {})
        wacc_val = wacc_b.get("wacc") if wacc_b else dcf.get("rate")
        tv_pct = dcf.get("tv_pct")
        parts = [
            f"{name} ({ticker}) is valued at **{headline} per share** "
            f"on a {method.upper()} basis."
        ]
        if wacc_val is not None:
            parts.append(f"The discount rate applied is {_fmt_pct(wacc_val)}.")
        if tv_pct is not None:
            parts.append(
                f"Terminal value accounts for {_fmt_pct(tv_pct)} of enterprise value, "
                "the primary swing factor."
            )
        lines.append(" ".join(parts))
    elif method == "rnpv":
        rnpv = results.get("rnpv", {})
        sw = rnpv.get("scenario_weighted")
        rt = rnpv.get("rounded_target")
        vps = rnpv.get("value_per_share")
        parts = [
            f"{name} ({ticker}) is valued at **{_fmt_sh(rt or vps)} per share** "
            f"on a risk-adjusted NPV (SOTP) basis."
        ]
        if sw is not None:
            parts.append(
                f"The probability-weighted scenario target is {_fmt_sh(sw)}, "
                f"rounded to {_fmt_sh(rt)} as the base-case anchor."
            )
        parts.append(
            "The biggest swing factor is pipeline probability-of-success across the lead assets."
        )
        lines.append(" ".join(parts))
    elif method == "relative":
        rel = results.get("relative", {})
        metric = rel.get("metric_name", "the valuation multiple")
        med = rel.get("median_multiple")
        parts = [
            f"{name} ({ticker}) is valued at **{headline} per share** "
            f"using a {method} approach anchored to {metric}."
        ]
        if med is not None:
            parts.append(f"The applied median peer multiple is {med:.1f}x.")
        lines.append(" ".join(parts))
    else:
        lines.append(f"{name} ({ticker}) — valuation complete. Implied value per share: **{headline}**.")

    lines.append("")
    return lines


def _section_why_method(results: dict) -> list[str]:
    method = results.get("method", "")
    pages = results.get("methodology_pages", [])

    rationale = {
        "fcff": (
            "FCFF (free cash flow to firm) is appropriate when the firm is not highly "
            "levered and capital structure is expected to evolve; it values the operating "
            "assets independently of financing and bridges to equity via net debt."
        ),
        "fcfe": (
            "FCFE (free cash flow to equity) is used when leverage is stable and the "
            "equity cash flows can be projected reliably; the discount rate is the cost "
            "of equity rather than WACC."
        ),
        "ddm": (
            "The Dividend Discount Model is appropriate for mature, dividend-paying firms "
            "with a predictable payout ratio; intrinsic value equals the present value "
            "of expected future dividends."
        ),
        "rnpv": (
            "Risk-adjusted NPV / SOTP is the standard approach for biotech / clinical-stage "
            "companies where revenue is probability-weighted by regulatory LoA; each asset "
            "is valued independently and the results are summed."
        ),
        "relative": (
            "Relative valuation anchors the implied price to a peer-derived trading multiple; "
            "used as a cross-check or primary method when the firm has comparable traded peers."
        ),
    }
    text = rationale.get(method, f"Method: {method}.")
    lines = ["## 2. Why this method", "", text, ""]
    if pages:
        lines.append("Pages consulted: " + "; ".join(str(p) for p in pages))
    else:
        lines.append("Pages consulted: Damodaran *Investment Valuation* (core methodology).")
    lines.append("")
    return lines


def _section_valuation_dcf(results: dict) -> list[str]:
    dcf = results.get("dcf", {})
    wacc_b = results.get("wacc_build", {})
    lines = ["## 3. Valuation", ""]

    # ── WACC summary line
    if wacc_b:
        rf = wacc_b.get("rf")
        beta = wacc_b.get("beta")
        erp = wacc_b.get("erp")
        ke = wacc_b.get("cost_of_equity")
        kd = wacc_b.get("cost_of_debt_after_tax")
        wacc = wacc_b.get("wacc")
        parts = []
        if rf is not None:
            parts.append(f"rf = {_fmt_pct(rf)}")
        if beta is not None:
            parts.append(f"β = {float(beta):.2f}")
        if erp is not None:
            parts.append(f"ERP = {_fmt_pct(erp)}")
        if ke is not None:
            parts.append(f"Ke = {_fmt_pct(ke)}")
        if kd is not None:
            parts.append(f"Kd(at) = {_fmt_pct(kd)}")
        if wacc is not None:
            parts.append(f"**WACC = {_fmt_pct(wacc)}**")
        if parts:
            lines.append("**WACC build:** " + " | ".join(parts))
            lines.append("")

    # ── Terminal value note
    tv = dcf.get("terminal_value")
    pv_tv = dcf.get("pv_terminal")
    ev = dcf.get("enterprise_value")
    tv_pct = dcf.get("tv_pct")
    if tv is not None:
        tv_line = f"Terminal value = {_fmt_m(tv)}"
        if pv_tv is not None:
            tv_line += f" (PV: {_fmt_m(pv_tv)})"
        if tv_pct is not None:
            tv_line += f" — **{_fmt_pct(tv_pct)} of EV**"
        lines.append(tv_line)
        lines.append("")

    # ── Discounting-convention disclosure [report D12]
    mid_year = dcf.get("mid_year")
    if mid_year is not None:
        conv = ("mid-year (cash flows at t−0.5; terminal value discounted at n−0.5, "
                "matched between the results JSON and the Excel model)") if mid_year else \
               "end-of-year (cash flows and terminal value at integer periods)"
        lines.append(f"*Discounting convention:* {conv}.")
        lines.append("")

    # ── APV build disclosure — tax shield added once, never embedded in the rate [report D4]
    if results.get("method") == "apv":
        rho, vu = dcf.get("rho_u"), dcf.get("unlevered_value")
        ts, di = dcf.get("tax_shield_pv"), dcf.get("distress_pv")
        apv_parts = []
        if rho is not None:
            apv_parts.append(f"unlevered value at ρu = {_fmt_pct(rho)}")
        if vu is not None:
            apv_parts.append(f"V_u = {_fmt_m(vu)}")
        if ts is not None:
            apv_parts.append(f"+ PV(tax shield) = {_fmt_m(ts)}")
        if di:
            apv_parts.append(f"− PV(distress) = {_fmt_m(di)}")
        if apv_parts:
            lines.append("**APV build:** " + "; ".join(apv_parts)
                         + " — tax shield added once, not embedded in the discount rate.")
            lines.append("")

    # ── Bridge table
    lines.append("### EV → Equity bridge")
    lines.append("")
    lines.append("| Driver | Value |")
    lines.append("| --- | --- |")
    if ev is not None:
        lines.append(f"| Enterprise value | {_fmt_m(ev)} |")
    nd = dcf.get("net_debt")
    if nd is not None:
        lines.append(f"| − Net debt | {_fmt_m(nd)} |")
    eq = dcf.get("equity_value")
    if eq is not None:
        lines.append(f"| = Equity value | **{_fmt_m(eq)}** |")
    sh = dcf.get("shares")
    if sh is not None:
        lines.append(f"| ÷ Shares (M) | {float(sh):,.1f} |")
    vps = dcf.get("value_per_share")
    if vps is not None:
        lines.append(f"| = Value per share | **{_fmt_sh(vps)}** |")
    lines.append("")

    # ── Driver assumptions (young/high-growth/cyclical FCFF, Ch.22-23)
    drv = dcf.get("drivers") if dcf.get("driver_based") else None
    if drv:
        conv = ("half the gap/yr" if abs(drv.get("margin_converge", 0.5) - 0.5) < 1e-9
                else f"{drv.get('margin_converge')} of the gap/yr") \
            if drv.get("margin_mode", "fraction") == "fraction" else "linearly"
        lines.append(
            f"**Driver-based FCFF:** base revenue {_fmt_m(drv.get('base_revenue'))}, "
            f"operating margin converging from {_fmt_pct(drv.get('current_margin'))} to a "
            f"target {_fmt_pct(drv.get('target_margin'))} ({conv}); reinvestment = "
            f"ΔRevenue ÷ sales-to-capital {drv.get('sales_to_capital')}"
            + (f"; terminal ROC {_fmt_pct(drv.get('terminal_roc'))}" if drv.get('terminal_roc') else "")
            + (f"; NOL carryforward {_fmt_m(drv.get('nol'))}" if drv.get('nol') else "")
            + ". [Ch.22-23]")
        lines.append("")

    # ── Projection table (if present)
    proj = dcf.get("projection", [])
    if proj:
        lines.append("### Projection")
        lines.append("")
        if drv:  # richer driver table
            lines.append("| Year | Revenue | Op margin | EBIT(1−t) | Reinvest | FCFF | PV |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for row in proj:
                lines.append(
                    f"| {row.get('year','')} | {_fmt_m(row.get('revenue'))} | "
                    f"{_fmt_pct(row['margin']) if row.get('margin') is not None else '—'} | "
                    f"{_fmt_m(row.get('ebit_after_tax'))} | {_fmt_m(row.get('reinvestment'))} | "
                    f"{_fmt_m(row.get('cf'))} | {_fmt_m(row.get('pv'))} |")
        else:
            lines.append("| Year | Growth | Cash flow | PV |")
            lines.append("| --- | --- | --- | --- |")
            for row in proj:
                gr = _fmt_pct(row["growth"]) if row.get("growth") is not None else "—"
                cf = _fmt_m(row["cf"]) if row.get("cf") is not None else "—"
                pv = _fmt_m(row["pv"]) if row.get("pv") is not None else "—"
                lines.append(f"| {row.get('year','')} | {gr} | {cf} | {pv} |")
        lines.append("")

    return lines


def _section_valuation_rnpv(results: dict) -> list[str]:
    rnpv = results.get("rnpv", {})
    lines = ["## 3. Valuation", ""]

    assets = rnpv.get("assets", [])
    if assets:
        lines.append("### SOTP — Pipeline assets")
        lines.append("")
        lines.append("| Asset | Peak sales | LoA | PV(comm) | rNPV | $/sh |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for a in assets:
            name = a.get("name", "—")
            ps = _fmt_m(a["peak_sales"]) if a.get("peak_sales") is not None else "—"
            loa = _fmt_pct(a["loa"]) if a.get("loa") is not None else "—"
            pvc = (_fmt_m(a["pv_commercial"]) + ("†" if a.get("pv_commercial_built") else "")) \
                if a.get("pv_commercial") is not None else "—"
            rnpv_val = _fmt_m(a["rnpv"]) if a.get("rnpv") is not None else "—"
            psh = _fmt_sh(a["per_share"]) if a.get("per_share") is not None else "—"
            lines.append(f"| {name} | {ps} | {loa} | {pvc} | {rnpv_val} | {psh} |")
        lines.append("")
        if any(a.get("pv_commercial_built") for a in assets):
            lines.append("† PV of commercial cash flows built from a drug curve "
                         "(launch → ramp → plateau → LoE erosion → margin, discounted); "
                         "risk-unadjusted — risk is captured in LoA, not the discount rate.")
            lines.append("")

    # ── SOTP bridge
    lines.append("### SOTP bridge")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("| --- | --- |")
    ps = rnpv.get("pipeline_subtotal")
    if ps is not None:
        lines.append(f"| Pipeline subtotal | {_fmt_m(ps)} |")
    nc = rnpv.get("net_cash")
    if nc is not None:
        lines.append(f"| + Net cash | {_fmt_m(nc)} |")
    oh = rnpv.get("overhead_pv")
    if oh is not None:
        lines.append(f"| − Overhead PV | {_fmt_m(oh)} |")
    ov = rnpv.get("options_value")
    if ov:
        lines.append(f"| − Options value (liability) | {_fmt_m(ov)} |")
    eq = rnpv.get("equity_value")
    if eq is not None:
        lines.append(f"| = Equity value | **{_fmt_m(eq)}** |")
    sh = rnpv.get("shares")
    if sh is not None:
        lines.append(f"| ÷ Shares (M) | {float(sh):,.2f} |")
    vps = rnpv.get("value_per_share")
    if vps is not None:
        lines.append(f"| = Value per share | **{_fmt_sh(vps)}** |")
    lines.append("")
    return lines


def _section_valuation_relative(results: dict) -> list[str]:
    rel = results.get("relative", {})
    lines = ["## 3. Valuation", ""]

    metric = rel.get("metric_name", "Multiple")
    peers = rel.get("peers", [])
    outliers = set(rel.get("outliers") or [])
    if peers:
        lines.append("### Peer trading multiples")
        lines.append("")
        lines.append(f"| Peer | {metric} |")
        lines.append("| --- | --- |")
        for p in peers:
            pname = p.get("name", "—")
            mult = p.get("multiple")
            mult_str = f"{float(mult):.1f}x" if mult is not None else "—"
            if pname in outliers:
                mult_str += " (excl.)"
            lines.append(f"| {pname} | {mult_str} |")
        lines.append("")

    med = rel.get("median_multiple")
    tgt = rel.get("target_metric")
    implied = rel.get("implied_value")
    eq = rel.get("equity_value")
    sh = rel.get("shares")
    ips = rel.get("implied_per_share")

    lines.append("### Applied multiple bridge")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("| --- | --- |")
    if med is not None:
        lines.append(f"| Median peer {metric} | {float(med):.1f}x |")
    if tgt is not None:
        lines.append(f"| Target {metric} | {_fmt_m(tgt)} |")
    if implied is not None:
        lines.append(f"| Implied enterprise/equity value | {_fmt_m(implied)} |")
    if eq is not None:
        lines.append(f"| Equity value | **{_fmt_m(eq)}** |")
    if sh is not None:
        lines.append(f"| ÷ Shares (M) | {float(sh):,.1f} |")
    if ips is not None:
        lines.append(f"| = Implied per share | **{_fmt_sh(ips)}** |")
    lines.append("")
    return lines


def _section_scenarios(results: dict) -> list[str]:
    rnpv = results.get("rnpv", {})
    scenarios = rnpv.get("scenarios", [])
    if not scenarios:
        return []

    lines = ["## 4. Scenarios & convexity", ""]
    lines.append("| Scenario | Probability | Target |")
    lines.append("| --- | --- | --- |")
    for s in scenarios:
        sname = s.get("name", "—")
        prob = _fmt_pct(s["prob"]) if s.get("prob") is not None else "—"
        tgt = _fmt_sh(s["target"]) if s.get("target") is not None else "—"
        lines.append(f"| {sname} | {prob} | {tgt} |")
    lines.append("")

    sw = rnpv.get("scenario_weighted")
    rt = rnpv.get("rounded_target")
    if sw is not None:
        lines.append(f"**Probability-weighted target:** {_fmt_sh(sw)}")
    if rt is not None:
        lines.append(f"**Rounded base-case anchor:** {_fmt_sh(rt)}")
    lines.append("")
    return lines


def _section_sensitivity(results: dict) -> list[str]:
    sens = results.get("sensitivity")
    if not sens:
        return []

    row_var = sens.get("row_var", "Row")
    col_var = sens.get("col_var", "Col")
    row_vals = sens.get("row_vals", [])
    col_vals = sens.get("col_vals", [])
    grid = sens.get("grid", [])

    lines = ["## 5. Sensitivity", ""]
    # header: first col = row_var label, then col_vals
    hdr = f"| {row_var} \\ {col_var} |"
    for cv in col_vals:
        try:
            hdr += f" {_fmt_pct(cv)} |"
        except Exception:
            hdr += f" {cv} |"
    lines.append(hdr)
    sep = "| --- |" + " --- |" * len(col_vals)
    lines.append(sep)
    for i, rv in enumerate(row_vals):
        try:
            rv_str = _fmt_pct(rv)
        except Exception:
            rv_str = str(rv)
        row_line = f"| {rv_str} |"
        row_data = grid[i] if i < len(grid) else []
        for j in range(len(col_vals)):
            val = row_data[j] if j < len(row_data) else None
            row_line += f" {_fmt_sh(val) if val is not None else '—'} |"
        lines.append(row_line)
    lines.append("")
    return lines


def _section_risks(results: dict) -> list[str]:
    warnings = results.get("warnings", [])
    lines = ["## 6. Risks & guardrails", ""]
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("No validation warnings.")
    lines.append("")
    return lines


def _section_methodology(results: dict) -> list[str]:
    pages = results.get("methodology_pages", [])
    lines = ["## 7. Methodology note (Damodaran-anchored)", ""]
    if pages:
        for p in pages:
            lines.append(f"- {p}")
    else:
        lines.append("- Damodaran *Investment Valuation* (core methodology)")
    lines.append(
        "- Intrinsic equity value ÷ current/primary shares; "
        "options valued as a liability (p.446–447)."
    )
    lines.append(
        "- For money-losing/young firms a fair-value future raise is already in the "
        "cash flows — not double-counted; value transfers only on a below-intrinsic "
        "raise (p.371/443/658)."
    )
    lines.append("")
    return lines


# ──────────────────────────────────────────────────────────────────────────────
# Core builder
# ──────────────────────────────────────────────────────────────────────────────

def build_memo(results: dict, out_dir: str) -> dict:
    """
    Build a narrative memo from a `results` dict.

    Args:
        results:  Valuation results dict (see module docstring for schema).
        out_dir:  Directory where outputs are written (created if absent).

    Returns:
        {"md": <absolute path to .md>, "docx": <absolute path to .docx>}
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    company = results.get("company", {})
    raw_name = company.get("name", "Company")
    ticker = company.get("ticker", "UNK")
    method = results.get("method", "valuation")
    as_of = company.get("as_of", "")

    # Safe filename slug
    slug_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_name)
    slug_name = slug_name.strip("_") or "Company"
    stem = f"{slug_name}_{method}_memo"
    md_path = out_path / f"{stem}.md"
    docx_path = out_path / f"{stem}.docx"

    headline = _headline(results)
    method_label = method.upper()

    # Title block
    md_lines: list[str] = []
    md_lines.append(f"# {raw_name} ({ticker}) — Valuation")
    md_lines.append("")
    as_of_str = f" | As of {as_of}" if as_of else ""
    md_lines.append(f"**Method: {method_label} | Value: {headline}{as_of_str}**")
    md_lines.append("")

    # Section 1 — Summary
    md_lines.extend(_section_summary(results))

    # Section 2 — Why this method
    md_lines.extend(_section_why_method(results))

    # Section 3 — Valuation (method-specific)
    if method in ("fcff", "fcfe", "ddm", "apv") and results.get("dcf"):
        md_lines.extend(_section_valuation_dcf(results))
    elif method == "rnpv" and results.get("rnpv"):
        md_lines.extend(_section_valuation_rnpv(results))
    elif method == "relative" and results.get("relative"):
        md_lines.extend(_section_valuation_relative(results))
    else:
        md_lines.append("## 3. Valuation")
        md_lines.append("")
        md_lines.append("*(Valuation data not available for this method.)*")
        md_lines.append("")

    # Section 4 — Scenarios (rnpv only)
    md_lines.extend(_section_scenarios(results))

    # Section 5 — Sensitivity (optional)
    md_lines.extend(_section_sensitivity(results))

    # Section 6 — Risks
    md_lines.extend(_section_risks(results))

    # Section 7 — Methodology note
    md_lines.extend(_section_methodology(results))

    # Footer
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("*For research only; not investment advice.*")
    md_lines.append("")

    md_text = "\n".join(md_lines)
    md_path.write_text(md_text, encoding="utf-8")

    # Convert to DOCX via md2docx.py
    md2docx_script = SCRIPT_DIR / "md2docx.py"
    result = subprocess.run(
        [sys.executable, str(md2docx_script), str(md_path), str(docx_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"md2docx.py failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    return {"md": str(md_path), "docx": str(docx_path)}


# ──────────────────────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────────────────────

def _make_upb_results() -> dict:
    """Upstream-Bio rNPV sample dict."""
    return {
        "company": {
            "name": "Upstream-Bio",
            "ticker": "UPB",
            "currency": "USD",
            "units": "M",
            "as_of": "2026-06-25",
        },
        "method": "rnpv",
        "rnpv": {
            "assets": [
                {"name": "Asthma (UPB-101)", "peak_sales": 1200.0,
                 "loa": 0.30, "rnpv": 215.0, "per_share": 3.95},
                {"name": "CRSwNP (UPB-102)", "peak_sales": 900.0,
                 "loa": 0.25, "rnpv": 150.0, "per_share": 2.75},
                {"name": "COPD (UPB-103)", "peak_sales": 400.0,
                 "loa": 0.10, "rnpv": 15.0, "per_share": 0.28},
            ],
            "pipeline_subtotal": 380.0,
            "net_cash": 255.0,
            "overhead_pv": 110.0,
            "equity_value": 525.0,
            "shares": 54.45,
            "value_per_share": 9.65,
            "scenarios": [
                {"name": "Bull", "prob": 0.25, "target": 18.00},
                {"name": "Base", "prob": 0.50, "target": 9.65},
                {"name": "Bear", "prob": 0.25, "target": 4.25},
            ],
            "scenario_weighted": 10.1175,
            "rounded_target": 10.00,
        },
        "warnings": ["LoA estimates sourced from Citeline; update on each trial read-out."],
        "methodology_pages": ["dilution p.371/443/658", "risk-adjusted NPV / SOTP",
                               "patent-as-option p.781-787"],
    }


def _make_fcff_results() -> dict:
    """Simple FCFF sample dict."""
    return {
        "company": {
            "name": "AcmeCo",
            "ticker": "ACM",
            "currency": "USD",
            "units": "M",
            "as_of": "2026-06-25",
        },
        "method": "fcff",
        "wacc_build": {
            "rf": 0.045,
            "erp": 0.055,
            "beta": 1.10,
            "cost_of_equity": 0.1055,
            "cost_of_debt_after_tax": 0.038,
            "wacc": 0.09,
        },
        "dcf": {
            "rate": 0.09,
            "stable_growth": 0.03,
            "enterprise_value": 2000.0,
            "terminal_value": 1800.0,
            "pv_terminal": 1240.0,
            "explicit_pv": 760.0,
            "tv_pct": 0.62,
            "net_debt": 200.0,
            "equity_value": 1800.0,
            "shares": 100.0,
            "value_per_share": 18.00,
        },
        "warnings": [],
        "methodology_pages": ["FCFF p.380-399", "WACC market-value weights p.220",
                               "terminal g<=rf p.306-307"],
    }


def run_selftest() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="memo_selftest_") as tmpdir:
        # ── Test 1: Upstream-Bio (rNPV)
        upb = _make_upb_results()
        try:
            out = build_memo(upb, tmpdir)
            md_path = Path(out["md"])
            docx_path = Path(out["docx"])

            # Existence checks
            if not md_path.exists():
                failures.append("UPB: .md file does not exist")
            if not docx_path.exists():
                failures.append("UPB: .docx file does not exist")
            elif docx_path.stat().st_size == 0:
                failures.append("UPB: .docx file is empty")

            # Content assertions
            if md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                if "$9.65" not in text:
                    failures.append(f"UPB: '$9.65' not found in memo text")
                if "$10.00" not in text:
                    failures.append(f"UPB: '$10.00' not found in memo text (rounded target)")
                if "Upstream" not in text:
                    failures.append("UPB: 'Upstream' not found in memo text")

            print(f"UPB .md  : {md_path}")
            print(f"UPB .docx: {docx_path}")
        except Exception as exc:
            failures.append(f"UPB: exception during build_memo — {exc}")

        # ── Test 2: AcmeCo FCFF
        fcff = _make_fcff_results()
        try:
            out = build_memo(fcff, tmpdir)
            md_path = Path(out["md"])
            docx_path = Path(out["docx"])

            if not md_path.exists():
                failures.append("FCFF: .md file does not exist")
            if not docx_path.exists():
                failures.append("FCFF: .docx file does not exist")
            elif docx_path.stat().st_size == 0:
                failures.append("FCFF: .docx file is empty")

            # Content spot-checks
            if md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                if "$18.00" not in text:
                    failures.append("FCFF: '$18.00' not found in memo text")
                if "FCFF" not in text:
                    failures.append("FCFF: 'FCFF' not found in memo text")

            print(f"FCFF .md  : {md_path}")
            print(f"FCFF .docx: {docx_path}")
        except Exception as exc:
            failures.append(f"FCFF: exception during build_memo — {exc}")

    if failures:
        print("\nFAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    else:
        print("\nPASS — all assertions satisfied")
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(run_selftest())

    parser = argparse.ArgumentParser(
        description="Build a narrative valuation memo (.md + .docx) from a results JSON."
    )
    parser.add_argument("--results", required=True, help="Path to results.json")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)

    paths = build_memo(results, args.out)
    print(f"Memo written:")
    print(f"  .md   : {paths['md']}")
    print(f"  .docx : {paths['docx']}")


if __name__ == "__main__":
    main()
