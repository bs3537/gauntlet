#!/usr/bin/env python3
"""Tests for merge_subagent_evidence.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'merge_subagent_evidence.py')
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
CITATION_MANAGER = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'citation_manager.py')
EVIDENCE_STORE = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'evidence_store.py')


def run_mse(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


def run_script(script: str, *args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


def write_jsonl(path: str, rows: list[dict]):
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def write_json(path: str, payload: dict):
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
        f.write('\n')


def read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class TestMergeSubagentEvidence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.subagent_dir = os.path.join(self.tmpdir, 'subagent_outputs')
        os.makedirs(self.subagent_dir, exist_ok=True)
        open(os.path.join(self.tmpdir, 'sources.jsonl'), 'w').close()
        open(os.path.join(self.tmpdir, 'evidence.jsonl'), 'w').close()
        self.input_path = os.path.join(self.subagent_dir, 'lane_a.evidence.jsonl')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_merges_valid_subagent_row_into_source_and_evidence_ledgers(self):
        write_jsonl(self.input_path, [
            {
                'claim': 'Revenue increased in 2025.',
                'evidence_quote': 'Revenue increased 12% year over year in 2025.',
                'source_url': 'https://example.com/report?utm_source=x&id=42#section',
                'source_title': 'Annual Report',
                'source_type': 'company_ir',
                'source_tier': 'primary',
                'document_date': '2025-02-15',
                'retrieved_at': '2026-07-05T12:00:00Z',
                'locator': 'page 5',
                'topic_id': 'financials',
            },
        ])

        out = run_mse('--dir', self.tmpdir)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['sources_added'], 1)
        self.assertEqual(out['evidence_added'], 1)

        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(sources[0]['title'], 'Annual Report')
        self.assertEqual(sources[0]['source_type'], 'company_ir')
        self.assertEqual(sources[0]['source_tier'], 'primary')
        self.assertEqual(sources[0]['document_date'], '2025-02-15')
        self.assertEqual(sources[0]['retrieved_at'], '2026-07-05T12:00:00Z')
        self.assertNotIn('utm_source', sources[0]['canonical_locator'])
        self.assertNotIn('#section', sources[0]['canonical_locator'])
        self.assertEqual(evidence[0]['source_id'], sources[0]['source_id'])
        self.assertEqual(evidence[0]['quote'], 'Revenue increased 12% year over year in 2025.')
        self.assertEqual(evidence[0]['locator'], 'page 5')
        self.assertEqual(evidence[0]['retrieval_query'], 'Revenue increased in 2025.')

    def test_nested_source_payload_is_supported(self):
        write_jsonl(self.input_path, [
            {
                'claim': 'The study met its endpoint.',
                'quote': 'The study met its primary endpoint.',
                'source': {
                    'raw_url': 'https://example.com/study',
                    'title': 'Study Result',
                    'source_tier': 'primary',
                    'document_date': '2025-06-01',
                    'retrieved_at': '2026-07-05T12:00:00Z',
                },
                'locator': 'press release',
            },
        ])

        run_mse('--dir', self.tmpdir, '--input', self.input_path)
        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['title'], 'Study Result')
        self.assertEqual(sources[0]['source_tier'], 'primary')
        self.assertEqual(evidence[0]['quote'], 'The study met its primary endpoint.')

    def test_malformed_rows_are_skipped_and_reported_without_corrupting_ledgers(self):
        with open(self.input_path, 'w') as f:
            f.write('{bad json}\n')
            f.write(json.dumps({'claim': 'Claim-only row is not evidence.'}) + '\n')
            f.write(json.dumps({
                'source_url': 'https://example.com/valid',
                'evidence_quote': 'Valid evidence quote.',
            }) + '\n')

        # Row-level behavior only: disable the lane-health floor so this test keeps
        # asserting skip accounting rather than the P0-C usable-ratio gate.
        out = run_mse('--dir', self.tmpdir, '--min-usable-ratio', '0')
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(out['rows_read'], 2)
        self.assertEqual(out['rows_skipped'], 2)
        self.assertEqual(out['evidence_added'], 1)

        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['quote'], 'Valid evidence quote.')

    def test_strict_mode_exits_nonzero_on_malformed_rows(self):
        with open(self.input_path, 'w') as f:
            f.write(json.dumps({'claim': 'Claim-only row is not evidence.'}) + '\n')

        out = run_mse('--dir', self.tmpdir, '--strict', expect_fail=True)
        # Zero valid rows always fails the file under P0-C, so status is 'fail'
        # rather than 'partial'; the strict exit-code contract is unchanged.
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['rows_skipped'], 1)

    def test_per_file_usable_ratio_is_reported(self):
        with open(self.input_path, 'w') as f:
            for i in range(7):
                f.write(json.dumps({
                    'source_url': f'https://example.com/ok{i}',
                    'evidence_quote': f'Valid evidence quote number {i}.',
                }) + '\n')
            for i in range(3):
                f.write(json.dumps({'claim': f'No evidence quote {i}.'}) + '\n')

        out = run_mse('--dir', self.tmpdir)
        self.assertEqual(len(out['per_file']), 1)
        stats = out['per_file'][0]
        self.assertEqual(stats['rows_read'], 10)
        self.assertEqual(stats['rows_ok'], 7)
        self.assertEqual(stats['rows_skipped'], 3)
        self.assertAlmostEqual(stats['usable_ratio'], 0.7, places=4)

    def test_usable_ratio_below_threshold_fails_strict(self):
        with open(self.input_path, 'w') as f:
            for i in range(7):
                f.write(json.dumps({
                    'source_url': f'https://example.com/ok{i}',
                    'evidence_quote': f'Valid evidence quote number {i}.',
                }) + '\n')
            for i in range(3):
                f.write(json.dumps({'claim': f'No evidence quote {i}.'}) + '\n')

        out = run_mse('--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')
        self.assertEqual(out['files_below_threshold'], 1)
        self.assertTrue(out['per_file'][0]['below_min_usable_ratio'])
        self.assertEqual(out['min_usable_ratio'], 0.8)

    def test_usable_ratio_above_threshold_passes_strict(self):
        with open(self.input_path, 'w') as f:
            for i in range(9):
                f.write(json.dumps({
                    'source_url': f'https://example.com/ok{i}',
                    'evidence_quote': f'Valid evidence quote number {i}.',
                }) + '\n')
            f.write(json.dumps({'claim': 'Only one bad row.'}) + '\n')

        out = run_mse('--dir', self.tmpdir, '--strict', '--min-usable-ratio', '0.8', expect_fail=True)
        # Rows are still skipped, so --strict still trips on errors; the ratio itself is fine.
        self.assertEqual(out['files_below_threshold'], 0)
        self.assertFalse(out['per_file'][0]['below_min_usable_ratio'])
        self.assertAlmostEqual(out['per_file'][0]['usable_ratio'], 0.9, places=4)

    def test_zero_valid_rows_always_fails_the_file(self):
        write_jsonl(self.input_path, [
            {'claim': 'No evidence quote at all.'},
            {'claim': 'Still nothing usable.'},
        ])

        out = run_mse('--dir', self.tmpdir)
        self.assertEqual(out['status'], 'fail')
        self.assertTrue(out['per_file'][0]['zero_valid_rows'])
        self.assertEqual(out['files_below_threshold'], 1)

    def test_empty_input_file_fails(self):
        open(self.input_path, 'w').close()

        out = run_mse('--dir', self.tmpdir)
        self.assertEqual(out['status'], 'fail')
        self.assertTrue(out['per_file'][0]['zero_valid_rows'])

    def test_fully_valid_file_reports_ratio_one_and_passes_strict(self):
        write_jsonl(self.input_path, [
            {'source_url': 'https://example.com/a', 'evidence_quote': 'Quote A is valid.'},
            {'source_url': 'https://example.com/b', 'evidence_quote': 'Quote B is valid.'},
        ])

        out = run_mse('--dir', self.tmpdir, '--strict')
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['files_below_threshold'], 0)
        self.assertAlmostEqual(out['per_file'][0]['usable_ratio'], 1.0, places=4)

    def test_missing_source_url_is_rejected_unless_existing_source_id_is_valid(self):
        write_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'), [
            {
                'source_id': 'src_existing',
                'canonical_locator': 'https://example.com/existing',
                'raw_url': 'https://example.com/existing',
                'title': 'Existing Source',
                'source_type': 'web',
                'metadata_status': 'unverified',
                'registered_at': '2026-07-05T12:00:00Z',
            },
        ])
        write_jsonl(self.input_path, [
            {'evidence_quote': 'No source URL means this must be skipped.'},
            {'source_id': 'src_existing', 'evidence_quote': 'Existing source evidence.'},
        ])

        # Row-level behavior only; see note in the malformed-rows test above.
        out = run_mse('--dir', self.tmpdir, '--min-usable-ratio', '0')
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(out['rows_skipped'], 1)
        self.assertEqual(out['sources_reused'], 1)
        self.assertEqual(out['evidence_added'], 1)

        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))
        self.assertEqual(len(sources), 1)
        self.assertEqual(evidence[0]['source_id'], 'src_existing')

    def test_url_source_dedup_uses_canonical_locator(self):
        write_jsonl(self.input_path, [
            {
                'source_url': 'https://Example.com/article?id=42&utm_source=x#frag',
                'source_title': 'First Title',
                'evidence_quote': 'First quote from the article.',
            },
            {
                'source_url': 'https://example.com/article/?utm_medium=y&id=42',
                'source_title': 'Second Title',
                'evidence_quote': 'Second quote from the article.',
            },
        ])

        out = run_mse('--dir', self.tmpdir)
        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))

        self.assertEqual(out['sources_added'], 1)
        self.assertEqual(out['sources_reused'], 1)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(evidence), 2)
        self.assertEqual({row['source_id'] for row in evidence}, {sources[0]['source_id']})
        self.assertEqual(sources[0]['canonical_locator'], 'https://example.com/article?id=42')

    def test_duplicate_evidence_dedups_by_source_quote_and_locator(self):
        write_jsonl(self.input_path, [
            {
                'source_url': 'https://example.com/source',
                'evidence_quote': '  Same   quote text. ',
                'locator': 'page 1',
            },
            {
                'source_url': 'https://example.com/source',
                'evidence_quote': 'Same quote text.',
                'locator': 'page 1',
            },
            {
                'source_url': 'https://example.com/source',
                'evidence_quote': 'Same quote text.',
                'locator': 'page 2',
            },
        ])

        out = run_mse('--dir', self.tmpdir)
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))

        self.assertEqual(out['evidence_added'], 2)
        self.assertEqual(out['evidence_reused'], 1)
        self.assertEqual(len(evidence), 2)
        self.assertEqual({row['locator'] for row in evidence}, {'page 1', 'page 2'})

    def test_stable_ids_are_independent_of_input_order(self):
        rows = [
            {'source_url': 'https://example.com/a', 'evidence_quote': 'Quote A.', 'locator': 'A'},
            {'source_url': 'https://example.com/b', 'evidence_quote': 'Quote B.', 'locator': 'B'},
        ]
        other_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(other_dir, ignore_errors=True))
        os.makedirs(os.path.join(other_dir, 'subagent_outputs'), exist_ok=True)
        open(os.path.join(other_dir, 'sources.jsonl'), 'w').close()
        open(os.path.join(other_dir, 'evidence.jsonl'), 'w').close()

        write_jsonl(self.input_path, rows)
        write_jsonl(os.path.join(other_dir, 'subagent_outputs', 'lane.evidence.jsonl'), list(reversed(rows)))

        run_mse('--dir', self.tmpdir)
        run_mse('--dir', other_dir)

        sources_a = sorted(row['source_id'] for row in read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl')))
        sources_b = sorted(row['source_id'] for row in read_jsonl(os.path.join(other_dir, 'sources.jsonl')))
        evidence_a = sorted(row['evidence_id'] for row in read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl')))
        evidence_b = sorted(row['evidence_id'] for row in read_jsonl(os.path.join(other_dir, 'evidence.jsonl')))
        self.assertEqual(sources_a, sources_b)
        self.assertEqual(evidence_a, evidence_b)

    def test_idempotent_rerun_does_not_append_duplicates(self):
        write_jsonl(self.input_path, [
            {
                'source_url': 'https://example.com/source',
                'evidence_quote': 'A quote worth keeping.',
                'locator': 'section 1',
            },
        ])

        out1 = run_mse('--dir', self.tmpdir)
        out2 = run_mse('--dir', self.tmpdir)
        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))

        self.assertEqual(out1['sources_added'], 1)
        self.assertEqual(out1['evidence_added'], 1)
        self.assertEqual(out2['sources_added'], 0)
        self.assertEqual(out2['evidence_added'], 0)
        self.assertEqual(out2['evidence_reused'], 1)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(evidence), 1)

    def test_merge_round_trip_rebuilds_stale_index_and_downstream_helpers_dedup(self):
        write_json(os.path.join(self.tmpdir, 'ledger_index.json'), {
            'version': '1.0',
            'sources': {
                'count': 1,
                'source_ids': ['stale_source'],
                'source_id_by_canonical_locator': {'https://stale.example': 'stale_source'},
            },
            'evidence': {
                'count': 1,
                'evidence_ids': ['stale_evidence'],
                'evidence_ids_by_source_id': {'stale_source': ['stale_evidence']},
            },
        })
        write_jsonl(self.input_path, [
            {
                'source_url': 'https://Example.com/report?utm_source=x&id=42#frag',
                'source_title': 'Report',
                'evidence_id': 'worker_bogus_id_a',
                'evidence_quote': '  Revenue increased 10 percent in 2025. ',
                'locator': 'page 1',
            },
            {
                'source_url': 'https://example.com/report/?utm_medium=y&id=42',
                'source_title': 'Report',
                'evidence_id': 'worker_bogus_id_b',
                'evidence_quote': 'Revenue increased 10 percent in 2025.',
                'locator': 'page 1',
            },
            {
                'source_url': 'https://example.com/report?id=42',
                'source_title': 'Report',
                'evidence_id': 'worker_bogus_id_c',
                'evidence_quote': 'Revenue increased 10 percent in 2025.',
                'locator': 'page 2',
            },
        ])

        out = run_mse('--dir', self.tmpdir)
        sources = read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))
        evidence = read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))

        self.assertEqual(out['sources_added'], 1)
        self.assertEqual(out['sources_reused'], 2)
        self.assertEqual(out['evidence_added'], 2)
        self.assertEqual(out['evidence_reused'], 1)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(sources[0]['canonical_locator'], 'https://example.com/report?id=42')
        self.assertFalse(any(row['evidence_id'].startswith('worker_bogus') for row in evidence))

        index_out = run_script(CITATION_MANAGER, 'build-index', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, 'ledger_index.json')) as f:
            index = json.load(f)
        self.assertEqual(index_out['status'], 'ok')
        self.assertEqual(index['sources']['count'], 1)
        self.assertEqual(index['evidence']['count'], 2)
        self.assertEqual(
            index['sources']['source_id_by_canonical_locator']['https://example.com/report?id=42'],
            sources[0]['source_id'],
        )
        self.assertEqual(set(index['evidence']['evidence_ids_by_source_id'][sources[0]['source_id']]), {
            row['evidence_id'] for row in evidence
        })

        duplicate_source = run_script(
            CITATION_MANAGER,
            'register-source',
            '--dir', self.tmpdir,
            '--json', json.dumps({
                'raw_url': 'https://example.com/report/?utm_campaign=noise&id=42',
                'title': 'Duplicate Report',
            }),
        )
        duplicate_evidence = run_script(
            EVIDENCE_STORE,
            'add',
            '--dir', self.tmpdir,
            '--json', json.dumps({
                'source_id': sources[0]['source_id'],
                'quote': 'Revenue increased 10 percent in 2025.',
                'locator': 'page 1',
            }),
        )
        self.assertEqual(duplicate_source['status'], 'duplicate')
        self.assertEqual(duplicate_evidence['status'], 'duplicate')
        self.assertEqual(len(read_jsonl(os.path.join(self.tmpdir, 'sources.jsonl'))), 1)
        self.assertEqual(len(read_jsonl(os.path.join(self.tmpdir, 'evidence.jsonl'))), 2)


class TestMergeSubagentEvidenceIDs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, SCRIPTS_DIR)
        from citation_manager import canonicalize_locator, compute_source_id
        from evidence_store import compute_evidence_id
        cls.canonicalize = staticmethod(canonicalize_locator)
        cls.compute_source_id = staticmethod(compute_source_id)
        cls.compute_evidence_id = staticmethod(compute_evidence_id)

    def test_expected_source_and_evidence_ids(self):
        canonical = self.canonicalize('https://Example.com/source?utm_source=x&id=1#frag')
        source_id = self.compute_source_id(canonical)
        evidence_id = self.compute_evidence_id(source_id, 'Quote text.', 'page 1')

        self.assertEqual(canonical, 'https://example.com/source?id=1')
        self.assertEqual(len(source_id), 16)
        self.assertEqual(len(evidence_id), 16)


if __name__ == '__main__':
    unittest.main()
