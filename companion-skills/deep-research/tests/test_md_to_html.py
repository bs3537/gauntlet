#!/usr/bin/env python3
"""Tests for md_to_html.py."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SCRIPT = SCRIPTS / 'md_to_html.py'


class MdToHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        import md_to_html
        cls.md_to_html = md_to_html

    def test_cli_writes_final_html_with_escaped_code_and_no_placeholders(self):
        markdown = """# Host <Report>

## Executive Summary

AT&T revenue was **higher** in `Q1` [1].

```python
if a < b:
    print("unsafe & escaped")
```

## Analysis

| Metric | Value |
| --- | --- |
| Unsafe | <script>alert("x")</script> |

## Bibliography

[1] AT&T filing - https://example.com/att
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = tmp_path / 'report.md'
            html_path = tmp_path / 'report.html'
            md_path.write_text(markdown, encoding='utf-8')
            (tmp_path / 'sources.jsonl').write_text('{"source_id":"s1"}\n', encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(md_path),
                    '--out',
                    str(html_path),
                    '--date',
                    '2026-07-05',
                    '--run-dir',
                    str(tmp_path),
                    '--metric',
                    'Sources=1',
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            html = html_path.read_text(encoding='utf-8')
            self.assertIn('<title>Host &lt;Report&gt; - Deep Research Report</title>', html)
            self.assertIn('<pre><code class="language-python">', html)
            self.assertIn('if a &lt; b:', html)
            self.assertIn('&lt;script&gt;alert("x")&lt;/script&gt;', html)
            self.assertIn('<table class="data-table">', html)
            self.assertIn('class="bibliography"', html)
            self.assertNotIn('{{CONTENT}}', html)
            self.assertNotIn('<script>alert("x")</script>', html)

    def test_bibliography_is_empty_unless_explicit_section_exists(self):
        html_doc = self.md_to_html.render_report_html(
            '# Title\n\n## Executive Summary\n\nClaim [1].',
            report_date='2026-07-05',
        )

        self.assertNotIn('class="bibliography"', html_doc)
        self.assertIn('[1]', html_doc)

    def test_source_count_prefers_sources_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / 'sources.jsonl'
            ledger.write_text('{"source_id":"a"}\n{"source_id":"b"}\n', encoding='utf-8')

            count = self.md_to_html.count_sources('Claim [1].', ledger)

            self.assertEqual(count, 2)

    def test_chrome_pdf_uses_windows_paths_for_windows_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'report.html'
            pdf_path = Path(tmp) / 'report.pdf'
            html_path.write_text('<html></html>', encoding='utf-8')

            with mock.patch.object(
                self.md_to_html,
                'find_chrome',
                return_value='/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
            ), mock.patch.object(
                self.md_to_html,
                'wsl_to_windows_path',
                side_effect=lambda p: 'C:\\tmp\\' + Path(p).name,
            ), mock.patch.object(
                self.md_to_html,
                'windows_file_url',
                return_value='file:///C:/tmp/report.html',
            ), mock.patch.object(self.md_to_html.subprocess, 'run') as run:
                self.md_to_html.render_pdf_with_chrome(html_path, pdf_path)

            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe')
            self.assertIn('--print-to-pdf=C:\\tmp\\report.pdf', cmd)
            self.assertIn('file:///C:/tmp/report.html', cmd)


if __name__ == '__main__':
    unittest.main()
