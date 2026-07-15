#!/usr/bin/env python3
"""
Claim-Support Verification — checks whether evidence supports claims.

CLI subcommands:
  verify       Check all claims against evidence, update support_status
  report       Generate a support verification summary

Version 1 is deterministic and cheap: entity, number, date, and
lexical-overlap checks over stored evidence. No LLM calls.

Only factual claims hard-fail in strict mode, and strict mode blocks any
factual claim that is unsupported, needs review, or only partially supported.
Synthesis/recommendation need traceability but softer thresholds.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

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


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# Support verification logic
# ---------------------------------------------------------------------------

# Extract numbers (integers and decimals)
NUMBER_RE = re.compile(r'\b\d+(?:\.\d+)?(?:%|x|X)?\b')

# Extract full year-like numbers
YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')

# Extract capitalized entities (naive NER)
ENTITY_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')

# Common stop entities to ignore
STOP_ENTITIES = frozenset([
    'The', 'This', 'That', 'These', 'However', 'Furthermore',
    'Moreover', 'Additionally', 'Therefore', 'Nevertheless',
])

INVESTMENT_DOMAINS = frozenset([
    'clinical', 'regulatory', 'financial', 'commercial',
    'competitive', 'scientific', 'market',
])
STRICT_BLOCKING_STATUSES = frozenset(['unsupported', 'needs_review', 'partial'])
EVIDENCE_TEXT_FIELDS = ('quote', 'evidence_quote', 'evidence_quote_or_span')

NEGATION_CUES = frozenset([
    'absent', 'absence', 'fail', 'failed', 'fails', 'failure', 'lack',
    'lacked', 'lacking', 'lacks', 'negative', 'never', 'no', 'none',
    'nor', 'not', 'without',
])
NEGATION_PHRASES = (
    'did not', 'does not', 'do not', 'was not', 'were not', 'is not',
    'are not', 'no evidence', 'not statistically significant', 'failed to',
    'fails to', 'fail to', 'failure to',
)
UP_CUES = frozenset([
    'achieved', 'benefit', 'beneficial', 'gain', 'gained', 'grew',
    'growth', 'higher', 'improve', 'improved', 'improves', 'improving',
    'increase', 'increased', 'increases', 'increasing', 'met', 'positive',
    'rise', 'rises', 'rose', 'superior',
])
DOWN_CUES = frozenset([
    'decline', 'declined', 'declines', 'decrease', 'decreased',
    'decreases', 'decreasing', 'drop', 'dropped', 'fall', 'falls', 'fell',
    'lower', 'miss', 'missed', 'misses', 'reduced', 'reduces', 'reduction',
    'worse', 'worsen', 'worsened', 'worsening',
])
CLAUSE_SPLIT_RE = re.compile(
    r'(?:[.;:]\s+|,\s*(?:but|while|whereas|although|though|however)\s+|\b(?:but|while|whereas|although|though|however)\b)',
    re.IGNORECASE,
)


def get_claim_role(claim: dict) -> str:
    """Return factual/synthesis/recommendation/speculation even for investment-domain ledgers."""
    claim_type = claim.get('claim_type', 'factual')
    if claim_type in INVESTMENT_DOMAINS:
        return claim.get('claim_role', 'factual')
    return claim_type


def evidence_quote(evidence: dict) -> str:
    """Return the best available evidence text across local and Search-as-Code ledgers."""
    for key in EVIDENCE_TEXT_FIELDS:
        value = str(evidence.get(key) or '').strip()
        if value:
            return value
    return ''


def has_support_waiver(claim: dict) -> bool:
    """Allow explicit human waivers without weakening default strict mode."""
    return bool(
        claim.get('support_waiver')
        or claim.get('allow_partial_support')
        or claim.get('support_status_waiver')
    )


def is_blocking_factual(claim: dict) -> bool:
    """Return True when strict verification should block delivery."""
    return (
        get_claim_role(claim) == 'factual'
        and claim.get('support_status') in STRICT_BLOCKING_STATUSES
        and not has_support_waiver(claim)
    )


def extract_tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens (>3 chars)."""
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    return set(words)


