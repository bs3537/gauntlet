#!/usr/bin/env python3
"""Small persisted indexes for append-only deep-research ledgers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


INDEX_FILENAME = 'ledger_index.json'
SOURCE_LEDGER = 'sources.jsonl'
EVIDENCE_LEDGER = 'evidence.jsonl'
SUPPORTED_LEDGERS = (SOURCE_LEDGER, EVIDENCE_LEDGER)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def index_path(run_dir: str) -> str:
    return os.path.join(run_dir, INDEX_FILENAME)


def ledger_path(run_dir: str, ledger_name: str) -> str:
    return os.path.join(run_dir, ledger_name)


def read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ledger_signature(run_dir: str, ledger_name: str) -> dict:
    path = ledger_path(run_dir, ledger_name)
    if not os.path.exists(path):
        return {'exists': False, 'size': 0, 'mtime_ns': None}
    stat = os.stat(path)
    return {
        'exists': True,
        'size': stat.st_size,
        'mtime_ns': stat.st_mtime_ns,
    }


def empty_index() -> dict:
    return {
        'version': '1.0',
        'generated_at': utc_now(),
        'ledgers': {},
        'sources': {
            'count': 0,
            'source_ids': [],
            'source_id_by_canonical_locator': {},
        },
        'evidence': {
            'count': 0,
            'evidence_ids': [],
            'evidence_ids_by_source_id': {},
        },
    }


def load_index(run_dir: str) -> dict:
    path = index_path(run_dir)
    if not os.path.exists(path):
        return empty_index()
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return empty_index()
    base = empty_index()
    base.update(data)
    base.setdefault('ledgers', {})
    base.setdefault('sources', empty_index()['sources'])
    base.setdefault('evidence', empty_index()['evidence'])
    return base


def save_index(run_dir: str, index: dict) -> str:
    os.makedirs(run_dir, exist_ok=True)
    path = index_path(run_dir)
    index['generated_at'] = utc_now()
    with open(path, 'w') as f:
        json.dump(index, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')
    return path


def _dedup_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def rebuild_sources_section(run_dir: str, index: dict) -> dict:
    rows = read_jsonl(ledger_path(run_dir, SOURCE_LEDGER))
    source_ids: list[str] = []
    canonical_map: dict[str, str] = {}
    for row in rows:
        source_id = row.get('source_id') or row.get('id')
        if not source_id:
            continue
        source_ids.append(source_id)
        canonical = row.get('canonical_locator')
        if canonical:
            canonical_map.setdefault(canonical, source_id)
    unique_ids = _dedup_ordered(source_ids)
    index['sources'] = {
        'count': len(unique_ids),
        'source_ids': unique_ids,
        'source_id_by_canonical_locator': canonical_map,
    }
    index.setdefault('ledgers', {})[SOURCE_LEDGER] = ledger_signature(run_dir, SOURCE_LEDGER)
    return index


def rebuild_evidence_section(run_dir: str, index: dict) -> dict:
    rows = read_jsonl(ledger_path(run_dir, EVIDENCE_LEDGER))
    evidence_ids: list[str] = []
    by_source: dict[str, list[str]] = {}
    for row in rows:
        evidence_id = row.get('evidence_id')
        if not evidence_id:
            continue
        evidence_ids.append(evidence_id)
        source_id = row.get('source_id')
        if source_id:
            by_source.setdefault(source_id, []).append(evidence_id)
    unique_ids = _dedup_ordered(evidence_ids)
    index['evidence'] = {
        'count': len(unique_ids),
        'evidence_ids': unique_ids,
        'evidence_ids_by_source_id': {
            source_id: _dedup_ordered(ids)
            for source_id, ids in by_source.items()
        },
    }
    index.setdefault('ledgers', {})[EVIDENCE_LEDGER] = ledger_signature(run_dir, EVIDENCE_LEDGER)
    return index


def rebuild_ledger(index: dict, run_dir: str, ledger_name: str) -> dict:
    if ledger_name == SOURCE_LEDGER:
        return rebuild_sources_section(run_dir, index)
    if ledger_name == EVIDENCE_LEDGER:
        return rebuild_evidence_section(run_dir, index)
    raise ValueError(f'unsupported ledger for index: {ledger_name}')


def build_ledger_index(run_dir: str, ledgers: tuple[str, ...] = SUPPORTED_LEDGERS) -> dict:
    index = empty_index()
    for ledger_name in ledgers:
        rebuild_ledger(index, run_dir, ledger_name)
    return index


def load_or_build_index(run_dir: str, ledgers: tuple[str, ...] = SUPPORTED_LEDGERS) -> dict:
    index = load_index(run_dir)
    changed = False
    for ledger_name in ledgers:
        expected = ledger_signature(run_dir, ledger_name)
        if index.get('ledgers', {}).get(ledger_name) != expected:
            rebuild_ledger(index, run_dir, ledger_name)
            changed = True
    if changed or not os.path.exists(index_path(run_dir)):
        save_index(run_dir, index)
    return index


def refresh_ledger_signature(index: dict, run_dir: str, ledger_name: str) -> None:
    index.setdefault('ledgers', {})[ledger_name] = ledger_signature(run_dir, ledger_name)


def source_ids_from_index(index: dict) -> set[str]:
    return set(index.get('sources', {}).get('source_ids') or [])


def evidence_ids_from_index(index: dict) -> set[str]:
    return set(index.get('evidence', {}).get('evidence_ids') or [])


def add_source_to_index(index: dict, source: dict) -> None:
    sources = index.setdefault('sources', {
        'count': 0,
        'source_ids': [],
        'source_id_by_canonical_locator': {},
    })
    source_id = source.get('source_id')
    if not source_id:
        return
    source_ids = _dedup_ordered([*(sources.get('source_ids') or []), source_id])
    sources['source_ids'] = source_ids
    sources['count'] = len(source_ids)
    canonical = source.get('canonical_locator')
    if canonical:
        sources.setdefault('source_id_by_canonical_locator', {})[canonical] = source_id


def add_evidence_to_index(index: dict, evidence: dict) -> None:
    evidence_section = index.setdefault('evidence', {
        'count': 0,
        'evidence_ids': [],
        'evidence_ids_by_source_id': {},
    })
    evidence_id = evidence.get('evidence_id')
    if not evidence_id:
        return
    evidence_ids = _dedup_ordered([*(evidence_section.get('evidence_ids') or []), evidence_id])
    evidence_section['evidence_ids'] = evidence_ids
    evidence_section['count'] = len(evidence_ids)
    source_id = evidence.get('source_id')
    if source_id:
        by_source = evidence_section.setdefault('evidence_ids_by_source_id', {})
        by_source[source_id] = _dedup_ordered([*(by_source.get(source_id) or []), evidence_id])
