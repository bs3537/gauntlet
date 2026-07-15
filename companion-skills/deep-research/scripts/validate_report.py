#!/usr/bin/env python3
"""
Report Validation Script
Ensures research reports meet quality standards before delivery
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict


class ReportValidator:
    """Validates research report quality"""

    def __init__(self, report_path: Path):
        self.report_path = report_path
        self.content = self._read_report()
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def _read_report(self) -> str:
        """Read report file"""
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"❌ ERROR: Cannot read report: {e}")
            sys.exit(1)

    def validate(self) -> bool:
        """Run all validation checks"""
        print(f"\n{'='*60}")
        print(f"VALIDATING REPORT: {self.report_path.name}")
        print(f"{'='*60}\n")

        checks = [
            ("Executive Summary", self._check_executive_summary),
            ("Required Sections", self._check_required_sections),
            ("Citations", self._check_citations),
            ("Source Registry", self._check_source_registry),
            ("Placeholder Text", self._check_placeholders),
            ("Content Truncation", self._check_content_truncation),
            ("Word Count", self._check_word_count),
            ("Source Count", self._check_source_count),
            ("Broken Links", self._check_broken_references),
        ]

        for check_name, check_func in checks:
            print(f"⏳ Checking: {check_name}...", end=" ")
            passed = check_func()
            if passed:
                print("✅ PASS")
            else:
                print("❌ FAIL")

        self._print_summary()

        return len(self.errors) == 0

    def _check_executive_summary(self) -> bool:
        """Check executive summary exists and is 200-400 words"""
        pattern = r'## Executive Summary(.*?)(?=##|\Z)'
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            self.errors.append("Missing 'Executive Summary' section")
            return False

        summary = match.group(1).strip()
        word_count = len(summary.split())

        if word_count > 400:
            self.warnings.append(f"Executive summary too long: {word_count} words (should be ≤400)")

        if word_count < 50:
            self.warnings.append(f"Executive summary too short: {word_count} words (should be ≥50)")

        return True

    def _check_required_sections(self) -> bool:
        """Check all required sections are present"""
        required = [
            "Executive Summary",
            "Introduction",
            "Main Analysis",
            "Synthesis",
            "Limitations",
            "Recommendations",
            "Methodology"
        ]

        # Recommended sections (warnings if missing, not errors)
        recommended = [
            "Counterevidence Register",
            "Claims-Evidence Table"
        ]

        missing = []
        for section in required:
            if not re.search(rf'##.*{section}', self.content, re.IGNORECASE):
                missing.append(section)

        if missing:
            self.errors.append(f"Missing sections: {', '.join(missing)}")
            return False

        # Check recommended sections (warnings only)
        missing_recommended = []
        for section in recommended:
            if not re.search(rf'##.*{section}', self.content, re.IGNORECASE):
                missing_recommended.append(section)

        if missing_recommended:
            self.warnings.append(f"Missing recommended sections (for academic rigor): {', '.join(missing_recommended)}")

        return True

    def _citation_refs(self) -> List[str]:
        """Find compact source labels such as [1], [S1], or [E12]."""
        return re.findall(r'\[(?:S|E)?\d+\]', self.content)

    def _check_citations(self) -> bool:
        """Check compact source labels are present"""
        citations = self._citation_refs()

        if not citations:
            self.errors.append("No compact source labels found in report")
            return False

        unique_citations = set(citations)

        if len(unique_citations) < 10:
            self.warnings.append(f"Only {len(unique_citations)} unique source labels found (recommended: ≥10)")

        # Check consecutive numbering only for pure numeric citations.
        numeric_only = [c.strip('[]') for c in unique_citations if re.match(r'^\[\d+\]$', c)]
        citation_nums = sorted([int(c) for c in numeric_only])
        if citation_nums:
            max_citation = max(citation_nums)
            expected = set(range(1, max_citation + 1))
            missing = expected - set(citation_nums)

            if missing:
                self.warnings.append(f"Non-consecutive citation numbers, missing: {sorted(missing)}")

        return True

    def _check_source_registry(self) -> bool:
        """Check bibliography is not required and source artifacts exist when available."""
        artifact_names = [
            'sources.jsonl',
            'evidence.jsonl',
            'claims.jsonl',
            'source_notes.md',
        ]
        found_artifacts = [
            name for name in artifact_names
            if (self.report_path.parent / name).exists()
        ]
        notes_dir = self.report_path.parent / 'notes'
        if notes_dir.exists() and any(notes_dir.glob('*.md')):
            found_artifacts.append('notes/*.md')

        if not found_artifacts:
            self.warnings.append(
                "No external source artifacts found next to report "
                "(expected sources.jsonl/evidence.jsonl/claims.jsonl when available)"
            )

        # Full bibliography is optional. If present, only check it is not truncated.
        pattern = r'## Bibliography(.*?)(?=##|\Z)'
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            return True

        bib_section = match.group(1)

        # CRITICAL: Check for truncation placeholders (2025 CiteGuard enhancement)
        truncation_patterns = [
            (r'\[\d+-\d+\]', 'Citation range (e.g., [8-75])'),
            (r'Additional.*citations', 'Phrase "Additional citations"'),
            (r'would be included', 'Phrase "would be included"'),
            (r'\[\.\.\.continue', 'Pattern "[...continue"'),
            (r'\[Continue with', 'Pattern "[Continue with"'),
            (r'etc\.(?!\w)', 'Standalone "etc."'),
            (r'and so on', 'Phrase "and so on"'),
        ]

        for pattern_re, description in truncation_patterns:
            if re.search(pattern_re, bib_section, re.IGNORECASE):
                self.errors.append(f"⚠️ CRITICAL: Bibliography contains truncation placeholder: {description}")
                self.errors.append(f"   Remove the placeholder or move full source details to sources.jsonl")
                return False

        self.warnings.append(
            "Report contains a Bibliography section; keep this only when explicitly requested"
        )

        return True

    def _check_placeholders(self) -> bool:
        """Check for placeholder text that shouldn't be in final report"""
        placeholders = [
            'TBD', 'TODO', 'FIXME', 'XXX',
            '[citation needed]', '[needs citation]',
            '[placeholder]', '[TODO]', '[TBD]'
        ]

        found_placeholders = []
        for placeholder in placeholders:
            if placeholder in self.content:
                found_placeholders.append(placeholder)

        if found_placeholders:
            self.errors.append(f"Found placeholder text: {', '.join(found_placeholders)}")
            return False

        return True

    def _check_content_truncation(self) -> bool:
        """Check for content truncation patterns (2025 Progressive Assembly enhancement)"""
        truncation_patterns = [
            (r'Content continues', 'Phrase "Content continues"'),
            (r'Due to length', 'Phrase "Due to length"'),
            (r'would continue', 'Phrase "would continue"'),
            (r'\[Sections \d+-\d+', 'Pattern "[Sections X-Y"'),
            (r'Additional sections', 'Phrase "Additional sections"'),
            (r'comprehensive.*word document that continues', 'Pattern "comprehensive...document that continues"'),
        ]

        for pattern_re, description in truncation_patterns:
            if re.search(pattern_re, self.content, re.IGNORECASE):
                self.errors.append(f"⚠️ CRITICAL: Content truncation detected: {description}")
                self.errors.append(f"   Report is INCOMPLETE and UNUSABLE - regenerate with progressive assembly")
                return False

        return True

    def _check_word_count(self) -> bool:
        """Check overall report length"""
        word_count = len(self.content.split())

        if word_count < 500:
            self.warnings.append(f"Report is very short: {word_count} words (consider expanding)")
        # No upper limit warning - progressive assembly supports unlimited lengths

        return True

    def _check_source_count(self) -> bool:
        """Check minimum source count"""
        sources_path = self.report_path.parent / 'sources.jsonl'
        if sources_path.exists():
            with open(sources_path, 'r', encoding='utf-8') as f:
                source_count = sum(1 for line in f if line.strip())
        else:
            source_count = len(set(self._citation_refs()))

        if source_count < 10:
            self.warnings.append(f"Only {source_count} sources (recommended: ≥10)")

        return True

    def _check_broken_references(self) -> bool:
        """Check for broken internal references"""
        # Find all markdown links [text](./path)
        internal_links = re.findall(r'\[.*?\]\((\.\/.*?)\)', self.content)

        broken = []
        for link in internal_links:
            # Remove anchor if present
            link_path = link.split('#')[0]
            full_path = self.report_path.parent / link_path

            if not full_path.exists():
                broken.append(link)

        if broken:
            self.errors.append(f"Broken internal links: {', '.join(broken)}")
            return False

        return True

    def _print_summary(self):
        """Print validation summary"""
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*60}\n")

        if self.errors:
            print(f"❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"   • {error}")
            print()

        if self.warnings:
            print(f"⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")
            print()

        if not self.errors and not self.warnings:
            print("✅ ALL CHECKS PASSED - Report meets quality standards!\n")
        elif not self.errors:
            print("✅ VALIDATION PASSED (with warnings)\n")
        else:
            print("❌ VALIDATION FAILED - Please fix errors before delivery\n")


def main():
    parser = argparse.ArgumentParser(
        description="Validate research report quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_report.py --report report.md
  python validate_report.py -r ~/.claude/research_output/research_report_20251104_153045.md
        """
    )

    parser.add_argument(
        '--report', '-r',
        type=str,
        required=True,
        help='Path to research report markdown file'
    )

    args = parser.parse_args()

    report_path = Path(args.report)

    if not report_path.exists():
        print(f"❌ ERROR: Report file not found: {report_path}")
        sys.exit(1)

    validator = ReportValidator(report_path)
    passed = validator.validate()

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
