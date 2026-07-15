#!/usr/bin/env python3
"""Build anonymized blind-review prompts for Hybrid Model Fusion."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from panel_config import load_panelists


LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_routing(report_path: Path) -> dict[str, object]:
    path = report_path.with_suffix(report_path.suffix + ".routing.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def stable_seed(original_prompt: str, existing: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    digest.update(original_prompt.encode("utf-8", errors="replace"))
    for panelist in sorted(existing, key=lambda item: str(item["slug"])):
        digest.update(str(panelist["slug"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(read_text(Path(panelist["path"])).encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:24]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", help="Hybrid fusion run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    skill_dir = Path(__file__).resolve().parents[1]
    panelists = load_panelists(skill_dir)
    rubric_path = skill_dir / "references" / "peer_review_rubric.md"
    rubric = read_text(rubric_path)
    original_prompt_path = run_dir / "original_prompt.md"
    original_prompt_missing = not original_prompt_path.is_file() or original_prompt_path.stat().st_size == 0
    original_prompt = (
        read_text(original_prompt_path)
        if not original_prompt_missing
        else "[missing original_prompt.md: reviewers must judge task fit only where inferable from the reports]"
    )

    existing = []
    for panelist in panelists:
        report_path = run_dir / panelist["report_file"]
        if report_path.is_file() and report_path.stat().st_size > 0:
            item = dict(panelist)
            item["path"] = report_path
            item["routing"] = read_routing(report_path)
            if item["routing"].get("fallback_used") and item["routing"].get("resolved_model") == "gpt-5.5":
                item["display"] = "GPT-5.5 (safety fallback)"
            existing.append(item)

    if len(existing) < 2:
        raise SystemExit("Need at least two non-empty panel reports to build peer-review packets.")

    seed = stable_seed(original_prompt, existing)
    rng = random.Random(seed)
    label_assignment = list(existing)
    rng.shuffle(label_assignment)

    mapping = {}
    for index, panelist in enumerate(label_assignment):
        label = LABELS[index]
        routing = panelist.get("routing", {})
        mapping[label] = {
            "model": panelist["slug"],
            "display": panelist["display"],
            "file": panelist["report_file"],
            "primary_model": routing.get("primary_model"),
            "resolved_model": routing.get("resolved_model"),
            "resolved_effort": routing.get("resolved_effort"),
            "fallback_used": bool(routing.get("fallback_used")),
            "fallback_reason": routing.get("fallback_reason", ""),
        }

    (run_dir / "response_mapping.json").write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "mode": "hybrid_model_fusion",
        "mapping_file": "response_mapping.json",
        "original_prompt_file": "original_prompt.md",
        "label_assignment_seed": seed,
        "warnings": ["original_prompt.md missing; packet used explicit missing-task placeholder."]
        if original_prompt_missing
        else [],
        "review_prompts": [],
        "note": "Peer-review prompts are anonymized, run-seeded, presentation-randomized, and exclude counted self-review.",
    }

    for reviewer in existing:
        reviewed_labels = []
        for label, meta in mapping.items():
            if meta["model"] == reviewer["slug"]:
                continue
            reviewed_labels.append(label)
        rng.shuffle(reviewed_labels)

        reviewed = []
        for label in reviewed_labels:
            meta = mapping[label]
            report_text = read_text(run_dir / meta["file"])
            reviewed.append((label, report_text))

        prompt_parts = [
            "You are a blind peer reviewer in a Hybrid Model Fusion run.",
            "Review only the anonymized responses below. Do not infer model identity.",
            f'Your reviewer id is "{reviewer["slug"]}".',
            "",
            "## Original User Task",
            "Use this task to judge completeness and task fit.",
            "<original_user_task>",
            original_prompt,
            "</original_user_task>",
            "",
            rubric,
            "",
            "You are reviewing these responses:",
            "",
        ]
        for label, report_text in reviewed:
            prompt_parts.extend(
                [
                    f"## Response {label}",
                    "<untrusted_model_report>",
                    report_text,
                    "</untrusted_model_report>",
                    "",
                ]
            )
        prompt_parts.extend(
            [
                "Return a fenced JSON block first, then a short Markdown explanation.",
                "The JSON must include exactly the reviewed response labels and no self-review.",
                "",
            ]
        )

        prompt_file = run_dir / f'review_prompt_{reviewer["slug"]}.txt'
        prompt_file.write_text("\n".join(prompt_parts), encoding="utf-8")
        manifest["review_prompts"].append(
            {
                "reviewer": reviewer["slug"],
                "prompt_file": prompt_file.name,
                "output_md": reviewer["review_file"],
                "output_json": f'review_{reviewer["slug"]}.json',
                "reviewed_responses": [label for label, _ in reviewed],
                "presentation_order": [label for label, _ in reviewed],
                "excluded_self_label": next(
                    (label for label, meta in mapping.items() if meta["model"] == reviewer["slug"]),
                    None,
                ),
            }
        )

    (run_dir / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote response mapping and {len(manifest['review_prompts'])} review prompts in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
