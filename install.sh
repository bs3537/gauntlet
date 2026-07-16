#!/usr/bin/env bash
#
# Gauntlet one-shot installer.
#
# Installs the gauntlet skill AND every bundled companion skill
# (deep-research, search-as-code, valuation, hybrid-model-fusion, fintwit) into your
# Claude Code skills tree in a single step — no separate downloads.
#
# It also mirrors the valuation engine (and a gauntlet parity copy) into the
# codex skills tree, which the Stage-2 GPT-5.6 Sol reviewer needs to
# independently rerun the rNPV/DCF model.
#
# Usage:
#   ./install.sh
#
# Overridable targets (env vars):
#   CLAUDE_SKILLS_DIR   default: ~/.claude/skills
#   CODEX_SKILLS_DIR    default: ~/.codex/skills
#   FORCE_CODEX_MIRROR  set to 1 to mirror to the codex tree even if ~/.codex
#                       does not exist
#
# This installer only copies SKILL FILES. It does NOT install API keys, MCP
# servers, or the codex CLI — see the "External data sources & tools" section
# of README.md for what you must provide yourself.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SKILLS="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
CODEX_SKILLS="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"

COMPANIONS=(deep-research search-as-code valuation hybrid-model-fusion fintwit)

# Copy the CONTENTS of $1 into $2 (portable; GNU + BSD cp). Overlay, never delete.
install_dir() {
  mkdir -p "$2"
  cp -R "$1/." "$2/"
}

# Install the gauntlet skill itself from the repo root (skill files only —
# never the bundle, installer, docs-plan, or repo metadata).
install_gauntlet() {
  local dst="$1"
  mkdir -p "$dst"
  cp -R "$REPO_DIR/SKILL.md" "$REPO_DIR/README.md" \
        "$REPO_DIR/scripts" "$REPO_DIR/references" "$dst/"
  [ -d "$REPO_DIR/docs" ] && cp -R "$REPO_DIR/docs" "$dst/"
}

echo "Gauntlet installer"
echo "  repo:           $REPO_DIR"
echo "  claude skills:  $CLAUDE_SKILLS"
echo "  codex skills:   $CODEX_SKILLS"
echo

# 1. Claude tree — gauntlet + all companion skills.
echo "==> Installing into Claude skills tree: $CLAUDE_SKILLS"
echo "    - gauntlet"
install_gauntlet "$CLAUDE_SKILLS/gauntlet"
for s in "${COMPANIONS[@]}"; do
  echo "    - $s"
  install_dir "$REPO_DIR/companion-skills/$s" "$CLAUDE_SKILLS/$s"
done

# 2. Codex tree — reviewer needs valuation to rerun the engine; gauntlet parity copy.
if [ -d "$HOME/.codex" ] || [ -n "${FORCE_CODEX_MIRROR:-}" ]; then
  echo "==> Mirroring reviewer-side skills into codex tree: $CODEX_SKILLS"
  echo "    - valuation (so the GPT-5.6 Sol reviewer can rerun the rNPV engine)"
  install_dir "$REPO_DIR/companion-skills/valuation" "$CODEX_SKILLS/valuation"
  echo "    - gauntlet (parity/reference copy — do not invoke from codex)"
  install_gauntlet "$CODEX_SKILLS/gauntlet"
else
  echo "==> ~/.codex not found — skipping codex-tree mirror."
  echo "    (Install codex, then re-run with FORCE_CODEX_MIRROR=1, or copy"
  echo "     companion-skills/valuation into your codex skills tree by hand.)"
fi

echo
echo "Done. Installed skills: gauntlet ${COMPANIONS[*]}"
echo
echo "NOTE — fintwit (default-on Tier-4 X/sentiment step) needs an xAI API key:"
echo "  create one at https://console.x.ai , then:"
echo "    save your xAI API key into ~/.claude/secrets/xai.env (chmod 600); the variable name is XAI_API_KEY"
echo "  Without it, a gauntlet run simply SKIPS FinTwit and notes it in the report (nothing else breaks)."
echo
echo "NEXT — provide the external data sources & tools Gauntlet relies on"
echo "(none are bundled; see README.md 'External data sources & tools'):"
echo "  * Financial data : FMP API key (~/.fmp_api_key) or an alternative provider"
echo "  * Literature     : BioMCP (biomedical) and/or Scite / Semantic Scholar (tech/general)"
echo "  * Web search     : the model's native web search, or a Perplexity/Brave/Exa API key"
echo "  * Reviewer       : the 'codex' CLI on PATH, authenticated for gpt-5.6-sol"
