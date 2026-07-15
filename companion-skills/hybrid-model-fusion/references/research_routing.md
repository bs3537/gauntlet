# Standard Research Routing

Apply this contract to the independent panel reports and final judge verification.

1. **First pass — native discovery.** Use the runtime's native web search and fetch capability—Codex native web, Claude WebSearch/WebFetch, or Antigravity/Google grounding—for broad discovery, current verification, and primary-document discovery. Treat this as a wide, Search-as-Code-style query pass, but do not invoke the separate `search-as-code` skill unless the user requested deep research or the active workflow explicitly requires it.
2. **Second pass — Perplexity gaps.** Use the Perplexity Search MCP available in that runtime for rapid orientation, alternate query formulations, source-targeted follow-ups, competing narratives, and material gaps the native pass may have missed. If Perplexity is unavailable, continue native-only and disclose that limitation; never fail the lane solely because the second pass is unavailable.
3. **Primary-source verification.** Search snippets and synthesized answers are discovery context only. Open and verify every load-bearing claim in the underlying primary or authoritative document—such as an FDA or other regulator page, SEC or exchange filing, trial registry, journal paper, conference material, official company document, or first-party technical documentation.
4. **Conflict handling.** If native search and Perplexity disagree on a material claim, preserve the discrepancy, verify against the highest-authority source, and do not silently merge the claims.

Use structured tools such as FMP, Scite, BioMCP, and registries where relevant, but do not let them replace the underlying primary document for a material conclusion.
