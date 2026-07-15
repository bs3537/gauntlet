#!/usr/bin/env python3
"""
Citation Verification Script

Catches fabricated citations by checking:
1. DOI resolution (via doi.org)
2. Basic metadata matching (title similarity, year match)
3. URL accessibility verification
4. Hallucination pattern detection (generic titles, suspicious patterns)
5. Flags suspicious entries for manual review

Usage:
    python verify_citations.py --report [path]
    python verify_citations.py --report [path] --strict  # Fail on any unverified

Does NOT require API keys - uses free DOI resolver and heuristics.
"""

import sys
import argparse
import re
import os
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from urllib import request, error
from urllib.parse import quote, urlsplit
import json
from datetime import datetime


USER_AGENT = 'DeepResearchCitationVerifier/3.1 contact=research-integrity@example.com'
RESTRICTED_ACCESS_HOSTS = (
    'bloomberg.com',
    'ft.com',
    'jstor.org',
    'nature.com',
    'nejm.org',
    'sciencedirect.com',
    'sec.gov',
    'statnews.com',
    'thelancet.com',
    'wsj.com',
)

class CitationVerifier:
    """Verify citations in research report"""

    def __init__(self, report_path: Path, strict_mode: bool = False, max_workers: int = 4, cache_path: Path | None = None):
        self.report_path = report_path
        self.strict_mode = strict_mode
        self.max_workers = max(1, min(int(max_workers or 4), 16))
        self.cache_path = cache_path or (report_path.parent / '.citation_verification_cache.json')
        self.cache = self._load_cache()
        self.content = self._read_report()
        self.suspicious = []
        self.verified = []
        self.errors = []

        # Hallucination detection patterns (2025 CiteGuard enhancement)
        self.suspicious_patterns = [
            # Generic academic-sounding but fake patterns
            (r'^(A |An |The )?(Study|Analysis|Review|Survey|Investigation) (of|on|into)',
             "Generic academic title pattern"),
            (r'^(Recent|Current|Modern|Contemporary) (Advances|Developments|Trends) in',
             "Generic 'advances' title pattern"),
            # Too perfect, templated titles
            (r'^[A-Z][a-z]+ [A-Z][a-z]+: A (Comprehensive|Complete|Systematic) (Review|Analysis|Guide)$',
             "Too perfect, templated structure"),
        ]

    def _load_cache(self) -> Dict:
        if not self.cache_path or not self.cache_path.exists():
            return {'doi': {}, 'url': {}}
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            payload.setdefault('doi', {})
            payload.setdefault('url', {})
            return payload
        except Exception:
            return {'doi': {}, 'url': {}}

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, sort_keys=True)
                f.write('\n')
        except Exception as exc:
            self.errors.append(f'Could not write citation verification cache: {exc}')

    def _read_report(self) -> str:
        """Read report file"""
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"L ERROR: Cannot read report: {e}")
            sys.exit(1)

    def extract_sources_jsonl(self, sources_path: Path) -> List[Dict]:
        """Extract source entries from companion sources.jsonl."""
        entries = []

        with open(sources_path, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    self.errors.append(f"Invalid JSON in sources.jsonl line {idx}")
                    continue

                source_id = (
                    data.get('display_id')
                    or data.get('source_id')
                    or data.get('id')
                    or f"S{idx}"
                )
                title = data.get('title') or data.get('name') or data.get('raw_url') or data.get('url')
                url = data.get('url') or data.get('raw_url') or data.get('canonical_url')
                year = data.get('year') or data.get('published_year') or data.get('publication_year')
                doi = self.extract_doi(data)

                entries.append({
                    'num': str(source_id).strip('[]'),
                    'raw': json.dumps(data, sort_keys=True),
                    'year': str(year) if year else None,
                    'title': str(title) if title else None,
                    'doi': str(doi) if doi else None,
                    'url': str(url) if url else None
                })

        return entries

    def extract_doi(self, data: Dict) -> str | None:
        """Extract DOI from explicit field, canonical_locator, provider_ids, or URLs."""
        candidates = [
            data.get('doi'),
            data.get('DOI'),
            data.get('canonical_locator'),
            data.get('raw_url'),
            data.get('url'),
            data.get('canonical_url'),
        ]
        provider_ids = data.get('provider_ids') or {}
        if isinstance(provider_ids, dict):
            for key, value in provider_ids.items():
                if str(key).lower() in {'doi', 'crossref_doi'}:
                    candidates.append(value)

        for candidate in candidates:
            if not candidate:
                continue
            text = str(candidate).strip()
            match = re.search(r'(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/\S+)', text, re.IGNORECASE)
            if match:
                return match.group(1).rstrip('.,);]')
        return None

    def extract_bibliography(self) -> List[Dict]:
        """Extract sources from sources.jsonl, or bibliography if explicitly present."""
        sources_path = self.report_path.parent / 'sources.jsonl'
        if sources_path.exists():
            return self.extract_sources_jsonl(sources_path)

        pattern = r'## Bibliography(.*?)(?=##|\Z)'
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            self.errors.append("No sources.jsonl or Bibliography section found")
            return []

        bib_section = match.group(1)

        # Parse entries: [N] Author (Year). "Title". Venue. URL
        entries = []
        lines = bib_section.strip().split('\n')

        current_entry = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if starts with citation number [N]
            match_num = re.match(r'^\[(\d+)\]\s+(.+)$', line)
            if match_num:
                if current_entry:
                    entries.append(current_entry)

                num = match_num.group(1)
                rest = match_num.group(2)

                # Try to parse: Author (Year). "Title". Venue. URL
                year_match = re.search(r'\((\d{4})\)', rest)
                title_match = re.search(r'"([^"]+)"', rest)
                doi_match = re.search(r'doi\.org/(10\.\S+)', rest)
                url_match = re.search(r'https?://[^\s\)]+', rest)

                current_entry = {
                    'num': num,
                    'raw': rest,
                    'year': year_match.group(1) if year_match else None,
                    'title': title_match.group(1) if title_match else None,
                    'doi': doi_match.group(1) if doi_match else None,
                    'url': url_match.group(0) if url_match else None
                }
            elif current_entry:
                # Multi-line entry, append to raw
                current_entry['raw'] += ' ' + line

        if current_entry:
            entries.append(current_entry)

        return entries

    def verify_doi(self, doi: str) -> Tuple[bool, Dict]:
        """
        Verify DOI exists and get metadata.
        Returns (success, metadata_dict)
        """
        if not doi:
            return False, {}
        cache_key = doi.lower()
        if cache_key in self.cache['doi']:
            cached = self.cache['doi'][cache_key]
            return bool(cached.get('success')), cached.get('metadata') or {}

        try:
            # Use content negotiation to get JSON metadata
            url = f"https://doi.org/{quote(doi)}"
            req = request.Request(url)
            req.add_header('Accept', 'application/vnd.citationstyles.csl+json')
            req.add_header('User-Agent', USER_AGENT)

            with request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                metadata = {
                    'title': data.get('title', ''),
                    'year': data.get('issued', {}).get('date-parts', [[None]])[0][0],
                    'authors': [
                        f"{a.get('family', '')} {a.get('given', '')}"
                        for a in data.get('author', [])
                    ],
                    'venue': data.get('container-title', '')
                }
                self.cache['doi'][cache_key] = {'success': True, 'metadata': metadata}
                return True, metadata
        except error.HTTPError as e:
            if e.code == 404:
                metadata = {'error': 'DOI not found (404)'}
            else:
                metadata = {'error': f'HTTP {e.code}'}
            self.cache['doi'][cache_key] = {'success': False, 'metadata': metadata}
            return False, metadata
        except Exception as e:
            metadata = {'error': str(e)}
            self.cache['doi'][cache_key] = {'success': False, 'metadata': metadata}
            return False, metadata

    def is_restricted_access_host(self, url: str) -> bool:
        host = urlsplit(url).netloc.lower().removeprefix('www.')
        return any(host == allowed or host.endswith(f'.{allowed}') for allowed in RESTRICTED_ACCESS_HOSTS)

    def open_url_check(self, url: str, method: str):
        req = request.Request(url, method=method)
        req.add_header('User-Agent', USER_AGENT)
        req.add_header('Accept', 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8')
        return request.urlopen(req, timeout=10)

    def verify_url(self, url: str) -> Tuple[bool, str]:
        """
        Verify URL is accessible (2025 CiteGuard enhancement).
        Returns (accessible, status_message)
        """
        if not url:
            return False, "No URL"
        if url in self.cache['url']:
            cached = self.cache['url'][url]
            return bool(cached.get('success')), str(cached.get('status') or '')

        try:
            with self.open_url_check(url, 'HEAD') as response:
                if 200 <= response.status < 400:
                    status = "URL accessible"
                    self.cache['url'][url] = {'success': True, 'status': status}
                    return True, status
                status = f"HTTP {response.status}"
                self.cache['url'][url] = {'success': False, 'status': status}
                return False, status
        except error.HTTPError as e:
            if e.code in {403, 405}:
                try:
                    with self.open_url_check(url, 'GET') as response:
                        if 200 <= response.status < 400:
                            status = "URL accessible via GET fallback"
                            self.cache['url'][url] = {'success': True, 'status': status}
                            return True, status
                        status = f"HTTP {response.status}"
                        self.cache['url'][url] = {'success': False, 'status': status}
                        return False, status
                except error.HTTPError as get_error:
                    if get_error.code in {401, 403} and self.is_restricted_access_host(url):
                        status = f"Restricted/paywalled URL accepted as warning (HTTP {get_error.code})"
                        self.cache['url'][url] = {'success': True, 'status': status, 'warning': True}
                        return True, status
                    status = f"HTTP {get_error.code}"
                    self.cache['url'][url] = {'success': False, 'status': status}
                    return False, status
            if e.code in {401, 403} and self.is_restricted_access_host(url):
                status = f"Restricted/paywalled URL accepted as warning (HTTP {e.code})"
                self.cache['url'][url] = {'success': True, 'status': status, 'warning': True}
                return True, status
            status = f"HTTP {e.code}"
            self.cache['url'][url] = {'success': False, 'status': status}
            return False, status
        except error.URLError as e:
            status = f"URL error: {e.reason}"
            self.cache['url'][url] = {'success': False, 'status': status}
            return False, status
        except Exception as e:
            status = f"Connection error: {str(e)[:50]}"
            self.cache['url'][url] = {'success': False, 'status': status}
            return False, status

    def detect_hallucination_patterns(self, entry: Dict) -> List[str]:
        """
        Detect common LLM hallucination patterns in citations (2025 CiteGuard).
        Returns list of detected issues.
        """
        issues = []
        title = entry.get('title', '')

        if not title:
            return issues

        # Check against suspicious patterns
        for pattern, description in self.suspicious_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                issues.append(f"Suspicious title pattern: {description}")

        # Check for overly generic titles
        generic_words = ['overview', 'introduction', 'guide', 'handbook', 'manual']
        if any(word in title.lower() for word in generic_words) and len(title.split()) < 5:
            issues.append("Very generic short title")

        # Check for placeholder-like titles
        if any(x in title.lower() for x in ['tbd', 'todo', 'placeholder', 'example']):
            issues.append("Placeholder text in title")

        # Check for inconsistent metadata
        if entry.get('year'):
            year = int(entry['year'])
            current_year = datetime.now().year
            # Very recent without DOI or URL is suspicious
            if year >= current_year - 1 and not entry.get('doi') and not entry.get('url'):
                issues.append(f"Recent year ({year}) with no verification method")
            # Future year is definitely wrong
            if year > current_year:
                issues.append(f"Future year: {year} (current: {current_year})")
            # Very old with modern phrasing is suspicious
            if year < 2000 and any(word in title.lower() for word in ['ai', 'llm', 'gpt', 'transformer']):
                issues.append(f"Anachronistic: pre-2000 ({year}) citation mentioning modern AI terms")

        return issues

    def check_title_similarity(self, title1: str, title2: str) -> float:
        """
        Simple title similarity check (word overlap).
        Returns score 0.0-1.0
        """
        if not title1 or not title2:
            return 0.0

        # Normalize: lowercase, remove punctuation, split
        def normalize(s):
            s = s.lower()
            s = re.sub(r'[^\w\s]', ' ', s)
            return set(s.split())

        words1 = normalize(title1)
        words2 = normalize(title2)

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    def verify_entry(self, entry: Dict) -> Dict:
        """Verify a single bibliography entry (Enhanced 2025 with CiteGuard)"""
        result = {
            'num': entry['num'],
            'status': 'unknown',
            'issues': [],
            'warnings': [],
            'metadata': {},
            'verification_methods': []
        }

        # STEP 1: Run hallucination detection (CiteGuard 2025)
        hallucination_issues = self.detect_hallucination_patterns(entry)
        if hallucination_issues:
            result['issues'].extend(hallucination_issues)
            result['status'] = 'suspicious'

        # STEP 2: Has DOI?
        if entry['doi']:
            print(f"  [{entry['num']}] Checking DOI {entry['doi']}...", end=' ')
            success, metadata = self.verify_doi(entry['doi'])

            if success:
                result['metadata'] = metadata
                result['status'] = 'verified'
                print("")

                # Check title similarity if we have both
                if entry['title'] and metadata.get('title'):
                    similarity = self.check_title_similarity(
                        entry['title'],
                        metadata['title']
                    )

                    if similarity < 0.5:
                        result['issues'].append(
                            f"Title mismatch (similarity: {similarity:.1%})"
                        )
                        result['status'] = 'suspicious'

                # Check year match
                if entry['year'] and metadata.get('year'):
                    if int(entry['year']) != int(metadata['year']):
                        result['issues'].append(
                            f"Year mismatch: report says {entry['year']}, DOI says {metadata['year']}"
                        )
                        result['status'] = 'suspicious'

            else:
                print(f"✗ {metadata.get('error', 'Failed')}")
                result['status'] = 'unverified'
                result['issues'].append(f"DOI resolution failed: {metadata.get('error', 'unknown')}")

        # STEP 3: Check URL accessibility (if no DOI or DOI failed)
        if entry['url'] and result['status'] != 'verified':
            url_ok, url_status = self.verify_url(entry['url'])
            if url_ok:
                result['verification_methods'].append('URL')
                # Upgrade status if URL verifies
                if result['status'] in ['unknown', 'no_doi', 'unverified']:
                    result['status'] = 'url_verified'
                print(f"  [{entry['num']}] URL accessible ✓")
                if 'warning' in url_status.lower() or 'restricted' in url_status.lower() or 'paywall' in url_status.lower():
                    result['warnings'].append(url_status)
            else:
                result['issues'].append(f"URL check failed: {url_status}")

        # STEP 4: Final fallback - no verification method
        if not entry['doi'] and not entry['url']:
            if 'No DOI provided' not in ' '.join(result['issues']):
                result['issues'].append("No DOI or URL - cannot verify")
            result['status'] = 'suspicious'

        return result

    def verify_all(self):
        """Verify all bibliography entries"""
        print(f"\n{'='*60}")
        print(f"CITATION VERIFICATION: {self.report_path.name}")
        print(f"{'='*60}\n")

        entries = self.extract_bibliography()

        if not entries:
            print("No source registry or bibliography entries found\n")
            return False

        print(f"Found {len(entries)} citations\n")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(self.verify_entry, entries))
        self._save_cache()

        # Summarize
        print(f"\n{'='*60}")
        print(f"VERIFICATION SUMMARY")
        print(f"{'='*60}\n")

        verified = [r for r in results if r['status'] == 'verified']
        url_verified = [r for r in results if r['status'] == 'url_verified']
        suspicious = [r for r in results if r['status'] == 'suspicious']
        unverified = [r for r in results if r['status'] in ['unverified', 'no_doi', 'unknown']]

        print(f'DOI Verified: {len(verified)}/{len(results)}')
        print(f'URL Verified: {len(url_verified)}/{len(results)}')
        print(f'Suspicious: {len(suspicious)}/{len(results)}')
        print(f'Unverified: {len(unverified)}/{len(results)}')
        print()

        if suspicious:
            print('SUSPICIOUS CITATIONS (Manual Review Needed):')
            for r in suspicious:
                print(f"\n  [{r['num']}]")
                for issue in r['issues']:
                    print(f"    - {issue}")
            print()

        warning_results = [r for r in results if r.get('warnings')]
        if warning_results:
            print('CITATION WARNINGS:')
            for r in warning_results:
                for warning in r.get('warnings', []):
                    print(f"  [{r['num']}] {warning}")
            print()

        if unverified and len(unverified) > 0:
            print('UNVERIFIED CITATIONS (Could not check):')
            for r in unverified:
                print(f"  [{r['num']}] {r['issues'][0] if r['issues'] else 'Unknown'}")
            print()

        # Decision (Enhanced 2025 - includes URL-verified as acceptable)
        total_verified = len(verified) + len(url_verified)

        if suspicious:
            print('WARNING: Suspicious citations detected')
            if self.strict_mode:
                print('  STRICT MODE: Failing due to suspicious citations')
                return False
            else:
                print('  (Continuing in non-strict mode)')

        if self.strict_mode and unverified:
            print('STRICT MODE: Unverified citations found')
            return False

        if total_verified / len(results) < 0.5:
            print('WARNING: Less than 50% citations verified')
            return True  # Pass with warning
        else:
            print('CITATION VERIFICATION PASSED')
            return True


def main():
    parser = argparse.ArgumentParser(
        description="Verify citations in research report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python verify_citations.py --report report.md

Note: Requires internet connection to check DOIs.
Uses sources.jsonl when present; otherwise falls back to an explicit Bibliography section.
Uses free DOI resolver - no API key needed.
        """
    )

    parser.add_argument(
        '--report', '-r',
        type=str,
        required=True,
        help='Path to research report markdown file'
    )

    parser.add_argument(
        '--strict',
        action='store_true',
        help='Strict mode: fail on any unverified or suspicious citations'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=int(os.environ.get('DEEP_RESEARCH_VERIFY_CITATIONS_MAX_WORKERS', '4')),
        help='Maximum concurrent DOI/URL checks (default: 4, capped at 16)'
    )
    parser.add_argument(
        '--cache-file',
        type=str,
        help='Optional JSON cache path for DOI/URL verification results'
    )

    args = parser.parse_args()
    report_path = Path(args.report)

    if not report_path.exists():
        print(f"ERROR: Report file not found: {report_path}")
        sys.exit(1)

    verifier = CitationVerifier(
        report_path,
        strict_mode=args.strict,
        max_workers=args.max_workers,
        cache_path=Path(args.cache_file) if args.cache_file else None,
    )
    passed = verifier.verify_all()

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
