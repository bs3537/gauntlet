#!/usr/bin/env python3
"""Smoke tests for file_ingest.py local file ingestion."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INGEST_SCRIPT = ROOT / 'scripts' / 'file_ingest.py'
CM_SCRIPT = ROOT / 'scripts' / 'citation_manager.py'


def run_json(script: Path, *args: str, check: bool = True) -> tuple[dict, subprocess.CompletedProcess]:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return payload, result


class FileIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        run_json(CM_SCRIPT, 'init-run', '--out-dir', str(self.tmpdir), '--query', 'file ingest test')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def read_jsonl(self, name: str) -> list[dict]:
        path = self.tmpdir / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_csv_ingest_registers_dataset_profile_and_data_point_evidence(self):
        csv_path = self.tmpdir / 'revenue.csv'
        csv_path.write_text('year,revenue\n2024,10\n2025,12\n', encoding='utf-8')

        out, result = run_json(
            INGEST_SCRIPT,
            'ingest',
            '--dir', str(self.tmpdir),
            '--file', str(csv_path),
            '--title', 'Revenue table',
            '--source-tier', 'primary',
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['file_kind'], 'csv')
        self.assertEqual(out['extraction_status'], 'parsed')
        self.assertGreaterEqual(out['evidence_added'], 2)

        sources = self.read_jsonl('sources.jsonl')
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['source_type'], 'dataset')
        self.assertTrue(sources[0]['canonical_locator'].startswith('file-sha256:'))

        manifests = self.read_jsonl('file_manifest.jsonl')
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]['source_id'], out['source_id'])
        self.assertEqual(manifests[0]['extraction_status'], 'parsed')

        profiles = self.read_jsonl('data_profile.jsonl')
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]['row_count'], 2)
        self.assertEqual(profiles[0]['column_count'], 2)
        self.assertIn('revenue', profiles[0]['numeric_columns'])

        evidence = self.read_jsonl('evidence.jsonl')
        quotes = [row['quote'] for row in evidence]
        self.assertTrue(any('contains 2 rows and 2 columns' in quote for quote in quotes))
        self.assertTrue(any("Column 'revenue'" in quote for quote in quotes))
        self.assertTrue(all(row['provider'] == 'local_file_ingest' for row in evidence))

    def test_pdf_without_text_extraction_registers_followup_without_fake_evidence(self):
        pdf_path = self.tmpdir / 'deck.pdf'
        pdf_path.write_bytes(b'%PDF-1.4\n% minimal invalid test pdf\n')

        out, result = run_json(
            INGEST_SCRIPT,
            'ingest',
            '--dir', str(self.tmpdir),
            '--file', str(pdf_path),
            '--kind', 'pdf',
            '--strict',
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out['status'], 'needs_followup')
        self.assertEqual(out['file_kind'], 'pdf')
        self.assertEqual(out['extraction_status'], 'registered_needs_pdf_text')
        self.assertTrue(out['actions_required'])
        self.assertEqual(out['evidence_added'], 0)

        sources = self.read_jsonl('sources.jsonl')
        self.assertEqual(sources[0]['source_type'], 'pdf')
        manifests = self.read_jsonl('file_manifest.jsonl')
        self.assertEqual(manifests[0]['actions_required'], out['actions_required'])

    def test_png_image_registers_dimensions_and_requires_vision_or_ocr(self):
        png_path = self.tmpdir / 'chart.png'
        png_path.write_bytes(
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR'
            + (640).to_bytes(4, 'big')
            + (480).to_bytes(4, 'big')
            + b'\x08\x02\x00\x00\x00'
            + b'\x00\x00\x00\x00'
        )

        out, result = run_json(
            INGEST_SCRIPT,
            'ingest',
            '--dir', str(self.tmpdir),
            '--file', str(png_path),
            '--kind', 'image',
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(out['status'], 'needs_followup')
        self.assertEqual(out['actions_required'], ['vision_or_ocr_required'])
        self.assertEqual(out['evidence_added'], 0)

        sources = self.read_jsonl('sources.jsonl')
        self.assertEqual(sources[0]['source_type'], 'image')
        manifest = self.read_jsonl('file_manifest.jsonl')[0]
        self.assertEqual(manifest['extraction_status'], 'registered_needs_vision_ocr')
        self.assertIn('"width": 640', manifest['artifacts']['image_dimensions'])
        self.assertIn('"height": 480', manifest['artifacts']['image_dimensions'])


if __name__ == '__main__':
    unittest.main()
