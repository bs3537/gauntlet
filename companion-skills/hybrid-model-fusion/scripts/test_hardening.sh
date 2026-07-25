#!/usr/bin/env bash
# Offline tests for the first-attempt-failure hardening (2026-07-14) in hybrid-model-fusion:
#   - _fusion_is_transient / _fusion_should_retry detectors (narrow; auth/policy NOT transient)
#   - run_grok.sh / run_gemini.sh bounded transient retry (incl. agy exit-0 + empty overload signature)
#   - _fusion_agy_recover_stub brain-dir promotion (positive) + legit-report-untouched (negative)
#   - detect_panel.sh auth preflight gate + run_hybrid.sh aborting when it fails
#   - run_gemini.sh large-prompt --add-dir path
# Fake CLIs only; no real API calls.
set -euo pipefail

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$SKILL/scripts/_fusion_lib.sh"
REL="$SKILL/scripts/fusion_reliability.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
BIN="$T/bin"; mkdir -p "$BIN"
pass(){ echo "  [ok] $1"; }
fail(){ echo "  [FAIL] $1" >&2; exit 1; }

# ── 1. transient detectors ──
(
  . "$LIB"
  echo "HTTP 429 Too Many Requests" > "$T/l1"; _fusion_is_transient "$T/l1" || fail "429 should be transient"
  echo "socket hang up (ECONNRESET)"  > "$T/l2"; _fusion_is_transient "$T/l2" || fail "reset should be transient"
  echo "503 Service Unavailable"      > "$T/l3"; _fusion_is_transient "$T/l3" || fail "503 should be transient"
  echo "Error: invalid API key"       > "$T/l4"; _fusion_is_transient "$T/l4" && fail "auth wrongly transient" || true
  echo "content_policy_violation"     > "$T/l5"; _fusion_is_transient "$T/l5" && fail "policy wrongly transient" || true
  : > "$T/empty"; printf x > "$T/nonempty"
  _fusion_should_retry 1   "$T/l1" "$T/empty"    || fail "should_retry: 429+empty"
  _fusion_should_retry 1   "$T/l1" "$T/nonempty" && fail "should_retry: had output" || true
  _fusion_should_retry 124 "$T/l1" "$T/empty"    && fail "should_retry: timeout"    || true
  _fusion_should_retry 1   "$T/l4" "$T/empty"    && fail "should_retry: auth err"   || true
  pass "transient detectors"
)

# ── 2. run_grok.sh: 429-then-succeed ──
cat > "$BIN/grok" <<'SH'
#!/usr/bin/env bash
c="$STATE/grok.count"; n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$c"
[ "$n" -le 1 ] && { echo "HTTP 429 Too Many Requests" >&2; exit 1; }
printf '# Grok recovered\n'; for _ in $(seq 1 40); do printf 'body line here\n'; done
SH
chmod +x "$BIN/grok"
printf 'p\n' > "$T/gp.txt"
STATE="$T" FUSION_GROK_BIN="$BIN/grok" FUSION_TIMEOUT=10 FUSION_TRANSIENT_BACKOFF=0 \
  bash "$SKILL/scripts/run_grok.sh" "$T/gp.txt" "$T/g_out.md" 2> "$T/g_err.log" || fail "run_grok retry did not recover"
grep -q 'Grok recovered' "$T/g_out.md"     || fail "run_grok did not use 2nd attempt"
grep -q 'transient failure' "$T/g_err.log" || fail "run_grok retry not logged"
[ "$(cat "$T/grok.count")" = "2" ]         || fail "run_grok not retried exactly once"
pass "run_grok transient retry"

