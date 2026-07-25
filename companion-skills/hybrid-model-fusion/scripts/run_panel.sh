#!/usr/bin/env bash
# Default PANEL launcher (Stage 1) — reliability layer.
# GUARANTEES all 3 panel reports: ALWAYS PARALLEL, per-panelist validation,
# single-pass retry on stub/empty/timeout, and a non-zero ESCALATE if any can't complete
# after retries (panel inputs are mandatory — never silently drops a panelist).
# Also sanitizes agy output and prevents orphaned processes (via _fusion_lib process-group kill).
#
# Usage: run_panel.sh RUN_DIR [normal|deep] [effort]
#   RUN_DIR must already contain prompt_{opus5,grok4.5,gemini3.5flash,gpt5.6sol}.txt
#   mode "deep"/"normal" => panelists ALWAYS run in parallel (RAM-based sequential downgrade removed 2026-06-25)
# Tunables (env): FUSION_PANEL_RETRIES FUSION_PANEL_TIMEOUT FUSION_DEEP_PARALLEL_RAM_GB FUSION_AGY_PRINT_TIMEOUT
set -uo pipefail
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SD/fusion_reliability.sh"
rd="${1:?usage: run_panel.sh RUN_DIR [normal|deep] [effort]}"
mode="${2:-normal}"
effort="${3:-max}"
mkdir -p "$rd/logs"
fusion_run_panel "$mode" "$effort" "$rd"
