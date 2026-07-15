#!/usr/bin/env python3
"""Deep Research phase instruction provider.

This module is not a runtime orchestrator. The authoritative run state lives in
run_manifest.json, plan.json, coverage_map.json, sources.jsonl, evidence.jsonl,
claims.jsonl, display_map.json, and audit_manifest.json.

Legacy Source and ResearchState classes remain as deprecated compatibility
shims for old saved-state files. New runs should use citation_manager.py,
run_trace.py, evidence_store.py, extract_claims.py, and delivery_gate.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


ENGINE_VERSION = '3.0.0'


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def surface_home() -> Path:
    """Return ~/.claude, ~/.codex, or ~/.gemini from the installed script path."""
    return Path(__file__).resolve().parents[3]


def search_as_code_path() -> str:
    return str(surface_home() / 'skills' / 'search-as-code')


def default_cross_model_reviewer() -> str:
    surface = surface_home().name
    if surface == '.claude':
        return 'codex'
    if surface in {'.codex', '.gemini'}:
        return 'claude'
    return 'codex'


class ResearchPhase(Enum):
    """Documented deep-research phases."""

    CLARIFY_OR_BRIEF = 'clarify_or_brief'
    SCOPE = 'scope'
    PLAN = 'plan'
    RETRIEVE = 'retrieve'
    TRIANGULATE = 'triangulate'
    OUTLINE_REFINEMENT = 'outline_refinement'
    SYNTHESIZE = 'synthesize'
    CRITIQUE = 'critique'
    REFINE = 'refine'
    AUDIT = 'audit'
    CROSS_MODEL_CRITIQUE = 'cross_model_critique'
    PACKAGE = 'package'


class ResearchMode(Enum):
    """Research depth modes."""

    QUICK = 'quick'
    STANDARD = 'standard'
    DEEP = 'deep'
    ULTRADEEP = 'ultradeep'


PHASE_METADATA: dict[ResearchPhase, dict[str, str]] = {
    ResearchPhase.CLARIFY_OR_BRIEF: {'number': '0.5', 'name': 'CLARIFY-OR-BRIEF'},
    ResearchPhase.SCOPE: {'number': '1', 'name': 'SCOPE'},
    ResearchPhase.PLAN: {'number': '2', 'name': 'PLAN'},
    ResearchPhase.RETRIEVE: {'number': '3', 'name': 'RETRIEVE'},
    ResearchPhase.TRIANGULATE: {'number': '4', 'name': 'TRIANGULATE'},
    ResearchPhase.OUTLINE_REFINEMENT: {'number': '4.5', 'name': 'OUTLINE REFINEMENT'},
    ResearchPhase.SYNTHESIZE: {'number': '5', 'name': 'SYNTHESIZE'},
    ResearchPhase.CRITIQUE: {'number': '6', 'name': 'CRITIQUE'},
    ResearchPhase.REFINE: {'number': '7', 'name': 'REFINE'},
    ResearchPhase.AUDIT: {'number': '7.5', 'name': 'AUDIT'},
    ResearchPhase.CROSS_MODEL_CRITIQUE: {'number': '7.6', 'name': 'OPTIONAL CROSS-MODEL CRITIQUE'},
    ResearchPhase.PACKAGE: {'number': '8', 'name': 'PACKAGE'},
}


MODE_PHASES: dict[ResearchMode, list[ResearchPhase]] = {
    ResearchMode.QUICK: [
        ResearchPhase.CLARIFY_OR_BRIEF,
        ResearchPhase.SCOPE,
        ResearchPhase.RETRIEVE,
        ResearchPhase.PACKAGE,
    ],
    ResearchMode.STANDARD: [
        ResearchPhase.CLARIFY_OR_BRIEF,
        ResearchPhase.SCOPE,
        ResearchPhase.PLAN,
        ResearchPhase.RETRIEVE,
        ResearchPhase.TRIANGULATE,
        ResearchPhase.OUTLINE_REFINEMENT,
        ResearchPhase.SYNTHESIZE,
        ResearchPhase.PACKAGE,
    ],
    ResearchMode.DEEP: [
        ResearchPhase.CLARIFY_OR_BRIEF,
        ResearchPhase.SCOPE,
        ResearchPhase.PLAN,
        ResearchPhase.RETRIEVE,
        ResearchPhase.TRIANGULATE,
        ResearchPhase.OUTLINE_REFINEMENT,
        ResearchPhase.SYNTHESIZE,
        ResearchPhase.CRITIQUE,
        ResearchPhase.REFINE,
        ResearchPhase.AUDIT,
        ResearchPhase.PACKAGE,
    ],
    ResearchMode.ULTRADEEP: [
        ResearchPhase.CLARIFY_OR_BRIEF,
        ResearchPhase.SCOPE,
        ResearchPhase.PLAN,
        ResearchPhase.RETRIEVE,
        ResearchPhase.TRIANGULATE,
        ResearchPhase.OUTLINE_REFINEMENT,
        ResearchPhase.SYNTHESIZE,
        ResearchPhase.CRITIQUE,
        ResearchPhase.REFINE,
        ResearchPhase.AUDIT,
        ResearchPhase.PACKAGE,
    ],
}


@dataclass
class Source:
    """Deprecated compatibility shim. Use sources.jsonl for new runs."""

    url: str
    title: str
    snippet: str = ''
    retrieved_at: str = ''
    credibility_score: float = 0.0
    source_type: str = 'web'
    verification_status: str = 'unverified'

    def __post_init__(self) -> None:
        warnings.warn(
            'research_engine.Source is deprecated; persist sources with citation_manager.py instead.',
            DeprecationWarning,
            stacklevel=2,
        )

    def to_citation(self, index: int) -> str:
        return f'[{index}] {self.title} - {self.url} (Retrieved: {self.retrieved_at})'


@dataclass
class ResearchState:
    """Deprecated compatibility shim. Use run_manifest.json and ledgers for new runs."""

    query: str
    mode: ResearchMode | str
    phase: ResearchPhase | str
    scope: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] = field(default_factory=dict)
    critique: dict[str, Any] = field(default_factory=dict)
    report: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        warnings.warn(
            'research_engine.ResearchState is deprecated; use run_manifest.json, plan.json, and ledgers.',
            DeprecationWarning,
            stacklevel=2,
        )

    def save(self, filepath: Path) -> None:
        with open(filepath, 'w') as f:
            json.dump(self._serialize(), f, indent=2)
            f.write('\n')

    def _serialize(self) -> dict[str, Any]:
        mode = self.mode.value if isinstance(self.mode, ResearchMode) else str(self.mode)
        phase = self.phase.value if isinstance(self.phase, ResearchPhase) else str(self.phase)
        metadata = dict(self.metadata)
        metadata.setdefault('version', 'legacy-1.0')
        metadata.setdefault('pipeline_version', ENGINE_VERSION)
        metadata.setdefault('deprecated_state_model', True)
        return {
            'query': self.query,
            'mode': mode,
            'phase': phase,
            'scope': self.scope,
            'plan': self.plan,
            'sources': [asdict(s) for s in self.sources],
            'findings': self.findings,
            'synthesis': self.synthesis,
            'critique': self.critique,
            'report': self.report,
            'metadata': metadata,
        }

    @classmethod
    def load(cls, filepath: Path) -> 'ResearchState':
        with open(filepath) as f:
            data = json.load(f)
        return cls(
            query=data['query'],
            mode=ResearchMode(data['mode']),
            phase=ResearchPhase(data['phase']),
            scope=data.get('scope', {}),
            plan=data.get('plan', {}),
            sources=[Source(**s) for s in data.get('sources', [])],
            findings=data.get('findings', []),
            synthesis=data.get('synthesis', {}),
            critique=data.get('critique', {}),
            report=data.get('report', ''),
            metadata=data.get('metadata', {}),
        )


def coerce_mode(value: ResearchMode | str) -> ResearchMode:
    if isinstance(value, ResearchMode):
        return value
    return ResearchMode(str(value))


def coerce_phase(value: ResearchPhase | str) -> ResearchPhase:
    if isinstance(value, ResearchPhase):
        return value
    normalized = str(value).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        '0.5': ResearchPhase.CLARIFY_OR_BRIEF,
        'clarify': ResearchPhase.CLARIFY_OR_BRIEF,
        'clarify_or_brief': ResearchPhase.CLARIFY_OR_BRIEF,
        '4.5': ResearchPhase.OUTLINE_REFINEMENT,
        'outline': ResearchPhase.OUTLINE_REFINEMENT,
        'outline_refinement': ResearchPhase.OUTLINE_REFINEMENT,
        '7.5': ResearchPhase.AUDIT,
        'citation_audit': ResearchPhase.AUDIT,
        'gap_audit': ResearchPhase.AUDIT,
        'audit': ResearchPhase.AUDIT,
        '7.6': ResearchPhase.CROSS_MODEL_CRITIQUE,
        'cross_model': ResearchPhase.CROSS_MODEL_CRITIQUE,
        'cross_model_critique': ResearchPhase.CROSS_MODEL_CRITIQUE,
        '8': ResearchPhase.PACKAGE,
    }
    if normalized in aliases:
        return aliases[normalized]
    for phase in ResearchPhase:
        if normalized in {phase.value, phase.name.lower()}:
            return phase
    raise ValueError(f'unknown phase: {value}')


def phase_label(phase: ResearchPhase) -> str:
    meta = PHASE_METADATA[phase]
    return f"Phase {meta['number']}: {meta['name']}"


def phase_sequence(mode: ResearchMode | str, include_optional: bool = False) -> list[ResearchPhase]:
    phases = list(MODE_PHASES[coerce_mode(mode)])
    if include_optional and ResearchPhase.CROSS_MODEL_CRITIQUE not in phases:
        package_index = phases.index(ResearchPhase.PACKAGE)
        phases.insert(package_index, ResearchPhase.CROSS_MODEL_CRITIQUE)
    return phases


def phase_manifest(mode: ResearchMode | str, include_optional: bool = False) -> list[dict[str, str]]:
    return [
        {
            'number': PHASE_METADATA[phase]['number'],
            'name': PHASE_METADATA[phase]['name'],
            'key': phase.value,
        }
        for phase in phase_sequence(mode, include_optional=include_optional)
    ]


class ResearchEngine:
    """Phase instruction provider, not an autonomous research engine."""

    def __init__(self, mode: ResearchMode | str = ResearchMode.STANDARD):
        self.mode = coerce_mode(mode)

    def initialize_research(self, query: str) -> ResearchState:
        """Deprecated: create a legacy shim only for callers that still import it."""
        return ResearchState(
            query=query,
            mode=self.mode,
            phase=ResearchPhase.CLARIFY_OR_BRIEF,
            metadata={
                'started_at': utc_now(),
                'version': 'legacy-1.0',
                'pipeline_version': ENGINE_VERSION,
                'deprecated_state_model': True,
            },
        )

    def _get_phases_for_mode(self, include_optional: bool = False) -> list[ResearchPhase]:
        return phase_sequence(self.mode, include_optional=include_optional)

    def get_phase_instructions(self, phase: ResearchPhase | str) -> str:
        phase = coerce_phase(phase)
        instructions = {
            ResearchPhase.CLARIFY_OR_BRIEF: f"""
