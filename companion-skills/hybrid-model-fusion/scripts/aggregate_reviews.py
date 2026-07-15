#!/usr/bin/env python3
"""Aggregate blind peer-review rankings for Hybrid Model Fusion."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from panel_config import load_panelists


DIMENSIONS = [
    "correctness",
    "evidence_quality",
    "completeness",
    "reasoning_quality",
    "calibration",
    "actionability",
]

def _iter_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for candidate in fenced:
        try:
            objects.append(json.loads(candidate))
        except json.JSONDecodeError:
            pass

    for start in [m.start() for m in re.finditer(r"\{", text)]:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    if obj not in objects:
                        objects.append(obj)
                    break
    return objects


def _has_nonzero_score(raw: dict[str, Any]) -> bool:
    scores = raw.get("scores", {})
    if not isinstance(scores, dict):
        return False
    for score_obj in scores.values():
        if not isinstance(score_obj, dict):
            continue
        for dim in [*DIMENSIONS, "total"]:
            if as_float(score_obj.get(dim), 0.0) != 0.0:
                return True
    return False


def _ranked_labels(raw: dict[str, Any]) -> set[str]:
    ranked = raw.get("ranked_order", [])
    if not isinstance(ranked, list):
        return set()
    return {str(label).upper() for label in ranked}


def extract_json_object(text: str, valid_labels: set[str] | None = None) -> dict[str, Any]:
    objects = _iter_json_objects(text)
    if not objects:
        raise ValueError("no JSON object found")
    if valid_labels:
        exact = [
            obj
            for obj in objects
            if _ranked_labels(obj) == valid_labels and set(str(label).upper() for label in obj.get("scores", {})) <= valid_labels
        ]
        for obj in exact:
            if _has_nonzero_score(obj):
                return obj
        if exact:
            return exact[0]
    for obj in objects:
        ranked = _ranked_labels(obj)
        if not ranked:
            continue
        if valid_labels is not None and not ranked.intersection(valid_labels):
            continue
        if _has_nonzero_score(obj):
            return obj
    for obj in objects:
        ranked = _ranked_labels(obj)
        if ranked and (valid_labels is None or ranked.intersection(valid_labels)):
            return obj
    raise ValueError("no usable review JSON found")
    raise ValueError("unterminated JSON object")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def normalize_review(
    raw: dict[str, Any],
    reviewer_slug: str,
    mapping: dict[str, Any],
    allowed_labels: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    labels = set(mapping)
    allowed = set(allowed_labels or labels)
    self_labels = {label for label, meta in mapping.items() if meta.get("model") == reviewer_slug}
    allowed -= self_labels

    def keep_label(label: Any, field: str) -> str | None:
        normalized = str(label).upper()
        if normalized not in labels:
            warnings.append(f"{reviewer_slug}: dropped unknown label {normalized!r} from {field}.")
            return None
        if normalized in self_labels:
            warnings.append(f"{reviewer_slug}: stripped self-ballot label {normalized} from {field}.")
            return None
        if normalized not in allowed:
            warnings.append(f"{reviewer_slug}: dropped manifest-disallowed label {normalized} from {field}.")
            return None
        return normalized

    reviewed = [label for label in (keep_label(label, "reviewed_responses") for label in raw.get("reviewed_responses", [])) if label]
    ranked = [label for label in (keep_label(label, "ranked_order") for label in raw.get("ranked_order", [])) if label]

    if not reviewed:
        reviewed = [label for label in allowed if label in set(ranked)] or sorted(allowed)
    if not ranked:
        warnings.append(f"{reviewer_slug}: missing ranked_order; aggregation will rely on scores only.")
    if len(ranked) != len(set(ranked)):
        warnings.append(f"{reviewer_slug}: duplicate labels in ranked_order.")
        ranked = list(dict.fromkeys(ranked))
    if reviewed and set(ranked) - set(reviewed):
        warnings.append(f"{reviewer_slug}: ranked_order includes labels outside reviewed_responses.")

    raw_scores = raw.get("scores", {})
    scores: dict[str, Any] = {}
    for label, score_obj in raw_scores.items():
        label = keep_label(label, "scores")
        if not label or not isinstance(score_obj, dict):
            continue
        normalized_dims = {dim: as_float(score_obj.get(dim), 0.0) for dim in DIMENSIONS}
        total = as_float(score_obj.get("total"), sum(normalized_dims.values()))
        if total == 0.0:
            total = sum(normalized_dims.values())
        scores[label] = {**normalized_dims, "total": total}

    confidence = as_float(raw.get("confidence"), 1.0)
    if confidence < 0 or confidence > 1:
        warnings.append(f"{reviewer_slug}: confidence outside 0-1; using 1.0.")
        confidence = 1.0
    elif confidence == 0:
        warnings.append(f"{reviewer_slug}: confidence is 0.0; keeping explicit zero weight.")

    normalized = {
        "reviewer": str(raw.get("reviewer") or reviewer_slug),
        "reviewed_responses": reviewed,
        "ranked_order": ranked,
        "forced_choice_winner": str(raw.get("forced_choice_winner") or (ranked[0] if ranked else "")).upper(),
        "scores": scores,
        "best_supported_claims": raw.get("best_supported_claims", {}),
        "weak_or_unsupported_claims": raw.get("weak_or_unsupported_claims", {}),
        "missed_by_response": raw.get("missed_by_response", {}),
        "claim_verdicts": raw.get("claim_verdicts", []),
        "decisive_differences": raw.get("decisive_differences", []),
        "confidence": confidence,
        "notes_for_judge": raw.get("notes_for_judge", []),
    }
    return normalized, warnings


def pairwise_cycle(peer_rankings: list[dict[str, Any]], labels: list[str]) -> bool:
    if len(labels) < 3:
        return False
    wins: dict[tuple[str, str], int] = defaultdict(int)
    for ranking in peer_rankings:
        order = ranking.get("ranked_order", [])
        position = {label: idx for idx, label in enumerate(order)}
        for a in labels:
            for b in labels:
                if a == b or a not in position or b not in position:
                    continue
                if position[a] < position[b]:
                    wins[(a, b)] += 1
    directed: set[tuple[str, str]] = set()
    for a in labels:
        for b in labels:
            if a >= b:
                continue
            if wins[(a, b)] > wins[(b, a)]:
                directed.add((a, b))
            elif wins[(b, a)] > wins[(a, b)]:
                directed.add((b, a))
    for a in labels:
        for b in labels:
            for c in labels:
                if len({a, b, c}) == 3 and (a, b) in directed and (b, c) in directed and (c, a) in directed:
                    return True
    return False


def rank_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (-row["borda_rate"], -row["weighted_total_score"], -row["avg_total_score"])


def consensus_label(
    rows: list[dict[str, Any]],
    valid_review_count: int,
    expected_review_count: int,
    peer_rankings: list[dict[str, Any]],
) -> str:
    if not rows:
        return "no_consensus"
    if pairwise_cycle(peer_rankings, [row["response"] for row in rows]):
        return "peer_cycle"
    ranked_by_borda = sorted(rows, key=rank_sort_key)
    ranked_by_score = sorted(rows, key=lambda row: (-row["avg_total_score"], -row["borda_rate"], -row["weighted_total_score"]))
    if ranked_by_borda[0]["response"] != ranked_by_score[0]["response"]:
        return "split_consensus"
    if valid_review_count < expected_review_count:
        return "degraded_coverage"
    if len(rows) == 1:
        return "weak_consensus"
    top = ranked_by_borda[0]
    score_margin = ranked_by_score[0]["avg_total_score"] - ranked_by_score[1]["avg_total_score"]
    if top["ranking_ballots_received"] >= 2 and top["first_place_votes"] == top["ranking_ballots_received"] and score_margin >= 5:
        return "strong_consensus"
    return "weak_consensus"


def load_review_manifest(run_dir: Path, mapping: dict[str, Any], warnings: list[str]) -> dict[str, set[str]]:
    manifest_path = run_dir / "review_manifest.json"
    default = {
        meta.get("model"): {label for label in mapping if label != self_label}
        for self_label, meta in mapping.items()
    }
    if not manifest_path.is_file():
        warnings.append("review_manifest.json missing; using mapping-derived self-review exclusions only.")
        return default
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append(f"review_manifest.json invalid ({exc}); using mapping-derived self-review exclusions only.")
        return default
    allowed: dict[str, set[str]] = {}
    for item in manifest.get("review_prompts", []):
        reviewer = item.get("reviewer")
        reviewed = {str(label).upper() for label in item.get("reviewed_responses", []) if str(label).upper() in mapping}
        if reviewer and reviewed:
            allowed[str(reviewer)] = reviewed
    for reviewer, labels in default.items():
        allowed.setdefault(str(reviewer), labels)
    return allowed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", help="Hybrid fusion run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    mapping_path = run_dir / "response_mapping.json"
    if not mapping_path.is_file():
        raise SystemExit(f"Missing response mapping: {mapping_path}")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    panelists = load_panelists(Path(__file__).resolve().parents[1])
    review_files = [(item["slug"], item["review_file"]) for item in panelists]

    warnings: list[str] = []
    allowed_by_reviewer = load_review_manifest(run_dir, mapping, warnings)
    valid_reviews: list[dict[str, Any]] = []
    for reviewer_slug, filename in review_files:
        path = run_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            warnings.append(f"{reviewer_slug}: missing review file {filename}.")
            continue
        try:
            raw = extract_json_object(path.read_text(encoding="utf-8"), set(mapping))
            normalized, review_warnings = normalize_review(
                raw,
                reviewer_slug,
                mapping,
                allowed_by_reviewer.get(reviewer_slug),
            )
        except Exception as exc:  # noqa: BLE001 - preserve parse error in audit output.
            warnings.append(f"{reviewer_slug}: excluded invalid review JSON ({exc}).")
            continue
        warnings.extend(review_warnings)
        valid_reviews.append(normalized)
        (run_dir / f"review_{reviewer_slug}.json").write_text(
            json.dumps(normalized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    aggregates: dict[str, Any] = {
        label: {
            "response": label,
            "model": meta.get("model"),
            "display": meta.get("display"),
            "file": meta.get("file"),
            "borda_points": 0.0,
            "borda_rates": [],
            "weighted_borda_rates": [],
            "ranking_weight_sum": 0.0,
            "total_scores": [],
            "weighted_total_sum": 0.0,
            "weight_sum": 0.0,
            "dimension_scores": defaultdict(list),
            "ranked_by": [],
        }
        for label, meta in mapping.items()
    }

    peer_rankings = []
    contested_claims = []
    for review in valid_reviews:
        ranked = review.get("ranked_order", [])
        n = len(ranked)
        confidence = as_float(review.get("confidence"), 1.0)
        for index, label in enumerate(ranked):
            if label in aggregates:
                raw_points = n - index - 1
                rate = raw_points / (n - 1) if n > 1 else 0.0
                aggregates[label]["borda_points"] += raw_points
                aggregates[label]["borda_rates"].append(rate)
                aggregates[label]["weighted_borda_rates"].append(rate * confidence)
                aggregates[label]["ranking_weight_sum"] += confidence
                aggregates[label]["ranked_by"].append({"reviewer": review["reviewer"], "rank": index + 1})
        peer_rankings.append({"reviewer": review["reviewer"], "ranked_order": ranked})
        for item in review.get("claim_verdicts", []) or []:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("verdict", "")).lower()
            if verdict in {"weak", "flawed", "unverified", "contested", "refuted"}:
                contested_claims.append({"reviewer": review["reviewer"], **item})

        for label, score in review.get("scores", {}).items():
            if label not in aggregates:
                continue
            total = as_float(score.get("total"), 0.0)
            aggregates[label]["total_scores"].append(total)
            aggregates[label]["weighted_total_sum"] += total * confidence
            aggregates[label]["weight_sum"] += confidence
            for dim in DIMENSIONS:
                aggregates[label]["dimension_scores"][dim].append(as_float(score.get(dim), 0.0))

    rows = []
    for label, data in aggregates.items():
        total_scores = data["total_scores"]
        borda_rates = data["borda_rates"]
        ranking_weight_sum = data["ranking_weight_sum"]
        weighted_borda_rate = (
            sum(data["weighted_borda_rates"]) / ranking_weight_sum if ranking_weight_sum else 0.0
        )
        avg_total = sum(total_scores) / len(total_scores) if total_scores else 0.0
        weighted = data["weighted_total_sum"] / data["weight_sum"] if data["weight_sum"] else avg_total
        dim_avg = {
            dim: (sum(values) / len(values) if values else 0.0)
            for dim, values in data["dimension_scores"].items()
        }
        rows.append(
            {
                "response": label,
                "model": data["model"],
                "display": data["display"],
                "file": data["file"],
                "borda_points": data["borda_points"],
                "borda_rate": round(weighted_borda_rate, 4),
                "raw_borda_rate": round(sum(borda_rates) / len(borda_rates), 4) if borda_rates else 0.0,
                "avg_total_score": round(avg_total, 2),
                "weighted_total_score": round(weighted, 2),
                "score_stdev": round(stdev(total_scores), 2),
                "reviews_received": len(total_scores),
                "ranking_ballots_received": len(borda_rates),
                "first_place_votes": sum(1 for vote in data["ranked_by"] if vote["rank"] == 1),
                "dimension_averages": {dim: round(dim_avg.get(dim, 0.0), 2) for dim in DIMENSIONS},
                "ranked_by": data["ranked_by"],
            }
        )

    rows.sort(key=rank_sort_key)
    previous_key: tuple[float, float, float] | None = None
    previous_rank = 0
    for index, row in enumerate(rows, start=1):
        current_key = rank_sort_key(row)
        if previous_key is not None and current_key == previous_key:
            row["aggregate_rank"] = previous_rank
            row["tied"] = True
        else:
            row["aggregate_rank"] = index
            row["tied"] = False
            previous_rank = index
            previous_key = current_key

    scorecard = {
        "mode": "hybrid_model_fusion",
        "consensus_label": consensus_label(rows, len(valid_reviews), len(review_files), peer_rankings),
        "valid_review_count": len(valid_reviews),
        "expected_review_count": len(review_files),
        "responses": rows,
        "peer_rankings": peer_rankings,
        "contested_claims_file": "contested_claims.json" if contested_claims else None,
        "warnings": warnings,
    }
    (run_dir / "aggregate_scorecard.json").write_text(
        json.dumps(scorecard, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if contested_claims:
        (run_dir / "contested_claims.json").write_text(
            json.dumps(contested_claims, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        claim_lines = ["# Contested Claims", ""]
        for item in contested_claims:
            claim_lines.append(
                f"- `{item.get('response', '?')}` {item.get('verdict', 'unverified')}: "
                f"{item.get('claim', '')} ({item.get('reason', 'no reason')})"
            )
        (run_dir / "contested_claims.md").write_text("\n".join(claim_lines) + "\n", encoding="utf-8")

    lines = [
        "# Aggregate Peer Review Scorecard",
        "",
        f"Consensus label: `{scorecard['consensus_label']}`",
        f"Valid reviews: {len(valid_reviews)}",
        "",
        "## Aggregate Ranking",
        "",
        "| Rank | Response | Model | Borda | Borda rate | Avg total | Weighted total | Reviews | Stdev | Tie |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['aggregate_rank']} | {row['response']} | {row['display']} | {row['borda_points']:.1f} | "
            f"{row['borda_rate']:.2f} | "
            f"{row['avg_total_score']:.2f} | {row['weighted_total_score']:.2f} | "
            f"{row['reviews_received']} | {row['score_stdev']:.2f} | {'yes' if row['tied'] else ''} |"
        )

    lines.extend(["", "## Per-Reviewer Rankings", "", "| Reviewer | Ranked order |", "| --- | --- |"])
    for ranking in peer_rankings:
        lines.append(f"| {ranking['reviewer']} | {' > '.join(ranking['ranked_order'])} |")

    lines.extend(["", "## Dimension Averages", ""])
    header = "| Response | Model | " + " | ".join(DIMENSIONS) + " |"
    lines.append(header)
    lines.append("| --- | --- | " + " | ".join(["---:"] * len(DIMENSIONS)) + " |")
    for row in rows:
        dims = " | ".join(f"{row['dimension_averages'][dim]:.2f}" for dim in DIMENSIONS)
        lines.append(f"| {row['response']} | {row['display']} | {dims} |")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")

    if contested_claims:
        lines.extend(["", "## Contested Claims", ""])
        lines.append("See `contested_claims.json` and `contested_claims.md`.")

    (run_dir / "aggregate_scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote aggregate_scorecard.json and aggregate_scorecard.md in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
