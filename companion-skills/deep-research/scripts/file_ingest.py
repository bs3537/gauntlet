#!/usr/bin/env python3
"""Local file ingestion for deep-research runs.

This CLI registers local PDFs, tables, text files, and images as sources, then
persists only evidence that was actually extracted. It never pretends OCR,
vision, or PDF text extraction happened when the local runtime lacks those
capabilities.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from citation_manager import (
    SOURCE_LEDGER,
    add_source_to_index,
    append_jsonl,
    load_or_build_index,
    refresh_ledger_signature,
    save_index,
    source_ids_from_index,
    source_row_from_data,
)
from evidence_store import (
    EVIDENCE_LEDGER,
    add_evidence_to_index,
    evidence_ids_from_index,
    evidence_row_from_data,
)


FILE_MANIFEST = 'file_manifest.jsonl'
DATA_PROFILE = 'data_profile.jsonl'
INGESTED_DIR = 'ingested_files'


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ensure_artifacts(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in (FILE_MANIFEST, DATA_PROFILE, 'sources.jsonl', 'evidence.jsonl'):
        path = run_dir / name
        if not path.exists():
            path.touch()
    (run_dir / INGESTED_DIR).mkdir(exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def detect_kind(path: Path, override: str = 'auto') -> str:
    if override != 'auto':
        return override
    ext = path.suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    if ext == '.csv':
        return 'csv'
    if ext in {'.tsv', '.tab'}:
        return 'tsv'
    if ext in {'.png', '.jpg', '.jpeg'}:
        return 'image'
    if ext in {'.txt', '.md', '.markdown'}:
        return 'text'
    return 'binary'


def source_type_for_kind(kind: str) -> str:
    return {
        'pdf': 'pdf',
        'csv': 'dataset',
        'tsv': 'dataset',
        'image': 'image',
        'text': 'local_file',
    }.get(kind, 'local_file')


def media_type_for(path: Path, kind: str) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return {
        'csv': 'text/csv',
        'tsv': 'text/tab-separated-values',
        'pdf': 'application/pdf',
        'image': 'image/*',
        'text': 'text/plain',
    }.get(kind, 'application/octet-stream')


def register_file_source(
    run_dir: Path,
    path: Path,
    file_hash: str,
    kind: str,
    title: str,
    source_tier: str | None,
) -> tuple[str, str]:
    data = {
        'raw_url': file_uri(path),
        'canonical_locator': f'file-sha256:{file_hash}',
        'title': title,
        'source_type': source_type_for_kind(kind),
        'source_tier': source_tier,
        'retrieved_at': utc_now(),
        'metadata_status': 'url_verified',
        'provider_ids': {'sha256': file_hash},
    }
    source, error = source_row_from_data(data)
    if error:
        raise ValueError(error['error'])
    assert source is not None

    index = load_or_build_index(str(run_dir), (SOURCE_LEDGER,))
    source_id = source['source_id']
    status = 'duplicate' if source_id in source_ids_from_index(index) else 'registered'
    if status == 'registered':
        append_jsonl(str(run_dir / 'sources.jsonl'), source)
        add_source_to_index(index, source)
        refresh_ledger_signature(index, str(run_dir), SOURCE_LEDGER)
        save_index(str(run_dir), index)
    return source_id, status


def add_evidence_rows(run_dir: Path, evidence_inputs: list[dict]) -> list[str]:
    if not evidence_inputs:
        return []
    index = load_or_build_index(str(run_dir), (EVIDENCE_LEDGER,))
    known = evidence_ids_from_index(index)
    added_rows = []
    added_ids = []
    for data in evidence_inputs:
        row, error = evidence_row_from_data(data)
        if error:
            raise ValueError(error['error'])
        assert row is not None
        evidence_id = row['evidence_id']
        if evidence_id in known:
            continue
        added_rows.append(row)
        added_ids.append(evidence_id)
        known.add(evidence_id)

    for row in added_rows:
        append_jsonl(str(run_dir / 'evidence.jsonl'), row)
        add_evidence_to_index(index, row)
    refresh_ledger_signature(index, str(run_dir), EVIDENCE_LEDGER)
    save_index(str(run_dir), index)
    return added_ids


def dedup_append_jsonl(path: Path, key: str, row: dict) -> bool:
    existing = {item.get(key) for item in read_jsonl(path)}
    if row.get(key) in existing:
        return False
    append_jsonl(str(path), row)
    return True


def numeric_profile(values: list[str]) -> dict | None:
    numbers = []
    for value in values:
        text = str(value).strip().replace(',', '')
        if not text:
            continue
        try:
            numbers.append(float(text))
        except ValueError:
            continue
    if not numbers:
        return None
    return {
        'count': len(numbers),
        'min': min(numbers),
        'max': max(numbers),
        'mean': sum(numbers) / len(numbers),
    }


def compact_number(value: float) -> str:
    return f'{value:.6g}'


def profile_table(path: Path, kind: str, file_id: str, source_id: str) -> tuple[dict, list[dict]]:
    delimiter = '\t' if kind == 'tsv' else ','
    with path.open(newline='', encoding='utf-8-sig') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
        except csv.Error:
            dialect = csv.excel_tab if kind == 'tsv' else csv.excel
            dialect.delimiter = delimiter
        reader = csv.DictReader(f, dialect=dialect)
        columns = reader.fieldnames or []
        rows = list(reader)

    row_count = len(rows)
    column_profiles: dict[str, dict] = {}
    for column in columns:
        profile = numeric_profile([row.get(column, '') for row in rows])
        if profile:
            column_profiles[column] = profile

    profile_row = {
        'version': '1.0',
        'file_id': file_id,
        'source_id': source_id,
        'profile_type': 'tabular',
        'row_count': row_count,
        'column_count': len(columns),
        'columns': columns,
        'numeric_columns': column_profiles,
        'sample_rows': rows[:5],
        'profiled_at': utc_now(),
    }

    evidence_inputs = [{
        'source_id': source_id,
        'quote': f"Dataset {path.name} contains {row_count} rows and {len(columns)} columns: {', '.join(columns)}.",
        'locator': 'table profile',
        'evidence_type': 'data_point',
        'provider': 'local_file_ingest',
    }]
    for column, stats in list(column_profiles.items())[:10]:
        evidence_inputs.append({
            'source_id': source_id,
            'quote': (
                f"Column '{column}' has {stats['count']} numeric values with "
                f"min {compact_number(stats['min'])}, max {compact_number(stats['max'])}, "
                f"mean {compact_number(stats['mean'])}."
            ),
            'locator': f'column:{column}',
            'evidence_type': 'data_point',
            'provider': 'local_file_ingest',
        })
    return profile_row, evidence_inputs


def text_chunks(text: str, limit: int) -> list[str]:
    chunks = []
    current = []
    current_len = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if current and current_len + len(line) > 700:
            chunks.append(' '.join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
        if len(chunks) >= limit:
            break
    if current and len(chunks) < limit:
        chunks.append(' '.join(current))
    return chunks[:limit]


def extract_text_file(path: Path, limit: int) -> tuple[str, list[str]]:
    text = path.read_text(encoding='utf-8', errors='replace')
    return text, text_chunks(text, limit)


def extract_pdf_text(path: Path, limit: int) -> tuple[str | None, list[str], str | None]:
    pdftotext = shutil.which('pdftotext')
    if not pdftotext:
        return None, [], 'pdftotext_unavailable'
    result = subprocess.run(
        [pdftotext, '-layout', str(path), '-'],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None, [], 'pdftotext_failed'
    text = result.stdout
    return text, text_chunks(text, limit), None


def png_dimensions(path: Path) -> dict | None:
    with path.open('rb') as f:
        header = f.read(24)
    if len(header) >= 24 and header[:8] == b'\x89PNG\r\n\x1a\n':
        width, height = struct.unpack('>II', header[16:24])
        return {'width': width, 'height': height}
    return None


def jpeg_dimensions(path: Path) -> dict | None:
    with path.open('rb') as f:
        if f.read(2) != b'\xff\xd8':
            return None
        while True:
            marker_start = f.read(1)
            if marker_start != b'\xff':
                return None
            marker = f.read(1)
            while marker == b'\xff':
                marker = f.read(1)
            if marker in {b'\xc0', b'\xc1', b'\xc2', b'\xc3'}:
                length = struct.unpack('>H', f.read(2))[0]
                data = f.read(length - 2)
                if len(data) >= 5:
                    height, width = struct.unpack('>HH', data[1:5])
                    return {'width': width, 'height': height}
                return None
            length_bytes = f.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack('>H', length_bytes)[0]
            f.seek(length - 2, os.SEEK_CUR)


def image_metadata(path: Path) -> dict:
    lower = path.suffix.lower()
    dimensions = png_dimensions(path) if lower == '.png' else None
    if dimensions is None and lower in {'.jpg', '.jpeg'}:
        dimensions = jpeg_dimensions(path)
    return dimensions or {}


def write_extracted_text(run_dir: Path, file_id: str, text: str) -> str:
    out_path = run_dir / INGESTED_DIR / f'{file_id}.txt'
    out_path.write_text(text, encoding='utf-8')
    return str(out_path)


def cmd_ingest(args: argparse.Namespace) -> None:
    run_dir = Path(args.dir).resolve()
    path = Path(args.file).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(json.dumps({'error': 'file not found', 'path': str(path)}), file=sys.stderr)
        sys.exit(1)

    ensure_artifacts(run_dir)
    kind = detect_kind(path, args.kind)
    file_hash = sha256_file(path)
    file_id = f'file_{file_hash[:12]}'
    title = args.title or path.name
    source_id, source_status = register_file_source(
        run_dir,
        path,
        file_hash,
        kind,
        title,
        args.source_tier,
    )

    actions_required: list[str] = []
    artifacts: dict[str, str] = {}
    data_profile_written = False
    extraction_status = 'registered'
    evidence_inputs: list[dict[str, Any]] = []

    if kind in {'csv', 'tsv'}:
        profile, table_evidence = profile_table(path, kind, file_id, source_id)
        data_profile_written = dedup_append_jsonl(run_dir / DATA_PROFILE, 'file_id', profile)
        evidence_inputs.extend(table_evidence)
        extraction_status = 'parsed'
    elif kind == 'text':
        text, chunks = extract_text_file(path, args.max_text_evidence)
        artifacts['extracted_text'] = write_extracted_text(run_dir, file_id, text)
        for index, chunk in enumerate(chunks, start=1):
            evidence_inputs.append({
                'source_id': source_id,
                'quote': chunk,
                'locator': f'text chunk {index}',
                'evidence_type': 'direct_quote',
                'provider': 'local_file_ingest',
            })
        extraction_status = 'text_extracted'
    elif kind == 'pdf':
        text, chunks, error = extract_pdf_text(path, args.max_text_evidence)
        if text:
            artifacts['extracted_text'] = write_extracted_text(run_dir, file_id, text)
            for index, chunk in enumerate(chunks, start=1):
                evidence_inputs.append({
                    'source_id': source_id,
                    'quote': chunk,
                    'locator': f'pdf text chunk {index}',
                    'evidence_type': 'direct_quote',
                    'provider': 'local_file_ingest',
                })
            extraction_status = 'text_extracted'
        else:
            extraction_status = 'registered_needs_pdf_text'
            actions_required.append(error or 'pdf_text_extraction_required')
    elif kind == 'image':
        metadata = image_metadata(path)
        if metadata:
            artifacts['image_dimensions'] = json.dumps(metadata, sort_keys=True)
        extraction_status = 'registered_needs_vision_ocr'
        actions_required.append('vision_or_ocr_required')
    else:
        extraction_status = 'registered_unsupported_binary'
        actions_required.append('unsupported_binary_requires_manual_extraction')

    for row in evidence_inputs:
        if args.lane_id:
            row['lane_id'] = args.lane_id
        if args.query_family_id:
            row['query_family_id'] = args.query_family_id

    evidence_ids = add_evidence_rows(run_dir, evidence_inputs)

    stat = path.stat()
    manifest_row = {
        'version': '1.0',
        'file_id': file_id,
        'source_id': source_id,
        'file_path': str(path),
        'file_uri': file_uri(path),
        'filename': path.name,
        'sha256': file_hash,
        'size_bytes': stat.st_size,
        'modified_at': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        'ingested_at': utc_now(),
        'file_kind': kind,
        'media_type': media_type_for(path, kind),
        'extraction_status': extraction_status,
        'actions_required': actions_required,
        'artifacts': artifacts,
    }
    manifest_written = dedup_append_jsonl(run_dir / FILE_MANIFEST, 'file_id', manifest_row)

    payload = {
        'status': 'ok' if not actions_required else 'needs_followup',
        'file_id': file_id,
        'source_id': source_id,
        'source_status': source_status,
        'file_kind': kind,
        'extraction_status': extraction_status,
        'actions_required': actions_required,
        'manifest_written': manifest_written,
        'data_profile_written': data_profile_written,
        'evidence_added': len(evidence_ids),
        'evidence_ids': evidence_ids,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.strict and actions_required:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Ingest local files into deep-research ledgers')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_ingest = sub.add_parser('ingest', help='Register a local file and extract safe evidence when possible')
    p_ingest.add_argument('--dir', required=True, help='Run directory containing sources/evidence ledgers')
    p_ingest.add_argument('--file', required=True, help='Local file path')
    p_ingest.add_argument('--kind', default='auto', choices=['auto', 'pdf', 'csv', 'tsv', 'image', 'text', 'binary'])
    p_ingest.add_argument('--title', help='Source title; defaults to filename')
    p_ingest.add_argument('--source-tier', choices=['primary', 'high_quality_secondary', 'secondary', 'low_confidence'])
    p_ingest.add_argument('--lane-id')
    p_ingest.add_argument('--query-family-id')
    p_ingest.add_argument('--max-text-evidence', type=int, default=5)
    p_ingest.add_argument('--strict', action='store_true', help='Exit nonzero when follow-up extraction is required')
    p_ingest.set_defaults(func=cmd_ingest)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
