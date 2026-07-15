#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/_fusion_lib.sh"

missing=0

# Self-heal the GLOBAL Gemini MCP config: model-council-fast (fast mode) swaps
# ~/.gemini/config/mcp_config.json to {"mcpServers":{}} for a run's duration and restores it on EXIT —
# but a SIGKILLed run skips the trap, silently leaving hybrid's Gemini panelist MCP-less. Restore from
# the .fusion-golden backup whenever the file is still sitting at the empty sentinel. (Ported from
# model-council-fast/scripts/detect_panel.sh.)
repair_gemini_mcp_if_needed() {
  local cfg="${GEMINI_MCP_CONFIG:-$HOME/.gemini/config/mcp_config.json}"
  local golden="${cfg}.fusion-golden"
  local sentinel='{"mcpServers":{}}'
  [ -f "$cfg" ] || return 0
  [ -f "$golden" ] || return 0
  [ "$(cat "$cfg" 2>/dev/null || true)" = "$sentinel" ] || return 0
  # A live council Gemini panelist legitimately holds the config at the sentinel for its whole run —
  # council's run_gemini.sh keeps this same lock for its swap->run->restore window; never repair mid-run.
  exec 8>"$(dirname "$cfg")/.fusion.lock"
  if ! flock -n 8; then exec 8>&-; return 0; fi
  # Consume the golden on restore: it should only exist between a crashed run and this repair,
  # so it can never grow stale enough to clobber a config the user deliberately emptied later.
  cp -p "$golden" "$cfg" 2>/dev/null && { rm -f "$golden" 2>/dev/null; echo "[repair] restored Gemini MCP config from $golden"; }
  exec 8>&-
}

check_cmd() {
  local label="$1"
  local cmd="$2"
  if have "$cmd"; then
    printf '[ok] %s: %s\n' "$label" "$(command -v "$cmd")"
  else
    printf '[missing] %s: command not found: %s\n' "$label" "$cmd" >&2
    missing=1
  fi
}

repair_gemini_mcp_if_needed

echo "Hybrid Model Fusion CLI preflight"
check_cmd "Opus 4.8 panel/reviewer via Claude Code" "claude"
check_cmd "Grok 4.5 panel/reviewer via Grok Build CLI" "grok"
check_cmd "GPT-5.6 Sol panelist via Codex" "codex"
check_cmd "Gemini 3.5 Flash panel/reviewer via Antigravity" "agy"

if [ "$missing" -ne 0 ]; then
  echo "Hybrid mode needs all four CLIs (claude, grok, codex, agy) for the full 4-model workflow." >&2
  exit 1
fi

# Auth/reachability preflight — catch expired/blocked logins BEFORE launching the panel, so we fail
# fast with a clear message instead of 4 slow simultaneous panelist failures. Opt out with
# FUSION_AUTH_PREFLIGHT=0. Probes are the cheap per-CLI status subcommands.
if [ "${FUSION_AUTH_PREFLIGHT:-1}" = "1" ]; then
  authfail=0
  _apt="${FUSION_AUTH_PROBE_TIMEOUT:-10}"
  _fusion_auth_probe "Opus 4.8 (claude)"      "$_apt" claude auth status                              || authfail=1
  _fusion_auth_probe "Grok 4.5 (grok)"        "$_apt" "${FUSION_GROK_BIN:-$HOME/.grok/bin/grok}" models || authfail=1
  # CODEX_SKIP_SCITE_REFRESH=1: `codex` resolves to a wrapper that synchronously refreshes the Scite
  # OAuth token first (up to 3x30s HTTP on expiry) — that must never fail this 10s probe of codex itself.
  # (run_hybrid.sh's MCP warmup refreshes the Scite token separately, with its own 60s budget.)
  _fusion_auth_probe "GPT-5.6 Sol (codex)"    "$_apt" env CODEX_SKIP_SCITE_REFRESH=1 codex login status || authfail=1
  _fusion_auth_probe "Gemini 3.5 Flash (agy)" "$_apt" agy models                                     || authfail=1
  if [ "$authfail" -ne 0 ]; then
    echo "Hybrid preflight: a CLI failed auth/reachability (see [auth-fail] above). Re-authenticate (claude /login, grok login, codex login, agy) or set FUSION_AUTH_PREFLIGHT=0 to skip." >&2
    exit 1
  fi
fi

panel_models="$(python3 "$SCRIPT_DIR/panel_config.py" models 2>/dev/null | paste -sd- -)"
preset="$(python3 "$SCRIPT_DIR/panel_config.py" preset 2>/dev/null || echo default)"
echo "panel=${panel_models:-opus4.8-grok4.5-gemini3.5flash-gpt5.6sol} preset=${preset} grok_model=${FUSION_GROK_MODEL:-grok-4.5} grok_effort=high codex_model=${FUSION_CODEX_MODEL:-gpt-5.6-sol} codex_effort=max judge=${FUSION_JUDGE_MODEL:-claude-opus-4-8} judge_effort=max judge_blind=${FUSION_JUDGE_BLIND:-1}"

if [ -n "${1:-}" ]; then
  run_dir="$1"
  mkdir -p "$run_dir"
  # CODEX_SKIP_SCITE_REFRESH=1 for the same reason as the auth probe above: the codex wrapper's
  # synchronous Scite refresh must not eat the hardcoded 8s/10s subprocess timeouts below.
  CODEX_SKIP_SCITE_REFRESH=1 python3 - "$run_dir/run_env.json" <<'PY'
import json, os, pathlib, shutil, subprocess, sys, time
path = pathlib.Path(sys.argv[1])
commands = {name: shutil.which(name) for name in ["claude", "grok", "agy", "codex"]}
versions = {}
for name, cmd in commands.items():
    if not cmd:
        continue
    try:
        versions[name] = subprocess.run([cmd, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8).stdout.strip().splitlines()[:2]
    except Exception as exc:
        versions[name] = [f"version check failed: {exc}"]
def run_status(name, argv):
    try:
        out = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10).stdout.strip()
        return {"ok": True, "output": out.splitlines()[:8]}
    except Exception as exc:
        return {"ok": False, "output": [str(exc)]}
auth_checks = {}
if commands.get("claude"):
    auth_checks["claude"] = run_status("claude", ["claude", "auth", "status"])
if commands.get("grok"):
    auth_checks["grok"] = run_status("grok", ["grok", "models"])
if commands.get("codex"):
    auth_checks["codex"] = run_status("codex", ["codex", "login", "status"])
if commands.get("agy"):
    auth_checks["agy"] = run_status("agy", ["agy", "models"])
payload = {
    "time": int(time.time()),
    "commands": commands,
    "versions": versions,
    "auth_checks": auth_checks,
    "panel": os.environ.get("FUSION_PANEL_PRESET", "default"),
    "judge_model": os.environ.get("FUSION_JUDGE_MODEL", "claude-opus-4-8"),
    "judge_effort": "max",
    "judge_blind": os.environ.get("FUSION_JUDGE_BLIND", "1"),
    "grok_model": os.environ.get("FUSION_GROK_MODEL", "grok-4.5"),
    "grok_effort": os.environ.get("FUSION_GROK_EFFORT", "high"),
    "codex_model": os.environ.get("FUSION_CODEX_MODEL", "gpt-5.6-sol"),
    "codex_effort": "max",
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {path}")
PY
fi
