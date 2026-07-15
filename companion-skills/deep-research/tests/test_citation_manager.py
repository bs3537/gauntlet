#!/usr/bin/env python3
"""Smoke tests for citation_manager.py CLI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'citation_manager.py')


def run_cm(*args: str) -> dict:
    """Run citation_manager.py with args, return parsed JSON from stdout."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout


class TestInitRun(unittest.TestCase):
    def test_creates_manifest_and_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_cm('init-run', '--out-dir', d, '--query', 'test question', '--mode', 'deep')
            self.assertEqual(out['status'], 'ok')

            # Manifest exists and has correct fields
            with open(os.path.join(d, 'run_manifest.json')) as f:
                manifest = json.load(f)
            self.assertEqual(manifest['version'], '3.0.0')
            self.assertEqual(manifest['query'], 'test question')
            self.assertEqual(manifest['mode'], 'deep')
            self.assertEqual(manifest['provider_config']['primary'], 'native-web-search')
            self.assertEqual(manifest['provider_config']['wide_discovery'], 'search-as-code')
            self.assertEqual(manifest['provider_config']['follow_up'], 'perplexity-search-mcp')
            self.assertIsNotNone(manifest['started_at'])
            self.assertIsNone(manifest['finished_at'])
            self.assertEqual(manifest['artifact_paths']['sources'], 'sources.jsonl')
            self.assertEqual(manifest['artifact_paths']['file_manifest'], 'file_manifest.jsonl')
            self.assertEqual(manifest['artifact_paths']['data_profile'], 'data_profile.jsonl')
            self.assertEqual(manifest['artifact_paths']['plan'], 'plan.json')
            self.assertEqual(manifest['artifact_paths']['coverage_map'], 'coverage_map.json')
            self.assertEqual(manifest['artifact_paths']['ledger_index'], 'ledger_index.json')
            self.assertIn('execution_trace', manifest)
            self.assertEqual(manifest['execution_trace']['phase_metrics'], {})
            self.assertTrue(os.path.exists(os.path.join(d, 'plan.json')))
            self.assertTrue(os.path.exists(os.path.join(d, 'coverage_map.json')))
            self.assertTrue(os.path.exists(os.path.join(d, 'ledger_index.json')))
            with open(os.path.join(d, 'plan.json')) as f:
                plan = json.load(f)
            self.assertEqual(plan['checkpoint']['status'], 'skipped_headless')
            self.assertFalse(plan['checkpoint']['interactive'])
            budgets = {lane['role']: lane['execution_budget'] for lane in plan['lanes']}
            self.assertEqual(budgets['primary_source']['reasoning_effort'], 'medium')
            self.assertEqual(budgets['corroboration']['reasoning_effort'], 'medium')

            # Empty JSONL files exist
            for name in ('sources.jsonl', 'evidence.jsonl', 'claims.jsonl', 'file_manifest.jsonl', 'data_profile.jsonl'):
                path = os.path.join(d, name)
                self.assertTrue(os.path.exists(path), f'{name} missing')
                self.assertEqual(os.path.getsize(path), 0)

    def test_interactive_init_run_pauses_on_plan_review(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test question', '--mode', 'standard', '--interactive')

            with open(os.path.join(d, 'plan.json')) as f:
                plan = json.load(f)
            self.assertEqual(plan['checkpoint']['status'], 'ready_for_review')
            self.assertTrue(plan['checkpoint']['interactive'])
            self.assertIn('paused_at', plan['checkpoint'])

            with open(os.path.join(d, 'run_manifest.json')) as f:
                manifest = json.load(f)
            events = manifest['execution_trace']['events']
            self.assertTrue(any(event['phase'] == 'plan_checkpoint' for event in events))

    def test_finish_run_stamps_finished_at_and_trace_event(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test question')
            out = run_cm(
                'finish-run',
                '--dir', d,
                '--finished-at', '2026-07-05T01:02:03Z',
                '--report', 'report.md',
                '--note', 'Delivery gate passed.',
            )
            self.assertEqual(out['status'], 'ok')
            self.assertEqual(out['finished_at'], '2026-07-05T01:02:03Z')

            with open(os.path.join(d, 'run_manifest.json')) as f:
                manifest = json.load(f)
            self.assertEqual(manifest['finished_at'], '2026-07-05T01:02:03Z')
            finish_events = [
                event for event in manifest['execution_trace']['events']
                if event['phase'] == 'finish_run'
            ]
            self.assertEqual(len(finish_events), 1)
            self.assertEqual(finish_events[0]['report'], 'report.md')
            self.assertEqual(finish_events[0]['message'], 'Delivery gate passed.')

    def test_finish_run_backfills_execution_trace_required_fields_for_legacy_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            manifest_path = os.path.join(d, 'run_manifest.json')
            with open(manifest_path, 'w') as f:
                json.dump({
                    'version': '3.0.0',
                    'query': 'legacy closeout',
                    'mode': 'standard',
                    'started_at': '2026-07-05T00:00:00Z',
                    'finished_at': None,
                    'report_dir': d,
                    'artifact_paths': {
                        'sources': 'sources.jsonl',
                        'evidence': 'evidence.jsonl',
                        'claims': 'claims.jsonl',
                        'report': 'report.md',
                    },
                }, f)
                f.write('\n')

            out = run_cm(
                'finish-run',
                '--dir', d,
                '--finished-at', '2026-07-05T01:02:03Z',
            )
            self.assertEqual(out['status'], 'ok')
            with open(manifest_path) as f:
                manifest = json.load(f)
            trace = manifest['execution_trace']
            self.assertEqual(trace['version'], '1.0')
            self.assertEqual(trace['provider_calls'], [])
            self.assertEqual(trace['subagents'], [])
            self.assertEqual(trace['lane_source_counts'], {})
            self.assertEqual(trace['query_family_source_counts'], {})
            self.assertEqual(trace['phase_metrics'], {})
            self.assertEqual(trace['events'][0]['phase'], 'finish_run')

    def test_ultradeep_plan_assigns_higher_effort_to_adversarial_lanes(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test question', '--mode', 'ultradeep')

            with open(os.path.join(d, 'plan.json')) as f:
                plan = json.load(f)
            budgets = {lane['role']: lane['execution_budget'] for lane in plan['lanes']}
            self.assertEqual(budgets['primary_source']['reasoning_effort'], 'medium')
            self.assertEqual(budgets['corroboration']['reasoning_effort'], 'medium')
            self.assertEqual(budgets['adversarial']['reasoning_effort'], 'high')
            self.assertEqual(budgets['gap_scout']['reasoning_effort'], 'high')
            self.assertGreaterEqual(budgets['adversarial']['timeout_seconds'], 900)


class TestRegisterSource(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_cm('init-run', '--out-dir', self.tmpdir, '--query', 'test')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_register_and_dedup(self):
        src = json.dumps({
            'raw_url': 'https://arxiv.org/abs/2305.14251',
            'title': 'FActScore',
            'source_type': 'academic',
            'year': '2023',
        })
        out1 = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertEqual(out1['status'], 'registered')
        self.assertEqual(len(out1['source_id']), 16)
        self.assertTrue(out1['canonical_locator'].startswith('arxiv:'))

        # Same URL -> duplicate
        out2 = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertEqual(out2['status'], 'duplicate')
        self.assertEqual(out2['source_id'], out1['source_id'])

    def test_doi_canonicalization(self):
        src = json.dumps({
            'raw_url': 'https://doi.org/10.1038/s41586-023-06745-9',
            'title': 'Some Nature paper',
        })
        out = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertTrue(out['canonical_locator'].startswith('doi:10.1038/'))

    def test_doi_prefix_canonicalization_dedups_against_doi_url(self):
        src_prefix = json.dumps({
            'raw_url': 'doi:10.5555/p2-10.source',
            'title': 'P2-10 DOI Prefix',
            'source_type': 'academic',
        })
        src_url = json.dumps({
            'raw_url': 'https://doi.org/10.5555/p2-10.source',
            'title': 'P2-10 DOI URL Duplicate',
            'source_type': 'academic',
        })

        out1 = run_cm('register-source', '--json', src_prefix, '--dir', self.tmpdir)
        out2 = run_cm('register-source', '--json', src_url, '--dir', self.tmpdir)

        self.assertEqual(out1['canonical_locator'], 'doi:10.5555/p2-10.source')
        self.assertEqual(out2['status'], 'duplicate')
        self.assertEqual(out2['source_id'], out1['source_id'])

    def test_url_normalization(self):
        src1 = json.dumps({
            'raw_url': 'https://Example.Com/article?utm_source=google&id=42',
            'title': 'Test',
        })
        src2 = json.dumps({
            'raw_url': 'https://example.com/article?id=42&utm_medium=email',
            'title': 'Test duplicate',
        })
        out1 = run_cm('register-source', '--json', src1, '--dir', self.tmpdir)
        out2 = run_cm('register-source', '--json', src2, '--dir', self.tmpdir)
        # Both should resolve to same canonical locator -> same source_id
        self.assertEqual(out1['source_id'], out2['source_id'])
        self.assertEqual(out2['status'], 'duplicate')

    def test_register_sources_batch_dedups_and_updates_index(self):
        batch_path = Path(self.tmpdir) / 'sources_batch.jsonl'
        rows = [
            {'raw_url': 'https://Example.com/report?utm_source=x&id=1#frag', 'title': 'Report A'},
            {'raw_url': 'https://example.com/report?id=1', 'title': 'Report A duplicate'},
            {'raw_url': 'https://doi.org/10.1234/example', 'title': 'Paper B', 'source_type': 'academic'},
        ]
        batch_path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')

        out = run_cm('register-sources', '--jsonl', str(batch_path), '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['rows_read'], 3)
        self.assertEqual(out['registered'], 2)
        self.assertEqual(out['duplicates'], 1)

        sources = [json.loads(line) for line in Path(self.tmpdir, 'sources.jsonl').read_text().splitlines()]
        self.assertEqual(len(sources), 2)
        canonical_locators = {source['canonical_locator'] for source in sources}
        self.assertIn('https://example.com/report?id=1', canonical_locators)
        self.assertTrue(any(locator.startswith('doi:10.1234/example') for locator in canonical_locators))

        with open(Path(self.tmpdir) / 'ledger_index.json') as f:
            index = json.load(f)
        self.assertEqual(index['sources']['count'], 2)
        self.assertEqual(set(index['sources']['source_ids']), {source['source_id'] for source in sources})

    def test_register_sources_strict_reports_bad_rows_without_losing_valid_rows(self):
        batch_path = Path(self.tmpdir) / 'bad_sources.jsonl'
        batch_path.write_text(
            json.dumps({'raw_url': 'https://example.com/good', 'title': 'Good'}) + '\n'
            + '{"raw_url":\n'
            + json.dumps({'title': 'Missing URL'}) + '\n'
        )

        result = subprocess.run(
            [sys.executable, SCRIPT, 'register-sources', '--jsonl', str(batch_path), '--dir', self.tmpdir, '--strict'],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(out['registered'], 1)
        self.assertEqual(len(out['errors']), 2)
        sources = Path(self.tmpdir, 'sources.jsonl').read_text().splitlines()
        self.assertEqual(len(sources), 1)

    def test_build_index_rebuilds_from_ledgers_when_cache_is_stale(self):
        src = json.dumps({
            'raw_url': 'https://example.com/rebuild',
            'title': 'Rebuild Source',
        })
        out = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        index_path = Path(self.tmpdir) / 'ledger_index.json'
        index_path.write_text(json.dumps({
            'version': '1.0',
            'ledgers': {},
            'sources': {'count': 1, 'source_ids': ['badbadbadbadbadb'], 'source_id_by_canonical_locator': {}},
            'evidence': {'count': 0, 'evidence_ids': [], 'evidence_ids_by_source_id': {}},
        }))

        rebuilt = run_cm('build-index', '--dir', self.tmpdir)
        self.assertEqual(rebuilt['status'], 'ok')
        self.assertEqual(rebuilt['sources'], 1)
        with open(index_path) as f:
            index = json.load(f)
        self.assertEqual(index['sources']['source_ids'], [out['source_id']])


class TestResearchBrief(unittest.TestCase):
    def test_add_assumption_persists_and_updates_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')

            text = 'Assume the scope is limited to public-company sources unless private data is provided.'
            out1 = run_cm(
                'add-assumption',
                '--dir', d,
                '--text', text,
                '--materiality', 'high',
                '--status', 'implicit',
            )
            self.assertEqual(out1['status'], 'added')
            assumption_id = out1['assumption']['assumption_id']
            self.assertRegex(assumption_id, r'^asm_[0-9a-f]{8}$')

            out2 = run_cm(
                'add-assumption',
                '--dir', d,
                '--text', text,
                '--materiality', 'medium',
                '--status', 'user_confirmed',
            )
            self.assertEqual(out2['status'], 'updated')
            self.assertEqual(out2['assumption']['assumption_id'], assumption_id)

            with open(os.path.join(d, 'run_manifest.json')) as f:
                manifest = json.load(f)
            self.assertEqual(len(manifest['assumptions']), 1)
            self.assertEqual(manifest['assumptions'][0]['materiality'], 'medium')
            self.assertEqual(manifest['assumptions'][0]['status'], 'user_confirmed')

    def test_write_brief_uses_scope_questions_and_assumptions(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'compare AI search products', '--mode', 'deep')
            run_cm(
                'add-assumption',
                '--dir', d,
                '--text', 'Assume public product documentation is sufficient for feature parity claims.',
                '--materiality', 'high',
            )

            out = run_cm(
                'write-brief',
                '--dir', d,
                '--scope-in', 'published product capabilities|benchmark claims',
                '--scope-out', 'private roadmap speculation',
                '--open-question', 'Which claims need primary-source confirmation?',
            )
            self.assertEqual(out['status'], 'ok')
            brief_text = Path(out['brief']).read_text()
            self.assertIn('# Research Brief', brief_text)
            self.assertIn('compare AI search products', brief_text)
            self.assertIn('published product capabilities', brief_text)
            self.assertIn('private roadmap speculation', brief_text)
            self.assertIn('Which claims need primary-source confirmation?', brief_text)
            self.assertIn('public product documentation', brief_text)


class TestAssignDisplayNumbers(unittest.TestCase):
    def test_assigns_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')

            for i, url in enumerate(['https://a.com/1', 'https://b.com/2', 'https://c.com/3']):
                run_cm('register-source', '--json', json.dumps({
                    'raw_url': url, 'title': f'Source {i+1}',
                }), '--dir', d)

            mapping = run_cm('assign-display-numbers', '--dir', d)
            self.assertEqual(len(mapping), 3)
            # Values should be 1, 2, 3
            self.assertEqual(sorted(mapping.values()), [1, 2, 3])

    def test_write_display_map_from_report_first_use(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://a.com/source',
                'title': 'Source A',
                'display_id': '[1]',
            }), '--dir', d)
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://b.com/source',
                'title': 'Source B',
                'display_id': '[2]',
            }), '--dir', d)
            report_path = Path(d) / 'report.md'
            report_path.write_text('## Finding 1\n\nB appears first [2]. A appears second [1].\n')

            mapping = run_cm(
                'assign-display-numbers',
                '--dir', d,
                '--order-from-report', str(report_path),
                '--write',
            )
            display_map_path = Path(d) / 'display_map.json'
            self.assertTrue(display_map_path.exists())
            display_map = json.loads(display_map_path.read_text())
            source_b = display_map['label_to_source_id']['2']
            source_a = display_map['label_to_source_id']['1']

            self.assertEqual(mapping[source_b], 1)
            self.assertEqual(mapping[source_a], 2)
            self.assertEqual(display_map['label_source'], 'report')
            self.assertEqual(display_map['display_number_to_source_id']['1'], source_b)


class TestExportBibliography(unittest.TestCase):
    def test_markdown_export(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://arxiv.org/abs/2305.14251',
                'title': 'FActScore',
                'authors': ['Min, S.', 'Krishna, K.'],
                'year': '2023',
                'source_type': 'academic',
            }), '--dir', d)

            out = run_cm('export-bibliography', '--dir', d, '--style', 'markdown')
            self.assertIn('[1]', out)
            self.assertIn('FActScore', out)
            self.assertIn('Min, S. & Krishna, K.', out)

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://example.com/paper',
                'title': 'Test Paper',
            }), '--dir', d)

            out = run_cm('export-bibliography', '--dir', d, '--style', 'json')
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]['display_number'], 1)
            self.assertEqual(out[0]['title'], 'Test Paper')


