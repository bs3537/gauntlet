#!/usr/bin/env python3
"""FinTwit engine — pull live X / FinTwit sentiment on a stock ticker via xAI Grok + x_search.

Calls the xAI Responses API (POST https://api.x.ai/v1/responses) with model grok-4.3 and the
server-side `x_search` tool. Grok searches X in real time and returns a synthesized answer plus a
flat `citations[]` array of x.com post URLs (the API does NOT return structured post objects, so we
instruct Grok to format per-post lines and a trailing ```json fence we parse best-effort).

Egress: external HTTPS is routed through Windows curl.exe (direct WSL networking to external HTTPS is
unreliable in this environment), with the API key passed via curl's stdin --config channel so it never
appears in the process argument list. This mirrors ~/.claude/scripts/perplexity-mcp.py.

Output: writes <out>/fintwit_context.md (+ fintwit_context.json) and echoes the markdown to stdout.
This is SOCIAL SENTIMENT — Tier 4. It must never anchor a material claim or override structured-data
(FMP) / primary sources.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

XAI_RESPONSES_URL = os.environ.get("XAI_RESPONSES_URL", "https://api.x.ai/v1/responses")
# Resolve secret + cache RELATIVE to this tree so the same engine works unchanged in
# ~/.claude, ~/.codex, and ~/.gemini. Layout: <tree>/skills/fintwit/scripts/fintwit_engine.py
# -> parents[3] = tree root (.claude/.codex/.gemini); cache lives inside the skill dir.
_TREE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SECRET_FILE = _TREE_ROOT / "secrets" / "xai.env"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
DEFAULT_WINDOWS_CURL = os.environ.get("XAI_WINDOWS_CURL", "/mnt/c/Windows/System32/curl.exe")
DEFAULT_MODEL = os.environ.get("XAI_MODEL", "grok-4.3")
DEFAULT_DAYS = 7
DEFAULT_TIMEOUT = float(os.environ.get("XAI_HTTP_TIMEOUT", "120"))
MAX_HANDLES = 20
RETRYABLE = ("429", "500", "502", "503", "504", "timed out", "timeout", "Connection")


# ── secrets / egress (mirrors perplexity-mcp.py) ──────────────────────────────
def cfg_escape(value: str) -> str:
    """Escape a value for inclusion inside a double-quoted curl --config field."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:  # already-set env var wins (per-session override)
            os.environ[key] = value


def get_api_key() -> str:
    if not os.environ.get("XAI_API_KEY"):
        env_file = Path(os.environ.get("XAI_ENV_FILE") or DEFAULT_SECRET_FILE)
        load_env_file(env_file)
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        env_file = Path(os.environ.get("XAI_ENV_FILE") or DEFAULT_SECRET_FILE)
        raise RuntimeError(f"XAI_API_KEY not set. Define it in {env_file} (XAI_API_KEY=...).")
    return api_key


