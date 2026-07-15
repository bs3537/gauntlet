#!/usr/bin/env python3
"""
Evidence Store — append-only evidence persistence for deep-research v3.0.

CLI subcommands:
  init         Create empty evidence.jsonl in a run directory
  add          Append an evidence row, return evidence_id
  add-batch    Append evidence rows from a JSONL file
  list         List evidence rows, optionally filtered by source_id
  export       Export evidence as JSON array

Evidence identity:
  evidence_id = sha256(source_id + normalized_quote + locator)[:16]

All state is append-only JSONL. Evidence is never modified after capture.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from ledger_index import (
    EVIDENCE_LEDGER,
    add_evidence_to_index,
    build_ledger_index,
    evidence_ids_from_index,
    load_or_build_index,
    refresh_ledger_signature,
    save_index,
)


# ---------------------------------------------------------------------------
# Evidence ID computation
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')


def normalize_quote(quote: str) -> str:
    """Normalize whitespace for stable hashing."""
    return _WHITESPACE_RE.sub(' ', quote.strip()).lower()


def compute_evidence_id(source_id: str, quote: str, locator: str | None) -> str:
    """sha256(source_id + normalized_quote + locator)[:16] hex."""
    payload = source_id + normalize_quote(quote) + (locator or '')
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL helpers (shared pattern with citation_manager)
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


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    """Create empty evidence.jsonl if it doesn't exist."""
    out_dir = os.path.abspath(args.dir)
    path = os.path.join(out_dir, 'evidence.jsonl')
    if not os.path.exists(path):
        os.makedirs(out_dir, exist_ok=True)
        open(path, 'w').close()
    index = build_ledger_index(out_dir, (EVIDENCE_LEDGER,))
    save_index(out_dir, index)
    print(json.dumps({'status': 'ok', 'path': path}))


def evidence_row_from_data(data: dict) -> tuple[dict | None, dict | None]:
    source_id = data.get('source_id', '')
    quote = data.get('quote', '')
    if not source_id or not quote:
        return None, {'error': 'source_id and quote are required'}

    locator = data.get('locator')
    evidence_id = compute_evidence_id(source_id, quote, locator)
    valid_types = {'direct_quote', 'paraphrase', 'data_point', 'figure_reference', 'methodology'}
    evidence_type = data.get('evidence_type', 'direct_quote')
    if evidence_type not in valid_types:
        evidence_type = 'direct_quote'

    row = {
        'evidence_id': evidence_id,
        'source_id': source_id,
        'retrieval_query': data.get('retrieval_query'),
        'locator': locator,
        'quote': quote,
        'evidence_type': evidence_type,
        'captured_at': datetime.now(timezone.utc).isoformat(),
    }
    for key in (
        'lane_id',
        'query_family_id',
        'provider',
        'provider_call_id',
        'subagent_id',
        'subagent_role',
    ):
        if key in data:
            row[key] = data.get(key)
    return row, None


def cmd_add(args: argparse.Namespace) -> None:
    """Append evidence row, print evidence_id."""
    data = json.loads(args.json)
    row, error = evidence_row_from_data(data)
    if error:
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)

    assert row is not None
    evidence_id = row['evidence_id']
    source_id = row['source_id']
    evidence_path = os.path.join(args.dir, 'evidence.jsonl')

    index = load_or_build_index(args.dir, (EVIDENCE_LEDGER,))
    if evidence_id in evidence_ids_from_index(index):
        print(json.dumps({
            'status': 'duplicate',
            'evidence_id': evidence_id,
        }))
        return

    append_jsonl(evidence_path, row)
    add_evidence_to_index(index, row)
    refresh_ledger_signature(index, args.dir, EVIDENCE_LEDGER)
    save_index(args.dir, index)
    print(json.dumps({
        'status': 'added',
        'evidence_id': evidence_id,
        'source_id': source_id,
    }))


