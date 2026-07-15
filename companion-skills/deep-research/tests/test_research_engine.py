#!/usr/bin/env python3
"""Tests for research_engine.py phase instruction provider."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCRIPT = os.path.join(ROOT, 'scripts', 'research_engine.py')


def expected_default_reviewer() -> str:
    surface = Path(ROOT).parents[1].name
    if surface == '.claude':
        return 'codex'
    if surface in {'.codex', '.gemini'}:
        return 'claude'
    return 'codex'


class TestResearchEnginePhaseProvider(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import research_engine
        cls.engine = research_engine

    def test_engine_version_matches_manifest_version(self):
        self.assertEqual(self.engine.ENGINE_VERSION, '3.0.0')

    def test_phase_sequence_matches_documented_deep_pipeline(self):
        phases = self.engine.phase_sequence('deep')
        values = [phase.value for phase in phases]
        self.assertIn('clarify_or_brief', values)
        self.assertIn('outline_refinement', values)
        self.assertIn('audit', values)
        self.assertNotIn('cross_model_critique', values)

        with_optional = self.engine.phase_sequence('deep', include_optional=True)
        optional_values = [phase.value for phase in with_optional]
        self.assertIn('cross_model_critique', optional_values)
        self.assertLess(optional_values.index('cross_model_critique'), optional_values.index('package'))

    def test_single_phase_cli_prints_phase_4_5(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, '--phase', '4.5'],
            capture_output=True, text=True, check=True,
        )
        self.assertIn('Phase 4.5: OUTLINE REFINEMENT', result.stdout)
        self.assertIn('evidence actually gathered', result.stdout)

    def test_synthesize_phase_blocks_drafting_before_retrieval_closure(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, '--phase', 'synthesize'],
            capture_output=True, text=True, check=True,
        )
        self.assertIn('Do not draft report prose while retrieval is still active', result.stdout)
        self.assertIn('coverage_map.json.overall.status', result.stdout)
        self.assertIn('audit/section_citation_issues', result.stdout)

    def test_package_phase_requires_section_citation_audits(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, '--phase', 'package'],
            capture_output=True, text=True, check=True,
        )
        self.assertIn('--require-section-citation-audits', result.stdout)
        self.assertIn('audit/section_citation_issues', result.stdout)

    def test_cross_model_phase_uses_surface_default_reviewer(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, '--phase', 'cross_model_critique'],
            capture_output=True, text=True, check=True,
        )
        self.assertIn(f'--reviewer {expected_default_reviewer()}', result.stdout)

    def test_json_manifest_declares_external_state_model(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, '--query', 'test', '--mode', 'ultradeep', '--include-optional', '--json'],
            capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload['version'], '3.0.0')
        self.assertFalse(payload['orchestrator'])
        self.assertEqual(payload['state_model'], 'external_ledgers')
        self.assertEqual(payload['deprecated_classes'], ['Source', 'ResearchState'])
        numbers = [phase['number'] for phase in payload['phases']]
        self.assertIn('0.5', numbers)
        self.assertIn('4.5', numbers)
        self.assertIn('7.5', numbers)
        self.assertIn('7.6', numbers)

    def test_deprecated_state_serializes_versioned_warning_metadata(self):
        with self.assertWarns(DeprecationWarning):
            state = self.engine.ResearchState(
                query='test',
                mode=self.engine.ResearchMode.STANDARD,
                phase=self.engine.ResearchPhase.CLARIFY_OR_BRIEF,
            )
        serialized = state._serialize()
        self.assertEqual(serialized['metadata']['version'], 'legacy-1.0')
        self.assertEqual(serialized['metadata']['pipeline_version'], '3.0.0')
        self.assertTrue(serialized['metadata']['deprecated_state_model'])


if __name__ == '__main__':
    unittest.main()