# ── 3. run_gemini.sh: agy exit-0 + EMPTY stdout then real content ──
cat > "$BIN/agy" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in models) echo "Gemini 3.5 Flash (High)"; exit 0;; esac
c="$STATE/agy.count"; n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$c"
[ "$n" -le 1 ] && exit 0                     # attempt 1: exit 0 with EMPTY stdout
printf '# Gemini recovered\n'; for _ in $(seq 1 40); do printf 'body line here\n'; done
SH
chmod +x "$BIN/agy"
printf 'p\n' > "$T/ap.txt"
STATE="$T" PATH="$BIN:$PATH" FUSION_TIMEOUT=10 FUSION_AGY_TRANSIENT_BACKOFF=0 \
  bash "$SKILL/scripts/run_gemini.sh" "$T/ap.txt" "$T/a_out.md" 2> "$T/a_err.log" || fail "run_gemini exit0 retry did not recover"
grep -q 'Gemini recovered' "$T/a_out.md"       || fail "run_gemini did not use 2nd attempt"
grep -q 'transient agy failure' "$T/a_err.log" || fail "run_gemini retry not logged"
pass "run_gemini exit0+empty retry"

# ── 4. agy stub recovery (positive + negative) ──
brain_dir="$HOME/.gemini/antigravity-cli/brain/test-hyb-$$"
mkdir -p "$brain_dir"; real="$brain_dir/report.md"
{ printf '# Real Gemini Report\n\n'; for _ in $(seq 1 200); do printf 'Substantive analysis line.\n'; done; } > "$real"
{ printf '[COGNITIVE MONOLOGUE]\nI will now write the report.\n\n'; printf 'Report saved to file://%s\n' "$real"; printf 'Done.\n'; } > "$T/stub.md"
( . "$REL"; _fusion_agy_recover_stub "$T/stub.md" ) 2> "$T/rec.log"
grep -q 'Real Gemini Report' "$T/stub.md"  || fail "stub not promoted to brain report"
[ -f "$T/stub.md.stub_backup" ]            || fail "stub backup not created"
pass "agy stub recovery (positive)"
{ printf '[COGNITIVE MONOLOGUE]\nsee file://%s\n\n# Inline Report\n' "$real"; for _ in $(seq 1 200); do printf 'The real inline body content.\n'; done; } > "$T/legit.md"
cp "$T/legit.md" "$T/legit.orig"
( . "$REL"; _fusion_agy_recover_stub "$T/legit.md" ) 2>/dev/null
diff -q "$T/legit.md" "$T/legit.orig" >/dev/null || fail "legit report wrongly modified"
[ ! -f "$T/legit.md.stub_backup" ]               || fail "backup wrongly created for legit report"
pass "agy stub recovery (negative/legit untouched)"
# negative 2 (P0-2 regression): SHORT legit report with real findings ending in a citation to a
# BIGGER brain file -> must NOT be clobbered (the old <300-chars-after-pointer heuristic did clobber it).
{ printf '[COGNITIVE MONOLOGUE]\nplanning the analysis\n\n# Findings\n'; for i in $(seq 1 20); do printf -- '- Finding %d: a concrete substantive result about the market and its drivers.\n' "$i"; done; printf 'Intermediate reasoning trace: file://%s\n' "$real"; } > "$T/legit2.md"
cp "$T/legit2.md" "$T/legit2.orig"
( . "$REL"; _fusion_agy_recover_stub "$T/legit2.md" ) 2>/dev/null
diff -q "$T/legit2.md" "$T/legit2.orig" >/dev/null || fail "short legit report (P0-2) wrongly clobbered"
[ ! -f "$T/legit2.md.stub_backup" ]              || fail "backup wrongly created for short legit report"
pass "agy stub recovery (short legit report untouched — P0-2 regression)"
rm -rf "$brain_dir"

# ── 5. detect_panel.sh auth preflight (pass / catch / opt-out) ──
for c in claude grok codex agy; do printf '#!/usr/bin/env bash\nexit 0\n' > "$BIN/$c"; chmod +x "$BIN/$c"; done
PATH="$BIN:$PATH" FUSION_GROK_BIN="$BIN/grok" FUSION_AUTH_PROBE_TIMEOUT=5 \
  bash "$SKILL/scripts/detect_panel.sh" >/dev/null 2>&1 || fail "auth preflight false-negative (all ok)"
