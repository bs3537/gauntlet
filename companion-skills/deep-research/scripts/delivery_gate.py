#!/usr/bin/env python3
"""Strict delivery gate for deep-research report packages.

This script orchestrates the existing validators in the order required for a
deliverable package:

1. report structure validation
2. citation verification
3. global and per-section CitationAuditor issue blocking
4. claim extraction
5. strict deterministic claim-support verification
6. optional semantic claim-support verification
7. strict global audit manifest

It keeps the component scripts independently usable while making the final
delivery decision depend on the global audit manifest and CitationAuditor
issue artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def tail_text(text: str, max_chars: int = 2000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    if not stripped.startswith('{'):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def compact_summary(step_name: str, parsed: dict[str, Any] | None) -> dict[str, Any]:
    if not parsed:
        return {}

    if step_name == 'claim_extraction':
        return {
            'status': parsed.get('status'),
            'claims_added': parsed.get('claims_added'),
            'claims_skipped': parsed.get('claims_skipped'),
            'claims_updated': parsed.get('claims_updated'),
            'total_claims': parsed.get('total_claims'),
        }

    if step_name == 'claim_support':
        return {
            'status': parsed.get('status'),
            'verified': parsed.get('verified'),
            'factual_blocking': parsed.get('factual_blocking'),
            'support_status_counts': parsed.get('support_status_counts'),
            'blocking_rate': parsed.get('blocking_rate'),
        }

    if step_name == 'semantic_claim_support':
        return {
            'status': parsed.get('status'),
            'selected': parsed.get('selected'),
            'judged': parsed.get('judged'),
            'entailed': parsed.get('entailed'),
            'contradicted': parsed.get('contradicted'),
            'insufficient': parsed.get('insufficient'),
            'missing_judgments': parsed.get('missing_judgments'),
            'blocking_after': parsed.get('blocking_after'),
            'judge_model': parsed.get('judge_model'),
            'judge_version': parsed.get('judge_version'),
        }

    if step_name == 'global_audit':
        return {
            'status': parsed.get('status'),
            'counts': parsed.get('counts'),
            'critical_codes': [
                item.get('code')
                for item in parsed.get('critical', [])
                if isinstance(item, dict)
            ],
            'warning_codes': [
                item.get('code')
                for item in parsed.get('warnings', [])
                if isinstance(item, dict)
            ],
        }

    return {}


def run_step(name: str, cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    parsed = parse_json_stdout(result.stdout)
    step: dict[str, Any] = {
        'name': name,
        'status': 'pass' if result.returncode == 0 else 'fail',
        'returncode': result.returncode,
        'command': cmd,
    }
    summary = compact_summary(name, parsed)
    if summary:
        step['summary'] = summary
    if result.stdout.strip():
        step['stdout_tail'] = tail_text(result.stdout)
    if result.stderr.strip():
        step['stderr_tail'] = tail_text(result.stderr)
    return step


def read_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / 'audit_manifest.json'
    if not manifest_path.exists():
        return {}
    try:
        with open(manifest_path, encoding='utf-8') as f:
            parsed = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_issue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ('issues', 'citation_issues'):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def check_citation_auditor_issues(path: Path) -> dict[str, Any]:
    step: dict[str, Any] = {
        'name': 'citation_auditor_issues',
        'status': 'pass',
        'returncode': 0,
        'path': str(path),
    }
    if not path.exists():
        step['summary'] = {'status': 'not_found', 'critical_issues': 0, 'total_issues': 0}
        return step

    try:
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        step['status'] = 'fail'
        step['returncode'] = 1
        step['summary'] = {'status': 'invalid_json', 'error': str(exc)}
        return step

    rows = normalize_issue_rows(payload)
    severity_counts: dict[str, int] = {}
    for row in rows:
        severity = str(row.get('severity') or 'unknown').lower()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    critical = [
        {
            'claim': row.get('claim'),
            'citation': row.get('citation'),
            'issue_type': row.get('issue_type'),
            'suggested_fix': row.get('suggested_fix'),
        }
        for row in rows
        if str(row.get('severity') or '').lower() == 'critical'
    ]
    if critical:
        step['status'] = 'fail'
        step['returncode'] = 1
    step['summary'] = {
        'status': 'fail' if critical else 'pass',
        'critical_issues': len(critical),
        'total_issues': len(rows),
        'severity_counts': severity_counts,
        'critical_examples': critical[:10],
    }
    return step


def expected_section_ids(report_path: Path) -> list[str]:
    from extract_claims import parse_sections

    with open(report_path, encoding='utf-8') as f:
        markdown = f.read()
    seen: set[str] = set()
    section_ids: list[str] = []
    for section_id, content in parse_sections(markdown):
        if section_id == 'preamble' or not content.strip():
            continue
        if section_id not in seen:
            seen.add(section_id)
            section_ids.append(section_id)
    return section_ids


def check_section_citation_audits(path: Path, report_path: Path | None = None, require: bool = False) -> dict[str, Any]:
    step: dict[str, Any] = {
        'name': 'section_citation_audits',
        'status': 'pass',
        'returncode': 0,
        'path': str(path),
        'required': bool(require),
    }
    expected_sections = expected_section_ids(report_path) if require and report_path else []
    if not path.exists():
        if require and expected_sections:
            step['status'] = 'fail'
            step['returncode'] = 1
        step['summary'] = {
            'status': 'not_found',
            'audit_files': 0,
            'critical_issues': 0,
            'total_issues': 0,
            'expected_sections': expected_sections,
            'missing_sections': expected_sections,
        }
        return step
    if not path.is_dir():
        step['status'] = 'fail'
        step['returncode'] = 1
        step['summary'] = {'status': 'invalid_path', 'error': 'section citation audit path is not a directory'}
        return step

    files = sorted(path.glob('*.json'))
    file_sections = {issue_file.stem for issue_file in files}
    missing_sections = [section_id for section_id in expected_sections if section_id not in file_sections]
    invalid_files: list[dict[str, str]] = []
    severity_counts: dict[str, int] = {}
    critical: list[dict[str, Any]] = []
    total_issues = 0
    for issue_file in files:
        try:
            with open(issue_file, encoding='utf-8') as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            invalid_files.append({'file': str(issue_file), 'error': str(exc)})
            continue

        rows = normalize_issue_rows(payload)
        total_issues += len(rows)
        section_id = issue_file.stem
        for row in rows:
            severity = str(row.get('severity') or 'unknown').lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            if severity == 'critical':
                critical.append({
                    'file': str(issue_file),
                    'section_id': row.get('section_id') or section_id,
                    'claim': row.get('claim'),
                    'citation': row.get('citation'),
                    'issue_type': row.get('issue_type'),
                    'suggested_fix': row.get('suggested_fix'),
                })

    if invalid_files or critical or missing_sections:
        step['status'] = 'fail'
        step['returncode'] = 1
    step['summary'] = {
        'status': 'fail' if invalid_files or critical or missing_sections else 'pass',
        'audit_files': len(files),
        'critical_issues': len(critical),
        'total_issues': total_issues,
        'severity_counts': severity_counts,
        'critical_examples': critical[:10],
        'invalid_files': invalid_files[:10],
        'expected_sections': expected_sections,
        'missing_sections': missing_sections,
    }
    return step


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding='utf-8') as f:
        return sum(1 for line in f if line.strip())


def prepare_claim_ledger(run_dir: Path, preserve_existing: bool) -> dict[str, Any]:
    claims_path = run_dir / 'claims.jsonl'
    archive_path = run_dir / 'claims.before_delivery_gate.jsonl'
    step: dict[str, Any] = {
        'name': 'claim_ledger_rebuild',
        'status': 'pass',
        'returncode': 0,
        'path': str(claims_path),
    }

    previous_rows = count_jsonl_rows(claims_path)
    if preserve_existing:
        step['summary'] = {
            'action': 'preserved_existing_claims',
            'previous_rows': previous_rows,
        }
        return step

    run_dir.mkdir(parents=True, exist_ok=True)
    if claims_path.exists():
        with open(claims_path, 'rb') as src, open(archive_path, 'wb') as dst:
            dst.write(src.read())
    with open(claims_path, 'w', encoding='utf-8'):
        pass

    step['summary'] = {
        'action': 'rebuilt_current_report_claims',
        'previous_rows': previous_rows,
        'archived_to': str(archive_path) if previous_rows else None,
    }
    return step


def build_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    py = sys.executable
    report = os.path.abspath(args.report)
    run_dir = os.path.abspath(args.dir)

    commands: list[tuple[str, list[str]]] = [
        ('structure_validation', [py, str(SCRIPT_DIR / 'validate_report.py'), '--report', report]),
        ('citation_verification', [py, str(SCRIPT_DIR / 'verify_citations.py'), '--report', report]),
        ('claim_extraction', [py, str(SCRIPT_DIR / 'extract_claims.py'), 'extract', '--report', report, '--dir', run_dir]),
        ('claim_support', [py, str(SCRIPT_DIR / 'verify_claim_support.py'), 'verify', '--dir', run_dir]),
    ]
    if args.semantic:
        semantic_cmd = [
            py,
            str(SCRIPT_DIR / 'verify_claim_support_llm.py'),
            'verify',
            '--dir',
            run_dir,
            '--sample-supported-rate',
            str(args.semantic_sample_supported_rate),
            '--judge-model',
            args.semantic_judge_model,
            '--judge-version',
            args.semantic_judge_version,
            '--timeout',
            str(args.semantic_timeout),
        ]
        if args.semantic_judgments:
            semantic_cmd.extend(['--judgments', os.path.abspath(args.semantic_judgments)])
        if args.semantic_judge_command:
            semantic_cmd.extend(['--judge-command', args.semantic_judge_command])
        commands.append(('semantic_claim_support', semantic_cmd))
    commands.append(('global_audit', [py, str(SCRIPT_DIR / 'audit_manifest.py'), '--dir', run_dir, '--report', report]))

    if args.strict_citations:
        commands[1][1].append('--strict')
    if args.strict:
        commands[3][1].append('--strict')
        if args.semantic:
            commands[-2][1].append('--strict')
        commands[-1][1].append('--strict')
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the deep-research strict delivery gate.')
    parser.add_argument('--dir', required=True, help='Run directory containing sources/evidence/claims ledgers')
    parser.add_argument('--report', required=True, help='Markdown report path to validate and audit')
    parser.add_argument('--strict', action='store_true', help='Exit 1 if any required delivery gate fails')
    parser.add_argument(
        '--strict-citations',
        action='store_true',
        help='Pass --strict to verify_citations.py; useful when DOI/URL verification should be blocking',
    )
    parser.add_argument(
        '--citation-issues',
        help='Optional CitationAuditor JSON path; defaults to [run_dir]/audit/citation_issues.json when present',
    )
    parser.add_argument(
        '--section-citation-issues-dir',
        help='Optional directory of per-section CitationAuditor JSON files; defaults to [run_dir]/audit/section_citation_issues',
    )
    parser.add_argument(
        '--require-section-citation-audits',
        action='store_true',
        help='Fail if any non-empty report section lacks a JSON audit file in the per-section CitationAuditor directory',
    )
    parser.add_argument(
        '--preserve-existing-claims',
        action='store_true',
        help='Do not rebuild claims.jsonl before extraction; use only when stale draft claims are intentionally retained',
    )
    parser.add_argument(
        '--semantic',
        action='store_true',
        help='Run semantic claim-support verification after deterministic claim support',
    )
    parser.add_argument('--semantic-judgments', help='Offline JSON judgments for semantic claim-support verification')
    parser.add_argument('--semantic-judge-command', help='Override semantic judge command; defaults inside verify_claim_support_llm.py')
    parser.add_argument('--semantic-judge-model', default=os.environ.get('DEEP_RESEARCH_SEMANTIC_JUDGE_MODEL', 'claude-sonnet'))
    parser.add_argument('--semantic-judge-version', default=os.environ.get('DEEP_RESEARCH_SEMANTIC_JUDGE_VERSION', 'unversioned'))
    parser.add_argument('--semantic-timeout', type=int, default=600)
    parser.add_argument('--semantic-sample-supported-rate', type=float, default=0.10)
    args = parser.parse_args()

    run_dir = Path(args.dir).resolve()
    report_path = Path(args.report).resolve()
    citation_issues_path = (
        Path(args.citation_issues).resolve()
        if args.citation_issues
        else run_dir / 'audit' / 'citation_issues.json'
    )
    section_citation_issues_dir = (
        Path(args.section_citation_issues_dir).resolve()
        if args.section_citation_issues_dir
        else run_dir / 'audit' / 'section_citation_issues'
    )
    steps = []
    for name, cmd in build_commands(args):
        if name == 'claim_extraction':
            steps.append(prepare_claim_ledger(run_dir, args.preserve_existing_claims))
        steps.append(run_step(name, cmd))
        if name == 'citation_verification':
            steps.append(check_citation_auditor_issues(citation_issues_path))
            steps.append(
                check_section_citation_audits(
                    section_citation_issues_dir,
                    report_path=report_path,
                    require=args.require_section_citation_audits,
                )
            )
    manifest = read_manifest(run_dir)
    manifest_status = manifest.get('status')

    failed_steps = [step['name'] for step in steps if step['returncode'] != 0]
    if manifest and manifest_status != 'pass' and 'global_audit' not in failed_steps:
        failed_steps.append('global_audit')

    passed = not failed_steps
    summary = {
        'status': 'pass' if passed else 'fail',
        'strict': bool(args.strict),
        'strict_citations': bool(args.strict_citations),
        'semantic': bool(args.semantic),
        'run_dir': str(run_dir),
        'report_path': str(report_path),
        'audit_manifest_path': str(run_dir / 'audit_manifest.json'),
        'audit_manifest_status': manifest_status,
        'failed_steps': failed_steps,
        'steps': steps,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))

    if args.strict and not passed:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
