#!/usr/bin/env bash
# Hybrid Model Fusion — reliability layer (2026-06-23).
# Source this in the orchestration launcher. Provides:
#   - PANEL: ALWAYS parallel — all panelists concurrent in both normal & deep modes (never sequential)
#   - PANEL: guarantee every configured panelist report (validate -> single-pass retry -> escalate)
#   - REVIEWS: quorum with grace timeout; one fast-fail retry; reviewers are optional
#   - agy output sanitizer (strips leaked [COGNITIVE MONOLOGUE]/"I will..."/process trailers)
#   - orphan cleanup
# Env knobs (all overridable):
FUSION_OPUS_PANEL_EFFORT="${FUSION_OPUS_PANEL_EFFORT:-high}"
FUSION_GROK_EFFORT="${FUSION_GROK_EFFORT:-high}"
FUSION_CODEX_PANEL_EFFORT="${FUSION_CODEX_PANEL_EFFORT:-xhigh}"
FUSION_MIN_REPORT_BYTES="${FUSION_MIN_REPORT_BYTES:-2500}"
FUSION_MIN_REVIEW_BYTES="${FUSION_MIN_REVIEW_BYTES:-400}"
FUSION_PANEL_RETRIES="${FUSION_PANEL_RETRIES:-2}"
FUSION_PANEL_TIMEOUT="${FUSION_PANEL_TIMEOUT:-1800}"        # per-panelist (round 1)
FUSION_PANEL_RETRY_TIMEOUT="${FUSION_PANEL_RETRY_TIMEOUT:-1500}"
FUSION_REVIEW_TIMEOUT="${FUSION_REVIEW_TIMEOUT:-720}"       # 12 min (successful reviews ran ~4-8 min)
FUSION_REVIEW_QUORUM="${FUSION_REVIEW_QUORUM:-2}"
FUSION_REVIEW_GRACE="${FUSION_REVIEW_GRACE:-150}"           # grace for laggard after quorum
FUSION_REVIEW_RETRIES="${FUSION_REVIEW_RETRIES:-1}"
FUSION_DEEP_PARALLEL_RAM_GB="${FUSION_DEEP_PARALLEL_RAM_GB:-40}"  # need >= this avail RAM to run deep panels in parallel
FUSION_AGY_PRINT_TIMEOUT="${FUSION_AGY_PRINT_TIMEOUT:-480}" # 8 min (vs agy default 5m / old 40m override)

_FR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$_FR_DIR/_fusion_lib.sh"

fusion_ram_gb() { awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0; }

# Machine-wide cleanup is opt-in. The old default killed any agy process older than ~1h,
# which could terminate a concurrent run. Enable only for manual maintenance.
fusion_cleanup_orphans() {
  [ "${FUSION_CLEANUP_ORPHANS:-0}" = "1" ] || return 0
  local now; now=$(date +%s 2>/dev/null) || return 0
  ps -eo pid,etimes,comm 2>/dev/null | awk '$3=="agy" && $2>3600 {print $1}' | while read -r pid; do
    pkill -P "$pid" 2>/dev/null; kill -KILL "$pid" 2>/dev/null
  done
}

fusion_panel_models() {
  python3 "$_FR_DIR/panel_config.py" models 2>/dev/null || printf '%s\n' opus5 grok4.5 gemini3.6flash gpt5.6sol
}

# _fusion_kill_tree PID -> recursively TERM then KILL a process and all its descendants.
# Used for review-quorum straggler cleanup: a bare `pkill -P` + TERM only reaches direct children,
# leaving grandchildren (agy's node workers, codex/claude subprocesses) alive and burning API/RAM.
_fusion_kill_tree() {
  local pid="$1" child
  kill -0 "$pid" 2>/dev/null || return 0
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    _fusion_kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null || true
  sleep 1
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    _fusion_kill_tree "$child"
  done
  kill -KILL "$pid" 2>/dev/null || true
}

