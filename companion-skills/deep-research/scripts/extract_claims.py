#!/usr/bin/env python3
"""
Atomic Claim Extractor — decomposes report sections into typed claims.

CLI subcommands:
  extract      Parse a markdown report into atomic claims (claims.jsonl)
  add          Manually add a single claim
  list         List claims, optionally filtered by section or type
  stats        Show claim statistics (counts by type/status)

Claim identity:
  claim_id = sha256(section_id + normalized_text)[:16]

Claim types (per GPT Pro's refinement of Codex's proposal):
  - factual: hard-fails on lack of support
  - synthesis: needs traceability, softer threshold
  - recommendation: needs traceability, softer threshold
  - speculation: labeled, no support gate
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Claim ID computation
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')


def normalize_text(text: str) -> str:
    """Normalize for stable hashing."""
    return _WHITESPACE_RE.sub(' ', text.strip()).lower()


def compute_claim_id(section_id: str, text: str) -> str:
    """sha256(section_id + normalized_text)[:16] hex."""
    payload = section_id + normalize_text(text)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def append_jsonl(path: str, obj: dict) -> None:
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
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


def read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Report parsing helpers
# ---------------------------------------------------------------------------

# Section header patterns
SECTION_PATTERNS = [
    (re.compile(r'^##\s+Executive\s+Summary', re.I), 'executive_summary'),
    (re.compile(r'^##\s+Introduction', re.I), 'introduction'),
    (re.compile(r'^##\s+Finding\s+(\d+)', re.I), lambda m: f'finding_{m.group(1)}'),
    (re.compile(r'^##\s+Synthesis', re.I), 'synthesis'),
    (re.compile(r'^##\s+Limitations', re.I), 'limitations'),
    (re.compile(r'^##\s+Recommendations', re.I), 'recommendations'),
    (re.compile(r'^##\s+Conclusion', re.I), 'conclusion'),
    (re.compile(r'^##\s+(.+)', re.I), lambda m: re.sub(r'\W+', '_', m.group(1).strip().lower())[:30]),
]

# Citation pattern [N], [S12], [E4], or comma-separated numeric labels.
CITATION_RE = re.compile(r'\[((?:[SE]?\d+)(?:,\s*(?:[SE]?\d+))*)\]')

# Sentence splitting (basic but handles abbreviations)
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

# Markdown table separator row, e.g. |---|:---:|---:|
TABLE_SEPARATOR_CELL_RE = re.compile(r':?-{3,}:?')
VALID_CLAIM_TYPES = frozenset(['factual', 'synthesis', 'recommendation', 'speculation'])
INVESTMENT_DOMAINS = frozenset([
    'clinical', 'regulatory', 'financial', 'commercial',
    'competitive', 'scientific', 'market',
])
TABLE_FIELD_ALIASES = {
    'ticker': ('ticker', 'symbol'),
    'company': ('company', 'issuer'),
    'asset': ('asset', 'drug', 'product', 'program'),
    'indication': ('indication', 'disease', 'setting'),
    'source_tier': ('source tier', 'tier'),
    'source_name': ('source name', 'source'),
    'source_url': ('source url', 'url', 'link'),
    'document_date': ('document date', 'date'),
    'retrieved_at': ('retrieved at', 'retrieved'),
    'evidence_quote_or_span': ('evidence quote or span', 'evidence span', 'evidence quote', 'quote'),
    'status': ('status', 'verification status'),
    'investment_relevance': ('investment relevance', 'relevance'),
    'notes': ('notes', 'note'),
}


def normalize_citation_label(raw_label: str) -> str:
    """Return the numeric display label from labels like 1, S1, or E1."""
    label = str(raw_label or '').strip().strip('[]').upper()
    if label.startswith(('S', 'E')):
        label = label[1:]
    return label


def extract_citation_labels(text: str) -> list[str]:
    """Extract normalized citation labels from a sentence."""
    labels: list[str] = []
    for match in CITATION_RE.finditer(text):
        for raw_label in match.group(1).split(','):
            label = normalize_citation_label(raw_label)
            if label.isdigit():
                labels.append(label)
    return labels


def clean_inline_markdown(text: str) -> str:
    """Remove lightweight inline Markdown while preserving citation labels."""
    text = re.sub(r'<br\s*/?>', '; ', text, flags=re.I)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)
    return _WHITESPACE_RE.sub(' ', text).strip()


def split_markdown_table_row(line: str) -> list[str]:
    """Split a Markdown table row, preserving escaped pipes inside cells."""
    stripped = line.strip()
    if '|' not in stripped:
        return []
    if stripped.startswith('|'):
        stripped = stripped[1:]
    if stripped.endswith('|') and not stripped.endswith(r'\|'):
        stripped = stripped[:-1]

    cells = []
    current = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == '|':
            cells.append(clean_inline_markdown(''.join(current)))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append('\\')
    cells.append(clean_inline_markdown(''.join(current)))
    return cells


def is_table_separator(line: str) -> bool:
    """Return True for Markdown table alignment/separator rows."""
    cells = split_markdown_table_row(line)
    if len(cells) < 2:
        return False
    return all(TABLE_SEPARATOR_CELL_RE.fullmatch(cell.replace(' ', '')) for cell in cells)


def normalize_table_header(header: str, index: int) -> str:
    """Return a usable column label for table-derived claim context."""
    header = clean_inline_markdown(header).strip(': ')
    return header or f'Column {index + 1}'


def iter_markdown_tables(text: str) -> list[dict]:
    """Return Markdown table blocks with headers, rows, and source line numbers."""
    lines = text.split('\n')
    tables = []
    i = 0
    while i < len(lines) - 1:
        header_cells = split_markdown_table_row(lines[i])
        if len(header_cells) < 2 or not is_table_separator(lines[i + 1]):
            i += 1
            continue

        rows = []
        j = i + 2
        while j < len(lines):
            row_cells = split_markdown_table_row(lines[j])
            if not row_cells or is_table_separator(lines[j]):
                break
            if any(cell.strip() for cell in row_cells):
                rows.append({'line_number': j + 1, 'cells': row_cells})
            j += 1

        if rows:
            tables.append({
                'line_number': i + 1,
                'headers': header_cells,
                'rows': rows,
            })
        i = max(j, i + 1)
    return tables


def strip_markdown_tables(text: str) -> str:
    """Remove Markdown table blocks before sentence extraction."""
    lines = text.split('\n')
    kept = []
    i = 0
    while i < len(lines):
        if i < len(lines) - 1 and len(split_markdown_table_row(lines[i])) >= 2 and is_table_separator(lines[i + 1]):
            i += 2
            while i < len(lines) and split_markdown_table_row(lines[i]):
                i += 1
            kept.append('')
            continue
        kept.append(lines[i])
        i += 1
    return '\n'.join(kept)


def table_cell_map(headers: list[str], cells: list[str]) -> dict[str, str]:
    """Map normalized table headers to non-empty cell values."""
    max_columns = max(len(headers), len(cells))
    mapped = {}
    used = set()
    for index in range(max_columns):
        value = cells[index].strip() if index < len(cells) else ''
        if not value:
            continue
        header = normalize_table_header(headers[index] if index < len(headers) else '', index)
        key = header
        if key in used:
            key = f'{header} {index + 1}'
        used.add(key)
        mapped[key] = value
    return mapped


def table_row_claim_text(headers: list[str], cells: list[str]) -> tuple[str, dict[str, str]]:
    """Convert one Markdown table row into a compact, self-contained claim."""
    mapped = table_cell_map(headers, cells)
    parts = [f'{header}: {value}' for header, value in mapped.items()]
    text = '; '.join(parts)
    if text and text[-1] not in '.!?':
        text += '.'
    return text, mapped


def normalized_header_key(header: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', header.lower()).strip()


def table_cell_by_alias(cells: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    aliases = tuple(normalized_header_key(alias) for alias in aliases)
    for header, value in cells.items():
        if normalized_header_key(header) in aliases and value:
            return value
    return None


def derive_table_claim_metadata(cells: dict[str, str]) -> dict:
    """Derive schema-compatible optional metadata from recognized table columns."""
    metadata: dict = {}
    for field, aliases in TABLE_FIELD_ALIASES.items():
        value = table_cell_by_alias(cells, aliases)
        if value:
            metadata[field] = value

    claim_domain = table_cell_by_alias(cells, ('claim domain', 'domain'))
    if claim_domain and claim_domain.lower() in INVESTMENT_DOMAINS:
        metadata['claim_domain'] = claim_domain.lower()

    claim_role = table_cell_by_alias(cells, ('claim role', 'role'))
    claim_type = table_cell_by_alias(cells, ('claim type', 'type'))
    if claim_role and claim_role.lower() in VALID_CLAIM_TYPES:
        metadata['claim_type'] = claim_role.lower()
    elif claim_type and claim_type.lower() in VALID_CLAIM_TYPES:
        metadata['claim_type'] = claim_type.lower()
    elif claim_type and claim_type.lower() in INVESTMENT_DOMAINS:
        metadata['claim_domain'] = claim_type.lower()

    return metadata


def should_extract_table_claim(text: str, cells: dict[str, str]) -> bool:
    """Filter structural/noise rows while keeping table facts without citations."""
    if len(normalize_text(text)) <= 30:
        return False
    if extract_citation_labels(text):
        return True
    if re.search(r'\b\d+(?:\.\d+)?(?:%|x|X)?\b', text):
        return True
    return sum(1 for value in cells.values() if len(value) >= 4) >= 2


def extract_table_claims(text: str) -> list[dict]:
    """Extract row-level claims from Markdown tables."""
    claims = []
    for table_index, table in enumerate(iter_markdown_tables(text), start=1):
        headers = [normalize_table_header(header, index) for index, header in enumerate(table['headers'])]
        for row_index, row in enumerate(table['rows'], start=1):
            claim_text, cells = table_row_claim_text(headers, row['cells'])
            if not should_extract_table_claim(claim_text, cells):
                continue
            claims.append({
                'text': claim_text,
                **derive_table_claim_metadata(cells),
                '_extraction_method': 'table_row',
                '_table_index': table_index,
                '_table_row_index': row_index,
                '_table_line_number': row['line_number'],
                '_table_headers': headers,
                '_table_cells': cells,
            })
    return claims


def build_source_display_index(run_dir: str) -> dict[str, str]:
    """Map display labels such as 1/S1/E1 to stable source_id values."""
    sources_path = os.path.join(run_dir, 'sources.jsonl')
    sources = read_jsonl(sources_path)
    source_ids = {
        source.get('source_id') or source.get('id')
        for source in sources
        if source.get('source_id') or source.get('id')
    }
    index: dict[str, str] = {}

    display_map = read_json(os.path.join(run_dir, 'display_map.json'))
    map_sources = []
    if display_map.get('label_source') == 'report':
        map_sources.extend([
            display_map.get('label_to_source_id') or {},
            display_map.get('display_number_to_source_id') or {},
            display_map.get('source_alias_to_source_id') or {},
        ])
    else:
        map_sources.extend([
            display_map.get('display_number_to_source_id') or {},
            display_map.get('label_to_source_id') or {},
            display_map.get('source_alias_to_source_id') or {},
        ])
    for mapping in map_sources:
        for label, source_id in mapping.items():
            normalized = normalize_citation_label(label)
            if normalized and source_id in source_ids:
                index.setdefault(normalized, source_id)

    # Fallback for runs created before display_map.json: explicit labels first,
    # then registration-order ordinals.
    for ordinal, source in enumerate(sources, start=1):
        source_id = source.get('source_id') or source.get('id')
        if not source_id:
            continue
        labels = [
            str(source.get('display_id') or ''),
            str(source.get('display_number') or ''),
            str(source.get('num') or ''),
        ]
        for label in labels:
            normalized = normalize_citation_label(label)
            if normalized:
                index.setdefault(normalized, source_id)
    for ordinal, source in enumerate(sources, start=1):
        source_id = source.get('source_id') or source.get('id')
        if source_id:
            index.setdefault(str(ordinal), source_id)
    return index


def build_evidence_ids_by_source(run_dir: str) -> dict[str, list[str]]:
    """Map source_id to evidence_id values for source-linked claim support."""
    evidence_path = os.path.join(run_dir, 'evidence.jsonl')
    by_source: dict[str, list[str]] = {}
    for evidence in read_jsonl(evidence_path):
        source_id = evidence.get('source_id')
        evidence_id = evidence.get('evidence_id')
        if not source_id or not evidence_id:
            continue
        by_source.setdefault(source_id, [])
        if evidence_id not in by_source[source_id]:
            by_source[source_id].append(evidence_id)
    return by_source


def classify_claim(text: str, section_id: str) -> str:
    """Heuristic claim type classification."""
    lower = text.lower()

    # Recommendation indicators
    if any(w in lower for w in ['should', 'recommend', 'suggest', 'advise', 'consider']):
        if section_id == 'recommendations':
            return 'recommendation'
        return 'recommendation'

    # Speculation indicators
    if any(w in lower for w in ['might', 'could potentially', 'it is possible', 'may eventually',
                                 'hypothetically', 'speculatively']):
        return 'speculation'

    # Synthesis indicators (often in synthesis/conclusion sections)
    if section_id in ('synthesis', 'conclusion', 'limitations'):
        if any(w in lower for w in ['overall', 'taken together', 'collectively',
                                     'the evidence suggests', 'this implies']):
            return 'synthesis'

    # Default: factual
    return 'factual'


def parse_sections(markdown: str) -> list[tuple[str, str]]:
    """Parse markdown into (section_id, content) pairs."""
    lines = markdown.split('\n')
    sections = []
    current_id = 'preamble'
    current_lines = []

    for line in lines:
        matched = False
        for pattern, id_or_fn in SECTION_PATTERNS:
            m = pattern.match(line)
            if m:
                if current_lines:
                    sections.append((current_id, '\n'.join(current_lines)))
                current_id = id_or_fn(m) if callable(id_or_fn) else id_or_fn
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)

    if current_lines:
        sections.append((current_id, '\n'.join(current_lines)))

    return sections


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering noise."""
    # Remove markdown formatting noise
    text = re.sub(r'^[-*]\s+', '', text, flags=re.M)  # bullet points
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # italic

    sentences = SENTENCE_RE.split(text)
    result = []
    for s in sentences:
        s = s.strip()
        # Filter out very short fragments, headings, empty lines
        if len(s) > 30 and not s.startswith('#') and not s.startswith('|'):
            result.append(s)
    return result


