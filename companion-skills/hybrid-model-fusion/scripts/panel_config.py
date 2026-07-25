#!/usr/bin/env python3
"""Load the Hybrid Model Fusion panel roster."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PANELISTS = [
    {
        "slug": "opus5",
        "display": "Opus 5",
        "report_file": "report_opus5.md",
        "prompt_file": "prompt_opus5.txt",
        "review_file": "review_opus5.md",
        "review_prompt_file": "review_prompt_opus5.txt",
        "html_title": "Opus 5 (max)",
    },
    {
        "slug": "grok4.5",
        "display": "Grok 4.5",
        "report_file": "report_grok4.5.md",
        "prompt_file": "prompt_grok4.5.txt",
        "review_file": "review_grok4.5.md",
        "review_prompt_file": "review_prompt_grok4.5.txt",
        "html_title": "Grok 4.5 (high)",
    },
    {
        "slug": "gemini3.5flash",
        "display": "Gemini 3.5 Flash",
        "report_file": "report_gemini3.5flash.md",
        "prompt_file": "prompt_gemini3.5flash.txt",
        "review_file": "review_gemini3.5flash.md",
        "review_prompt_file": "review_prompt_gemini3.5flash.txt",
        "html_title": "Gemini 3.5 Flash (High)",
    },
    {
        "slug": "gpt5.6sol",
        "display": "GPT-5.6 Sol",
        "report_file": "report_gpt5.6sol.md",
        "prompt_file": "prompt_gpt5.6sol.txt",
        "review_file": "review_gpt5.6sol.md",
        "review_prompt_file": "review_prompt_gpt5.6sol.txt",
        "html_title": "GPT-5.6 Sol (max)",
    },
]


def skill_dir_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(skill_dir: Path | None = None) -> dict[str, Any]:
    skill_dir = skill_dir or skill_dir_from_here()
    path = skill_dir / "config" / "panel.json"
    if not path.is_file():
        return {"version": 1, "panelists": DEFAULT_PANELISTS}
    data = json.loads(path.read_text(encoding="utf-8"))
    panelists = data.get("panelists")
    if not isinstance(panelists, list) or not panelists:
        raise ValueError(f"{path} must contain a non-empty panelists list")
    required = {"slug", "display", "report_file", "prompt_file", "review_file", "review_prompt_file"}
    for item in panelists:
        missing = required - set(item)
        if missing:
            raise ValueError(f"{path}: panelist {item!r} missing {sorted(missing)}")
    return data


def load_panelists(skill_dir: Path | None = None) -> list[dict[str, str]]:
    data = load_config(skill_dir)
    panelists = data.get("panelists", DEFAULT_PANELISTS)
    preset_name = os.environ.get("FUSION_PANEL_PRESET", "default")
    presets = data.get("presets", {})
    if preset_name in presets:
        catalog = {item["slug"]: item for item in panelists}
        selected = []
        for slug in presets[preset_name].get("panelists", []):
            if slug not in catalog:
                raise ValueError(f"preset {preset_name!r} references unknown panelist {slug!r}")
            selected.append(dict(catalog[slug]))
        if selected:
            return selected
    return [dict(item) for item in panelists if item.get("slug") in {"opus5", "grok4.5", "gemini3.5flash", "gpt5.6sol"}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["models", "panel-json", "render-targets", "preset"])
    parser.add_argument("--topic", default="Fusion")
    args = parser.parse_args()

    panelists = load_panelists()
    if args.command == "models":
        for item in panelists:
            print(item["slug"])
    elif args.command == "panel-json":
        print(json.dumps(panelists, indent=2, sort_keys=True))
    elif args.command == "render-targets":
        for item in panelists:
            base = item["report_file"].removesuffix(".md")
            print(f"{base}\t{item.get('html_title', item['display'])} - {args.topic}")
        print(f"report_fusion\tFusion Report - {args.topic}")
        print(f"aggregate_scorecard\tAggregate Scorecard - {args.topic}")
    elif args.command == "preset":
        print(os.environ.get("FUSION_PANEL_PRESET", "default"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