def cmd_add_batch(args: argparse.Namespace) -> None:
    """Append evidence rows from JSONL with one ledger-index load."""
    input_rows, errors = read_jsonl_input(args.jsonl)
    evidence_path = os.path.join(args.dir, 'evidence.jsonl')
    index = load_or_build_index(args.dir, (EVIDENCE_LEDGER,))
    known_evidence_ids = evidence_ids_from_index(index)
    batch_evidence_ids: set[str] = set()
    additions: list[dict] = []
    duplicates: list[str] = []

    for row_no, data in input_rows:
        row, error = evidence_row_from_data(data)
        if error:
            errors.append({'line': row_no, **error})
            continue
        assert row is not None
        evidence_id = row['evidence_id']
        if evidence_id in known_evidence_ids or evidence_id in batch_evidence_ids:
            duplicates.append(evidence_id)
            continue
        additions.append(row)
        batch_evidence_ids.add(evidence_id)

    append_jsonl_many(evidence_path, additions)
    for row in additions:
        add_evidence_to_index(index, row)
    refresh_ledger_signature(index, args.dir, EVIDENCE_LEDGER)
    save_index(args.dir, index)

    payload = {
        'status': 'ok' if not errors else 'partial',
        'rows_read': len(input_rows) + len(errors),
        'added': len(additions),
        'duplicates': len(duplicates),
        'errors': errors,
        'evidence_ids': [row['evidence_id'] for row in additions],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if errors and args.strict:
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    """List evidence rows, optionally filtered."""
    evidence_path = os.path.join(args.dir, 'evidence.jsonl')
    rows = read_jsonl(evidence_path)

    if args.source_id:
        rows = [r for r in rows if r.get('source_id') == args.source_id]

    # Deduplicate by evidence_id
    seen = set()
    unique = []
    for r in rows:
        eid = r.get('evidence_id')
        if eid not in seen:
            seen.add(eid)
            unique.append(r)

    print(json.dumps({
        'count': len(unique),
        'evidence': unique,
    }, indent=2, ensure_ascii=False))


def cmd_export(args: argparse.Namespace) -> None:
    """Export all evidence as JSON array."""
    evidence_path = os.path.join(args.dir, 'evidence.jsonl')
    rows = read_jsonl(evidence_path)

    # Deduplicate
    seen = set()
    unique = []
    for r in rows:
        eid = r.get('evidence_id')
        if eid not in seen:
            seen.add(eid)
            unique.append(r)

    print(json.dumps(unique, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='evidence_store',
        description='Append-only evidence persistence for deep-research v3.0',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # init
    p_init = sub.add_parser('init', help='Create empty evidence.jsonl')
    p_init.add_argument('--dir', required=True, help='Run directory')

    # add
    p_add = sub.add_parser('add', help='Append evidence row')
    p_add.add_argument('--json', required=True, help='JSON with source_id, quote, locator, evidence_type, retrieval_query')
    p_add.add_argument('--dir', required=True, help='Run directory containing evidence.jsonl')

    # add-batch
    p_add_batch = sub.add_parser('add-batch', help='Append evidence rows from a JSONL file')
    p_add_batch.add_argument('--jsonl', required=True, help='JSONL file with one evidence object per line')
    p_add_batch.add_argument('--dir', required=True, help='Run directory containing evidence.jsonl')
    p_add_batch.add_argument('--strict', action='store_true', help='Exit nonzero if any batch row is malformed')

    # list
    p_list = sub.add_parser('list', help='List evidence rows')
    p_list.add_argument('--dir', required=True, help='Run directory')
    p_list.add_argument('--source-id', default=None, help='Filter by source_id')

    # export
    p_export = sub.add_parser('export', help='Export all evidence as JSON array')
    p_export.add_argument('--dir', required=True, help='Run directory')

    args = parser.parse_args()

    dispatch = {
        'init': cmd_init,
        'add': cmd_add,
        'add-batch': cmd_add_batch,
        'list': cmd_list,
        'export': cmd_export,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