# {phase_label(phase)}

Interactive runs: ask one batched clarification round with at most four material questions.
Headless runs: persist assumptions and write the research brief before retrieval.

Required commands:
- `python scripts/citation_manager.py init-run --out-dir [run_folder] --query "[question]" --mode {self.mode.value}`
- `python scripts/citation_manager.py add-assumption --dir [run_folder] --text "[assumption]" --materiality high --status implicit`
- `python scripts/citation_manager.py write-brief --dir [run_folder] --scope-in "[included]" --scope-out "[excluded]" --open-question "[question]"`
""",
            ResearchPhase.SCOPE: f"""
# {phase_label(phase)}

Define the research boundary, audience, decision criteria, assumptions, and material exclusions.
Keep high-materiality assumptions visible in the introduction or methodology appendix unless replaced by evidence.
""",
            ResearchPhase.PLAN: f"""
# {phase_label(phase)}

Create or edit `plan.json` before retrieval. Represent lanes, query families, expected source minimums,
roles, stop conditions, and role `execution_budget` values. Interactive runs must be approved before
retrieval trace records are allowed.

Required command:
- `python scripts/run_trace.py approve-plan --dir [run_folder] --approved-by user --note "Plan reviewed."`
""",
            ResearchPhase.RETRIEVE: f"""
