#!/usr/bin/env python3
"""Tests for verify_claim_support.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'verify_claim_support.py')


def run_vcs(*args: str, expect_fail: bool = False) -> dict | str:
    """Run verify_claim_support.py."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    stdout = result.stdout.strip()
    if stdout.startswith('{'):
        return json.loads(stdout)
    return stdout


def write_jsonl(path: str, rows: list[dict]):
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


class TestVerifySupported(unittest.TestCase):
    """Claims with matching evidence should be supported."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Sources
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_quantum_001', 'title': 'Quantum Computing 2024'},
        ])
        # Evidence with clear overlap to the claim
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_shor_001',
                'source_id': 'src_quantum_001',
                'quote': "Shor's algorithm can factor large integers exponentially faster than any known classical algorithm, threatening RSA-2048 encryption.",
                'evidence_type': 'direct_quote',
            },
        ])
        # Claim that matches the evidence
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_factor_001',
                'section_id': 'finding_1',
                'text': "Shor's algorithm can factor large numbers exponentially faster than classical methods, threatening RSA-2048.",
                'claim_type': 'factual',
                'cited_source_ids': ['src_quantum_001'],
                'evidence_ids': ['ev_shor_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_supported_claim(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['factual_unsupported'], 0)

        # Check updated claims file
        claims = []
        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            for line in f:
                claims.append(json.loads(line))
        self.assertEqual(claims[0]['support_status'], 'supported')


class TestVerifyEvidenceQuoteFallback(unittest.TestCase):
    """Search-as-Code evidence_quote rows should count as evidence."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_sac_001', 'title': 'Search-as-Code Source'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_sac_001',
                'source_id': 'src_sac_001',
                'evidence_quote': 'Search-as-Code writes persisted evidence rows with an evidence_quote field for source snippets.',
                'evidence_type': 'search_snippet',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_sac_001',
                'section_id': 'finding_1',
                'text': 'Search-as-Code writes persisted evidence rows with an evidence_quote field for source snippets.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_sac_001'],
                'evidence_ids': ['ev_sac_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_evidence_quote_field_supports_claim(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict')
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['factual_blocking'], 0)

        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            claims = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(claims[0]['support_status'], 'supported')
        self.assertEqual(claims[0]['_support_evidence_count'], 1)


