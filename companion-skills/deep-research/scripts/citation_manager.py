#!/usr/bin/env python3
"""
Citation Manager — stable source identity and run manifest management.

CLI subcommands:
  init-run             Create run_manifest.json + empty artifact JSONL files
  register-source      Append a source to sources.jsonl, return source_id
  add-assumption       Persist a scoped assumption in run_manifest.json
  finish-run           Stamp run_manifest.finished_at after delivery gates pass
  write-brief          Write a headless Research Brief before retrieval
  assign-display-numbers  Generate stable_id -> display_number mapping
  export-bibliography   Render bibliography from sources.jsonl

Source identity:
  source_id = sha256(canonical_locator)[:16]
  canonical_locator = doi:..., arxiv:..., or normalized URL

All state is append-only JSONL. No mutable citation numbers in state files.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from ledger_index import (
    EVIDENCE_LEDGER,
    INDEX_FILENAME,
    SOURCE_LEDGER,
    add_source_to_index,
    build_ledger_index,
    load_or_build_index,
    refresh_ledger_signature,
    save_index,
    source_ids_from_index,
)


# ---------------------------------------------------------------------------
# Canonical locator normalization
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|doi:)(10\.\d{4,}/\S+)', re.IGNORECASE)
ARXIV_RE = re.compile(r'(?:https?://arxiv\.org/abs/|arxiv:)(\d{4}\.\d{4,}(?:v\d+)?)', re.IGNORECASE)
CITATION_RE = re.compile(r'\[((?:[SE]?\d+)(?:,\s*(?:[SE]?\d+))*)\]')

# URL query params that are tracking noise, not content identifiers
TRACKING_PARAMS = frozenset([
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'ref', 'source', 'fbclid', 'gclid', 'mc_cid', 'mc_eid',
])


def canonicalize_locator(raw_url: str) -> str:
    """Derive a canonical locator from a raw URL or identifier string.

    Priority: DOI > arXiv > normalized URL.
    """
    # DOI
    m = DOI_RE.search(raw_url)
    if m:
        return f'doi:{m.group(1).rstrip(".")}'

    # arXiv
    m = ARXIV_RE.search(raw_url)
    if m:
        return f'arxiv:{m.group(1)}'

    # Normalized URL: lowercase scheme+host, strip fragment and tracking params
    parsed = urlparse(raw_url)
    scheme = (parsed.scheme or 'https').lower()
    host = (parsed.hostname or '').lower()
    path = parsed.path.rstrip('/')
    # Filter query params
    if parsed.query:
        pairs = []
        for part in parsed.query.split('&'):
            kv = part.split('=', 1)
            if kv[0].lower() not in TRACKING_PARAMS:
                pairs.append(part)
        query = '&'.join(sorted(pairs))
    else:
        query = ''
    return urlunparse((scheme, host, path, '', query, ''))


def compute_source_id(canonical_locator: str) -> str:
    """sha256(canonical_locator)[:16] hex."""
    return hashlib.sha256(canonical_locator.encode('utf-8')).hexdigest()[:16]


def compute_assumption_id(text: str) -> str:
    """Stable assumption ID for run_manifest assumptions."""
    return 'asm_' + hashlib.sha256(text.strip().lower().encode('utf-8')).hexdigest()[:8]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def append_jsonl(path: str, obj: dict) -> None:
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def append_jsonl_many(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, 'a') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: str, payload: dict) -> None:
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def ensure_execution_trace(manifest: dict) -> dict:
    """Ensure run_manifest.execution_trace has the schema-required containers."""
    trace = manifest.setdefault('execution_trace', {})
    trace.setdefault('version', '1.0')
    trace.setdefault('provider_calls', [])
    trace.setdefault('subagents', [])
    trace.setdefault('lane_source_counts', {})
    trace.setdefault('query_family_source_counts', {})
    trace.setdefault('phase_metrics', {})
    trace.setdefault('events', [])
    return trace


def read_jsonl_input(path: str) -> tuple[list[tuple[int, dict]], list[dict]]:
    rows: list[tuple[int, dict]] = []
    errors: list[dict] = []
    with open(path) as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append({'line': line_no, 'error': f'invalid JSON: {exc.msg}'})
                continue
            if not isinstance(row, dict):
                errors.append({'line': line_no, 'error': 'expected a JSON object'})
                continue
            rows.append((line_no, row))
    return rows, errors


def normalize_citation_label(raw_label: str) -> str:
    """Return the numeric display label from labels like 1, [1], S1, or E1."""
    label = str(raw_label or '').strip().strip('[]').upper()
    if label.startswith(('S', 'E')):
        label = label[1:]
    return label


def source_display_labels(source: dict, ordinal: int | None = None) -> list[str]:
    """Return explicit source labels plus optional ordinal fallback."""
    labels: list[str] = []
    for key in ('display_id', 'display_number', 'num'):
        normalized = normalize_citation_label(source.get(key))
        if normalized and normalized not in labels:
            labels.append(normalized)
    if ordinal is not None:
        labels.append(str(ordinal))
    return labels


def unique_sources(sources: list[dict]) -> list[dict]:
    """Deduplicate source rows by source_id while preserving first occurrence."""
    seen = set()
    unique = []
    for source in sources:
        source_id = source.get('source_id') or source.get('id')
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        unique.append(source)
    return unique


def build_source_alias_index(sources: list[dict]) -> dict[str, str]:
    """Map known display labels to source_id, preferring explicit row labels."""
    unique = unique_sources(sources)
    index: dict[str, str] = {}

    # Explicit labels are stronger than ledger ordinal.
    for source in unique:
        source_id = source.get('source_id') or source.get('id')
        for label in source_display_labels(source):
            index.setdefault(label, source_id)

    # Ordinal fallback exists only for older runs without persisted display maps.
    for ordinal, source in enumerate(unique, start=1):
        source_id = source.get('source_id') or source.get('id')
        index.setdefault(str(ordinal), source_id)

    return index


def extract_report_citation_labels(report_path: str) -> list[str]:
    """Return citation labels in first-use order from a markdown report."""
    if not report_path or not os.path.exists(report_path):
        return []
    with open(report_path) as f:
        text = f.read()

    labels: list[str] = []
    seen = set()
    for match in CITATION_RE.finditer(text):
        for raw_label in match.group(1).split(','):
            label = normalize_citation_label(raw_label)
            if label.isdigit() and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def build_display_map(sources: list[dict], report_path: str | None = None) -> dict:
    """Build a persisted display map for report labels and source IDs."""
    unique = unique_sources(sources)
    alias_index = build_source_alias_index(unique)
    ordered_source_ids: list[str] = []

    report_labels = extract_report_citation_labels(report_path) if report_path else []
    for label in report_labels:
        source_id = alias_index.get(label)
        if source_id and source_id not in ordered_source_ids:
            ordered_source_ids.append(source_id)

    for source in unique:
        source_id = source.get('source_id') or source.get('id')
        if source_id and source_id not in ordered_source_ids:
            ordered_source_ids.append(source_id)

    source_id_to_display_number = {
        source_id: i for i, source_id in enumerate(ordered_source_ids, start=1)
    }
    display_number_to_source_id = {
        str(display_number): source_id
        for source_id, display_number in source_id_to_display_number.items()
    }

    if report_labels:
        label_to_source_id = {
            label: alias_index[label]
            for label in report_labels
            if label in alias_index
        }
        label_source = 'report'
    else:
        label_to_source_id = dict(display_number_to_source_id)
        label_source = 'assigned'

    return {
        'version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'label_source': label_source,
        'order_from_report': report_path,
        'source_id_to_display_number': source_id_to_display_number,
        'display_number_to_source_id': display_number_to_source_id,
        'label_to_source_id': label_to_source_id,
        'source_alias_to_source_id': alias_index,
    }


def env_var_present(name: str) -> bool:
    """Return True when an env var is set directly or in the BioMCP secret env file."""
    if os.environ.get(name):
        return True
    candidate_paths = [
        os.environ.get('BIOMCP_ENV_FILE'),
        os.path.expanduser('~/.claude/secrets/biomcp.env'),
        os.path.expanduser('~/.codex/secrets/biomcp.env'),
    ]
    for path in candidate_paths:
        if not path or not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or '=' not in stripped:
                    continue
                key, value = stripped.split('=', 1)
                if key == name and value.strip():
                    return True
    return False


MODE_LANE_DEFAULTS = {
    'quick': [
        ('lane_core', 'main_thread', 'Core answer and source-backed orientation', 10),
    ],
    'standard': [
        ('lane_core', 'main_thread', 'Core research question and highest-value evidence', 25),
    ],
    'deep': [
        ('lane_primary', 'primary_source', 'Primary and authoritative sources for material claims', 25),
        ('lane_corroboration', 'corroboration', 'Independent corroboration and secondary context', 25),
    ],
    'ultradeep': [
        ('lane_primary', 'primary_source', 'Primary and authoritative sources for material claims', 25),
        ('lane_corroboration', 'corroboration', 'Independent corroboration and secondary context', 25),
        ('lane_adversarial', 'adversarial', 'Contradictions, bear cases, and disconfirming evidence', 25),
        ('lane_gap_scout', 'gap_scout', 'Coverage gaps, hard-target retrieval, and missing source classes', 25),
    ],
}


ROLE_EXECUTION_BUDGETS = {
    'main_thread': {
        'model_hint': 'runtime_default',
        'reasoning_effort': 'medium',
        'timeout_seconds': 600,
        'max_tool_calls': 6,
        'notes': 'Inline retrieval lane; keep narrow and evidence-led.',
    },
    'primary_source': {
        'model_hint': 'runtime_default',
        'reasoning_effort': 'medium',
        'timeout_seconds': 900,
        'max_tool_calls': 12,
        'notes': 'Discovery and primary-source retrieval worker.',
    },
    'corroboration': {
        'model_hint': 'runtime_default',
        'reasoning_effort': 'medium',
        'timeout_seconds': 900,
        'max_tool_calls': 12,
        'notes': 'Independent corroboration worker.',
    },
    'adversarial': {
        'model_hint': 'runtime_default',
        'reasoning_effort': 'high',
        'timeout_seconds': 900,
        'max_tool_calls': 10,
        'notes': 'Adversarial and contradiction-finding worker; use higher reasoning when supported.',
    },
    'gap_scout': {
        'model_hint': 'runtime_default',
        'reasoning_effort': 'high',
        'timeout_seconds': 900,
        'max_tool_calls': 10,
        'notes': 'Coverage-gap and hard-target worker; use higher reasoning when supported.',
    },
}


def execution_budget_for_role(role: str) -> dict:
    """Return a copy of the role-specific execution budget."""
    return dict(ROLE_EXECUTION_BUDGETS.get(role, ROLE_EXECUTION_BUDGETS['main_thread']))


def default_plan_for_mode(mode: str, query: str = '') -> dict:
    """Create a conservative pre-retrieval plan skeleton for a run mode."""
    lanes = []
    for lane_id, role, objective, source_min in MODE_LANE_DEFAULTS.get(mode, MODE_LANE_DEFAULTS['standard']):
        query_family_id = f'{lane_id}_core'
        lanes.append({
            'lane_id': lane_id,
            'role': role,
            'objective': objective,
            'query_families': [
                {
                    'query_family_id': query_family_id,
                    'description': 'Initial query family derived from the research brief and scope.',
                    'queries': [query] if query else [],
                }
            ],
            'expected_source_min': source_min,
            'expected_roles': [role],
            'execution_budget': execution_budget_for_role(role),
            'stop_conditions': [
                'Minimum source target met, or residual gap is explicitly marked bounded/gap_disclosed.',
                'Material claims in this lane have source-backed evidence or are moved to limitations.',
            ],
        })
    return {
        'version': '1.0',
        'mode': mode,
        'created_at': utc_now(),
        'lanes': lanes,
    }


def plan_content_hash(plan: dict) -> str:
    """Hash retrieval plan content while excluding checkpoint metadata."""
    body = {key: value for key, value in plan.items() if key != 'checkpoint'}
    payload = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def attach_plan_checkpoint(plan: dict, *, interactive: bool, created_at: str) -> dict:
    """Attach the editable-plan checkpoint used before retrieval."""
    checkpoint = {
        'status': 'ready_for_review' if interactive else 'skipped_headless',
        'interactive': bool(interactive),
        'notes': [],
        'plan_hash_before_review': plan_content_hash(plan),
        'edits_detected': False,
    }
    if interactive:
        checkpoint['paused_at'] = created_at
    plan['checkpoint'] = checkpoint
    return plan


def initial_coverage_map(plan: dict) -> dict:
    """Create an empty coverage map from a plan skeleton."""
    lane_coverage = []
    query_family_coverage = []
    for lane in plan.get('lanes', []):
        lane_id = lane.get('lane_id')
        lane_coverage.append({
            'lane_id': lane_id,
            'planned': True,
            'executed': False,
            'executed_role': None,
            'source_count': 0,
            'evidence_count': 0,
            'provider_call_count': 0,
            'subagent_count': 0,
            'expected_source_min': int(lane.get('expected_source_min') or 0),
            'missing_from_plan': True,
            'status': 'planned',
            'gaps': [],
        })
        for family in lane.get('query_families', []):
            query_family_coverage.append({
                'query_family_id': family.get('query_family_id'),
                'lane_id': lane_id,
                'planned': True,
                'executed': False,
                'provider_call_count': 0,
                'retained_source_count': 0,
                'status': 'planned',
            })
    return {
        'version': '1.0',
        'generated_at': utc_now(),
        'mode': plan.get('mode', 'standard'),
        'lane_coverage': lane_coverage,
        'query_family_coverage': query_family_coverage,
        'overall': {
            'planned_lanes': len(lane_coverage),
            'executed_lanes': 0,
            'covered_lanes': 0,
            'gap_disclosed_lanes': 0,
            'bounded_lanes': 0,
            'below_target_lanes': 0,
            'total_sources': 0,
            'total_evidence': 0,
            'status': 'planned',
        },
    }


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init_run(args: argparse.Namespace) -> None:
    """Create run_manifest.json and empty JSONL artifact files."""
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    artifact_paths = {
        'sources': 'sources.jsonl',
        'evidence': 'evidence.jsonl',
        'claims': 'claims.jsonl',
        'file_manifest': 'file_manifest.jsonl',
        'data_profile': 'data_profile.jsonl',
        'report': 'report.md',
        'plan': 'plan.json',
        'coverage_map': 'coverage_map.json',
        'audit_manifest': 'audit_manifest.json',
        'ledger_index': INDEX_FILENAME,
    }

    started_at = utc_now()
    plan = attach_plan_checkpoint(
        default_plan_for_mode(args.mode, args.query or ''),
        interactive=bool(args.interactive),
        created_at=started_at,
    )
    coverage_map = initial_coverage_map(plan)
    manifest = {
        'version': '3.0.0',
        'query': args.query or '',
        'mode': args.mode,
        'started_at': started_at,
        'finished_at': None,
        'assumptions': [],
        'provider_config': {
            'primary': 'native-web-search',
            'wide_discovery': 'search-as-code',
            'follow_up': 'perplexity-search-mcp',
            'scholarly': 'semantic_scholar' if env_var_present('S2_API_KEY') else None,
        },
        'report_dir': out_dir,
        'artifact_paths': artifact_paths,
        'continuation': None,
        'execution_trace': {
            'version': '1.0',
            'provider_calls': [],
            'subagents': [],
            'lane_source_counts': {},
            'query_family_source_counts': {},
            'phase_metrics': {},
            'events': [
                {
                    'event_id': 'evt_init_run',
                    'phase': 'init',
                    'status': 'ok',
                    'created_at': started_at,
                    'message': 'Run initialized with plan.json and coverage_map.json skeletons.',
                },
                {
                    'event_id': 'evt_plan_checkpoint',
                    'phase': 'plan_checkpoint',
                    'status': plan['checkpoint']['status'],
                    'created_at': started_at,
                    'message': (
                        'Interactive run paused for plan.json review before retrieval.'
                        if args.interactive
                        else 'Headless run marked plan checkpoint skipped_headless.'
                    ),
                }
            ],
        },
    }

    manifest_path = os.path.join(out_dir, 'run_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')
    write_json(os.path.join(out_dir, artifact_paths['plan']), plan)
    write_json(os.path.join(out_dir, artifact_paths['coverage_map']), coverage_map)

    # Create empty artifact files
    for name in ('sources', 'evidence', 'claims', 'file_manifest', 'data_profile'):
        p = os.path.join(out_dir, artifact_paths[name])
        if not os.path.exists(p):
            open(p, 'w').close()

    save_index(out_dir, build_ledger_index(out_dir, (SOURCE_LEDGER, EVIDENCE_LEDGER)))

    print(json.dumps({'status': 'ok', 'manifest': manifest_path, 'dir': out_dir}))


def source_row_from_data(data: dict) -> tuple[dict | None, dict | None]:
    """Return a normalized source row or an error object for batch reporting."""
    raw_url = data.get('raw_url', data.get('url', ''))
    if not raw_url:
        return None, {'error': 'raw_url is required'}

    canonical = data.get('canonical_locator') or canonicalize_locator(raw_url)
    source_id = compute_source_id(canonical)
    source = {
        'source_id': source_id,
        'canonical_locator': canonical,
        'raw_url': raw_url,
        'title': data.get('title', ''),
        'authors': data.get('authors'),
        'year': data.get('year'),
        'source_type': data.get('source_type', 'web'),
        'source_tier': data.get('source_tier'),
        'document_date': data.get('document_date'),
        'retrieved_at': data.get('retrieved_at'),
        'provider_ids': data.get('provider_ids'),
        'venue': data.get('venue'),
        'citation_count': data.get('citation_count'),
        'influential_citation_count': data.get('influential_citation_count'),
        'open_access_pdf_url': data.get('open_access_pdf_url'),
        'metadata_status': data.get('metadata_status', 'unverified'),
        'editorial_notice_status': data.get('editorial_notice_status'),
        'scite_checked_at': data.get('scite_checked_at'),
        'registered_at': datetime.now(timezone.utc).isoformat(),
    }
    return source, None


def cmd_register_source(args: argparse.Namespace) -> None:
    """Register a source, append to sources.jsonl, print source_id."""
    data = json.loads(args.json)
    source, error = source_row_from_data(data)
    if error:
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)

    assert source is not None
    source_id = source['source_id']
    canonical = source['canonical_locator']

    sources_path = os.path.join(args.dir, 'sources.jsonl')
    index = load_or_build_index(args.dir, (SOURCE_LEDGER,))
    if source_id in source_ids_from_index(index):
        print(json.dumps({
            'status': 'duplicate',
            'source_id': source_id,
            'canonical_locator': canonical,
        }))
        return

    append_jsonl(sources_path, source)
    add_source_to_index(index, source)
    refresh_ledger_signature(index, args.dir, SOURCE_LEDGER)
    save_index(args.dir, index)
    print(json.dumps({
        'status': 'registered',
        'source_id': source_id,
        'canonical_locator': canonical,
    }))


def cmd_register_sources(args: argparse.Namespace) -> None:
    """Register a JSONL batch of sources with one ledger read and one append."""
    input_rows, errors = read_jsonl_input(args.jsonl)

    sources_path = os.path.join(args.dir, 'sources.jsonl')
    index = load_or_build_index(args.dir, (SOURCE_LEDGER,))
    known_source_ids = source_ids_from_index(index)
    batch_source_ids: set[str] = set()
    additions: list[dict] = []
    duplicates: list[str] = []

    for row_no, data in input_rows:
        source, error = source_row_from_data(data)
        if error:
            errors.append({'line': row_no, **error})
            continue
        assert source is not None
        source_id = source['source_id']
        if source_id in known_source_ids or source_id in batch_source_ids:
            duplicates.append(source_id)
            continue
        additions.append(source)
        batch_source_ids.add(source_id)

    append_jsonl_many(sources_path, additions)
    for source in additions:
        add_source_to_index(index, source)
    refresh_ledger_signature(index, args.dir, SOURCE_LEDGER)
    save_index(args.dir, index)

    payload = {
        'status': 'ok' if not errors else 'partial',
        'rows_read': len(input_rows) + len(errors),
        'registered': len(additions),
        'duplicates': len(duplicates),
        'errors': errors,
        'source_ids': [source['source_id'] for source in additions],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if errors and args.strict:
        sys.exit(1)


def cmd_build_index(args: argparse.Namespace) -> None:
    """Rebuild the persisted ledger index from current JSONL artifacts."""
    index = build_ledger_index(args.dir, (SOURCE_LEDGER, EVIDENCE_LEDGER))
    path = save_index(args.dir, index)
    print(json.dumps({
        'status': 'ok',
        'path': path,
        'sources': index['sources']['count'],
        'evidence': index['evidence']['count'],
    }))


def cmd_add_assumption(args: argparse.Namespace) -> None:
    """Persist or update one research assumption in run_manifest.json."""
    manifest_path = os.path.join(args.dir, 'run_manifest.json')
    manifest = read_json(manifest_path)
    if not manifest:
        print(json.dumps({'error': 'run_manifest.json not found', 'path': manifest_path}), file=sys.stderr)
        sys.exit(1)

    assumption_id = args.assumption_id or compute_assumption_id(args.text)
    assumption = {
        'assumption_id': assumption_id,
        'text': args.text.strip(),
        'materiality': args.materiality,
        'status': args.status,
    }

    assumptions = manifest.setdefault('assumptions', [])
    for idx, existing in enumerate(assumptions):
        if existing.get('assumption_id') == assumption_id:
            assumptions[idx] = assumption
            write_json(manifest_path, manifest)
            print(json.dumps({'status': 'updated', 'assumption': assumption}))
            return

    assumptions.append(assumption)
    write_json(manifest_path, manifest)
    print(json.dumps({'status': 'added', 'assumption': assumption}))


def cmd_finish_run(args: argparse.Namespace) -> None:
    """Stamp run_manifest.finished_at and append a completion trace event."""
    manifest_path = os.path.join(args.dir, 'run_manifest.json')
    manifest = read_json(manifest_path)
    if not manifest:
        print(json.dumps({'error': 'run_manifest.json not found', 'path': manifest_path}), file=sys.stderr)
        sys.exit(1)

    finished_at = args.finished_at or utc_now()
    manifest['finished_at'] = finished_at
    trace = ensure_execution_trace(manifest)
    events = trace['events']
    event = {
        'event_id': f'evt_finish_run_{len(events) + 1}',
        'phase': 'finish_run',
        'status': 'ok',
        'created_at': finished_at,
        'message': args.note or 'Run marked finished after delivery validation.',
    }
    if args.report:
        event['report'] = args.report
    events.append(event)
    write_json(manifest_path, manifest)
    print(json.dumps({
        'status': 'ok',
        'finished_at': finished_at,
        'manifest': manifest_path,
    }))


def split_brief_items(values: list[str] | None) -> list[str]:
    """Normalize repeated CLI values and pipe-delimited lists."""
    items: list[str] = []
    for value in values or []:
        for part in str(value).split('|'):
            item = part.strip()
            if item:
                items.append(item)
    return items


def render_bullet_section(title: str, items: list[str]) -> list[str]:
    lines = [f'## {title}', '']
    if items:
        lines.extend(f'- {item}' for item in items)
    else:
        lines.append('- Not specified.')
    lines.append('')
    return lines


def cmd_write_brief(args: argparse.Namespace) -> None:
    """Write a headless Research Brief artifact from manifest assumptions."""
    manifest_path = os.path.join(args.dir, 'run_manifest.json')
    manifest = read_json(manifest_path)
    if not manifest:
        print(json.dumps({'error': 'run_manifest.json not found', 'path': manifest_path}), file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(args.dir, 'research_brief.md')
    if not os.path.isabs(output_path):
        output_path = os.path.join(args.dir, output_path)

    scope_in = split_brief_items(args.scope_in)
    scope_out = split_brief_items(args.scope_out)
    open_questions = split_brief_items(args.open_question)
    assumptions = manifest.get('assumptions') or []

    lines = [
        '# Research Brief',
        '',
        f'**Query:** {manifest.get("query", "").strip() or "Not specified."}',
        f'**Mode:** {manifest.get("mode", "standard")}',
        f'**Generated:** {datetime.now(timezone.utc).isoformat()}',
        '',
    ]
    lines.extend(render_bullet_section('Scope In', scope_in))
    lines.extend(render_bullet_section('Scope Out', scope_out))
    lines.extend(render_bullet_section('Open Questions', open_questions))
    lines.extend(['## Assumptions', ''])
    if assumptions:
        lines.extend([
            '| ID | Materiality | Status | Assumption |',
            '| --- | --- | --- | --- |',
        ])
        for assumption in assumptions:
            text = str(assumption.get('text', '')).replace('|', '\\|')
            lines.append(
                f'| {assumption.get("assumption_id", "")} '
                f'| {assumption.get("materiality", "")} '
                f'| {assumption.get("status", "")} '
                f'| {text} |'
            )
    else:
        lines.append('- None recorded.')
    lines.extend([
        '',
        '## Retrieval Implications',
        '',
        '- Validate high-materiality assumptions before treating them as report facts.',
        '- Convert unresolved open questions into Phase 2 query families or explicit limitations.',
        '',
    ])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(json.dumps({'status': 'ok', 'brief': output_path}))


def cmd_assign_display_numbers(args: argparse.Namespace) -> None:
    """Read sources.jsonl, assign stable display numbers, optionally persist display_map.json."""
    sources_path = os.path.join(args.dir, 'sources.jsonl')
    sources = read_jsonl(sources_path)
    report_path = args.order_from_report
    if report_path and not os.path.isabs(report_path):
        report_path = os.path.join(args.dir, report_path)

    display_map = build_display_map(sources, report_path)
    mapping = display_map['source_id_to_display_number']

    if args.write:
        out_path = args.out or os.path.join(args.dir, 'display_map.json')
        write_json(out_path, display_map)

    print(json.dumps(mapping, indent=2))


def cmd_export_bibliography(args: argparse.Namespace) -> None:
    """Generate bibliography from sources.jsonl."""
    sources_path = os.path.join(args.dir, 'sources.jsonl')
    sources = read_jsonl(sources_path)

    # Deduplicate by source_id, preserve order
    seen = set()
    unique = []
    for src in sources:
        if src['source_id'] not in seen:
            seen.add(src['source_id'])
            unique.append(src)

    style = args.style

    if style == 'markdown':
        lines = ['## Bibliography', '']
        for i, src in enumerate(unique, 1):
            author_str = ''
            if src.get('authors'):
                authors = src['authors']
                if len(authors) == 1:
                    author_str = f'{authors[0]}. '
                elif len(authors) == 2:
                    author_str = f'{authors[0]} & {authors[1]}. '
                else:
                    author_str = f'{authors[0]} et al. '

            year_str = f'({src["year"]})' if src.get('year') else '(n.d.)'
            title = src.get('title', 'Untitled')
            url = src.get('raw_url', '')
            lines.append(f'[{i}] {author_str}{year_str}. [{title}]({url})')
        print('\n'.join(lines))

    elif style == 'json':
        out = []
        for i, src in enumerate(unique, 1):
            out.append({
                'display_number': i,
                'source_id': src['source_id'],
                'canonical_locator': src['canonical_locator'],
                'title': src.get('title', ''),
                'authors': src.get('authors'),
                'year': src.get('year'),
                'raw_url': src.get('raw_url', ''),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))

    else:
        print(f'Unknown style: {style}', file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='citation_manager',
        description='Stable source identity and run manifest management for deep-research v3.0',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # init-run
    p_init = sub.add_parser('init-run', help='Create run manifest and empty artifact files')
    p_init.add_argument('--out-dir', required=True, help='Output directory for the research run')
    p_init.add_argument('--query', default='', help='Original research question')
    p_init.add_argument('--mode', default='standard', choices=['quick', 'standard', 'deep', 'ultradeep'])
    p_init.add_argument(
        '--interactive',
        action='store_true',
        help='Write plan.json as ready_for_review so retrieval waits for approve-plan',
    )

    # register-source
    p_reg = sub.add_parser('register-source', help='Register a source and return its stable ID')
    p_reg.add_argument('--json', required=True, help='JSON object with at least raw_url and title')
    p_reg.add_argument('--dir', required=True, help='Run directory containing sources.jsonl')

    # register-sources
    p_reg_batch = sub.add_parser('register-sources', help='Register source rows from a JSONL file')
    p_reg_batch.add_argument('--jsonl', required=True, help='JSONL file with one source object per line')
    p_reg_batch.add_argument('--dir', required=True, help='Run directory containing sources.jsonl')
    p_reg_batch.add_argument('--strict', action='store_true', help='Exit nonzero if any batch row is malformed')

    # build-index
    p_index = sub.add_parser('build-index', help='Rebuild ledger_index.json from current ledgers')
    p_index.add_argument('--dir', required=True, help='Run directory containing sources/evidence JSONL ledgers')

    # add-assumption
    p_assume = sub.add_parser('add-assumption', help='Persist or update one assumption in run_manifest.json')
    p_assume.add_argument('--dir', required=True, help='Run directory containing run_manifest.json')
    p_assume.add_argument('--text', required=True, help='Assumption text to persist')
    p_assume.add_argument(
        '--materiality',
        default='medium',
        choices=['low', 'medium', 'high'],
        help='Expected impact if the assumption is wrong',
    )
    p_assume.add_argument(
        '--status',
        default='implicit',
        choices=['implicit', 'user_confirmed', 'evidence_validated'],
        help='How the assumption is currently supported',
    )
    p_assume.add_argument('--assumption-id', help='Optional asm_[8 hex] ID; defaults to text hash')

    # finish-run
    p_finish = sub.add_parser('finish-run', help='Stamp run_manifest.finished_at after validation')
    p_finish.add_argument('--dir', required=True, help='Run directory containing run_manifest.json')
    p_finish.add_argument('--finished-at', help='Optional ISO timestamp; defaults to current UTC time')
    p_finish.add_argument('--report', help='Optional final report path to record in the finish event')
    p_finish.add_argument('--note', help='Optional completion note for execution_trace.events')

    # write-brief
    p_brief = sub.add_parser('write-brief', help='Write research_brief.md from manifest assumptions')
    p_brief.add_argument('--dir', required=True, help='Run directory containing run_manifest.json')
    p_brief.add_argument('--output', help='Output path; defaults to research_brief.md in the run directory')
    p_brief.add_argument('--scope-in', action='append', help='Included scope item; repeat or use pipe separators')
    p_brief.add_argument('--scope-out', action='append', help='Excluded scope item; repeat or use pipe separators')
    p_brief.add_argument('--open-question', action='append', help='Open question; repeat or use pipe separators')

    # assign-display-numbers
    p_num = sub.add_parser('assign-display-numbers', help='Map stable source IDs to display numbers')
    p_num.add_argument('--dir', required=True, help='Run directory containing sources.jsonl')
    p_num.add_argument('--write', action='store_true', help='Persist display_map.json in the run directory')
    p_num.add_argument('--out', help='Optional output path for --write; defaults to display_map.json')
    p_num.add_argument('--order-from-report', help='Optional report path whose citation first-use order controls numbering')

    # export-bibliography
    p_bib = sub.add_parser('export-bibliography', help='Generate bibliography from sources')
    p_bib.add_argument('--dir', required=True, help='Run directory containing sources.jsonl')
    p_bib.add_argument('--style', default='markdown', choices=['markdown', 'json'])

    args = parser.parse_args()

    dispatch = {
        'init-run': cmd_init_run,
        'register-source': cmd_register_source,
        'register-sources': cmd_register_sources,
        'build-index': cmd_build_index,
        'add-assumption': cmd_add_assumption,
        'finish-run': cmd_finish_run,
        'write-brief': cmd_write_brief,
        'assign-display-numbers': cmd_assign_display_numbers,
        'export-bibliography': cmd_export_bibliography,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