# fusion_validate_output FILE MINBYTES  -> 0 good; prints reason + returns 1 if stub/empty/error
fusion_validate_output() {
  local f="$1" min="${2:-$FUSION_MIN_REPORT_BYTES}"
  [ -s "$f" ] || { echo "empty"; return 1; }
  local sz; sz=$(wc -c < "$f")
  [ "$sz" -ge "$min" ] || { echo "too-small(${sz}<${min})"; return 1; }
  grep -qiE 'spend limit|monthly spend|you.?ve hit your' "$f" && { echo "spend-limit-error"; return 1; }
  head -c 700 "$f" | grep -qiE 'Report saved|saved to:|will be deleted|^I will (now|list|begin)|no output' && { echo "save-pointer-or-stub"; return 1; }
  return 0
}

# _fusion_agy_recover_stub FILE -> if FILE is an agy STUB (a [COGNITIVE MONOLOGUE] wrapper whose real
# report was saved to the Antigravity brain dir and only referenced by a file:// pointer), promote the
# referenced brain file over the stub. Verified real failure: a 5KB stub can pass BOTH the size and the
# head-c-700 checks in fusion_validate_output. Guarded so it never clobbers a legit report that merely
# CITES a brain file: requires the monologue marker AND <300 non-space chars AFTER the last brain pointer.
_fusion_agy_recover_stub() {
  local f="$1"; [ -s "$f" ] || return 0
  python3 - "$f" <<'PY' 2>/dev/null || true
import os, re, shutil, sys
f = sys.argv[1]
t = open(f, encoding='utf-8', errors='replace').read()
if '[COGNITIVE MONOLOGUE]' not in t:              # agy emits this on raw output; needed but NOT sufficient
    sys.exit(0)
hits = list(re.finditer(r'file://(/[^\s")\']+/antigravity-cli/brain/[^\s")\']+\.md)', t))
if not hits:
    sys.exit(0)
# A STUB is dominated by monologue + a save-pointer with essentially no report body of its own.
# Measure the SUBSTANTIVE body: drop pointer + obvious narration/monologue lines, collapse whitespace.
# A real report (even a short, header-less one) leaves a substantial body and is NEVER promoted-over;
# only a near-empty stub falls below the threshold. Biased to KEEP (never clobber a real report).
NARR = re.compile(r'^\s*(\[COGNITIVE MONOLOGUE\]|I (?:will|have|need to|am going to|\'ll|\'ve|can|now)\b|Question for you:|Summary of Completed Work|Key Decisional Angles|(?:The |Full )?[Rr]eport (?:saved|written|is saved|has been saved)|saved to:|written to:|I saved|Here is the|see the (?:full )?report)', re.I)
kept = [ln for ln in t.split('\n')
        if not ('file://' in ln and 'antigravity-cli/brain/' in ln) and not NARR.match(ln)]
if len(re.sub(r'\s+', '', '\n'.join(kept))) >= int(os.environ.get('FUSION_AGY_STUB_MAX_BODY', '400')):
    sys.exit(0)                                   # has a real report body -> keep, do NOT promote
try:
    brain = os.path.realpath(hits[-1].group(1))
except OSError:
    sys.exit(0)
home = os.path.realpath(os.path.expanduser('~/.gemini/antigravity-cli/brain'))
if not brain.startswith(home + os.sep) or not os.path.isfile(brain):
    sys.exit(0)
body = open(brain, encoding='utf-8', errors='replace').read()
if len(body) <= os.path.getsize(f):               # brain file no bigger -> nothing gained, keep stub
    sys.exit(0)
shutil.copyfile(f, f + '.stub_backup')
open(f, 'w', encoding='utf-8').write(body)
sys.stderr.write('[recover_agy] promoted brain report %s -> %s\n' % (brain, f))
PY
}