def merge_unique(existing: list, new_values: list) -> list:
    merged = list(existing or [])
    for value in new_values or []:
        if value not in merged:
            merged.append(value)
    return merged


def merge_claim(existing: dict, candidate: dict) -> bool:
    """Merge newly extracted metadata into an existing stable claim row."""
    changed = False

    for key in ('cited_source_ids', 'evidence_ids', '_citation_labels', '_citation_numbers'):
        merged = merge_unique(existing.get(key, []), candidate.get(key, []))
        if merged != existing.get(key, []):
            existing[key] = merged
            changed = True

    for key in (
        'claim_domain', 'ticker', 'company', 'asset', 'indication', 'source_tier',
        'source_name', 'source_url', 'document_date', 'retrieved_at',
        'evidence_quote_or_span', 'status', 'investment_relevance', 'notes',
        '_extraction_method', '_table_index', '_table_row_index',
        '_table_line_number', '_table_headers', '_table_cells',
    ):
        if key in candidate and not existing.get(key):
            existing[key] = candidate[key]
            changed = True

    if existing.get('claim_type') not in VALID_CLAIM_TYPES and candidate.get('claim_type') in VALID_CLAIM_TYPES:
        existing['claim_type'] = candidate['claim_type']
        changed = True

    return changed


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_extract(args: argparse.Namespace) -> None:
    """Extract atomic claims from a markdown report."""
    report_path = args.report
    if not os.path.exists(report_path):
        print(json.dumps({'error': f'Report not found: {report_path}'}), file=sys.stderr)
        sys.exit(1)

    with open(report_path) as f:
        markdown = f.read()

    claims_path = os.path.join(args.dir, 'claims.jsonl')
    claims = read_jsonl(claims_path)
    existing_by_id = {r['claim_id']: r for r in claims if r.get('claim_id')}
    existing_ids = set(existing_by_id)

    source_index = build_source_display_index(args.dir)
    evidence_by_source = build_evidence_ids_by_source(args.dir)
    sections = parse_sections(markdown)
    added = 0
    skipped = 0
    updated = 0

    for section_id, content in sections:
        if section_id == 'preamble':
            continue
        claim_items = [
            {'text': sentence}
            for sentence in extract_sentences(strip_markdown_tables(content))
        ]
        claim_items.extend(extract_table_claims(content))

        for item in claim_items:
            sentence = item['text']
            claim_id = compute_claim_id(section_id, sentence)

            citation_labels = extract_citation_labels(sentence)
            cited_source_ids = []
            evidence_ids = []
            for label in citation_labels:
                source_id = source_index.get(label)
                if not source_id or source_id in cited_source_ids:
                    continue
                cited_source_ids.append(source_id)
                evidence_ids.extend(evidence_by_source.get(source_id, []))

            claim = {
                'claim_id': claim_id,
                'section_id': section_id,
                'text': sentence,
                'claim_type': item.get('claim_type') or classify_claim(sentence, section_id),
                'cited_source_ids': cited_source_ids,
                'evidence_ids': sorted(set(evidence_ids)),
                'support_status': 'unverified',
                'extracted_at': datetime.now(timezone.utc).isoformat(),
                '_citation_numbers': [int(label) for label in citation_labels],
                '_citation_labels': citation_labels,
            }
            for key in (
                'claim_domain', 'ticker', 'company', 'asset', 'indication',
                'source_tier', 'source_name', 'source_url', 'document_date',
                'retrieved_at', 'evidence_quote_or_span', 'status',
                'investment_relevance', 'notes',
                '_extraction_method', '_table_index', '_table_row_index',
                '_table_line_number', '_table_headers', '_table_cells',
            ):
                if key in item:
                    claim[key] = item[key]

            if claim_id in existing_by_id:
                skipped += 1
                if merge_claim(existing_by_id[claim_id], claim):
                    updated += 1
                continue

            claims.append(claim)
            existing_by_id[claim_id] = claim
            existing_ids.add(claim_id)
            added += 1

    write_jsonl(claims_path, claims)
    print(json.dumps({
        'status': 'ok',
        'claims_added': added,
        'claims_skipped': skipped,
        'claims_updated': updated,
        'total_claims': len(existing_ids),
    }))