class TestVerifyRejectsMalformedEvidenceClaimField(unittest.TestCase):
    """An evidence row's own claim field should not support report claims."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_claim_only', 'title': 'Malformed Evidence Source'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_claim_only',
                'source_id': 'src_claim_only',
                'claim': 'The therapy improved overall survival.',
                'evidence_type': 'malformed',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_claim_only',
                'section_id': 'finding_1',
                'text': 'The therapy improved overall survival.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_claim_only'],
                'evidence_ids': ['ev_claim_only'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_claim_field_is_not_evidence_text(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['factual_needs_review'], 1)

        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            claims = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(claims[0]['support_status'], 'needs_review')
        self.assertEqual(claims[0]['_support_evidence_count'], 0)


class TestVerifyUnsupported(unittest.TestCase):
    """Claims without evidence should be unsupported."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_no_ev_001',
                'section_id': 'finding_1',
                'text': 'The population of Mars is 500 million as of 2025.',
                'claim_type': 'factual',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unsupported_no_evidence(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        self.assertEqual(out['factual_unsupported'], 1)
        self.assertEqual(out['status'], 'pass')  # Non-strict by default

    def test_strict_fails(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')


class TestVerifyMixed(unittest.TestCase):
    """Mixed claim types with different thresholds."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_spec_001',
                'section_id': 'finding_1',
                'text': 'Quantum computers might eventually solve protein folding in real time.',
                'claim_type': 'speculation',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
            {
                'claim_id': 'clm_rec_001',
                'section_id': 'recommendations',
                'text': 'Organizations should begin PQC migration planning immediately.',
                'claim_type': 'recommendation',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_speculation_passes(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        # Speculation doesn't need evidence
        claims = []
        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            for line in f:
                claims.append(json.loads(line))
        spec = [c for c in claims if c['claim_type'] == 'speculation'][0]
        self.assertEqual(spec['support_status'], 'supported')


class TestVerifyPartial(unittest.TestCase):
    """Evidence with partial overlap should result in partial status."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_nist_001', 'title': 'NIST PQC Standards'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_nist_001',
                'source_id': 'src_nist_001',
                'quote': 'NIST announced the standardization of CRYSTALS-Kyber for key encapsulation.',
                'evidence_type': 'direct_quote',
            },
        ])
        # Claim mentions NIST but adds unverified detail about timeline
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_nist_time',
                'section_id': 'finding_2',
                'text': 'NIST standardized four lattice-based algorithms in 2024, covering both encryption and signatures.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_nist_001'],
                'evidence_ids': ['ev_nist_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_partial_support(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'pass')
        claims = []
        with open(os.path.join(self.tmpdir, 'claims.jsonl')) as f:
            for line in f:
                claims.append(json.loads(line))
        # Should not be fully supported due to number/detail mismatch.
        self.assertIn(claims[0]['support_status'], ('partial', 'needs_review'))


class TestStrictBlockingStatuses(unittest.TestCase):
    """Strict mode should block factual claims that need review or are partial."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_empty', 'title': 'Source without captured evidence'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_review_001',
                'section_id': 'finding_1',
                'text': 'The cited source proves a specific factual claim that has not been captured.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_empty'],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_strict_fails_needs_review(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['factual_needs_review'], 1)
        self.assertEqual(out['factual_blocking'], 1)


class TestStrictBlocksLexicalContradictions(unittest.TestCase):
    """Strict mode should block high-overlap evidence with lexical contradiction guards."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {'source_id': 'src_revenue', 'title': 'Revenue Update'},
        ])
        write_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'), [
            {
                'evidence_id': 'ev_revenue',
                'source_id': 'src_revenue',
                'quote': 'Revenue decreased in 2024.',
                'evidence_type': 'direct_quote',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_revenue',
                'section_id': 'finding_1',
                'text': 'Revenue increased in 2024.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_revenue'],
                'evidence_ids': ['ev_revenue'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_strict_fails_direction_mismatch(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['factual_blocking'], 1)
        self.assertEqual(out['factual_needs_review'], 1)


class TestSupportScore(unittest.TestCase):
    """Unit tests for compute_support_score."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from verify_claim_support import compute_support_score
        cls.score = staticmethod(compute_support_score)

    def test_identical_text(self):
        status, score, _ = self.score(
            'RSA-2048 uses 2048-bit keys for encryption.',
            ['RSA-2048 uses 2048-bit keys for encryption.'],
        )
        self.assertEqual(status, 'supported')
        self.assertGreater(score, 0.8)

    def test_no_evidence(self):
        status, score, _ = self.score('Any claim text.', [])
        self.assertEqual(status, 'unsupported')
        self.assertEqual(score, 0.0)

    def test_unrelated_evidence(self):
        status, score, _ = self.score(
            'The moon landing occurred in 1969.',
            ['Bananas are a good source of potassium and fiber.'],
        )
        self.assertIn(status, ('needs_review', 'unsupported'))
        self.assertLess(score, 0.35)

    def test_full_year_mismatch_does_not_get_century_credit(self):
        status, score, notes = self.score(
            'The trial started in 2019.',
            ['The trial started in 2024.'],
        )
        self.assertNotEqual(status, 'supported')
        self.assertLess(score, 0.6)
        self.assertIn('year mismatch', notes)

    def test_extract_years_returns_full_years_not_century_prefixes(self):
        from verify_claim_support import extract_years
        self.assertEqual(extract_years('The trial ran from 2019 to 2024.'), {'2019', '2024'})

    def test_year_only_overlap_does_not_hit_supported_floor(self):
        status, score, notes = self.score(
            'The platform launched in 2024.',
            ['The committee met in 2024.'],
        )
        self.assertNotEqual(status, 'supported')
        self.assertLess(score, 0.6)
        self.assertIn('low lexical overlap', notes)

    def test_no_feature_floor_for_unrelated_claim(self):
        status, score, notes = self.score(
            'The therapy did not improve overall survival.',
            ['Weather patterns shifted across regional markets.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertLess(score, 0.35)
        self.assertIn('low lexical overlap', notes)

    def test_negation_mismatch_caps_support(self):
        status, score, notes = self.score(
            'The therapy did not improve overall survival.',
            ['The therapy improved overall survival in the study.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertGreaterEqual(score, 0.6)
        self.assertIn('negation mismatch', notes)

    def test_no_negation_pair_caps_support(self):
        status, score, notes = self.score(
            'The trial showed no statistically significant improvement in overall survival.',
            ['The trial showed statistically significant improvement in overall survival.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertGreaterEqual(score, 0.6)
        self.assertIn('negation mismatch', notes)

    def test_paraphrase_with_shared_features_is_supported(self):
        status, score, notes = self.score(
            "Acme's subscription revenue grew in 2025.",
            ['In 2025, Acme reported growth in subscription revenue.'],
        )
        self.assertEqual(status, 'supported')
        self.assertGreaterEqual(score, 0.6)
        self.assertEqual(notes, 'adequate overlap')

    def test_direction_mismatch_caps_support(self):
        status, score, notes = self.score(
            'Revenue increased in 2024.',
            ['Revenue decreased in 2024.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertGreaterEqual(score, 0.6)
        self.assertIn('direction mismatch', notes)

    def test_contradictory_linked_quote_caps_support(self):
        status, score, notes = self.score(
            'Revenue increased in 2024.',
            ['Revenue increased in 2024.', 'Revenue decreased in 2024.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertGreaterEqual(score, 0.9)
        self.assertIn('direction mismatch', notes)

    def test_met_vs_missed_endpoint_caps_support(self):
        status, score, notes = self.score(
            'The trial met its primary endpoint.',
            ['The trial missed its primary endpoint.'],
        )
        self.assertEqual(status, 'needs_review')
        self.assertGreaterEqual(score, 0.6)
        self.assertIn('direction mismatch', notes)

    def test_clause_scoped_negation_does_not_cap_supported_clause(self):
        status, score, notes = self.score(
            'The biomarker improved in 2024.',
            ['The trial did not meet its primary endpoint, but the biomarker improved in 2024.'],
        )
        self.assertEqual(status, 'supported')
        self.assertGreaterEqual(score, 0.6)
        self.assertNotIn('negation mismatch', notes)

    def test_clause_scoped_direction_does_not_cap_supported_clause(self):
        status, score, notes = self.score(
            'Revenue increased in 2024.',
            ['Revenue increased in 2024 while operating costs decreased.'],
        )
        self.assertEqual(status, 'supported')
        self.assertGreaterEqual(score, 0.6)
        self.assertNotIn('direction mismatch', notes)


if __name__ == '__main__':
    unittest.main()
