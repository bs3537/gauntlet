#!/usr/bin/env bash
# preflight_selftest.sh — deterministic behavioral test of the Stage-0/Stage-2 codex
# preflight. No network, no real codex: a stub `codex` on PATH simulates each outcome and
# `run_review.sh --preflight-only` must map it to the right exit code.
#
#   0 = reachable, no limit signal      -> run normally
#   4 = reachable but QUOTA/RATE limited -> downgrade to PANEL=0 / labeled self-review
#   1 = unreachable or unauthenticated   -> fix auth, or fall back
#
# The 0/1/4 split is the whole point: a quota wall and a dead endpoint need different
# responses, and both must be discovered BEFORE the ~1-hour first pass, not after it.
# PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../scripts/run_review.sh"
[ -f "$RUNNER" ] || { echo "FAILED: runner missing: $RUNNER"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/gauntlet-preflight.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/run"
export PATH="$TMP/bin:$PATH"

fails=0
# Each mode makes the stub behave like one real codex outcome; CODEX_STUB_MODE selects it.
cat > "$TMP/bin/codex" <<'STUB'
#!/usr/bin/env bash
out=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
cat > /dev/null
case "${CODEX_STUB_MODE:-ok}" in
  ok)      printf 'OK\n' > "$out"; exit 0 ;;
  quota)   echo "stream error: You've hit your usage limit. Try again after 5:00 PM." >&2; exit 1 ;;
  rate)    echo "429 Too Many Requests (rate limit exceeded)" >&2; exit 1 ;;
  weekly)  printf 'OK\n' > "$out"; echo "note: weekly limit reached for the reviewer model" >&2; exit 0 ;;
  authfail) echo "error: not logged in. Run 'codex login'." >&2; exit 1 ;;
  silent)  exit 1 ;;
  garbage) printf 'I cannot comply.\n' > "$out"; exit 0 ;;
esac
STUB
chmod +x "$TMP/bin/codex"

check() {  # check <label> <mode> <expected_rc>
  local label="$1" mode="$2" want="$3" got
  env CODEX_STUB_MODE="$mode" bash "$RUNNER" --preflight-only "$TMP/run" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then
    printf 'PASS  %-56s (rc=%s)\n' "$label" "$got"
  else
    printf 'FAIL  %-56s (rc=%s, wanted %s)\n' "$label" "$got" "$want"; fails=$((fails+1))
  fi
}

check "reachable and healthy -> proceed"                    ok       0
check "usage limit hit -> quota downgrade signal"           quota    4
check "429 rate limit -> quota downgrade signal"            rate     4
check "answered BUT weekly limit warned -> quota signal"    weekly   4
check "unauthenticated -> launch failure"                   authfail 1
check "no output at all -> launch failure"                  silent   1
check "reachable but wrong answer -> launch failure"        garbage  1

# The judge launch must inherit the same three-way outcome (PREFLIGHT defaults on for judge).
printf 'REVIEW PROMPT (stub)\n' > "$TMP/run/09_reviewer_prompt.txt"
env CODEX_STUB_MODE=quota bash "$RUNNER" "$TMP/run" 1 >/dev/null 2>&1
rc=$?
[ "$rc" -eq 4 ] && printf 'PASS  %-56s (rc=%s)\n' "judge launch aborts on a quota-limited preflight" "$rc" \
                || { printf 'FAIL  %-56s (rc=%s, wanted 4)\n' "judge launch aborts on a quota-limited preflight" "$rc"; fails=$((fails+1)); }

env CODEX_STUB_MODE=ok PREFLIGHT=0 QC_MODE=lane bash "$RUNNER" --show-routing | grep -q 'preflight=0' \
  && printf 'PASS  %-56s\n' "lane default keeps preflight off (no 4x redundant ping)" \
  || { printf 'FAIL  %-56s\n' "lane default keeps preflight off"; fails=$((fails+1)); }

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: preflight reachability/quota self-test (9/9)."; exit 0
else
  echo "FAILED: $fails assertion(s)."; exit 1
fi
