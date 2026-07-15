#!/usr/bin/env python3
"""Render a deep-research Markdown report into final McKinsey-style HTML."""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = SKILL_DIR / 'templates' / 'mckinsey_report_template.html'
BIBLIOGRAPHY_RE = re.compile(r'^##\s+Bibliography\s*$', re.IGNORECASE | re.MULTILINE)


def convert_markdown_to_html(markdown_text: str) -> Tuple[str, str]:
    """Convert Markdown into main report HTML and optional bibliography HTML."""
    content_md, bibliography_md = split_bibliography(markdown_text)
    content_html = MarkdownRenderer(skip_first_h1=True).render(content_md)
    bibliography_html = convert_bibliography_section(bibliography_md)
    return content_html, bibliography_html


def split_bibliography(markdown_text: str) -> Tuple[str, str]:
    """Split a report into content and bibliography Markdown."""
    match = BIBLIOGRAPHY_RE.search(markdown_text)
    if not match:
        return markdown_text, ''
    return markdown_text[:match.start()], markdown_text[match.end():]


def extract_title(markdown_text: str, fallback: str) -> str:
    """Extract a report title from the first H1/H2 heading."""
    for pattern in (r'^#\s+(.+)$', r'^##\s+(.+)$'):
        match = re.search(pattern, markdown_text, re.MULTILINE)
        if match:
            return strip_inline_markdown(match.group(1)).strip() or fallback
    return fallback


def strip_inline_markdown(text: str) -> str:
    """Remove common inline Markdown markers for plain-text metadata."""
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return html.unescape(text)


def count_sources(markdown_text: str, source_ledger: Optional[Path] = None) -> int:
    """Count sources from sources.jsonl when available, else unique report citations."""
    if source_ledger and source_ledger.exists():
        with source_ledger.open(encoding='utf-8') as handle:
            return sum(1 for line in handle if line.strip())
    content_md, _ = split_bibliography(markdown_text)
    citations = set(re.findall(r'\[(?:S|E)?(\d+)\]', content_md))
    return len(citations)


def build_metrics_dashboard(metrics: Sequence[str]) -> str:
    """Build the optional metrics dashboard from LABEL=VALUE pairs."""
    parsed = []
    for metric in metrics:
        if '=' not in metric:
            raise ValueError(f'Metric must be LABEL=VALUE: {metric}')
        label, value = metric.split('=', 1)
        parsed.append((label.strip(), value.strip()))

    if not parsed:
        return ''

    cards = []
    for label, value in parsed[:4]:
        cards.append(
            '            <div class="metric">\n'
            f'                <span class="metric-number">{html.escape(value)}</span>\n'
            f'                <span class="metric-label">{html.escape(label)}</span>\n'
            '            </div>'
        )
    return '<div class="metrics-dashboard">\n' + '\n'.join(cards) + '\n        </div>'


