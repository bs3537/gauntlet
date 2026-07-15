#!/usr/bin/env bash
# Run every self-test in the valuation skill. Exit non-zero if any fails.
set -u
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$SD/scripts"
fail=0
run() {
  echo "==================== $1 ===================="
  if python3 "$S/$1" selftest; then echo "[$1] OK"; else echo "[$1] FAILED"; fail=1; fi
  echo
}
run cost_of_capital.py
run dcf.py
run drivers.py
run rnpv.py
run relative_val.py
run excel_builder.py
run validate_valuation.py
run memo_builder.py
run valuation_engine.py
echo "============================================="
if [ "$fail" -eq 0 ]; then echo "ALL SELFTESTS PASSED"; else echo "SOME SELFTESTS FAILED"; fi
exit $fail
