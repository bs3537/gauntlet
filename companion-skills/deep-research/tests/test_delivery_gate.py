#!/usr/bin/env python3
"""Tests for delivery_gate.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'delivery_gate.py')
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def run_gate(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


class DeliveryGateFixtureMixin:
    """Run-directory fixture builders shared by the delivery-gate test classes.

    Kept free of test methods so subclasses do not re-execute the whole parent
    suite just to reuse the helpers.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.report_path = os.path.join(self.tmpdir, 'report.md')
        self.write_report('[1]')
        self.write_ledgers(
            'Acme revenue increased to 10 percent in 2025 as subscription adoption improved.',
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_report(self, citation_label: str) -> None:
        claim = (
            f'Acme revenue increased to 10 percent in 2025 as subscription adoption improved '
            f'{citation_label}.'
        )
        with open(self.report_path, 'w') as f:
            f.write(
                '# Test Research Report\n\n'
                '## Executive Summary\n\n'
                f'{claim}\n\n'
                '## Introduction\n\n'
                '## Main Analysis\n\n'
                '## Synthesis\n\n'
                '## Limitations\n\n'
                '## Recommendations\n\n'
                '## Methodology\n\n'
            )

    def write_ledgers(self, evidence_quote: str) -> None:
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_001', 'display_id': '[1]', 'title': 'Acme Annual Report 2025', 'source_tier': 'primary'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {'evidence_id': 'ev_001', 'source_id': 'src_001', 'quote': evidence_quote},
        ])
        open(os.path.join(self.tmpdir, 'claims.jsonl'), 'w').close()

    def write_run_manifest(self, mode: str) -> None:
        with open(os.path.join(self.tmpdir, 'run_manifest.json'), 'w') as f:
            json.dump({
                'version': '3.0.0',
                'query': 'delivery gate test',
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
                    'plan': 'missing_plan.json',
                    'coverage_map': 'missing_coverage_map.json',
                    'audit_manifest': 'audit_manifest.json',
                },
                'continuation': None,
            }, f)

    def read_manifest(self) -> dict:
        with open(os.path.join(self.tmpdir, 'audit_manifest.json')) as f:
            return json.load(f)


