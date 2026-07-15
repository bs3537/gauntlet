#!/usr/bin/env python3
"""Tests for run_eval.py CLI."""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'run_eval.py')
TASKS = os.path.join(os.path.dirname(__file__), '..', 'evals', 'tasks', 'gold_tasks.json')
RUN_SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'run_manifest.schema.json')


def write_json(path: str, payload: dict) -> None:
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
        f.write('\n')


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def run_eval(*args: str, expect_fail: bool = False) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    if result.stdout.strip().startswith('{'):
        return json.loads(result.stdout)
    return {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


class RunEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = os.path.join(self.tmpdir, 'run')
        os.makedirs(self.run_dir)
        self.results_dir = os.path.join(self.tmpdir, 'results')
        self.runs_csv = os.path.join(self.tmpdir, 'runs.csv')
        self.report_path = os.path.join(self.run_dir, 'report.md')
        Path(self.report_path).write_text('## Main Analysis\n\nAcme revenue increased in 2025 [1].\n')
        write_json(os.path.join(self.run_dir, 'run_manifest.json'), {
            'version': '3.0.0',
            'query': 'test query',
            'mode': 'deep',
            'started_at': '2026-07-05T00:00:00Z',
            'finished_at': '2026-07-05T00:05:00Z',
            'assumptions': [],
            'provider_config': {'primary': 'perplexity-search-mcp'},
            'report_dir': self.run_dir,
            'artifact_paths': {
                'sources': 'sources.jsonl',
                'evidence': 'evidence.jsonl',
                'claims': 'claims.jsonl',
                'report': 'report.md',
            },
            'continuation': None,
        })
        write_jsonl(os.path.join(self.run_dir, 'sources.jsonl'), [
            {'source_id': 'src_001', 'display_id': '[1]', 'title': 'Acme Results', 'source_tier': 'primary'},
        ])
        write_jsonl(os.path.join(self.run_dir, 'evidence.jsonl'), [
            {'evidence_id': 'ev_001', 'source_id': 'src_001', 'quote': 'Acme revenue increased in 2025.'},
        ])
        write_jsonl(os.path.join(self.run_dir, 'claims.jsonl'), [
            {
                'claim_id': 'aaaaaaaaaaaaaaaa',
                'section_id': 'main_analysis',
                'text': 'Acme revenue increased in 2025.',
                'claim_type': 'factual',
                'support_status': 'supported',
                'support_status_llm': 'entailed',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            },
        ])
        write_json(os.path.join(self.run_dir, 'audit_manifest.json'), {
            'status': 'pass',
            'generated_at': '2026-07-05T00:06:00Z',
            'counts': {'critical_findings': 0, 'warnings': 0},
        })
        now = time.time() + 10
        os.utime(os.path.join(self.run_dir, 'audit_manifest.json'), (now, now))

        self.judge_output = os.path.join(self.tmpdir, 'judge_output.json')
        write_json(self.judge_output, {
            'race_scores': {
                'instruction_following': 90,
                'comprehensiveness': 80,
                'insight': 75,
                'writing_objectivity': 85,
            },
            'race_rationales': {
                'instruction_following': 'Follows task.',
                'comprehensiveness': 'Covers main issue.',
                'insight': 'Some synthesis.',
                'writing_objectivity': 'Calibrated.',
            },
            'fact_judgments': [
                {'claim_id': 'aaaaaaaaaaaaaaaa', 'verdict': 'entailed', 'rationale': 'Evidence states the claim.'},
            ],
        })

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def score_args(self) -> list[str]:
        return [
            'score-run',
            '--task', TASKS,
            '--task-id', 'adversarial-negation-001',
            '--run-dir', self.run_dir,
            '--judge-output', self.judge_output,
            '--judge-model', 'fixture-race-mini',
            '--judge-version', '2026-07-05',
            '--runs-csv', self.runs_csv,
            '--results-dir', self.results_dir,
            '--eval-run-id', 'eval_test',
            '--strict',
        ]

    def test_score_run_writes_self_eval_result_and_runs_csv(self):
        out = run_eval(*self.score_args())

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['judge']['model'], 'fixture-race-mini')
        self.assertEqual(out['judge']['version'], '2026-07-05')
        self.assertFalse(out['network_used'])
        self.assertFalse(out['llm_used'])
        self.assertEqual(out['fact_mini']['sample_size'], 1)
        self.assertEqual(out['fact_mini']['entailed'], 1)

        with open(os.path.join(self.run_dir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(manifest['self_eval']['status'], 'pass')
        self.assertEqual(manifest['self_eval']['eval_run_id'], 'eval_test')

        self.assertTrue(os.path.exists(os.path.join(self.results_dir, 'eval_test.json')))
        with open(self.runs_csv) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'pass')
        self.assertEqual(rows[0]['judge_model'], 'fixture-race-mini')

    def test_requires_judge_model_and_version(self):
        args = self.score_args()
        args.remove('--judge-version')
        args.remove('2026-07-05')

        result = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('judge-version', result.stderr)

    def test_strict_fails_stale_audit_manifest(self):
        old = time.time() - 100
        os.utime(os.path.join(self.run_dir, 'audit_manifest.json'), (old, old))

        out = run_eval(*self.score_args(), expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertTrue(any(check['name'] == 'audit_manifest_freshness' and check['status'] == 'fail' for check in out['checks']))

    def test_fact_mini_samples_max_10_deterministically(self):
        claims = []
        judgments = []
        for i in range(12):
            claim_id = f'{i:016x}'
            claims.append({
                'claim_id': claim_id,
                'section_id': 'main_analysis',
                'text': f'Claim {i} is supported.',
                'claim_type': 'factual',
                'support_status': 'supported',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            })
            judgments.append({'claim_id': claim_id, 'verdict': 'entailed', 'rationale': 'Fixture support.'})
        write_jsonl(os.path.join(self.run_dir, 'claims.jsonl'), claims)
        write_json(self.judge_output, {
            'race_scores': {
                'instruction_following': 90,
                'comprehensiveness': 80,
                'insight': 75,
                'writing_objectivity': 85,
            },
            'fact_judgments': judgments,
        })
        now = time.time() + 10
        os.utime(os.path.join(self.run_dir, 'audit_manifest.json'), (now, now))

        out = run_eval(*self.score_args())

        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['fact_mini']['sample_size'], 10)
        first_sample = out['fact_mini']['sampled_claim_ids']
        out2 = run_eval(*self.score_args())
        self.assertEqual(out2['fact_mini']['sampled_claim_ids'], first_sample)

    def test_invalid_judge_json_fails_without_silent_pass(self):
        Path(self.judge_output).write_text('{not valid json')

        out = run_eval(*self.score_args(), expect_fail=True)

        self.assertEqual(out['status'], 'fail')
        self.assertTrue(any(check['name'] == 'score_run_exception' for check in out['checks']))
        with open(self.runs_csv) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]['status'], 'fail')

    def test_list_tasks_reads_gold_catalog(self):
        out = run_eval('list-tasks', '--task-file', TASKS)
        self.assertEqual(out['count'], 20)
        self.assertTrue(any(task['task_id'] == 'adversarial-negation-001' for task in out['tasks']))

    def test_run_manifest_schema_allows_optional_self_eval(self):
        with open(RUN_SCHEMA) as f:
            schema = json.load(f)
        self.assertIn('self_eval', schema['properties'])
        self.assertNotIn('self_eval', schema['required'])
        self.assertFalse(schema['properties']['self_eval']['additionalProperties'])
        for key in ('status', 'evaluated_at', 'checks', 'strict'):
            self.assertIn(key, schema['properties']['self_eval']['properties'])


if __name__ == '__main__':
    unittest.main()
