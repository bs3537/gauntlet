#!/usr/bin/env bash
# Shared helpers for Hybrid Model Fusion runner scripts.

FUSION_TIMEOUT="${FUSION_TIMEOUT:-1800}"

have() { command -v "$1" >/dev/null 2>&1; }

# _run_with_timeout SECONDS cmd [args...]
# Exit status is the command's own status, or 124 if killed for exceeding SECONDS.
_run_with_timeout() {
  local secs="$1"; shift
  # The child becomes a process-group leader (setpgrp) and, on timeout, we signal the
  # WHOLE GROUP (kill -PID) so descendants (e.g. agy's node children, codex/claude subagents)
  # are killed too -- prevents orphaned processes piling up and leaking RAM. (fix 2026-06-23)
  # $timed_out distinguishes "our alarm fired" from "child died to an external signal" (OOM kill,
  # manual kill): only the former is exit 124. Matches model-council-fast's _fusion_lib.sh — keeps
  # the retry logic from misreading an external kill as a timeout (124 is never retried).
  perl -e '
    my $secs = shift @ARGV;
    my $pid = fork();
    exit 127 unless defined $pid;
    if ($pid == 0) { setpgrp(0,0); exec @ARGV or exit 127; }
    my $timed_out = 0;
    local $SIG{ALRM} = sub { $timed_out = 1; kill "TERM", -$pid; sleep 2; kill "KILL", -$pid; };
    alarm $secs;
    waitpid($pid, 0);
    my $rc = $?;
    alarm 0;
    if ($rc & 127) {
      my $sig = $rc & 127;
      exit 124 if $timed_out;
      exit(128 + $sig);
    }
    exit($rc >> 8);
  ' "$secs" "$@"
}

# ── First-attempt-failure hardening (2026-07-14) ──────────────────────────────
# _fusion_is_transient LOGFILE -> 0 if the captured log looks like a TRANSIENT infra
# error (rate limit / 5xx / connection reset / provider overload) that a short in-runner
# retry can clear. Deliberately NARROW so it never masks auth, content-policy, quota, or
# validation failures — those keep their own code paths. Case-insensitive.
_fusion_is_transient() {
  local log="$1"
  [ -s "$log" ] || return 1
  grep -qiE 'rate[ _-]?limit|too many requests|overloaded|service unavailable|temporarily unavailable|bad gateway|gateway timeout|econnreset|econnrefused|etimedout|socket hang up|connection reset|connection refused|resource[ _-]?exhausted|(^|[^0-9])(429|500|502|503|504)([^0-9]|$)' "$log"
}

# _fusion_should_retry STATUS LOGFILE OUTFILE -> 0 if a bounded transient retry is warranted:
# NOT a timeout(124) or not-installed(127), the output file is empty (no partial answer to keep),
# and the log matches the narrow transient allowlist above.
_fusion_should_retry() {
  local status="$1" log="$2" out="$3"
  [ "$status" -ne 124 ] && [ "$status" -ne 127 ] || return 1
  [ -s "$out" ] && return 1
  _fusion_is_transient "$log"
}

# _fusion_auth_probe LABEL TIMEOUT CMD... -> 0 if the CLI's cheap auth/reachability probe
# succeeds within TIMEOUT seconds; else 1 (prints a labeled diagnostic to stderr). Used by
# detect_panel.sh to fail fast on expired/missing credentials BEFORE launching the panel.
_fusion_auth_probe() {
  local label="$1" timeout="$2"; shift 2
  local rc
  _run_with_timeout "$timeout" "$@" >/dev/null 2>&1 </dev/null
  rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '[auth-fail] %s: `%s` exited %s (expired/blocked login or unreachable API?)\n' "$label" "$*" "$rc" >&2
    return 1
  fi
  return 0
}

# Print an allowlisted structured Codex safety error code from a --json event log.
# Model-authored prose and message-only diagnostics are deliberately ignored.
_fusion_codex_safety_code() {
  local events_file="$1"
  [ -s "$events_file" ] || return 1
  python3 - "$events_file" "${FUSION_CODEX_SAFETY_CODES:-content_policy_violation,safety_check_failed,safety_identifier_blocked,safety_rejected,safety_violation}" <<'PY'
import json, sys

path, configured = sys.argv[1:3]
allowed = {item.strip() for item in configured.split(",") if item.strip()}

def structured_code(payload, depth=0):
    if depth > 3 or not isinstance(payload, dict):
        return None
    error = payload.get("error")
    nested_error = error.get("error") if isinstance(error, dict) else None
    candidates = [value for value in (error, nested_error, payload) if isinstance(value, dict)]
    for candidate in candidates:
        code = candidate.get("code")
        if isinstance(code, str) and code:
            return code
    for candidate in candidates:
        kind = candidate.get("type")
        if isinstance(kind, str) and kind not in {"error", "turn.failed", "item.completed"}:
            return kind
    for candidate in candidates:
        message = candidate.get("message")
        if isinstance(message, str) and message.lstrip().startswith("{"):
            try:
                decoded = json.loads(message)
            except json.JSONDecodeError:
                continue
            code = structured_code(decoded, depth + 1)
            if code:
                return code
    return None

with open(path, encoding="utf-8", errors="replace") as handle:
    for raw in handle:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        payload = None
        if isinstance(event, dict) and event.get("type") in {"error", "turn.failed"}:
            payload = event
        elif isinstance(event, dict) and event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "error":
                payload = item
        if payload is None:
            continue
        code = structured_code(payload)
        if code in allowed:
            print(code)
            raise SystemExit(0)
raise SystemExit(1)
PY
}

_fusion_write_codex_routing() {
  local path="$1" primary_model="$2" primary_effort="$3" resolved_model="$4" resolved_effort="$5"
  local fallback_used="$6" reason="$7" primary_rc="$8" resolved_rc="$9" stage="${10:-panel}" prompt_sha256="${11:-}"
  python3 - "$path" "$primary_model" "$primary_effort" "$resolved_model" "$resolved_effort" \
    "$fallback_used" "$reason" "$primary_rc" "$resolved_rc" "$stage" "$prompt_sha256" <<'PY'
import json, os, pathlib, sys

path = pathlib.Path(sys.argv[1])
primary_model, primary_effort, resolved_model, resolved_effort = sys.argv[2:6]
fallback_used, reason, primary_rc, resolved_rc, stage, prompt_sha256 = sys.argv[6:12]

def rc(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

payload = {
    "stage": stage,
    "fast": os.environ.get("FUSION_FAST") == "1",
    "primary_model": primary_model,
    "primary_effort": primary_effort,
    "primary_returncode": rc(primary_rc),
    "fallback_used": fallback_used == "1",
    "fallback_reason": reason,
    "resolved_model": resolved_model,
    "resolved_effort": resolved_effort,
    "resolved_returncode": rc(resolved_rc),
    "prompt_sha256": prompt_sha256,
}
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}
