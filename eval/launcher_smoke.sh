#!/usr/bin/env bash
# launcher_smoke.sh — deterministic launcher-equivalence + contract test for Stage 2.
#
# Stage 2 depends on a launcher owned by ANOTHER skill (hybrid-model-fusion's run_codex.sh)
# through a private env contract, with a Gauntlet-owned raw-codex path behind it. Two ways
# that bites: the upstream launcher drifts and Gauntlet degrades silently, or the fallback
# fires and produces DIFFERENT artifacts than the primary path, so downstream stages quietly
# lose the routing json / stream log they were told to check.
#
# This test pins both. No LLM, no network, no real codex: a stub `codex` on PATH returns a
# canned QC-passing review, and each launcher path is run against it.
#   1. external launcher path  == gauntlet raw-codex path, by run-dir FILE SET
#   2. both paths emit <capture>.routing.json with the same routing key/values
#   3. --contract-check passes on a conforming launcher and FAILS on a drifted one
#   4. a drifted launcher does not silently degrade the run (fallback engages; strict aborts)
# PASS -> exit 0.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER="$ROOT/scripts/run_review.sh"
EXTERNAL="$ROOT/companion-skills/hybrid-model-fusion/scripts/run_codex.sh"
[ -f "$RUNNER" ] || { echo "FAILED: runner missing: $RUNNER"; exit 1; }
[ -f "$EXTERNAL" ] || { echo "SKIP: bundled hybrid-model-fusion launcher not in this tree"; exit 0; }
command -v perl >/dev/null 2>&1 || { echo "SKIP: perl missing (the external launcher needs it)"; exit 0; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/gauntlet-launcher.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

fails=0
ok()   { printf 'PASS  %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; fails=$((fails+1)); }

# ── stub codex ────────────────────────────────────────────────────────────────
# Honors the two invocations Gauntlet makes: the preflight ping and the review launch.
# Writes its output to the file named by -o, exactly like the real CLI.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/codex" <<'STUB'
#!/usr/bin/env bash
out=""; prev=""
for a in "$@"; do
  [ "$prev" = "-o" ] && out="$a"
  prev="$a"
done
prompt="$(cat)"
[ -n "$out" ] || exit 2
if printf '%s' "$prompt" | grep -q 'Reply with exactly: OK'; then
  printf 'OK\n' > "$out"; exit 0
fi
{
  echo 'ADVERSARIAL REVIEW — Exemplar Grid Industries (XGRD)'
  echo 'VERDICT: the thesis survives with material caveats. Overall 81/100, band B.'
  echo '## CLAIM VERIFICATION'
  echo '| # | Claim | Verdict | Evidence |'
  echo '|---|-------|---------|----------|'
  echo '| 1 | XGRD FY25 revenue $1,790M | Confirmed | FY25 10-K p.61 |'
  echo '| 2 | XGRD net debt $410M | Confirmed | FY25 10-K p.88 |'
  echo '| 3 | XGRD EV/EBITDA 8.9x | Refuted | recomputed 6.2x |'
  echo 'COMPLIANCE: anti-gaming and anti-hallucination rules met.'
  yes 'padding: independent verification of the claim against its primary-source locator.' | head -n 600
} > "$out"
exit 0
STUB
chmod +x "$TMP/bin/codex"
export PATH="$TMP/bin:$PATH"

mkrun() {  # mkrun <dir> — a minimal run dir with the round-1 reviewer prompt
  mkdir -p "$1"
  printf 'REVIEW PROMPT for XGRD (stub).\n' > "$1/09_reviewer_prompt.txt"
}

fileset() { (cd "$1" && find . -type f | LC_ALL=C sort); }

routing_keys() {  # the routing fields downstream stages actually read
  python3 - "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:            # noqa: BLE001 — surfaced as a test failure
    print(f"UNREADABLE:{exc}"); raise SystemExit(0)
keys = ("stage", "fast", "primary_model", "primary_effort",
        "resolved_model", "resolved_effort", "fallback_used")
print(" ".join(f"{k}={d.get(k)}" for k in keys))
PY
}

# ── 1. external launcher path ─────────────────────────────────────────────────
ext="$TMP/run_external"; mkrun "$ext"
env PREFLIGHT=0 QC_EXPECT_TICKER=XGRD GAUNTLET_CODEX_RUNNER="$EXTERNAL" \
  bash "$RUNNER" "$ext" 1 > "$TMP/external.out" 2>&1
ext_rc=$?
[ "$ext_rc" -eq 0 ] && ok "external launcher path completes and passes QC (rc=0)" \
                    || bad "external launcher path rc=$ext_rc (see $TMP/external.out)"
# Prove this path really went through the external launcher — otherwise the equivalence
# assertion below would pass vacuously with both runs on the fallback.
grep -q 'launcher=external' "$TMP/external.out" && grep -q 'run_codex.sh' "$ext/10_review_capture_r1.stream.log" \
  && ok "external path demonstrably ran the external launcher" \
  || bad "external path did not actually use the external launcher (equivalence would be vacuous)"

# ── 2. gauntlet raw-codex fallback path ───────────────────────────────────────
raw="$TMP/run_raw"; mkrun "$raw"
env PREFLIGHT=0 QC_EXPECT_TICKER=XGRD GAUNTLET_CODEX_RUNNER="$TMP/nonexistent_run_codex.sh" \
  bash "$RUNNER" "$raw" 1 > "$TMP/raw.out" 2>&1
raw_rc=$?
[ "$raw_rc" -eq 0 ] && ok "gauntlet raw-codex path completes and passes QC (rc=0)" \
                    || bad "gauntlet raw-codex path rc=$raw_rc (see $TMP/raw.out)"
grep -q 'launcher contract not satisfied' "$TMP/raw.out" && grep -q 'launcher=gauntlet-raw' "$TMP/raw.out" \
  && ok "missing launcher is reported, not silently swallowed" \
  || bad "missing launcher produced no contract warning"

# ── 3. artifact equivalence ───────────────────────────────────────────────────
if diff <(fileset "$ext") <(fileset "$raw") > "$TMP/fileset.diff" 2>&1; then
  ok "both launcher paths produce an identical run-dir file set"
else
  bad "run-dir file sets differ between launcher paths:"; sed 's/^/      /' "$TMP/fileset.diff"
fi

ext_route="$(routing_keys "$ext/10_review_capture_r1.md.routing.json")"
raw_route="$(routing_keys "$raw/10_review_capture_r1.md.routing.json")"
if [ "$ext_route" = "$raw_route" ] && [ -n "$ext_route" ]; then
  ok "routing json is equivalent on both paths ($ext_route)"
else
  bad "routing json differs: external[$ext_route] vs raw[$raw_route]"
fi

# ── 4. contract check: conforming vs drifted launcher ─────────────────────────
env GAUNTLET_CODEX_RUNNER="$EXTERNAL" bash "$RUNNER" --contract-check >/dev/null 2>&1 \
  && ok "--contract-check passes on the bundled conforming launcher" \
  || bad "--contract-check rejected the bundled launcher (contract or launcher drifted)"

drifted="$TMP/drifted_run_codex.sh"
sed 's/FUSION_RUN_STAGE/FUSION_STAGE_RENAMED/g; s/FUSION_CODEX_SAFETY_FALLBACK/FUSION_SAFETY_RENAMED/g' \
  "$EXTERNAL" > "$drifted"
env GAUNTLET_CODEX_RUNNER="$drifted" bash "$RUNNER" --contract-check >/dev/null 2>&1 \
  && bad "--contract-check accepted a launcher that dropped FUSION_RUN_STAGE" \
  || ok "--contract-check rejects a drifted launcher"

drift_run="$TMP/run_drift"; mkrun "$drift_run"
env PREFLIGHT=0 QC_EXPECT_TICKER=XGRD GAUNTLET_CODEX_RUNNER="$drifted" \
  bash "$RUNNER" "$drift_run" 1 > "$TMP/drift.out" 2>&1
drift_rc=$?
if [ "$drift_rc" -eq 0 ] && grep -q 'launcher contract not satisfied' "$TMP/drift.out"; then
  ok "drifted launcher is refused and the run completes on the gauntlet path"
else
  bad "drifted launcher handling wrong (rc=$drift_rc; see $TMP/drift.out)"
fi

strict_run="$TMP/run_strict"; mkrun "$strict_run"
env PREFLIGHT=0 GAUNTLET_STRICT_CONTRACT=1 GAUNTLET_CODEX_RUNNER="$drifted" \
  bash "$RUNNER" "$strict_run" 1 > "$TMP/strict.out" 2>&1
strict_rc=$?
[ "$strict_rc" -eq 1 ] && ok "GAUNTLET_STRICT_CONTRACT=1 aborts on a drifted launcher (rc=1)" \
                       || bad "strict mode rc=$strict_rc, wanted 1 (see $TMP/strict.out)"

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: launcher contract + artifact-equivalence smoke test."; exit 0
else
  echo "FAILED: $fails assertion(s)."; exit 1
fi
