#!/usr/bin/env python3
"""Run-trace and coverage accounting for deep-research runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def stable_id(prefix: str, *parts: str) -> str:
    payload = '|'.join(str(part or '') for part in parts)
    return f'{prefix}_{hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]}'


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def plan_content_hash(plan: dict) -> str:
    """Hash plan content while excluding checkpoint metadata."""
    body = {key: value for key, value in plan.items() if key != 'checkpoint'}
    payload = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def manifest_path(run_dir: Path) -> Path:
    return run_dir / 'run_manifest.json'


def artifact_path(run_dir: Path, manifest: dict, key: str, default: str) -> Path:
    rel = (manifest.get('artifact_paths') or {}).get(key) or default
    path = Path(rel)
    return path if path.is_absolute() else run_dir / path


def load_manifest(run_dir: Path) -> dict:
    manifest = read_json(manifest_path(run_dir))
    if not manifest:
        raise SystemExit(f'run_manifest.json not found in {run_dir}')
    trace = manifest.setdefault('execution_trace', {})
    trace.setdefault('version', '1.0')
    trace.setdefault('provider_calls', [])
    trace.setdefault('subagents', [])
    trace.setdefault('lane_source_counts', {})
    trace.setdefault('query_family_source_counts', {})
    trace.setdefault('phase_metrics', {})
    trace.setdefault('events', [])
    return manifest


def plan_path_for_manifest(run_dir: Path, manifest: dict) -> Path:
    return artifact_path(run_dir, manifest, 'plan', 'plan.json')


def append_event(trace: dict, phase: str, status: str, message: str) -> None:
    trace.setdefault('events', []).append({
        'event_id': stable_id('evt', phase, status, message, utc_now()),
        'phase': phase,
        'status': status,
        'created_at': utc_now(),
        'message': message,
    })


def update_phase_metrics(
    trace: dict,
    phase: str,
    *,
    status: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_seconds: float | None = None,
    provider_call_count: int = 0,
    subagent_count: int = 0,
    result_count: int = 0,
    retained_source_count: int = 0,
    evidence_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
) -> dict:
    metrics = trace.setdefault('phase_metrics', {})
    row = metrics.setdefault(phase, {
        'phase': phase,
        'status': 'in_progress',
        'started_at': None,
        'finished_at': None,
        'duration_seconds': 0.0,
        'provider_call_count': 0,
        'subagent_count': 0,
        'result_count': 0,
        'retained_source_count': 0,
        'evidence_count': 0,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'estimated_cost_usd': 0.0,
    })
    if status:
        row['status'] = status
    if started_at and not row.get('started_at'):
        row['started_at'] = started_at
    if finished_at:
        row['finished_at'] = finished_at
    if duration_seconds is not None:
        row['duration_seconds'] = float(row.get('duration_seconds') or 0) + max(float(duration_seconds), 0.0)
    row['provider_call_count'] = int(row.get('provider_call_count') or 0) + max(provider_call_count, 0)
    row['subagent_count'] = int(row.get('subagent_count') or 0) + max(subagent_count, 0)
    row['result_count'] = int(row.get('result_count') or 0) + max(result_count, 0)
    row['retained_source_count'] = int(row.get('retained_source_count') or 0) + max(retained_source_count, 0)
    row['evidence_count'] = int(row.get('evidence_count') or 0) + max(evidence_count, 0)
    row['input_tokens'] = int(row.get('input_tokens') or 0) + max(input_tokens, 0)
    row['output_tokens'] = int(row.get('output_tokens') or 0) + max(output_tokens, 0)
    row['total_tokens'] = row['input_tokens'] + row['output_tokens']
    row['estimated_cost_usd'] = round(float(row.get('estimated_cost_usd') or 0) + max(float(estimated_cost_usd), 0.0), 6)
    return row


def ensure_plan_allows_retrieval(run_dir: Path, manifest: dict) -> None:
    """Block retrieval records for an interactive plan that has not been approved."""
    plan = read_json(plan_path_for_manifest(run_dir, manifest))
    checkpoint = plan.get('checkpoint') or {}
    if not checkpoint.get('interactive'):
        return
    if checkpoint.get('status') in {'approved', 'edited_approved'}:
        return
    raise SystemExit(
        'interactive plan checkpoint is not approved; review/edit plan.json, then run '
        'python scripts/run_trace.py approve-plan --dir [run_folder]'
    )


def approve_plan(args: argparse.Namespace) -> dict:
    """Approve plan.json after optional interactive edits."""
    run_dir = Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    plan_path = plan_path_for_manifest(run_dir, manifest)
    plan = read_json(plan_path)
    if not plan:
        raise SystemExit(f'plan.json not found at {plan_path}')

    checkpoint = plan.setdefault('checkpoint', {})
    before_hash = checkpoint.get('plan_hash_before_review') or plan_content_hash(plan)
    current_hash = plan_content_hash(plan)
    edits_detected = before_hash != current_hash
    checkpoint.update({
        'status': 'edited_approved' if edits_detected else 'approved',
        'interactive': bool(checkpoint.get('interactive', True)),
        'approved_at': args.approved_at or utc_now(),
        'approved_by': args.approved_by,
        'plan_hash_before_review': before_hash,
        'approved_plan_hash': current_hash,
        'edits_detected': edits_detected,
    })
    notes = list(checkpoint.get('notes') or [])
    if args.note:
        notes.append(args.note)
    checkpoint['notes'] = notes
    write_json(plan_path, plan)

    trace = manifest['execution_trace']
    append_event(
        trace,
        'plan_checkpoint',
        checkpoint['status'],
        'plan.json approved for retrieval; edits_detected=' + str(edits_detected).lower(),
    )
    write_json(manifest_path(run_dir), manifest)
    return {'status': 'ok', 'plan': str(plan_path), 'checkpoint': checkpoint}


def record_provider_call(args: argparse.Namespace) -> dict:
    run_dir = Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    ensure_plan_allows_retrieval(run_dir, manifest)
    trace = manifest['execution_trace']
    started_at = args.started_at or utc_now()
    provider_call_id = args.provider_call_id or stable_id(
        'call',
        args.provider,
        args.tool,
        args.query,
        args.lane_id or '',
        started_at,
    )
    call = {
        'provider_call_id': provider_call_id,
        'phase': args.phase,
        'provider': args.provider,
        'tool': args.tool,
        'query': args.query,
        'lane_id': args.lane_id,
        'query_family_id': args.query_family_id,
        'started_at': started_at,
        'finished_at': args.finished_at or utc_now(),
        'status': args.status,
        'result_count': max(args.result_count, 0),
        'retained_source_count': max(args.retained_source_count, 0),
        'input_tokens': max(args.input_tokens, 0),
        'output_tokens': max(args.output_tokens, 0),
        'estimated_cost_usd': max(args.cost_usd, 0.0),
        'artifacts': args.artifact or [],
    }
    trace['provider_calls'].append(call)
    if args.lane_id:
        trace['lane_source_counts'][args.lane_id] = (
            int(trace['lane_source_counts'].get(args.lane_id, 0)) + call['retained_source_count']
        )
    if args.query_family_id:
        trace['query_family_source_counts'][args.query_family_id] = (
            int(trace['query_family_source_counts'].get(args.query_family_id, 0)) + call['retained_source_count']
        )
    update_phase_metrics(
        trace,
        args.phase,
        status=args.status,
        started_at=call['started_at'],
        finished_at=call['finished_at'],
        provider_call_count=1,
        result_count=call['result_count'],
        retained_source_count=call['retained_source_count'],
        input_tokens=call['input_tokens'],
        output_tokens=call['output_tokens'],
        estimated_cost_usd=call['estimated_cost_usd'],
    )
    append_event(trace, 'retrieval', args.status, f'provider call recorded: {provider_call_id}')
    write_json(manifest_path(run_dir), manifest)
    return {'status': 'ok', 'provider_call': call}


def record_subagent(args: argparse.Namespace) -> dict:
    run_dir = Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    ensure_plan_allows_retrieval(run_dir, manifest)
    trace = manifest['execution_trace']
    started_at = args.started_at or utc_now()
    subagent_id = args.subagent_id or stable_id('agent', args.lane_id or '', args.role, started_at)
    subagent = {
        'subagent_id': subagent_id,
        'phase': args.phase,
        'lane_id': args.lane_id,
        'role': args.role,
        'model': args.model,
        'reasoning': args.reasoning,
        'status': args.status,
        'source_count': max(args.source_count, 0),
        'evidence_count': max(args.evidence_count, 0),
        'started_at': started_at,
        'finished_at': args.finished_at or utc_now(),
    }
    trace['subagents'].append(subagent)
    if args.lane_id:
        trace['lane_source_counts'][args.lane_id] = (
            int(trace['lane_source_counts'].get(args.lane_id, 0)) + subagent['source_count']
        )
    update_phase_metrics(
        trace,
        args.phase,
        status=args.status,
        started_at=subagent['started_at'],
        finished_at=subagent['finished_at'],
        subagent_count=1,
        retained_source_count=subagent['source_count'],
        evidence_count=subagent['evidence_count'],
        input_tokens=max(args.input_tokens, 0),
        output_tokens=max(args.output_tokens, 0),
        estimated_cost_usd=max(args.cost_usd, 0.0),
    )
    append_event(trace, 'subagent', args.status, f'subagent recorded: {subagent_id}')
    write_json(manifest_path(run_dir), manifest)
    return {'status': 'ok', 'subagent': subagent}


def record_phase_metric(args: argparse.Namespace) -> dict:
    run_dir = Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    trace = manifest['execution_trace']
    row = update_phase_metrics(
        trace,
        args.phase,
        status=args.status,
        started_at=args.started_at,
        finished_at=args.finished_at,
        duration_seconds=args.duration_seconds,
        provider_call_count=args.provider_call_count,
        subagent_count=args.subagent_count,
        result_count=args.result_count,
        retained_source_count=args.retained_source_count,
        evidence_count=args.evidence_count,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        estimated_cost_usd=args.cost_usd,
    )
    append_event(trace, args.phase, args.status, f'phase metrics recorded: {args.phase}')
    write_json(manifest_path(run_dir), manifest)
    return {'status': 'ok', 'phase': args.phase, 'metrics': row}


def explicit_count(rows: list[dict], key: str) -> Counter:
    counts = Counter()
    for row in rows:
        value = row.get(key)
        if value:
            counts[str(value)] += 1
    return counts


def parse_lane_status(values: list[str] | None) -> dict[str, str]:
    out = {}
    for value in values or []:
        if '=' not in value:
            raise SystemExit('--lane-status must be lane_id=status')
        lane_id, status = value.split('=', 1)
        out[lane_id.strip()] = status.strip()
    return out


def parse_lane_gap(values: list[str] | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for value in values or []:
        if '=' not in value:
            raise SystemExit('--lane-gap must be lane_id=text')
        lane_id, text = value.split('=', 1)
        out[lane_id.strip()].append(text.strip())
    return out


def rebuild_coverage(args: argparse.Namespace) -> dict:
    run_dir = Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    plan_path = artifact_path(run_dir, manifest, 'plan', 'plan.json')
    coverage_path = artifact_path(run_dir, manifest, 'coverage_map', 'coverage_map.json')
    plan = read_json(plan_path)
    if not plan:
        raise SystemExit(f'plan.json not found at {plan_path}')

    trace = manifest['execution_trace']
    sources = read_jsonl(artifact_path(run_dir, manifest, 'sources', 'sources.jsonl'))
    evidence = read_jsonl(artifact_path(run_dir, manifest, 'evidence', 'evidence.jsonl'))
    manual_status = parse_lane_status(args.lane_status)
    manual_gaps = parse_lane_gap(args.lane_gap)
    existing = read_json(coverage_path)
    existing_by_lane = {
        row.get('lane_id'): row
        for row in existing.get('lane_coverage', [])
        if row.get('lane_id')
    }

    provider_calls = trace.get('provider_calls') or []
    subagents = trace.get('subagents') or []
    provider_by_lane = Counter(call.get('lane_id') for call in provider_calls if call.get('lane_id'))
    provider_by_family = Counter(call.get('query_family_id') for call in provider_calls if call.get('query_family_id'))
    retained_by_lane = Counter()
    retained_by_family = Counter()
    for call in provider_calls:
        retained = int(call.get('retained_source_count') or 0)
        if call.get('lane_id'):
            retained_by_lane[call['lane_id']] += retained
        if call.get('query_family_id'):
            retained_by_family[call['query_family_id']] += retained
    subagents_by_lane = Counter(agent.get('lane_id') for agent in subagents if agent.get('lane_id'))
    subagent_sources_by_lane = Counter()
    subagent_evidence_by_lane = Counter()
    roles_by_lane: dict[str, str] = {}
    for agent in subagents:
        lane_id = agent.get('lane_id')
        if not lane_id:
            continue
        subagent_sources_by_lane[lane_id] += int(agent.get('source_count') or 0)
        subagent_evidence_by_lane[lane_id] += int(agent.get('evidence_count') or 0)
        roles_by_lane.setdefault(lane_id, str(agent.get('role') or ''))

    source_lane_counts = explicit_count(sources, 'lane_id')
    evidence_lane_counts = explicit_count(evidence, 'lane_id')
    lanes = []
    families = []
    for lane in plan.get('lanes', []):
        lane_id = lane.get('lane_id')
        expected_min = int(lane.get('expected_source_min') or 0)
        source_count = max(
            int(trace.get('lane_source_counts', {}).get(lane_id, 0)),
            retained_by_lane[lane_id] + subagent_sources_by_lane[lane_id],
            source_lane_counts[lane_id],
        )
        evidence_count = max(evidence_lane_counts[lane_id], subagent_evidence_by_lane[lane_id])
        provider_count = provider_by_lane[lane_id]
        subagent_count = subagents_by_lane[lane_id]
        executed = bool(provider_count or subagent_count or source_count or evidence_count)
        prior = existing_by_lane.get(lane_id, {})
        gaps = list(prior.get('gaps') or [])
        gaps.extend(manual_gaps.get(lane_id, []))
        if lane_id in manual_status:
            status = manual_status[lane_id]
        elif prior.get('status') in {'bounded', 'gap_disclosed'}:
            status = prior['status']
        elif source_count >= expected_min:
            status = 'covered'
        elif executed:
            status = 'below_target'
        else:
            status = 'planned'
        lanes.append({
            'lane_id': lane_id,
            'planned': True,
            'executed': executed,
            'executed_role': roles_by_lane.get(lane_id) or lane.get('role') if executed else None,
            'source_count': source_count,
            'evidence_count': evidence_count,
            'provider_call_count': provider_count,
            'subagent_count': subagent_count,
            'expected_source_min': expected_min,
            'missing_from_plan': not executed,
            'status': status,
            'gaps': gaps,
        })
        for family in lane.get('query_families', []):
            family_id = family.get('query_family_id')
            retained = retained_by_family[family_id] + int(trace.get('query_family_source_counts', {}).get(family_id, 0))
            executed_family = bool(provider_by_family[family_id] or retained)
            families.append({
                'query_family_id': family_id,
                'lane_id': lane_id,
                'planned': True,
                'executed': executed_family,
                'provider_call_count': provider_by_family[family_id],
                'retained_source_count': retained,
                'status': 'covered' if retained else ('in_progress' if executed_family else 'planned'),
            })

    overall = {
        'planned_lanes': len(lanes),
        'executed_lanes': sum(1 for lane in lanes if lane['executed']),
        'covered_lanes': sum(1 for lane in lanes if lane['status'] == 'covered'),
        'gap_disclosed_lanes': sum(1 for lane in lanes if lane['status'] == 'gap_disclosed'),
        'bounded_lanes': sum(1 for lane in lanes if lane['status'] == 'bounded'),
        'below_target_lanes': sum(1 for lane in lanes if lane['status'] in {'planned', 'below_target', 'in_progress'}),
        'total_sources': len({row.get('source_id') for row in sources if row.get('source_id')}),
        'total_evidence': len({row.get('evidence_id') for row in evidence if row.get('evidence_id')}),
        'status': 'covered' if lanes and all(lane['status'] in {'covered', 'bounded', 'gap_disclosed'} for lane in lanes) else 'incomplete',
    }
    coverage = {
        'version': '1.0',
        'generated_at': utc_now(),
        'mode': plan.get('mode') or manifest.get('mode') or 'standard',
        'lane_coverage': lanes,
        'query_family_coverage': families,
        'overall': overall,
    }
    trace['lane_source_counts'] = {lane['lane_id']: lane['source_count'] for lane in lanes}
    trace['query_family_source_counts'] = {
        family['query_family_id']: family['retained_source_count']
        for family in families
    }
    append_event(trace, 'coverage', overall['status'], 'coverage_map.json rebuilt')
    write_json(coverage_path, coverage)
    write_json(manifest_path(run_dir), manifest)
    return {'status': 'ok', 'coverage_map': str(coverage_path), 'overall': overall}


def main() -> int:
    parser = argparse.ArgumentParser(description='Record run trace and rebuild deep-research coverage maps.')
    sub = parser.add_subparsers(dest='command', required=True)

    p_call = sub.add_parser('provider-call', help='Append one provider/tool call to run_manifest.execution_trace')
    p_call.add_argument('--dir', required=True)
    p_call.add_argument('--provider', required=True)
    p_call.add_argument('--tool', required=True)
    p_call.add_argument('--query', required=True)
    p_call.add_argument('--phase', default='retrieval')
    p_call.add_argument('--lane-id')
    p_call.add_argument('--query-family-id')
    p_call.add_argument('--status', default='ok')
    p_call.add_argument('--result-count', type=int, default=0)
    p_call.add_argument('--retained-source-count', type=int, default=0)
    p_call.add_argument('--input-tokens', type=int, default=0)
    p_call.add_argument('--output-tokens', type=int, default=0)
    p_call.add_argument('--cost-usd', type=float, default=0.0)
    p_call.add_argument('--started-at')
    p_call.add_argument('--finished-at')
    p_call.add_argument('--provider-call-id')
    p_call.add_argument('--artifact', action='append')

    p_agent = sub.add_parser('subagent', help='Append one subagent execution record to run_manifest.execution_trace')
    p_agent.add_argument('--dir', required=True)
    p_agent.add_argument('--subagent-id')
    p_agent.add_argument('--phase', default='retrieval')
    p_agent.add_argument('--lane-id')
    p_agent.add_argument('--role', required=True)
    p_agent.add_argument('--model')
    p_agent.add_argument('--reasoning')
    p_agent.add_argument('--status', default='ok')
    p_agent.add_argument('--source-count', type=int, default=0)
    p_agent.add_argument('--evidence-count', type=int, default=0)
    p_agent.add_argument('--input-tokens', type=int, default=0)
    p_agent.add_argument('--output-tokens', type=int, default=0)
    p_agent.add_argument('--cost-usd', type=float, default=0.0)
    p_agent.add_argument('--started-at')
    p_agent.add_argument('--finished-at')

    p_cov = sub.add_parser('coverage', help='Rebuild coverage_map.json from plan, trace, and ledgers')
    p_cov.add_argument('--dir', required=True)
    p_cov.add_argument('--lane-status', action='append', help='Manual lane status override as lane_id=status')
    p_cov.add_argument('--lane-gap', action='append', help='Manual lane gap note as lane_id=text')

    p_approve = sub.add_parser('approve-plan', help='Approve plan.json after optional interactive edits')
    p_approve.add_argument('--dir', required=True)
    p_approve.add_argument('--approved-by', default='user')
    p_approve.add_argument('--approved-at')
    p_approve.add_argument('--note')

    p_phase = sub.add_parser('phase', help='Record per-phase timing/token/cost counters')
    p_phase.add_argument('--dir', required=True)
    p_phase.add_argument('--phase', required=True)
    p_phase.add_argument('--status', default='ok')
    p_phase.add_argument('--started-at')
    p_phase.add_argument('--finished-at')
    p_phase.add_argument('--duration-seconds', type=float, default=0.0)
    p_phase.add_argument('--provider-call-count', type=int, default=0)
    p_phase.add_argument('--subagent-count', type=int, default=0)
    p_phase.add_argument('--result-count', type=int, default=0)
    p_phase.add_argument('--retained-source-count', type=int, default=0)
    p_phase.add_argument('--evidence-count', type=int, default=0)
    p_phase.add_argument('--input-tokens', type=int, default=0)
    p_phase.add_argument('--output-tokens', type=int, default=0)
    p_phase.add_argument('--cost-usd', type=float, default=0.0)

    args = parser.parse_args()
    if args.command == 'provider-call':
        out = record_provider_call(args)
    elif args.command == 'subagent':
        out = record_subagent(args)
    elif args.command == 'coverage':
        out = rebuild_coverage(args)
    elif args.command == 'approve-plan':
        out = approve_plan(args)
    elif args.command == 'phase':
        out = record_phase_metric(args)
    else:
        raise SystemExit(f'unknown command: {args.command}')
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