class TestCanonicalization(unittest.TestCase):
    """Unit tests for canonicalize_locator without running the CLI."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from citation_manager import canonicalize_locator, compute_source_id
        cls.canonicalize = staticmethod(canonicalize_locator)
        cls.compute_id = staticmethod(compute_source_id)

    def test_doi_from_url(self):
        canonicalize_locator = self.canonicalize
        self.assertEqual(
            canonicalize_locator('https://doi.org/10.1038/s41586-023-06745-9'),
            'doi:10.1038/s41586-023-06745-9',
        )
        self.assertEqual(
            canonicalize_locator('https://dx.doi.org/10.1234/test.'),
            'doi:10.1234/test',
        )

    def test_arxiv_from_url(self):
        canonicalize_locator = self.canonicalize
        self.assertEqual(
            canonicalize_locator('https://arxiv.org/abs/2305.14251v2'),
            'arxiv:2305.14251v2',
        )
        self.assertEqual(
            canonicalize_locator('arxiv:2401.15884'),
            'arxiv:2401.15884',
        )

    def test_url_strips_tracking(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://Example.Com/page?utm_source=x&key=val')
        self.assertNotIn('utm_source', result)
        self.assertIn('key=val', result)
        self.assertTrue(result.startswith('https://example.com'))

    def test_url_strips_fragment(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://example.com/page#section')
        self.assertNotIn('#section', result)

    def test_url_strips_trailing_slash(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://example.com/page/')
        self.assertFalse(result.endswith('/'))


if __name__ == '__main__':
    unittest.main()
