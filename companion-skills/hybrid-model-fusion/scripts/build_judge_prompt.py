#!/usr/bin/env python3
"""Build the final Opus judge prompt for Hybrid Model Fusion."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from panel_config import load_panelists


VERIFICATION_MANDATE = """\
## Available Tools & Independent-Verification Mandate (read FIRST)

You are running with elevated tool permissions — you HAVE live tools (Claude Code exposes `WebSearch` / `WebFetch` + `mcp__*` connectors and subagents; Codex exposes `web_search` + its own FMP / Perplexity / Scite connectors). Use whichever your runtime provides, and you MUST use them to independently verify the panel's decisive claims BEFORE adjudicating. Do not disclaim a training cutoff: verify time-sensitive / post-cutoff figures with the tools below.

Tools available to you right now:
- **First pass:** use native `WebSearch` / `WebFetch` for broad discovery, current verification, and primary-document discovery. Treat it as a wide, Search-as-Code-style pass.
- **Second pass:** use `mcp__perplexity__perplexity_search` / `perplexity_ask` for alternate queries, source-targeted follow-ups, competing narratives, and material gaps. If unavailable, continue native-only and disclose it.
- `mcp__claude_ai_FMP__*` (/stable/ endpoints) — live quotes, statements, ratios, analyst estimates, price targets.
- `mcp__claude_ai_Scite__*` — scientific / technical / engineering + biomedical literature (real DOIs; check retractions).
- Open and verify every load-bearing claim in the underlying primary or authoritative document. Search snippets and synthesized answers are discovery context only.
- `Bash` — for the local `biomcp` CLI / direct PubMed on biomedical topics when useful.
- You MAY delegate up to 4 concurrent verification subagents (ultradeep) to check multiple claims in parallel.