# {phase_label(phase)}

Use Perplexity as the default web-discovery path. For deep, ultradeep, or source-backed deep-dive work,
load `{search_as_code_path()}` for coordinated discovery packs. Persist source and evidence rows during
retrieval; do not leave evidence only in model context.

Batch commands for retrieval waves:
- `python scripts/citation_manager.py register-sources --jsonl [sources_batch.jsonl] --dir [run_folder]`
- `python scripts/evidence_store.py add-batch --jsonl [evidence_batch.jsonl] --dir [run_folder]`
- `python scripts/run_trace.py provider-call --dir [run_folder] --provider [provider] --tool [tool] --query "[query]" --lane-id [lane_id] --query-family-id [query_family_id] --result-count [n] --retained-source-count [n]`
""",
            ResearchPhase.TRIANGULATE: f"""
# {phase_label(phase)}

Validate material claims across independent sources. Preserve source tier, document date, retrieved date,
and evidence span for investment-sensitive, clinical, regulatory, financial, commercial, and scientific claims.
Resolve conflicts by primary-source priority and disclose unresolved gaps.
""",
            ResearchPhase.OUTLINE_REFINEMENT: f"""
# {phase_label(phase)}

Revise the outline based on evidence actually gathered. Promote well-supported emergent themes, demote or
remove thin sections, and record bounded gaps rather than forcing unsupported sections.
""",
            ResearchPhase.SYNTHESIZE: f"""