def extract_word_tokens(text: str) -> set[str]:
    """Extract lowercase word tokens for polarity and direction checks."""
    return set(re.findall(r"\b[a-z]+(?:'[a-z]+)?\b", text.lower()))


def extract_numbers(text: str) -> set[str]:
    """Extract numeric values."""
    return set(NUMBER_RE.findall(text))


def extract_years(text: str) -> set[str]:
    """Extract year mentions."""
    return set(YEAR_RE.findall(text))


def extract_entities(text: str) -> set[str]:
    """Extract capitalized entity mentions."""
    ents = set(ENTITY_RE.findall(text))
    return ents - STOP_ENTITIES


def has_negation(text: str) -> bool:
    lower = re.sub(r'\s+', ' ', text.lower())
    if any(phrase in lower for phrase in NEGATION_PHRASES):
        return True
    return bool(extract_word_tokens(text) & NEGATION_CUES)


def direction_cues(text: str) -> set[str]:
    words = extract_word_tokens(text)
    cues = set()
    if words & UP_CUES:
        cues.add('up')
    if words & DOWN_CUES:
        cues.add('down')
    return cues


def split_clauses(text: str) -> list[str]:
    """Split evidence into coarse clauses so guards do not overreact to unrelated clauses."""
    clauses = []
    for part in CLAUSE_SPLIT_RE.split(text):
        clause = part.strip(' ,;:.')
        if clause:
            clauses.append(clause)
    return clauses or [text]


def best_matching_clause(claim_text: str, evidence_text: str) -> str:
    """Return the evidence clause with the strongest lexical overlap to the claim."""
    claim_tokens = extract_tokens(claim_text)
    claim_words = extract_word_tokens(claim_text)
    best_clause = evidence_text
    best_score = -1.0

    for clause in split_clauses(evidence_text):
        clause_tokens = extract_tokens(clause)
        clause_words = extract_word_tokens(clause)
        token_score = len(claim_tokens & clause_tokens) / max(len(claim_tokens), 1)
        word_score = len(claim_words & clause_words) / max(len(claim_words), 1)
        score = max(token_score, word_score)
        if score > best_score:
            best_clause = clause
            best_score = score

    return best_clause


def contradiction_notes(claim_text: str, evidence_text: str) -> list[str]:
    """Return conservative lexical warnings for polarity/direction mismatches."""
    evidence_scope = best_matching_clause(claim_text, evidence_text)
    notes = []
    if has_negation(claim_text) != has_negation(evidence_scope):
        notes.append('negation mismatch')

    claim_direction = direction_cues(claim_text)
    evidence_direction = direction_cues(evidence_scope)
    if (
        ('up' in claim_direction and 'down' in evidence_direction and 'up' not in evidence_direction)
        or ('down' in claim_direction and 'up' in evidence_direction and 'down' not in evidence_direction)
    ):
        notes.append('direction mismatch')

    return notes


def weighted_feature_score(components: list[tuple[float, float]]) -> float:
    """Normalize over only claim features that are actually present."""
    active_weight = sum(weight for weight, _ in components)
    if not active_weight:
        return 0.0
    weighted_sum = sum(weight * score for weight, score in components)
    return weighted_sum / active_weight


