#!/usr/bin/env python3
"""Validate a blind peer-review output against mapping and manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aggregate_reviews import extract_json_object, load_review_manifest, normalize_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("reviewer")
    parser.add_argument("review_file")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    review_file = Path(args.review_file).expanduser().resolve()
    mapping_path = run_dir / "response_mapping.json"
    if not mapping_path.is_file():
        raise SystemExit(f"missing response_mapping.json in {run_dir}")
    if not review_file.is_file() or review_file.stat().st_size == 0:
        raise SystemExit(f"missing or empty review file: {review_file}")

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    warnings: list[str] = []
    allowed = load_review_manifest(run_dir, mapping, warnings).get(args.reviewer)
    raw = extract_json_object(review_file.read_text(encoding="utf-8"), allowed or set(mapping))
    normalized, review_warnings = normalize_review(raw, args.reviewer, mapping, allowed)
    warnings.extend(review_warnings)

    ranked = normalized.get("ranked_order", [])
    if not ranked:
        raise SystemExit(f"{args.reviewer}: ranked_order is empty after normalization")
    if len(ranked) < len(allowed or ranked):
        raise SystemExit(f"{args.reviewer}: ranked_order does not cover all manifest-reviewed labels")
    missing_scores = [label for label in ranked if label not in normalized.get("scores", {})]
    if missing_scores:
        raise SystemExit(f"{args.reviewer}: missing scores for {', '.join(missing_scores)}")

    print(json.dumps({"reviewer": args.reviewer, "ranked_order": ranked, "warnings": warnings}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