def render_report_html(
    markdown_text: str,
    *,
    template_path: Path = DEFAULT_TEMPLATE,
    title: Optional[str] = None,
    report_date: Optional[str] = None,
    source_count: Optional[int] = None,
    source_ledger: Optional[Path] = None,
    metrics: Sequence[str] = (),
    fallback_title: str = 'Deep Research Report',
) -> str:
    """Render a full HTML document from Markdown and the McKinsey template."""
    template = template_path.read_text(encoding='utf-8')
    content_html, bibliography_html = convert_markdown_to_html(markdown_text)
    report_title = title or extract_title(markdown_text, fallback_title)
    source_total = source_count if source_count is not None else count_sources(markdown_text, source_ledger)
    generated_date = report_date or date.today().isoformat()

    replacements = {
        '{{TITLE}}': html.escape(report_title),
        '{{DATE}}': html.escape(generated_date),
        '{{SOURCE_COUNT}}': str(source_total),
        '{{METRICS_DASHBOARD}}': build_metrics_dashboard(metrics),
        '{{CONTENT}}': content_html,
        '{{BIBLIOGRAPHY}}': bibliography_html,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


class MarkdownRenderer:
    """Small safe Markdown renderer for report packaging."""

    def __init__(self, *, skip_first_h1: bool = False):
        self.skip_first_h1 = skip_first_h1
        self._skipped_h1 = False
        self._lines: List[str] = []
        self._paragraph: List[str] = []
        self._list_type: Optional[str] = None
        self._section_open = False
        self._code_open = False

    def render(self, markdown: str) -> str:
        source_lines = markdown.splitlines()
        index = 0
        while index < len(source_lines):
            line = source_lines[index]

            if self._code_open:
                if line.strip().startswith('```'):
                    self._lines.append('</code></pre>')
                    self._code_open = False
                else:
                    self._lines.append(html.escape(line, quote=False))
                index += 1
                continue

            if line.strip().startswith('```'):
                self._flush_paragraph()
                self._close_list()
                language = line.strip()[3:].strip()
                language_class = ''
                if language:
                    safe_language = re.sub(r'[^A-Za-z0-9_-]', '', language)
                    if safe_language:
                        language_class = f' class="language-{safe_language}"'
                self._lines.append(f'<pre><code{language_class}>')
                self._code_open = True
                index += 1
                continue

            if not line.strip():
                self._flush_paragraph()
                self._close_list()
                index += 1
                continue

            if self._is_table_start(source_lines, index):
                index = self._render_table(source_lines, index)
                continue

            heading = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading:
                self._render_heading(len(heading.group(1)), heading.group(2))
                index += 1
                continue

            list_match = re.match(r'^\s*((?:[-*])|\d+\.)\s+(.+)$', line)
            if list_match:
                marker = list_match.group(1)
                list_type = 'ol' if marker.endswith('.') and marker[:-1].isdigit() else 'ul'
                self._render_list_item(list_type, list_match.group(2))
                index += 1
                continue

            blockquote = re.match(r'^\s*>\s?(.+)$', line)
            if blockquote:
                self._flush_paragraph()
                self._close_list()
                self._lines.append(f'<blockquote>{format_inline(blockquote.group(1))}</blockquote>')
                index += 1
                continue

            self._paragraph.append(line.strip())
            index += 1

        self._flush_paragraph()
        self._close_list()
        if self._code_open:
            self._lines.append('</code></pre>')
            self._code_open = False
        if self._section_open:
            self._lines.append('</div>')
            self._section_open = False
        return '\n'.join(self._lines).strip()

    def _render_heading(self, level: int, text: str) -> None:
        self._flush_paragraph()
        self._close_list()
        if level == 1 and self.skip_first_h1 and not self._skipped_h1:
            self._skipped_h1 = True
            return
        formatted = format_inline(text)
        if level == 2:
            if self._section_open:
                self._lines.append('</div>')
            self._lines.append(f'<div class="section"><h2 class="section-title">{formatted}</h2>')
            self._section_open = True
        elif level == 3:
            self._lines.append(f'<h3 class="subsection-title">{formatted}</h3>')
        elif level == 4:
            self._lines.append(f'<h4 class="subsubsection-title">{formatted}</h4>')
        else:
            tag = f'h{min(level, 6)}'
            self._lines.append(f'<{tag}>{formatted}</{tag}>')

    def _render_list_item(self, list_type: str, text: str) -> None:
        self._flush_paragraph()
        if self._list_type != list_type:
            self._close_list()
            self._lines.append(f'<{list_type}>')
            self._list_type = list_type
        self._lines.append(f'<li>{format_inline(text)}</li>')

    def _render_table(self, source_lines: Sequence[str], start: int) -> int:
        self._flush_paragraph()
        self._close_list()
        header = parse_table_row(source_lines[start])
        rows = []
        index = start + 2
        while index < len(source_lines) and is_table_row(source_lines[index]):
            rows.append(parse_table_row(source_lines[index]))
            index += 1

        self._lines.append('<table class="data-table">')
        self._lines.append('<thead><tr>')
        for cell in header:
            self._lines.append(f'<th>{format_inline(cell)}</th>')
        self._lines.append('</tr></thead>')
        self._lines.append('<tbody>')
        for row in rows:
            self._lines.append('<tr>')
            for cell in row:
                self._lines.append(f'<td>{format_inline(cell)}</td>')
            self._lines.append('</tr>')
        self._lines.append('</tbody></table>')
        return index

    def _is_table_start(self, source_lines: Sequence[str], index: int) -> bool:
        if index + 1 >= len(source_lines):
            return False
        return is_table_row(source_lines[index]) and is_table_separator(source_lines[index + 1])

    def _flush_paragraph(self) -> None:
        if not self._paragraph:
            return
        paragraph = ' '.join(self._paragraph).strip()
        if paragraph:
            self._lines.append(f'<p>{format_inline(paragraph)}</p>')
        self._paragraph = []

    def _close_list(self) -> None:
        if self._list_type:
            self._lines.append(f'</{self._list_type}>')
            self._list_type = None


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 2


def is_table_separator(line: str) -> bool:
    if not is_table_row(line):
        return False
    cells = parse_table_row(line)
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell.strip()) for cell in cells)