def cmd_add(args: argparse.Namespace) -> None:
    """Manually add a single claim."""
    data = json.loads(args.json)
    section_id = data.get('section_id', 'unknown')
    text = data.get('text') or data.get('claim', '')
    if not text:
        print(json.dumps({'error': 'text is required'}), file=sys.stderr)
        sys.exit(1)

    claim_id = compute_claim_id(section_id, text)
    claims_path = os.path.join(args.dir, 'claims.jsonl')

    existing = read_jsonl(claims_path)
    for row in existing:
        if row.get('claim_id') == claim_id:
            print(json.dumps({'status': 'duplicate', 'claim_id': claim_id}))
            return

    valid_types = {'factual', 'synthesis', 'recommendation', 'speculation'}
    investment_domains = {'clinical', 'regulatory', 'financial', 'commercial', 'competitive', 'scientific', 'market'}
    claim_type = data.get('claim_type', 'factual')
    claim_domain = data.get('claim_domain')
    if claim_type in investment_domains and not claim_domain:
        claim_domain = claim_type
        claim_type = data.get('claim_role', 'factual')
    if claim_type not in valid_types:
        claim_type = 'factual'

    claim = {
        'claim_id': claim_id,
        'section_id': section_id,
        'text': text,
        'claim_type': claim_type,
        'claim_domain': claim_domain,
        'cited_source_ids': data.get('cited_source_ids', []),
        'evidence_ids': data.get('evidence_ids', []),
        'support_status': 'unverified',
        'extracted_at': datetime.now(timezone.utc).isoformat(),
    }
    for key in (
        'ticker', 'company', 'asset', 'indication', 'source_tier',
        'source_name', 'source_url', 'document_date', 'retrieved_at',
        'evidence_quote_or_span', 'status', 'investment_relevance', 'notes'
    ):
        if key in data:
            claim[key] = data[key]
    append_jsonl(claims_path, claim)
    print(json.dumps({'status': 'added', 'claim_id': claim_id}))


