#!/usr/bin/env python3
"""Global audit manifest for deep-research evidence packages.

The audit manifest is a deterministic final gate over the observable research
trajectory: source ledger, evidence ledger, claim ledger, and optional report.
It does not inspect hidden chain-of-thought. It checks whether the delivered
artifact is supported by a coherent, citation-linked evidence trail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit


EVIDENCE_TEXT_FIELDS = ('quote', 'evidence_quote', 'evidence_quote_or_span')
FACTUAL_BLOCKING_STATUSES = frozenset(['unsupported', 'needs_review', 'partial', 'unverified', None])
CITATION_RE = re.compile(r'\[((?:[SE]?\d+)(?:,\s*(?:[SE]?\d+))*)\]')
LOW_INFO_PATTERNS = (
    'accessibility statement',
    'skip navigation',
    'client login',
    'send a release',
    'javascript is disabled',
    'enable javascript',
    'verify that you are human',
    "verify that you're not a robot",
    'privacy policy',
    'cookie policy',
    'terms of use',
    'all rights reserved',
    'contact pr newswire',
)
NAV_TOKENS = frozenset([
    'about', 'accessibility', 'careers', 'client', 'contact', 'cookies',
    'login', 'navigation', 'privacy', 'resources', 'rss', 'sitemap',
])
MODE_SOURCE_TARGETS = {
    'quick': 10,
    'standard': 25,
    'deep': 50,
    'ultradeep': 100,
}
MODE_LANE_TARGETS = {
    'quick': 1,
    'standard': 1,
    'deep': 2,
    'ultradeep': 4,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path: str, payload: dict) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def normalize_issue_rows(payload) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ('issues', 'citation_issues'):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def evidence_text(row: dict) -> str:
    for key in EVIDENCE_TEXT_FIELDS:
        value = str(row.get(key) or '').strip()
        if value:
            return value
    return ''


def normalize_citation_label(raw_label: str) -> str:
    label = str(raw_label or '').strip().strip('[]').upper()
    if label.startswith(('S', 'E')):
        label = label[1:]
    return label


def extract_citation_labels(text: str) -> set[str]:
    labels: set[str] = set()
    for match in CITATION_RE.finditer(text):
        for raw_label in match.group(1).split(','):
            label = normalize_citation_label(raw_label)
            if label.isdigit():
                labels.add(label)
    return labels


def source_label_index(sources: list[dict], run_dir: str | None = None) -> dict[str, str]:
    index: dict[str, str] = {}
    source_ids = {
        source.get('source_id') or source.get('id')
        for source in sources
        if source.get('source_id') or source.get('id')
    }

    if run_dir:
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


def claim_role(claim: dict) -> str:
    claim_type = claim.get('claim_type', 'factual')
    if claim_type in {'clinical', 'regulatory', 'financial', 'commercial', 'competitive', 'scientific', 'market'}:
        return claim.get('claim_role', 'factual')
    return claim_type


def has_support_waiver(claim: dict) -> bool:
    return bool(
        claim.get('support_waiver')
        or claim.get('allow_partial_support')
        or claim.get('support_status_waiver')
    )


def is_low_information_text(text: str) -> bool:
    compact = re.sub(r'\s+', ' ', text).strip().lower()
    if not compact:
        return True
    if len(compact) < 40:
        return True
    if any(pattern in compact for pattern in LOW_INFO_PATTERNS):
        return True
    tokens = re.findall(r'[a-z]{3,}', compact[:800])
    if len(tokens) < 12:
        return True
    nav_hits = sum(1 for token in tokens if token in NAV_TOKENS)
    return nav_hits >= 6 and nav_hits / max(len(tokens), 1) > 0.2


def host_for(source: dict) -> str:
    url = str(source.get('canonical_url') or source.get('url') or '')
    return urlsplit(url).netloc.lower().removeprefix('www.')


def is_peer_reviewed_source(source: dict) -> bool:
    source_type = str(source.get('source_type') or '').lower()
    canonical = str(source.get('canonical_locator') or '').lower()
    venue = str(source.get('venue') or '').lower()
    return (
        source_type == 'academic'
        or canonical.startswith('doi:')
        or 'journal' in venue
        or source.get('doi')
    )


def artifact_path(run_dir: str, manifest: dict, key: str, default: str) -> str:
    rel = (manifest.get('artifact_paths') or {}).get(key) or default
    return rel if os.path.isabs(rel) else os.path.join(run_dir, rel)


def add_coverage_finding(
    warnings: list[dict],
    critical: list[dict],
    *,
    mode: str | None,
    strict: bool,
    finding: dict,
) -> None:
    if strict and mode == 'ultradeep':
        critical.append(finding)
    else:
        warnings.append(finding)


def audit_plan_coverage(run_dir: str, sources: list[dict], warnings: list[dict], critical: list[dict], strict: bool) -> dict:
    run_manifest_path = os.path.join(run_dir, 'run_manifest.json')
    run_manifest = read_json(run_manifest_path)
    if not run_manifest:
        warnings.append({
            'code': 'run_manifest_missing',
            'message': 'run_manifest.json not found; plan/coverage accounting treated as legacy unavailable',
        })
        return {'mode': None, 'plan_lanes': 0, 'coverage_lanes': 0, 'coverage_findings': 1}

    mode = run_manifest.get('mode')
    if mode not in MODE_SOURCE_TARGETS:
        warnings.append({
            'code': 'run_manifest_mode_unknown',
            'mode': mode,
            'message': 'Run manifest mode is missing or unknown; plan/coverage checks are warnings only',
        })

    findings = 0
    plan_path = artifact_path(run_dir, run_manifest, 'plan', 'plan.json')
    coverage_path = artifact_path(run_dir, run_manifest, 'coverage_map', 'coverage_map.json')
    plan = read_json(plan_path)
    coverage = read_json(coverage_path)

    if not plan:
        add_coverage_finding(
            warnings,
            critical,
            mode=mode,
            strict=strict,
            finding={
                'code': 'missing_plan',
                'path': plan_path,
                'message': 'plan.json is missing; planned lanes and query families cannot be audited',
            },
        )
        findings += 1
    if not coverage:
        add_coverage_finding(
            warnings,
            critical,
            mode=mode,
            strict=strict,
            finding={
                'code': 'missing_coverage_map',
                'path': coverage_path,
                'message': 'coverage_map.json is missing; planned-vs-executed coverage cannot be audited',
            },
        )
        findings += 1

    lanes = plan.get('lanes') or []
    expected_lanes = MODE_LANE_TARGETS.get(mode)
    if expected_lanes is not None and lanes and len(lanes) < expected_lanes:
        add_coverage_finding(
            warnings,
            critical,
            mode=mode,
            strict=strict,
            finding={
                'code': 'planned_lanes_below_mode_target',
                'mode': mode,
                'planned_lanes': len(lanes),
                'expected_lanes': expected_lanes,
                'message': 'Plan has fewer lanes than the mode target',
            },
        )
        findings += 1

    source_target = MODE_SOURCE_TARGETS.get(mode)
    unique_source_count = len({source.get('source_id') for source in sources if source.get('source_id')})
    if source_target is not None and unique_source_count < source_target:
        add_coverage_finding(
            warnings,
            critical,
            mode=mode,
            strict=strict,
            finding={
                'code': 'source_count_below_mode_target',
                'mode': mode,
                'source_count': unique_source_count,
                'expected_min': source_target,
                'message': 'Unique retained sources are below the mode target',
            },
        )
        findings += 1

    for lane in coverage.get('lane_coverage') or []:
        lane_id = lane.get('lane_id')
        status = lane.get('status')
        if lane.get('planned') and not lane.get('executed') and status not in {'covered', 'bounded', 'gap_disclosed'}:
            add_coverage_finding(
                warnings,
                critical,
                mode=mode,
                strict=strict,
                finding={
                    'code': 'planned_lane_not_executed',
                    'lane_id': lane_id,
                    'status': status,
                    'message': 'A planned lane has no recorded execution',
                },
            )
            findings += 1
        expected_min = int(lane.get('expected_source_min') or 0)
        source_count = int(lane.get('source_count') or 0)
        if status not in {'covered', 'bounded', 'gap_disclosed'} and source_count < expected_min:
            add_coverage_finding(
                warnings,
                critical,
                mode=mode,
                strict=strict,
                finding={
                    'code': 'lane_source_count_below_plan',
                    'lane_id': lane_id,
                    'source_count': source_count,
                    'expected_min': expected_min,
                    'status': status,
                    'message': 'A planned lane is below its source target and not bounded or disclosed',
                },
            )
            findings += 1

    for family in coverage.get('query_family_coverage') or []:
        if family.get('planned') and not family.get('executed'):
            add_coverage_finding(
                warnings,
                critical,
                mode=mode,
                strict=strict,
                finding={
                    'code': 'query_family_missing',
                    'query_family_id': family.get('query_family_id'),
                    'lane_id': family.get('lane_id'),
                    'message': 'A planned query family has no recorded provider call or retained source',
                },
            )
            findings += 1

    return {
        'mode': mode,
        'plan_lanes': len(lanes),
        'coverage_lanes': len(coverage.get('lane_coverage') or []),
        'coverage_findings': findings,
    }


INCOMPLETE_LANE_STATUSES = frozenset(['bounded', 'gap_disclosed', 'below_target'])

# Status-precision language: claims that pin a regulatory, trial, or filing
# state are load-bearing even when the ledger carries no investment_relevance.
STATUS_PRECISION_RE = re.compile(
    r'\b('
    r'approved|approval|cleared|clearance|authorized|authorisation|authorization'
    r'|phase\s*(?:1|2|3|i{1,3})\b|topline|top-line|primary endpoint|met its endpoint'
    r'|filed|filing|submitted|accepted for review|complete response letter|crl'
    r'|breakthrough therapy|fast track|orphan drug|pdufa'
    r'|recalled|withdrawn|discontinued|terminated'
    r')\b',
    re.IGNORECASE,
)


def is_material_claim(claim: dict) -> bool:
    """Materiality decided mechanically, never by the writer's judgment."""
    if claim.get('material') is True:
        return True
    if str(claim.get('investment_relevance') or '').lower() == 'high':
        return True
    text = str(claim.get('text') or claim.get('claim') or '')
    return bool(STATUS_PRECISION_RE.search(text))


