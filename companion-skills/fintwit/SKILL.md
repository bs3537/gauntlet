---
name: fintwit
description: >-
  Pull live X / FinTwit social sentiment for a stock ticker using xAI Grok (grok-4.3) with the
  x_search tool. Trigger on "/fintwit", "FinTwit", "X sentiment", "Twitter sentiment", "what is X
  saying about <ticker>", or as the mandatory social-sentiment step for ANY stock/ticker research
  query (simple or deep). Returns a labeled Markdown report (Sentiment verdict + 0-100 score, bull
  themes, bear themes, top posts, catalysts, caveats) plus an optional JSON sidecar. Output is SOCIAL
  SENTIMENT — Tier 4: never anchor material claims to it and never let it override structured data or
  primary sources. Cost ~$0.05-0.15 per ticker (grok-4.3 $1.25/$2.50 per M tokens + x_search $5/1000
  calls). Not for general web research (use Perplexity) or for fundamentals (use FMP / valuation).
---

# FinTwit / X Sentiment (xAI Grok + x_search)

Automates "what are experienced investors saying about this stock on X" — replacing the manual scroll
with one Grok `x_search` call that reads X in real time and returns a synthesized, cited summary.

## When to run

- Any time a query concerns a specific **stock / ticker** — a quick "what's the read on $NVDA?" or a
  full deep-research / valuation / fusion run. This is the mandatory social-sentiment step referenced
  by `CLAUDE.md`, `deep-research`, `model-fusion`, and `hybrid-model-fusion`.
- Skip when: no specific ticker is identifiable; `SKIP_FINTWIT=1` is set; or model-fusion fast mode
  (`FUSION_FAST=1`) — the wrapper auto-exits in those cases.

## Usage

Standalone (writes to `~/Documents/FinTwit_<TICKER>_<ts>/` and echoes to stdout):
```bash
bash ~/.claude/skills/fintwit/scripts/fintwit.sh NVDA
```

Direct engine call (full control):
```bash
python3 ~/.claude/skills/fintwit/scripts/fintwit_engine.py --ticker NVDA --days 7 --out <dir> --json
```

Into a fusion run folder (the fusion skills do this in their Step 0.5):
```bash
bash ~/.claude/skills/fintwit/scripts/fintwit.sh "$RUN_DIR" NVDA   # writes $RUN_DIR/fintwit_context.md
```

Key flags: `--days N` (lookback, default 7), `--handles <file>` (restrict to curated accounts —
see `references/handles.txt`), `--no-cache` (force fresh; same-day results are cached per ticker),
`--dry-run` (print the request body without calling), `--model` (default `grok-4.3`).

## Output

`fintwit_context.md` (primary) + `fintwit_context.json` (structured: sentiment, score, bull/bear
themes, catalysts, top_handles, bot_noise_warning, post_count, citations). The report is headed with a
**[SOCIAL SENTIMENT — Tier 4]** banner. Sections: Sentiment Verdict, Bull Themes, Bear Themes, Top
Posts (`@handle — gist (link) — BULL/BEAR/NEUTRAL`), Catalysts, Caveats, Cited X Posts.

## How to use the output

Present it as a clearly-labeled **FinTwit / X Sentiment** section. It is Tier-4 social signal: useful
for gauging narrative, positioning, and catalysts the crowd is watching — **never** a basis for a
material factual claim, and it never overrides FMP / filings / primary sources. Posts flagged
`[PROMO/BOT?]` and the standard bot/selection-bias caveat must be respected. `x_search` surfaces what
Grok deems relevant, not the full firehose, so treat coverage as indicative, not exhaustive.

## Setup

Requires `~/.claude/secrets/xai.env` with `XAI_API_KEY=...` (chmod 600). Egress is routed through
Windows `curl.exe` (WSL → external HTTPS), mirroring the Perplexity adapter.
