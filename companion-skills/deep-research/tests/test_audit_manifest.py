#!/usr/bin/env python3
"""Tests for audit_manifest.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'audit_manifest.py')


def write_jsonl(path: str, rows: list[dict]):
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def write_json(path: str, payload: dict):
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
        f.write('\n')


def run_am(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


class AuditManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.report_path = os.path.join(self.tmpdir, 'report.md')
        with open(self.report_path, 'w') as f:
            f.write('## Finding 1\n\nThe source-backed claim is fully supported [1].\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_valid_ledgers(self):
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_001', 'display_id': '[1]', 'url': 'https://example.com/source', 'source_tier': 'primary'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_001',
                'source_id': 'src_001',
                'quote': 'The source-backed claim is fully supported by this evidence row, which includes specific factual context, source language, and enough surrounding detail for verification.',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_001',
                'section_id': 'finding_1',
                'text': 'The source-backed claim is fully supported.',
                'claim_type': 'factual',
                'support_status': 'supported',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
        ])

    def write_run_manifest(self, mode: str, plan: str = 'plan.json', coverage_map: str = 'coverage_map.json'):
        write_json(os.path.join(self.tmpdir, 'run_manifest.json'), {
            'version': '3.0.0',
            'query': 'audit test',
            'mode': mode,
            'started_at': '2026-07-05T00:00:00Z',
            'finished_at': None,
            'assumptions': [],
            'provider_config': {'primary': 'perplexity-search-mcp'},
            'report_dir': self.tmpdir,
            'artifact_paths': {
                'sources': 'sources.jsonl',
                'evidence': 'evidence.jsonl',
                'claims': 'claims.jsonl',
                'report': 'report.md',
                'plan': plan,
                'coverage_map': coverage_map,
                'audit_manifest': 'audit_manifest.json',
            },
            'continuation': None,
        })

    def write_plan_and_coverage(self, mode: str, lane_status: str = 'planned', executed: bool = False):
        write_json(os.path.join(self.tmpdir, 'plan.json'), {
            'version': '1.0',
            'mode': mode,
            'created_at': '2026-07-05T00:00:00Z',
            'lanes': [
                {
                    'lane_id': 'lane_primary',
                    'role': 'primary_source',
                    'objective': 'Primary sources',
                    'query_families': [
                        {
                            'query_family_id': 'lane_primary_core',
                            'description': 'Primary-source query family',
                            'queries': ['primary sources'],
                        }
                    ],
                    'expected_source_min': 25,
                    'expected_roles': ['primary_source'],
                    'stop_conditions': ['Target met or gap disclosed'],
                }
            ],
        })
        write_json(os.path.join(self.tmpdir, 'coverage_map.json'), {
            'version': '1.0',
            'generated_at': '2026-07-05T00:01:00Z',
            'mode': mode,
            'lane_coverage': [
                {
                    'lane_id': 'lane_primary',
                    'planned': True,
                    'executed': executed,
                    'executed_role': None,
                    'source_count': 1 if executed else 0,
                    'evidence_count': 1 if executed else 0,
                    'provider_call_count': 1 if executed else 0,
                    'subagent_count': 0,
                    'expected_source_min': 25,
                    'missing_from_plan': not executed,
                    'status': lane_status,
                    'gaps': [],
                }
            ],
            'query_family_coverage': [
                {
                    'query_family_id': 'lane_primary_core',
                    'lane_id': 'lane_primary',
                    'planned': True,
                    'executed': executed,
                    'provider_call_count': 1 if executed else 0,
                    'retained_source_count': 1 if executed else 0,
                    'status': 'in_progress' if executed else 'planned',
                }
            ],
            'overall': {
                'planned_lanes': 1,
                'executed_lanes': 1 if executed else 0,
                'covered_lanes': 0,
                'gap_disclosed_lanes': 0,
                'bounded_lanes': 0,
                'below_target_lanes': 1,
                'total_sources': 1,
                'total_evidence': 1,
                'status': 'incomplete',
            },
        })
    def test_strict_passes_valid_package(self):
        self.write_valid_ledgers()
        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict')
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['counts']['critical_findings'], 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, 'audit_manifest.json')))

    def test_strict_fails_blocking_factual_claim(self):
        self.write_valid_ledgers()
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_001',
                'section_id': 'finding_1',
                'text': 'The source-backed claim is only partially checked.',
                'claim_type': 'factual',
                'support_status': 'partial',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
        ])
        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['counts']['blocking_factual_claims'], 1)
        self.assertTrue(any(item['code'] == 'blocking_factual_claims' for item in out['critical']))

    def test_strict_fails_missing_report_citation_label(self):
        self.write_valid_ledgers()
        with open(self.report_path, 'w') as f:
            f.write('## Finding 1\n\nThis claim cites a missing source label [9].\n')
        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['counts']['missing_report_citations'], 1)

    def test_display_map_resolves_nonordinal_report_label(self):
        self.write_valid_ledgers()
        with open(self.report_path, 'w') as f:
            f.write('## Finding 1\n\nThis claim cites a persisted display label [9].\n')
        with open(os.path.join(self.tmpdir, 'display_map.json'), 'w') as f:
            json.dump({
                'version': '1.0',
                'label_source': 'report',
                'label_to_source_id': {'9': 'src_001'},
                'display_number_to_source_id': {},
                'source_alias_to_source_id': {},
            }, f)

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict')
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['counts']['missing_report_citations'], 0)

    def test_low_information_evidence_warns(self):
        self.write_valid_ledgers()
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_001',
                'source_id': 'src_001',
                'quote': 'The source-backed claim is fully supported by this evidence row, which includes specific factual context, source language, and enough surrounding detail for verification.',
            },
            {
                'evidence_id': 'ev_low',
                'source_id': 'src_001',
                'evidence_quote': 'Accessibility Statement Skip Navigation Client Login Send a Release Privacy Policy Terms of Use',
            },
        ])
        out = run_am('--dir', self.tmpdir, '--report', self.report_path)
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['counts']['low_information_evidence'], 1)
        self.assertTrue(any(item['code'] == 'low_information_evidence' for item in out['warnings']))

    def test_claim_field_alone_does_not_count_as_evidence_text(self):
        self.write_valid_ledgers()
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_001',
                'source_id': 'src_001',
                'claim': 'The source-backed claim is fully supported.',
            },
        ])

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertTrue(any(item['code'] == 'missing_evidence_text' for item in out['critical']))

    def test_strict_fails_critical_section_citation_auditor_issue(self):
        self.write_valid_ledgers()
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'finding_1.json'), 'w') as f:
            json.dump([
                {
                    'section_id': 'finding_1',
                    'claim': 'The source-backed claim is fully supported.',
                    'citation': '[1]',
                    'issue_type': 'unsupported_sentence',
                    'severity': 'critical',
                    'suggested_fix': 'Replace the evidence or delete the claim.',
                },
            ], f)

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['counts']['citation_auditor_section_files'], 1)
        self.assertEqual(out['counts']['citation_auditor_critical_issues'], 1)
        self.assertEqual(out['citation_auditor']['section_issues'], 1)
        self.assertTrue(any(item['code'] == 'citation_auditor_critical_issues' for item in out['critical']))

    def test_noncritical_section_citation_auditor_issue_warns(self):
        self.write_valid_ledgers()
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'finding_1.json'), 'w') as f:
            json.dump({
                'issues': [
                    {
                        'section_id': 'finding_1',
                        'claim': 'The source-backed claim is fully supported.',
                        'citation': '[1]',
                        'issue_type': 'locator_imprecise',
                        'severity': 'medium',
                        'suggested_fix': 'Tighten the locator.',
                    },
                ],
            }, f)

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['counts']['citation_auditor_section_files'], 1)
        self.assertEqual(out['counts']['citation_auditor_section_issues'], 1)
        self.assertTrue(any(item['code'] == 'citation_auditor_noncritical_issues' for item in out['warnings']))

    def test_invalid_section_citation_auditor_json_is_critical(self):
        self.write_valid_ledgers()
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'finding_1.json'), 'w') as f:
            f.write('{not json')

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['counts']['citation_auditor_invalid_files'], 1)
        self.assertTrue(any(item['code'] == 'citation_auditor_invalid_json' for item in out['critical']))

    def test_standard_missing_plan_warns_not_critical_under_strict(self):
        self.write_valid_ledgers()
        self.write_run_manifest('standard', plan='missing_plan.json', coverage_map='missing_coverage_map.json')

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        warning_codes = {item['code'] for item in out['warnings']}
        critical_codes = {item['code'] for item in out['critical']}
        self.assertIn('missing_plan', warning_codes)
        self.assertIn('missing_coverage_map', warning_codes)
        self.assertIn('source_count_below_mode_target', warning_codes)
        self.assertNotIn('missing_plan', critical_codes)

    def test_deep_below_plan_coverage_warns_under_strict(self):
        self.write_valid_ledgers()
        self.write_run_manifest('deep')
        self.write_plan_and_coverage('deep', lane_status='below_target', executed=True)

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        self.assertTrue(any(item['code'] == 'lane_source_count_below_plan' for item in out['warnings']))
        self.assertFalse(any(item['code'] == 'lane_source_count_below_plan' for item in out['critical']))

    def test_ultradeep_strict_missing_plan_is_critical(self):
        self.write_valid_ledgers()
        self.write_run_manifest('ultradeep', plan='missing_plan.json', coverage_map='missing_coverage_map.json')

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertTrue(any(item['code'] == 'missing_plan' for item in out['critical']))
        self.assertTrue(any(item['code'] == 'source_count_below_mode_target' for item in out['critical']))

    def test_ultradeep_non_strict_missing_plan_warns(self):
        self.write_valid_ledgers()
        self.write_run_manifest('ultradeep', plan='missing_plan.json', coverage_map='missing_coverage_map.json')

        out = run_am('--dir', self.tmpdir, '--report', self.report_path)

        self.assertEqual(out['status'], 'pass')
        self.assertTrue(any(item['code'] == 'missing_plan' for item in out['warnings']))
        self.assertFalse(any(item['code'] == 'missing_plan' for item in out['critical']))

    def test_peer_reviewed_source_missing_scite_editorial_notice_warns(self):
        self.write_valid_ledgers()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {
                'source_id': 'src_001',
                'display_id': '[1]',
                'url': 'https://doi.org/10.1234/example',
                'canonical_locator': 'doi:10.1234/example',
                'source_type': 'academic',
                'source_tier': 'primary',
                'title': 'Peer Reviewed Source',
            },
        ])

        out = run_am('--dir', self.tmpdir, '--report', self.report_path)

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['counts']['scite_editorial_notice_missing'], 1)
        self.assertTrue(any(item['code'] == 'scite_editorial_notice_missing' for item in out['warnings']))

    def test_retracted_peer_reviewed_source_is_critical(self):
        self.write_valid_ledgers()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {
                'source_id': 'src_001',
                'display_id': '[1]',
                'url': 'https://doi.org/10.1234/retracted',
                'canonical_locator': 'doi:10.1234/retracted',
                'source_type': 'academic',
                'source_tier': 'primary',
                'title': 'Retracted Source',
                'editorial_notice_status': 'retracted',
                'scite_checked_at': '2026-07-05T00:00:00Z',
            },
        ])

        out = run_am('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['counts']['scite_editorial_notice_blocking'], 1)
        self.assertTrue(any(item['code'] == 'scite_editorial_notice_blocking' for item in out['critical']))


if __name__ == '__main__':
    unittest.main()