class DeliveryGateTests(DeliveryGateFixtureMixin, unittest.TestCase):
    def test_strict_delivery_gate_passes_supported_package(self):
        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['audit_manifest_status'], 'pass')
        self.assertEqual(out['failed_steps'], [])
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, 'audit_manifest.json')))

        support_step = next(step for step in out['steps'] if step['name'] == 'claim_support')
        self.assertEqual(support_step['summary']['factual_blocking'], 0)

    def test_strict_delivery_gate_blocks_unresolved_report_citation(self):
        self.write_report('[9]')
        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('global_audit', out['failed_steps'])
        manifest = self.read_manifest()
        self.assertEqual(manifest['status'], 'fail')
        self.assertTrue(any(item['code'] == 'report_citation_labels_missing' for item in manifest['critical']))

    def test_strict_delivery_gate_continues_to_audit_after_support_failure(self):
        self.write_ledgers('Acme published governance background in 2025 for board oversight.')
        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('claim_support', out['failed_steps'])
        self.assertIn('global_audit', out['failed_steps'])
        manifest = self.read_manifest()
        self.assertEqual(manifest['status'], 'fail')
        self.assertTrue(any(item['code'] == 'blocking_factual_claims' for item in manifest['critical']))

    def test_strict_delivery_gate_blocks_critical_citation_auditor_issue(self):
        audit_dir = os.path.join(self.tmpdir, 'audit')
        os.makedirs(audit_dir)
        with open(os.path.join(audit_dir, 'citation_issues.json'), 'w') as f:
            json.dump([
                {
                    'claim': 'Acme revenue increased.',
                    'citation': '[1]',
                    'issue_type': 'unsupported_sentence',
                    'severity': 'critical',
                    'suggested_fix': 'Replace the evidence or remove the claim.',
                },
            ], f)

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('citation_auditor_issues', out['failed_steps'])
        citation_step = next(step for step in out['steps'] if step['name'] == 'citation_auditor_issues')
        self.assertEqual(citation_step['summary']['critical_issues'], 1)

    def test_strict_delivery_gate_blocks_critical_section_citation_auditor_issue(self):
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'main_analysis.json'), 'w') as f:
            json.dump({
                'issues': [
                    {
                        'section_id': 'main_analysis',
                        'claim': 'Acme revenue increased.',
                        'citation': '[1]',
                        'issue_type': 'unsupported_sentence',
                        'severity': 'critical',
                        'suggested_fix': 'Replace the evidence or remove the claim.',
                    },
                ],
            }, f)

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('section_citation_audits', out['failed_steps'])
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertEqual(section_step['summary']['audit_files'], 1)
        self.assertEqual(section_step['summary']['critical_issues'], 1)
        self.assertEqual(section_step['summary']['critical_examples'][0]['section_id'], 'main_analysis')

    def test_strict_delivery_gate_allows_noncritical_section_citation_auditor_issue(self):
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'main_analysis.json'), 'w') as f:
            json.dump([
                {
                    'section_id': 'main_analysis',
                    'claim': 'Acme revenue increased.',
                    'citation': '[1]',
                    'issue_type': 'locator_imprecise',
                    'severity': 'medium',
                    'suggested_fix': 'Tighten the locator before final delivery.',
                },
            ], f)

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertEqual(section_step['summary']['audit_files'], 1)
        self.assertEqual(section_step['summary']['critical_issues'], 0)
        self.assertEqual(section_step['summary']['severity_counts']['medium'], 1)

    def test_strict_delivery_gate_requires_section_citation_audits_when_flagged(self):
        out = run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            '--require-section-citation-audits',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertIn('section_citation_audits', out['failed_steps'])
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertTrue(section_step['required'])
        self.assertIn('executive_summary', section_step['summary']['missing_sections'])

    def test_strict_delivery_gate_required_section_citation_audits_pass_when_present(self):
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'executive_summary.json'), 'w') as f:
            json.dump([], f)

        out = run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            '--require-section-citation-audits',
        )

        self.assertEqual(out['status'], 'pass')
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertTrue(section_step['required'])
        self.assertEqual(section_step['summary']['missing_sections'], [])
        self.assertEqual(section_step['summary']['audit_files'], 1)

    def test_strict_delivery_gate_honors_custom_section_citation_audit_dir(self):
        section_dir = os.path.join(self.tmpdir, 'custom_section_audits')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'executive_summary.json'), 'w') as f:
            json.dump([], f)

        out = run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            '--require-section-citation-audits',
            '--section-citation-issues-dir', section_dir,
        )

        self.assertEqual(out['status'], 'pass')
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertEqual(section_step['path'], section_dir)

    def test_strict_delivery_gate_blocks_invalid_section_citation_audit_json(self):
        section_dir = os.path.join(self.tmpdir, 'audit', 'section_citation_issues')
        os.makedirs(section_dir)
        with open(os.path.join(section_dir, 'executive_summary.json'), 'w') as f:
            f.write('{not json')

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('section_citation_audits', out['failed_steps'])
        section_step = next(step for step in out['steps'] if step['name'] == 'section_citation_audits')
        self.assertEqual(len(section_step['summary']['invalid_files']), 1)

    def test_strict_delivery_gate_rebuilds_stale_pass_manifest(self):
        with open(os.path.join(self.tmpdir, 'audit_manifest.json'), 'w') as f:
            json.dump({'status': 'pass'}, f)
        self.write_report('[9]')

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('global_audit', out['failed_steps'])
        manifest = self.read_manifest()
        self.assertEqual(manifest['status'], 'fail')
        self.assertTrue(any(item['code'] == 'report_citation_labels_missing' for item in manifest['critical']))

    def test_strict_delivery_gate_display_map_allows_nonordinal_report_label(self):
        self.write_report('[9]')
        with open(os.path.join(self.tmpdir, 'display_map.json'), 'w') as f:
            json.dump({
                'version': '1.0',
                'label_source': 'report',
                'label_to_source_id': {'9': 'src_001'},
                'display_number_to_source_id': {},
                'source_alias_to_source_id': {},
            }, f)

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['audit_manifest_status'], 'pass')

    def test_strict_delivery_gate_rebuilds_stale_claims_by_default(self):
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'stale_claim',
                'section_id': 'old_draft',
                'text': 'A stale unsupported claim from an older draft should not gate the current report.',
                'claim_type': 'factual',
                'support_status': 'unsupported',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
        ])

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, 'claims.before_delivery_gate.jsonl')))
        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            claims = [json.loads(line) for line in f if line.strip()]
        self.assertTrue(claims)
        self.assertFalse(any(claim.get('claim_id') == 'stale_claim' for claim in claims))

    def test_strict_delivery_gate_runs_semantic_support_when_requested(self):
        sys.path.insert(0, SCRIPTS_DIR)
        from extract_claims import compute_claim_id

        claim_id = compute_claim_id(
            'executive_summary',
            'Acme revenue increased to 10 percent in 2025 as subscription adoption improved [1].',
        )
        judgments_path = os.path.join(self.tmpdir, 'judgments.json')
        with open(judgments_path, 'w') as f:
            json.dump({
                'judgments': [
                    {
                        'claim_id': claim_id,
                        'verdict': 'contradicted',
                        'rationale': 'The evidence contradicts the report claim.',
                    }
                ]
            }, f)

        out = run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            '--semantic',
            '--semantic-judgments', judgments_path,
            '--semantic-sample-supported-rate', '1',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertIn('semantic_claim_support', out['failed_steps'])
        semantic_step = next(step for step in out['steps'] if step['name'] == 'semantic_claim_support')
        self.assertEqual(semantic_step['summary']['contradicted'], 1)

    def test_delivery_gate_ultradeep_strict_blocks_missing_plan_coverage(self):
        self.write_run_manifest('ultradeep')

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict', expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('global_audit', out['failed_steps'])
        manifest = self.read_manifest()
        self.assertTrue(any(item['code'] == 'missing_plan' for item in manifest['critical']))

    def test_delivery_gate_deep_strict_allows_plan_coverage_warnings(self):
        self.write_run_manifest('deep')

        out = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')

        self.assertEqual(out['status'], 'pass')
        manifest = self.read_manifest()
        self.assertTrue(any(item['code'] == 'missing_plan' for item in manifest['warnings']))
        self.assertFalse(any(item['code'] == 'missing_plan' for item in manifest['critical']))


