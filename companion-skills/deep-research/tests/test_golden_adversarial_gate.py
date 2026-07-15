#!/usr/bin/env python3
"""Golden adversarial tests for the strict delivery gate."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
DELIVERY_GATE = os.path.join(ROOT, 'scripts', 'delivery_gate.py')
MERGE_SUBAGENT_EVIDENCE = os.path.join(ROOT, 'scripts', 'merge_subagent_evidence.py')


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_json(script: str, *args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


class GoldenAdversarialGateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.report_path = os.path.join(self.tmpdir, 'report.md')
        open(os.path.join(self.tmpdir, 'claims.jsonl'), 'w').close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_report(self, claim_sentence: str) -> None:
        with open(self.report_path, 'w') as f:
            f.write(
                '# Golden Adversarial Gate Report\n\n'
                '## Executive Summary\n\n'
                f'{claim_sentence}\n\n'
                '## Introduction\n\n'
                '## Main Analysis\n\n'
                '## Synthesis\n\n'
                '## Limitations\n\n'
                '## Recommendations\n\n'
                '## Methodology\n\n'
            )

    def write_single_source_package(
        self,
        claim_sentence: str,
        evidence_quote: str,
        *,
        source_id: str = 'src_001',
        evidence_id: str = 'ev_001',
        source: dict | None = None,
    ) -> None:
        self.write_report(claim_sentence)
        source_row = {
            'source_id': source_id,
            'display_id': '[1]',
            'title': 'Golden Source',
            'source_tier': 'primary',
        }
        if source:
            source_row.update(source)
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [source_row])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': evidence_id,
                'source_id': source_id,
                'quote': evidence_quote,
                'evidence_type': 'direct_quote',
            },
        ])

    def run_gate(self, expect_fail: bool = False) -> dict:
        return run_json(
            DELIVERY_GATE,
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--strict',
            expect_fail=expect_fail,
        )

    def read_claims(self) -> list[dict]:
        return read_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'))

    def test_gate_blocks_negation_pair(self):
        self.write_single_source_package(
            'The therapy improved overall survival [1].',
            'The therapy did not improve overall survival in the study.',
        )

        out = self.run_gate(expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertIn('claim_support', out['failed_steps'])
        claim = self.read_claims()[0]
        self.assertEqual(claim['support_status'], 'needs_review')
        self.assertIn('negation mismatch', claim['_support_notes'])

    def test_gate_passes_supported_paraphrase_pair(self):
        self.write_single_source_package(
            "Acme's operating margin widened to 21% in 2025 [1].",
            'Acme reported 2025 operating margin of 21%, up from 18% a year earlier.',
        )

        out = self.run_gate()

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(self.read_claims()[0]['support_status'], 'supported')

    def test_gate_blocks_vacuous_zero_sixty_floor_case(self):
        self.write_single_source_package(
            'The therapy did not improve overall survival [1].',
            'Regional weather patterns shifted across commodity markets in 2025.',
        )

        out = self.run_gate(expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        claim = self.read_claims()[0]
        self.assertEqual(claim['support_status'], 'needs_review')
        self.assertLess(claim['_support_score'], 0.35)

    def test_gate_blocks_year_regression_case(self):
        self.write_single_source_package(
            'The trial started enrollment in 2019 for the pivotal program [1].',
            'The trial started enrollment in 2024 for the pivotal program.',
        )

        out = self.run_gate(expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        claim = self.read_claims()[0]
        self.assertIn(claim['support_status'], ('partial', 'needs_review'))
        self.assertLess(claim['_support_score'], 0.6)
        self.assertIn('year mismatch', claim['_support_notes'])

    def test_gate_uses_display_map_when_registration_order_is_shuffled(self):
        self.write_report('Acme revenue increased to 10% in 2025 [1].')
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_wrong_first', 'title': 'Wrong First Source', 'source_tier': 'secondary'},
            {'source_id': 'src_actual_label_one', 'title': 'Actual Source One', 'source_tier': 'primary'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {'evidence_id': 'ev_wrong', 'source_id': 'src_wrong_first', 'quote': 'This evidence is unrelated.'},
            {
                'evidence_id': 'ev_actual',
                'source_id': 'src_actual_label_one',
                'quote': 'Acme revenue increased to 10% in 2025.',
            },
        ])
        with open(os.path.join(self.tmpdir, 'display_map.json'), 'w') as f:
            json.dump({
                'version': '1.0',
                'label_source': 'report',
                'label_to_source_id': {'1': 'src_actual_label_one'},
                'display_number_to_source_id': {'1': 'src_wrong_first'},
                'source_alias_to_source_id': {},
            }, f)

        out = self.run_gate()

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(self.read_claims()[0]['cited_source_ids'], ['src_actual_label_one'])
        self.assertEqual(self.read_claims()[0]['evidence_ids'], ['ev_actual'])

    def test_subagent_merge_round_trip_then_gate_is_idempotent(self):
        subagent_dir = os.path.join(self.tmpdir, 'subagent_outputs')
        os.makedirs(subagent_dir)
        open(os.path.join(self.tmpdir, 'sources.jsonl'), 'w').close()
        open(os.path.join(self.tmpdir, 'evidence.jsonl'), 'w').close()
        write_jsonl(os.path.join(subagent_dir, 'lane_financials.evidence.jsonl'), [
            {
                'claim': 'Acme revenue increased to 10 percent in 2025.',
                'evidence_quote': 'Acme revenue increased to 10 percent in 2025 as subscription adoption improved.',
                'source_url': 'https://example.com/report?utm_source=x&id=42#financials',
                'source_title': 'Acme Annual Report',
                'source_type': 'company_ir',
                'source_tier': 'primary',
                'locator': 'page 5',
                'lane_id': 'lane_financials',
                'query_family_id': 'qf_financials',
            },
        ])

        first = run_json(MERGE_SUBAGENT_EVIDENCE, '--dir', self.tmpdir)
        second = run_json(MERGE_SUBAGENT_EVIDENCE, '--dir', self.tmpdir)
        self.write_report('Acme revenue increased to 10 percent in 2025 [1].')
        out = self.run_gate()

        self.assertEqual(first['sources_added'], 1)
        self.assertEqual(first['evidence_added'], 1)
        self.assertEqual(second['sources_added'], 0)
        self.assertEqual(second['evidence_added'], 0)
        self.assertEqual(out['status'], 'pass')
        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(sources[0]['canonical_locator'], 'https://example.com/report?id=42')
        self.assertEqual(evidence[0]['source_id'], sources[0]['source_id'])

    def test_doi_locator_source_passes_strict_gate(self):
        self.write_single_source_package(
            'The DOI-backed study reported 42 participants in 2025 [1].',
            'The DOI-backed study reported 42 participants in 2025.',
            source={
                'raw_url': 'doi:10.1234/golden.adversarial',
                'canonical_locator': 'doi:10.1234/golden.adversarial',
                'source_type': 'academic',
                'editorial_notice_status': 'none',
                'scite_checked_at': '2026-07-05T00:00:00Z',
            },
        )

        out = self.run_gate()

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['audit_manifest_status'], 'pass')


if __name__ == '__main__':
    unittest.main()
