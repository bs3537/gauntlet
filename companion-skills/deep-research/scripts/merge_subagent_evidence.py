#!/usr/bin/env python3
"""
Merge subagent evidence handoff files into canonical deep-research ledgers.

Subagents write a handoff schema with source_url/source_title/evidence_quote.
The master gate expects sources.jsonl plus evidence.jsonl rows keyed by source_id.
This script registers/deduplicates sources first, then emits canonical evidence
rows that verify_claim_support.py can see through source_id/evidence_id indexes.
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

from citation_manager import canonicalize_locator, compute_source_id
from evidence_store import compute_evidence_id


VALID_SOURCE_TYPES = frozenset([
    'web', 'academic', 'documentation', 'code', 'news', 'government', 'book',
    'regulatory', 'sec_filing', 'clinical_trial', 'company_ir', 'conference',
    'financial_data',
])
VALID_SOURCE_TIERS = frozenset([
    'primary', 'high_quality_secondary', 'secondary', 'low_confidence',
])
VALID_EVIDENCE_TYPES = frozenset([
    'direct_quote', 'paraphrase', 'data_point', 'figure_reference', 'methodology',
])


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


def append_jsonl(path: str, row: dict) -> None:
    with open(path, 'a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_subagent_jsonl(path: str) -> tuple[list[dict], list[dict]]:
    rows = []
    errors = []
    with open(path) as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append({
                    'file': path,
                    'line': line_number,
                    'error': f'invalid json: {exc.msg}',
                })
                continue
            if not isinstance(payload, dict):
                errors.append({
                    'file': path,
                    'line': line_number,
                    'error': 'row must be a JSON object',
                })
                continue
            rows.append(payload)
    return rows, errors


def first_value(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return ''


def source_payload(row: dict) -> dict:
    source = row.get('source')
    return source if isinstance(source, dict) else {}


def first_source_value(row: dict, keys: tuple[str, ...]) -> str:
    return first_value(row, keys) or first_value(source_payload(row), keys)


def source_field(row: dict, key: str):
    if key in row and row.get(key) is not None:
        return row.get(key)
    return source_payload(row).get(key)


def clean_source_type(value: str) -> str:
    value = (value or '').strip()
    return value if value in VALID_SOURCE_TYPES else 'web'


def clean_source_tier(value: str) -> str | None:
    value = (value or '').strip()
    return value if value in VALID_SOURCE_TIERS else None


def clean_evidence_type(value: str) -> str:
    value = (value or '').strip()
    return value if value in VALID_EVIDENCE_TYPES else 'direct_quote'


def build_source_row(row: dict, now: str) -> tuple[dict | None, str | None]:
    raw_url = first_source_value(row, ('source_url', 'raw_url', 'url'))
    if not raw_url:
        return None, 'missing source_url'

    canonical = first_source_value(row, ('canonical_locator',)) or canonicalize_locator(raw_url)
    source_id = compute_source_id(canonical)
    title = first_source_value(row, ('source_title', 'title', 'source_name')) or raw_url

    source = {
        'source_id': source_id,
        'canonical_locator': canonical,
        'raw_url': raw_url,
        'title': title,
        'authors': source_field(row, 'authors'),
        'year': source_field(row, 'year'),
        'venue': source_field(row, 'venue'),
        'provider_ids': source_field(row, 'provider_ids'),
        'citation_count': source_field(row, 'citation_count'),
        'influential_citation_count': source_field(row, 'influential_citation_count'),
        'open_access_pdf_url': source_field(row, 'open_access_pdf_url'),
        'source_type': clean_source_type(first_source_value(row, ('source_type',))),
        'source_tier': clean_source_tier(first_source_value(row, ('source_tier',))),
        'document_date': source_field(row, 'document_date'),
        'retrieved_at': source_field(row, 'retrieved_at'),
        'metadata_status': source_field(row, 'metadata_status') or 'unverified',
        'registered_at': now,
    }
    return source, None


def source_id_for_row(row: dict, sources_by_id: dict[str, dict], now: str) -> tuple[str | None, dict | None, str | None]:
    explicit_source_id = first_value(row, ('source_id',))
    if explicit_source_id and explicit_source_id in sources_by_id:
        return explicit_source_id, None, None

    source, error = build_source_row(row, now)
    if error:
        return None, None, error
    return source['source_id'], source, None


def build_evidence_row(row: dict, source_id: str, now: str) -> tuple[dict | None, str | None]:
    quote = first_value(row, ('quote', 'evidence_quote', 'evidence_quote_or_span', 'snippet'))
    if not quote:
        return None, 'missing evidence_quote'

    locator = first_value(row, ('locator', 'location', 'page', 'section')) or None
    evidence_id = compute_evidence_id(source_id, quote, locator)
    retrieval_query = first_value(row, ('retrieval_query', 'query', 'claim')) or None
    captured_at = first_value(row, ('captured_at',)) or now

    evidence = {
        'evidence_id': evidence_id,
        'source_id': source_id,
        'retrieval_query': retrieval_query,
        'locator': locator,
        'quote': quote,
        'evidence_type': clean_evidence_type(first_value(row, ('evidence_type',))),
        'captured_at': captured_at,
    }
    for key in ('lane_id', 'query_family_id', 'provider', 'provider_call_id', 'subagent_id', 'subagent_role'):
        value = first_value(row, (key,))
        if value:
            evidence[key] = value
    return evidence, None


def discover_inputs(run_dir: str, subagent_dir: str | None, inputs: list[str]) -> list[str]:
    paths = []
    for path in inputs:
        paths.extend(glob.glob(path))
    if not paths:
        root = subagent_dir or os.path.join(run_dir, 'subagent_outputs')
        paths.extend(glob.glob(os.path.join(root, '*.evidence.jsonl')))
    return sorted({os.path.abspath(path) for path in paths if os.path.exists(path)})


DEFAULT_MIN_USABLE_RATIO = 0.8


def merge(
    run_dir: str,
    inputs: list[str],
    subagent_dir: str | None = None,
    min_usable_ratio: float = DEFAULT_MIN_USABLE_RATIO,
) -> dict:
    os.makedirs(run_dir, exist_ok=True)
    sources_path = os.path.join(run_dir, 'sources.jsonl')
    evidence_path = os.path.join(run_dir, 'evidence.jsonl')
    for path in (sources_path, evidence_path):
        if not os.path.exists(path):
            open(path, 'w').close()

    sources = read_jsonl(sources_path)
    evidence_rows = read_jsonl(evidence_path)
    sources_by_id = {row.get('source_id'): row for row in sources if row.get('source_id')}
    evidence_by_id = {row.get('evidence_id'): row for row in evidence_rows if row.get('evidence_id')}
    input_paths = discover_inputs(run_dir, subagent_dir, inputs)

    summary = {
        'status': 'ok',
        'files_processed': 0,
        'rows_read': 0,
        'sources_added': 0,
        'sources_reused': 0,
        'evidence_added': 0,
        'evidence_reused': 0,
        'rows_skipped': 0,
        'min_usable_ratio': min_usable_ratio,
        'files_below_threshold': 0,
        'per_file': [],
        'lane_source_counts': {},
        'query_family_source_counts': {},
        'errors': [],
    }
    lane_source_counts = Counter()
    query_family_source_counts = Counter()

    now = datetime.now(timezone.utc).isoformat()
    for path in input_paths:
        rows, errors = read_subagent_jsonl(path)
        summary['files_processed'] += 1
        summary['errors'].extend(errors)
        summary['rows_skipped'] += len(errors)

        # Per-file acceptance accounting. A lane that hands back mostly unusable
        # rows has not done the work, regardless of its own self-report, so the
        # caller must be able to see the ratio rather than a global total that a
        # healthy sibling lane can mask.
        file_rows_read = len(errors)
        file_rows_skipped = len(errors)
        file_rows_ok = 0

        for row in rows:
            summary['rows_read'] += 1
            file_rows_read += 1
            source_id, source, source_error = source_id_for_row(row, sources_by_id, now)
            if source_error:
                summary['rows_skipped'] += 1
                file_rows_skipped += 1
                summary['errors'].append({'file': path, 'error': source_error, 'row': row})
                continue

            if source_id in sources_by_id:
                summary['sources_reused'] += 1
            elif source:
                append_jsonl(sources_path, source)
                sources_by_id[source_id] = source
                summary['sources_added'] += 1

            evidence, evidence_error = build_evidence_row(row, source_id, now)
            if evidence_error:
                summary['rows_skipped'] += 1
                file_rows_skipped += 1
                summary['errors'].append({'file': path, 'error': evidence_error, 'row': row})
                continue

            file_rows_ok += 1
            if evidence['evidence_id'] in evidence_by_id:
                summary['evidence_reused'] += 1
                continue

            append_jsonl(evidence_path, evidence)
            evidence_by_id[evidence['evidence_id']] = evidence
            summary['evidence_added'] += 1
            if evidence.get('lane_id'):
                lane_source_counts[evidence['lane_id']] += 1
            if evidence.get('query_family_id'):
                query_family_source_counts[evidence['query_family_id']] += 1

        usable_ratio = (file_rows_ok / file_rows_read) if file_rows_read else 0.0
        zero_valid_rows = file_rows_ok == 0
        below_threshold = zero_valid_rows or usable_ratio < min_usable_ratio
        if below_threshold:
            summary['files_below_threshold'] += 1
        summary['per_file'].append({
            'file': path,
            'rows_read': file_rows_read,
            'rows_ok': file_rows_ok,
            'rows_skipped': file_rows_skipped,
            'usable_ratio': round(usable_ratio, 4),
            'zero_valid_rows': zero_valid_rows,
            'below_min_usable_ratio': below_threshold,
        })

    # A lane below the usable-row floor is a mechanical failure, not a judgment
    # call: the lead must record it as below_target/gap_disclosed rather than
    # covered. Row-level skips alone remain 'partial'.
    if summary['files_below_threshold']:
        summary['status'] = 'fail'
    elif summary['errors']:
        summary['status'] = 'partial'
    summary['lane_source_counts'] = dict(lane_source_counts)
    summary['query_family_source_counts'] = dict(query_family_source_counts)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='merge_subagent_evidence',
        description='Normalize subagent evidence handoff JSONL into sources.jsonl and evidence.jsonl',
    )
    parser.add_argument('--dir', required=True, help='Run directory containing sources.jsonl/evidence.jsonl')
    parser.add_argument('--input', action='append', default=[], help='Subagent evidence JSONL file or glob; may be repeated')
    parser.add_argument('--subagent-dir', default=None, help='Directory containing *.evidence.jsonl files; defaults to DIR/subagent_outputs')
    parser.add_argument('--strict', action='store_true', help='Exit nonzero if any row is malformed or skipped')
    parser.add_argument(
        '--min-usable-ratio',
        type=float,
        default=DEFAULT_MIN_USABLE_RATIO,
        help=(
            'Minimum accepted rows / read rows per input file before the lane counts as '
            f'a failed handoff (default {DEFAULT_MIN_USABLE_RATIO}). A file with zero valid '
            'rows always fails regardless of this value.'
        ),
    )
    args = parser.parse_args()

    summary = merge(os.path.abspath(args.dir), args.input, args.subagent_dir, args.min_usable_ratio)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.strict and (summary['errors'] or summary['files_below_threshold']):
        sys.exit(1)


if __name__ == '__main__':
    main()
