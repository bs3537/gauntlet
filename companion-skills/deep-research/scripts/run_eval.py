#!/usr/bin/env python3
"""Internal self-evaluation harness for deep-research runs.

This is not an external benchmark implementation. It scores completed local run
folders against internal gold-task prompts using pinned judge metadata and local
artifacts. Tests use fixture judge output and do not require network or LLMs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_EVAL_DIR = SKILL_DIR / 'evals'
RACE_DIMENSIONS = (
    'instruction_following',
    'comprehensiveness',
    'insight',
    'writing_objectivity',
)
FACT_VERDICTS = ('entailed', 'contradicted', 'insufficient')
CSV_COLUMNS = [
    'eval_run_id', 'status', 'task_id', 'category', 'mode', 'run_dir',
    'report_path', 'evaluated_at', 'judge_provider', 'judge_model',
    'judge_version', 'judge_prompt_hash', 'rubric_version',
    'instruction_following', 'comprehensiveness', 'insight',
    'writing_objectivity', 'race_overall', 'fact_sample_size',
    'fact_entailed', 'fact_contradicted', 'fact_insufficient',
    'fact_accuracy', 'delivery_gate_status', 'audit_manifest_status',
    'network_mode', 'llm_used', 'elapsed_seconds', 'result_path',
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path: Path) -> Any:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_tasks(task_path: Path) -> list[dict]:
    payload = read_json(task_path)
    if isinstance(payload, list):
        tasks = payload
    elif isinstance(payload, dict) and isinstance(payload.get('tasks'), list):
        tasks = payload['tasks']
    elif isinstance(payload, dict):
        tasks = [payload]
    else:
        raise ValueError('task file must be a task object, task list, or {"tasks": [...]}')
    return [task for task in tasks if isinstance(task, dict)]


def select_task(task_path: Path, task_id: str | None) -> dict:
    tasks = load_tasks(task_path)
    if task_id:
        for task in tasks:
            if task.get('task_id') == task_id:
                return task
        raise ValueError(f'task_id not found in {task_path}: {task_id}')
    if len(tasks) != 1:
        raise ValueError('task file contains multiple tasks; pass --task-id')
    return tasks[0]


def run_manifest_path(run_dir: Path) -> Path:
    return run_dir / 'run_manifest.json'


def artifact_path(run_dir: Path, manifest: dict, key: str, fallback: str) -> Path:
    rel = (manifest.get('artifact_paths') or {}).get(key, fallback)
    path = Path(rel)
    return path if path.is_absolute() else run_dir / path


def resolve_report_path(run_dir: Path, manifest: dict, explicit_report: str | None) -> Path:
    if explicit_report:
        return Path(explicit_report).resolve()
    return artifact_path(run_dir, manifest, 'report', 'report.md')


def normalize_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'invalid score: {value!r}')
    if score < 0 or score > 100:
        raise ValueError(f'score outside 0-100: {score}')
    return score


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError('empty judge output')
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    starts = [idx for idx in (stripped.find('{'), stripped.find('[')) if idx != -1]
    if not starts:
        raise ValueError('judge output did not contain JSON')
    start = min(starts)
    end = max(stripped.rfind('}'), stripped.rfind(']'))
    if end < start:
        raise ValueError('judge output contained incomplete JSON')
    return json.loads(stripped[start:end + 1])


def build_judge_prompt(task: dict, report_text: str, fact_claims: list[dict]) -> dict:
    return {
        'task': 'Score this internal deep-research run. Return only JSON.',
        'not_external_benchmark': True,
        'rubric_version': task.get('rubric_version', 'race-mini-v1'),
        'required_race_dimensions': list(RACE_DIMENSIONS),
        'required_fact_verdicts': list(FACT_VERDICTS),
        'research_task': {
            'task_id': task.get('task_id'),
            'category': task.get('category'),
            'prompt': task.get('prompt'),
            'success_criteria': task.get('success_criteria') or [],
        },
        'report_text': report_text[:60000],
        'fact_claims': fact_claims,
        'output_schema': {
            'race_scores': {dimension: '0-100 number' for dimension in RACE_DIMENSIONS},
            'race_rationales': {dimension: 'short rationale' for dimension in RACE_DIMENSIONS},
            'fact_judgments': [
                {'claim_id': 'string', 'verdict': 'entailed|contradicted|insufficient', 'rationale': 'short rationale'}
            ],
        },
    }


def run_judge(payload: dict, command: str, timeout: int) -> Any:
    cmd = shlex.split(command)
    if not cmd:
        raise ValueError('judge command is empty')
    result = subprocess.run(
        cmd,
        input=json.dumps(payload, indent=2, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f'judge command exited {result.returncode}: {result.stderr.strip()}')
    return extract_json(result.stdout)


def select_fact_claims(claims: list[dict], sample_size: int, seed: str) -> list[dict]:
    factual = [
        claim for claim in claims
        if claim.get('claim_type') == 'factual' and (claim.get('cited_source_ids') or claim.get('evidence_ids'))
    ]
    def key(claim: dict) -> str:
        return hashlib.sha256(f'{seed}:{claim.get("claim_id")}'.encode('utf-8')).hexdigest()
    factual.sort(key=key)
    return factual[:max(sample_size, 0)]


def normalize_fact_judgments(payload: Any) -> dict[str, dict]:
    rows: list[dict] = []
    if isinstance(payload, dict) and isinstance(payload.get('fact_judgments'), list):
        rows = payload['fact_judgments']
    elif isinstance(payload, dict) and isinstance(payload.get('judgments'), list):
        rows = payload['judgments']
    elif isinstance(payload, list):
        rows = payload
    judgments: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get('claim_id') or '').strip()
        verdict = str(row.get('verdict') or '').strip().lower()
        if claim_id and verdict in FACT_VERDICTS:
            judgments[claim_id] = {
                'verdict': verdict,
                'rationale': str(row.get('rationale') or '').strip(),
            }
    return judgments


def infer_fact_verdict(claim: dict) -> str:
    semantic = claim.get('support_status_llm')
    if semantic in FACT_VERDICTS:
        return semantic
    return 'entailed' if claim.get('support_status') == 'supported' else 'insufficient'


def score_fact_mini(sampled_claims: list[dict], judge_payload: Any | None) -> dict:
    provided = normalize_fact_judgments(judge_payload or {})
    counts = {'entailed': 0, 'contradicted': 0, 'insufficient': 0}
    details = []
    for claim in sampled_claims:
        claim_id = claim.get('claim_id')
        judgment = provided.get(claim_id)
        verdict = judgment['verdict'] if judgment else infer_fact_verdict(claim)
        counts[verdict] += 1
        details.append({
            'claim_id': claim_id,
            'verdict': verdict,
            'source': 'judge_output' if judgment else 'stored_support_status',
            'rationale': judgment.get('rationale', '') if judgment else '',
        })
    sample_size = len(sampled_claims)
    accuracy = counts['entailed'] / sample_size if sample_size else None
    return {
        'sample_size': sample_size,
        'entailed': counts['entailed'],
        'contradicted': counts['contradicted'],
        'insufficient': counts['insufficient'],
        'accuracy': round(accuracy, 4) if accuracy is not None else None,
        'sampled_claim_ids': [claim.get('claim_id') for claim in sampled_claims],
        'details': details,
    }


def normalize_race_scores(judge_payload: dict) -> tuple[dict[str, float], dict[str, str]]:
    raw_scores = judge_payload.get('race_scores') or {}
    raw_rationales = judge_payload.get('race_rationales') or {}
    scores = {dimension: normalize_score(raw_scores.get(dimension)) for dimension in RACE_DIMENSIONS}
    rationales = {dimension: str(raw_rationales.get(dimension) or '') for dimension in RACE_DIMENSIONS}
    return scores, rationales


def check_artifacts(run_dir: Path, manifest: dict, report_path: Path) -> tuple[list[dict], dict[str, str | None], dict[str, float | None]]:
    paths = {
        'run_manifest': run_manifest_path(run_dir),
        'report': report_path,
        'sources': artifact_path(run_dir, manifest, 'sources', 'sources.jsonl'),
        'evidence': artifact_path(run_dir, manifest, 'evidence', 'evidence.jsonl'),
        'claims': artifact_path(run_dir, manifest, 'claims', 'claims.jsonl'),
        'audit_manifest': run_dir / 'audit_manifest.json',
    }
    checks: list[dict] = []
    hashes: dict[str, str | None] = {}
    mtimes: dict[str, float | None] = {}
    for name, path in paths.items():
        exists = path.exists()
        checks.append({'name': f'artifact:{name}', 'status': 'pass' if exists else 'fail', 'path': str(path)})
        hashes[name] = sha256_file(path)
        mtimes[name] = path.stat().st_mtime if exists else None

    audit_mtime = mtimes.get('audit_manifest')
    if audit_mtime is not None:
        stale_inputs = [
            name for name in ('report', 'sources', 'evidence', 'claims')
            if mtimes.get(name) is not None and mtimes[name] > audit_mtime
        ]
        checks.append({
            'name': 'audit_manifest_freshness',
            'status': 'fail' if stale_inputs else 'pass',
            'stale_inputs': stale_inputs,
        })
    return checks, hashes, mtimes


def append_runs_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, '') for column in CSV_COLUMNS})


def cmd_list_tasks(args: argparse.Namespace) -> int:
    tasks = load_tasks(Path(args.task_file))
    print(json.dumps({'count': len(tasks), 'tasks': tasks}, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def cmd_score_run(args: argparse.Namespace) -> int:
    started = time.time()
    if not args.judge_model or not args.judge_version:
        print(json.dumps({'status': 'fail', 'error': 'judge_model and judge_version are required'}, indent=2))
        return 2

    run_dir = Path(args.run_dir).resolve()
    task_path = Path(args.task).resolve()
    eval_run_id = args.eval_run_id or f'eval_{uuid.uuid4().hex[:12]}'
    evaluated_at = utc_now()
    checks: list[dict] = []
    incomplete_reasons: list[str] = []
    judge_status = 'skipped'
    judge_payload: dict[str, Any] | None = None

    try:
        task = select_task(task_path, args.task_id)
        manifest = read_json(run_manifest_path(run_dir))
        report_path = resolve_report_path(run_dir, manifest, args.report)
        report_text = report_path.read_text(encoding='utf-8') if report_path.exists() else ''
        artifact_checks, artifact_hashes, artifact_mtimes = check_artifacts(run_dir, manifest, report_path)
        checks.extend(artifact_checks)

        audit_manifest = read_json(run_dir / 'audit_manifest.json') if (run_dir / 'audit_manifest.json').exists() else {}
        audit_status = audit_manifest.get('status')
        checks.append({'name': 'audit_manifest_status', 'status': 'pass' if audit_status == 'pass' else 'fail', 'value': audit_status})

        if args.strict and not manifest.get('finished_at'):
            checks.append({'name': 'finished_at', 'status': 'fail', 'message': 'run_manifest.finished_at is required in strict eval mode'})
        else:
            checks.append({'name': 'finished_at', 'status': 'pass' if manifest.get('finished_at') else 'warning'})

        claims = read_jsonl(artifact_path(run_dir, manifest, 'claims', 'claims.jsonl'))
        sampled_claims = select_fact_claims(claims, args.fact_sample_size, args.seed)
        fact_prompt_claims = [
            {
                'claim_id': claim.get('claim_id'),
                'text': claim.get('text'),
                'support_status': claim.get('support_status'),
                'support_status_llm': claim.get('support_status_llm'),
                'cited_source_ids': claim.get('cited_source_ids') or [],
                'evidence_ids': claim.get('evidence_ids') or [],
            }
            for claim in sampled_claims
        ]
        judge_prompt = build_judge_prompt(task, report_text, fact_prompt_claims)
        judge_prompt_hash = sha256_text(json.dumps(judge_prompt, sort_keys=True, ensure_ascii=False))

        if args.judge_output:
            judge_payload = read_json(Path(args.judge_output))
            judge_status = 'ok'
        elif args.judge_command:
            judge_payload = run_judge(judge_prompt, args.judge_command, args.timeout)
            judge_status = 'ok'
        else:
            judge_status = 'failed'
            incomplete_reasons.append('judge_output_or_command_required')
            judge_payload = {}

        if judge_status == 'ok':
            race_scores, race_rationales = normalize_race_scores(judge_payload)
        else:
            race_scores = {dimension: 0.0 for dimension in RACE_DIMENSIONS}
            race_rationales = {dimension: '' for dimension in RACE_DIMENSIONS}
            checks.append({'name': 'judge_call', 'status': 'fail', 'judge_status': judge_status})

        fact_mini = score_fact_mini(sampled_claims, judge_payload)
        race_overall = round(sum(race_scores.values()) / len(RACE_DIMENSIONS), 4)
    except Exception as exc:
        task = {'task_id': args.task_id or '(unknown)', 'category': '(unknown)'}
        manifest = {}
        report_path = Path(args.report or '')
        audit_status = None
        artifact_hashes = {}
        artifact_mtimes = {}
        judge_prompt_hash = ''
        race_scores = {dimension: 0.0 for dimension in RACE_DIMENSIONS}
        race_rationales = {dimension: '' for dimension in RACE_DIMENSIONS}
        race_overall = 0.0
        fact_mini = {'sample_size': 0, 'entailed': 0, 'contradicted': 0, 'insufficient': 0, 'accuracy': None, 'sampled_claim_ids': [], 'details': []}
        checks.append({'name': 'score_run_exception', 'status': 'fail', 'error': str(exc)})
        incomplete_reasons.append(str(exc))

    failed_checks = [check for check in checks if check.get('status') == 'fail']
    if judge_status != 'ok' and 'judge_output_or_command_required' not in incomplete_reasons:
        incomplete_reasons.append(f'judge_status:{judge_status}')
    status = 'fail' if failed_checks or judge_status != 'ok' else 'pass'
    elapsed = round(time.time() - started, 4)
    result_path = Path(args.results_dir or (DEFAULT_EVAL_DIR / 'results')) / f'{eval_run_id}.json'

    self_eval = {
        'version': '1.0',
        'eval_run_id': eval_run_id,
        'task_id': task.get('task_id'),
        'task_category': task.get('category'),
        'status': status,
        'evaluated_at': evaluated_at,
        'strict': bool(args.strict),
        'judge': {
            'provider': args.judge_provider,
            'model': args.judge_model,
            'version': args.judge_version,
            'prompt_hash': judge_prompt_hash,
            'rubric_version': task.get('rubric_version', 'race-mini-v1'),
            'temperature': args.temperature,
            'seed': args.seed,
            'status': judge_status,
        },
        'checks': checks,
        'counts': {
            'critical_findings': len(failed_checks),
            'warnings': sum(1 for check in checks if check.get('status') == 'warning'),
        },
        'race_scores': race_scores,
        'race_rationales': race_rationales,
        'race_overall': race_overall,
        'fact_mini': fact_mini,
        'delivery_gate': {
            'status': 'pass' if audit_status == 'pass' else 'fail',
            'audit_manifest_status': audit_status,
        },
        'artifact_hashes': artifact_hashes,
        'artifact_mtimes': artifact_mtimes,
        'network_mode': 'enabled' if args.network else 'disabled',
        'network_used': bool(args.network),
        'llm_used': bool(args.judge_command),
        'result_path': str(result_path),
        'incomplete_reason': '; '.join(incomplete_reasons) if incomplete_reasons else None,
        'elapsed_seconds': elapsed,
    }

    try:
        manifest_path = run_manifest_path(run_dir)
        if manifest_path.exists():
            current_manifest = read_json(manifest_path)
            current_manifest['self_eval'] = self_eval
            write_json(manifest_path, current_manifest)
    except Exception as exc:
        self_eval['status'] = 'fail'
        self_eval['checks'].append({'name': 'write_self_eval', 'status': 'fail', 'error': str(exc)})

    write_json(result_path, self_eval)
    csv_row = {
        'eval_run_id': eval_run_id,
        'status': self_eval['status'],
        'task_id': self_eval.get('task_id'),
        'category': self_eval.get('task_category'),
        'mode': manifest.get('mode') if isinstance(manifest, dict) else '',
        'run_dir': str(run_dir),
        'report_path': str(report_path),
        'evaluated_at': evaluated_at,
        'judge_provider': args.judge_provider,
        'judge_model': args.judge_model,
        'judge_version': args.judge_version,
        'judge_prompt_hash': self_eval['judge']['prompt_hash'],
        'rubric_version': self_eval['judge']['rubric_version'],
        'instruction_following': race_scores['instruction_following'],
        'comprehensiveness': race_scores['comprehensiveness'],
        'insight': race_scores['insight'],
        'writing_objectivity': race_scores['writing_objectivity'],
        'race_overall': race_overall,
        'fact_sample_size': fact_mini['sample_size'],
        'fact_entailed': fact_mini['entailed'],
        'fact_contradicted': fact_mini['contradicted'],
        'fact_insufficient': fact_mini['insufficient'],
        'fact_accuracy': fact_mini['accuracy'],
        'delivery_gate_status': self_eval['delivery_gate']['status'],
        'audit_manifest_status': self_eval['delivery_gate']['audit_manifest_status'],
        'network_mode': self_eval['network_mode'],
        'llm_used': self_eval['llm_used'],
        'elapsed_seconds': elapsed,
        'result_path': str(result_path),
    }
    append_runs_csv(Path(args.runs_csv or (DEFAULT_EVAL_DIR / 'runs.csv')), csv_row)
    print(json.dumps(self_eval, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if args.strict and self_eval['status'] != 'pass' else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog='run_eval', description='Internal deep-research self-evaluation harness')
    sub = parser.add_subparsers(dest='command', required=True)

    p_list = sub.add_parser('list-tasks', help='List tasks from a task file')
    p_list.add_argument('--task-file', default=str(DEFAULT_EVAL_DIR / 'tasks' / 'gold_tasks.json'))

    p_score = sub.add_parser('score-run', help='Score a completed run directory')
    p_score.add_argument('--task', required=True, help='Task JSON file or task collection JSON')
    p_score.add_argument('--task-id', help='Task ID when --task points to a collection')
    p_score.add_argument('--run-dir', required=True)
    p_score.add_argument('--report')
    p_score.add_argument('--judge-output', help='Fixture/live judge JSON output')
    p_score.add_argument('--judge-command', help='Command that reads the judge prompt from stdin and returns JSON')
    p_score.add_argument('--judge-provider', default='fixture')
    p_score.add_argument('--judge-model', required=True)
    p_score.add_argument('--judge-version', required=True)
    p_score.add_argument('--temperature', default='0')
    p_score.add_argument('--seed', default='self-eval-v1')
    p_score.add_argument('--fact-sample-size', type=int, default=10)
    p_score.add_argument('--timeout', type=int, default=900)
    p_score.add_argument('--strict', action='store_true')
    p_score.add_argument('--network', action='store_true', help='Allow networked fetch/judge behavior and record that mode')
    p_score.add_argument('--runs-csv')
    p_score.add_argument('--results-dir')
    p_score.add_argument('--eval-run-id')

    args = parser.parse_args()
    if args.command == 'list-tasks':
        return cmd_list_tasks(args)
    if args.command == 'score-run':
        return cmd_score_run(args)
    return 1


if __name__ == '__main__':
    sys.exit(main())
