#!/usr/bin/env python3
"""
md_to_html.py — self-contained Markdown -> styled HTML converter for the Model Fusion skill.

No third-party dependencies (python-markdown is NOT installed on this machine). Produces a
complete, print-friendly HTML document with embedded CSS in a single CLI call.

Usage:
    md_to_html.py <input.md> <output.html> [title]

Handles: ATX headings, bold/italic/inline-code, links, ordered & unordered lists (incl. one
level of nesting), fenced code blocks, blockquotes, GFM pipe tables, horizontal rules, and
paragraphs.

Section-aware styling for the fusion report: tables under a "...Agrees / ...Disagrees /
Unique..." heading get classes matrix/disagree/unique; lists under "Recommendations /
Next steps" or "Follow-up" headings get classes recommendations/followup; and table cells
whose entire content is a confidence token (High/Med/Low) or a presence symbol (✓ / –) render
as styled badges.
"""
import sys
import re
import html
from pathlib import Path


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', lambda m: '<code>' + m.group(1) + '</code>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![\*\w])\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', text)
    return text


def _badge(cell: str) -> str:
    """Whole-cell-only badge/symbol styling for table cells (applied after inline formatting).
    Narrow exact-match so prose cells (e.g. 'High confidence that...') are never touched."""
    s = cell.strip()
    if s == 'High':
        return '<span class="badge badge-high">High</span>'
    if s in ('Med', 'Medium'):
        return '<span class="badge badge-med">Med</span>'
    if s == 'Low':
        return '<span class="badge badge-low">Low</span>'
    if s in ('✓', '✔'):                       # ✓ ✔
        return '<span class="cell-check">✓</span>'
    if s in ('–', '—', '-', '✗'):        # – — - ✗
        return '<span class="cell-cross">–</span>'
    return cell


_STOP = re.compile(r'^(#{1,6}\s|\s*([-*+]|\d+\.)\s|\s*>|```|\s*\|)')
_HR = re.compile(r'^\s*([-*_])\s*(\1\s*){2,}$')
_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$')