pass "detect_panel auth preflight (all ok)"
printf '#!/usr/bin/env bash\nexit 1\n' > "$BIN/codex"; chmod +x "$BIN/codex"
if PATH="$BIN:$PATH" FUSION_GROK_BIN="$BIN/grok" FUSION_AUTH_PROBE_TIMEOUT=5 \
     bash "$SKILL/scripts/detect_panel.sh" >/dev/null 2>&1; then fail "auth preflight missed failing codex"; fi
pass "detect_panel auth preflight (catches failure)"
PATH="$BIN:$PATH" FUSION_GROK_BIN="$BIN/grok" FUSION_AUTH_PREFLIGHT=0 \
  bash "$SKILL/scripts/detect_panel.sh" >/dev/null 2>&1 || fail "FUSION_AUTH_PREFLIGHT=0 did not skip"
pass "detect_panel auth preflight (opt-out)"

# ── 6. run_hybrid.sh aborts when the auth preflight fails (the |: exit $? wiring) ──
# claude/grok/agy pass auth; codex fails -> detect_panel exits 1 -> run_hybrid must stop at 'start'.
for c in claude grok agy; do printf '#!/usr/bin/env bash\nexit 0\n' > "$BIN/$c"; chmod +x "$BIN/$c"; done
printf '#!/usr/bin/env bash\nexit 1\n' > "$BIN/codex"; chmod +x "$BIN/codex"
printf 'test prompt\n' > "$T/hp.md"
if PATH="$BIN:$PATH" FUSION_GROK_BIN="$BIN/grok" FUSION_MCP_WARMUP=0 FUSION_AUTH_PROBE_TIMEOUT=5 \
     bash "$SKILL/scripts/run_hybrid.sh" --prompt "$T/hp.md" --run-dir "$T/hrun" >/dev/null 2>&1; then
  fail "run_hybrid did not abort on failed auth preflight"
fi
[ -f "$T/hrun/run_state.json" ] || fail "run_hybrid did not even write start state"
python3 -c "import json,sys; s=json.load(open('$T/hrun/run_state.json')); steps=[x['step'] for x in s['steps']]; sys.exit(0 if steps==['start'] else 1)" \
  || fail "run_hybrid proceeded past detect_panel despite auth failure"
pass "run_hybrid aborts on failed auth preflight"

# ── 7. run_gemini.sh large-prompt (>cap) -> --add-dir path ──
cat > "$BIN/agy" <<'SH'
#!/usr/bin/env bash
printf 'AGY2:%s\n' "$*" >> "$STATE/agy2.log"
case "${1:-}" in models) exit 0;; esac
printf '# big prompt handled\n'; for _ in $(seq 1 40); do printf 'body line here\n'; done
SH
chmod +x "$BIN/agy"
python3 -c "print('x'*130000)" > "$T/big.txt"
STATE="$T" PATH="$BIN:$PATH" FUSION_TIMEOUT=10 \
  bash "$SKILL/scripts/run_gemini.sh" "$T/big.txt" "$T/big_out.md" 2> "$T/big_err.log" || fail "large-prompt run failed"
grep -q -- '--add-dir' "$T/agy2.log" || fail "large prompt did not use --add-dir"
[ -s "$T/big_out.md" ]               || fail "large prompt produced no output"
pass "run_gemini large-prompt --add-dir path"

# ── 8. codex: internal transient retry (503) then content-policy still triggers the gpt-5.5 safety
#       fallback (P0-1: the transient retry must NOT starve/mask the fallback) ──
rm -f "$T/sol.count"
cat > "$BIN/codex" <<'SH'
#!/usr/bin/env bash
model=""; out=""
while [ "$#" -gt 0 ]; do case "$1" in -m) model="$2"; shift 2;; -o) out="$2"; shift 2;; *) shift;; esac; done
cat >/dev/null
if [ "$model" = "gpt-5.6-sol" ]; then
  c="$STATE/sol.count"; n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$c"
  [ "$n" -le 1 ] && { echo '503 Service Unavailable transient'; exit 1; }
  echo '{"type":"turn.failed","error":{"code":"content_policy_violation"}}'; exit 1