# fusion_sanitize_agy FILE  -> strip leaked narration/monologue/process trailers (agy panel/review output)
fusion_sanitize_agy() {
  local f="$1"; [ -s "$f" ] || return 0
  python3 - "$f" <<'PY' 2>/dev/null || true
import sys, re
p = sys.argv[1]
t = open(p, encoding='utf-8', errors='replace').read()
if not re.search(r'\[COGNITIVE MONOLOGUE\]|^I will \w|Summary of Completed Work|Question for you:|^I (have|need to|will begin)\b', t, re.M):
    sys.exit(0)                       # no agy artifacts -> leave untouched
lines = t.split('\n'); n = len(lines)
def is_hdr(l): return bool(re.match(r'^#{1,2}\s+\S', l)) and 'COGNITIVE MONOLOGUE' not in l
mono = next((i for i,l in enumerate(lines) if 'COGNITIVE MONOLOGUE' in l), -1)
if mono >= 0:
    start = next((i for i in range(mono+1, n) if is_hdr(lines[i])), 0)
else:
    start = next((i for i in range(n) if is_hdr(lines[i])), 0)
body = '\n'.join(lines[start:])
body = re.split(r'\n#{1,4}\s*(Summary of Completed Work|Key Decisional Angles)', body)[0]
body = '\n'.join(l for l in body.split('\n')
                 if not re.match(r'^\s*(I will (now|list|view|check|run|read|write|perform|search|begin|verify|call|terminate|analyze|formulate|provide|format)\b|Question for you:)\s', l))
body = body.strip() + '\n'
if len(body) > 200 and body != t:
    raw = p + '.raw'
    try:
        open(raw, 'x', encoding='utf-8').write(t)
    except FileExistsError:
        pass
    open(p, 'w', encoding='utf-8').write(body)
    sys.stderr.write("[sanitize_agy] cleaned %s\n" % p)
PY
}

# _fusion_role_effort MODEL REQUESTED_EFFORT -> pinned full-Hybrid panel/reviewer effort.
# The shared requested effort is retained only for non-default experimental seats such as Fable.
_fusion_role_effort() {
  local model="$1" requested="${2:-xhigh}"
  case "$model" in
    opus5)        printf '%s\n' "$FUSION_OPUS_PANEL_EFFORT" ;;
    grok4.5)        printf '%s\n' "$FUSION_GROK_EFFORT" ;;
    gemini3.6flash) printf '%s\n' "high" ;;
    gpt5.6sol)      printf '%s\n' "$FUSION_CODEX_PANEL_EFFORT" ;;
    *)              printf '%s\n' "$requested" ;;
  esac
}

# _fusion_run_one MODEL PROMPT OUT REQUESTED_EFFORT [singlepass] [stage]
# MODEL in {opus5,grok4.5,gemini3.6flash,gpt5.6sol}; singlepass=1 prepends a no-subagent directive (claude/grok/codex).
_fusion_run_one() {
  local model="$1" prompt="$2" out="$3" requested_effort="${4:-xhigh}" sp="${5:-0}" stage="${6:-panel}"
  local effort
  effort="$(_fusion_role_effort "$model" "$requested_effort")"
  local runner p="$prompt" tmp_prompt="" codex_prompt_sha256=""
  case "$model" in
	    opus5)        runner="$_FR_DIR/run_claude.sh" ;;                              # Opus 5: high
	    fable5)         runner="$_FR_DIR/run_claude.sh" ;;                              # claude: FUSION_CLAUDE_MODEL overridden below
	    grok4.5)        runner="$_FR_DIR/run_grok.sh" ;;                                # Grok 4.5 panelist via Grok Build CLI (high)
    gpt5.6sol)      runner="$_FR_DIR/run_codex.sh" ;;                               # GPT-5.6 Sol panelist via Codex (xhigh)
    gemini3.6flash) runner="$_FR_DIR/run_gemini.sh" ;;                             # agy: effort ignored (model label = High)
    *) echo "[fusion] unknown model $model" >&2; return 2 ;;
  esac
  if [ "$model" = "gpt5.6sol" ]; then
    codex_prompt_sha256="$(sha256sum "$prompt" | awk '{print $1}')"
  fi
  if [ "$sp" = "1" ] && [ "$model" != "gemini3.6flash" ]; then
    p="$(mktemp)"; tmp_prompt="$p"; { printf 'OPERATIONAL: do a thorough SINGLE-PASS run; do NOT spawn parallel research subagents (resource safety). Emit the COMPLETE final report inline to stdout.\n\n'; cat "$prompt"; } > "$p"
  fi
  if [ "$model" = "fable5" ]; then
    FUSION_CLAUDE_MODEL="${FUSION_FABLE_MODEL:-claude-fable-5}" FUSION_RUN_STAGE="$stage" bash "$runner" "$p" "$out" "$effort"
  elif [ "$model" = "gemini3.6flash" ]; then
    FUSION_RUN_STAGE="$stage" AGY_PRINT_TIMEOUT="${FUSION_AGY_PRINT_TIMEOUT}s" bash "$runner" "$p" "$out" "$effort"
  elif [ "$model" = "gpt5.6sol" ]; then
    FUSION_RUN_STAGE="$stage" FUSION_CODEX_PROMPT_SHA256="$codex_prompt_sha256" \
      FUSION_CODEX_OUTER_RETRY="$sp" bash "$runner" "$p" "$out" "$effort"
  else
    FUSION_RUN_STAGE="$stage" bash "$runner" "$p" "$out" "$effort"
  fi
  local rc=$?
  [ -n "$tmp_prompt" ] && rm -f "$tmp_prompt"
  if [ "$model" = "gemini3.6flash" ]; then
    _fusion_agy_recover_stub "$out"   # promote a brain-dir report BEFORE sanitize strips the monologue marker
    fusion_sanitize_agy "$out"
  fi
  return $rc
}

