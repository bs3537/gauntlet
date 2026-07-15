#!/usr/bin/env python3
"""Tests for cross_model_critique.py."""

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = os.path.join(ROOT, 'scripts', 'cross_model_critique.py')


def expected_default_reviewer() -> str:
    surface = ROOT.parents[1].name
    if surface == '.claude':
        return 'codex'
    if surface in {'.codex', '.gemini'}:
        return 'claude'
    return 'codex'


def load_script_module():
    spec = importlib.util.spec_from_file_location('cross_model_critique_under_test', SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load cross_model_critique.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout)


class CrossModelCritiqueTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.report_path = os.path.join(self.tmpdir, 'report.md')
        Path(self.report_path).write_text(
            '# Report\n\n## Executive Summary\n\nRevenue increased 10 percent [1].\n',
            encoding='utf-8',
        )
        write_jsonl(os.path.join(self.tmpdir, 'claims.jsonl'), [
            {
                'claim_id': 'clm_001',
                'section_id': 'executive_summary',
                'text': 'Revenue increased 10 percent.',
                'claim_type': 'factual',
                'support_status': 'supported',
                'cited_source_ids': ['src_001'],
                'evidence_ids': ['ev_001'],
            }
        ])
        Path(os.path.join(self.tmpdir, 'run_manifest.json')).write_text(json.dumps({
            'version': '3.0.0',
            'query': 'test',
            'mode': 'deep',
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
            },
            'continuation': None,
        }), encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_prompt_writes_artifacts_and_manifest_record(self):
        out = run_script('build-prompt', '--dir', self.tmpdir, '--report', self.report_path, '--reviewer', 'codex')

        self.assertEqual(out['status'], 'prompt_written')
        prompt = Path(out['prompt_path']).read_text(encoding='utf-8')
        self.assertIn('Claims sample', prompt)
        self.assertIn('Revenue increased 10 percent.', prompt)
        self.assertIn('final delivery recommendation', prompt)

        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(manifest['cross_model_critiques'][0]['status'], 'prompt_written')

    def test_omitted_reviewer_uses_surface_default(self):
        out = run_script('build-prompt', '--dir', self.tmpdir, '--report', self.report_path)
        expected = expected_default_reviewer()

        self.assertEqual(out['reviewer'], expected)
        self.assertTrue(out['prompt_path'].endswith(f'{expected}_prompt.md'))
        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(manifest['cross_model_critiques'][-1]['reviewer'], expected)

    def test_default_commands_use_opposite_model_with_highest_effort(self):
        module = load_script_module()

        codex_command = module.default_command('codex')
        self.assertIn('codex exec --model gpt-5.5', codex_command)
        self.assertIn('model_reasoning_effort="xhigh"', codex_command)
        self.assertIn('--ephemeral', codex_command)

        claude_command = module.default_command('claude')
        self.assertIn('claude --print --model opus', claude_command)
        self.assertIn('--effort max', claude_command)
        self.assertIn('--no-session-persistence', claude_command)

    def test_model_and_effort_overrides_do_not_require_full_command_replacement(self):
        module = load_script_module()

        codex_command = module.default_command('codex', model='gpt-5.6', effort='max')
        self.assertIn('codex exec --model gpt-5.6', codex_command)
        self.assertIn('model_reasoning_effort="max"', codex_command)

        claude_command = module.default_command('claude', model='claude-opus-next', effort='max')
        self.assertIn('claude --print --model claude-opus-next', claude_command)
        self.assertIn('--effort max', claude_command)

    def test_environment_command_override_still_takes_precedence(self):
        module = load_script_module()

        with mock.patch.dict(os.environ, {'DEEP_RESEARCH_CROSS_MODEL_CLAUDE_COMMAND': 'custom claude'}):
            self.assertEqual(module.default_command('claude'), 'custom claude')
        with mock.patch.dict(os.environ, {'DEEP_RESEARCH_CROSS_MODEL_CODEX_COMMAND': 'custom codex'}):
            self.assertEqual(module.default_command('codex'), 'custom codex')

    def test_default_run_records_command_without_invoking_external_cli(self):
        module = load_script_module()
        captured = {}

        def fake_run(command, prompt, timeout):
            captured['command'] = command
            captured['prompt'] = prompt
            captured['timeout'] = timeout
            return subprocess.CompletedProcess(command, 0, 'REVIEW OK\n', '')

        args = SimpleNamespace(
            dir=self.tmpdir,
            report=self.report_path,
            reviewer=None,
            model=None,
            effort=None,
            out_dir=None,
            max_claims=12,
            max_report_chars=50000,
            timeout=30,
            command=None,
        )
        with mock.patch.object(module, 'run_reviewer_command', fake_run):
            out = module.execute(args, run_command=True)

        expected = expected_default_reviewer()
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['reviewer'], expected)
        self.assertEqual(captured['command'], module.default_command(expected))
        self.assertIn('Claims sample', captured['prompt'])
        self.assertEqual(out['model'], module.reviewer_profile(expected)['model'])
        self.assertEqual(out['reasoning_effort'], module.reviewer_profile(expected)['reasoning_effort'])

    def test_run_executes_fixture_reviewer_command(self):
        reviewer_script = os.path.join(self.tmpdir, 'reviewer.py')
        Path(reviewer_script).write_text(
            'import sys\n'
            'prompt = sys.stdin.read()\n'
            'print("REVIEW OK")\n'
            'print("Claims sample" in prompt)\n',
            encoding='utf-8',
        )

        out = run_script(
            'run',
            '--dir', self.tmpdir,
            '--report', self.report_path,
            '--reviewer', 'codex',
            '--command', f'{sys.executable} {reviewer_script}',
            '--timeout', '30',
        )

        self.assertEqual(out['status'], 'ok')
        output = Path(out['output_path']).read_text(encoding='utf-8')
        self.assertIn('REVIEW OK', output)
        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(manifest['cross_model_critiques'][-1]['returncode'], 0)


if __name__ == '__main__':
    unittest.main()
