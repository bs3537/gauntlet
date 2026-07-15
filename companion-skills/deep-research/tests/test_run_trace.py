#!/usr/bin/env python3
"""Tests for run_trace.py CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


TRACE_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'run_trace.py')
CM_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'citation_manager.py')
PLAN_SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'plan.schema.json')
COVERAGE_SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'coverage_map.schema.json')
RUN_SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'run_manifest.schema.json')
EVIDENCE_SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'evidence.schema.json')


def run_script(script: str, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


def run_script_raw(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
        text=True,
    )


class RunTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_script(CM_SCRIPT, 'init-run', '--out-dir', self.tmpdir, '--query', 'trace test', '--mode', 'deep')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_provider_subagent_and_coverage_update_manifest(self):
        call = run_script(
            TRACE_SCRIPT,
            'provider-call',
            '--dir', self.tmpdir,
            '--provider', 'perplexity',
            '--tool', 'perplexity_search',
            '--query', 'trace test primary sources',
            '--lane-id', 'lane_primary',
            '--query-family-id', 'lane_primary_core',
            '--result-count', '40',
            '--retained-source-count', '30',
            '--input-tokens', '1000',
            '--output-tokens', '250',
            '--cost-usd', '0.1234',
        )
        self.assertEqual(call['status'], 'ok')

        agent = run_script(
            TRACE_SCRIPT,
            'subagent',
            '--dir', self.tmpdir,
            '--subagent-id', 'agent_001',
            '--lane-id', 'lane_corroboration',
            '--role', 'corroboration',
            '--model', 'fixture-model',
            '--reasoning', 'medium',
            '--source-count', '25',
            '--evidence-count', '10',
        )
        self.assertEqual(agent['status'], 'ok')

        coverage = run_script(TRACE_SCRIPT, 'coverage', '--dir', self.tmpdir)
        self.assertEqual(coverage['overall']['status'], 'covered')

        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(len(manifest['execution_trace']['provider_calls']), 1)
        self.assertEqual(len(manifest['execution_trace']['subagents']), 1)
        self.assertEqual(manifest['execution_trace']['lane_source_counts']['lane_primary'], 30)
        self.assertEqual(manifest['execution_trace']['lane_source_counts']['lane_corroboration'], 25)
        retrieval_metrics = manifest['execution_trace']['phase_metrics']['retrieval']
        self.assertEqual(retrieval_metrics['provider_call_count'], 1)
        self.assertEqual(retrieval_metrics['subagent_count'], 1)
        self.assertEqual(retrieval_metrics['input_tokens'], 1000)
        self.assertEqual(retrieval_metrics['output_tokens'], 250)
        self.assertEqual(retrieval_metrics['total_tokens'], 1250)
        self.assertAlmostEqual(retrieval_metrics['estimated_cost_usd'], 0.1234)

        with open(os.path.join(self.tmpdir, 'coverage_map.json')) as f:
            coverage_map = json.load(f)
        by_lane = {lane['lane_id']: lane for lane in coverage_map['lane_coverage']}
        self.assertEqual(by_lane['lane_primary']['status'], 'covered')
        self.assertEqual(by_lane['lane_corroboration']['status'], 'covered')

    def test_coverage_can_mark_lane_gap_disclosed(self):
        run_script(
            TRACE_SCRIPT,
            'provider-call',
            '--dir', self.tmpdir,
            '--provider', 'perplexity',
            '--tool', 'perplexity_search',
            '--query', 'limited evidence query',
            '--lane-id', 'lane_primary',
            '--query-family-id', 'lane_primary_core',
            '--retained-source-count', '3',
        )
        out = run_script(
            TRACE_SCRIPT,
            'coverage',
            '--dir', self.tmpdir,
            '--lane-status', 'lane_primary=gap_disclosed',
            '--lane-gap', 'lane_primary=Only three primary sources were available.',
            '--lane-status', 'lane_corroboration=bounded',
        )
        self.assertEqual(out['status'], 'ok')
        with open(os.path.join(self.tmpdir, 'coverage_map.json')) as f:
            coverage_map = json.load(f)
        by_lane = {lane['lane_id']: lane for lane in coverage_map['lane_coverage']}
        self.assertEqual(by_lane['lane_primary']['status'], 'gap_disclosed')
        self.assertIn('Only three primary sources', by_lane['lane_primary']['gaps'][0])
        self.assertEqual(by_lane['lane_corroboration']['status'], 'bounded')

    def test_schema_files_expose_p1_2_contract(self):
        with open(PLAN_SCHEMA) as f:
            plan_schema = json.load(f)
        with open(COVERAGE_SCHEMA) as f:
            coverage_schema = json.load(f)
        with open(RUN_SCHEMA) as f:
            run_schema = json.load(f)
        with open(EVIDENCE_SCHEMA) as f:
            evidence_schema = json.load(f)

        self.assertEqual(plan_schema['title'], 'ResearchPlan')
        self.assertIn('checkpoint', plan_schema['properties'])
        lane_props = plan_schema['properties']['lanes']['items']['properties']
        self.assertIn('execution_budget', lane_props)
        self.assertIn('other', lane_props['role']['enum'])
        self.assertEqual(lane_props['expected_roles']['items']['type'], 'string')
        self.assertEqual(coverage_schema['title'], 'CoverageMap')
        self.assertIn('plan', run_schema['properties']['artifact_paths']['properties'])
        self.assertIn('coverage_map', run_schema['properties']['artifact_paths']['properties'])
        self.assertIn('execution_trace', run_schema['properties'])
        self.assertIn('phase_metrics', run_schema['properties']['execution_trace']['properties'])
        self.assertIn('provider', evidence_schema['properties'])
        self.assertIn('subagent_id', evidence_schema['properties'])
        self.assertIn('subagent_role', evidence_schema['properties'])

    def test_deep_crawler_lane_uses_other_plan_role_and_executed_role_trace(self):
        plan_path = os.path.join(self.tmpdir, 'plan.json')
        with open(plan_path) as f:
            plan = json.load(f)
        plan['lanes'] = [{
            'lane_id': 'lane_deep_crawler',
            'role': 'other',
            'objective': 'Bounded browser rendering for a hard-target public page.',
            'query_families': [{
                'query_family_id': 'deep_crawler_known_urls',
                'description': 'Known public URLs surfaced by prior retrieval.',
                'queries': ['https://example.com/public-dynamic-page'],
            }],
            'expected_source_min': 1,
            'expected_roles': ['deep_crawler'],
            'execution_budget': {
                'model_hint': 'runtime_default',
                'reasoning_effort': 'medium',
                'timeout_seconds': 600,
                'max_tool_calls': 5,
            },
            'stop_conditions': ['Stop on login, paywall, CAPTCHA, robots/access-control, rate-limit, or terms-of-use boundary.'],
        }]
        with open(plan_path, 'w') as f:
            json.dump(plan, f, indent=2)
            f.write('\n')

        agent = run_script(
            TRACE_SCRIPT,
            'subagent',
            '--dir', self.tmpdir,
            '--subagent-id', 'crawler_001',
            '--lane-id', 'lane_deep_crawler',
            '--role', 'deep_crawler',
            '--model', 'fixture-model',
            '--reasoning', 'medium',
            '--source-count', '1',
            '--evidence-count', '1',
        )
        self.assertEqual(agent['status'], 'ok')

        coverage = run_script(TRACE_SCRIPT, 'coverage', '--dir', self.tmpdir)
        self.assertEqual(coverage['overall']['status'], 'covered')
        with open(os.path.join(self.tmpdir, 'coverage_map.json')) as f:
            coverage_map = json.load(f)
        by_lane = {lane['lane_id']: lane for lane in coverage_map['lane_coverage']}
        self.assertEqual(by_lane['lane_deep_crawler']['executed_role'], 'deep_crawler')
        self.assertEqual(by_lane['lane_deep_crawler']['status'], 'covered')

    def test_interactive_plan_must_be_approved_before_retrieval_trace(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.tmpdir = tempfile.mkdtemp()
        run_script(
            CM_SCRIPT,
            'init-run',
            '--out-dir', self.tmpdir,
            '--query', 'interactive trace test',
            '--mode', 'standard',
            '--interactive',
        )

        blocked = run_script_raw(
            TRACE_SCRIPT,
            'provider-call',
            '--dir', self.tmpdir,
            '--provider', 'perplexity',
            '--tool', 'perplexity_search',
            '--query', 'blocked before approval',
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('approve-plan', blocked.stderr)

        plan_path = os.path.join(self.tmpdir, 'plan.json')
        with open(plan_path) as f:
            plan = json.load(f)
        plan['lanes'][0]['query_families'][0]['queries'].append('edited query')
        with open(plan_path, 'w') as f:
            json.dump(plan, f, indent=2)
            f.write('\n')

        approved = run_script(
            TRACE_SCRIPT,
            'approve-plan',
            '--dir', self.tmpdir,
            '--approved-by', 'tester',
            '--note', 'Plan reviewed and edited.',
        )
        self.assertEqual(approved['status'], 'ok')
        self.assertEqual(approved['checkpoint']['status'], 'edited_approved')
        self.assertTrue(approved['checkpoint']['edits_detected'])

        call = run_script(
            TRACE_SCRIPT,
            'provider-call',
            '--dir', self.tmpdir,
            '--provider', 'perplexity',
            '--tool', 'perplexity_search',
            '--query', 'allowed after approval',
            '--retained-source-count', '1',
        )
        self.assertEqual(call['status'], 'ok')

    def test_phase_command_records_latency_token_and_cost_metrics(self):
        out = run_script(
            TRACE_SCRIPT,
            'phase',
            '--dir', self.tmpdir,
            '--phase', 'synthesis',
            '--status', 'ok',
            '--duration-seconds', '12.5',
            '--provider-call-count', '2',
            '--retained-source-count', '7',
            '--evidence-count', '5',
            '--input-tokens', '500',
            '--output-tokens', '125',
            '--cost-usd', '0.045',
        )

        self.assertEqual(out['status'], 'ok')
        metrics = out['metrics']
        self.assertEqual(metrics['phase'], 'synthesis')
        self.assertEqual(metrics['provider_call_count'], 2)
        self.assertEqual(metrics['retained_source_count'], 7)
        self.assertEqual(metrics['evidence_count'], 5)
        self.assertEqual(metrics['total_tokens'], 625)
        self.assertAlmostEqual(metrics['duration_seconds'], 12.5)
        self.assertAlmostEqual(metrics['estimated_cost_usd'], 0.045)

    def test_package_phase_then_finish_run_share_timestamp(self):
        finished_at = '2026-07-05T01:02:03Z'
        phase_out = run_script(
            TRACE_SCRIPT,
            'phase',
            '--dir', self.tmpdir,
            '--phase', 'package',
            '--status', 'ok',
            '--finished-at', finished_at,
            '--duration-seconds', '7',
            '--input-tokens', '100',
            '--output-tokens', '25',
            '--cost-usd', '0.01',
        )
        self.assertEqual(phase_out['metrics']['finished_at'], finished_at)

        finish_out = run_script(
            CM_SCRIPT,
            'finish-run',
            '--dir', self.tmpdir,
            '--finished-at', finished_at,
            '--report', 'report.md',
            '--note', 'Delivery gate passed.',
        )
        self.assertEqual(finish_out['finished_at'], finished_at)

        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(manifest['finished_at'], finished_at)
        self.assertEqual(manifest['execution_trace']['phase_metrics']['package']['finished_at'], finished_at)
        finish_events = [
            event for event in manifest['execution_trace']['events']
            if event['phase'] == 'finish_run'
        ]
        self.assertEqual(len(finish_events), 1)


if __name__ == '__main__':
    unittest.main()
