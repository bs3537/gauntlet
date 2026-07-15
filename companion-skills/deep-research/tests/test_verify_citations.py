#!/usr/bin/env python3
"""Tests for verify_citations.py."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SCHEMA = Path(__file__).resolve().parents[1] / 'schemas' / 'source.schema.json'


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b'{}'):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


class VerifyCitationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(SCRIPTS))
        from verify_citations import CitationVerifier
        cls.CitationVerifier = CitationVerifier

    def make_verifier(self, tmpdir: str):
        report = Path(tmpdir) / 'report.md'
        report.write_text('# Report\n')
        return self.CitationVerifier(report, cache_path=Path(tmpdir) / 'cache.json')

    def test_extracts_doi_from_canonical_locator_and_provider_ids(self):
        with tempfile.TemporaryDirectory() as d:
            verifier = self.make_verifier(d)
            self.assertEqual(
                verifier.extract_doi({'canonical_locator': 'doi:10.1234/example.2026'}),
                '10.1234/example.2026',
            )
            self.assertEqual(
                verifier.extract_doi({'provider_ids': {'DOI': '10.5678/provider-id'}}),
                '10.5678/provider-id',
            )

    def test_sources_jsonl_doi_locator_verifies_via_doi_without_url_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            verifier = self.make_verifier(d)
            sources_path = Path(d) / 'sources.jsonl'
            sources_path.write_text(json.dumps({
                'source_id': '400b560aee0da44f',
                'canonical_locator': 'doi:10.5555/p2-10.case',
                'raw_url': 'https://publisher.example/p2-10-case',
                'title': 'P2-10 DOI Case',
                'year': '2026',
                'source_type': 'academic',
                'metadata_status': 'unverified',
                'registered_at': '2026-07-05T00:00:00Z',
            }) + '\n')

            entries = verifier.extract_sources_jsonl(sources_path)
            self.assertEqual(entries[0]['doi'], '10.5555/p2-10.case')

            with (
                mock.patch.object(verifier, 'verify_doi', return_value=(True, {
                    'title': 'P2-10 DOI Case',
                    'year': 2026,
                })) as verify_doi,
                mock.patch.object(verifier, 'verify_url') as verify_url,
            ):
                result = verifier.verify_entry(entries[0])

            self.assertEqual(result['status'], 'verified')
            verify_doi.assert_called_once_with('10.5555/p2-10.case')
            verify_url.assert_not_called()

    def test_url_head_405_uses_get_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            verifier = self.make_verifier(d)
            calls = []

            def fake_open(url, method):
                calls.append(method)
                if method == 'HEAD':
                    raise error.HTTPError(url, 405, 'Method Not Allowed', hdrs=None, fp=None)
                return FakeResponse(200)

            with mock.patch.object(verifier, 'open_url_check', side_effect=fake_open):
                ok, status = verifier.verify_url('https://example.com/report')

            self.assertTrue(ok)
            self.assertEqual(status, 'URL accessible via GET fallback')
            self.assertEqual(calls, ['HEAD', 'GET'])

    def test_restricted_allowlisted_url_is_warning_not_failure(self):
        with tempfile.TemporaryDirectory() as d:
            verifier = self.make_verifier(d)

            def fake_open(url, method):
                raise error.HTTPError(url, 403, 'Forbidden', hdrs=None, fp=None)

            with mock.patch.object(verifier, 'open_url_check', side_effect=fake_open):
                ok, status = verifier.verify_url('https://www.nature.com/articles/test')

            self.assertTrue(ok)
            self.assertIn('Restricted/paywalled', status)

    def test_url_cache_reuses_result(self):
        with tempfile.TemporaryDirectory() as d:
            verifier = self.make_verifier(d)
            with mock.patch.object(verifier, 'open_url_check', return_value=FakeResponse(200)) as opened:
                self.assertTrue(verifier.verify_url('https://example.com/cache')[0])
                self.assertTrue(verifier.verify_url('https://example.com/cache')[0])

            self.assertEqual(opened.call_count, 1)

    def test_source_schema_has_scite_editorial_notice_fields(self):
        schema = json.loads(SCHEMA.read_text())
        self.assertIn('editorial_notice_status', schema['properties'])
        self.assertIn('scite_checked_at', schema['properties'])


if __name__ == '__main__':
    unittest.main()
