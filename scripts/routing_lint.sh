#!/usr/bin/env bash
# routing_lint.sh — fail on any STALE model name anywhere in the Gauntlet core.
#
# Prompt templates get their routing by token substitution (scripts/render_prompt.sh), but
# prose cannot: SKILL.md, README.md, install.sh and the docs plan legitimately name the
# models in running text. Those copies are what silently rot after a model bump. This lint
# is the guard: it reads config/routing.env — the single source of truth — and reports every
# place a model name of a known class does not match the configured value, with file:line.
#
# A model bump is therefore: edit config/routing.env, run this, fix exactly what it lists.
#
# Usage:
#   routing_lint.sh              # lint the core tree
#   routing_lint.sh <path>...    # lint specific files
#
# A line containing `routing-lint: allow` (e.g. as an HTML comment in Markdown) is exempt —
# for deliberate references to another model, such as a launcher's own fallback route.
# Exit: 0 clean · 1 stale names found · 2 config/setup error.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROUTING_CONF="${GAUNTLET_ROUTING_CONF:-$ROOT/config/routing.env}"
[ -f "$ROUTING_CONF" ] || { echo "routing_lint: missing routing config: $ROUTING_CONF" >&2; exit 2; }
# shellcheck disable=SC1090
. "$ROUTING_CONF"
[ -n "${GAUNTLET_LINT_CLASSES:-}" ] || { echo "routing_lint: GAUNTLET_LINT_CLASSES unset in $ROUTING_CONF" >&2; exit 2; }

# Default scope: the Gauntlet core only. companion-skills/ are vendored third-party skills
# with their own (legitimately different) model routes, and config/routing.env is the
# definition itself — linting either would be self-defeating noise.
targets=("$@")
if [ "${#targets[@]}" -eq 0 ]; then
  mapfile -t targets < <(
    find "$ROOT" \
      -path "$ROOT/.git" -prune -o \
      -path "$ROOT/companion-skills" -prune -o \
      -path "$ROOT/config" -prune -o \
      -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.html' -o -name '*.json' \) -print
  )
fi

printf '%s\n' "${targets[@]}" | GAUNTLET_LINT_CLASSES="$GAUNTLET_LINT_CLASSES" python3 -c '
import os, re, sys

classes = []
for spec in os.environ["GAUNTLET_LINT_CLASSES"].strip().splitlines():
    spec = spec.strip()
    if not spec:
        continue
    pattern, expected = spec.rsplit("|", 1)
    classes.append((re.compile(pattern), expected.strip()))

stale = 0
checked = 0
for path in (line.strip() for line in sys.stdin if line.strip()):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError as exc:
        print(f"routing_lint: cannot read {path}: {exc}", file=sys.stderr)
        continue
    checked += 1
    for lineno, line in enumerate(lines, 1):
        if "routing-lint: allow" in line:
            continue
        for pattern, expected in classes:
            for match in pattern.finditer(line):
                if match.group(0) != expected:
                    print(f"{path}:{lineno}: stale {match.group(0)!r} (config says {expected!r})")
                    stale += 1

print(f"routing_lint: {checked} file(s) checked, {stale} stale reference(s)")
sys.exit(1 if stale else 0)
'