# fusion_run_panel MODE EFFORT RUN_DIR   (MODE: normal|deep) -> 0 if every configured report is valid
# Expects $RUN_DIR/prompt_<model>.txt to exist; writes report_<model>.md.
fusion_run_panel() {
  local mode="$1" effort="${2:-xhigh}" rd="$3"
  local models=()
  mapfile -t models < <(fusion_panel_models)
  fusion_cleanup_orphans
  # ALWAYS PARALLEL — every panelist is launched concurrently in BOTH normal and deep modes,
  # regardless of available RAM or whether panelists use deep research. The RAM-based sequential
  # downgrade was removed by user request (2026-06-25). $mode is kept only for backward-compat.
  local ram; ram=$(fusion_ram_gb)
  echo "[panel] mode=${mode}: launching all ${#models[@]} panelists in PARALLEL (${ram}GB avail); single-pass retry fallback on failure" >&2
  export FUSION_TIMEOUT="$FUSION_PANEL_TIMEOUT"
  local m
  local pids=()
  for m in "${models[@]}"; do _fusion_run_one "$m" "$rd/prompt_${m}.txt" "$rd/report_${m}.md" "$effort" 0 panel >"$rd/logs/panel_${m}.log" 2>&1 & pids+=("$!"); echo "$!" > "$rd/logs/panel_${m}.pid"; done
  for p in "${pids[@]}"; do wait "$p"; done
  # validate + retry (PARALLEL, single-pass) — panel is MANDATORY, retry until all configured reports exist or escalate
  local attempt=0 failed
  while :; do
    failed=()
    for m in "${models[@]}"; do
      local reason; reason=$(fusion_validate_output "$rd/report_${m}.md") || failed+=("$m:$reason")
    done
    [ ${#failed[@]} -eq 0 ] && { echo "[panel] all ${#models[@]} reports valid"; return 0; }
    attempt=$((attempt+1))
    if [ "$attempt" -gt "$FUSION_PANEL_RETRIES" ]; then
      echo "[panel] ESCALATE: still failing after ${FUSION_PANEL_RETRIES} retries: ${failed[*]}" >&2
      return 1
    fi
    echo "[panel] retry $attempt (single-pass, PARALLEL) for: ${failed[*]}" >&2
    export FUSION_TIMEOUT="$FUSION_PANEL_RETRY_TIMEOUT"
    local fm; local rpids=()
    for fm in "${failed[@]}"; do m="${fm%%:*}"; _fusion_run_one "$m" "$rd/prompt_${m}.txt" "$rd/report_${m}.md" "$effort" 1 panel >"$rd/logs/panel_${m}_retry${attempt}.log" 2>&1 & rpids+=("$!"); echo "$!" > "$rd/logs/panel_${m}_retry${attempt}.pid"; done
    for p in "${rpids[@]}"; do wait "$p"; done
  done
}

fusion_validate_review() {
  local rd="$1" model="$2"
  local f="$rd/review_${model}.md"
  fusion_validate_output "$f" "$FUSION_MIN_REVIEW_BYTES" >/dev/null 2>&1 || return 1
  python3 "$_FR_DIR/validate_review_json.py" "$rd" "$model" "$f" >/dev/null 2>&1
}

fusion_count_valid_reviews() {
  local rd="$1"; shift
  local valid=0 m
  for m in "$@"; do fusion_validate_review "$rd" "$m" && valid=$((valid+1)); done
  echo "$valid"
}

fusion_retry_invalid_reviews() {
  local rd="$1" effort="$2"; shift 2
  local rpids=() m
  for m in "$@"; do
    if ! fusion_validate_review "$rd" "$m"; then
      echo "[reviews] retrying invalid/missing review for $m" >&2
      _fusion_run_one "$m" "$rd/review_prompt_${m}.txt" "$rd/review_${m}.md" "$effort" 1 review >"$rd/logs/review_${m}_retry1.log" 2>&1 &
      rpids+=("$!"); echo "$!" > "$rd/logs/review_${m}_retry1.pid"
    fi
  done
  for p in "${rpids[@]}"; do wait "$p"; done
}

# fusion_run_reviews EFFORT RUN_DIR -> 0 if >= quorum valid reviews (proceed); reviewers are optional
# Expects $RUN_DIR/review_prompt_<model>.txt; writes review_<model>.md. Proceeds on quorum + grace.
fusion_run_reviews() {
  local effort="${1:-xhigh}" rd="$2"
  local models=()
  mapfile -t models < <(fusion_panel_models)
  fusion_cleanup_orphans
  export FUSION_TIMEOUT="$FUSION_REVIEW_TIMEOUT"
  local pids=() m
  for m in "${models[@]}"; do
    _fusion_run_one "$m" "$rd/review_prompt_${m}.txt" "$rd/review_${m}.md" "$effort" 0 review >"$rd/logs/review_${m}.log" 2>&1 &
    pids+=("$!")
    echo "$!" > "$rd/logs/review_${m}.pid"
  done
  local t0 tq=0 retried=0
  t0=$(date +%s)
  while :; do
    local valid=0
    valid=$(fusion_count_valid_reviews "$rd" "${models[@]}")
    # all processes done?
    local alive=0; for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive+1)); done
    if [ "$valid" -ge "$FUSION_REVIEW_QUORUM" ]; then
      [ "$tq" -eq 0 ] && tq=$(date +%s)
      local since=$(( $(date +%s) - tq ))
      if [ "$alive" -eq 0 ] || [ "$since" -ge "$FUSION_REVIEW_GRACE" ]; then
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && _fusion_kill_tree "$p"; done
        echo "[reviews] proceeding with ${valid}/3 (quorum ${FUSION_REVIEW_QUORUM}, grace ${since}s)";
        for m in "${models[@]}"; do fusion_validate_review "$rd" "$m" || { [ -f "$rd/review_${m}.md" ] && mv "$rd/review_${m}.md" "$rd/review_${m}.md.empty" 2>/dev/null; }; done
        return 0
      fi
    fi
    [ "$alive" -eq 0 ] && {
      [ "$valid" -ge "$FUSION_REVIEW_QUORUM" ] && return 0
      if [ "$retried" -lt "$FUSION_REVIEW_RETRIES" ]; then
        retried=$((retried+1))
        fusion_retry_invalid_reviews "$rd" "$effort" "${models[@]}"
        valid=$(fusion_count_valid_reviews "$rd" "${models[@]}")
        [ "$valid" -ge "$FUSION_REVIEW_QUORUM" ] && return 0
      fi
      echo "[reviews] WARNING: only ${valid}/3 reviews and all processes ended (< quorum ${FUSION_REVIEW_QUORUM})" >&2; return 1; }
    sleep 5
  done
}
