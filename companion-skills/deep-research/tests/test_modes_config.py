#!/usr/bin/env python3
"""P1-F: depth-mode constants live in modes.json, not in scattered prose.

The point is a single mechanical source of truth. These tests assert that the
file exists, is complete, and agrees with the constants the scripts actually
enforce -- so a future edit to one and not the other fails here rather than
silently producing a run that does not match its documented mode.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(ROOT / 'scripts')
CITATION_MANAGER = str(ROOT / 'scripts' / 'citation_manager.py')
MODES_PATH = ROOT / 'modes.json'

MODES = ('quick', 'standard', 'deep', 'ultradeep')
REQUIRED_KEYS = (
    'research_lanes',
    'query_families_per_lane',
    'material_claim_target_per_lane',
    'judge_candidate_cap',
    'judge_packets',
    'research_subagents',
    'source_floor',
)


def load_modes() -> dict:
    with open(MODES_PATH) as f:
        return json.load(f)


class ModesConfigTests(unittest.TestCase):
    def test_modes_file_exists_and_covers_every_mode(self):
        config = load_modes()
        self.assertIn('modes', config)
        self.assertEqual(set(config['modes']), set(MODES))

    def test_every_mode_defines_every_required_constant(self):
        config = load_modes()
        for mode in MODES:
            for key in REQUIRED_KEYS:
                self.assertIn(key, config['modes'][mode], f'{mode} is missing {key}')

    def test_ultradeep_pins_exactly_four_lanes_and_four_subagents(self):
        """CLAUDE.md hard rule: ultradeep is exactly four concurrent lanes."""
        ultradeep = load_modes()['modes']['ultradeep']
        self.assertEqual(ultradeep['research_lanes'], 4)
        self.assertEqual(ultradeep['research_subagents'], 4)

    def test_source_floors_match_audit_manifest_constants(self):
        sys.path.insert(0, SCRIPTS_DIR)
        import audit_manifest

        config = load_modes()['modes']
        for mode in MODES:
            self.assertEqual(
                config[mode]['source_floor'],
                audit_manifest.MODE_SOURCE_TARGETS[mode],
                f'{mode} source_floor disagrees with MODE_SOURCE_TARGETS',
            )

    def test_lane_counts_match_audit_manifest_constants(self):
        sys.path.insert(0, SCRIPTS_DIR)
        import audit_manifest

        config = load_modes()['modes']
        for mode in MODES:
            self.assertEqual(
                config[mode]['research_lanes'],
                audit_manifest.MODE_LANE_TARGETS[mode],
                f'{mode} research_lanes disagrees with MODE_LANE_TARGETS',
            )

    def test_lane_counts_match_citation_manager_plan_defaults(self):
        sys.path.insert(0, SCRIPTS_DIR)
        import citation_manager

        config = load_modes()['modes']
        for mode in MODES:
            self.assertEqual(
                config[mode]['research_lanes'],
                len(citation_manager.MODE_LANE_DEFAULTS[mode]),
                f'{mode} research_lanes disagrees with MODE_LANE_DEFAULTS',
            )

    def test_judge_packets_never_exceed_the_candidate_cap(self):
        config = load_modes()['modes']
        for mode in MODES:
            self.assertLessEqual(
                config[mode]['judge_packets'],
                config[mode]['judge_candidate_cap'],
                f'{mode} would shard more packets than it can fill',
            )

    def test_init_run_emits_lane_count_matching_modes_json(self):
        config = load_modes()['modes']
        for mode in MODES:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        sys.executable, CITATION_MANAGER, 'init-run',
                        '--out-dir', tmpdir,
                        '--query', 'modes consistency check',
                        '--mode', mode,
                    ],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                with open(os.path.join(tmpdir, 'plan.json')) as f:
                    plan = json.load(f)
                self.assertEqual(
                    len(plan['lanes']),
                    config[mode]['research_lanes'],
                    f'{mode} init-run produced a lane count that modes.json does not describe',
                )

    def test_init_run_records_the_mode_budget_on_the_manifest(self):
        config = load_modes()['modes']
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable, CITATION_MANAGER, 'init-run',
                    '--out-dir', tmpdir,
                    '--query', 'modes budget check',
                    '--mode', 'ultradeep',
                ],
                capture_output=True, text=True, check=True,
            )
            with open(os.path.join(tmpdir, 'run_manifest.json')) as f:
                manifest = json.load(f)
        self.assertEqual(manifest['mode_budget'], config['ultradeep'])


if __name__ == '__main__':
    unittest.main()