# {phase_label(phase)}

Do not draft report prose while retrieval is still active. Rerun `python scripts/run_trace.py coverage --dir [run_folder]`
and confirm `coverage_map.json.overall.status` is covered, or every remaining lane is bounded/gap_disclosed
with rationale, before final narrative drafting begins.

Draft section-level analysis from persisted ledgers and the evidence-driven outline. After each drafted section,
write/update its CitationAuditor checkpoint under `audit/section_citation_issues/` before drafting the next section.
Extract atomic claims after drafting and run deterministic support checks before packaging.

Required commands:
- `python scripts/extract_claims.py extract --report [draft.md] --dir [run_folder]`
- `python scripts/verify_claim_support.py verify --dir [run_folder] --strict`
""",
            ResearchPhase.CRITIQUE: f"""
# {phase_label(phase)}

Run adversarial review for logic, source balance, unsupported claims, missing counterevidence, and hidden
assumptions. Convert unsupported factual content into limitations, synthesis, or delta-retrieval targets.
""",
            ResearchPhase.REFINE: f"""
# {phase_label(phase)}

Apply critique findings, run targeted delta retrieval where needed, and update the affected report sections,
claims ledger, evidence ledger, and coverage map.
""",
            ResearchPhase.AUDIT: f"""
# {phase_label(phase)}

Run CitationAuditor and GapAuditor before delivery. Fix critical citation issues, unsupported evidence spans,
and critical coverage gaps before packaging.

Required commands:
- `python scripts/citation_manager.py assign-display-numbers --dir [run_folder] --write --order-from-report [draft.md]`
- `python scripts/delivery_gate.py --dir [run_folder] --report [draft.md] --strict --semantic --require-section-citation-audits`
""",
            ResearchPhase.CROSS_MODEL_CRITIQUE: f"""
# {phase_label(phase)}

Optional advisory review. Use it to find blind spots and delta-retrieval targets; it is not a hard delivery
gate by itself.

Example command:
- `python scripts/cross_model_critique.py run --dir [run_folder] --report [draft.md] --reviewer {default_cross_model_reviewer()} --timeout 600`
""",
            ResearchPhase.PACKAGE: f"""
# {phase_label(phase)}

