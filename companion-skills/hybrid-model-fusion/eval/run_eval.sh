#!/usr/bin/env bash
# DRACO-style evaluation harness for Hybrid Model Fusion.

set -uo pipefail

SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS="$SD/tasks.jsonl"
OUT=""
DRY_RUN=0
PASSES="${FUSION_EVAL_PASSES:-3}"
ARMS=(best-solo model-fusion hybrid fable-panelist self-fusion)

usage() {
  cat >&2 <<'EOF'
usage: run_eval.sh [--dry-run] [--tasks tasks.jsonl] --out OUT_DIR

Dry-run mode writes deterministic placeholder arm outputs and grade JSON files,
then aggregates them. Live mode scaffolds the same directory structure and
prompts, but intentionally stops before expensive model calls; fill arm outputs
or wire the run_arm functions for the active environment.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --tasks) TASKS="${2:?missing --tasks value}"; shift 2 ;;
    --out) OUT="${2:?missing --out value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[ -n "$OUT" ] || { usage; exit 2; }
mkdir -p "$OUT"
cp "$TASKS" "$OUT/tasks.jsonl"
cp "$SD/rubric_template.md" "$OUT/rubric_template.md"

write_dry_grade() {
  local task_id="$1" arm="$2" pass="$3" out="$4"
  local base=28
  case "$arm" in
    best-solo) base=27 ;;
    model-fusion) base=30 ;;
    hybrid) base=31 ;;
    fable-panelist) base=30 ;;
    self-fusion) base=29 ;;
  esac
  python3 - "$task_id" "$arm" "$pass" "$base" "$out" <<'PY'
import json, sys
task_id, arm, pass_id, base, out = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
scores = {
    "accuracy": min(10, base / 4),
    "evidence": min(10, base / 4),
    "reasoning": min(10, base / 4),
    "decision_usefulness": min(10, base / 4),
}
payload = {
    "task_id": task_id,
    "arm": arm,
    "pass_id": pass_id,
    "scores": scores,
    "penalties": {"confident_wrong": 0, "verbosity": 0, "missed_task": 0, "unsupported_claims": 0},
    "total": sum(scores.values()),
    "rationale": "dry-run placeholder grade",
    "fatal_flaws": [],
}
open(out, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
}

python3 - "$TASKS" "$OUT" "$DRY_RUN" "${ARMS[@]}" <<'PY'
import json, pathlib, sys
tasks_path = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
dry = sys.argv[3] == "1"
arms = sys.argv[4:]
for line in tasks_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    task = json.loads(line)
    task_id = task["id"]
    for arm in arms:
        arm_dir = out / task_id / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        (arm_dir / "task_prompt.md").write_text(task["prompt"] + "\n", encoding="utf-8")
        if dry:
            (arm_dir / "arm_output.md").write_text(
                f"# {arm} dry-run output for {task_id}\n\nThis placeholder validates eval plumbing only.\n",
                encoding="utf-8",
            )
PY

if [ "$DRY_RUN" -eq 1 ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    task_id=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$line")
    for arm in "${ARMS[@]}"; do
      for pass in $(seq 1 "$PASSES"); do
        write_dry_grade "$task_id" "$arm" "pass_$pass" "$OUT/$task_id/$arm/grade_pass_$pass.json"
      done
    done
  done < "$TASKS"
else
  cat > "$OUT/LIVE_MODE_NEXT_STEPS.md" <<'EOF'
# Live Eval Next Steps

This harness has created task and arm directories. For a live run, produce each
`arm_output.md`, then grade it at least three times with the shared
`rubric_template.md`, saving `grade_pass_1.json`, `grade_pass_2.json`, and
`grade_pass_3.json` in each arm directory. Run `python3 eval/grade.py --out OUT`
after grading.

Keep the judge fixed across arms. Prefer a held-out non-panelist judge for
bias-sensitive comparisons.
EOF
fi

python3 "$SD/grade.py" --tasks "$TASKS" --out "$OUT"
echo "[run_eval] wrote eval scaffold/results to $OUT"
