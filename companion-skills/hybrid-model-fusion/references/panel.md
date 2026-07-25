# Hybrid Panel Rules

Hybrid Model Fusion starts with independent reports. The same user task goes to Opus 5, Grok 4.5, Gemini 3.5 Flash, and GPT-5.6 Sol without cross-contamination.

## No Lenses Or Personas

Do not assign panelists roles such as skeptic, bull case, bear case, optimizer, or first-principles analyst. That creates artificial diversity. The value comes from independent model reasoning on the same task.

## Independence Boundary

Panelists must not see each other's work before all primary reports are saved.

Allowed sequence:

```text
all primary reports complete -> anonymize reports -> blind peer review -> aggregate -> final judge
```

Disallowed sequence:

```text
model A sees model B before model A writes its primary report
```

## Panel Composition

- `Opus 5`: Claude Code CLI at max effort.
- `Grok 4.5`: Grok Build CLI (`grok`) at `high` effort.
- `Gemini 3.5 Flash`: Antigravity `agy` with the High model setting.
- `GPT-5.6 Sol`: Codex CLI at `max` effort (one `gpt-5.5`/`xhigh` structured-safety-fallback retry).

The `grok4.5` slug runs the Grok Build CLI panelist (`grok-4.5` at `high`, no safety fallback); the `gpt5.6sol` slug runs the Codex panelist (`gpt-5.6-sol` at `max`, one `gpt-5.5`/`xhigh` structured-safety retry).

The final judge is a fresh Opus 5 max run via Claude Code by default (a `gpt-*`/`codex` `FUSION_JUDGE_MODEL` override runs it via Codex instead). Opus 5 also sits on the panel, so its final judge run stays separate and happens only after the panel reports and peer reviews are complete.

## Primary Report Prompt

Give each panelist:

- the user's task verbatim,
- a short instruction to produce a complete Markdown report,
- permission to use available search/tools if appropriate,
- no summaries of other model outputs,
- no model-specific framing that nudges the conclusion.

Append the identical `research_routing.md` contract to all four panel prompts:

- **First pass:** use that runtime's native web search/fetch for a wide, Search-as-Code-style discovery and current-verification pass.
- **Second pass:** use Perplexity Search MCP for alternate queries, source-targeted follow-ups, competing narratives, and material gaps. If unavailable, continue native-only and disclose it.
- Open and verify load-bearing claims in the underlying primary documents; preserve provider discrepancies instead of silently merging them.