def convert(md: str) -> str:
    lines = md.split('\n')
    out, i, n = [], 0, len(lines)
    list_stack = []  # (tag, indent)
    last_h2 = ''     # most recent h2 text (lowercased) — drives section-aware classes

    def close_lists(to_indent: int = -1):
        while list_stack and list_stack[-1][1] > to_indent:
            out.append('</%s>' % list_stack.pop()[0])

    def cells(row: str):
        row = row.strip()
        if row.startswith('|'):
            row = row[1:]
        if row.endswith('|'):
            row = row[:-1]
        return [c.strip() for c in row.split('|')]

    while i < n:
        line = lines[i]

        if line.lstrip().startswith('```'):
            close_lists()
            i += 1
            code = []
            while i < n and not lines[i].lstrip().startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            out.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>')
            continue

        if _HR.match(line):
            close_lists()
            out.append('<hr>')
            i += 1
            continue

        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            close_lists()
            lvl = len(m.group(1))
            htext = m.group(2).strip()
            if lvl == 2:
                last_h2 = htext.lower()
            out.append('<h%d>%s</h%d>' % (lvl, _inline(htext), lvl))
            i += 1
            continue

        if '|' in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]):
            close_lists()
            header = cells(line)
            tcls = ''
            if 'disagree' in last_h2:                       # check disagree before agree ("disagree" contains "agree")
                tcls = ' class="disagree"'
            elif 'agree' in last_h2:
                tcls = ' class="matrix"'
            elif 'unique' in last_h2 or 'discoveries' in last_h2:
                tcls = ' class="unique"'
            out.append('<table%s><thead><tr>' % tcls + ''.join('<th>%s</th>' % _inline(c) for c in header) + '</tr></thead><tbody>')
            i += 2
            while i < n and '|' in lines[i] and lines[i].strip():
                out.append('<tr>' + ''.join('<td>%s</td>' % _badge(_inline(c)) for c in cells(lines[i])) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue

        if re.match(r'^\s*>\s?', line):
            close_lists()
            quote = []
            while i < n and re.match(r'^\s*>\s?', lines[i]):
                quote.append(re.sub(r'^\s*>\s?', '', lines[i]))
                i += 1
            out.append('<blockquote>' + _inline(' '.join(quote)) + '</blockquote>')
            continue

        m = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', line)
        if m:
            indent = len(m.group(1))
            tag = 'ol' if re.match(r'\d+\.', m.group(2)) else 'ul'
            lcls = ''
            if 'recommend' in last_h2 or 'next step' in last_h2:
                lcls = ' class="recommendations"'
            elif 'follow' in last_h2:
                lcls = ' class="followup"'
            if not list_stack or indent > list_stack[-1][1]:
                list_stack.append((tag, indent))
                out.append('<%s%s>' % (tag, lcls))
            else:
                close_lists(indent)
                if not list_stack or list_stack[-1][1] < indent:
                    list_stack.append((tag, indent))
                    out.append('<%s%s>' % (tag, lcls))
            out.append('<li>%s</li>' % _inline(m.group(3).strip()))
            i += 1
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not _STOP.match(lines[i]) and not _HR.match(lines[i]):
            para.append(lines[i])
            i += 1
        out.append('<p>' + _inline(' '.join(s.strip() for s in para)) + '</p>')

    close_lists()
    return '\n'.join(out)


CSS = """
:root{--ink:#1a1f29;--muted:#5b6573;--rule:#e3e7ee;--accent:#1f5fae;--bg:#fff;--codebg:#f5f7fa}
*{box-sizing:border-box}
body{margin:0;background:#eef1f5;color:var(--ink);font:16px/1.65 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main.report{max-width:880px;margin:32px auto;background:var(--bg);padding:56px 64px;border-radius:6px;box-shadow:0 1px 4px rgba(20,30,50,.08)}
.report-head{border-bottom:3px solid var(--accent);margin-bottom:28px;padding-bottom:14px}
.doc-title{font-size:26px;line-height:1.25;margin:0;color:var(--ink)}
h1,h2,h3,h4{line-height:1.25;color:var(--ink);font-weight:650}
h1{font-size:24px;margin:34px 0 12px;border-bottom:1px solid var(--rule);padding-bottom:6px}
h2{font-size:20px;margin:30px 0 10px}
h3{font-size:17px;margin:24px 0 8px}
h4{font-size:15px;margin:20px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
p{margin:0 0 14px}
ul,ol{margin:0 0 14px;padding-left:26px}
li{margin:4px 0}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code{background:var(--codebg);border:1px solid var(--rule);border-radius:4px;padding:1px 5px;font:13.5px/1.5 SFMono-Regular,Consolas,Menlo,monospace}
pre{background:var(--codebg);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;overflow:auto;margin:0 0 16px}
pre code{background:none;border:0;padding:0;font-size:13px}
blockquote{margin:0 0 16px;padding:6px 16px;border-left:4px solid var(--accent);background:#f7f9fc;color:var(--muted)}
table{border-collapse:collapse;width:100%;margin:0 0 18px;font-size:14.5px}
th,td{border:1px solid var(--rule);padding:8px 11px;text-align:left;vertical-align:top}
th{background:#f0f4f9;font-weight:650}
tr:nth-child(even) td{background:#fafbfd}
hr{border:0;border-top:1px solid var(--rule);margin:26px 0}
/* ── confidence badges ─────────────────────────────────────── */
.badge{display:inline-block;font-size:11.5px;font-weight:700;letter-spacing:.03em;padding:2px 8px;border-radius:11px;white-space:nowrap}
.badge-high{background:#d6f0db;color:#14672c;border:1px solid #b6e3c0}
.badge-med{background:#fdf0c8;color:#7a5a06;border:1px solid #f4e2a3}
.badge-low{background:#f9d9dc;color:#7a1f29;border:1px solid #f1bcc2}
/* ── check / cross matrix cells ─────────────────────────────── */
.cell-check{color:#1a7a3e;font-size:16px;font-weight:700}
.cell-cross{color:#aab2bd;font-size:16px}
/* ── agreement matrix table ─────────────────────────────────── */
table.matrix th,table.matrix td{text-align:center}
table.matrix th:first-child,table.matrix td:first-child{text-align:left;min-width:210px}
table.matrix th:last-child,table.matrix td:last-child{text-align:left;font-size:13px;color:var(--muted)}
/* ── disagreement table ─────────────────────────────────────── */
table.disagree td:first-child{font-weight:650;min-width:120px}
table.disagree td:last-child{font-style:italic;color:#41454f;background:#f7f9fc}
/* ── unique-insights table ──────────────────────────────────── */
table.unique td:first-child{font-weight:700;white-space:nowrap;color:var(--accent)}
/* ── recommendations (numbered cards) ───────────────────────── */
ol.recommendations{counter-reset:rec;list-style:none;padding-left:0}
ol.recommendations>li{position:relative;padding:11px 14px 11px 46px;margin:0 0 10px;background:#f7f9fc;border:1px solid var(--rule);border-left:3px solid var(--accent);border-radius:5px}
ol.recommendations>li::before{content:counter(rec);counter-increment:rec;position:absolute;left:14px;top:11px;font-weight:700;color:var(--accent)}
/* ── follow-up question pills ───────────────────────────────── */
ul.followup{list-style:none;padding-left:0}
ul.followup>li{padding:8px 14px;margin:0 0 7px;background:#f0f4f9;border-left:3px solid #8eafd4;border-radius:5px;font-size:14.5px}
@media print{body{background:#fff}main.report{box-shadow:none;margin:0;max-width:none;padding:0}}
"""


def main():
    if len(sys.argv) < 3:
        print("Usage: md_to_html.py <input.md> <output.html> [title]")
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else src.stem
    if not src.exists():
        print("Error: %s not found" % src)
        sys.exit(1)
    body = convert(src.read_text(encoding='utf-8'))
    doc = (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>%s</title>\n<style>%s</style></head>\n'
        '<body><main class="report">\n'
        '<header class="report-head"><div class="doc-title">%s</div></header>\n'
        '%s\n</main></body></html>\n'
    ) % (html.escape(title), CSS, html.escape(title), body)
    dst.write_text(doc, encoding='utf-8')
    print("[md_to_html] %s -> %s (%d bytes)" % (src, dst, len(doc)))


if __name__ == '__main__':
    main()