def compute_support_score(claim_text: str, evidence_quotes: list[str]) -> tuple[str, float, str]:
    """
    Compute support status for a claim given its linked evidence quotes.

    Returns (status, score, notes).
    Score range: 0.0 (no overlap) to 1.0 (strong support).
    """
    if not evidence_quotes:
        return ('unsupported', 0.0, 'no evidence linked')

    claim_tokens = extract_tokens(claim_text)
    claim_numbers = extract_numbers(claim_text)
    claim_years = extract_years(claim_text)
    claim_entities = extract_entities(claim_text)

    best_score = -1.0
    best_notes = []
    relevant_guard_notes = []

    for quote in evidence_quotes:
        ev_tokens = extract_tokens(quote)
        ev_numbers = extract_numbers(quote)
        ev_years = extract_years(quote)
        ev_entities = extract_entities(quote)
        guard_notes = contradiction_notes(claim_text, quote)

        # Token overlap (Jaccard-like)
        if claim_tokens:
            token_overlap = len(claim_tokens & ev_tokens) / len(claim_tokens)
        else:
            token_overlap = 0.0

        # Number match
        if claim_numbers:
            number_match = len(claim_numbers & ev_numbers) / len(claim_numbers)
        else:
            number_match = None

        # Year match
        if claim_years:
            year_match = len(claim_years & ev_years) / len(claim_years)
        else:
            year_match = None

        # Entity match
        if claim_entities:
            entity_match = len(claim_entities & ev_entities) / len(claim_entities)
        else:
            entity_match = None

        # Weighted composite over present claim features only. Missing numbers,
        # years, or entities should not award free support credit.
        components = []
        if claim_tokens:
            components.append((0.4, token_overlap))
        if claim_numbers:
            components.append((0.25, number_match))
        if claim_years:
            components.append((0.15, year_match))
        if claim_entities:
            components.append((0.2, entity_match))
        score = weighted_feature_score(components)

        if score >= 0.35:
            for note in guard_notes:
                if note not in relevant_guard_notes:
                    relevant_guard_notes.append(note)

        if score > best_score:
            best_score = score
            best_notes = []
            if token_overlap < 0.3:
                best_notes.append('low lexical overlap')
            if claim_numbers and number_match < 0.5:
                best_notes.append('number mismatch')
            if claim_years and year_match < 1.0:
                best_notes.append('year mismatch')
            if claim_entities and entity_match < 0.3:
                best_notes.append('entity mismatch')
            best_notes.extend(guard_notes)

    # Threshold decision
    if best_score >= 0.6:
        status = 'supported'
    elif best_score >= 0.35:
        status = 'partial'
    else:
        status = 'needs_review'

    if relevant_guard_notes:
        status = 'needs_review'
        for note in relevant_guard_notes:
            if note not in best_notes:
                best_notes.append(note)

    notes = '; '.join(best_notes) if best_notes else 'adequate overlap'
    return (status, round(max(best_score, 0.0), 3), notes)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> None:
    """Verify all claims against evidence, update claims.jsonl."""
    claims_path = os.path.join(args.dir, 'claims.jsonl')
    evidence_path = os.path.join(args.dir, 'evidence.jsonl')
    sources_path = os.path.join(args.dir, 'sources.jsonl')

    claims = read_jsonl(claims_path)
    evidence = read_jsonl(evidence_path)
    sources = read_jsonl(sources_path)

    # Build evidence index by source_id and evidence_id.
    ev_by_source: dict[str, list[str]] = {}
    ev_by_id: dict[str, dict] = {}
    for ev in evidence:
        sid = ev.get('source_id', '')
        eid = ev.get('evidence_id', '')
        quote = evidence_quote(ev)
        if sid and quote:
            ev_by_source.setdefault(sid, []).append(quote)
        if eid:
            ev_by_id[eid] = ev

    # Deduplicate claims
    seen = set()
    unique_claims = []
    for c in claims:
        cid = c.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique_claims.append(c)

    verified = 0
    updated_claims = []

    for claim in unique_claims:
        claim_type = get_claim_role(claim)

        # Gather evidence for this claim
        cited_ids = claim.get('cited_source_ids', [])
        evidence_ids = claim.get('evidence_ids', [])

        # Collect evidence quotes from linked evidence_ids
        quotes = []
        for eid in evidence_ids:
            if eid in ev_by_id:
                quote = evidence_quote(ev_by_id[eid])
                if quote:
                    quotes.append(quote)

        # Also gather from cited sources
        for sid in cited_ids:
            if sid in ev_by_source:
                quotes.extend(ev_by_source[sid])

        # Deterministic scoring should not overweight duplicate snippets.
        quotes = list(dict.fromkeys(q for q in quotes if q))
        claim['_support_evidence_count'] = len(quotes)

        if not quotes and not cited_ids and not evidence_ids:
            # No links at all
            if claim_type == 'speculation':
                claim['support_status'] = 'supported'  # Speculation doesn't need evidence
            else:
                claim['support_status'] = 'unsupported'
        elif not quotes:
            # Has cited sources but no evidence captured yet
            claim['support_status'] = 'needs_review'
        else:
            status, score, notes = compute_support_score(claim['text'], quotes)
            claim['support_status'] = status
            claim['_support_score'] = score
            claim['_support_notes'] = notes

        verified += 1
        updated_claims.append(claim)

    # Rewrite claims.jsonl with updated statuses
    write_jsonl(claims_path, updated_claims)

    # Compute summary
    status_counts = Counter(c.get('support_status') for c in updated_claims)
    factual_unsupported = sum(
        1 for c in updated_claims
        if get_claim_role(c) == 'factual' and c.get('support_status') == 'unsupported'
    )
    factual_needs_review = sum(
        1 for c in updated_claims
        if get_claim_role(c) == 'factual' and c.get('support_status') == 'needs_review'
    )
    factual_partial = sum(
        1 for c in updated_claims
        if get_claim_role(c) == 'factual' and c.get('support_status') == 'partial'
    )
    factual_blocking = sum(1 for c in updated_claims if is_blocking_factual(c))
    total_factual = sum(1 for c in updated_claims if get_claim_role(c) == 'factual')

    # Strict mode: fail if any factual claim lacks full deterministic support.
    passed = True
    if args.strict and factual_blocking > 0:
        passed = False

    print(json.dumps({
        'status': 'pass' if passed else 'fail',
        'verified': verified,
        'support_status_counts': dict(status_counts),
        'factual_blocking': factual_blocking,
        'factual_unsupported': factual_unsupported,
        'factual_needs_review': factual_needs_review,
        'factual_partial': factual_partial,
        'total_factual': total_factual,
        'unsupported_rate': round(factual_unsupported / max(total_factual, 1), 3),
        'blocking_rate': round(factual_blocking / max(total_factual, 1), 3),
    }, indent=2))

    if not passed:
        sys.exit(1)


