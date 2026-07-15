#!/usr/bin/env python3
"""Aggregate DRACO-style evaluation grades for Hybrid Model Fusion arms."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ARMS = ["best-solo", "model-fusion", "hybrid", "fable-panelist", "self-fusion"]
CATEGORIES = ["accuracy", "evidence", "reasoning", "decision_usefulness"]
PENALTIES = ["confident_wrong", "verbosity", "missed_task", "unsupported_claims"]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSONL ({exc})") from exc
    return rows


def extract_json(text: str) -> dict[str, Any]:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = fenced or [text]
    for candidate in candidates:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no parseable grade JSON")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_grade(raw: dict[str, Any], task_id: str, arm: str, pass_id: str) -> dict[str, Any]:
    scores = raw.get("scores", {})
    penalties = raw.get("penalties", {})
    subtotal = sum(max(0.0, min(10.0, as_float(scores.get(cat)))) for cat in CATEGORIES)
    penalty_total = sum(max(0.0, as_float(penalties.get(name))) for name in PENALTIES)
    total = as_float(raw.get("total"), subtotal - penalty_total)
    return {
        "task_id": str(raw.get("task_id") or task_id),
        "arm": str(raw.get("arm") or arm),
        "pass_id": str(raw.get("pass_id") or pass_id),
        "scores": {cat: as_float(scores.get(cat)) for cat in CATEGORIES},
        "penalties": {name: as_float(penalties.get(name)) for name in PENALTIES},
        "total": round(total, 2),
        "rationale": raw.get("rationale", ""),
        "fatal_flaws": raw.get("fatal_flaws", []),
    }


def discover_grades(out_dir: Path, tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    grades: list[dict[str, Any]] = []
    warnings: list[str] = []
    for task in tasks:
        task_id = str(task["id"])
        for arm in ARMS:
            arm_dir = out_dir / task_id / arm
            if not arm_dir.is_dir():
                warnings.append(f"{task_id}/{arm}: missing arm directory")
                continue
            grade_files = sorted(arm_dir.glob("grade_pass_*.json")) + sorted(arm_dir.glob("grade_pass_*.md"))
            if len(grade_files) < 3:
                warnings.append(f"{task_id}/{arm}: only {len(grade_files)} grade pass(es); target is >=3")
            for grade_file in grade_files:
                try:
                    raw = extract_json(grade_file.read_text(encoding="utf-8"))
                    grades.append(normalize_grade(raw, task_id, arm, grade_file.stem))
                except Exception as exc:  # noqa: BLE001 - report invalid grade but continue.
                    warnings.append(f"{task_id}/{arm}/{grade_file.name}: invalid grade ({exc})")
    return grades, warnings


def summarize(grades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for grade in grades:
        grouped[grade["arm"]].append(grade)
    rows = []
    for arm, items in grouped.items():
        totals = [as_float(item["total"]) for item in items]
        rows.append(
            {
                "arm": arm,
                "grade_count": len(items),
                "avg_total": round(sum(totals) / len(totals), 2) if totals else 0.0,
                "min_total": round(min(totals), 2) if totals else 0.0,
                "max_total": round(max(totals), 2) if totals else 0.0,
            }
        )
    rows.sort(key=lambda row: (-row["avg_total"], row["arm"]))
    return rows


def write_summary(out_dir: Path, grades: list[dict[str, Any]], warnings: list[str]) -> None:
    rows = summarize(grades)
    payload = {"arms": rows, "grades": grades, "warnings": warnings}
    (out_dir / "eval_results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Hybrid Fusion Eval Results",
        "",
        "| Rank | Arm | Avg total | Grade count | Min | Max |",
        "| ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            f"| {rank} | {row['arm']} | {row['avg_total']:.2f} | {row['grade_count']} | "
            f"{row['min_total']:.2f} | {row['max_total']:.2f} |"
        )
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    (out_dir / "eval_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default=str(Path(__file__).with_name("tasks.jsonl")), help="Tasks JSONL")
    parser.add_argument("--out", required=True, help="Evaluation output directory")
    args = parser.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    tasks = read_jsonl(Path(args.tasks).expanduser().resolve())
    grades, warnings = discover_grades(out_dir, tasks)
    write_summary(out_dir, grades, warnings)
    print(f"Wrote {out_dir / 'eval_results.json'} and {out_dir / 'eval_results.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