fi
{ printf '# GPT-5.5 fallback report\n'; for _ in $(seq 1 40); do printf 'body line here\n'; done; } > "${out:-/dev/stdout}"
exit 0
SH
chmod +x "$BIN/codex"
printf 'p\n' > "$T/cp.txt"
STATE="$T" PATH="$BIN:$PATH" FUSION_TIMEOUT=30 FUSION_TRANSIENT_BACKOFF=0 \
  bash "$SKILL/scripts/run_codex.sh" "$T/cp.txt" "$T/c_out.md" high 2> "$T/c_err.log" || fail "run_codex compose did not succeed"
grep -q 'GPT-5.5 fallback report' "$T/c_out.md" || fail "codex did not fall back to gpt-5.5"
python3 -c "import json,sys; r=json.load(open('$T/c_out.md.routing.json')); sys.exit(0 if (r['fallback_used'] and r['resolved_model']=='gpt-5.5') else 1)" \
  || fail "routing.json did not record the safety fallback"
[ "$(cat "$T/sol.count")" = "2" ] || fail "expected exactly 1 transient retry before content-policy (sol.count=$(cat "$T/sol.count"))"
grep -q 'transient failure' "$T/c_err.log" || fail "codex transient retry not logged"
pass "run_codex transient-retry + safety-fallback compose"

# ── 9. de-anon unit: blind Response labels -> model names (tables + prose + plural; stray capitals safe) ──
cat > "$T/dmap.json" <<'JSON'
{"A":{"display":"Opus 5"},"B":{"display":"GPT-5.6 Sol"},"C":{"display":"Gemini 3.5 Flash"},"D":{"display":"Grok 4.5"}}
JSON
printf '| Response A | x |\nResponse A led; Responses A and D agreed; Panelists A, B and C converged. A grade of A stands.\n' > "$T/dr.md"
python3 "$SKILL/scripts/deanonymize_report.py" "$T/dr.md" "$T/dmap.json" 2>/dev/null
grep -q 'Opus 5 and Grok 4.5 agreed' "$T/dr.md" || fail "de-anon plural list"
grep -q 'grade of A stands' "$T/dr.md"            || fail "de-anon touched a stray capital"
grep -qE 'Response [A-D]\b' "$T/dr.md"             && fail "de-anon left Response labels" || true
pass "deanonymize_report labels->model names"

# ── 10. run_judge de-anon wiring: a BLIND judge report is restored to model names in the final report ──
jrd="$T/jrun"; mkdir -p "$jrd"
cat > "$jrd/response_mapping.json" <<'JSON'
{"A":{"display":"Opus 5","model":"opus5"},"B":{"display":"Grok 4.5","model":"grok4.5"}}
JSON
printf 'Synthesize.\n' > "$jrd/judge_prompt.txt"
cat > "$BIN/claude" <<'SH'
#!/usr/bin/env bash
cat >/dev/null
printf '## Synthesis\n| Finding | Response A | Response B |\n| x | yes | no |\n\nResponse A was strongest.\n'
SH
chmod +x "$BIN/claude"
PATH="$BIN:$PATH" FUSION_JUDGE_TIMEOUT=10 \
  bash "$SKILL/scripts/run_judge.sh" "$jrd/judge_prompt.txt" "$jrd/report_fusion.md" high 2> "$T/judge.log" || fail "run_judge failed"
grep -q 'de-anonymized' "$T/judge.log"                || fail "run_judge did not de-anon"
grep -qE 'Response [A-B]\b' "$jrd/report_fusion.md"   && fail "run_judge left Response labels" || true
grep -q 'Opus 5 was strongest' "$jrd/report_fusion.md" || fail "run_judge de-anon prose failed"
pass "run_judge de-anon wiring (blind judge -> named report)"

echo "[test_hardening] passed"