Package the final report only after strict delivery gates pass. Keep the narrative report body focused; do not
append a long bibliography unless explicitly requested. Store full source/evidence/claim metadata in artifacts.
Per-section CitationAuditor JSON files under `audit/section_citation_issues/` are required for strict package delivery.

Required commands:
- `python scripts/delivery_gate.py --dir [run_folder] --report [report.md] --strict --semantic --require-section-citation-audits`
- `python scripts/md_to_html.py [report.md] --out [report.html] --run-dir [run_folder]`
""",
        }
        return instructions[phase].strip() + '\n'

    def render_mode_instructions(
        self,
        query: str,
        include_optional: bool = False,
        as_json: bool = False,
    ) -> str:
        phases = self._get_phases_for_mode(include_optional=include_optional)
        if as_json:
            return json.dumps({
                'version': ENGINE_VERSION,
                'query': query,
                'mode': self.mode.value,
                'orchestrator': False,
                'state_model': 'external_ledgers',
                'deprecated_classes': ['Source', 'ResearchState'],
                'phases': phase_manifest(self.mode, include_optional=include_optional),
            }, indent=2)

        lines = [
            '# Deep Research Phase Instructions',
            '',
            f'Query: {query}',
            f'Mode: {self.mode.value}',
            f'Version: {ENGINE_VERSION}',
            '',
            'This helper prints phase instructions only. It does not execute retrieval, spawn agents,',
            'or maintain authoritative research state. Use the run manifest, plan, ledgers, and gates.',
            '',
        ]
        for phase in phases:
            lines.append(self.get_phase_instructions(phase))
        return '\n'.join(lines)

    def execute_phase(self, phase: ResearchPhase | str) -> dict[str, Any]:
        phase = coerce_phase(phase)
        print(self.get_phase_instructions(phase))
        return {
            'phase': phase.value,
            'phase_number': PHASE_METADATA[phase]['number'],
            'status': 'instructions_displayed',
            'timestamp': utc_now(),
            'orchestrator': False,
        }

    def run_pipeline(self, query: str) -> str:
        """Deprecated: return instructions instead of executing a pipeline."""
        warnings.warn(
            'ResearchEngine.run_pipeline is deprecated; this helper only renders phase instructions.',
            DeprecationWarning,
            stacklevel=2,
        )
        return self.render_mode_instructions(query)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Deep Research phase instruction provider',
    )
    parser.add_argument('--query', '-q', default='', help='Research question or topic')
    parser.add_argument(
        '--mode',
        '-m',
        choices=[mode.value for mode in ResearchMode],
        default=ResearchMode.STANDARD.value,
        help='Research depth mode',
    )
    parser.add_argument(
        '--phase',
        help='Print one phase only. Accepts keys such as retrieve, 4.5, audit, or 7.6.',
    )
    parser.add_argument(
        '--include-optional',
        action='store_true',
        help='Include optional Phase 7.6 in mode-level output.',
    )
    parser.add_argument('--json', action='store_true', help='Print machine-readable phase manifest')
    parser.add_argument(
        '--resume',
        help='Deprecated. Validate that a legacy state file exists, then print migration guidance.',
    )
    args = parser.parse_args()

    if args.resume:
        state_file = Path(args.resume)
        if not state_file.exists():
            print(f'Error: State file not found: {state_file}', file=sys.stderr)
            sys.exit(1)
        print(
            'Legacy ResearchState resume is deprecated. Use run_manifest.json, plan.json, '
            'coverage_map.json, and the JSONL ledgers for continuation.',
            file=sys.stderr,
        )

    engine = ResearchEngine(mode=args.mode)
    if args.phase:
        phase = coerce_phase(args.phase)
        if args.json:
            print(json.dumps({
                'version': ENGINE_VERSION,
                'phase': phase.value,
                'number': PHASE_METADATA[phase]['number'],
                'name': PHASE_METADATA[phase]['name'],
                'instructions': engine.get_phase_instructions(phase),
            }, indent=2))
        else:
            print(engine.get_phase_instructions(phase))
        return

    print(engine.render_mode_instructions(args.query, include_optional=args.include_optional, as_json=args.json))


if __name__ == '__main__':
    main()
