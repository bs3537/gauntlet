#!/usr/bin/env python3
"""Tests for cross_model_critique.py."""

import json
import importlib.util
import os
import shlex
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
        return 'claude'
    if surface == '.codex':
        return 'codex'
    if surface == '.gemini':
        return 'agy'
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
            'generator_identity': {
                'model': 'selected-model',
                'reasoning_effort': 'xhigh',
                'recorded_at': '2026-07-05T00:00:00Z',
            },
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
        self.assertIn('Locked artifact inventory', prompt)
        self.assertTrue(out['locked_artifacts'])

        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertNotIn('cross_model_critiques', manifest)

    def test_omitted_reviewer_uses_surface_default(self):
        out = run_script('build-prompt', '--dir', self.tmpdir, '--report', self.report_path)
        expected = expected_default_reviewer()

        self.assertEqual(out['reviewer'], expected)
        self.assertTrue(out['prompt_path'].endswith(f'{expected}_prompt.md'))
        with open(os.path.join(self.tmpdir, 'run_manifest.json')) as f:
            manifest = json.load(f)
        self.assertNotIn('cross_model_critiques', manifest)

    def test_default_commands_fail_closed_without_selected_model_and_effort(self):
        module = load_script_module()

        self.assertIsNone(module.default_command('codex'))
        self.assertIsNone(module.default_command('claude'))

    def test_model_and_effort_overrides_do_not_require_full_command_replacement(self):
        module = load_script_module()

        codex_command = module.default_command('codex', model='gpt-5.6', effort='max')
        self.assertIn('codex exec --model gpt-5.6', codex_command)
        self.assertIn('model_reasoning_effort="max"', codex_command)

        claude_command = module.default_command('claude', model='claude-opus-next', effort='max')
        self.assertIn('claude --print --model claude-opus-next', claude_command)
        self.assertIn('--effort max', claude_command)

    def test_environment_command_override_is_ignored(self):
        module = load_script_module()

        with mock.patch.dict(os.environ, {'DEEP_RESEARCH_SAME_MODEL_CLAUDE_COMMAND': 'custom claude'}):
            self.assertIn('claude --print --model selected-model', module.default_command('claude', model='selected-model', effort='xhigh'))
        with mock.patch.dict(os.environ, {'DEEP_RESEARCH_SAME_MODEL_CODEX_COMMAND': 'custom codex'}):
            self.assertIn('codex exec --model selected-model', module.default_command('codex', model='selected-model', effort='xhigh'))

    def test_run_rejects_identity_mismatch(self):
        module = load_script_module()
        manifest = json.loads(Path(self.tmpdir, 'run_manifest.json').read_text(encoding='utf-8'))
        with self.assertRaises(SystemExit):
            module.validate_generator_identity(manifest, 'wrong-model', 'xhigh')
        with self.assertRaises(SystemExit):
            module.validate_generator_identity(manifest, 'selected-model', 'medium')

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
            model='selected-model',
            effort='xhigh',
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
        self.assertEqual(captured['command'], module.default_command(expected, model='selected-model', effort='xhigh'))
        self.assertIn('Claims sample', captured['prompt'])
        self.assertEqual(out['model'], 'selected-model')
        self.assertEqual(out['reasoning_effort'], 'xhigh')

    def test_run_rejects_non_reviewer_command(self):
        reviewer = expected_default_reviewer()
        reviewer_script = os.path.join(self.tmpdir, 'reviewer.py')
        Path(reviewer_script).write_text(
            'import sys\n'
            'prompt = sys.stdin.read()\n'
            'print("REVIEW OK")\n'
            'print("Claims sample" in prompt)\n',
            encoding='utf-8',
        )

        result = subprocess.run(
            [sys.executable, SCRIPT, 'run', '--dir', self.tmpdir, '--report', self.report_path,
             '--reviewer', reviewer, '--model', 'selected-model', '--effort', 'xhigh',
             '--command', f'{sys.executable} {reviewer_script}', '--timeout', '30'],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must invoke', result.stderr)

    def test_validator_rejects_model_or_effort_as_stray_tokens(self):
        module = load_script_module()
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(
                'codex exec --model wrong -c model_reasoning_effort=low --ephemeral selected-model xhigh',
                'codex', 'selected-model', 'xhigh',
            )
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(
                'claude --print --model wrong --effort low --no-session-persistence selected-model xhigh',
                'claude', 'selected-model', 'xhigh',
            )
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(
                'codex exec --model selected-model --model wrong -c model_reasoning_effort=xhigh --ephemeral',
                'codex', 'selected-model', 'xhigh',
            )
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(
                'claude --print --model selected-model --model wrong --effort xhigh --no-session-persistence',
                'claude', 'selected-model', 'xhigh',
            )

    def test_validator_rejects_extra_arguments_missing_isolation_and_same_name_wrapper(self):
        module = load_script_module()
        reviewer = expected_default_reviewer()
        valid = module.default_command(reviewer, model='selected-model', effort='xhigh')
        self.assertEqual(shlex.split(valid)[0], str(Path.home() / '.local' / 'bin' / reviewer))
        isolation = '--ephemeral' if reviewer == 'codex' else '--no-session-persistence'
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(f'{valid} -- --model wrong', reviewer, 'selected-model', 'xhigh')
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(valid.replace(isolation, ''), reviewer, 'selected-model', 'xhigh')
        wrapper = Path(self.tmpdir) / reviewer
        wrapper.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        wrapped = valid.replace(reviewer, str(wrapper), 1)
        with self.assertRaises(SystemExit):
            module.validate_reviewer_command(wrapped, reviewer, 'selected-model', 'xhigh')

        shadow_dir = Path(self.tmpdir) / 'shadow'
        shadow_dir.mkdir()
        shadow = shadow_dir / reviewer
        shadow.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        shadow.chmod(0o755)
        with mock.patch.dict(os.environ, {'PATH': f'{shadow_dir}:{os.environ.get("PATH", "")}'}, clear=False):
            module.validate_reviewer_command(valid, reviewer, 'selected-model', 'xhigh')

    def test_run_detects_locked_artifact_mutation(self):
        module = load_script_module()
        reviewer = expected_default_reviewer()

        def mutating_run(command, prompt, timeout):
            Path(self.report_path).write_text('changed during review\n', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, 'REVIEW OK\n', '')

        args = SimpleNamespace(
            dir=self.tmpdir, report=self.report_path, reviewer=reviewer,
            model='selected-model', effort='xhigh', out_dir=None,
            max_claims=12, max_report_chars=50000, timeout=30, command=None,
        )
        with mock.patch.object(module, 'run_reviewer_command', mutating_run):
            out = module.execute(args, run_command=True)
        self.assertEqual(out['status'], 'failed_artifact_mutation')

    def test_lock_includes_external_manifest_artifact_and_rejects_output_ancestor(self):
        module = load_script_module()
        external = Path(self.tmpdir).parent / f'{Path(self.tmpdir).name}-external.txt'
        external.write_text('locked external input\n', encoding='utf-8')
        self.addCleanup(external.unlink, missing_ok=True)
        manifest_path = Path(self.tmpdir, 'run_manifest.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['artifact_paths']['external_model'] = str(external)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        rows = module.locked_artifacts(Path(self.tmpdir), manifest, Path(self.report_path))
        self.assertIn(str(external.resolve()), {row['path'] for row in rows})

        args = SimpleNamespace(
            dir=self.tmpdir, report=self.report_path, reviewer=expected_default_reviewer(),
            model='selected-model', effort='xhigh', out_dir=str(Path(self.tmpdir).parent),
            max_claims=12, max_report_chars=50000, timeout=30, command=None,
        )
        with self.assertRaises(SystemExit):
            module.execute(args, run_command=False)


if __name__ == '__main__':
    unittest.main()
