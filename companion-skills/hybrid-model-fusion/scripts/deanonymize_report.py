#!/usr/bin/env python3
"""De-anonymize a blind judge report: replace run-randomized `Response A/B/C/D` labels with the real
model display names, IN PLACE.

The judge adjudicates BLIND (it is shown panelist reports only as `Response A/B/C/D` under a
run-randomized mapping, so it cannot favor "its own" manufacturer's report — the labeled
self-preference mechanism). This step restores model identities in the FINISHED report so the reader
still sees which model proposed what (esp. the unique-insights table), without ever having biased the
adjudication.

Usage:
  deanonymize_report.py <report_file> <response_mapping.json>

response_mapping.json format (written by the judge-prompt / review-packet builder):
  { "A": {"model": "opus4.8", "display": "Opus 4.8", ...}, "B": {...}, ... }
Keys may be a bare letter ("A") or a full label ("Response A"); the last whitespace token is the letter.
Only the word forms `Response X` / `Report X` / `Panelist X` are rewritten (the judge is instructed to
always use the full label), so ordinary prose containing a stray capital letter is never touched.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load_display_map(mapping_path: Path) -> dict[str, str]:
    try:
        raw = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    disp: dict[str, str] = {}
    for key, info in raw.items():
        letter = str(key).strip().split()[-1].upper()
        name = info.get("display") if isinstance(info, dict) else str(info)
        if letter and name:
            disp[letter] = str(name)
    return disp


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: deanonymize_report.py <report_file> <response_mapping.json>\n")
        return 2
    report_path = Path(sys.argv[1])
    disp = load_display_map(Path(sys.argv[2]))
    if not disp or not report_path.is_file():
        return 0  # nothing to do (unblinded run, missing mapping, or missing report) — leave as-is
    text = report_path.read_text(encoding="utf-8", errors="replace")

    # Match a label PREFIX (Response/Report/Panelist, singular or plural) followed by a comma/and-separated
    # list of single letters — e.g. "Response A", "Responses A and D", "Panelists A, B and C". Only the full
    # label forms are rewritten (a bare stray capital in prose is never matched), and the whole match is
    # replaced only if EVERY listed token is a known label letter — otherwise it is left untouched.
    _sep = r"\s*(?:,|and|&|or|/)\s*"
    label_re = re.compile(rf"\b(?:Responses?|Reports?|Panelists?)\s+([A-Za-z](?:{_sep}[A-Za-z])*)\b")

    def repl(m: re.Match) -> str:
        tokens = re.split(_sep, m.group(1))
        if not tokens or any(len(t) != 1 or t.upper() not in disp for t in tokens):
            return m.group(0)
        names = [disp[t.upper()] for t in tokens]
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    new_text, n = label_re.subn(repl, text)
    if new_text != text:
        report_path.write_text(new_text, encoding="utf-8")
    sys.stderr.write(f"[deanon] {n} label->model substitutions ({', '.join(sorted(disp))})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
