#!/usr/bin/env python3
"""Tests for verify_claim_support_llm.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'verify_claim_support_llm.py')
AUDIT_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'audit_manifest.py')


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def run_vcs_llm(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


def run_audit(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, AUDIT_SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


class VerifyClaimSupportLlmTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_001', 'display_id': '[1]', 'title': 'Acme Results', 'source_tier': 'primary'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_001',
                'source_id': 'src_001',
                'quote': 'Acme revenue increased to 10 percent in 2025 as subscription adoption improved.',
            },
            {
                'evidence_id': 'ev_002',
                'source_id': 'src_001',
                'quote': 'Acme revenue declined in 2025 after subscription adoption weakened.',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'section_id': 'main_analysis',
                'text': 'Acme revenue increased to 10 percent in 2025 as subscription adoption improved.',
                'claim_type': 'factual',
                'support_status': 'partial',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
            {
                'claim_id': 'bbbbbbbbbbbbbbbb',
                'section_id': 'main_analysis',
                'text': 'Acme revenue increased in 2025.',
                'claim_type': 'factual',
                'support_status': 'supported',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_judgments(self, rows: list[dict]) -> str:
        path = os.path.join(self.tmpdir, 'judgments.json')
        with open(path, 'w') as f:
            json.dump({'judgments': rows}, f)
        return path

    def read_claims(self) -> list[dict]:
        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_entailment_upgrades_blocking_claim_and_pins_judge(self):
        judgments = self.write_judgments([
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'verdict': 'entailed',
                'rationale': 'The evidence directly states the increase, amount, year, and driver.',
            },
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--judge-model', 'mock-judge',
            '--judge-version', '2026-07-05',
            '--sample-supported-rate', '0',
            '--strict',
        )

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['upgraded_to_supported'], 1)
        claims = self.read_claims()
        claim = next(row for row in claims if row['claim_id'] == 'aaaaaaaaaaaaaaaa')
        self.assertEqual(claim['support_status'], 'supported')
        self.assertEqual(claim['support_status_llm'], 'entailed')
        self.assertEqual(claim['support_judge_model'], 'mock-judge')
        self.assertEqual(claim['support_judge_version'], '2026-07-05')
        self.assertEqual(claim['semantic_gate'], 'pass')

    def test_contradiction_fails_strict_and_audit_blocks(self):
        judgments = self.write_judgments([
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'verdict': 'contradicted',
                'rationale': 'The evidence says revenue declined, not increased.',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'section_id': 'main_analysis',
                'text': 'Acme revenue increased in 2025.',
                'claim_type': 'factual',
                'support_status': 'partial',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_002'],
            },
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--judge-model', 'mock-judge',
            '--judge-version', '2026-07-05',
            '--strict',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['contradicted'], 1)
        audit = run_audit('--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(audit['counts']['semantic_contradictions'], 1)
        self.assertTrue(any(item['code'] == 'semantic_contradictions' for item in audit['critical']))

    def test_missing_judgment_fails_strict_without_silent_pass(self):
        judgments = self.write_judgments([])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
            '--strict',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['missing_judgments'], 1)

    def test_supported_sampling_is_deterministic_and_optional(self):
        judgments = self.write_judgments([
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'verdict': 'entailed',
                'rationale': 'Supported by evidence.',
            },
            {
                'claim_id': 'bbbbbbbbbbbbbbbb',
                'verdict': 'entailed',
                'rationale': 'Supported sample also passes.',
            },
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '1',
            '--strict',
        )

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['selected'], 2)
        self.assertEqual(out['judged'], 2)

    def test_extra_claim_id_fails_batch_without_applying_upgrades(self):
        """A judge that returns an ID outside the selection has drifted: reject the batch."""
        judgments = self.write_judgments([
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'entailed', 'rationale': 'Supported.'},
            {'claim_id': 'zzzzzzzzzzzzzzzz', 'verdict': 'entailed', 'rationale': 'Not in selection.'},
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
            '--strict',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['extra_ids'], 1)
        self.assertEqual(out['upgraded_to_supported'], 0)
        claim = next(row for row in self.read_claims() if row['claim_id'] == 'aaaaaaaaaaaaaaaa')
        self.assertEqual(claim['support_status'], 'partial')
        self.assertNotIn('support_status_llm', claim)

    def test_duplicate_claim_id_fails_batch_without_applying_upgrades(self):
        """Conflicting duplicate verdicts must not silently resolve last-wins."""
        judgments = self.write_judgments([
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'contradicted', 'rationale': 'First verdict.'},
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'entailed', 'rationale': 'Second, conflicting.'},
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
            '--strict',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['duplicate_ids'], 1)
        self.assertEqual(out['upgraded_to_supported'], 0)
        claim = next(row for row in self.read_claims() if row['claim_id'] == 'aaaaaaaaaaaaaaaa')
        self.assertEqual(claim['support_status'], 'partial')

    def test_invalid_verdict_fails_batch_without_applying_upgrades(self):
        """An unrecognized verdict string is drift, not a row to skip."""
        judgments = self.write_judgments([
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'probably_fine', 'rationale': 'Out of vocabulary.'},
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
            '--strict',
            expect_fail=True,
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['invalid_verdicts'], 1)
        self.assertEqual(out['upgraded_to_supported'], 0)
        claim = next(row for row in self.read_claims() if row['claim_id'] == 'aaaaaaaaaaaaaaaa')
        self.assertEqual(claim['support_status'], 'partial')

    def test_clean_batch_reports_zero_integrity_violations(self):
        judgments = self.write_judgments([
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'entailed', 'rationale': 'Supported.'},
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
            '--strict',
        )

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['extra_ids'], 0)
        self.assertEqual(out['duplicate_ids'], 0)
        self.assertEqual(out['invalid_verdicts'], 0)
        self.assertEqual(out['judge_batch_integrity'], 'ok')

    def test_integrity_failure_is_non_blocking_without_strict(self):
        judgments = self.write_judgments([
            {'claim_id': 'zzzzzzzzzzzzzzzz', 'verdict': 'entailed', 'rationale': 'Not in selection.'},
        ])

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--sample-supported-rate', '0',
        )

        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['extra_ids'], 1)

    def test_write_prompt_does_not_require_live_judge_with_judgments(self):
        judgments = self.write_judgments([
            {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'entailed', 'rationale': 'Supported.'},
        ])
        prompt_path = os.path.join(self.tmpdir, 'semantic_prompt.json')

        out = run_vcs_llm(
            'verify',
            '--dir', self.tmpdir,
            '--judgments', judgments,
            '--write-prompt', prompt_path,
            '--sample-supported-rate', '0',
            '--strict',
        )

        self.assertEqual(out['status'], 'pass')
        with open(prompt_path) as f:
            payload = json.load(f)
        self.assertEqual(payload['allowed_verdicts'], ['entailed', 'contradicted', 'insufficient'])
        self.assertEqual(payload['claims'][0]['claim_id'], 'aaaaaaaaaaaaaaaa')


if __name__ == '__main__':
    unittest.main()
