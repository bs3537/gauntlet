# HTML Generation: McKinsey Style Report

## Design Principles

- Sharp corners (NO border-radius)
- Muted corporate colors (navy #003d5c, gray #f8f9fa)
- Ultra-compact layout
- Info-first structure
- 14px base font, compact spacing
- No decorative gradients or colors
- NO EMOJIS in final HTML

---

## Generation Steps

### Step 0: Confirm Delivery Gate Passed

Before converting or opening a deliverable, run the strict report package gate:

```bash
cd ~/.claude/skills/deep-research
python scripts/delivery_gate.py --dir [run_folder] --report [markdown_report_path] --strict --semantic --require-section-citation-audits
```

Proceed to HTML/PDF only when the gate passes and `[run_folder]/audit_manifest.json` has `status: pass`.

### Step 1: Read McKinsey Template
Load template from: `./templates/mckinsey_report_template.html`

### Step 2: Extract Key Metrics
Extract 3-4 key quantitative findings for dashboard display at top.

### Step 3: Convert MD to Final HTML

Use the packaged Python script. It writes the final template-filled HTML artifact; it does not just print fragments:
```bash
cd ~/.claude/skills/deep-research
python scripts/md_to_html.py [markdown_report_path] \
  --out [html_path] \
  --run-dir [run_folder]
```

Useful options:
- `--source-count [n]` overrides the header source count
- `--source-ledger [run_folder]/sources.jsonl` uses an explicit source ledger
- `--metric "Label=Value"` adds one top-dashboard metric, repeat up to four times
- `--open` opens the HTML after writing it using the host-safe open flow
- `--pdf-out [pdf_path]` writes a PDF after HTML generation

**Script handles all conversion:**
- Escaping of untrusted/report text before insertion into HTML
- Headers: `##` -> `<div class="section"><h2 class="section-title">`
- Headers: `###` -> `<h3 class="subsection-title">`
- Lists: Markdown bullets and numbered lists -> `<ul>/<ol><li>`
- Tables: Markdown tables -> `<table>` with thead/tbody
- Paragraphs: Text wrapped in `<p>` tags
- Bold/italic: `**text**` -> `<strong>`, `*text*` -> `<em>`
- Fenced code blocks: triple-backtick blocks -> `<pre><code>` with escaped contents
- Citations: [N] preserved for tooltip conversion
- Optional bibliography: keep empty by default; populate only when the user explicitly requested a bibliography/source-list section such as `## Bibliography`

### Step 4: Add Citation Tooltips (Optional)

Attribution Gradients - wrap each [N] citation:
```html
<span class="citation">[N]
  <span class="citation-tooltip">
    <div class="tooltip-title">[Source Title]</div>
    <div class="tooltip-source">[Author/Publisher]</div>
    <div class="tooltip-claim">
      <div class="tooltip-claim-label">Supports Claim:</div>
      [Extract sentence with this citation]
    </div>
  </span>
</span>
```
NOTE: This step is optional for speed. Basic [N] citations are sufficient.

### Step 5: Replace Template Placeholders

| Placeholder | Content |
|-------------|---------|
| {{TITLE}} | Report title (from first ## heading) |
| {{DATE}} | Generation date (YYYY-MM-DD) |
| {{SOURCE_COUNT}} | Number of unique sources |
| {{METRICS_DASHBOARD}} | Metrics HTML from step 2 |
| {{CONTENT}} | HTML from Part A |
| {{BIBLIOGRAPHY}} | Empty by default; complete bibliography-section HTML only from an explicitly requested bibliography/source-list section |

### Step 6: Verify HTML

```bash
python scripts/verify_html.py --html [html_path] --md [md_path]
```
- Pass: Proceed to open
- Fail: Fix errors and re-run

### Step 7: Open in Browser

In WSL/Linux, use Linux openers first and fall back to Windows Explorer when needed:
```bash
xdg-open [html_path]
explorer.exe "$(wslpath -w [html_path])"
```

The converter can do this automatically:
```bash
python scripts/md_to_html.py [markdown_report_path] --out [html_path] --run-dir [run_folder] --open
```

---

## PDF Generation

**Option A: Windows Chrome Headless from WSL (Preferred on this host)**

Use Windows Chrome with `wslpath` so paths resolve correctly from WSL:

```bash
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --print-to-pdf="$(wslpath -w [pdf_path])" \
  "$(wslpath -w [html_path])"
```

Or use the converter:
```bash
python scripts/md_to_html.py [markdown_report_path] \
  --out [html_path] \
  --run-dir [run_folder] \
  --pdf-out [pdf_path]
```

**Option B: WeasyPrint Direct (Optional when installed)**

1. Create print-optimized HTML following `./reference/weasyprint_guidelines.md`
2. Critical CSS:
   - `page-break-inside: avoid` on tables, boxes
   - `page-break-after: avoid` on headings
   - `orphans: 3; widows: 3` on paragraphs
   - Use `display: table` not Flexbox/Grid
   - Font sizes in pt (10pt body, 8pt citations)
3. Generate: `weasyprint [html_path] [pdf_path]`
4. Open: `xdg-open [pdf_path]` or `explorer.exe "$(wslpath -w [pdf_path])"`

**Option C: generating-pdf Skill**

Use Task tool with general-purpose agent, invoke generating-pdf skill.