def parse_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def format_inline(text: str) -> str:
    """Escape text and then apply safe inline Markdown formatting."""
    escaped = html.escape(text, quote=False)
    escaped = re.sub(
        r'\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+|file:[^)\s]+)\)',
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}" target="_blank">'
            f'{match.group(1)}</a>'
        ),
        escaped,
    )
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', escaped)
    return escaped


def convert_bibliography_section(markdown: str) -> str:
    """Convert an optional bibliography block to HTML."""
    if not markdown.strip():
        return ''

    entries = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r'^\[(\d+)\]\s*(.+?)\s+-\s*(https?://\S+)$', line)
        if match:
            number, title, url = match.groups()
            entries.append(
                '<div class="bib-entry">'
                f'<span class="bib-number">[{html.escape(number)}]</span> '
                f'<a href="{html.escape(url, quote=True)}" target="_blank">{format_inline(title)}</a>'
                '</div>'
            )
        else:
            entries.append(f'<div class="bib-entry">{format_inline(line)}</div>')

    return (
        '<div class="bibliography">\n'
        '    <div class="section-title">Bibliography</div>\n'
        '    <div class="bibliography-content">\n'
        + '\n'.join(f'        {entry}' for entry in entries)
        + '\n    </div>\n'
        '</div>'
    )


def is_wsl() -> bool:
    """Return True when running inside WSL."""
    release = Path('/proc/sys/kernel/osrelease')
    if not release.exists():
        return False
    text = release.read_text(encoding='utf-8', errors='ignore').lower()
    return 'microsoft' in text or 'wsl' in text


def wsl_to_windows_path(path: Path) -> str:
    """Convert a WSL path to a Windows path when wslpath is available."""
    if not is_wsl() or shutil.which('wslpath') is None:
        return str(path)
    return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()


def windows_file_url(path: Path) -> str:
    """Build a file URL suitable for Windows Chrome from a WSL path."""
    windows_path = wsl_to_windows_path(path)
    normalized = windows_path.replace('\\', '/')
    if normalized.startswith('//'):
        return 'file:' + normalized
    if re.match(r'^[A-Za-z]:/', normalized):
        return 'file:///' + normalized
    return path.resolve().as_uri()


def open_host_path(path: Path) -> None:
    """Open an output artifact from WSL/Linux/macOS without assuming macOS open."""
    opener = shutil.which('xdg-open') or shutil.which('open')
    if opener:
        result = subprocess.run([opener, str(path)], check=False)
        if result.returncode == 0:
            return
    if is_wsl() and shutil.which('explorer.exe'):
        subprocess.run(['explorer.exe', wsl_to_windows_path(path)], check=False)