def cmd_list(args: argparse.Namespace) -> None:
    """List claims with optional filters."""
    claims_path = os.path.join(args.dir, 'claims.jsonl')
    rows = read_jsonl(claims_path)

    if args.section:
        rows = [r for r in rows if r.get('section_id') == args.section]
    if args.type:
        rows = [r for r in rows if r.get('claim_type') == args.type]
    if args.status:
        rows = [r for r in rows if r.get('support_status') == args.status]

    # Deduplicate
    seen = set()
    unique = []
    for r in rows:
        cid = r.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(r)

    print(json.dumps({'count': len(unique), 'claims': unique}, indent=2, ensure_ascii=False))


def cmd_stats(args: argparse.Namespace) -> None:
    """Show claim statistics."""
    claims_path = os.path.join(args.dir, 'claims.jsonl')
    rows = read_jsonl(claims_path)

    # Deduplicate
    seen = set()
    unique = []
    for r in rows:
        cid = r.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(r)

    by_type = {}
    by_status = {}
    by_section = {}
    for r in unique:
        t = r.get('claim_type', 'unknown')
        s = r.get('support_status', 'unknown')
        sec = r.get('section_id', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1
        by_section[sec] = by_section.get(sec, 0) + 1

    print(json.dumps({
        'total': len(unique),
        'by_type': by_type,
        'by_status': by_status,
        'by_section': by_section,
    }, indent=2))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='extract_claims',
        description='Atomic claim extraction and ledger for deep-research v3.0',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # extract
    p_ext = sub.add_parser('extract', help='Extract claims from markdown report')
    p_ext.add_argument('--report', required=True, help='Path to report.md')
    p_ext.add_argument('--dir', required=True, help='Run directory containing claims.jsonl')

    # add
    p_add = sub.add_parser('add', help='Manually add a single claim')
    p_add.add_argument('--json', required=True, help='JSON with section_id, text/claim, claim_type or claim_domain')
    p_add.add_argument('--dir', required=True, help='Run directory')

    # list
    p_list = sub.add_parser('list', help='List claims')
    p_list.add_argument('--dir', required=True, help='Run directory')
    p_list.add_argument('--section', default=None, help='Filter by section_id')
    p_list.add_argument('--type', default=None, help='Filter by claim_type')
    p_list.add_argument('--status', default=None, help='Filter by support_status')

    # stats
    p_stats = sub.add_parser('stats', help='Claim statistics')
    p_stats.add_argument('--dir', required=True, help='Run directory')

    args = parser.parse_args()
    dispatch = {
        'extract': cmd_extract,
        'add': cmd_add,
        'list': cmd_list,
        'stats': cmd_stats,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