class VerifiedFindingsArtifactTests(DeliveryGateFixtureMixin, unittest.TestCase):
    """P2-H: an opt-in honest-partial artifact.

    Never auto-delivered and never a substitute for the report. It exists so a
    run that cannot pass the strict gate after three fix cycles can still hand
    the user the claims that did survive, stamped Partial, instead of nothing.
    """

    def artifact_path(self) -> str:
        return os.path.join(self.tmpdir, 'verified_findings.md')

    def test_artifact_is_not_written_unless_requested(self):
        run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')
        self.assertFalse(os.path.exists(self.artifact_path()))

    def test_artifact_is_written_when_requested(self):
        run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--emit-verified-findings', self.artifact_path(),
        )
        self.assertTrue(os.path.exists(self.artifact_path()))
        with open(self.artifact_path()) as f:
            self.assertIn('**Status: Partial**', f.read())

    def test_emitting_the_artifact_does_not_change_the_gate_decision(self):
        without = run_gate('--dir', self.tmpdir, '--report', self.report_path, '--strict')
        with_artifact = run_gate(
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            '--emit-verified-findings', self.artifact_path(),
        )
        self.assertEqual(without['status'], with_artifact['status'])
        self.assertEqual(without['failed_steps'], with_artifact['failed_steps'])


class VerifiedFindingsRenderingTests(unittest.TestCase):
    """Unit-level rendering contract for the P2-H artifact.

    Exercised directly rather than through the CLI because the delivery gate
    rebuilds claims.jsonl during claim extraction, so a pre-seeded ledger would
    never reach the renderer.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, SCRIPTS_DIR)
        from delivery_gate import write_verified_findings
        cls.render = staticmethod(write_verified_findings)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))
        self.out = os.path.join(self.tmpdir, 'verified_findings.md')

    def render_with(self, claims: list[dict], manifest: dict | None = None) -> str:
        from pathlib import Path
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), claims)
        self.render(Path(self.tmpdir), Path(self.out), manifest or {})
        with open(self.out) as f:
            return f.read()

    def test_lists_only_supported_claims(self):
        text = self.render_with([
            {
                'claim_id': 'clm_ok', 'claim_type': 'factual', 'support_status': 'supported',
                'text': 'This claim survived verification.', 'cited_source_ids': ['src_001'],
            },
            {
                'claim_id': 'clm_bad', 'claim_type': 'factual', 'support_status': 'needs_review',
                'text': 'This claim did not survive verification.', 'cited_source_ids': ['src_001'],
            },
        ])

        findings, excluded = text.split('## Excluded by verification')
        self.assertIn('This claim survived verification.', findings)
        self.assertNotIn('This claim did not survive verification.', findings)
        self.assertIn('clm_bad', excluded)

    def test_is_always_stamped_partial(self):
        text = self.render_with([
            {
                'claim_id': 'clm_ok', 'claim_type': 'factual', 'support_status': 'supported',
                'text': 'Everything here is supported.', 'cited_source_ids': ['src_001'],
            },
        ])
        self.assertIn('**Status: Partial**', text)

    def test_reports_when_nothing_survived(self):
        text = self.render_with([
            {
                'claim_id': 'clm_bad', 'claim_type': 'factual', 'support_status': 'unsupported',
                'text': 'Nothing here is supported.', 'cited_source_ids': ['src_001'],
            },
        ])
        self.assertIn('No factual claim survived verification', text)

    def test_carries_run_status_reasons_into_coverage_section(self):
        text = self.render_with(
            [
                {
                    'claim_id': 'clm_ok', 'claim_type': 'factual', 'support_status': 'supported',
                    'text': 'A supported claim.', 'cited_source_ids': ['src_001'],
                },
            ],
            manifest={'run_status_reasons': [
                {'code': 'lane_not_fully_covered', 'message': 'One lane shipped with a disclosed gap'},
            ]},
        )
        self.assertIn('lane_not_fully_covered', text)
        self.assertIn('One lane shipped with a disclosed gap', text)

    def test_missing_claims_ledger_still_renders_an_honest_artifact(self):
        from pathlib import Path
        self.render(Path(self.tmpdir), Path(self.out), {})
        with open(self.out) as f:
            text = f.read()
        self.assertIn('**Status: Partial**', text)
        self.assertIn('No factual claim survived verification', text)


if __name__ == '__main__':
    unittest.main()