def has_independent_verification(claim: dict) -> bool:
    """Both a fresh quote and a fresh locator are required.

    A quote with no locator cannot be re-checked by the next reader, and a
    locator with no quote records only that someone visited the page.
    """
    quote = str(claim.get('verifier_quote') or '').strip()
    locator = str(claim.get('verifier_locator') or '').strip()
    return bool(quote and locator)


def compute_run_status(
    run_dir: str,
    claims: list[dict],
    critical: list[dict],
    citation_auditor_summary: dict,
    declared_reasons: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """Compute the run-level Verified/Partial stamp.

    This is a disclosure layer on top of the strict gate, never a substitute for
    it: a run can pass every critical check and still be `partial` because it
    shipped with disclosed coverage gaps, support waivers, surviving semantic
    warnings, or a failed research lane. The reader must be able to see that
    from the report headline rather than by reading Limitations closely.
    """
    reasons: list[dict] = []

    coverage = read_json(os.path.join(run_dir, 'coverage_map.json'))
    incomplete_lanes = [
        lane.get('lane_id')
        for lane in (coverage.get('lane_coverage') or [])
        if lane.get('status') in INCOMPLETE_LANE_STATUSES
    ]
    if incomplete_lanes:
        reasons.append({
            'code': 'lane_not_fully_covered',
            'count': len(incomplete_lanes),
            'lane_ids': incomplete_lanes[:10],
            'message': 'One or more lanes were bounded, below target, or shipped with a disclosed gap',
        })

    waived = [
        claim.get('claim_id') for claim in claims
        if has_support_waiver(claim)
    ]
    if waived:
        reasons.append({
            'code': 'support_waivers_present',
            'count': len(waived),
            'claim_ids': waived[:10],
            'message': 'Claims were delivered under a support waiver rather than full evidence support',
        })

    semantic_warnings = [
        claim.get('claim_id') for claim in claims
        if claim.get('semantic_gate') == 'warning'
    ]
    if semantic_warnings:
        reasons.append({
            'code': 'semantic_gate_warnings',
            'count': len(semantic_warnings),
            'claim_ids': semantic_warnings[:10],
            'message': 'Claims carry a surviving semantic-gate warning',
        })

    run_manifest = read_json(os.path.join(run_dir, 'run_manifest.json'))
    trace = run_manifest.get('execution_trace') or {}
    failed_subagents = [
        entry.get('subagent_id')
        for entry in (trace.get('subagents') or [])
        if str(entry.get('status') or '').lower() in {'failed', 'error', 'timeout', 'below_target'}
    ]
    if failed_subagents:
        reasons.append({
            'code': 'subagent_lane_failed',
            'count': len(failed_subagents),
            'subagent_ids': failed_subagents[:10],
            'message': 'A recorded research subagent lane failed, timed out, or landed below target',
        })

    noncritical_auditor_issues = (
        citation_auditor_summary.get('global_issues', 0)
        + citation_auditor_summary.get('section_issues', 0)
        - citation_auditor_summary.get('critical_issues', 0)
    )
    if noncritical_auditor_issues > 0:
        reasons.append({
            'code': 'citation_auditor_issues_hedged',
            'count': noncritical_auditor_issues,
            'message': 'CitationAuditor issues were resolved by hedging or disclosure rather than by a fix',
        })

    for declared in declared_reasons or []:
        text = str(declared).strip()
        if text:
            reasons.append({
                'code': 'declared_by_caller',
                'message': text,
            })

    if critical:
        reasons.append({
            'code': 'critical_findings_present',
            'count': len(critical),
            'message': 'The audit recorded critical findings; the run cannot be stamped verified',
        })

    return ('partial' if reasons else 'verified'), reasons


def audit_citation_auditor_issues(run_dir: str, warnings: list[dict], critical: list[dict]) -> dict:
    audit_dir = os.path.join(run_dir, 'audit')
    global_issue_path = os.path.join(audit_dir, 'citation_issues.json')
    section_issue_dir = os.path.join(audit_dir, 'section_citation_issues')
    summary = {
        'global_files': 0,
        'global_issues': 0,
        'section_files': 0,
        'section_issues': 0,
        'critical_issues': 0,
        'noncritical_issues': 0,
        'invalid_files': 0,
    }
    critical_examples = []
    noncritical_examples = []
    invalid_files = []

    def process_issue_file(path: str, scope: str, section_id: str | None = None) -> None:
        try:
            with open(path, encoding='utf-8') as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            invalid_files.append({'file': path, 'scope': scope, 'section_id': section_id, 'error': str(exc)})
            return

        rows = normalize_issue_rows(payload)
        if scope == 'section':
            summary['section_files'] += 1
            summary['section_issues'] += len(rows)
        else:
            summary['global_files'] += 1
            summary['global_issues'] += len(rows)

        for row in rows:
            severity = str(row.get('severity') or 'unknown').lower()
            example = {
                'scope': scope,
                'section_id': row.get('section_id') or section_id,
                'claim': row.get('claim'),
                'citation': row.get('citation'),
                'issue_type': row.get('issue_type'),
                'severity': severity,
                'suggested_fix': row.get('suggested_fix'),
            }
            if severity == 'critical':
                critical_examples.append(example)
            else:
                noncritical_examples.append(example)

    if os.path.exists(global_issue_path):
        process_issue_file(global_issue_path, 'global')
    if os.path.isdir(section_issue_dir):
        for filename in sorted(os.listdir(section_issue_dir)):
            if filename.endswith('.json'):
                section_id = os.path.splitext(filename)[0]
                process_issue_file(os.path.join(section_issue_dir, filename), 'section', section_id)

    summary['critical_issues'] = len(critical_examples)
    summary['noncritical_issues'] = len(noncritical_examples)
    summary['invalid_files'] = len(invalid_files)

    if invalid_files:
        critical.append({
            'code': 'citation_auditor_invalid_json',
            'count': len(invalid_files),
            'examples': invalid_files[:10],
            'message': 'CitationAuditor issue files must be valid JSON arrays or issue containers',
        })
    if critical_examples:
        critical.append({
            'code': 'citation_auditor_critical_issues',
            'count': len(critical_examples),
            'examples': critical_examples[:10],
            'message': 'CitationAuditor found critical citation issues that block delivery',
        })
    if noncritical_examples:
        warnings.append({
            'code': 'citation_auditor_noncritical_issues',
            'count': len(noncritical_examples),
            'examples': noncritical_examples[:10],
            'message': 'CitationAuditor found noncritical citation issues that should be fixed, hedged, or disclosed',
        })
    return summary


def build_manifest(
    run_dir: str,
    report_path: str | None = None,
    strict: bool = False,
    partial_reasons: list[str] | None = None,
) -> dict:
    sources_path = os.path.join(run_dir, 'sources.jsonl')
    evidence_path = os.path.join(run_dir, 'evidence.jsonl')
    claims_path = os.path.join(run_dir, 'claims.jsonl')
    sources = read_jsonl(sources_path)
    evidence = read_jsonl(evidence_path)
    claims = read_jsonl(claims_path)

    critical: list[dict] = []
    warnings: list[dict] = []
    coverage_summary: dict = {}

    for path, rows, ledger_name in (
        (sources_path, sources, 'sources.jsonl'),
        (evidence_path, evidence, 'evidence.jsonl'),
        (claims_path, claims, 'claims.jsonl'),
    ):
        if not os.path.exists(path):
            critical.append({'code': 'missing_ledger', 'ledger': ledger_name, 'message': f'{ledger_name} not found'})
        elif not rows:
            critical.append({'code': 'empty_ledger', 'ledger': ledger_name, 'message': f'{ledger_name} is empty'})

    source_ids = {row.get('source_id') for row in sources if row.get('source_id')}
    evidence_ids = {row.get('evidence_id') for row in evidence if row.get('evidence_id')}

    missing_evidence_text = []
    low_info_evidence = []
    for row in evidence:
        text = evidence_text(row)
        if not text:
            missing_evidence_text.append(row.get('evidence_id') or row.get('source_id') or '(unknown)')
            continue
        if is_low_information_text(text):
            low_info_evidence.append(row.get('evidence_id') or row.get('source_id') or '(unknown)')
        sid = row.get('source_id')
        if sid and source_ids and sid not in source_ids:
            warnings.append({'code': 'evidence_orphan_source', 'source_id': sid, 'message': 'Evidence source_id missing from sources.jsonl'})

    if missing_evidence_text:
        critical.append({
            'code': 'missing_evidence_text',
            'count': len(missing_evidence_text),
            'examples': missing_evidence_text[:10],
            'message': 'Evidence rows without quote/evidence_quote/evidence_quote_or_span cannot support claims',
        })
    if low_info_evidence:
        warnings.append({
            'code': 'low_information_evidence',
            'count': len(low_info_evidence),
            'examples': low_info_evidence[:10],
            'message': 'Some evidence rows look like navigation, cookie, bot-check, or other low-information extracts',
        })

    blocking_claims = []
    semantic_contradictions = []
    orphan_claim_sources = []
    orphan_claim_evidence = []
    for claim in claims:
        status = claim.get('support_status')
        if claim_role(claim) == 'factual' and status in FACTUAL_BLOCKING_STATUSES and not has_support_waiver(claim):
            blocking_claims.append({
                'claim_id': claim.get('claim_id'),
                'section_id': claim.get('section_id'),
                'support_status': status,
                'text': str(claim.get('text') or '')[:180],
            })
        if claim_role(claim) == 'factual' and claim.get('support_status_llm') == 'contradicted':
            semantic_contradictions.append({
                'claim_id': claim.get('claim_id'),
                'section_id': claim.get('section_id'),
                'support_status': status,
                'support_status_llm': claim.get('support_status_llm'),
                'rationale': str(claim.get('support_rationale_llm') or '')[:240],
                'text': str(claim.get('text') or '')[:180],
            })
        for source_id in claim.get('cited_source_ids') or []:
            if source_ids and source_id not in source_ids:
                orphan_claim_sources.append({'claim_id': claim.get('claim_id'), 'source_id': source_id})
        for evidence_id in claim.get('evidence_ids') or []:
            if evidence_ids and evidence_id not in evidence_ids:
                orphan_claim_evidence.append({'claim_id': claim.get('claim_id'), 'evidence_id': evidence_id})

    if blocking_claims:
        critical.append({
            'code': 'blocking_factual_claims',
            'count': len(blocking_claims),
            'examples': blocking_claims[:10],
            'message': 'Factual claims remain unsupported, partial, unverified, or review-needed',
        })
    if semantic_contradictions:
        critical.append({
            'code': 'semantic_contradictions',
            'count': len(semantic_contradictions),
            'examples': semantic_contradictions[:10],
            'message': 'Semantic support verifier found evidence that contradicts factual claims',
        })
    if orphan_claim_sources:
        critical.append({
            'code': 'claim_source_links_missing',
            'count': len(orphan_claim_sources),
            'examples': orphan_claim_sources[:10],
            'message': 'Claims cite source IDs absent from sources.jsonl',
        })
    if orphan_claim_evidence:
        critical.append({
            'code': 'claim_evidence_links_missing',
            'count': len(orphan_claim_evidence),
            'examples': orphan_claim_evidence[:10],
            'message': 'Claims cite evidence IDs absent from evidence.jsonl',
        })

    report_citations = set()
    missing_report_citations = []
    if report_path:
        if not os.path.exists(report_path):
            critical.append({'code': 'missing_report', 'report': report_path, 'message': 'Report path not found'})
        else:
            with open(report_path, encoding='utf-8') as f:
                report_text = f.read()
            report_citations = extract_citation_labels(report_text)
            labels = source_label_index(sources, run_dir)
            missing_report_citations = sorted(label for label in report_citations if label not in labels)
            if missing_report_citations:
                critical.append({
                    'code': 'report_citation_labels_missing',
                    'count': len(missing_report_citations),
                    'labels': missing_report_citations[:25],
                    'message': 'Report contains citation labels not present in sources.jsonl display labels or ordinals',
                })

    hosts = Counter(host_for(source) for source in sources if host_for(source))
    tiers = Counter(str(source.get('source_tier') or 'unknown') for source in sources)
    unknown_source_count = tiers.get('unknown', 0)
    if sources and unknown_source_count / len(sources) > 0.5:
        warnings.append({
            'code': 'high_unknown_source_tier_ratio',
            'ratio': round(unknown_source_count / len(sources), 3),
            'message': 'Most sources have unknown source_tier; primary/secondary trust boundaries may be weak',
        })
    if sources and hosts:
        host, count = hosts.most_common(1)[0]
        if count / len(sources) > 0.5 and len(sources) >= 5:
            warnings.append({
                'code': 'domain_concentration',
                'host': host,
                'ratio': round(count / len(sources), 3),
                'message': 'Retained sources are concentrated in one domain',
            })

    missing_editorial_checks = []
    retracted_or_concern_sources = []
    for source in sources:
        if not is_peer_reviewed_source(source):
            continue
        status_value = str(source.get('editorial_notice_status') or '').strip().lower()
        checked_at = source.get('scite_checked_at')
        if status_value in {'retracted', 'expression_of_concern'}:
            retracted_or_concern_sources.append({
                'source_id': source.get('source_id') or source.get('id'),
                'title': str(source.get('title') or '')[:180],
                'editorial_notice_status': status_value,
                'scite_checked_at': checked_at,
            })
        elif not status_value or not checked_at:
            missing_editorial_checks.append({
                'source_id': source.get('source_id') or source.get('id'),
                'title': str(source.get('title') or '')[:180],
                'editorial_notice_status': status_value or None,
                'scite_checked_at': checked_at,
            })
    if missing_editorial_checks:
        warnings.append({
            'code': 'scite_editorial_notice_missing',
            'count': len(missing_editorial_checks),
            'examples': missing_editorial_checks[:10],
            'message': 'Peer-reviewed/DOI sources lack machine-checkable editorial_notice_status or scite_checked_at',
        })
    if retracted_or_concern_sources:
        critical.append({
            'code': 'scite_editorial_notice_blocking',
            'count': len(retracted_or_concern_sources),
            'examples': retracted_or_concern_sources[:10],
            'message': 'Peer-reviewed/DOI sources include retracted papers or expressions of concern',
        })

    coverage_summary = audit_plan_coverage(run_dir, sources, warnings, critical, strict)
    citation_auditor_summary = audit_citation_auditor_issues(run_dir, warnings, critical)

    # P1-D: verification must be independent of generation. Escalated to
    # critical only under ultradeep+strict, matching the coverage-finding
    # policy, so legacy and lighter-mode runs surface it as a warning instead
    # of failing outright.
    run_manifest_for_mode = read_json(os.path.join(run_dir, 'run_manifest.json'))
    audit_mode = run_manifest_for_mode.get('mode')
    unverified_material = [
        {
            'claim_id': claim.get('claim_id'),
            'text': str(claim.get('text') or claim.get('claim') or '')[:180],
            'investment_relevance': claim.get('investment_relevance'),
        }
        for claim in claims
        if claim_role(claim) == 'factual'
        and is_material_claim(claim)
        and not has_independent_verification(claim)
    ]
    if unverified_material:
        add_coverage_finding(
            warnings,
            critical,
            mode=audit_mode,
            strict=strict,
            finding={
                'code': 'material_claim_no_independent_evidence',
                'count': len(unverified_material),
                'examples': unverified_material[:10],
                'message': (
                    'Material claims lack an auditor-supplied verifier_quote and '
                    'verifier_locator obtained by re-opening the source'
                ),
            },
        )

    status = 'fail' if critical else 'pass'
    run_status, run_status_reasons = compute_run_status(
        run_dir, claims, critical, citation_auditor_summary, partial_reasons,
    )
    return {
        'status': status,
        'run_status': run_status,
        'run_status_reasons': run_status_reasons,
        'generated_at': utc_now(),
        'run_dir': run_dir,
        'report_path': report_path,
        'counts': {
            'sources': len(sources),
            'evidence': len(evidence),
            'claims': len(claims),
            'report_citations': len(report_citations),
            'critical_findings': len(critical),
            'warnings': len(warnings),
            'low_information_evidence': len(low_info_evidence),
            'blocking_factual_claims': len(blocking_claims),
            'semantic_contradictions': len(semantic_contradictions),
            'missing_report_citations': len(missing_report_citations),
            'coverage_findings': coverage_summary.get('coverage_findings', 0),
            'material_claims_without_independent_evidence': len(unverified_material),
            'scite_editorial_notice_missing': len(missing_editorial_checks),
            'scite_editorial_notice_blocking': len(retracted_or_concern_sources),
            'citation_auditor_global_issues': citation_auditor_summary.get('global_issues', 0),
            'citation_auditor_section_files': citation_auditor_summary.get('section_files', 0),
            'citation_auditor_section_issues': citation_auditor_summary.get('section_issues', 0),
            'citation_auditor_critical_issues': citation_auditor_summary.get('critical_issues', 0),
            'citation_auditor_invalid_files': citation_auditor_summary.get('invalid_files', 0),
        },
        'coverage': coverage_summary,
        'citation_auditor': citation_auditor_summary,
        'source_tiers': dict(tiers),
        'top_domains': dict(hosts.most_common(10)),
        'critical': critical,
        'warnings': warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a deep-research audit_manifest.json gate.')
    parser.add_argument('--dir', required=True, help='Run directory containing sources/evidence/claims ledgers')
    parser.add_argument('--report', help='Optional markdown report path to audit citation labels')
    parser.add_argument('--strict', action='store_true', help='Exit 1 if the manifest contains critical findings')
    parser.add_argument(
        '--partial-reason',
        action='append',
        default=[],
        dest='partial_reasons',
        help=(
            'Declare a run-level partial trigger the ledgers cannot express '
            '(e.g. a Quick-mode Search-as-Code skip, or a verify_citations '
            'warning-pass). Repeatable. Never downgrades a partial to verified.'
        ),
    )
    args = parser.parse_args()

    manifest = build_manifest(args.dir, args.report, strict=args.strict, partial_reasons=args.partial_reasons)
    output_path = os.path.join(args.dir, 'audit_manifest.json')
    write_json(output_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    if args.strict and manifest['status'] != 'pass':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