def cmd_report(args: argparse.Namespace) -> None:
    """Generate human-readable support verification report."""
    claims_path = os.path.join(args.dir, 'claims.jsonl')
    claims = read_jsonl(claims_path)

    # Deduplicate
    seen = set()
    unique = []
    for c in claims:
        cid = c.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(c)

    lines = ['# Claim Support Verification Report', '']

    # Summary
    status_counts = Counter(c.get('support_status') for c in unique)
    type_counts = Counter(get_claim_role(c) for c in unique)
    domain_counts = Counter(c.get('claim_domain') or c.get('claim_type') for c in unique if (c.get('claim_domain') or c.get('claim_type')) in INVESTMENT_DOMAINS)
    lines.append(f'**Total claims:** {len(unique)}')
    lines.append(f'**By type:** {dict(type_counts)}')
    if domain_counts:
        lines.append(f'**By investment domain:** {dict(domain_counts)}')
    lines.append(f'**By status:** {dict(status_counts)}')
    lines.append('')

    # Blocking factual claims (the strict-mode failures)
    unsupported_factual = [
        c for c in unique
        if is_blocking_factual(c)
    ]
    if unsupported_factual:
        lines.append('## Blocking Factual Claims')
        lines.append('')
        for c in unsupported_factual:
            lines.append(f'- [{c["support_status"]}] `{c["section_id"]}`: {c["text"][:100]}...')
            if c.get('_support_notes'):
                lines.append(f'  Notes: {c["_support_notes"]}')
        lines.append('')

    # All clear
    if not unsupported_factual:
        lines.append('## All factual claims have adequate support.')
        lines.append('')

    print('\n'.join(lines))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='verify_claim_support',
        description='Claim-support verification for deep-research v3.0',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # verify
    p_ver = sub.add_parser('verify', help='Verify claims against evidence')
    p_ver.add_argument('--dir', required=True, help='Run directory')
    p_ver.add_argument('--strict', action='store_true', help='Exit 1 if any factual claim unsupported')

    # report
    p_rep = sub.add_parser('report', help='Generate verification report')
    p_rep.add_argument('--dir', required=True, help='Run directory')

    args = parser.parse_args()
    dispatch = {
        'verify': cmd_verify,
        'report': cmd_report,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
