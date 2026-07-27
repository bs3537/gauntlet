#!/usr/bin/env python3
"""Score a returned adversarial review against a planted-fraud scenario answer sheet.

This is the piece that turns "a human reads the review and scores it by eye" into a
regression test: it takes the review the reviewer actually produced and reports, per
planted fraud, whether it was CAUGHT — and whether either clean control was wrongly
flagged (a precision miss).

A catch requires BOTH, within `window_chars` of each other in the review text:
  * an ANCHOR   — the review is talking about the planted figure at all
  * a MECHANISM — it says WHY the figure is wrong (stale vintage, omitted net debt,
                  wrong denominator, trough-anchored window, unlabeled forecast, …)
Proximity is the point: a review that says "stale" about something unrelated, twelve
pages from any mention of $31.20, has not caught fraud F1.

Usage:
  score_review.py --review REVIEW.md --scenario eval/scenarios/planted-fraud-money-figures
                  [--json OUT.json] [--min-catches N] [--fail-on-control-fp] [--quiet]

Exit: 0 = catches >= min (and, with --fail-on-control-fp, no control flagged); 1 = below
      bar; 2 = usage/IO error. Deterministic, offline, model-independent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_scenario(scenario_dir: Path) -> dict:
    detection = scenario_dir / "detection.json"
    if not detection.is_file():
        sys.exit(f"score_review: missing detection rules: {detection}")
    return json.loads(detection.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace so line wrapping cannot hide a match.

    Unicode dashes/minus signs are folded to '-' because models reflow them freely.
    """
    text = text.lower()
    for dash in ("‐", "‑", "‒", "–", "—", "−"):
        text = text.replace(dash, "-")
    return re.sub(r"\s+", " ", text)


def find_all(patterns: list[str], text: str) -> list[tuple[str, int]]:
    """Every (pattern, position) hit for the given regex alternatives."""
    hits: list[tuple[str, int]] = []
    for pat in patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            hits.append((pat, match.start()))
    return hits


def near(a_hits, b_hits, window: int):
    """First (a_pattern, b_pattern, position) pair within `window` chars, else None."""
    for a_pat, a_pos in a_hits:
        for b_pat, b_pos in b_hits:
            if abs(a_pos - b_pos) <= window:
                return a_pat, b_pat, min(a_pos, b_pos)
    return None


def excerpt(text: str, pos: int, span: int = 160) -> str:
    start = max(0, pos - span // 4)
    return text[start : start + span].strip()


def score(review_text: str, rules: dict) -> dict:
    text = normalize(review_text)
    window = int(rules.get("window_chars", 800))

    frauds = []
    for fraud in rules["frauds"]:
        anchors = find_all(fraud["anchor_any"], text)
        mechanisms = find_all(fraud["mechanism_any"], text)
        hit = near(anchors, mechanisms, window) if anchors and mechanisms else None
        frauds.append(
            {
                "id": fraud["id"],
                "pattern": fraud["pattern"],
                "planted_text": fraud["planted_text"],
                "caught": hit is not None,
                "anchor_seen": bool(anchors),
                "mechanism_seen": bool(mechanisms),
                "matched_anchor": hit[0] if hit else None,
                "matched_mechanism": hit[1] if hit else None,
                "evidence": excerpt(text, hit[2]) if hit else "",
            }
        )

    controls = []
    for control in rules.get("controls", []):
        anchors = find_all(control["anchor_any"], text)
        accusations = find_all(control["accusation_any"], text)
        hit = near(anchors, accusations, window) if anchors and accusations else None
        controls.append(
            {
                "id": control["id"],
                "control_text": control["control_text"],
                "false_positive": hit is not None,
                "matched_accusation": hit[1] if hit else None,
                "evidence": excerpt(text, hit[2]) if hit else "",
            }
        )

    catches = sum(1 for f in frauds if f["caught"])
    total = len(frauds)
    pass_at = int(rules.get("pass_threshold", 5))
    marginal_at = int(rules.get("marginal_threshold", 4))
    verdict = "PASS" if catches >= pass_at else ("MARGINAL" if catches >= marginal_at else "FAIL")

    return {
        "scenario": rules.get("scenario", "unknown"),
        "catches": catches,
        "total": total,
        "pass_threshold": pass_at,
        "marginal_threshold": marginal_at,
        "verdict": verdict,
        "control_false_positives": sum(1 for c in controls if c["false_positive"]),
        "frauds": frauds,
        "controls": controls,
    }


def render(result: dict) -> str:
    lines = [
        f"Scenario: {result['scenario']}",
        f"{'ID':<4} {'CAUGHT':<7} {'PATTERN':<30} PLANTED TEXT",
    ]
    for fraud in result["frauds"]:
        mark = "yes" if fraud["caught"] else "NO"
        lines.append(f"{fraud['id']:<4} {mark:<7} {fraud['pattern']:<30} {fraud['planted_text']}")
        if not fraud["caught"]:
            why = []
            if not fraud["anchor_seen"]:
                why.append("never mentions the figure")
            elif not fraud["mechanism_seen"]:
                why.append("mentions the figure but never states a mechanism")
            else:
                why.append("figure and mechanism appear, but not near each other")
            lines.append(f"       └─ miss: {why[0]}")
    lines.append("")
    for control in result["controls"]:
        if control["false_positive"]:
            lines.append(
                f"PRECISION MISS: clean control {control['id']} was flagged "
                f"({control['matched_accusation']!r}) — {control['control_text']}"
            )
    lines.append(
        f"CATCHES {result['catches']}/{result['total']} "
        f"(pass >= {result['pass_threshold']}, marginal {result['marginal_threshold']}) "
        f"-> {result['verdict']}; control false positives: {result['control_false_positives']}"
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True, type=Path, help="the review artifact to score")
    ap.add_argument("--scenario", required=True, type=Path, help="scenario dir holding detection.json")
    ap.add_argument("--json", type=Path, help="also write the full result as JSON here")
    ap.add_argument("--min-catches", type=int, default=None, help="override the pass threshold")
    ap.add_argument("--fail-on-control-fp", action="store_true",
                    help="also fail when a clean control was flagged as a fraud")
    ap.add_argument("--quiet", action="store_true", help="print only the verdict line")
    args = ap.parse_args()

    if not args.review.is_file():
        print(f"score_review: missing review file: {args.review}", file=sys.stderr)
        return 2
    rules = load_scenario(args.scenario)
    if args.min_catches is not None:
        rules["pass_threshold"] = args.min_catches

    result = score(args.review.read_text(encoding="utf-8", errors="replace"), rules)
    result["review_file"] = str(args.review)

    text = render(result)
    print(text.splitlines()[-1] if args.quiet else text)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if result["catches"] < result["pass_threshold"]:
        return 1
    if args.fail_on_control_fp and result["control_false_positives"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