def find_chrome(chrome_bin: Optional[str] = None) -> Optional[str]:
    """Find Chrome/Chromium for headless PDF rendering."""
    candidates = []
    if chrome_bin:
        candidates.append(chrome_bin)
    candidates.extend(
        [
            os.environ.get('CHROME_BIN', ''),
            '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
            '/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe',
            shutil.which('google-chrome') or '',
            shutil.which('chromium') or '',
            shutil.which('chromium-browser') or '',
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def render_pdf_with_chrome(html_path: Path, pdf_path: Path, chrome_bin: Optional[str] = None) -> None:
    """Render PDF through Chrome headless."""
    chrome = find_chrome(chrome_bin)
    if not chrome:
        raise RuntimeError('Chrome/Chromium not found; install Chrome or use --pdf-engine weasyprint')

    pdf_target = wsl_to_windows_path(pdf_path) if chrome.endswith('.exe') else str(pdf_path)
    source = windows_file_url(html_path) if chrome.endswith('.exe') else html_path.resolve().as_uri()
    subprocess.run(
        [
            chrome,
            '--headless',
            '--disable-gpu',
            '--no-sandbox',
            f'--print-to-pdf={pdf_target}',
            source,
        ],
        check=True,
    )


def render_pdf_with_weasyprint(html_path: Path, pdf_path: Path) -> None:
    """Render PDF through WeasyPrint when installed."""
    weasyprint = shutil.which('weasyprint')
    if not weasyprint:
        raise RuntimeError('weasyprint not found')
    subprocess.run([weasyprint, str(html_path), str(pdf_path)], check=True)


def resolve_source_ledger(args: argparse.Namespace) -> Optional[Path]:
    """Resolve the source ledger from explicit path or run directory."""
    if args.source_ledger:
        return args.source_ledger
    if args.run_dir:
        return args.run_dir / 'sources.jsonl'
    return None


def write_html(markdown_path: Path, output_path: Path, args: argparse.Namespace) -> str:
    """Read Markdown and write final HTML."""
    markdown_text = markdown_path.read_text(encoding='utf-8')
    html_text = render_report_html(
        markdown_text,
        template_path=args.template,
        title=args.title,
        report_date=args.date,
        source_count=args.source_count,
        source_ledger=resolve_source_ledger(args),
        metrics=args.metric or (),
        fallback_title=markdown_path.stem.replace('_', ' ').replace('-', ' ').title(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding='utf-8')
    return html_text


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Render a deep-research Markdown report to final HTML')
    parser.add_argument('markdown_path', type=Path, help='Markdown report path')
    parser.add_argument('--out', type=Path, help='Output HTML path; defaults to markdown_path with .html suffix')
    parser.add_argument('--template', type=Path, default=DEFAULT_TEMPLATE, help='HTML template path')
    parser.add_argument('--title', help='Override report title')
    parser.add_argument('--date', help='Override report date, YYYY-MM-DD')
    parser.add_argument('--source-count', type=int, help='Override source count shown in header')
    parser.add_argument('--run-dir', type=Path, help='Run folder containing sources.jsonl')
    parser.add_argument('--source-ledger', type=Path, help='sources.jsonl path for source count')
    parser.add_argument('--metric', action='append', help='Dashboard metric as LABEL=VALUE; may be repeated')
    parser.add_argument('--open', action='store_true', help='Open HTML using explorer.exe on WSL or xdg-open/open')
    parser.add_argument('--pdf-out', type=Path, help='Optional PDF output path')
    parser.add_argument('--pdf-engine', choices=('chrome', 'weasyprint'), default='chrome')
    parser.add_argument('--chrome-bin', help='Chrome/Chromium executable for --pdf-engine chrome')
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    markdown_path = args.markdown_path
    if not markdown_path.exists():
        print(f'Error: Markdown file not found: {markdown_path}', file=sys.stderr)
        return 1
    if not args.template.exists():
        print(f'Error: HTML template not found: {args.template}', file=sys.stderr)
        return 1

    output_path = args.out or markdown_path.with_suffix('.html')
    write_html(markdown_path, output_path, args)
    print(f'Wrote HTML: {output_path}')

    if args.pdf_out:
        if args.pdf_engine == 'chrome':
            render_pdf_with_chrome(output_path, args.pdf_out, args.chrome_bin)
        else:
            render_pdf_with_weasyprint(output_path, args.pdf_out)
        print(f'Wrote PDF: {args.pdf_out}')

    if args.open:
        open_host_path(output_path)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
