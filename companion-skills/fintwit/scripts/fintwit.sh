#!/usr/bin/env bash
# fintwit.sh — wrapper around fintwit_engine.py for standalone and fusion (RUN_DIR) use.
#
# Usage:
#   fintwit.sh RUN_DIR TICKER   -> writes $RUN_DIR/fintwit_context.md (+ .json); RUN_DIR must exist.
#   fintwit.sh TICKER           -> writes ~/Documents/FinTwit_<TICKER>_<timestamp>/.
#   fintwit.sh "" TICKER        -> same as the standalone form (empty RUN_DIR).
#
# Skips entirely (exit 0, writes nothing) when FUSION_FAST=1 (model-fusion fast mode) or SKIP_FINTWIT=1.
set -uo pipefail

# Fast-mode / bypass guards MUST come first (before arg parsing) so no partial work happens.
if [ "${FUSION_FAST:-0}" = "1" ]; then
  echo "[fintwit.sh] FUSION_FAST=1 — skipping FinTwit/xAI step" >&2
  exit 0
fi
if [ "${SKIP_FINTWIT:-0}" = "1" ]; then
  echo "[fintwit.sh] SKIP_FINTWIT=1 — bypassing FinTwit step" >&2
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$SCRIPT_DIR/fintwit_engine.py"

if [ "$#" -ge 2 ]; then
  RUN_DIR="$1"; TICKER="$2"
elif [ "$#" -eq 1 ]; then
  RUN_DIR=""; TICKER="$1"
else
  echo "usage: fintwit.sh [RUN_DIR] TICKER" >&2; exit 2
fi

TICKER_CLEAN="${TICKER#\$}"
[ -n "$TICKER_CLEAN" ] || { echo "[fintwit.sh] empty ticker" >&2; exit 2; }

if [ -n "$RUN_DIR" ]; then
  [ -d "$RUN_DIR" ] || { echo "[fintwit.sh] RUN_DIR does not exist: $RUN_DIR" >&2; exit 1; }
  python3 "$ENGINE" --ticker "$TICKER_CLEAN" --out "$RUN_DIR" --json
else
  OUT_DIR="$HOME/Documents/FinTwit_${TICKER_CLEAN}_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$OUT_DIR"
  python3 "$ENGINE" --ticker "$TICKER_CLEAN" --out "$OUT_DIR" --json
  echo "[fintwit.sh] saved to $OUT_DIR/fintwit_context.md" >&2
fi