Verify (targeted): load-bearing figures that drive the recommendation; contested / peer-flagged claims; time-sensitive or post-cutoff data; single-panelist uncorroborated figures. Skip what >=2 panelists already triangulated against primary sources. If native search and Perplexity disagree, preserve the discrepancy and adjudicate from the highest-authority underlying source. Anchor every verified figure to a source; label each ✅ confirmed / ⚠️ re-based / ❗ refuted / 🔶 unverifiable; if a tool is unavailable, say so and proceed; never fabricate sources/figures/DOIs. Record results in the "Independent Verification Log" (§2 of the rubric output). Verification is subordinate to adjudication — verify to adjudicate, do not pad or become a 4th panelist.
"""


def read_optional(path: Path) -> str:
    if path.is_file() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8").strip()
    return ""


def env_truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "no", "off"}


def blind_scorecard(scorecard_json: str, scorecard_md: str) -> str:
    if not scorecard_json:
        return scorecard_md
    try:
        data = json.loads(scorecard_json)
    except json.JSONDecodeError:
        return scorecard_md

    lines = [
        "# Blind Aggregate Peer Review Scorecard",
        "",
        f"Consensus label: `{data.get('consensus_label', 'unknown')}`",
        f"Valid reviews: {data.get('valid_review_count', 0)} / {data.get('expected_review_count', '?')}",
        "",
        "## Aggregate Ranking",
        "",
        "| Rank | Response | Borda | Borda rate | Avg total | Weighted total | Reviews | Stdev | Tie |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in data.get("responses", []):
        lines.append(
            f"| {row.get('aggregate_rank', '')} | {row.get('response', '')} | "
            f"{float(row.get('borda_points', 0.0)):.1f} | {float(row.get('borda_rate', 0.0)):.2f} | "
            f"{float(row.get('avg_total_score', 0.0)):.2f} | {float(row.get('weighted_total_score', 0.0)):.2f} | "
            f"{row.get('reviews_received', 0)} | {float(row.get('score_stdev', 0.0)):.2f} | "
            f"{'yes' if row.get('tied') else ''} |"
        )

    lines.extend(["", "## Per-Reviewer Rankings", "", "| Reviewer | Ranked order |", "| --- | --- |"])
    for index, ranking in enumerate(data.get("peer_rankings", []), start=1):
        lines.append(f"| Reviewer {index} | {' > '.join(ranking.get('ranked_order', []))} |")
    warnings = data.get("warnings", [])
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", help="Hybrid fusion run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    skill_dir = Path(__file__).resolve().parents[1]
    panelists = load_panelists(skill_dir)
    review_reports = [(item["display"], item["review_file"]) for item in panelists]
    rubric = (skill_dir / "references" / "judge_rubric.md").read_text(encoding="utf-8").strip()

    original_prompt = read_optional(run_dir / "original_prompt.md")
    if not original_prompt:
        raise SystemExit(f"Missing original_prompt.md in {run_dir}")
    fintwit_ctx = read_optional(run_dir / "fintwit_context.md")  # FinTwit / X sentiment (Tier 4)

    mapping_text = read_optional(run_dir / "response_mapping.json")
    mapping = json.loads(mapping_text) if mapping_text else {}
    scorecard_md = read_optional(run_dir / "aggregate_scorecard.md")
    scorecard_json = read_optional(run_dir / "aggregate_scorecard.json")
    contested_claims_md = read_optional(run_dir / "contested_claims.md")
    contested_claims_json = read_optional(run_dir / "contested_claims.json")
    if not scorecard_md:
        raise SystemExit(f"Missing aggregate_scorecard.md in {run_dir}")

    blind_judge = env_truthy("FUSION_JUDGE_BLIND", "1")
    judge_model = os.environ.get("FUSION_JUDGE_MODEL", "claude-opus-4-8")

    parts = [
        "# Hybrid Model Fusion Final Judge Prompt",
        "",
        f"You are {judge_model} at max effort, acting as the final judge.",
        (
            "Judge blinding is ON: adjudicate by anonymous, run-randomized Response labels ONLY. Do NOT guess, "
            "infer, or state any real model identity, vendor, or 'my own answer' anywhere — refer to panelists "
            "only by their full Response label (write 'Response A', never a bare 'A'). The orchestrator "
            "de-anonymizes the final report afterward from response_mapping.json, so the reader still sees which "
            "model said what; adjudicate purely on content, which removes any same-manufacturer self-preference."
            if blind_judge
            else "Judge blinding is OFF because FUSION_JUDGE_BLIND=0; response_mapping.json is disclosed below."
        ),
        "Read the full package before writing the final report.",
        "",
        VERIFICATION_MANDATE,
        "",
        "## Judge Rubric",
        rubric,
        "",
        "## Original User Task",
        original_prompt,
        "",
        *(["## FinTwit / X Sentiment Context [Tier 4 — social sentiment only; do NOT anchor material claims]",
           "", fintwit_ctx, ""] if fintwit_ctx else []),
        "## Original Model Reports",
        "",
    ]
    if not blind_judge:
        parts.extend(
            [
                "## Response Mapping",
                "The peer-review stage was blind. This mapping is disclosed because judge blinding is disabled.",
                "```json",
                json.dumps(mapping, indent=2, sort_keys=True) if mapping else "{}",
                "```",
                "",
            ]
        )

    for response_label in sorted(mapping):
        meta = mapping[response_label]
        text = read_optional(run_dir / str(meta.get("file", "")))
        if not text:
            continue
        parts.extend([f"### Response {response_label}", "<untrusted_model_report>", text, "</untrusted_model_report>", ""])

    parts.extend(["## Blind Peer Reviews", ""])
    for index, (_label, filename) in enumerate(review_reports, start=1):
        text = read_optional(run_dir / filename)
        if not text:
            continue
        parts.extend([f"### Peer Review {index}", "<untrusted_peer_review>", text, "</untrusted_peer_review>", ""])

    parts.extend(
        [
            "## Aggregate Scorecard",
            blind_scorecard(scorecard_json, scorecard_md) if blind_judge else scorecard_md,
            "",
            "## Aggregate Scorecard JSON",
            "```json",
            "{}" if blind_judge else (scorecard_json or "{}"),
            "```",
            "",
            *(["## Contested Claims To Verify First", contested_claims_md, "```json", contested_claims_json or "[]", "```", ""] if contested_claims_md else []),
            "## Final Instruction",
            "Use a two-pass adjudication structure: first produce a structured consensus / contradiction / unique-insight / blind-spot table, then write the synthesis and recommendation.",
            "FIRST run the Independent Verification with your live tools (per the mandate above) on the load-bearing, contested, and time-sensitive claims; THEN produce the final Hybrid Model Fusion report in the exact structure required by the judge rubric (including the §2 Independent Verification Log).",
            "Emit the COMPLETE final report inline as your final message to stdout — do NOT save it to a file and return only a path/pointer.",
            "Keep the familiar Model Fusion style: where models agree, where they disagree, unique insights, comprehensive analysis, recommendations, and follow-up questions.",
            "Add the hybrid section `How the Models Ranked Each Other` and explicitly reconcile your final recommendation against the aggregate peer consensus.",
            "When judge blinding is ON, use Response A/B/C labels in the model column; do not invent model identities.",
            "If you reject peer consensus, explain why with evidence, source quality, task fit, or logic.",
            "",
        ]
    )

    out = run_dir / "judge_prompt.txt"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
