#!/usr/bin/env bash
# Default REVIEW launcher (Stage 3) — reliability layer.
# Reviewer inputs are OPTIONAL: runs all 3 blind reviews but proceeds on QUORUM (default 2/3)
# plus a short grace for the laggard, then kills stragglers. A slow/flaky agy can never stall
# the run. Returns 0 if >= quorum valid reviews were produced.
#
# Usage: run_reviews.sh RUN_DIR [effort]
#   RUN_DIR must already contain review_prompt_{...}.txt (from build_review_packets.py).
# Tunables (env): FUSION_REVIEW_TIMEOUT FUSION_REVIEW_QUORUM FUSION_REVIEW_GRACE FUSION_AGY_PRINT_TIMEOUT
set -uo pipefail
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SD/fusion_reliability.sh"
rd="${1:?usage: run_reviews.sh RUN_DIR [effort]}"
effort="${2:-max}"
mkdir -p "$rd/logs"
fusion_run_reviews "$effort" "$rd"
