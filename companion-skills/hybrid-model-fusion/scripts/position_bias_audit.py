#!/usr/bin/env python3
"""Audit accumulated hybrid runs for response-label position bias."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def iter_runs(root: Path):
    for manifest in root.glob("**/review_manifest.json"):
        scorecard = manifest.parent / "aggregate_scorecard.json"
        if scorecard.is_file():
            yield manifest.parent, manifest, scorecard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Directory containing hybrid run folders")
    parser.add_argument("--out", help="Optional output JSON path")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    label_positions: Counter[str] = Counter()
    winners: Counter[str] = Counter()
    first_label_wins = 0
    run_count = 0
    by_model: dict[str, Counter[str]] = defaultdict(Counter)

    for run_dir, manifest_path, scorecard_path in iter_runs(root):
        run_count += 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
        first_labels = set()
        for item in manifest.get("review_prompts", []):
            order = item.get("presentation_order") or item.get("reviewed_responses") or []
            if order:
                label_positions[str(order[0])] += 1
                first_labels.add(str(order[0]))
        responses = scorecard.get("responses", [])
        if responses:
            winner = str(responses[0].get("response"))
            winners[winner] += 1
            if winner in first_labels:
                first_label_wins += 1
        mapping_path = run_dir / "response_mapping.json"
        if mapping_path.is_file():
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            for label, meta in mapping.items():
                by_model[str(meta.get("model"))][str(label)] += 1

    payload = {
        "root": str(root),
        "run_count": run_count,
        "first_position_counts": dict(label_positions),
        "winner_counts": dict(winners),
        "winner_was_presented_first_count": first_label_wins,
        "model_label_counts": {model: dict(counts) for model, counts in by_model.items()},
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).expanduser().resolve().write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