def _curl_once(body: dict, api_key: str, timeout: float) -> dict:
    if not os.path.exists(DEFAULT_WINDOWS_CURL):
        raise RuntimeError(f"Windows curl not found at {DEFAULT_WINDOWS_CURL}.")
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=True)
    curl_config = (
        f'url = "{cfg_escape(XAI_RESPONSES_URL)}"\n'
        'request = "POST"\n'
        'header = "Content-Type: application/json"\n'
        'header = "Accept: application/json"\n'
        f'header = "Authorization: Bearer {cfg_escape(api_key)}"\n'
        'header = "User-Agent: claude-fintwit-engine/1.0"\n'
        f'data-binary = "{cfg_escape(payload)}"\n'
    )
    completed = subprocess.run(
        [
            DEFAULT_WINDOWS_CURL,
            "--silent", "--show-error", "--fail-with-body", "--http1.1",
            "--connect-timeout", "15",
            "--max-time", str(max(20.0, timeout)),
            "--config", "-",
        ],
        input=curl_config, text=True, capture_output=True,
        timeout=max(25.0, timeout + 8.0), check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()[:600] or f"exit code {completed.returncode}"
        raise RuntimeError(f"xAI request failed: {detail}")
    return json.loads(completed.stdout)


def call_grok(body: dict, api_key: str, timeout: float, retries: int = 2) -> dict:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _curl_once(body, api_key, timeout)
        except Exception as exc:  # noqa: BLE001
            last = exc
            msg = str(exc)
            if attempt < retries and any(tok in msg for tok in RETRYABLE):
                time.sleep(min(8.0, 2.0 ** attempt))
                continue
            raise
    raise last  # pragma: no cover


# ── request building ──────────────────────────────────────────────────────────
def read_handles(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        return []
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("@")
        if line and not line.startswith("#"):
            out.append(line)
    return out[:MAX_HANDLES]


def build_system_prompt(ticker: str, days: int) -> str:
    dynamic = (
        "You are a senior equity analyst summarizing FinTwit (financial X/Twitter) chatter for a "
        f"professional investor. Use the x_search tool to search X for posts about the stock ticker "
        f"${ticker} over approximately the last {days} days. Run SEVERAL x_search queries to cast a wide "
        f"net — by cashtag (${ticker}), by company name, and by keyword variations (earnings, guidance, "
        "analyst, price target, product, etc.) — and gather as many relevant posts as you can (aim for "
        "20-30) before writing.\n\n"
    )
    static = (
        "Coverage vs. signal: FEATURE credible, experienced voices first (fund managers, professional "
        "analysts, sell-side/buy-side, founders, accounts with a track record), but ALSO capture the "
        "broader conversation and overall mood. Do NOT discard the whole set just because few authors are "
        "verified professionals — instead, label likely promotional / coordinated / bot posts [PROMO/BOT?] "
        "and weight them down. Only report posts you actually found via x_search; link each to its real "
        "x.com URL; never fabricate posts, handles, URLs, or numbers.\n\n"
        "Produce a Markdown report with EXACTLY these H2 sections (use plain `## ` headers, do not bold them):\n"
        "## Sentiment Verdict\nBullish / Bearish / Mixed, a 0-100 bull score (0=max bearish, 50=neutral, "
        "100=max bullish), and a one-sentence rationale. ALWAYS give a verdict if you found any relevant posts.\n"
        "## Bull Themes\nBullets — the strongest bull arguments, attributed to handles where possible.\n"
        "## Bear Themes\nBullets — the strongest bear arguments / risks, attributed.\n"
        "## Top Posts\n15-25 of the most informative or most-engaged posts you found, one per line: "
        "`@handle — one-sentence gist ([link](url)) — BULLISH/BEARISH/NEUTRAL` (append [PROMO/BOT?] if suspect).\n"
        "## Catalysts\nBullets — upcoming events/dates/numbers investors are watching (earnings, product, FDA, macro).\n"
        "## Caveats\nData limits: social sentiment (not primary research), selection/survivorship bias, "
        "bot/promo contamination, and that coverage is only what x_search surfaced (not exhaustive).\n\n"
        'Set sentiment to "insufficient_data" ONLY if x_search genuinely returns almost nothing (fewer than '
        "~3 relevant posts total). Otherwise always summarize what you found, even if the mood is mixed or "
        "low-confidence.\n\n"
        "After the report, output a line containing only `---`, then a fenced ```json block with: "
        '{"ticker": str, "sentiment": "bullish"|"bearish"|"mixed"|"insufficient_data", "score": int 0-100, '
        '"bull_themes": [str], "bear_themes": [str], "catalysts": [str], "top_handles": [str], '
        '"bot_noise_warning": bool, "post_count": int}. Output valid JSON only inside that fence.'
    )
    return dynamic + static


def build_request_body(ticker: str, days: int, model: str, from_date: str, to_date: str,
                       handles: list[str], exclude: list[str], effort: str = "high") -> dict:
    x_tool: dict = {"type": "x_search", "from_date": from_date, "to_date": to_date}
    if handles:
        x_tool["allowed_x_handles"] = handles
    elif exclude:
        x_tool["excluded_x_handles"] = exclude
    body: dict = {
        "model": model,
        "instructions": build_system_prompt(ticker, days),
        "input": [{
            "role": "user",
            "content": (
                f"Summarize what investors on X are saying about ${ticker} over the last {days} days "
                f"({from_date} to {to_date}). Search broadly across several queries, then follow the "
                "required report structure exactly."
            ),
        }],
        "tools": [x_tool],
        "tool_choice": "auto",
        "stream": False,
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    return body


# ── response parsing ───────────────────────────────────────────────────────────
def extract_text(resp: dict) -> str:
    chunks: list[str] = []
    for item in resp.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content", []) or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                chunks.append(block["text"])
    if not chunks:
        # fallback shapes some SDKs expose
        if isinstance(resp.get("output_text"), str):
            chunks.append(resp["output_text"])
    return "\n".join(c for c in chunks if c).strip()


def extract_citations(resp: dict) -> list[str]:
    """Collect cited X-post URLs. The Responses API puts them in
    output[].content[].annotations[] (type 'url_citation'); some shapes also expose a
    top-level citations[]. Dedup, preserve order."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(u):
        if isinstance(u, str) and u and u not in seen:
            seen.add(u)
            urls.append(u)

    for c in resp.get("citations") or []:
        add(c)
    for item in resp.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            for ann in block.get("annotations", []) or []:
                if isinstance(ann, dict) and ann.get("type") == "url_citation":
                    add(ann.get("url"))
    return urls


def parse_json_fence(text: str):
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if not m:
        return None, text
    raw = m.group(1).strip()
    md_without_fence = (text[: m.start()].rstrip().rstrip("-").rstrip()).strip()
    try:
        return json.loads(raw), md_without_fence
    except json.JSONDecodeError:
        print("[fintwit] WARNING: could not parse JSON fence; keeping markdown only.", file=sys.stderr)
        return None, text


# ── output ─────────────────────────────────────────────────────────────────────
def normalize_headers(md: str) -> str:
    """Strip bold the model sometimes wraps around a header line: '**## X**' -> '## X'."""
    return re.sub(r"(?m)^[ \t]*\*\*([ \t]*#{1,6}[ \t]+.+?)\*\*[ \t]*$", r"\1", md)


def build_markdown(ticker: str, days: int, model: str, from_date: str, to_date: str,
                   generated_at: str, report_md: str, citations: list[str]) -> str:
    header = (
        f"# FinTwit / X Sentiment — ${ticker}\n\n"
        "> **[SOCIAL SENTIMENT — Tier 4]** Live X/FinTwit chatter via xAI Grok "
        f"`{model}` + x_search. Window: {from_date} → {to_date} ({days}d). "
        f"Generated {generated_at}. Social signal only — do NOT anchor material claims to this; "
        "it never overrides structured data (FMP) or primary sources.\n\n"
    )
    body = report_md.strip() + "\n"
    if citations:
        body += "\n## Cited X Posts\n" + "\n".join(f"- {u}" for u in citations) + "\n"
    return header + body


def save_outputs(out_dir: Path, markdown: str, json_data, want_json: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "fintwit_context.md"
    md_path.write_text(markdown, encoding="utf-8")
    if want_json and json_data is not None:
        (out_dir / "fintwit_context.json").write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return md_path


# ── main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="FinTwit X-sentiment engine (xAI Grok + x_search).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker", help="Stock ticker, e.g. AAPL (a leading $ is stripped).")
    g.add_argument("--query", help="Free-form query instead of a ticker (no caching).")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"Lookback window in days (default {DEFAULT_DAYS}).")
    ap.add_argument("--handles", help="Path to a file of X handles to restrict to (allowed_x_handles, max 20).")
    ap.add_argument("--exclude", help="Path to a file of X handles to exclude (excluded_x_handles, max 20).")
    ap.add_argument("--out", help="Output directory for fintwit_context.md/.json. If omitted, prints to stdout only.")
    ap.add_argument("--json", dest="want_json", action="store_true", default=True, help="Also write fintwit_context.json (default on).")
    ap.add_argument("--no-json", dest="want_json", action="store_false", help="Do not write the JSON sidecar.")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"xAI model id (default {DEFAULT_MODEL}).")
    ap.add_argument("--effort", default=os.environ.get("XAI_REASONING_EFFORT", "high"),
                    help="Reasoning effort low|medium|high (default high). Empty string disables.")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"HTTP timeout seconds (default {DEFAULT_TIMEOUT}).")
    ap.add_argument("--no-cache", action="store_true", help="Bypass the same-day cache and force a fresh call.")
    ap.add_argument("--dry-run", action="store_true", help="Print the request body and exit (no API call).")
    args = ap.parse_args()

    ticker = (args.ticker or "").lstrip("$").upper().strip()
    days = max(1, args.days)
    handles = read_handles(args.handles)
    exclude = read_handles(args.exclude)

    now = datetime.datetime.now(datetime.timezone.utc)
    to_date = now.strftime("%Y-%m-%d")
    from_date = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M UTC")

    subject = ticker if args.ticker else args.query
    body = build_request_body(subject, days, args.model, from_date, to_date, handles, exclude, args.effort)
    if args.query:
        body["instructions"] = body["instructions"].replace(f"${subject}", subject)

    if args.dry_run:
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0

    out_dir = Path(args.out).expanduser() if args.out else None

    # ── same-day cache (ticker mode only) ──
    cache_key = f"{ticker}_{days}d_{to_date}" if args.ticker and not handles and not exclude else None
    if cache_key and not args.no_cache:
        cached_md = CACHE_DIR / f"{cache_key}.md"
        if cached_md.exists() and cached_md.stat().st_size > 0:
            md_text = cached_md.read_text(encoding="utf-8")
            print(f"[fintwit] cache hit: {cached_md}", file=sys.stderr)
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cached_md, out_dir / "fintwit_context.md")
                cached_json = CACHE_DIR / f"{cache_key}.json"
                if args.want_json and cached_json.exists():
                    shutil.copy2(cached_json, out_dir / "fintwit_context.json")
            print(md_text)
            return 0

    try:
        api_key = get_api_key()
        resp = call_grok(body, api_key, args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[fintwit] ERROR: {exc}", file=sys.stderr)
        return 1

    report_text = extract_text(resp)
    if not report_text:
        print("[fintwit] ERROR: empty response from xAI (no output text).", file=sys.stderr)
        return 1

    citations = extract_citations(resp)
    # The model sometimes inlines post links as ([link](url)) instead of annotating; harvest those too.
    for u in re.findall(r"https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+", report_text):
        if u not in citations:
            citations.append(u)
    json_data, report_md = parse_json_fence(report_text)
    report_md = normalize_headers(report_md)
    markdown = build_markdown(ticker or subject, days, args.model, from_date, to_date, generated_at, report_md, citations)

    if json_data is not None:
        json_data.setdefault("ticker", ticker or subject)
        json_data["from_date"] = from_date
        json_data["to_date"] = to_date
        json_data["generated_at"] = generated_at
        json_data["model"] = args.model
        json_data["citations"] = citations

    # write cache (ticker mode)
    if cache_key:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / f"{cache_key}.md").write_text(markdown, encoding="utf-8")
            if args.want_json and json_data is not None:
                (CACHE_DIR / f"{cache_key}.json").write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"[fintwit] WARNING: cache write failed: {exc}", file=sys.stderr)

    if out_dir:
        md_path = save_outputs(out_dir, markdown, json_data, args.want_json)
        print(f"[fintwit] wrote {md_path}", file=sys.stderr)

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
